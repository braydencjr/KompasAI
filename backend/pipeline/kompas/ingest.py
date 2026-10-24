"""Ingestion runs: what every connector writes through.

A Run wraps one fetch of one stream (e.g. arXiv's monthly counts, GitHub's live poll). It
- holds a lease lock on (source, stream), so two processes can't advance the same checkpoint;
- writes documents through db.save_doc and counts inserted / updated / unchanged / skipped / failed;
- commits data and the stream's checkpoint in one transaction (`run.commit(cursor=...)`), so a checkpoint
  never points past data that isn't stored;
- logs the outcome in fetch_log with a status:
    ok         new or changed records were stored and nothing went wrong
    no_change  the source answered and nothing was new
    partial    some records were stored, but something was missing or failed (see detail / ingest_error)
    failed     nothing could be stored (source unreachable, rate limited, ...)
    invalid    the dataset failed validation, so nothing was stored
    interrupted  the process was stopped mid-run (committed batches stay; the checkpoint shows where)

Recovery after an interruption is to run the same command again: committed batches are kept, the
checkpoint says where to carry on, and upserts make re-fetched records harmless.
"""

import json
import logging
import os
import socket
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .document import Document
from .db import record_metric, save_doc
from .http import FetchError, Http
from .periods import iso, last_complete_months, months, parse, utcnow

log = logging.getLogger("kompas.ingest")

COUNTS = ("fetched", "inserted", "updated", "unchanged", "skipped", "failed", "retries")
SUCCESS = ("ok", "no_change")


class SourceBusy(Exception):
    """Another run holds this stream's lock."""


class DatasetInvalid(Exception):
    """The dataset failed validation; nothing from it was stored."""

    def __init__(self, errors: list[str]):
        super().__init__(f"{len(errors)} validation error(s): " + "; ".join(errors[:5]))
        self.errors = errors


@dataclass
class Options:
    since: str | None = None       # YYYY-MM; with until, an explicit backfill range
    until: str | None = None
    months: int = 12               # first run without a range or checkpoint: this many complete months
    force: bool = False            # re-fetch units that are already stored
    dry_run: bool = False          # fetch and validate, store nothing
    file: Path | None = None       # manual imports (DOSM CSV)


def log_event(event: str, **fields):
    """One structured log line. Callers never pass tokens, headers or resume text."""
    log.info(json.dumps({"event": event, **fields}, default=str, sort_keys=True))


class Run:
    def __init__(self, conn, source: str, stream: str, mode: str, dry_run: bool = False):
        self.conn, self.source, self.stream = conn, source, stream
        self.mode = "dry_run" if dry_run else mode
        self.dry_run = dry_run
        self.id: int | None = None
        self.counts = dict.fromkeys(COUNTS, 0)
        self.partial_reasons: list[str] = []
        self.findings: list[tuple[str, str, str | None, str]] = []   # severity, category, ref, message
        self.detail: dict = {}
        self.latest_published_at: str | None = None
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._committed_changes = 0
        self._cursor: str | None = None

    # ---- lifecycle ----

    def begin(self):
        now = utcnow()
        expires = iso(parse(now) + timedelta(minutes=config.LOCK_LEASE_MINUTES))
        self.conn.commit()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            held = self.conn.execute("SELECT owner, expires_at FROM ingest_lock WHERE source = ? AND stream = ?",
                                     (self.source, self.stream)).fetchone()
            if held and held["expires_at"] > now:
                raise SourceBusy(f"{self.source}/{self.stream} is locked by {held['owner']} "
                                 f"until {held['expires_at']}")
            self.id = self.conn.execute(
                "INSERT INTO fetch_log (source, mode, stream, status, started_at) VALUES (?, ?, ?, 'running', ?) "
                "RETURNING id", (self.source, self.mode, self.stream, now)).fetchone()[0]
            self.conn.execute(
                "INSERT INTO ingest_lock (source, stream, owner, run_id, acquired_at, expires_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (source, stream) DO UPDATE SET owner = excluded.owner, run_id = excluded.run_id, "
                "acquired_at = excluded.acquired_at, expires_at = excluded.expires_at",
                (self.source, self.stream, self.owner, self.id, now, expires))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self._cursor = self.checkpoint()
        log_event("run_start", source=self.source, stream=self.stream, run_id=self.id, mode=self.mode,
                  checkpoint=self._cursor)

    def finish(self, exc: BaseException | None):
        self.conn.rollback()   # anything not committed by run.commit() is dropped
        category, message = None, None
        if exc is None:
            if self.partial_reasons or self.counts["failed"]:
                status = "partial"
            elif self.counts["inserted"] + self.counts["updated"] == 0:
                status = "no_change"
            else:
                status = "ok"
        elif isinstance(exc, (KeyboardInterrupt, SystemExit)) or type(exc).__name__ == "CancelledError":
            status, category, message = "interrupted", "interrupted", type(exc).__name__
        else:
            category = getattr(exc, "category", None) or (
                "validation" if isinstance(exc, DatasetInvalid) else "internal")
            message = str(exc)[:500]
            if isinstance(exc, DatasetInvalid):
                status = "invalid"
                for e in exc.errors:
                    self.findings.append(("error", "validation", None, e))
            else:
                status = "partial" if self._committed_changes else "failed"
        if self.dry_run and status in ("ok", "no_change"):
            status = "ok"   # nothing is written in a dry run; "ok" means the data validated
        ok = None if self.dry_run else (1 if status in SUCCESS else 0)
        if self.partial_reasons:
            self.detail["partial"] = self.partial_reasons
        now = utcnow()
        self.conn.executemany(
            "INSERT INTO ingest_error (run_id, source, stream, at, severity, category, ref, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(self.id, self.source, self.stream, now, sev, cat, ref, msg[:1000]) for sev, cat, ref, msg in self.findings])
        self.conn.execute(
            """
            UPDATE fetch_log SET finished_at = ?, ok = ?, status = ?, n_docs = ?, error = ?, error_category = ?,
              n_fetched = ?, n_inserted = ?, n_updated = ?, n_unchanged = ?, n_skipped = ?, n_failed = ?,
              n_retries = ?, checkpoint = ?, latest_published_at = ?, detail = ?
            WHERE id = ?
            """,
            (now, ok, status, self.counts["inserted"] + self.counts["updated"], message, category,
             *(self.counts[k] for k in COUNTS), self.checkpoint(), self.latest_published_at,
             json.dumps(self.detail, sort_keys=True, default=str) if self.detail else None, self.id),
        )
        self.conn.execute("DELETE FROM ingest_lock WHERE source = ? AND stream = ? AND owner = ?",
                          (self.source, self.stream, self.owner))
        self.conn.commit()
        self.status, self.error_category, self.error = status, category, message
        log_event("run_end", source=self.source, stream=self.stream, run_id=self.id, status=status,
                  error_category=category, error=message, **self.counts)

    # ---- writing ----

    def http(self, **kwargs) -> Http:
        return Http(on_retry=self._on_retry, **kwargs)

    def _on_retry(self):
        self.counts["retries"] += 1

    def save(self, doc: Document) -> str:
        """Stores one document. A document that can't be stored (no publication time, bad timestamp) is
        recorded as a failed record, not written, and doesn't stop the run."""
        self.counts["fetched"] += 1
        try:
            result = save_doc(self.conn, doc)
        except ValueError as e:
            self.fail(doc.id, "validation", str(e))
            return "failed"
        self.counts[result] += 1
        if self.latest_published_at is None or doc.published_at > self.latest_published_at:
            self.latest_published_at = doc.published_at
        return result

    def observe(self, artifact_id: str, name: str, value: float, observed_at: str | None = None):
        record_metric(self.conn, artifact_id, name, value, observed_at)

    def skip(self, n: int = 1):
        self.counts["skipped"] += n

    def fail(self, ref: str | None, category: str, message: str):
        """A record that couldn't be fetched or stored. Makes the run partial; the run carries on."""
        self.counts["failed"] += 1
        self.findings.append(("error", category, ref, message))
        log_event("record_failed", source=self.source, stream=self.stream, run_id=self.id, ref=ref,
                  category=category, error=message[:300])

    def warn(self, ref: str | None, category: str, message: str):
        """Something worth knowing (e.g. an unmapped occupation code) that doesn't make the data wrong."""
        self.findings.append(("warning", category, ref, message))

    def partial(self, reason: str):
        """The source answered, but not completely (truncated results, a missing period, ...)."""
        self.partial_reasons.append(reason)
        log_event("partial", source=self.source, stream=self.stream, run_id=self.id, reason=reason)

    # ---- checkpoints ----

    def checkpoint(self) -> str | None:
        row = self.conn.execute("SELECT cursor FROM checkpoint WHERE source = ? AND stream = ?",
                                (self.source, self.stream)).fetchone()
        return row["cursor"] if row else None

    def commit(self, cursor: str | None = None):
        """Makes everything saved so far durable, together with the new checkpoint (if given), and renews
        the lock lease. In a dry run everything is rolled back instead."""
        if cursor is not None:
            self.conn.execute(
                "INSERT INTO checkpoint (source, stream, cursor, updated_at, run_id) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (source, stream) DO UPDATE SET cursor = excluded.cursor, updated_at = excluded.updated_at, "
                "run_id = excluded.run_id",
                (self.source, self.stream, cursor, utcnow(), self.id))
        expires = iso(parse(utcnow()) + timedelta(minutes=config.LOCK_LEASE_MINUTES))
        self.conn.execute("UPDATE ingest_lock SET expires_at = ? WHERE source = ? AND stream = ? AND owner = ?",
                          (expires, self.source, self.stream, self.owner))
        if self.dry_run:
            self.conn.rollback()
            return
        self.conn.commit()
        self._committed_changes = self.counts["inserted"] + self.counts["updated"]


class Breaker:
    """One failed request is a failed record; several in a row mean the source is down (or we're rate
    limited for good), so the run stops instead of failing every remaining request the same way."""

    def __init__(self, run: Run, limit: int = 3):
        self.run, self.limit, self.n = run, limit, 0

    def ok(self):
        self.n = 0

    def failed(self, ref: str, e: FetchError):
        self.run.fail(ref, e.category, str(e))
        self.n += 1
        if self.n >= self.limit:
            raise FetchError(e.category, f"stopped after {self.n} consecutive failures; last: {e}", e.url, e.status)


@contextmanager
def start_run(conn, source: str, stream: str, mode: str, dry_run: bool = False):
    run = Run(conn, source, stream, mode, dry_run)
    run.begin()
    try:
        yield run
    except BaseException as e:
        run.finish(e)
        raise
    run.finish(None)


# ---------- windows ----------


def shift_month(month: str, n: int) -> str:
    y, m = map(int, month.split("-"))
    k = y * 12 + m - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def month_window(run: Run, opts: Options) -> tuple[list[str], set[str]]:
    """Months to fetch, and the subset to re-fetch even if already stored.

    Explicit range: exactly that range (re-fetched only with --force). Otherwise incremental: from the
    checkpoint (the last month fully stored), re-fetching OVERLAP_MONTHS months back, up to the last
    complete month. With no checkpoint yet: the last `opts.months` complete months, skipping stored ones."""
    if opts.since and opts.until:
        ms = months(opts.since, opts.until)
        return ms, set(ms) if opts.force else set()
    default_since, until = last_complete_months(opts.months)
    cp = run.checkpoint()
    if not cp:
        ms = months(default_since, until)
        return ms, set(ms) if opts.force else set()
    since = min(shift_month(cp, 1 - config.OVERLAP_MONTHS), until)
    ms = months(since, until)
    overlap = {m for m in ms if m <= cp}
    return ms, set(ms) if opts.force else overlap


def later(a: str | None, b: str) -> str:
    """Checkpoints only move forward, even when an overlap window re-fetches older months."""
    return b if a is None or b > a else a


# ---------- orchestration ----------


def _jobs():
    from .connectors import arxiv, dosm, github, hn, mycol

    return {
        ("arxiv", "monthly"): arxiv.ingest,
        ("github", "counts"): github.ingest_counts,
        ("hn_front", "backfill"): hn.ingest_front,
        ("hn_hiring", "threads"): hn.ingest_hiring,
        ("dosm_jmi", "groups"): dosm.ingest_groups,
        ("dosm_jmi", "occupations"): dosm.ingest_csv,
        ("mycol", "editions"): mycol.ingest_editions,
    }


def _pollers():
    from .connectors import github, hn

    return {"hn_front": hn.poll_front, "github": github.poll}


SOURCES = ("arxiv", "github", "hn_front", "hn_hiring", "dosm_jmi", "mycol")


def run_stream(conn, cur, source: str, stream: str, opts: Options, mode: str = "scheduled") -> dict:
    """Runs one stream and reports its outcome. Never raises for source problems: a failing source is
    reported, and the caller moves on to the next one."""
    outcome = {"source": source, "stream": stream, "run_id": None, "status": None, "error": None,
               "error_category": None, "counts": None}
    spec = config.stream(source, stream)
    if spec.manual:
        path = opts.file or config.MANUAL_DIR / spec.manual_file
        if not Path(path).exists():
            outcome.update(status="skipped", error=f"no file at {path} (see data/manual/README.md)")
            log_event("run_skipped", source=source, stream=stream, reason=outcome["error"])
            return outcome
    run = None
    try:
        with start_run(conn, source, stream, mode, opts.dry_run) as run:
            _jobs()[(source, stream)](run, cur, opts)
    except SourceBusy as e:
        outcome.update(status="busy", error=str(e))
        log_event("run_skipped", source=source, stream=stream, reason=str(e))
        return outcome
    except Exception:
        pass   # recorded on the run by finish(); reported below
    outcome.update(run_id=run.id, status=run.status, error=run.error, error_category=run.error_category,
                   counts=dict(run.counts))
    return outcome


def run_sources(conn, cur, sources: list[str], opts: Options, mode: str = "scheduled") -> list[dict]:
    """Runs every stream of every listed source, one after another. One source failing doesn't stop the
    others; each gets its own outcome."""
    out = []
    for source in sources:
        for spec in config.STREAMS:
            if spec.source == source and not spec.live:
                out.append(run_stream(conn, cur, source, spec.stream, opts, mode))
    return out


def run_live(conn, cur, source: str) -> list[str]:
    """One live poll. Returns ids of new documents; raises if the poll failed (the run is logged either way)."""
    with start_run(conn, source, "live", "live") as run:
        new = _pollers()[source](run, cur)
        run.commit()
    return new


# ---------- status ----------


def _age_hours(ts: str | None, now: datetime) -> float | None:
    return None if ts is None else (now - parse(ts)).total_seconds() / 3600


def stream_status(conn, spec: config.Stream, now: datetime, live_mode: bool) -> dict:
    runs = conn.execute(
        "SELECT * FROM fetch_log WHERE source = ? AND stream = ? AND mode != 'dry_run' AND status != 'running' "
        "ORDER BY id DESC LIMIT 50", (spec.source, spec.stream)).fetchall()
    running = conn.execute(
        "SELECT l.acquired_at, l.expires_at FROM ingest_lock l WHERE l.source = ? AND l.stream = ? AND l.expires_at > ?",
        (spec.source, spec.stream, iso(now))).fetchone()
    last = runs[0] if runs else None
    success = next((r for r in runs if r["status"] in SUCCESS or (r["status"] == "partial")), None)
    full_success = next((r for r in runs if r["status"] in SUCCESS), None)
    consecutive = 0
    for r in runs:
        if r["status"] not in ("failed", "invalid"):
            break
        consecutive += 1
    last_error = next((r for r in runs if r["error"] or r["status"] in ("failed", "invalid", "partial")), None)
    cp = conn.execute("SELECT cursor, updated_at FROM checkpoint WHERE source = ? AND stream = ?",
                      (spec.source, spec.stream)).fetchone()
    kinds = ",".join("?" * len(spec.kinds))
    latest = conn.execute(
        f"SELECT MAX(published_at) p, MAX(period) per, COUNT(*) n FROM raw_doc WHERE source = ? AND kind IN ({kinds})",
        (spec.source, *spec.kinds)).fetchone()

    expected = not spec.live or live_mode
    reasons = []
    if not runs:
        state = "never_run"
        reasons.append("no ingestion run recorded" + (" (manual file not provided)" if spec.manual else ""))
    elif last["status"] == "invalid":
        state = "invalid"
        reasons.append("last dataset failed validation")
    elif last["status"] in ("failed", "interrupted") and consecutive:
        state = "unavailable"
        reasons.append(f"{consecutive} consecutive failed run(s)")
    else:
        state = {"partial": "partial", "no_change": "no_new_records", "ok": "ok"}.get(last["status"], "unknown")
        if last["status"] == "interrupted":
            state, _ = "partial", reasons.append("last run was interrupted")
    age = _age_hours(success["finished_at"] if success else None, now)
    if runs and state not in ("invalid", "unavailable") and (age is None or age > spec.max_age_hours):
        state = "stale"
        reasons.append("no successful fetch in the last " + f"{spec.max_age_hours / 24:.0f} days"
                       if spec.max_age_hours >= 48 else f"{spec.max_age_hours:.0f} hours")
    if spec.data_max_age_days and latest["p"]:
        data_age = _age_hours(latest["p"], now) / 24
        if data_age > spec.data_max_age_days:
            if state in ("ok", "no_new_records", "partial"):
                state = "stale"
            reasons.append(f"newest record was published {data_age:.0f} days ago")
    if not expected and state == "never_run":
        state = "not_expected"
        reasons = ["live polling is off"]
    return {
        "source": spec.source, "stream": spec.stream, "description": spec.description,
        "state": state, "reasons": reasons, "expected": expected,
        "last_attempt_at": last["started_at"] if last else None,
        "last_status": last["status"] if last else None,
        "last_success_at": success["finished_at"] if success else None,
        "last_complete_success_at": full_success["finished_at"] if full_success else None,
        "running_since": running["acquired_at"] if running else None,
        "consecutive_failures": consecutive,
        "last_counts": {k: last[f"n_{k}"] for k in COUNTS} if last else None,
        "last_error": {"at": last_error["finished_at"], "status": last_error["status"],
                       "category": last_error["error_category"], "message": last_error["error"],
                       "partial": (json.loads(last_error["detail"]) or {}).get("partial") if last_error["detail"] else None}
        if last_error else None,
        "checkpoint": cp["cursor"] if cp else None,
        "checkpoint_updated_at": cp["updated_at"] if cp else None,
        "records": latest["n"], "latest_published_at": latest["p"], "latest_period": latest["per"],
    }


def status(conn, live_mode: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    streams = [stream_status(conn, s, now, live_mode) for s in config.STREAMS]
    problems = [f"{s['source']}/{s['stream']}: {s['state']}" for s in streams
                if s["expected"] and s["state"] not in ("ok", "no_new_records")]
    return {"healthy": not problems, "problems": problems, "streams": streams, "checked_at": iso(now)}
