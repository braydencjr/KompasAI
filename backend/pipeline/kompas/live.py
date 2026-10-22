"""The fast loop: pollers that fetch, tag and re-rank the feed, and an in-process bus that pushes
events to SSE subscribers. Replay mode re-streams recorded events, so a demo always has movement."""

import asyncio
import json
import logging

from . import db
from .config import Params
from .connectors import github, hn
from .curated import Curated
from .feed import refresh_live
from .periods import utcnow
from .tag import retag

log = logging.getLogger("kompas.live")

POLLERS = {
    "hn_front": hn.poll_front,
    "github": github.poll,
}


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
        with db.fetch_run(conn, source, "live") as run:
            run["n"] = len(POLLERS[source](conn, cur))
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
