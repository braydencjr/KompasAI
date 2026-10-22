import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from kompas import config, db, ingest
from kompas.document import Document
from kompas.http import FetchError
from kompas.ingest import DatasetInvalid, Options, SourceBusy, start_run
from kompas.periods import iso


def story(i: int, title: str = "Show HN: a thing", points: int = 150, published="2026-09-02T10:00:00Z") -> Document:
    return Document(id=f"hn:{i}", source="hn_front", kind="story", source_id=str(i), url=f"https://x.test/{i}",
                    title=title, text="", published_at=published, period=published[:7], metrics={"points": points},
                    raw_payload={"id": i})


def last_run(conn, source="hn_front", stream="backfill"):
    return conn.execute("SELECT * FROM fetch_log WHERE source = ? AND stream = ? ORDER BY id DESC LIMIT 1",
                        (source, stream)).fetchone()


# ---------- documents ----------


def test_save_is_idempotent_and_tracks_observation_times(conn):
    assert db.save_doc(conn, story(1), now="2026-09-03T00:00:00Z") == "inserted"
    assert db.save_doc(conn, story(1), now="2026-09-04T00:00:00Z") == "unchanged"
    assert db.save_doc(conn, story(1, points=300), now="2026-09-05T00:00:00Z") == "updated"
    # the source can't move a record in time once stored
    assert db.save_doc(conn, story(1, points=300, published="2026-01-01T00:00:00Z"), now="2026-09-06T00:00:00Z") == "unchanged"
    row = conn.execute("SELECT * FROM raw_doc WHERE id = 'hn:1'").fetchone()
    assert conn.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 1
    assert row["first_seen_at"] == "2026-09-03T00:00:00Z" and row["last_seen_at"] == "2026-09-06T00:00:00Z"
    assert row["published_at"] == "2026-09-02T10:00:00Z"
    assert json.loads(row["metrics"])["points"] == 300 and json.loads(row["raw_payload"]) == {"id": 1}
    assert row["source_id"] == "1"


def test_content_change_triggers_retagging(conn, cur):
    from kompas.tag import retag

    db.save_doc(conn, story(2, title="Postgres tips"))
    conn.commit()
    retag(conn, cur)
    db.save_doc(conn, story(2, title="SQL and Postgres tips"))
    conn.commit()
    assert retag(conn, cur) == 1
    assert conn.execute("SELECT concept_id FROM tag WHERE doc_id = 'hn:2'").fetchone()["concept_id"] == "sql"


# ---------- runs ----------


def test_run_statuses_and_counts(conn):
    with start_run(conn, "hn_front", "backfill", "test") as run:
        run.save(story(1))
        run.save(story(2))
        run.commit(cursor="2026-09-07T00:00:00Z")
    r = last_run(conn)
    assert (r["status"], r["ok"], r["n_inserted"], r["n_fetched"], r["checkpoint"]) == ("ok", 1, 2, 2, "2026-09-07T00:00:00Z")

    with start_run(conn, "hn_front", "backfill", "test") as run:
        run.save(story(1))
        run.commit()
    r = last_run(conn)
    assert (r["status"], r["ok"], r["n_unchanged"]) == ("no_change", 1, 1)

    with start_run(conn, "hn_front", "backfill", "test") as run:
        run.save(story(3))
        run.save(Document(id="hn:4", source="hn_front", kind="story", source_id="4", url=None, title="x", text="",
                          published_at=None, period="2026-09"))
        run.commit()
    r = last_run(conn)
    assert (r["status"], r["ok"], r["n_failed"], r["n_inserted"]) == ("partial", 0, 1, 1)
    assert not db.has_doc(conn, "hn:4")
    err = conn.execute("SELECT * FROM ingest_error WHERE run_id = ?", (r["id"],)).fetchone()
    assert err["category"] == "validation" and "publication time unknown" in err["message"]


def test_uncommitted_work_is_rolled_back_and_checkpoint_stays(conn):
    with start_run(conn, "hn_front", "backfill", "test") as run:
        run.save(story(1))
        run.commit(cursor="2026-09-07T00:00:00Z")
    with pytest.raises(FetchError):
        with start_run(conn, "hn_front", "backfill", "test") as run:
            run.save(story(2))
            run.commit(cursor="2026-09-14T00:00:00Z")
            run.save(story(3))          # never committed
            raise FetchError("network", "connection reset")
    r = last_run(conn)
    assert r["status"] == "partial" and r["error_category"] == "network"
    assert db.has_doc(conn, "hn:2") and not db.has_doc(conn, "hn:3")
    assert r["checkpoint"] == "2026-09-14T00:00:00Z"

    with pytest.raises(FetchError):
        with start_run(conn, "hn_front", "backfill", "test") as run:
            run.save(story(5))
            raise FetchError("rate_limited", "HTTP 429")
    r = last_run(conn)
    assert (r["status"], r["ok"]) == ("failed", 0) and not db.has_doc(conn, "hn:5")
    assert ingest.Run(conn, "hn_front", "backfill", "x").checkpoint() == "2026-09-14T00:00:00Z"


def test_interrupted_run_is_recorded(conn):
    with pytest.raises(KeyboardInterrupt):
        with start_run(conn, "hn_front", "backfill", "test") as run:
            run.save(story(1))
            run.commit()
            raise KeyboardInterrupt
    assert last_run(conn)["status"] == "interrupted" and db.has_doc(conn, "hn:1")


def test_invalid_dataset_stores_nothing(conn):
    with pytest.raises(DatasetInvalid):
        with start_run(conn, "dosm_jmi", "occupations", "test") as run:
            run.warn("f.csv", "validation", "extra column")
            raise DatasetInvalid(["line 2: bad period"])
    r = last_run(conn, "dosm_jmi", "occupations")
    assert (r["status"], r["error_category"]) == ("invalid", "validation")
    found = {(e["severity"], e["message"]) for e in conn.execute("SELECT * FROM ingest_error WHERE run_id = ?", (r["id"],))}
    assert found == {("warning", "extra column"), ("error", "line 2: bad period")}


def test_dry_run_stores_nothing(conn):
    with start_run(conn, "hn_front", "backfill", "test", dry_run=True) as run:
        run.save(story(1))
        run.commit(cursor="2026-09-07T00:00:00Z")
    r = last_run(conn)
    assert (r["mode"], r["status"], r["ok"]) == ("dry_run", "ok", None)
    assert not db.has_doc(conn, "hn:1") and run.checkpoint() is None


# ---------- locking ----------


def test_one_writer_per_stream(conn, tmp_path):
    other = db.connect(tmp_path / "test.db")
    with start_run(conn, "github", "counts", "test"):
        with pytest.raises(SourceBusy):
            with start_run(other, "github", "counts", "test"):
                pass
        with start_run(other, "github", "live", "test"):   # a different stream isn't blocked
            pass
    with start_run(other, "github", "counts", "test"):    # released on exit
        pass


def test_expired_lease_from_a_crashed_run_is_taken_over(conn):
    past = iso(datetime.now(timezone.utc) - timedelta(hours=1))
    conn.execute("INSERT INTO ingest_lock VALUES ('github', 'counts', 'dead-host:1:x', 99, ?, ?)", (past, past))
    conn.commit()
    with start_run(conn, "github", "counts", "test") as run:
        run.commit()
    assert conn.execute("SELECT COUNT(*) FROM ingest_lock").fetchone()[0] == 0


# ---------- orchestration ----------


def test_one_failing_source_does_not_stop_the_others(conn, cur, monkeypatch):
    def broken(run, cur, opts):
        raise FetchError("server", "HTTP 503")

    def fine(run, cur, opts):
        run.save(story(1))
        run.commit()

    jobs = {key: fine for key in ingest._jobs()}
    jobs[("arxiv", "monthly")] = broken
    monkeypatch.setattr(ingest, "_jobs", lambda: jobs)
    outcomes = ingest.run_sources(conn, cur, ["arxiv", "hn_front", "dosm_jmi"], Options())
    by = {(o["source"], o["stream"]): o for o in outcomes}
    assert by[("arxiv", "monthly")]["status"] == "failed"
    assert by[("arxiv", "monthly")]["error_category"] == "server"
    assert by[("hn_front", "backfill")]["status"] == "ok"
    assert by[("dosm_jmi", "groups")]["status"] in ("ok", "no_change")
    # the manual stream reports a missing file instead of failing
    assert by[("dosm_jmi", "occupations")]["status"] == "skipped"


def test_month_window_resumes_from_checkpoint_with_overlap(conn):
    run = ingest.Run(conn, "arxiv", "monthly", "test")
    ms, refetch = ingest.month_window(run, Options(since="2026-01", until="2026-03"))
    assert ms == ["2026-01", "2026-02", "2026-03"] and refetch == set()
    assert ingest.month_window(run, Options(since="2026-01", until="2026-02", force=True))[1] == {"2026-01", "2026-02"}
    conn.execute("INSERT INTO checkpoint VALUES ('arxiv', 'monthly', '2026-06', '2026-07-02T00:00:00Z', NULL)")
    ms, refetch = ingest.month_window(run, Options())
    assert ms[0] == "2026-06" and refetch == {"2026-06"}     # one month of overlap
    assert ingest.later("2026-06", "2026-05") == "2026-06"   # checkpoints never move back


# ---------- migrations ----------


def legacy_db(path):
    """A database as the pipeline created it before schema versioning."""
    c = sqlite3.connect(path)
    c.executescript(db.SCHEMA)
    c.execute("INSERT INTO raw_doc (id, source, kind, url, title, text, topics, published_at, period, metrics, "
              "content_hash, tagged_hash, fetched_at) VALUES ('ax:2409.00001v2:rag', 'arxiv', 'paper', 'u', 't', '', "
              "'[]', '2024-09-01T00:00:00Z', '2024-09', '{}', 'h', 'h', '2026-10-01T00:00:00Z')")
    c.execute("INSERT INTO raw_doc (id, source, kind, url, title, text, topics, published_at, period, metrics, "
              "content_hash, fetched_at) VALUES ('gh:a/b', 'github', 'repo', 'u', 'a/b', '', '[]', "
              "'2026-09-01T00:00:00Z', '2026-09', '{}', 'h', '2026-10-02T00:00:00Z')")
    c.execute("INSERT INTO fetch_log (source, mode, started_at, finished_at, ok, n_docs) VALUES "
              "('github', 'live', '2026-10-02T00:00:00Z', '2026-10-02T00:01:00Z', 1, 3)")
    c.execute("INSERT INTO artifact_metric VALUES ('gh:a/b', '2026-10-02T00:00:00Z', 'stars', 250)")
    c.commit()
    c.close()


def test_migration_keeps_existing_data(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_db(path)
    conn = db.connect(path)
    assert db.schema_version(conn) == db.SCHEMA_VERSION
    paper = conn.execute("SELECT * FROM raw_doc WHERE id = 'ax:2409.00001v2:rag'").fetchone()
    assert paper["source_id"] == "2409.00001" and paper["tagged_hash"] == "h"
    assert paper["first_seen_at"] == paper["last_seen_at"] == "2026-10-01T00:00:00Z"
    assert conn.execute("SELECT source_id FROM raw_doc WHERE id = 'gh:a/b'").fetchone()[0] == "a/b"
    log_row = conn.execute("SELECT * FROM fetch_log").fetchone()
    assert (log_row["status"], log_row["stream"], log_row["n_docs"]) == ("ok", "live", 3)
    conn.execute("INSERT INTO fetch_log (source, mode, stream, status, ok, started_at) VALUES "
                 "('arxiv', 'backfill', 'backfill', 'ok', 1, '2026-10-01T00:00:00Z')")
    db._m2_legacy_streams(conn)
    assert conn.execute("SELECT stream FROM fetch_log WHERE source = 'arxiv'").fetchone()[0] == "monthly"
    assert conn.execute("SELECT COUNT(*) FROM artifact_metric").fetchone()[0] == 1
    conn.close()
    conn = db.connect(path)    # running again is a no-op
    assert conn.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 2


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    legacy_db(path)

    def half_done(conn):
        db._m1_ingestion(conn)
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "MIGRATIONS", [(1, half_done)])
    with pytest.raises(RuntimeError):
        db.connect(path)
    c = sqlite3.connect(path)
    cols = {r[1] for r in c.execute("PRAGMA table_info(raw_doc)")}
    assert "source_id" not in cols and not c.execute(
        "SELECT name FROM sqlite_master WHERE name = 'checkpoint'").fetchone()
    assert c.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 2
    c.close()


# ---------- health ----------


def log_run(conn, source, stream, status, finished, error=None, category=None):
    conn.execute("INSERT INTO fetch_log (source, mode, stream, status, ok, started_at, finished_at, error, "
                 "error_category) VALUES (?, 'scheduled', ?, ?, ?, ?, ?, ?, ?)",
                 (source, stream, status, 1 if status in ("ok", "no_change") else 0, finished, finished, error, category))


def test_health_distinguishes_states(conn):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    recent, old = iso(now - timedelta(days=1)), iso(now - timedelta(days=60))
    log_run(conn, "arxiv", "monthly", "ok", recent)
    db.save_doc(conn, Document(id="axb:2026-09", source="arxiv", kind="paper_baseline", source_id="2026-09", url=None,
                               title="", text="", published_at="2026-10-01T00:00:00Z", period="2026-09",
                               metrics={"count": 9000}))
    log_run(conn, "github", "counts", "ok", old)
    log_run(conn, "hn_front", "backfill", "ok", old)
    log_run(conn, "hn_front", "backfill", "failed", recent, "HTTP 503", "server")
    log_run(conn, "hn_front", "backfill", "failed", recent, "HTTP 503", "server")
    log_run(conn, "hn_hiring", "threads", "partial", recent)
    log_run(conn, "dosm_jmi", "occupations", "invalid", recent, "2 validation error(s)", "validation")
    conn.commit()
    report = ingest.status(conn, live_mode=False, now=now)
    s = {(x["source"], x["stream"]): x for x in report["streams"]}
    assert s[("arxiv", "monthly")]["state"] == "ok"
    assert s[("github", "counts")]["state"] == "stale"
    assert s[("hn_front", "backfill")]["state"] == "unavailable"
    assert s[("hn_front", "backfill")]["consecutive_failures"] == 2
    assert s[("hn_front", "backfill")]["last_error"]["category"] == "server"
    assert s[("hn_hiring", "threads")]["state"] == "partial"
    assert s[("dosm_jmi", "occupations")]["state"] == "invalid"
    assert s[("dosm_jmi", "groups")]["state"] == "never_run"
    assert s[("github", "live")]["state"] == "not_expected"
    assert not report["healthy"]
    assert ingest.status(conn, live_mode=True, now=now)["streams"][2]["state"] == "never_run"


def test_health_flags_old_data_even_when_fetches_succeed(conn):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    log_run(conn, "dosm_jmi", "groups", "no_change", iso(now - timedelta(hours=2)))
    db.save_doc(conn, Document(id="dosmg:2025Q2:2", source="dosm_jmi", kind="occupation_group_stat", source_id="x",
                               url=None, title="", text="", published_at="2025-08-15T15:59:59Z", period="2025Q2"))
    conn.commit()
    s = next(x for x in ingest.status(conn, now=now)["streams"] if x["stream"] == "groups")
    assert s["state"] == "stale" and "newest record was published" in s["reasons"][0]


def test_api_health_reports_ingestion(conn, cur):
    from fastapi.testclient import TestClient

    from kompas.api import create_app

    log_run(conn, "arxiv", "monthly", "failed", iso(datetime.now(timezone.utc)), "HTTP 503", "server")
    conn.commit()
    body = TestClient(create_app(live_mode=False, replay=False)).get("/health").json()
    assert body["ok"] is True and body["ingestion"]["healthy"] is False
    arxiv = next(s for s in body["sources"] if s["id"] == "arxiv")
    assert arxiv["state"] == "unavailable" and arxiv["data_as_of"] is None
    assert arxiv["last_error"]["category"] == "server"
