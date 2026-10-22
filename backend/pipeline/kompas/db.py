import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config
from .periods import utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- Everything a connector fetched, stored as received (after HTML clean-up).
-- kind: story | hiring_post | repo | repo_count | paper | paper_count | paper_baseline | occupation_stat
CREATE TABLE IF NOT EXISTS raw_doc (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  url TEXT,
  title TEXT,
  text TEXT,
  topics TEXT NOT NULL DEFAULT '[]',
  published_at TEXT NOT NULL,      -- when it became public; drives the no-look-ahead rule
  period TEXT NOT NULL,
  metrics TEXT NOT NULL DEFAULT '{}',
  content_hash TEXT NOT NULL,
  tagged_hash TEXT,                -- content_hash at last tagging; NULL = needs tagging
  fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS raw_doc_source_period ON raw_doc(source, kind, period);

-- Point-in-time observations (e.g. star counts), so history never uses today's numbers.
CREATE TABLE IF NOT EXISTS artifact_metric (
  artifact_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (artifact_id, observed_at, name)
);

CREATE TABLE IF NOT EXISTS tag (
  doc_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  method TEXT NOT NULL,            -- topic | topic_weak | dictionary | alias | query
  span TEXT,
  PRIMARY KEY (doc_id, concept_id)
);
CREATE INDEX IF NOT EXISTS tag_concept ON tag(concept_id);

CREATE TABLE IF NOT EXISTS snapshot (
  id TEXT PRIMARY KEY,
  as_of TEXT NOT NULL,
  created_at TEXT NOT NULL,
  params TEXT NOT NULL,
  sources TEXT NOT NULL,
  curated_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_status (
  snapshot_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  status TEXT NOT NULL,
  family_id TEXT,
  family_status TEXT,
  projected TEXT NOT NULL,
  rungs TEXT NOT NULL,
  evidence_ids TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, concept_id)
);

CREATE TABLE IF NOT EXISTS evidence (
  snapshot_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT,
  url TEXT,
  published_at TEXT NOT NULL,
  value REAL,
  value_label TEXT,
  concept_ids TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, id)
);

CREATE TABLE IF NOT EXISTS snapshot_feed (
  snapshot_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  item TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, rank)
);

CREATE TABLE IF NOT EXISTS change (
  snapshot_id TEXT NOT NULL,
  from_snapshot TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  field TEXT NOT NULL,
  old TEXT,
  new TEXT,
  reason TEXT,
  evidence_ids TEXT NOT NULL
);

-- Live feed: tagged artifacts ranked by momentum, updated by the pollers.
CREATE TABLE IF NOT EXISTS feed_item (
  artifact_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT,
  url TEXT,
  published_at TEXT NOT NULL,
  momentum REAL NOT NULL,
  momentum_raw REAL NOT NULL,
  momentum_label TEXT NOT NULL,
  concept_ids TEXT NOT NULL,
  counts TEXT NOT NULL DEFAULT '{}', -- raw points / stars and repo description, for display
  first_seen TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Append-only event log behind the SSE stream (supports Last-Event-ID and replay).
CREATE TABLE IF NOT EXISTS feed_event (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  type TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  mode TEXT NOT NULL,              -- backfill | live
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER,
  n_docs INTEGER,
  error TEXT
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection):
    """Adds columns introduced after a database was first created."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(concept_status)")}
    if "family_id" not in cols:
        conn.execute("ALTER TABLE concept_status ADD COLUMN family_id TEXT")
    if "counts" not in {r["name"] for r in conn.execute("PRAGMA table_info(feed_item)")}:
        conn.execute("ALTER TABLE feed_item ADD COLUMN counts TEXT NOT NULL DEFAULT '{}'")


def content_hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def upsert_doc(conn: sqlite3.Connection, doc: dict) -> bool:
    """Insert or update a raw doc. Returns True if the doc is new."""
    topics = json.dumps(doc.get("topics") or [])
    metrics = json.dumps(doc.get("metrics") or {}, sort_keys=True)
    chash = content_hash(doc.get("title"), doc.get("text"), topics)
    existed = conn.execute("SELECT 1 FROM raw_doc WHERE id = ?", (doc["id"],)).fetchone()
    conn.execute(
        """
        INSERT INTO raw_doc (id, source, kind, url, title, text, topics, published_at, period,
                             metrics, content_hash, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          url = excluded.url, title = excluded.title, text = excluded.text, topics = excluded.topics,
          metrics = excluded.metrics, content_hash = excluded.content_hash, fetched_at = excluded.fetched_at
        """,
        (doc["id"], doc["source"], doc["kind"], doc.get("url"), doc.get("title"), doc.get("text"), topics,
         doc["published_at"], doc["period"], metrics, chash, utcnow()),
    )
    return existed is None


def has_doc(conn: sqlite3.Connection, doc_id: str) -> bool:
    return conn.execute("SELECT 1 FROM raw_doc WHERE id = ?", (doc_id,)).fetchone() is not None


def record_metric(conn: sqlite3.Connection, artifact_id: str, name: str, value: float, observed_at: str | None = None):
    conn.execute(
        "INSERT OR REPLACE INTO artifact_metric (artifact_id, observed_at, name, value) VALUES (?, ?, ?, ?)",
        (artifact_id, observed_at or utcnow(), name, value),
    )


@contextmanager
def fetch_run(conn: sqlite3.Connection, source: str, mode: str):
    """Logs a fetch run; the yielded dict's 'n' is the number of docs written."""
    cur = conn.execute(
        "INSERT INTO fetch_log (source, mode, started_at) VALUES (?, ?, ?)", (source, mode, utcnow())
    )
    run_id, state = cur.lastrowid, {"n": 0}
    conn.commit()
    try:
        yield state
    except Exception as e:
        conn.rollback()
        conn.execute(
            "UPDATE fetch_log SET finished_at = ?, ok = 0, n_docs = ?, error = ? WHERE id = ?",
            (utcnow(), state["n"], repr(e)[:500], run_id),
        )
        conn.commit()
        raise
    conn.execute(
        "UPDATE fetch_log SET finished_at = ?, ok = 1, n_docs = ? WHERE id = ?", (utcnow(), state["n"], run_id)
    )
    conn.commit()


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
