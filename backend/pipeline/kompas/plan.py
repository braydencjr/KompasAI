"""The Route's AI learning plan: Gemini turns the computed route (which skills, in which order) into a learning path,
and every course in it is a real Coursera catalogue entry found by search.

1. journey.route() decides the steps: the role's skill gaps, prerequisites first, then by Signal Ladder status.
2. Gemini writes, per step, what to learn, a practice task, a time estimate and search terms for courses.
3. The Coursera catalogue is searched with those terms: up to 8 real candidates per step.
4. Gemini picks the best 1 to 3 candidates per step, by id. Ids that weren't candidates are dropped, so the model
   can't add a course of its own (PRD: AI never invents courses).

The plan is advice, labelled as AI-written; steps, order and courses come from code and the catalogue. Plans are
cached for a week per role and set of skills, so each costs two Gemini calls once.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import llm
from .connectors import coursera

CACHE_DAYS = 7
MAX_COURSES = 3
CANDIDATES = 8

PLAN_INSTRUCTIONS = """You plan learning for Kompas, a career guidance app for working adults in Malaysia. The person
wants to move into the role below. The steps are fixed: the skills they still need, already in the right order.
For each step, write:
- `goal`: one sentence on what they will be able to do, in the context of the role.
- `learn`: 3 to 5 concrete subtopics to learn, in order.
- `practice`: one small, realistic task to prove the skill (something they could show an employer).
- `weeks`: a realistic estimate at about 5 hours a week (a whole number, 1 to 12).
- `queries`: 3 short course-search phrases (2 to 4 words each) that would find beginner-to-intermediate online
  courses for this skill, using the words course titles use (e.g. "carbon footprint", "greenhouse gas emissions").
Also write `summary`: at most 50 words to the person ("you"), on how the steps build towards the role.
Rules: use only the role, skills and steps given. Never name a specific course, provider, certificate or price, and
never state statistics; courses are chosen separately from a real catalogue."""

PICK_INSTRUCTIONS = """For each learning step, choose the best 1 to 3 courses from that step's candidates: the ones that
teach the step's skill most directly at a beginner-to-intermediate level. Use only candidate ids listed for that
step. If no candidate really teaches the skill, choose none. `note`: one short sentence on why these fit (no
statistics, no claims about the provider)."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"}, "goal": {"type": "string"},
                "learn": {"type": "array", "items": {"type": "string"}},
                "practice": {"type": "string"}, "weeks": {"type": "integer"},
                "queries": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["skill_id", "goal", "learn", "practice", "weeks", "queries"],
        }},
    },
    "required": ["summary", "steps"],
}

PICK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"skill_id": {"type": "string"}, "course_ids": {"type": "array", "items": {"type": "string"}},
                       "note": {"type": "string"}},
        "required": ["skill_id", "course_ids", "note"],
    }}},
    "required": ["picks"],
}


class PlanUnavailable(Exception):
    """No plan could be written (no Gemini key, the model failed, or the course catalogue is unreachable)."""


def _cache(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS plan_cache (key TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                 "payload TEXT NOT NULL)")


def _key(role: dict, steps: list[dict], have: list[str]) -> str:
    raw = json.dumps({"role": role["isco"], "steps": [s["id"] for s in steps], "have": sorted(have)})
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build(conn, route: dict, role: dict, have_labels: list[str], client=None) -> dict:
    """The learning plan for a computed route. Raises PlanUnavailable with a reason the UI can show."""
    steps = route["steps"]
    if not steps:
        raise PlanUnavailable("nothing to learn for this role: you have every skill Kompas tracks for it")
    _cache(conn)
    key = _key(role, steps, have_labels)
    row = conn.execute("SELECT created_at, payload FROM plan_cache WHERE key = ?", (key,)).fetchone()
    now = datetime.now(timezone.utc)
    if row and now - datetime.fromisoformat(row["created_at"]) < timedelta(days=CACHE_DAYS):
        return {**json.loads(row["payload"]), "cached": True}

    facts = {"role": role["title"], "your_skills": have_labels,
             "steps": [{"skill_id": s["id"], "skill": s["label"], "why": s["why"]} for s in steps]}
    written, error = llm._generate(PLAN_INSTRUCTIONS, json.dumps(facts, ensure_ascii=False), PLAN_SCHEMA, client)
    if error:
        raise PlanUnavailable(error)
    by_id = {s["skill_id"]: s for s in written.get("steps", []) if isinstance(s, dict)}

    try:
        cat = coursera.catalog(conn)
    except Exception as e:     # the plan is still useful without courses, but say why they're missing
        cat, course_note = None, f"Course search unavailable ({e})"
    else:
        course_note = None

    candidates: dict[str, list[dict]] = {}
    if cat:
        for s in steps:
            queries = [s["label"], *(by_id.get(s["id"], {}).get("queries") or [])[:3]]
            candidates[s["id"]] = coursera.search(cat, queries, CANDIDATES)

    picks: dict[str, dict] = {}
    if any(candidates.values()):
        listing = [{"skill_id": s["id"], "skill": s["label"], "goal": by_id.get(s["id"], {}).get("goal", ""),
                    "candidates": [{"id": c["id"], "title": c["title"], "provider": c["provider"]}
                                   for c in candidates[s["id"]]]} for s in steps]
        chosen, error = llm._generate(PICK_INSTRUCTIONS, json.dumps(listing, ensure_ascii=False), PICK_SCHEMA, client)
        if error:
            course_note = f"Courses couldn't be chosen this time ({error}); showing the closest search results"
        for p in (chosen or {}).get("picks", []):
            if isinstance(p, dict) and p.get("skill_id") in candidates:
                picks[p["skill_id"]] = p

    out_steps = []
    for s in steps:
        w = by_id.get(s["id"], {})
        real = {c["id"]: c for c in candidates.get(s["id"], [])}
        pick = picks.get(s["id"])
        if pick is not None:
            # only ids that were real candidates survive
            courses = [real[i] for i in pick.get("course_ids", []) if i in real][:MAX_COURSES]
        else:
            courses = list(real.values())[:MAX_COURSES] if real and not picks else []
        out_steps.append({
            "id": s["id"], "label": s["label"], "status": s["status"], "order": s["order"],
            "goal": w.get("goal") or s["why"], "learn": [x for x in w.get("learn", []) if isinstance(x, str)][:5],
            "practice": w.get("practice") or "", "weeks": max(1, min(12, int(w.get("weeks") or 2))),
            "courses": courses, "course_note": (pick or {}).get("note") or "",
            # the curated or ImpactMojo course the rule-based route already had, kept as a fallback
            "resource": s.get("resource"),
        })
    plan = {
        "role": {"isco": role["isco"], "title": role["title"]},
        "summary": written.get("summary") or "",
        "steps": out_steps,
        "weeks": sum(s["weeks"] for s in out_steps),
        "by": llm.MODEL,
        "courses_from": coursera.PROVIDER if cat else None,
        "catalog_fetched_at": cat["fetched_at"] if cat else None,
        "note": course_note,
        "created_at": now.isoformat(timespec="seconds"),
    }
    conn.execute("INSERT INTO plan_cache (key, created_at, payload) VALUES (?, ?, ?) ON CONFLICT (key) DO UPDATE SET "
                 "created_at = excluded.created_at, payload = excluded.payload", (key, plan["created_at"], json.dumps(plan)))
    conn.commit()
    return {**plan, "cached": False}
