"""Plain-language briefs for computed journey results (PRD FR-10.2b, FR-10.4).

The facts come from journey.py. Gemini may rephrase them; a post-check then rejects any brief that mentions
a role, skill or number that isn't in those facts, and the fixed template is used instead. Without an API key
the template is used directly. Either way the response says which one wrote it.
"""

import re

from . import llm
from .curated import Curated

INSTRUCTIONS = """You write a short, plain-language brief for a career guidance app, from the facts given as JSON.
Rules:
- Use only the facts. Don't add roles, skills, courses, numbers, dates or claims that aren't in them.
- Name roles and skills exactly as written in the facts.
- At most 70 words, second person ("you"), no headings or lists, no hype.
- Describe estimates as estimates."""

SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


def _terms(cur: Curated) -> set[str]:
    """Every role title and skill label the app knows, for the post-check."""
    return {c.label for c in cur.concepts.values()} | set(cur.role_titles.values())


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def check(text: str, facts_text: str, allowed_terms: set[str], cur: Curated) -> str | None:
    """Why a brief can't be shown, or None. Unknown numbers and catalogue terms outside the facts fail it."""
    stray = _numbers(text) - _numbers(facts_text)
    if stray:
        return f"numbers not in the facts: {sorted(stray)}"
    for term in _terms(cur) - allowed_terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
            return f"mentions '{term}', which isn't in the result"
    if len(text.split()) > 90:
        return "too long"
    return None


def bets_facts(journey: dict) -> tuple[dict, set[str], str]:
    names = {"safe": "Safe Bet", "rising": "Rising Bet", "impact": "Impact Bet"}
    facts, terms = {"scenario": journey["scenario"], "bets": []}, set()
    for kind, b in journey["bets"].items():
        if "isco" not in b:
            closest = b.get("closest")
            facts["bets"].append({"kind": names[kind], "role": None, "closest_below_40_percent":
                                  closest and {"role": closest["title"], "match_percent": closest["match"]}})
            if closest:
                terms.add(closest["title"])
            continue
        terms.add(b["title"])
        entry = {"kind": names[kind], "role": b["title"], "match_percent": b["match"],
                 "skills_you_have": [h["label"] for h in b["have"]][:4],
                 "skills_to_learn": [g["label"] for g in b["gaps"]][:4],
                 "sdgs": [t["name"] for t in b["sdgs"]], "on_malaysia_critical_list": bool(b["mycol"])}
        terms.update(entry["skills_you_have"] + entry["skills_to_learn"])
        facts["bets"].append(entry)
    parts = []
    for e in facts["bets"]:
        if e["role"] is None:
            c = e["closest_below_40_percent"]
            parts.append(f"No {e['kind']} reaches a 40% match yet" + (f" (closest: {c['role']}, {c['match_percent']}%)" if c else
                         " (pick the goals you care about)" if e["kind"] == "Impact Bet" else ""))
        else:
            learn = f", learning {', '.join(e['skills_to_learn'][:2])}" if e["skills_to_learn"] else ""
            parts.append(f"{e['kind']}: {e['role']} ({e['match_percent']}% match{learn})")
    template = ". ".join(parts) + f". Scores are estimates under the {journey['scenario']} scenario."
    return facts, terms, template


def ping_facts(diff: dict) -> tuple[dict, set[str], str]:
    names = {"safe": "Safe Bet", "rising": "Rising Bet", "impact": "Impact Bet"}
    facts = {"from_snapshot": diff["from"]["as_of"], "to_snapshot": diff["to"]["as_of"],
             "skill_changes": [{"skill": s["label"], "from": s["from"], "to": s["to"], "why": s["reason"]}
                               for s in diff["skills"]],
             "bet_changes": [{"bet": names[b["kind"]], "from": b["from"] and b["from"]["title"],
                              "to": b["to"] and b["to"]["title"]} for b in diff["bets"]],
             "route_reordered": diff["route"]["changed"],
             "new_ghost_cv_slots": [x["label"] for x in diff["ghost"]["new_slots"]]}
    terms = {s["label"] for s in diff["skills"]} | {x for b in diff["bets"] for x in
                                                    ((b["from"] or {}).get("title"), (b["to"] or {}).get("title")) if x}
    terms |= set(diff["route"]["labels"].values()) | set(facts["new_ghost_cv_slots"])
    if not diff["changed"]:
        template = f"Nothing that affects you changed between {facts['from_snapshot']} and {facts['to_snapshot']}."
    else:
        bits = [f"{s['skill']} moved from {s['from']} to {s['to']}" for s in facts["skill_changes"][:4]]
        bits += [f"your {b['bet']} is now {b['to'] or 'empty'}" for b in facts["bet_changes"]]
        if diff["route"]["changed"]:
            bits.append("your route was reordered")
        template = f"Since {facts['from_snapshot']}: " + "; ".join(bits) + "."
    return facts, terms, template


def write(cur: Curated, facts: dict, terms: set[str], template: str, client=None) -> dict:
    import json

    facts_text = json.dumps(facts, ensure_ascii=False)
    result, error = llm._generate(INSTRUCTIONS, f"<facts>\n{facts_text}\n</facts>", SCHEMA, client)
    if result and result.get("text"):
        problem = check(result["text"], facts_text + " " + template, terms, cur)
        if problem is None:
            return {"text": result["text"].strip(), "by": llm.MODEL}
        error = f"brief rejected by the post-check: {problem}"
    return {"text": template, "by": "template", "note": error}
