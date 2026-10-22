"""Real-time API over the pipeline's SQLite store.

Run:  kompas serve [--live] [--replay]
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import curated, cv, db, explain, live
from .config import PARAMS
from .periods import iso

# PRD FR-4.2 demand multipliers, reused to weight personal feed items
STATUS_WEIGHT = {"Act now": 1.2, "Emerging": 1.1, "Stable": 1.0, "Watch": 0.9, "Declining": 0.7, "Stalled": 0.6}


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _snapshot_id(conn, snapshot: str | None) -> str:
    if snapshot:
        if not conn.execute("SELECT 1 FROM snapshot WHERE id = ?", (snapshot,)).fetchone():
            raise HTTPException(404, f"snapshot {snapshot!r} not found")
        return snapshot
    row = conn.execute("SELECT id FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(503, "no snapshot built yet; run `kompas snapshot`")
    return row["id"]


def _concept(row, cur: curated.Curated) -> dict:
    c = cur.concepts.get(row["concept_id"])
    return {
        "id": row["concept_id"], "label": c.label if c else row["concept_id"], "kind": c.kind if c else None,
        "parent_id": c.parent_id if c else None, "status": row["status"],
        "family_id": row["family_id"], "family_status": row["family_status"],
        "projected": json.loads(row["projected"]), "rungs": json.loads(row["rungs"]),
        "evidence_ids": json.loads(row["evidence_ids"]),
    }


def _statuses(conn, sid: str, ids: list[str], cur: curated.Curated) -> list[dict]:
    if not ids:
        return []
    rows = conn.execute(
        f"SELECT concept_id, status, family_status FROM concept_status WHERE snapshot_id = ? "
        f"AND concept_id IN ({','.join('?' * len(ids))})", (sid, *ids),
    ).fetchall()
    return [{"id": r["concept_id"], "label": cur.concepts[r["concept_id"]].label, "status": r["status"],
             "family_status": r["family_status"]} for r in rows if r["concept_id"] in cur.concepts]


class ProfileSkill(BaseModel):
    id: str
    evidence: Literal["claimed", "demonstrated"] = "claimed"


class Profile(BaseModel):
    skills: list[ProfileSkill] = []
    route: list[str] = []      # concepts the user is learning (their Route / Ghost CV gaps)
    exposed: list[str] = []    # capability concepts that reach the user's tasks (from the Mirror)
    limit: int = 20


def create_app(live_mode: bool | None = None, replay: bool | None = None) -> FastAPI:
    live_mode = os.environ.get("KOMPAS_LIVE") == "1" if live_mode is None else live_mode
    replay = os.environ.get("KOMPAS_REPLAY") == "1" if replay is None else replay
    cur = curated.load()
    bus = live.Bus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = []
        if live_mode:
            # e.g. KOMPAS_LIVE_SOURCES=hn_front while a GitHub backfill is using the search quota
            enabled = os.environ.get("KOMPAS_LIVE_SOURCES", "hn_front,github").split(",")
            intervals = {"hn_front": os.environ.get("KOMPAS_HN_INTERVAL", 120),
                         "github": os.environ.get("KOMPAS_GITHUB_INTERVAL", 900)}
            for source, interval in intervals.items():
                if source in enabled:
                    tasks.append(asyncio.create_task(live.poll_loop(source, float(interval), cur, PARAMS, bus)))
        if replay:
            tasks.append(asyncio.create_task(live.replay_loop(bus, float(os.environ.get("KOMPAS_REPLAY_INTERVAL", 4)))))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="Kompas Signal API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("KOMPAS_CORS", "http://localhost:3000").split(","),
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )

    @app.get("/health")
    def health(conn=Depends(get_conn)):
        snap = conn.execute("SELECT id, created_at FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
        sources = []
        stale_before = iso(datetime.now(timezone.utc) - timedelta(hours=2))
        for s in cur.sources:
            ok = conn.execute("SELECT MAX(finished_at) t FROM fetch_log WHERE source = ? AND ok = 1", (s,)).fetchone()["t"]
            err = conn.execute(
                "SELECT finished_at, error FROM fetch_log WHERE source = ? AND ok = 0 AND finished_at > ? "
                "ORDER BY id DESC LIMIT 1", (s, ok or ""),
            ).fetchone()
            running = conn.execute(
                # a run killed mid-way never finishes; ignore anything older than 2 hours
                "SELECT started_at FROM fetch_log WHERE source = ? AND finished_at IS NULL AND started_at > ? "
                "AND started_at > ? ORDER BY id DESC LIMIT 1", (s, ok or "", stale_before),
            ).fetchone()
            sources.append({"id": s, "data_as_of": ok, "running_since": running["started_at"] if running else None,
                            "last_error": dict(err) if err else None})
        return {"ok": True, "live": live_mode, "replay": replay, "subscribers": bus.subscribers,
                "latest_snapshot": dict(snap) if snap else None, "sources": sources}

    @app.get("/snapshots")
    def snapshots(conn=Depends(get_conn)):
        return [dict(r) for r in conn.execute("SELECT id, as_of, created_at FROM snapshot ORDER BY as_of")]

    @app.get("/snapshots/{sid}")
    def snapshot(sid: str, conn=Depends(get_conn)):
        sid = _snapshot_id(conn, None if sid == "latest" else sid)
        r = conn.execute("SELECT * FROM snapshot WHERE id = ?", (sid,)).fetchone()
        return {**dict(r), "params": json.loads(r["params"]), "sources": json.loads(r["sources"])}

    @app.get("/snapshots/{sid}/changes")
    def changes(sid: str, conn=Depends(get_conn)):
        sid = _snapshot_id(conn, None if sid == "latest" else sid)
        rows = conn.execute("SELECT * FROM change WHERE snapshot_id = ?", (sid,)).fetchall()
        return {"to": sid, "from": rows[0]["from_snapshot"] if rows else None, "changes": [
            {"concept_id": r["concept_id"], "label": cur.concepts[r["concept_id"]].label, "field": r["field"],
             "from": r["old"], "to": r["new"], "reason": r["reason"], "evidence_ids": json.loads(r["evidence_ids"])}
            for r in rows if r["concept_id"] in cur.concepts
        ]}

    @app.get("/concepts")
    def concepts(snapshot: str | None = None, status: str | None = None, kind: str | None = None,
                 conn=Depends(get_conn)):
        sid = _snapshot_id(conn, snapshot)
        rows = conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ?", (sid,)).fetchall()
        out = [_concept(r, cur) for r in rows]
        return {"snapshot": sid, "concepts": [
            c for c in out if (not status or c["status"] == status) and (not kind or c["kind"] == kind)
        ]}

    @app.get("/concepts/{cid}")
    def concept(cid: str, snapshot: str | None = None, conn=Depends(get_conn)):
        sid = _snapshot_id(conn, snapshot)
        r = conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ? AND concept_id = ?", (sid, cid)).fetchone()
        if not r:
            raise HTTPException(404, f"concept {cid!r} not found")
        return {"snapshot": sid, **_concept(r, cur)}

    @app.get("/concepts/{cid}/evidence")
    def concept_evidence(cid: str, snapshot: str | None = None, conn=Depends(get_conn)):
        sid = _snapshot_id(conn, snapshot)
        r = conn.execute("SELECT evidence_ids FROM concept_status WHERE snapshot_id = ? AND concept_id = ?",
                         (sid, cid)).fetchone()
        if not r:
            raise HTTPException(404, f"concept {cid!r} not found")
        ids = json.loads(r["evidence_ids"])
        rows = conn.execute(
            f"SELECT * FROM evidence WHERE snapshot_id = ? AND id IN ({','.join('?' * len(ids)) or 'NULL'})",
            (sid, *ids),
        ).fetchall()
        notes = {s.id: s.coverage_note for s in cur.sources.values()}
        return {"snapshot": sid, "concept_id": cid, "evidence": [
            {**dict(e), "concept_ids": json.loads(e["concept_ids"]), "coverage_note": notes.get(e["source"])}
            for e in rows
        ]}

    def _feed(conn, snapshot: str | None, concept: str | None, limit: int) -> tuple[str, list[dict]]:
        sid = _snapshot_id(conn, snapshot)
        if snapshot:
            items = [json.loads(r["item"]) for r in
                     conn.execute("SELECT item FROM snapshot_feed WHERE snapshot_id = ? ORDER BY rank", (sid,))]
        else:
            items = [{**{k: r[k] for k in r.keys() if k != "counts"}, **json.loads(r["counts"]),
                      "concept_ids": json.loads(r["concept_ids"])} for r in
                     conn.execute("SELECT * FROM feed_item ORDER BY momentum DESC")]
        if concept:
            items = [i for i in items if concept in i["concept_ids"]]
        for i in items:
            i["concepts"] = _statuses(conn, sid, i["concept_ids"], cur)
        return sid, items[:limit]

    @app.get("/feed")
    def feed(snapshot: str | None = None, concept: str | None = None, limit: int = Query(30, le=100),
             conn=Depends(get_conn)):
        """Live feed by default; pass ?snapshot= for the feed as it was on that date."""
        sid, items = _feed(conn, snapshot, concept, limit)
        return {"statuses_from": sid, "live": snapshot is None, "items": items}

    @app.get("/feed/stream")
    async def feed_stream(request: Request, last_event_id: str | None = Header(None)):
        """Server-sent events: `new` and `rising` feed items, each joined to its concepts' current status."""
        q = bus.subscribe()

        def enrich(event: dict) -> dict:
            conn = db.connect()
            try:
                sid = conn.execute("SELECT id FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
                item = dict(event["item"])
                item["concepts"] = _statuses(conn, sid["id"], item["concept_ids"], cur) if sid else []
                return {**event, "item": item}
            finally:
                conn.close()

        def frame(event: dict) -> str:
            return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(enrich(event))}\n\n"

        async def gen():
            try:
                if last_event_id and last_event_id.isdigit():
                    conn = db.connect()
                    missed = conn.execute("SELECT * FROM feed_event WHERE seq > ? ORDER BY seq LIMIT 200",
                                          (int(last_event_id),)).fetchall()
                    conn.close()
                    for r in missed:
                        yield frame({"seq": r["seq"], "type": r["type"], "at": r["at"], "item": json.loads(r["payload"])})
                yield ": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield frame(event)
            finally:
                bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/match")
    def match(profile: Profile, conn=Depends(get_conn)):
        """Personal feed for one profile: one explained card per skill, plus the Ping.
        Concept ids must exist (closed world)."""
        have = {s.id for s in profile.skills}
        route, exposed = set(profile.route), set(profile.exposed)
        unknown = sorted((have | route | exposed) - set(cur.concepts))
        if unknown:
            raise HTTPException(422, {"unknown_concepts": unknown})
        sid, items = _feed(conn, None, None, 100)
        rows = {r["concept_id"]: r for r in conn.execute(
            "SELECT concept_id, status, family_id, family_status, rungs FROM concept_status WHERE snapshot_id = ?",
            (sid,))}

        def ladder(cid: str) -> dict:
            """Which hiring steps the skill has reached. 'Talked about' is implied: the card exists because
            something about it is trending right now."""
            if cid not in rows:
                return {"abroad": False, "malaysia": None, "family_label": None}
            rungs = json.loads(rows[cid]["rungs"])
            r3 = rungs.get("3", {})
            fam = rows[cid]["family_id"]
            return {
                "abroad": bool(rungs.get("2", {}).get("active")),
                "malaysia": r3.get("level") if r3.get("active") else None,   # "concept" | "family" | None
                "family_label": cur.concepts[fam].label if fam in cur.concepts else None,
            }

        def relation(cid: str) -> tuple[str, float, str] | None:
            """(relation, weight, concept the card is about)"""
            if cid in exposed:
                return "exposed", 1.3, cid
            if cid in route:
                return "route", 1.2, cid
            if cid in have:
                return "have", 1.0, cid
            for a in cur.ancestors(cid):
                if a in have or a in route:
                    return "related", 0.5, a
            return None

        cards: dict[str, dict] = {}
        for item in items:
            hits = [r for cid in item["concept_ids"] if cid in cur.concepts and (r := relation(cid))]
            if not hits:
                continue
            rel, weight, cid = max(hits, key=lambda h: h[1])
            status = rows[cid]["status"] if cid in rows else "Stable"
            score = item["momentum"] * weight * STATUS_WEIGHT.get(status, 1.0)
            card = cards.get(cid)
            if card is None:
                fam = rows[cid]["family_id"] if cid in rows else None
                card = cards[cid] = {
                    "concept_id": cid, "label": cur.concepts[cid].label, "status": status,
                    "family_status": rows[cid]["family_status"] if cid in rows else None,
                    **explain.explain(rel, cur.concepts[cid].label, status,
                                      cur.concepts[fam].label if fam in cur.concepts else None,
                                      rows[cid]["family_status"] if cid in rows else None),
                    "ladder": ladder(cid), "score": 0.0, "items": [],
                }
            card["items"].append({k: item[k] for k in item if k not in ("concepts", "concept_ids")})
            # the strongest item sets the score; extra items add a little, so breadth counts but can't swamp
            card["score"] = round(max(card["score"], score) + 0.05 * (len(card["items"]) > 1), 4)
        signals = sorted(cards.values(), key=lambda c: c["score"], reverse=True)[: profile.limit]
        for c in signals:
            c["items"] = c["items"][:3]

        mine = have | route | exposed
        ping = [c for c in changes(sid, conn)["changes"] if c["concept_id"] in mine]
        return {"snapshot": sid, "summary": explain.summary(signals), "signals": signals, "ping": ping,
                "statuses": _statuses(conn, sid, sorted(mine), cur)}

    @app.post("/profile/extract")
    def extract_profile(file: UploadFile | None = File(None), text: str | None = Form(None), conn=Depends(get_conn)):
        """CV -> skills profile. The file is read in memory and never stored; nothing about the user is saved."""
        if file is not None:
            data = file.file.read(cv.MAX_BYTES + 1)
            if len(data) > cv.MAX_BYTES:
                raise HTTPException(413, "CV must be 5 MB or smaller")
            try:
                text = cv.extract_text(file.filename or "", data)
            except cv.UnsupportedFile as e:
                raise HTTPException(415, str(e))
            except Exception:
                raise HTTPException(422, "Couldn't read this file. Try saving it again as PDF or DOCX.")
        if not text or len(text.strip()) < 40:
            raise HTTPException(422, "No readable text found. A scanned PDF needs to be exported with text.")
        if len(text) > cv.MAX_CHARS:
            raise HTTPException(413, "That's much longer than a CV. Upload just the CV itself.")
        return {"file": file.filename if file else None, **cv.analyse(text, cur, conn)}

    return app


app = create_app()
