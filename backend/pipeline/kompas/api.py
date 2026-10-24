"""Real-time API over the pipeline's SQLite store.

Served by backend/app under /api/signals; `kompas serve [--live] [--replay]` runs it alone for development.
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import brief, curated, cv, db, explain, ingest, journey, live
from .config import PARAMS
from .http import FetchError

log = logging.getLogger("kompas.api")

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


# Uvicorn waits for open connections to close before it stops or reloads, and an event stream never closes on its
# own: without a way out, `fastapi dev` hangs on "Waiting for connections to close" after every file change, and
# answers no requests meanwhile. Streams end when the server is told to exit (the hook sse-starlette uses). Newer
# uvicorn installs its signal handlers before importing the app, so that hook can miss; each stream therefore also
# ends after STREAM_MAX_SECONDS, and browsers reconnect by themselves.
STREAM_MAX_SECONDS = 20
_exiting = False
try:
    from uvicorn.server import Server

    _handle_exit = Server.handle_exit

    def _note_exit(self, sig, frame):
        global _exiting
        _exiting = True
        return _handle_exit(self, sig, frame)

    Server.handle_exit = _note_exit
except ImportError:  # not served by uvicorn
    pass


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
        f"AND concept_id IN ({','.join('?' * len(ids))}) ORDER BY concept_id", (sid, *ids),
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


class JourneyRequest(BaseModel):
    """Everything the journey needs; it lives in the browser and is sent with each request."""
    skills: list[ProfileSkill] = []
    occupation: str | None = None                 # ISCO code of the current job
    overrides: dict[str, dict] = {}               # Mirror: task uri -> {"pile": "exposed"|"human", "reason": "..."}
    scenario: Literal["moderate", "fast"] = "moderate"
    sdgs: list[int] = []
    role: str | None = None                       # ISCO code of the chosen bet
    completed: list[str] = []                     # route skills marked done
    pace: float = Field(5, gt=0, le=60)           # hours a week
    snapshot: str | None = None                   # default: latest


class PingRequest(JourneyRequest):
    from_snapshot: str
    to_snapshot: str | None = None                # default: latest


class BriefRequest(JourneyRequest):
    kind: Literal["bets", "ping"]
    from_snapshot: str | None = None              # for kind=ping


def create_router(live_mode: bool | None = None, replay: bool | None = None):
    """The signal API as a router, plus the background tasks it needs (live pollers, replay).

    Returns (router, background): include the router in any FastAPI app, and enter `background()` in that
    app's lifespan. backend/app serves it under /api/signals; create_app() serves it on its own."""
    live_mode = os.environ.get("KOMPAS_LIVE") == "1" if live_mode is None else live_mode
    replay = os.environ.get("KOMPAS_REPLAY") == "1" if replay is None else replay
    cur = curated.load()
    bus = live.Bus()

    @asynccontextmanager
    async def background():
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

    app = APIRouter(tags=["signals"])   # named `app` so the route decorators below read as before

    @app.get("/health")
    def health(conn=Depends(get_conn)):
        """Server status plus ingestion health. `ok` only says the API answers; `ingestion.healthy` says
        whether every expected stream is fresh and its last run succeeded."""
        snap = conn.execute("SELECT id, created_at FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
        report = ingest.status(conn, live_mode=live_mode)
        rank = {"ok": 0, "no_new_records": 1, "not_expected": 1, "partial": 2, "stale": 3, "never_run": 4,
                "invalid": 5, "unavailable": 5}
        sources = []
        for s in cur.sources:
            streams = [x for x in report["streams"] if x["source"] == s]
            expected = [x for x in streams if x["expected"]] or streams
            errors = [x["last_error"] for x in streams if x["last_error"]]
            sources.append({
                "id": s,
                # kept for the frontend: when this source last delivered data successfully
                "data_as_of": max((x["last_success_at"] for x in streams if x["last_success_at"]), default=None),
                "running_since": min((x["running_since"] for x in streams if x["running_since"]), default=None),
                "last_error": max(errors, key=lambda e: e["at"] or "") if errors else None,
                "state": max((x["state"] for x in expected), key=lambda st: rank.get(st, 3)) if expected else None,
                "latest_published_at": max((x["latest_published_at"] for x in streams if x["latest_published_at"]),
                                           default=None),
            })
        return {"ok": True, "live": live_mode, "replay": replay, "subscribers": bus.subscribers,
                "latest_snapshot": dict(snap) if snap else None, "sources": sources, "ingestion": report}

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
        rows = conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ? ORDER BY concept_id", (sid,)).fetchall()
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
    def concept_evidence(cid: str, snapshot: str | None = None, task: str | None = Query(None, max_length=300),
                         why: str = Query("", max_length=400), conn=Depends(get_conn)):
        """The records behind a concept's status. With `task` (the job task that was clicked), only the ones that
        bear on that task, each with a sentence on how; `specific` is False when none do."""
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
        items = [{**dict(e), "concept_ids": json.loads(e["concept_ids"]), "coverage_note": notes.get(e["source"])}
                 for e in rows]
        if task and task.strip():
            from . import evidence_pick
            from .periods import cutoff
            as_of = conn.execute("SELECT as_of FROM snapshot WHERE id = ?", (sid,)).fetchone()["as_of"]
            return {"snapshot": sid, "concept_id": cid, "task": task,
                    **evidence_pick.pick(conn, sid, cid, task.strip(), why, items, cutoff(as_of), notes)}
        return {"snapshot": sid, "concept_id": cid, "evidence": items}

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
        items = items[:limit]
        # one query for every item's statuses: each round trip to the database costs ~100 ms on Supabase
        found = {s["id"]: s for s in _statuses(conn, sid, sorted({c for i in items for c in i["concept_ids"]}), cur)}
        for i in items:
            i["concepts"] = [found[c] for c in sorted(set(i["concept_ids"])) if c in found]
        return sid, items

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
                # the browser reconnects 1 s after the stream ends, sending Last-Event-ID, so nothing is missed
                yield "retry: 1000\n: connected\n\n"
                idle, started = 0, time.monotonic()
                while not _exiting and not await request.is_disconnected():
                    if time.monotonic() - started > STREAM_MAX_SECONDS:
                        break   # see STREAM_MAX_SECONDS
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=1)
                    except asyncio.TimeoutError:
                        idle += 1
                        if idle >= 15:      # a comment every 15 s keeps proxies from closing the stream
                            idle = 0
                            yield ": ping\n\n"
                        continue
                    idle = 0
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
            "SELECT concept_id, status, family_id, family_status, rungs FROM concept_status WHERE snapshot_id = ? "
            "ORDER BY concept_id",
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

    @app.get("/jobs")
    def jobs(isco: str, skills: str = "", conn=Depends(get_conn)):
        """Live openings in Malaysia for a role (JSearch, cached a day), each with the user's skills it mentions."""
        from .connectors import jsearch
        from .tag import Tagger

        if isco not in cur.role_titles:
            raise HTTPException(404, f"unknown occupation {isco!r}")
        title = cur.role_titles[isco]
        try:
            found = jsearch.search(conn, title)
        except FetchError as e:
            return {"role": title, "jobs": [], "source": jsearch.SOURCE, "fetched_at": None, "cached": False, "note": str(e)}
        have = {s for s in skills.split(",") if s}
        tagger = Tagger(cur)
        out = []
        for j in found["jobs"]:
            mentioned = {cid for cid, *_ in tagger.find_all(f"{j['title']}\n{j['description']}")}
            out.append({**{k: v for k, v in j.items() if k != "description"},
                        "matched": sorted(cur.concepts[c].label for c in mentioned & have)})
        return {"role": title, "jobs": out, "source": found["source"], "fetched_at": found["fetched_at"],
                "cached": found.get("cached", False), "note": found.get("note")}

    MAX_TEXT_LINES = 600     # the whole of a normal CV; the reader shows it scrollable

    @app.post("/profile/text")
    def profile_text(file: UploadFile = File(...)):
        """The CV's text lines, fast, so the scanner can show the real document while the reader works."""
        data = file.file.read(cv.MAX_BYTES + 1)
        if len(data) > cv.MAX_BYTES:
            raise HTTPException(413, "CV must be 5 MB or smaller")
        try:
            text = cv.extract_text(file.filename or "", data)
        except cv.UnsupportedFile as e:
            raise HTTPException(415, str(e))
        except Exception:
            raise HTTPException(422, "Couldn't read this file. Try saving it again as PDF or DOCX.")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return {"file": file.filename, "chars": len(text), "lines": lines[:MAX_TEXT_LINES]}

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

    @app.post("/profile/rescore")
    def rescore_profile(profile: dict, conn=Depends(get_conn)):
        """A profile saved in the browser, re-scored against the latest snapshot. No CV needed: the skills it found
        (with their quotes) are kept, and statuses, roles, evidence and insights are recomputed."""
        if not isinstance(profile.get("skills"), list):
            raise HTTPException(422, "Expected a profile from /profile/extract")
        return cv.rescore(profile, cur, conn)

    # ---------- user journey (PRD 5) ----------

    def _profile(req: JourneyRequest) -> journey.Profile:
        ids = {s.id for s in req.skills} | set(req.completed)
        unknown = sorted(i for i in ids if i not in cur.concepts)
        bad_occ = [o for o in (req.occupation, req.role) if o and o not in cur.role_titles]
        if unknown or bad_occ:
            raise HTTPException(422, {"unknown_concepts": unknown, "unknown_occupations": bad_occ})
        if any(not 1 <= g <= 17 for g in req.sdgs):
            raise HTTPException(422, "SDGs are numbered 1 to 17")
        return journey.Profile(skills={s.id: s.evidence for s in req.skills}, occupation=req.occupation,
                               overrides=req.overrides, scenario=req.scenario, sdgs=sorted(set(req.sdgs)),
                               role=req.role, completed=req.completed, pace=req.pace)

    def _resources(conn) -> dict:
        """Learning resources for The Route: the curated table plus ImpactMojo's live catalog. When ImpactMojo
        can't be reached (and nothing is cached), the curated table alone still gives each covered step a link."""
        from .connectors import impactmojo

        try:
            live_courses = impactmojo.resources(cur, conn)
        except FetchError as e:
            log.warning("ImpactMojo unavailable, using curated resources only: %s", e)
            live_courses = {}
        return {cid: cur.resources.get(cid, []) + live_courses.get(cid, [])
                for cid in cur.resources.keys() | live_courses.keys()}

    @app.get("/journey/catalog")
    def journey_catalog(conn=Depends(get_conn)):
        """Occupations for The Mirror, SDGs for the lens, snapshots for The Ping, and the scoring rules."""
        sid = _snapshot_id(conn, None)
        mycol = journey.mycol_codes(conn, "9999-12-31")
        masco = {isco: code for (system, code), isco in cur.occupation_codes.items() if system == "MASCO"}
        from .connectors import esco
        names = esco.aliases()
        occupations = [{"isco": isco, "title": title, "occupation": cur.occupation_titles[isco],
                        "aliases": names.get(isco, []),
                        "esco_occupation": cur.tasks[isco][0].occupation if isco in cur.tasks else None,
                        "tasks": len(cur.tasks.get(isco, [])), "mycol": mycol.get(masco.get(isco, ""))}
                       for isco, title in sorted(cur.role_titles.items(), key=lambda x: x[1])]
        goals = sorted({t.sdg for (kind, _), tags in cur.sdg_tags.items() if kind == "role" for t in tags})
        return {
            "latest_snapshot": sid,
            "snapshots": [dict(r) for r in conn.execute("SELECT id, as_of FROM snapshot ORDER BY as_of")],
            "occupations": occupations,
            "sdgs": [{"sdg": g, "name": journey.SDG_NAMES[g]} for g in goals],
            "skills": sorted(({"id": cid, "label": c.label} for cid, c in cur.concepts.items() if c.kind == "skill"),
                             key=lambda x: x["label"].lower()),
            "scenarios": [{"id": "moderate", "label": "Moderate"}, {"id": "fast", "label": "Fast"}],
            "rules": journey.WEIGHTS_DOC,
        }

    @app.post("/journey")
    def journey_build(req: JourneyRequest, conn=Depends(get_conn)):
        """The Mirror, Ghost CV, Three Bets, full ranking and Route for one profile, snapshot and scenario."""
        return journey.build(cur, conn, _snapshot_id(conn, req.snapshot), _profile(req), _resources(conn))

    @app.post("/journey/plan")
    def journey_plan(req: JourneyRequest, conn=Depends(get_conn)):
        """The Route as an AI learning plan: Gemini writes what to learn and a practice task per step, and picks
        courses from a search of the real Coursera catalogue. 503 with a reason when no plan can be written; the
        page then shows the rule-based route."""
        from . import plan

        p = _profile(req)
        j = journey.build(cur, conn, _snapshot_id(conn, req.snapshot), p, _resources(conn))
        if not j["route"]:
            raise HTTPException(422, "Choose a job first")
        have = [cur.concepts[s].label for s in p.skills if s in cur.concepts]
        try:
            return plan.build(conn, j["route"], j["route"]["role"], have)
        except plan.PlanUnavailable as e:
            raise HTTPException(503, str(e))

    @app.post("/journey/ping")
    def journey_ping(req: PingRequest, conn=Depends(get_conn)):
        """What changed for this profile between two snapshots (The Ping)."""
        return journey.ping(cur, conn, _snapshot_id(conn, req.from_snapshot), _snapshot_id(conn, req.to_snapshot),
                            _profile(req))

    @app.post("/journey/brief")
    def journey_brief(req: BriefRequest, conn=Depends(get_conn)):
        """A plain-language brief of the bets or of a ping, written by Gemini and checked against the computed
        result (PRD FR-10.4), or the fixed template."""
        p = _profile(req)
        if req.kind == "bets":
            facts, terms, template = brief.bets_facts(journey.build(cur, conn, _snapshot_id(conn, req.snapshot), p, _resources(conn)))
        else:
            if not req.from_snapshot:
                raise HTTPException(422, "from_snapshot is required for a ping brief")
            diff = journey.ping(cur, conn, _snapshot_id(conn, req.from_snapshot), _snapshot_id(conn, req.snapshot), p)
            facts, terms, template = brief.ping_facts(diff)
        return brief.write(cur, facts, terms, template)

    return app, background


def create_app(live_mode: bool | None = None, replay: bool | None = None) -> FastAPI:
    """The signal API on its own (`kompas serve`). backend/app serves the same routes under /api/signals."""
    router, background = create_router(live_mode, replay)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with background():
            yield

    app = FastAPI(title="Kompas Signal API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("KOMPAS_CORS", "http://localhost:3000").split(","),
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    app.include_router(router)
    return app
