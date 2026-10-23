import hashlib
import json
import re
import sqlite3
from pathlib import Path

from . import config
from .document import Document
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

-- JSearch answers, cached for a day (connectors/jsearch.py).
CREATE TABLE IF NOT EXISTS job_cache (query TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS course_cache (provider TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, payload TEXT NOT NULL);

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
    """The local SQLite file, or Postgres (Supabase) when DATABASE_URL is set and no file is asked for.
    Both connections take the same SQL (SQLite's dialect, translated in kompas/pg.py)."""
    url = None if path else config.database_url()
    if url:
        from . import pg
        return pg.connect(url)
    path = path or config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init(conn)
    return conn


def init(conn: sqlite3.Connection):
    """Creates the schema and brings it to the current version."""
    conn.executescript(SCHEMA)
    _migrate(conn)
    migrate(conn)


def _migrate(conn: sqlite3.Connection):
    """Adds columns introduced before schema versioning existed."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(concept_status)")}
    if "family_id" not in cols:
        conn.execute("ALTER TABLE concept_status ADD COLUMN family_id TEXT")
    if "counts" not in {r["name"] for r in conn.execute("PRAGMA table_info(feed_item)")}:
        conn.execute("ALTER TABLE feed_item ADD COLUMN counts TEXT NOT NULL DEFAULT '{}'")
    conn.commit()


# ---------- versioned migrations ----------
#
# Each migration runs once, inside one transaction, and records the new version in meta.schema_version.
# Migrations only add columns, tables and indexes, so an existing database keeps all of its rows.
# If one fails, the transaction rolls back and the database stays at the previous version.


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn, table: str, columns: dict[str, str]):
    have = _columns(conn, table)
    for name, decl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def legacy_source_id(doc_id: str, kind: str) -> str:
    """Native id for docs stored before source_id existed: the part of the Kompas id after the prefix."""
    rest = doc_id.split(":", 1)[1] if ":" in doc_id else doc_id
    if kind == "paper":  # ax:<arxiv id with version>:<concept>
        return re.sub(r"v\d+$", "", rest.rsplit(":", 1)[0])
    return rest


def _m1_ingestion(conn):
    """Canonical document fields, run statistics, checkpoints, locks and validation findings."""
    _add_columns(conn, "raw_doc", {
        "source_id": "TEXT",       # the source's own identifier
        "updated_at": "TEXT",      # source-reported update time, if any
        "first_seen_at": "TEXT",   # first successful observation by Kompas
        "last_seen_at": "TEXT",    # latest successful observation
        "raw_payload": "TEXT",     # source record as received (JSON), minus fields we don't keep
    })
    # Rows from before this migration: fetched_at is the only observation time we have. It is the last
    # fetch, so first_seen_at is an upper bound for these rows (the README says so).
    conn.execute("UPDATE raw_doc SET first_seen_at = fetched_at WHERE first_seen_at IS NULL")
    conn.execute("UPDATE raw_doc SET last_seen_at = fetched_at WHERE last_seen_at IS NULL")
    rows = conn.execute("SELECT id, kind FROM raw_doc WHERE source_id IS NULL").fetchall()
    conn.executemany("UPDATE raw_doc SET source_id = ? WHERE id = ?",
                     [(legacy_source_id(r["id"], r["kind"]), r["id"]) for r in rows])
    conn.execute("CREATE INDEX IF NOT EXISTS raw_doc_source_id ON raw_doc(source, source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS raw_doc_source_published ON raw_doc(source, published_at)")

    _add_columns(conn, "fetch_log", {
        "stream": "TEXT",                 # e.g. counts | live | groups; a source can have several
        "status": "TEXT",                 # running | ok | no_change | partial | failed | invalid | interrupted
        "n_fetched": "INTEGER DEFAULT 0",
        "n_inserted": "INTEGER DEFAULT 0",
        "n_updated": "INTEGER DEFAULT 0",
        "n_unchanged": "INTEGER DEFAULT 0",
        "n_skipped": "INTEGER DEFAULT 0",
        "n_failed": "INTEGER DEFAULT 0",
        "n_retries": "INTEGER DEFAULT 0",
        "error_category": "TEXT",
        "checkpoint": "TEXT",             # checkpoint position when the run ended
        "latest_published_at": "TEXT",    # newest publication time seen in this run
        "detail": "TEXT",                 # JSON: partial reasons, dataset notes
    })
    conn.execute("UPDATE fetch_log SET stream = mode WHERE stream IS NULL")
    conn.execute("UPDATE fetch_log SET status = CASE WHEN ok = 1 THEN 'ok' WHEN ok = 0 THEN 'failed' "
                 "ELSE 'interrupted' END WHERE status IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS fetch_log_stream ON fetch_log(source, stream, id)")

    # executescript() would commit the migration's transaction early, so statements run one by one
    for statement in """
    -- Where each incremental stream got to. Written in the same transaction as the data it covers.
    CREATE TABLE IF NOT EXISTS checkpoint (
      source TEXT NOT NULL,
      stream TEXT NOT NULL,
      cursor TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      run_id INTEGER,
      PRIMARY KEY (source, stream)
    );

    -- One writer per stream. A lease expires on its own if a process dies without releasing it.
    CREATE TABLE IF NOT EXISTS ingest_lock (
      source TEXT NOT NULL,
      stream TEXT NOT NULL,
      owner TEXT NOT NULL,
      run_id INTEGER,
      acquired_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      PRIMARY KEY (source, stream)
    );

    -- Record-level failures and dataset validation findings, per run.
    CREATE TABLE IF NOT EXISTS ingest_error (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER,
      source TEXT NOT NULL,
      stream TEXT,
      at TEXT NOT NULL,
      severity TEXT NOT NULL,      -- error | warning
      category TEXT NOT NULL,
      ref TEXT,
      message TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ingest_error_run ON ingest_error(run_id)
    """.split(";"):
        conn.execute(statement)


def _m2_legacy_streams(conn):
    """Runs logged before streams existed were named after their mode; give them the stream they fed."""
    for source, stream in (("arxiv", "monthly"), ("github", "counts"), ("hn_hiring", "threads"),
                           ("dosm_jmi", "occupations")):
        conn.execute("UPDATE fetch_log SET stream = ? WHERE source = ? AND stream = 'backfill'", (stream, source))


def _m3_alias_suggestions(conn):
    """LLM-suggested aliases waiting for a person's decision (kompas/suggest.py)."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS alias_suggestion (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      doc_id TEXT NOT NULL UNIQUE,     -- the unmatched item that was asked about (once)
      item_title TEXT,
      concept_id TEXT,
      alias TEXT,
      case_sensitive INTEGER,
      reason TEXT,
      model TEXT NOT NULL,
      status TEXT NOT NULL,            -- pending | approved | rejected | rejected_by_checks | no_match
      check_note TEXT,                 -- why the checks refused it
      reach INTEGER,                   -- stored items the alias would tag
      created_at TEXT NOT NULL,
      decided_at TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS alias_suggestion_status ON alias_suggestion(status)")


MIGRATIONS = [(1, _m1_ingestion), (2, _m2_legacy_streams), (3, _m3_alias_suggestions)]
SCHEMA_VERSION = MIGRATIONS[-1][0]


def schema_version(conn) -> int:
    return int(get_meta(conn, "schema_version") or 0)


def migrate(conn: sqlite3.Connection):
    for version, fn in MIGRATIONS:
        if schema_version(conn) >= version:
            continue
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        try:
            # re-check under the write lock: another process may have just migrated
            if schema_version(conn) < version:
                fn(conn)
                set_meta(conn, "schema_version", str(version))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


# ---------- documents and observations ----------


def content_hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def save_doc(conn: sqlite3.Connection, doc: Document, now: str | None = None) -> str:
    """Insert or update one document. Returns 'inserted', 'updated' (content, metrics or source update
    time changed) or 'unchanged' (only the observation times move).

    published_at and period are never rewritten: they say when the record became public, and changing
    them later would let old snapshots see data they couldn't have had."""
    doc.validate()
    now = now or utcnow()
    topics = json.dumps(doc.topics or [])
    metrics = json.dumps(doc.metrics or {}, sort_keys=True)
    chash = content_hash(doc.title, doc.text, topics)
    payload = doc.payload_json()
    row = conn.execute("SELECT content_hash, metrics, updated_at FROM raw_doc WHERE id = ?", (doc.id,)).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO raw_doc (id, source, kind, source_id, url, title, text, topics, published_at, updated_at,
                                 period, metrics, content_hash, raw_payload, first_seen_at, last_seen_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc.id, doc.source, doc.kind, doc.source_id, doc.url, doc.title, doc.text, topics, doc.published_at,
             doc.updated_at, doc.period, metrics, chash, payload, now, now, now),
        )
        return "inserted"
    changed = row["content_hash"] != chash or row["metrics"] != metrics or row["updated_at"] != doc.updated_at
    conn.execute(
        """
        UPDATE raw_doc SET source_id = COALESCE(?, source_id), url = ?, title = ?, text = ?, topics = ?,
          updated_at = ?, metrics = ?, content_hash = ?, raw_payload = COALESCE(?, raw_payload),
          last_seen_at = ?, fetched_at = ?
        WHERE id = ?
        """,
        (doc.source_id, doc.url, doc.title, doc.text, topics, doc.updated_at, metrics, chash, payload, now, now,
         doc.id),
    )
    return "updated" if changed else "unchanged"


def upsert_doc(conn: sqlite3.Connection, doc: dict) -> bool:
    """Dict form of save_doc, kept for tests and older callers. Returns True if the doc is new."""
    return save_doc(conn, Document.from_dict(doc)) == "inserted"


def has_doc(conn: sqlite3.Connection, doc_id: str) -> bool:
    return conn.execute("SELECT 1 FROM raw_doc WHERE id = ?", (doc_id,)).fetchone() is not None


def record_metric(conn: sqlite3.Connection, artifact_id: str, name: str, value: float, observed_at: str | None = None):
    """Point-in-time observation. Observations are history: a new one never replaces an older one, and the
    same (artifact, time, name) written twice keeps one row."""
    conn.execute(
        "INSERT INTO artifact_metric (artifact_id, observed_at, name, value) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (artifact_id, observed_at, name) DO UPDATE SET value = excluded.value",
        (artifact_id, observed_at or utcnow(), name, value),
    )


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str):
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                 (key, value))
