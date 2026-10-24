"""The reasons behind each suggested job, written by the LLM from an evidence pack and checked against it.

journey.reasons() writes every reason from fixed templates. Here the LLM rewrites the fit, demand, trend and AI
reasons from the job's evidence pack: the computed facts plus the records behind them (what its Malaysian postings
ask for, the ILO's scores for its tasks, the hiring and research items behind its skills' statuses, the person's
CV quotes). Every sentence must cite the pack's evidence ids, and a check rejects a reason that cites anything
else, uses a number that isn't in the pack, or names a role or skill outside it; that reason keeps its template.
The citations are removed before the text is shown, so the cards look as before. The evidence lists under each
reason are journey.reasons()' own, unchanged.

Written once per pack (keyed by its hash, in the narration table). mode "sync" waits for the model (the CV flow,
which already waits for it); "background" answers with the templates and writes the reasons for the next request
(the journey, whose toggles must stay instant).
"""

import hashlib
import json
import logging
import re
import threading

from . import db, llm
from .connectors import ilo
from .curated import Curated
from .periods import utcnow

log = logging.getLogger("kompas.narrate")

KINDS = ("fit", "demand", "trend", "ai")
MAX_ROLES = 8
MAX_WORDS = 55
VERSION = "4"       # bump when the pack or the prompt changes, so old texts aren't reused

RISING = ("Emerging", "Act now")
PLAIN = {"Act now": "in demand in Malaysia right now", "Emerging": "growing abroad, not yet in Malaysia",
         "Watch": "talked about, with no hiring behind it yet", "Stable": "steady", "Declining": "falling",
         "Stalled": "stalled after a burst of hype"}

_CITE = re.compile(r"\s*\[(E\d+(?:\s*,\s*E\d+)*)\]")
_cache: dict[str, dict] = {}
_running: set[str] = set()
_lock = threading.Lock()


def pack(cur: Curated, role: dict, quotes: dict[str, str], sig: dict) -> dict:
    """The facts and evidence one job's reasons may use. quotes: skill id -> the CV line that shows it."""
    evidence: list[dict] = []

    def add(**item) -> str:
        eid = f"E{len(evidence) + 1}"
        evidence.append({"id": eid, **item})
        return eid

    isco = role["isco"]
    kinds = ["fit"]
    if role["have"]:
        add(type="your skills", skills=[h["label"] for h in role["have"]],
            of_the_jobs_skills=[r["label"] for r in role["breakdown"]])
    for h in role["have"]:
        if h["id"] in quotes:
            add(type="your CV", skill=h["label"], quote=quotes[h["id"]])
    meta = cur.posting_meta.get(isco) if isco in cur.posting_roles else None
    if meta:
        add(type="job postings", about=f"a sample of {meta['postings']} live Malaysian job postings for this role "
                                        "(one search page, not a count of openings)",
            source=meta.get("source"), searched=(meta.get("fetched_at") or "")[:10])
        for s in meta["skills"][:6]:
            add(type="what the postings ask for", skill=s["label"], asked_in=s["count"], of=meta["postings"],
                quote=s["quotes"][0]["text"] if s["quotes"] else None)
    fam, fstat = role.get("family"), role.get("family_status")
    if fam and fstat:
        add(type="hiring signal", jobs=fam["label"], demand=PLAIN.get(fstat, fstat))
        for e in (sig.get(fam["id"]) or {}).get("evidence", [])[:2]:
            add(type="hiring record", title=e["title"], source=e["source"], date=e["date"])
        kinds.append("demand")
    if role.get("mycol"):
        add(type="official list", text=f"On Malaysia's Critical Occupations List, {role['mycol']}")
        if "demand" not in kinds:
            kinds.append("demand")
    # a breakdown row's status is the projected one (the scenario's 2028); today's is the measured one in `sig`
    rising = [r for r in role["breakdown"] if r["status"] in RISING][:3]
    for r in rising:
        now = (sig.get(r["id"]) or {}).get("status") or r["status"]
        add(type="skill trend", skill=r["label"], today=PLAIN.get(now, now),
            by_2028_if_ai_keeps_its_pace=PLAIN.get(r["status"], r["status"]).removesuffix(" right now"))
        for e in (sig.get(r["id"]) or {}).get("evidence", [])[:2]:
            add(type="trend record", skill=r["label"], title=e["title"], source=e["source"], date=e["date"])
    if rising:
        kinds.append("trend")
    occ = ilo.INDEX.occupations.get(isco)
    tasks = sorted(ilo.INDEX.tasks.get(isco, []), key=lambda t: -t.score)
    if occ and tasks and role.get("ai_exposure") is not None:
        add(type="ILO exposure index", occupation=occ.title, category=occ.gradient, mean_task_score=occ.mean,
            estimated_by_llm=occ.origin == "llm")
        for t in [*tasks[:2], tasks[-1]] if len(tasks) > 2 else tasks:
            add(type="ILO task score", task=t.label, score=t.score)
        kinds.append("ai")
    facts = {"job": role["title"], "match_percent": role["match"],
             "skills_you_have": [h["label"] for h in role["have"]], "skills_to_learn": [g["label"] for g in role["gaps"]],
             "ai_exposed_percent_of_tasks": role.get("ai_exposure"), "horizon": "2028"}
    return {"job_id": isco, "kinds": kinds, "facts": facts, "evidence": evidence}


def _key(p: dict) -> str:
    return "why:" + hashlib.sha256(json.dumps([VERSION, llm.MODEL, p], sort_keys=True).encode()).hexdigest()[:24]


def _numbers(text: str) -> set[str]:
    return {n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?", text)}


def _terms(cur: Curated) -> set[str]:
    return {c.label for c in cur.concepts.values()} | set(cur.role_titles.values())


def check(text: str, p: dict, cur: Curated) -> str | None:
    """Why a reason can't be shown, or None."""
    ids = {e["id"] for e in p["evidence"]}
    cited = [i.strip() for m in _CITE.finditer(text) for i in m.group(1).split(",")]
    if not cited:
        return "cites no evidence"
    if set(cited) - ids:
        return f"cites evidence not in the pack: {sorted(set(cited) - ids)}"
    sentences = [x for x in re.split(r"(?<=[.!?])\s+(?!\[)", text.strip()) if x.strip()]
    if any(not _CITE.search(x) for x in sentences):
        return "a sentence cites no evidence"
    plain = strip(text)
    source = json.dumps(p, ensure_ascii=False)
    stray = _numbers(plain) - _numbers(source)
    if stray:
        return f"numbers not in the pack: {sorted(stray)}"
    lower = source.lower()
    # a status in other words than its evidence's ("in demand in Malaysia" for a skill only growing abroad)
    for phrase in PLAIN.values():
        if phrase.lower() in plain.lower() and phrase.lower() not in lower:
            return f"says '{phrase}', which no evidence says"
    if re.search(r"\bin demand\b", plain, re.IGNORECASE) and "in demand" not in lower:
        return "calls something in demand that no evidence calls in demand"
    for term in _terms(cur):
        if term.lower() not in lower and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", plain, re.IGNORECASE):
            return f"mentions '{term}', which isn't in the pack"
    if len(plain.split()) > MAX_WORDS:
        return "too long"
    return None


def strip(text: str) -> str:
    out = _CITE.sub("", text)
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", out)).strip()


def _write(cur: Curated, conn, todo: list[tuple[str, dict]], client=None) -> dict[str, dict]:
    """Asks the model for the packs' reasons, checks each, stores what holds up. Returns key -> {kind: text}."""
    result, error = llm.narrate([p for _, p in todo], client=client)
    if result is None:
        log.info("reasons not written: %s", error)
        return {}
    by_job = {p["job_id"]: (k, p) for k, p in todo}
    out: dict[str, dict] = {k: {} for k, _ in todo}
    for r in result:
        if r.get("job_id") not in by_job or r.get("kind") not in KINDS:
            continue
        key, p = by_job[r["job_id"]]
        if r["kind"] not in p["kinds"] or r["kind"] in out[key]:
            continue
        problem = check(r.get("text") or "", p, cur)
        if problem:
            log.info("reason %s/%s rejected: %s", r["job_id"], r["kind"], problem)
            continue
        out[key][r["kind"]] = strip(r["text"])
    now = utcnow()
    conn.executemany("INSERT INTO narration (key, created_at, payload) VALUES (?, ?, ?) ON CONFLICT (key) DO NOTHING",
                     [(k, now, json.dumps(v)) for k, v in out.items()])
    conn.commit()
    _cache.update(out)
    return out


def _use(role: dict, texts: dict) -> None:
    for r in role.get("reasons") or []:
        if r["kind"] in texts:
            r["text"] = texts[r["kind"]]
            r["by"] = llm.MODEL


def apply(cur: Curated, conn, roles: list[dict], quotes: dict[str, str], sig: dict, mode: str = "background",
          client=None) -> None:
    """Replaces template reasons of `roles` (which already carry journey.reasons()) with checked LLM ones."""
    if not llm.available() and client is None:
        return
    packs = [(r, pack(cur, r, quotes, sig)) for r in roles[:MAX_ROLES] if r.get("reasons")]
    keyed = [(r, _key(p), p) for r, p in packs]
    missing = [k for _, k, _ in keyed if k not in _cache]
    if missing:
        q = ",".join("?" * len(missing))
        _cache.update({row["key"]: json.loads(row["payload"]) for row in
                       conn.execute(f"SELECT key, payload FROM narration WHERE key IN ({q})", missing)})
    todo = [(k, p) for _, k, p in keyed if k not in _cache]
    if todo and mode == "sync":
        _write(cur, conn, todo, client)
    elif todo and mode == "background":
        with _lock:
            todo = [(k, p) for k, p in todo if k not in _running]
            _running.update(k for k, _ in todo)
        if todo:
            def run():
                c = db.connect()
                try:
                    _write(cur, c, todo, client)
                except Exception:
                    log.exception("writing reasons failed")
                finally:
                    c.close()
                    with _lock:
                        _running.difference_update(k for k, _ in todo)
            threading.Thread(target=run, daemon=True, name="narrate").start()
    for r, k, _ in keyed:
        if k in _cache:
            _use(r, _cache[k])
