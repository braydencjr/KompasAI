import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import config, curated, db, ingest, llm, snapshot, suggest
from .live import run_cycle
from .periods import months
from .tag import retag

EXIT = {"failed": 1, "invalid": 1, "interrupted": 1, "busy": 3, "partial": 2}


def _print_outcomes(outcomes: list[dict]) -> int:
    for o in outcomes:
        c = o["counts"] or {}
        counts = " ".join(f"{k}={c[k]}" for k in ingest.COUNTS if c.get(k)) or "-"
        line = f"{o['source']}/{o['stream']}: {o['status']}  {counts}"
        if o["error"]:
            line += f"  [{o['error_category']}] {o['error']}" if o['error_category'] else f"  {o['error']}"
        print(line, flush=True)
    return max((EXIT.get(o["status"], 0) for o in outcomes), default=0)


def cmd_fetch(args, conn, cur):
    """Ingests one source (or all). Without --since/--until, runs incrementally from each stream's checkpoint.
    Sources run one after another; a failing source is reported and the rest still run."""
    if bool(args.since) != bool(args.until):
        sys.exit("--since and --until go together")
    if args.file and not args.stream:
        sys.exit("--file needs --stream (occupations for dosm_jmi, editions for mycol)")
    opts = ingest.Options(since=args.since, until=args.until, months=args.months, force=args.force,
                          dry_run=args.dry_run, file=Path(args.file) if args.file else None)
    if args.stream:
        if args.source == "all":
            sys.exit("--stream needs a single source")
        outcomes = [ingest.run_stream(conn, cur, args.source, args.stream, opts, "backfill" if args.since else "scheduled")]
    else:
        sources = list(ingest.SOURCES) if args.source == "all" else [args.source]
        outcomes = ingest.run_sources(conn, cur, sources, opts, "backfill" if args.since else "scheduled")
    sys.exit(_print_outcomes(outcomes))


def cmd_status(args, conn, cur):
    """Ingestion health per stream: freshness, last run, failures, checkpoint."""
    report = ingest.status(conn, live_mode=args.live)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    for s in report["streams"]:
        c = s["last_counts"] or {}
        print(f"{s['source']}/{s['stream']:<12} {s['state']:<15} records={s['records']:<6} "
              f"latest={s['latest_published_at'] or '-':<20} last_success={s['last_success_at'] or '-'}")
        if s["reasons"]:
            print(f"    {'; '.join(s['reasons'])}")
        if s["last_error"] and s["last_error"]["message"]:
            print(f"    last error ({s['last_error']['category']}): {s['last_error']['message'][:160]}")
        if s["checkpoint"]:
            print(f"    checkpoint: {s['checkpoint'][:120]}")
        if c:
            print("    last run: " + " ".join(f"{k}={c[k]}" for k in ingest.COUNTS if c.get(k)))
    print("healthy" if report["healthy"] else "problems: " + ", ".join(report["problems"]))
    sys.exit(0 if report["healthy"] else 1)


def cmd_errors(args, conn, cur):
    """Record failures and validation findings from the most recent runs."""
    rows = conn.execute(
        "SELECT e.*, f.started_at FROM ingest_error e LEFT JOIN fetch_log f ON f.id = e.run_id "
        + ("WHERE e.source = ? " if args.source else "") + "ORDER BY e.id DESC LIMIT ?",
        ((args.source,) if args.source else ()) + (args.limit,)).fetchall()
    for r in reversed(rows):
        print(f"{r['at']} run {r['run_id']} {r['source']}/{r['stream']} {r['severity']} [{r['category']}] "
              f"{r['ref'] or ''}: {r['message']}")


def cmd_unlock(args, conn, cur):
    """Frees a stream lock left by a killed process (locks also expire on their own)."""
    n = conn.execute("DELETE FROM ingest_lock WHERE source = ? AND stream = ?", (args.source, args.stream)).rowcount
    conn.execute("UPDATE fetch_log SET status = 'interrupted', ok = 0, finished_at = ? "
                 "WHERE source = ? AND stream = ? AND status = 'running'",
                 (ingest.utcnow(), args.source, args.stream))
    conn.commit()
    print(f"{'released' if n else 'no lock on'} {args.source}/{args.stream}")


def cmd_poll(args, conn, cur):
    """One live poll per source; a failing source is reported and the next one still runs."""
    code = 0
    for s in (["hn_front", "github"] if args.source == "all" else [args.source]):
        try:
            events = run_cycle(s, cur, config.PARAMS)
        except Exception as e:
            print(f"{s}: failed: {e}")
            code = 1
            continue
        print(f"{s}: {len(events)} feed events")
    sys.exit(code)


def cmd_snapshot(args, conn, cur):
    dates = [args.as_of or date.today().isoformat()]
    if args.monthly:
        dates = [f"{m}-01" for m in months(args.monthly[0], args.monthly[1])]
    for d in dates:
        print(json.dumps(snapshot.build(conn, cur, d, export=args.export)))


def cmd_diff(args, conn, cur):
    print(json.dumps(snapshot.diff(conn, args.a, args.b), indent=2))
    conn.commit()


def cmd_review(args, conn, cur):
    """Trending items that matched no concept: add an alias or concept, then re-run."""
    retag(conn, cur)
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.url, d.topics,
               COALESCE(CAST(json_extract(d.metrics, '$.points') AS REAL), CAST(json_extract(d.metrics, '$.stars') AS REAL)) AS score
        FROM raw_doc d LEFT JOIN tag t ON t.doc_id = d.id
        WHERE d.kind IN ('story', 'repo') AND t.doc_id IS NULL
        ORDER BY score DESC LIMIT ?
        """, (args.limit,),
    ).fetchall()
    for r in rows:
        topics = ", ".join(json.loads(r["topics"]))
        print(f"{int(r['score'] or 0):>7}  {r['title'][:80]}" + (f"  [{topics}]" if topics else ""))
        print(f"         {r['url']}")


def cmd_suggest(args, conn, cur):
    """Asks Gemini to place the most popular unmatched items; every answer is checked before it's listed."""
    if not llm.available():
        sys.exit("GEMINI_API_KEY isn't set (backend/.env)")
    result = suggest.suggest(conn, cur, limit=args.limit, days=args.days)
    print(", ".join(f"{k}={v}" for k, v in result.items()))
    if result.get("error"):
        sys.exit(1)
    print("Review with `kompas suggestions`, then `kompas approve <id>...` or `kompas reject <id>...`.")


def cmd_suggestions(args, conn, cur):
    rows = suggest.pending(conn, args.all)
    for r in rows:
        label = cur.concepts[r["concept_id"]].label if r["concept_id"] in cur.concepts else "-"
        flag = f" [{r['status']}{': ' + r['check_note'] if r['check_note'] else ''}]" if args.all else ""
        print(f"#{r['id']:<4} {r['alias'] or '-'!r} -> {label}  (would tag {r['reach'] if r['reach'] is not None else '?'} items){flag}")
        print(f"       from: {r['item_title'][:100]}")
        if r["reason"]:
            print(f"       why:  {r['reason']}")
    if not rows:
        print("nothing waiting for review")


def cmd_approve(args, conn, cur):
    try:
        added = suggest.approve(conn, args.ids)
    except ValueError as e:
        sys.exit(str(e))
    for a in added:
        print(f"added {a}")
    print("Re-tagging happens on the next `kompas snapshot`.")


def cmd_reject(args, conn, cur):
    print(f"rejected {suggest.reject(conn, args.ids)}")


def cmd_esco_sync(args, conn, cur):
    """Refreshes curated/occupation_task.csv (The Mirror's task cards) from the ESCO API."""
    from .connectors import esco

    counts = esco.sync()
    for isco, n in counts.items():
        print(f"{isco}: {n} tasks")
    print(f"wrote curated/occupation_task.csv ({sum(counts.values())} tasks)")


def cmd_esco_aliases(args, conn, cur):
    """Refreshes curated/occupation_alias.csv: the names people use for each catalogue job, from the ESCO API."""
    from .connectors import esco

    counts = esco.sync_aliases(list(cur.role_titles))
    for isco, n in counts.items():
        print(f"{isco} {cur.role_titles[isco]}: {n} names")
    print(f"wrote curated/occupation_alias.csv ({sum(counts.values())} names)")


def cmd_esco_skills(args, conn, cur):
    """Refreshes curated/occupation_skill_esco.csv: each role's ESCO skills, the evidence for its skill links."""
    from .connectors import esco

    counts = esco.sync_skills()
    for occupation, n in counts.items():
        print(f"{occupation}: {n} items")
    print(f"wrote curated/occupation_skill_esco.csv ({sum(counts.values())} items)")


def cmd_links_draft(args, conn, cur):
    """Drafts role skill links from ESCO with Gemini into curated/concept_occupation.draft.csv, for review."""
    from . import links

    if not llm.available():
        sys.exit("GEMINI_API_KEY isn't set (backend/.env)")
    result = links.draft(cur, links.esco_items())
    path = links.write_draft(result["rows"])
    by_status: dict[str, int] = {}
    for r in result["rows"]:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"wrote {path} ({', '.join(f'{n} {s}' for s, n in sorted(by_status.items()))}); "
          f"dropped {result['dropped']} proposals citing no real ESCO item")
    for isco, error in result["errors"].items():
        print(f"error: {isco}: {error}")
    print("Review it (set keep to 'no' to reject a row), then run `kompas links-apply`.")


def cmd_links_apply(args, conn, cur):
    from . import links

    counts = links.apply(cur)
    print(f"wrote curated/concept_occupation.csv: {counts['kept']} skill links kept, {counts['rejected']} rejected, "
          f"{counts['families']} family links unchanged")


def cmd_validate(args, conn, cur):
    errors = curated.validate(cur)
    for e in errors:
        print(f"error: {e}")
    print(f"{len(cur.concepts)} concepts, {len(cur.aliases)} aliases, "
          f"{len(cur.concept_occupations)} concepts linked to occupations, version {cur.version}")
    if errors:
        sys.exit(1)


def cmd_serve(args, conn, cur):
    import uvicorn

    from .api import create_app

    conn.close()
    logging.getLogger().setLevel(logging.INFO)
    uvicorn.run(create_app(live_mode=args.live, replay=args.replay), host=args.host, port=args.port)


def cmd_copy_to_postgres(args, conn, cur):
    """Copies the local SQLite database into Postgres (DATABASE_URL), once, when moving to Supabase."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("set DATABASE_URL in backend/.env first")
    from . import pg
    path = Path(args.source) if args.source else config.db_path()
    if not path.exists():
        sys.exit(f"no SQLite database at {path}")
    src = db.connect(path)
    try:
        counts = pg.copy_from_sqlite(src, url, replace=args.replace)
    except RuntimeError as e:
        sys.exit(str(e))
    finally:
        src.close()
    for table, (lite, postgres) in counts.items():
        print(f"{table:<18} sqlite={lite:<7} postgres={postgres}" + ("" if lite == postgres else "  MISMATCH"))
    sys.exit(0 if all(a == b for a, b in counts.values()) else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kompas", description="Kompas signal pipeline")
    ap.add_argument("-v", "--verbose", action="store_true", help="structured run logs on stderr")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="ingest a source (or all): incremental by default, a backfill with --since/--until")
    f.add_argument("source", choices=["all", *ingest.SOURCES])
    f.add_argument("--stream", help="one stream only, e.g. groups or occupations for dosm_jmi")
    f.add_argument("--since", help="first month, YYYY-MM (with --until: explicit backfill)")
    f.add_argument("--until", help="last month, YYYY-MM")
    f.add_argument("--months", type=int, default=12, help="first run without a range: this many complete months")
    f.add_argument("--force", action="store_true", help="re-fetch units that are already stored")
    f.add_argument("--dry-run", action="store_true", help="fetch and validate without storing anything")
    f.add_argument("--file", help="manual streams: the file to import (default data/manual/dosm_jmi.csv or mycol_editions.csv)")
    f.set_defaults(fn=cmd_fetch)

    st = sub.add_parser("status", help="ingestion health per stream")
    st.add_argument("--json", action="store_true")
    st.add_argument("--live", action="store_true", help="expect the live pollers to be running")
    st.set_defaults(fn=cmd_status)

    e = sub.add_parser("errors", help="recent record failures and validation findings")
    e.add_argument("source", nargs="?")
    e.add_argument("--limit", type=int, default=50)
    e.set_defaults(fn=cmd_errors)

    u = sub.add_parser("unlock", help="free a stream lock left by a killed process")
    u.add_argument("source")
    u.add_argument("stream")
    u.set_defaults(fn=cmd_unlock)

    p = sub.add_parser("poll", help="run one live poll cycle (fetch, tag, re-rank feed)")
    p.add_argument("source", choices=["all", "hn_front", "github"])
    p.set_defaults(fn=cmd_poll)

    s = sub.add_parser("snapshot", help="build a snapshot (default: today)")
    s.add_argument("--as-of", help="YYYY-MM-DD")
    s.add_argument("--monthly", nargs=2, metavar=("FROM", "TO"), help="one snapshot on the 1st of each month")
    s.add_argument("--export", action="store_true", help="also write JSON copies to data/snapshots/ for inspection")
    s.set_defaults(fn=cmd_snapshot)

    d = sub.add_parser("diff", help="compare two snapshots")
    d.add_argument("a")
    d.add_argument("b")
    d.set_defaults(fn=cmd_diff)

    r = sub.add_parser("review", help="list trending items that matched no concept")
    r.add_argument("--limit", type=int, default=30)
    r.set_defaults(fn=cmd_review)

    sg = sub.add_parser("suggest", help="ask Gemini to suggest aliases for popular unmatched items")
    sg.add_argument("--limit", type=int, default=50, help="items to ask about")
    sg.add_argument("--days", type=int, default=90, help="only items published in the last N days")
    sg.set_defaults(fn=cmd_suggest)

    sl = sub.add_parser("suggestions", help="list alias suggestions waiting for review")
    sl.add_argument("--all", action="store_true", help="include decided, refused and no-match ones")
    sl.set_defaults(fn=cmd_suggestions)

    ap_ = sub.add_parser("approve", help="add suggested aliases to curated/concept_alias.csv")
    ap_.add_argument("ids", type=int, nargs="+")
    ap_.set_defaults(fn=cmd_approve)

    rj = sub.add_parser("reject", help="drop alias suggestions")
    rj.add_argument("ids", type=int, nargs="+")
    rj.set_defaults(fn=cmd_reject)

    sub.add_parser("esco-sync", help="refresh The Mirror's task lists from the ESCO API").set_defaults(fn=cmd_esco_sync)
    sub.add_parser("esco-skills", help="fetch each role's ESCO skills (evidence for role skill links)").set_defaults(fn=cmd_esco_skills)
    sub.add_parser("esco-aliases", help="fetch the names people use for each catalogue job (job search)").set_defaults(fn=cmd_esco_aliases)
    sub.add_parser("links-draft", help="draft role skill links from ESCO with Gemini, for review").set_defaults(fn=cmd_links_draft)
    sub.add_parser("links-apply", help="merge the reviewed draft into concept_occupation.csv").set_defaults(fn=cmd_links_apply)
    sub.add_parser("validate", help="check the curated tables").set_defaults(fn=cmd_validate)
    cp = sub.add_parser("copy-to-postgres", help="copy the local SQLite database into DATABASE_URL (Supabase)")
    cp.add_argument("--source", help="SQLite file (default: KOMPAS_DB or backend/data/kompas.db)")
    cp.add_argument("--replace", action="store_true", help="overwrite data already in Postgres")
    cp.set_defaults(fn=cmd_copy_to_postgres)

    v = sub.add_parser("serve", help="run the API")
    v.add_argument("--live", action="store_true", help="run the HN and GitHub pollers")
    v.add_argument("--replay", action="store_true", help="re-stream recorded feed events (demo mode)")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8001, help="8001: the main backend (backend/app) uses 8000")
    v.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    cur = curated.load()
    conn = db.connect()
    try:
        args.fn(args, conn, cur)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
