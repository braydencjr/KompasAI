"""SDG tags for every role and skill (PRD FR-7.1): which UN Sustainable Development Goal each one contributes to, the
UN target the link rests on, and one sentence on how.

Three layers, best first:
1. curated: the hand-written rows in curated/sdg_tag.csv (roles and the skills Kompas tracks);
2. ai: for any other skill (most of an AI plan's skills come from ESCO) or role, Gemini picks one or two goals and
   writes the sentence. Its answer is checked (goal 1-17, a target of that goal, a sentence of sensible length) and
   saved in sdg_tag_ai, so each skill is tagged once and later requests read it like the curated rows;
3. default: when no model is reachable, a general link that is always true (a skill builds the skills for employment of
   target 4.4; a job provides work under target 8.5). It is not saved, so the next request tries the model again.

Every tag says where it came from (`origin`), and the page says so for anything the AI wrote.
"""

import json
import re
from datetime import datetime, timezone

from . import llm
from .curated import Curated

SDG_NAMES = {1: "No poverty", 2: "Zero hunger", 3: "Good health and well-being", 4: "Quality education",
             5: "Gender equality", 6: "Clean water and sanitation", 7: "Affordable and clean energy",
             8: "Decent work and economic growth", 9: "Industry, innovation and infrastructure",
             10: "Reduced inequalities", 11: "Sustainable cities and communities",
             12: "Responsible consumption and production", 13: "Climate action", 14: "Life below water",
             15: "Life on land", 16: "Peace, justice and strong institutions", 17: "Partnerships for the goals"}

DEFAULTS = {
    "skill": (4, "4.4", "Building this skill adds to the skills for employment and decent jobs that target 4.4 asks for."),
    "role": (8, "8.5", "This job is part of the full and productive employment and decent work that target 8.5 asks for."),
}
MAX_BATCH = 30
MAX_TAGS = 2
TARGET = re.compile(r"^(\d{1,2})\.(\d{1,2}|[a-z])$")
SENTENCE = (15, 260)

INSTRUCTIONS = """You tag jobs and skills with the UN Sustainable Development Goals for a career guidance app in
Malaysia. For each item give the 1 or 2 goals it contributes to most directly. Per goal:
- `sdg`: the goal number, 1 to 17.
- `target`: the UN target the link rests on, written like "8.5" or "9.c". It must belong to that goal.
- `rationale`: one plain sentence, at most 30 words, on HOW this skill or job contributes. Name what the work does, so
  the sentence couldn't be pasted onto a different item. No statistics, no claims about Malaysia's figures.
Use the goal where the link is strongest and don't force a second one. Return every item, using the ids and kinds given."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"}, "kind": {"type": "string"},
            "tags": {"type": "array", "items": {
                "type": "object",
                "properties": {"sdg": {"type": "integer"}, "target": {"type": "string"}, "rationale": {"type": "string"}},
                "required": ["sdg", "target", "rationale"],
            }},
        },
        "required": ["id", "kind", "tags"],
    }}},
    "required": ["items"],
}


def tag(sdg: int, target: str | None, rationale: str | None, origin: str) -> dict:
    return {"sdg": sdg, "name": SDG_NAMES[sdg], "target": target, "rationale": rationale, "origin": origin}


def curated(cur: Curated, kind: str, eid: str) -> list[dict]:
    return [tag(t.sdg, t.target, t.rationale, "curated") for t in cur.sdg_tags.get((kind, eid), [])]


def default(kind: str) -> list[dict]:
    sdg, target, why = DEFAULTS[kind]
    return [tag(sdg, target, why, "default")]


def _table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS sdg_tag_ai (entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, sdg INTEGER NOT NULL, "
                 "target TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "PRIMARY KEY (entity_type, entity_id, sdg))")


def saved(conn, kind: str, eid: str) -> list[dict]:
    _table(conn)
    rows = conn.execute("SELECT sdg, target, rationale FROM sdg_tag_ai WHERE entity_type = ? AND entity_id = ? ORDER BY sdg",
                        (kind, eid)).fetchall()
    return [tag(r["sdg"], r["target"], r["rationale"], "ai") for r in rows]


def checked(raw: list) -> list[dict]:
    """The model's tags that hold up: a goal 1-17, a target of that goal, a sentence of sensible length."""
    out, seen = [], set()
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict):
            continue
        sdg, target, why = t.get("sdg"), str(t.get("target") or "").strip().lower(), str(t.get("rationale") or "").strip()
        m = TARGET.match(target)
        if (isinstance(sdg, int) and not isinstance(sdg, bool) and sdg in SDG_NAMES and m and int(m.group(1)) == sdg
                and SENTENCE[0] <= len(why) <= SENTENCE[1] and sdg not in seen):
            seen.add(sdg)
            out.append({"sdg": sdg, "target": target, "rationale": why})
    return out[:MAX_TAGS]


def generate(conn, items: list[dict], client=None) -> dict[tuple[str, str], list[dict]]:
    """Gemini's tags for items [{kind, id, label}], saved. Items it gave nothing usable for are left out."""
    if not items:
        return {}
    wanted = {(i["kind"], i["id"]) for i in items}
    out, now = {}, datetime.now(timezone.utc).isoformat(timespec="seconds")
    for start in range(0, len(items), MAX_BATCH):
        batch = items[start:start + MAX_BATCH]
        facts = [{"id": i["id"], "kind": i["kind"], "name": i["label"]} for i in batch]
        answer, error = llm._generate(INSTRUCTIONS, json.dumps(facts, ensure_ascii=False), SCHEMA, client)
        if error or not isinstance(answer, dict):
            continue
        _table(conn)
        for row in answer.get("items", []):
            key = (row.get("kind"), row.get("id")) if isinstance(row, dict) else None
            good = checked(row.get("tags")) if key in wanted else []
            if not good:
                continue
            for t in good:
                conn.execute("INSERT INTO sdg_tag_ai (entity_type, entity_id, sdg, target, rationale, created_at) "
                             "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (entity_type, entity_id, sdg) DO UPDATE SET "
                             "target = excluded.target, rationale = excluded.rationale, created_at = excluded.created_at",
                             (key[0], key[1], t["sdg"], t["target"], t["rationale"], now))
            out[key] = [tag(t["sdg"], t["target"], t["rationale"], "ai") for t in good]
        conn.commit()
    return out


def resolve(conn, cur: Curated, items: list[dict], ask_model: bool = True, client=None) -> dict[str, list[dict]]:
    """Tags for items [{kind, id, label}] as {"kind:id": [tags]}: always at least one per item."""
    found: dict[tuple[str, str], list[dict]] = {}
    missing = []
    for i in items:
        key = (i["kind"], i["id"])
        if key in found:
            continue
        found[key] = curated(cur, *key) or saved(conn, *key)
        if not found[key]:
            missing.append(i)
    if missing and ask_model:
        found.update(generate(conn, list({(i["kind"], i["id"]): i for i in missing}.values()), client))
    return {f"{k}:{e}": tags or default(k) for (k, e), tags in found.items()}
