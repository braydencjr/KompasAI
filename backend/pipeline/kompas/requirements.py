"""A role's skills as Malaysian employers ask for them, measured from live job postings.

The role's postings come from JSearch (Google for Jobs: JobStreet, LinkedIn, Indeed, employers' sites; the same
cached search as the "Open jobs" panel). The LLM lists the skills each posting asks for, each with a verbatim quote
that is checked against that posting; Kompas's dictionary tagger adds the tracked skills it finds by name; skills
outside Kompas's list are resolved to ESCO (kompas/open_skills.py). A skill's weight is how many postings ask for
it: in at least half, essential (1.0); in at least a fifth, optional (0.5). The result replaces the hand-made
concept_occupation.csv links for that role when there are enough postings, and is refreshed weekly.
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from . import db, llm, open_skills
from .connectors import ilo, jsearch
from .curated import Curated
from .http import FetchError
from .periods import utcnow
from .tag import Tagger

log = logging.getLogger("kompas.requirements")

MIN_POSTINGS = 5        # with fewer, the curated links stand
MIN_DESCRIPTION = 200   # characters: shorter descriptions don't list requirements
MIN_SHARE = 0.2         # asked for by at least a fifth of the postings ...
MIN_COUNT = 2           # ... and at least two of them
ESSENTIAL_SHARE = 0.5
MAX_SKILLS = 12
MIN_SKILLS = 3
TTL = timedelta(days=7)


def _norm(s: str) -> str:
    from .cv import _norm as norm
    return norm(s)


def title_for(cur: Curated, conn, isco: str) -> str | None:
    if isco in cur.role_titles:
        return cur.role_titles[isco]
    occ = ilo.INDEX.load(conn).occupations.get(isco)
    return occ.title if occ else None


def build(conn, cur: Curated, isco: str, client=None) -> tuple[dict | None, str | None]:
    """Fetches the role's postings, measures what they ask for and stores it. Returns (row, None) or (None, why)."""
    from .cv import _line_around, verbatim

    title = title_for(cur, conn, isco)
    if not title:
        return None, f"unknown occupation {isco}"
    try:
        found = jsearch.search(conn, title)
    except FetchError as e:
        return None, str(e)
    postings = [j for j in found["jobs"] if len(j.get("description") or "") >= MIN_DESCRIPTION]
    if len(postings) < MIN_POSTINGS:
        return None, found.get("note") or f"only {len(postings)} postings with a description"
    items = [{"id": f"P{n}", "title": j["title"], "text": j["description"]} for n, j in enumerate(postings, start=1)]
    by_id = {i["id"]: i for i in items}
    norm = {i["id"]: _norm(f"{i['title']}\n{i['text']}") for i in items}

    asks: dict[str, dict[str, str]] = {i["id"]: {} for i in items}     # posting -> skill -> quote
    extraction, error = llm.extract_postings(items, cur, client=client)
    unresolved: list[tuple[str, str, str]] = []                          # (posting, name, quote)
    for entry in extraction or []:
        pid = entry.get("posting_id")
        if pid not in by_id:
            continue
        for s in entry.get("skills") or []:
            if not verbatim(s.get("quote") or "", norm[pid]):
                continue
            if s["skill_id"] in cur.concepts:
                asks[pid].setdefault(s["skill_id"], s["quote"])
            elif (s.get("name") or "").strip():
                unresolved.append((pid, s["name"].strip(), s["quote"]))
    if unresolved:
        ids, _why = open_skills.resolve(conn, cur, [n for _, n, _ in unresolved], "job postings", client=client)
        for pid, name, quote in unresolved:
            if ids.get(name):
                asks[pid].setdefault(ids[name], quote)
    # the tracked skills a posting names outright, whether or not the model listed them
    tagger = Tagger(cur)
    for i in items:
        text = f"{i['title']}\n{i['text']}"
        for cid, _m, _span, start in tagger.find_all(text):
            if cur.concepts[cid].kind == "skill":
                asks[i["id"]].setdefault(cid, _line_around(text, start))

    n = len(items)
    count: dict[str, list[str]] = {}
    for pid, skills in asks.items():
        for cid in skills:
            count.setdefault(cid, []).append(pid)
    kept = sorted(((cid, pids) for cid, pids in count.items() if len(pids) >= MIN_COUNT and len(pids) / n >= MIN_SHARE),
                  key=lambda x: (-len(x[1]), x[0]))[:MAX_SKILLS]
    if len(kept) < MIN_SKILLS:
        return None, f"the postings agree on only {len(kept)} skills" + (f" ({error})" if error else "")
    skills = [{"id": cid, "label": cur.concepts[cid].label, "count": len(pids), "share": round(len(pids) / n, 2),
               "importance": 1.0 if len(pids) / n >= ESSENTIAL_SHARE else 0.5,
               "quotes": [{"posting": pid, "text": asks[pid][cid]} for pid in pids[:3]]} for cid, pids in kept]
    payload = {"skills": skills, "source": found["source"], "searched": found.get("fetched_at"),
               "listing": [{"id": i["id"], "title": j["title"], "employer": j["employer"], "url": j["url"],
                             "posted": j["posted"]} for i, j in zip(items, postings)]}
    row = {"isco": isco, "title": title, "fetched_at": utcnow(), "postings": n, "skills": payload,
           "model": llm.MODEL if extraction else None}
    conn.execute("INSERT INTO role_requirement (isco, title, fetched_at, postings, skills, model) VALUES (?, ?, ?, ?, ?, ?) "
                 "ON CONFLICT (isco) DO UPDATE SET title = excluded.title, fetched_at = excluded.fetched_at, "
                 "postings = excluded.postings, skills = excluded.skills, model = excluded.model",
                 (isco, title, row["fetched_at"], n, json.dumps(payload), row["model"]))
    conn.commit()
    _apply(cur, row)
    return row, None


def _apply(cur: Curated, row: dict) -> None:
    """Copy and swap, never mutate: this runs in background threads while requests iterate the dicts."""
    payload = row["skills"]
    skills = [(s["id"], s["importance"]) for s in payload["skills"] if s["id"] in cur.concepts]
    meta = {**payload, "title": row["title"], "postings": row["postings"], "fetched_at": row["fetched_at"]}
    cur.posting_meta = {**cur.posting_meta, row["isco"]: meta}
    cur.posting_roles = {**cur.posting_roles, row["isco"]: skills}


_loaded = [0.0]
RELOAD_SECONDS = 120


def load_into(cur: Curated, conn, force: bool = False) -> None:
    """Every stored requirement onto cur (the ESCO skills they name first, so the ids resolve). Reloaded every
    RELOAD_SECONDS, since another process may have measured a role."""
    import time

    if not force and time.monotonic() - _loaded[0] < RELOAD_SECONDS:
        return
    open_skills.load_into(cur, conn, force=True)
    for r in conn.execute("SELECT * FROM role_requirement"):
        _apply(cur, {**dict(r), "skills": json.loads(r["skills"])})
    _loaded[0] = time.monotonic()


def stale(cur: Curated, isco: str) -> bool:
    meta = cur.posting_meta.get(isco)
    if not meta:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched_at"].replace("Z", "+00:00")) > TTL


_running: set[str] = set()
_tried: dict[str, datetime] = {}
_lock = threading.Lock()
RETRY = timedelta(hours=6)       # a role whose postings can't be used isn't asked about again for a while


def ensure_async(cur: Curated, isco: str | None) -> None:
    """Measures a role in the background when it has no fresh requirements: requests never wait for JSearch."""
    if not isco or not jsearch.available() or not stale(cur, isco):
        return
    now = datetime.now(timezone.utc)
    with _lock:
        if isco in _running or now - _tried.get(isco, now - RETRY) < RETRY:
            return
        _running.add(isco)
        _tried[isco] = now

    def run():
        conn = db.connect()
        try:
            _row, why = build(conn, cur, isco)
            if why:
                log.info("requirements for %s not updated: %s", isco, why)
        except Exception:
            log.exception("requirements for %s failed", isco)
        finally:
            conn.close()
            with _lock:
                _running.discard(isco)

    threading.Thread(target=run, daemon=True, name=f"requirements-{isco}").start()
