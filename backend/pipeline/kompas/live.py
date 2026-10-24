"""The fast loop: pollers that fetch, tag and re-rank the feed, and an in-process bus that pushes
events to SSE subscribers. Replay mode re-streams recorded events, so a demo always has movement."""

import asyncio
import json
import logging

from datetime import date

from . import db
from .config import Params
from .curated import Curated
from .feed import refresh_live
from .ingest import run_live
from .periods import utcnow
from .tag import retag

log = logging.getLogger("kompas.live")


class Bus:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subs.discard(q)

    def publish(self, event: dict):
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a stalled client misses events; it can catch up with Last-Event-ID

    @property
    def subscribers(self) -> int:
        return len(self._subs)


def run_cycle(source: str, cur: Curated, p: Params) -> list[dict]:
    """One poll of one source, then tag and re-rank. Runs in a worker thread."""
    conn = db.connect()
    try:
        run_live(conn, cur, source)
        retag(conn, cur)
        return refresh_live(conn, p)
    finally:
        conn.close()


async def poll_loop(source: str, interval: float, cur: Curated, p: Params, bus: Bus):
    while True:
        try:
            events = await asyncio.to_thread(run_cycle, source, cur, p)
            for e in events:
                bus.publish(e)
            log.info("%s: %d feed events", source, len(events))
        except Exception:
            log.exception("%s poll failed; keeping the last good feed", source)
        await asyncio.sleep(interval)


async def radar_loop(interval: float, cur: Curated, p: Params, bus: Bus, hn_source: str | None):
    """Radar's hourly refresh: GitHub Trending and the news (new stories go out as `news` events), and one Hacker
    News poll when no live poller covers it.
    The first pass runs at start-up only if the last scrape is older than the interval."""
    from . import radar   # radar imports this package's db and llm; imported here to keep start-up light
    first = True
    while True:
        try:
            started = utcnow()
            scraped = await asyncio.to_thread(radar.refresh_if_stale, cur, interval)
            if scraped:
                # the stories this run read and found worth showing, to the live feed (the page drips them in)
                for item in await asyncio.to_thread(radar.fresh_news, cur, started):
                    bus.publish({"seq": f"n:{item['id']}", "type": "news", "at": utcnow(), "item": item})
            if hn_source and (scraped or not first):
                for e in await asyncio.to_thread(run_cycle, hn_source, cur, p):
                    bus.publish(e)
            log.info("radar refresh: trending %s", "scraped" if scraped else "still fresh")
        except Exception:
            log.exception("radar refresh failed; serving the last good data")
        first = False
        await asyncio.sleep(interval)


async def replay_loop(bus: Bus, interval: float):
    """Re-streams the recorded event log in order, forever. Events are marked replay=true."""
    while True:
        conn = db.connect()
        rows = conn.execute("SELECT * FROM feed_event ORDER BY seq").fetchall()
        conn.close()
        if not rows:
            await asyncio.sleep(interval)
            continue
        for r in rows:
            bus.publish({"seq": f"r{r['seq']}", "type": r["type"], "at": utcnow(), "replay": True,
                         "item": json.loads(r["payload"])})
            await asyncio.sleep(interval)


def ensure_daily_snapshot(cur: Curated, p: Params) -> dict | None:
    """Checks the latest snapshot in the database. If it is older than today, builds today's snapshot."""
    today = date.today().isoformat()
    conn = db.connect()
    try:
        row = conn.execute("SELECT as_of FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
        latest = row["as_of"] if row else None
        if not latest:
            log.info("daily snapshot: no snapshot in database yet; skipping auto snapshot")
            return None
        if latest >= today:
            log.info("daily snapshot: already up to date (%s)", latest)
            return None
        log.info("daily snapshot: latest is %s, building snapshot for %s", latest, today)
        from . import snapshot as snapshot_mod
        result = snapshot_mod.build(conn, cur, today, p, export=False)
        log.info("daily snapshot: built %s (%d concepts)", today, result.get("concepts", 0))
        return result
    except Exception:
        log.exception("daily snapshot build failed")
        raise
    finally:
        conn.close()


async def daily_snapshot_loop(interval: float, cur: Curated, p: Params):
    """Daily check for a new snapshot. Runs on startup, then periodically checks."""
    while True:
        try:
            await asyncio.to_thread(ensure_daily_snapshot, cur, p)
        except Exception:
            log.exception("daily snapshot loop failed; will retry next interval")
        await asyncio.sleep(interval)

