import argparse
import json
import logging
import sys
from datetime import date

from . import config, curated, db, snapshot
from .connectors import arxiv, dosm, github, hn
from .live import run_cycle
from .periods import last_complete_months, months
from .tag import retag

# HN is cheap to re-fetch; GitHub and arXiv skip months already saved unless --force
BACKFILL = {
    "hn_front": lambda conn, cur, a, b, force: hn.backfill_front(conn, cur, a, b, min_points=config.PARAMS.hn_min_points),
    "hn_hiring": lambda conn, cur, a, b, force: hn.backfill_hiring(conn, cur, a, b),
    "github": lambda conn, cur, a, b, force: github.backfill(conn, cur, a, b, force=force),
    "arxiv": lambda conn, cur, a, b, force: arxiv.backfill(conn, cur, a, b, force=force),
}


def cmd_fetch(args, conn, cur):
    since, until = args.since, args.until
    if not since or not until:
        since, until = last_complete_months(args.months)
    sources = list(BACKFILL) + ["dosm_jmi"] if args.source == "all" else [args.source]
    for s in sources:
        path = config.MANUAL_DIR / "dosm_jmi.csv"
        if s == "dosm_jmi" and not path.exists():
            print(f"dosm_jmi: skipped, {path} not found (see data/manual/README.md)")
            continue
        with db.fetch_run(conn, s, "backfill") as run:
            if s == "dosm_jmi":
                run["n"] = dosm.import_csv(conn, cur, path)
            else:
                print(f"{s}: fetching {since}..{until}", flush=True)
                run["n"] = BACKFILL[s](conn, cur, since, until, args.force)
        print(f"{s}: {run['n']} docs")


def cmd_poll(args, conn, cur):
    for s in (["hn_front", "github"] if args.source == "all" else [args.source]):
        events = run_cycle(s, cur, config.PARAMS)
        print(f"{s}: {len(events)} feed events")


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
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(live_mode=args.live, replay=args.replay), host=args.host, port=args.port)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kompas", description="Kompas signal pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="backfill a source (or all) into the raw store")
    f.add_argument("source", choices=["all", *BACKFILL, "dosm_jmi"])
    f.add_argument("--since", help="first month, YYYY-MM")
    f.add_argument("--until", help="last month, YYYY-MM")
    f.add_argument("--months", type=int, default=12, help="if no range given: this many complete months")
    f.add_argument("--force", action="store_true", help="re-fetch months that are already saved")
    f.set_defaults(fn=cmd_fetch)

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

    sub.add_parser("validate", help="check the curated tables").set_defaults(fn=cmd_validate)

    v = sub.add_parser("serve", help="run the API")
    v.add_argument("--live", action="store_true", help="run the HN and GitHub pollers")
    v.add_argument("--replay", action="store_true", help="re-stream recorded feed events (demo mode)")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
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
