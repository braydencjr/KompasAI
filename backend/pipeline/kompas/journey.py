"""The user journey (PRD 5): The Mirror, Ghost CV, Three Bets with the SDG lens, The Route and The Ping.

Everything here is computed from a snapshot's Signal Ladder statuses and the curated tables, so the same
profile, snapshot and scenario always give the same result. The only LLM use is the optional plain-language
briefs (explain.py's checked writer), which only restate what is computed here.

A profile is what the browser holds: skills with an evidence level, the occupation of the current job,
Mirror overrides, the scenario, the SDGs the user cares about, the chosen role and completed route steps.
Nothing about the user is stored on the server.
"""

from collections import Counter
from dataclasses import dataclass, field

from . import explain
from .curated import Curated, task_matches
from .snapshot import _reason

SCENARIOS = ("moderate", "fast")
# PRD FR-4.2: demand multiplier by ladder status, and coverage by evidence level
DEMAND = {"Act now": 1.2, "Emerging": 1.1, "Stable": 1.0, "Watch": 0.9, "Declining": 0.7, "Stalled": 0.7}
COVERAGE = {"demonstrated": 1.0, "claimed": 0.7}
# The Mirror: how strongly an AI capability's status says it can do a task now (PRD FR-2.3)
EXPOSURE = {"Act now": 1.0, "Emerging": 0.8, "Watch": 0.6, "Stable": 0.4, "Stalled": 0.3, "Declining": 0.2}
EXPOSED_AT = 0.6
# the fast scenario's assumption: any task an AI capability already does at a basic level (Stable) gets taken over
EXPOSED_AT_FAST = 0.4


def exposed_at(scenario: str) -> float:
    return EXPOSED_AT_FAST if scenario == "fast" else EXPOSED_AT
# The Route: steps on the ladder's higher rungs come first (PRD FR-6.2)
PRIORITY = {"Act now": 0, "Emerging": 1, "Watch": 2, "Stable": 3, "Stalled": 4, "Declining": 5}
MIN_MATCH = 40          # PRD FR-4.3: Rising and Impact bets need at least this match
SAFE_SHARE = 0.7        # PRD FR-4.3: share of essential weight that must hold up under both scenarios
GHOST_SLOTS = 5
SDG_NAMES = {1: "No poverty", 2: "Zero hunger", 3: "Good health and well-being", 4: "Quality education",
             5: "Gender equality", 6: "Clean water and sanitation", 7: "Affordable and clean energy",
             8: "Decent work and economic growth", 9: "Industry, innovation and infrastructure",
             10: "Reduced inequalities", 11: "Sustainable cities and communities",
             12: "Responsible consumption and production", 13: "Climate action", 14: "Life below water",
             15: "Life on land", 16: "Peace, justice and strong institutions", 17: "Partnerships for the goals"}

WEIGHTS_DOC = {
    "match": "Match = Σ weight × coverage ÷ Σ weight, over the role's skills.",
    "weight": "Weight = importance (essential 1.0, optional 0.5) × demand (Act now 1.2, Emerging 1.1, Stable 1.0, "
              "Watch 0.9, Declining or Stalled 0.7), using each skill's status under the chosen scenario.",
    "coverage": "Coverage = 1.0 demonstrated, 0.7 claimed on a CV, 0 missing.",
    "safe": "Safe Bet: highest match where at least 70% of the essential weight is in skills that don't decline "
            "under either scenario.",
    "rising": "Rising Bet: highest demand × match among roles matching at least 40%. Demand is the role's "
              "importance-weighted average skill demand, raised 10% if the occupation is on Malaysia's Critical "
              "Occupations List (MyCOL).",
    "impact": "Impact Bet: highest SDG alignment × match among roles matching at least 40%. Alignment is the "
              "share of your chosen SDGs the role contributes to.",
    "exposure": "A task is AI-exposed when an AI capability that can do it scores at least 0.6: Act now 1.0, "
                "Emerging 0.8, Watch 0.6, Stable 0.4, Stalled 0.3, Declining 0.2, under the chosen scenario. The fast "
                "scenario assumes AI also takes over tasks a capability already does at a basic level (0.4 and up).",
    "route": "Route: missing skills of the chosen role (and the prerequisites you don't have), prerequisites "
             "first, then Act now, Emerging, Watch, Stable, then by weight.",
}


@dataclass
class Profile:
    skills: dict[str, str]                                  # concept id -> claimed | demonstrated
    occupation: str | None = None                           # ISCO code of the current job
    overrides: dict[str, dict] = field(default_factory=dict)  # task uri -> {"pile": "exposed"|"human", "reason"}
    scenario: str = "moderate"
    sdgs: list[int] = field(default_factory=list)
    role: str | None = None                                 # ISCO code of the chosen bet
    completed: list[str] = field(default_factory=list)      # route skills marked done
    pace: float = 5.0                                       # hours a week


class Statuses:
    """A snapshot's ladder statuses, readable per scenario."""

    def __init__(self, conn, snapshot_id: str | None):
        import json

        self.id, self.as_of, self.rows = snapshot_id, None, {}
        if snapshot_id is None:     # before the first snapshot: nothing is measured
            return
        self.as_of = conn.execute("SELECT as_of FROM snapshot WHERE id = ?", (snapshot_id,)).fetchone()["as_of"]
        for r in conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ? ORDER BY concept_id", (snapshot_id,)):
            self.rows[r["concept_id"]] = {"status": r["status"], "projected": json.loads(r["projected"]),
                                          "rungs": json.loads(r["rungs"]), "family_status": r["family_status"],
                                          "evidence": len(json.loads(r["evidence_ids"]))}

    @classmethod
    def latest(cls, conn) -> "Statuses":
        row = conn.execute("SELECT id FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
        return cls(conn, row["id"] if row else None)

    def measured(self, cid: str) -> str | None:
        """The current status, or None when no snapshot has measured this concept (now() assumes Stable)."""
        return self.rows[cid]["status"] if cid in self.rows else None

    def now(self, cid: str) -> str:
        return self.rows.get(cid, {}).get("status", "Stable")

    def get(self, cid: str, scenario: str) -> str:
        """Status projected to the Ghost CV horizon under the scenario (the current one if not projected)."""
        row = self.rows.get(cid)
        return row["projected"].get(scenario, row["status"]) if row else "Stable"


def mycol_codes(conn, as_of: str) -> dict[str, str]:
    """MASCO code -> latest MyCOL edition published by the snapshot date that lists it as critical."""
    out = {}
    for r in conn.execute("SELECT json_extract(metrics, '$.masco_code') code, json_extract(metrics, '$.edition') ed "
                          "FROM raw_doc WHERE kind = 'critical_occupation' AND published_at <= ? ORDER BY published_at",
                          (f"{as_of}T00:00:00Z",)):
        out[r["code"]] = r["ed"]
    return out


def _label(cur: Curated, cid: str) -> str:
    return cur.concepts[cid].label if cid in cur.concepts else cid


def _sdgs(cur: Curated, kind: str, eid: str) -> list[dict]:
    return [{"sdg": t.sdg, "name": SDG_NAMES[t.sdg], "target": t.target, "rationale": t.rationale}
            for t in cur.sdg_tags.get((kind, eid), [])]


# ---------- The Mirror ----------


HORIZONS = ("now", "moderate", "fast")


def mirror(cur: Curated, st: Statuses, p: Profile) -> dict:
    tasks = cur.tasks.get(p.occupation or "", [])
    cards = []
    for t in tasks:
        caps = []
        for rule in cur.task_rules:
            if task_matches(rule.pattern, t.label) and rule.capability_id not in [c["id"] for c in caps]:
                status = st.get(rule.capability_id, p.scenario)
                caps.append({"id": rule.capability_id, "label": _label(cur, rule.capability_id), "status": status,
                             "status_now": st.now(rule.capability_id), "score": EXPOSURE.get(status, 0.4),
                             "rationale": rule.rationale})
        score = max((c["score"] for c in caps), default=0.0)
        # when AI can take the task: today, by the projection horizon under moderate progress, or only if it's fast
        by = {h: max((EXPOSURE.get(st.now(c["id"]) if h == "now" else st.get(c["id"], h), 0.4) for c in caps),
                     default=0.0) for h in HORIZONS}
        when = next((h for h in HORIZONS if by[h] >= exposed_at(h)), "never")
        auto = "exposed" if score >= exposed_at(p.scenario) else "human"
        override = p.overrides.get(t.uri)
        pile = override["pile"] if override and override.get("pile") in ("exposed", "human") else auto
        top = max(caps, key=lambda c: c["score"]) if caps else None
        if top and auto == "exposed":
            reason = f"{top['label']} can do this: {top['rationale'].lower()}."
        elif top:
            reason = f"{top['label']} is {top['status']} under this scenario, not yet enough to take this over."
        else:
            reason = "No AI capability Kompas tracks does this task."
        cards.append({"id": t.uri, "task": t.label, "pile": pile, "auto_pile": auto, "score": round(score, 2),
                      "when": when, "scores": {h: round(v, 2) for h, v in by.items()},
                      "capabilities": caps, "reason": reason,
                      "override": override if override and pile != auto else None})
    exposed = [c for c in cards if c["pile"] == "exposed"]

    def share(h: str) -> int:
        """Exposed share at a horizon; the user's own moves count at every horizon."""
        hit = sum((c["override"]["pile"] if c["override"] else ("exposed" if c["scores"][h] >= exposed_at(h) else "human"))
                  == "exposed" for c in cards)
        return round(100 * hit / len(cards)) if cards else 0
    return {
        "occupation": p.occupation, "title": cur.role_titles.get(p.occupation or ""),
        "esco_occupation": tasks[0].occupation if tasks else None,
        "esco_uri": tasks[0].occupation_uri if tasks else None,
        "cards": cards, "exposed_share": round(100 * len(exposed) / len(cards)) if cards else 0,
        "shares": {h: share(h) for h in HORIZONS},
        # capabilities on the AI pile after the user's corrections: these drive the live feed's "affects your work"
        "exposed_capabilities": sorted({c["id"] for card in exposed for c in card["capabilities"]}),
    }


# ---------- matching and bets ----------


def role_skills(cur: Curated, isco: str) -> list[tuple[str, float]]:
    """(skill, importance) pairs the role needs, from concept_occupation.csv."""
    return [(cid, w) for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "skill"
            for i, w in occs if i == isco]


def exposure_share(cur: Curated, st: Statuses, isco: str, scenario: str, overrides: dict) -> int | None:
    """Share of an occupation's ESCO tasks on the AI-exposed pile (the user's Mirror corrections apply)."""
    tasks = cur.tasks.get(isco, [])
    if not tasks:
        return None
    exposed = 0
    for t in tasks:
        score = max((EXPOSURE.get(st.get(r.capability_id, scenario), 0.4) for r in cur.task_rules
                     if task_matches(r.pattern, t.label)), default=0.0)
        pile = "exposed" if score >= exposed_at(scenario) else "human"
        o = overrides.get(t.uri)
        if o and o.get("pile") in ("exposed", "human"):
            pile = o["pile"]
        exposed += pile == "exposed"
    return round(100 * exposed / len(tasks))


def demand_index(st: Statuses, skills: list[tuple[str, float]], scenario: str) -> float:
    total = sum(i for _, i in skills)
    return sum(i * DEMAND.get(st.get(cid, scenario), 1.0) for cid, i in skills) / total if total else 1.0


def score_roles(cur: Curated, st: Statuses, p: Profile, mycol: dict[str, str]) -> list[dict]:
    have = dict(p.skills)
    for s in p.completed:
        have.setdefault(s, "claimed")
    masco = {isco: code for (system, code), isco in cur.occupation_codes.items() if system == "MASCO"}
    roles = []
    for isco, title in cur.role_titles.items():
        skills = role_skills(cur, isco)
        if len(skills) < 2:
            continue
        rows, total, got = [], 0.0, 0.0
        for cid, importance in sorted(skills, key=lambda x: (-x[1], x[0])):
            status = st.get(cid, p.scenario)
            weight = importance * DEMAND.get(status, 1.0)
            cov = COVERAGE.get(have.get(cid, ""), 0.0)
            total, got = total + weight, got + weight * cov
            rows.append({"id": cid, "label": _label(cur, cid), "importance": importance, "status": status,
                         "measured": cid in st.rows, "weight": round(weight, 3), "coverage": cov,
                         "evidence": have.get(cid)})
        match = round(100 * got / total) if total else 0
        imp_total = sum(i for _, i in skills)
        demand = sum(r["importance"] * DEMAND.get(r["status"], 1.0) for r in rows) / imp_total
        critical = mycol.get(masco.get(isco, ""))
        if critical:
            demand *= 1.1
        essential = [r for r in rows if r["importance"] == 1.0]
        holds = sum(r["importance"] for r in essential
                    if all(st.get(r["id"], s) not in ("Declining", "Stalled") for s in SCENARIOS))
        safe_share = holds / sum(r["importance"] for r in essential) if essential else 0.0
        families = [(w, cid) for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "family"
                    for i, w in occs if i == isco]
        family = max(families)[1] if families else None
        tags = _sdgs(cur, "role", isco)
        role_goals = {t["sdg"] for t in tags}
        alignment = len(role_goals & set(p.sdgs)) / len(p.sdgs) if p.sdgs else 0.0
        roles.append({
            "isco": isco, "title": title, "occupation": cur.occupation_titles[isco], "match": match,
            "breakdown": rows, "have": [r for r in rows if r["coverage"]], "gaps": [r for r in rows if not r["coverage"]],
            "demand": round(demand, 3), "mycol": critical, "safe_share": round(safe_share, 2),
            "sdgs": tags, "alignment": round(alignment, 2), "covered": not any(not r["coverage"] for r in rows),
            "family": {"id": family, "label": _label(cur, family)} if family else None,
            "family_status": st.measured(family) if family else None,
            "ai_exposure": exposure_share(cur, st, isco, p.scenario, p.overrides),
            "scores": {"safe": match if safe_share >= SAFE_SHARE else None,
                       "rising": round(demand * match, 1) if match >= MIN_MATCH else None,
                       "impact": round(alignment * match, 1) if match >= MIN_MATCH and alignment > 0 else None},
        })
    # equal matches: the role with more of your skills behind it first (70% from 4 skills beats 70% from 1)
    return sorted(roles, key=lambda r: (-r["match"], -len(r["have"]), r["isco"]))


def pick_bets(roles: list[dict], current: str | None = None) -> dict[str, dict | None]:
    """PRD FR-4.3. Bets are where to go next, so the current occupation and roles with nothing left to learn are
    left out. If one role wins two categories, the later category takes its next best. A category nobody
    qualifies for comes back as {"role": None, "closest": ...}: the best role below the threshold."""
    candidates = [r for r in roles if r["gaps"] and r["isco"] != current]
    taken, out = set(), {}
    for kind in ("safe", "rising", "impact"):
        ranked = sorted((r for r in candidates if r["scores"][kind] is not None and r["isco"] not in taken),
                        key=lambda r: (-r["scores"][kind], -r["match"], r["isco"]))
        if ranked:
            out[kind] = ranked[0]
            taken.add(ranked[0]["isco"])
        else:
            closest = next((r for r in candidates if r["isco"] not in taken and (kind != "impact" or r["alignment"] > 0)), None)
            if closest:     # each empty category points at a different job
                taken.add(closest["isco"])
            out[kind] = {"role": None, "closest": closest and {"isco": closest["isco"], "title": closest["title"],
                                                               "match": closest["match"]}}
    return out


def is_bet(b: dict | None) -> bool:
    return bool(b) and "isco" in b


# ---------- Ghost CV ----------


RISING = ("Emerging", "Act now")
FADING = ("Declining", "Stalled")
_RANK = {"Act now": 0, "Emerging": 1}


def family_of(cur: Curated, cid: str) -> str | None:
    """The nearest job family above a skill (Power BI -> Data and analytics)."""
    return next((a for a in cur.ancestors(cid) if a in cur.concepts and cur.concepts[a].kind == "family"), None)


def ghost(cur: Curated, st: Statuses, p: Profile, roles: list[dict]) -> dict:
    """Your CV at the projection horizon: each skill you have is worth more, holds its value, fades, or is work AI takes
    over under the scenario (as in The Mirror); blank slots are
    rising skills you don't have yet, from the closest roles you could grow into, then your skills' families, then the
    whole market. Every slot says why it's there."""
    done = set(p.completed)
    # skills whose work AI takes over under this scenario: the same rule as The Mirror, through capability_skill.csv
    reach: dict[str, list[dict]] = {}
    for cap, links in cur.capability_skills.items():
        if EXPOSURE.get(st.get(cap, p.scenario), 0.4) >= exposed_at(p.scenario):
            for skill, why in links:
                reach.setdefault(skill, []).append({"id": cap, "label": _label(cur, cap), "why": why})
    lines = []
    for cid, evidence in sorted(p.skills.items(), key=lambda x: _label(cur, x[0])):
        if cid not in cur.concepts:
            continue
        status = st.get(cid, p.scenario)
        trend = "up" if status in RISING else "fade" if status in FADING else "ai" if cid in reach else "hold"
        lines.append({"id": cid, "label": _label(cur, cid), "status": status, "status_now": st.now(cid),
                      "evidence": evidence, "state": "faded" if status in FADING else "solid",
                      "trend": trend, "ai": reach.get(cid, [])})
    slots, seen = [], set(p.skills)

    def add(cid: str, why: str, for_role: str | None = None):
        status = st.get(cid, p.scenario)
        if cid in seen or len(slots) >= GHOST_SLOTS or status not in RISING:
            return
        seen.add(cid)
        slots.append({"id": cid, "label": _label(cur, cid), "status": status, "status_now": st.now(cid),
                      "for_role": for_role, "why": why, "state": "filled" if cid in done else "blank"})

    for role in [r for r in roles if r["gaps"]][:5]:
        for g in sorted(role["gaps"], key=lambda g: -g["weight"]):
            add(g["id"], f"Needed for {role['title']}", role["title"])
    rising = sorted((cid for cid, c in cur.concepts.items() if c.kind == "skill"),
                    key=lambda cid: (_RANK.get(st.get(cid, p.scenario), 9), -st.rows.get(cid, {}).get("evidence", 0), cid))
    # a family counts as yours when at least two of your skills are in it (one stray skill isn't a direction)
    owned = Counter(family_of(cur, cid) for cid in p.skills if cid in cur.concepts)
    families = {f for f, n in owned.items() if f and n >= 2}
    for cid in rising:
        fam = family_of(cur, cid)
        if fam in families:
            add(cid, f"Rising in {_label(cur, fam).lower()}")
    # market-wide picks are least personal: at most two, after everything closer to you
    cap = len(slots) + 2
    for cid in rising:
        if len(slots) >= cap:
            break
        add(cid, "Rising across the market")
    return {"lines": lines, "slots": slots, "horizon": "2028",
            "filled": sum(s["state"] == "filled" for s in slots)}


# ---------- The Route ----------


def route(cur: Curated, st: Statuses, p: Profile, role: dict | None) -> dict | None:
    if role is None:
        return None
    have = set(p.skills)
    weight = {g["id"]: g["weight"] for g in role["gaps"]}
    needed: list[str] = []

    def add(cid: str, trail: tuple = ()):
        if cid in have or cid in needed or cid in trail:
            return
        for req in cur.prereqs.get(cid, []):
            add(req, trail + (cid,))
        needed.append(cid)

    for g in sorted(role["gaps"], key=lambda g: (PRIORITY.get(g["status"], 3), -g["weight"], g["id"])):
        add(g["id"])
    # prerequisites stay before the skills that need them; otherwise ladder priority, then weight
    order: list[str] = []
    remaining = list(needed)
    while remaining:
        ready = [c for c in remaining if all(r in order or r in have or r not in needed for r in cur.prereqs.get(c, []))]
        ready = ready or remaining   # a prerequisite cycle in the curated table: don't loop forever
        nxt = min(ready, key=lambda c: (PRIORITY.get(st.get(c, p.scenario), 3), -weight.get(c, 0), c))
        order.append(nxt)
        remaining.remove(nxt)
    steps = []
    for i, cid in enumerate(order, start=1):
        options = sorted(cur.resources.get(cid, []), key=lambda r: (["free", "free-to-audit", "low-cost", "paid"].index(r.cost), r.hours))
        res = options[0] if options else None
        status = st.get(cid, p.scenario)
        steps.append({
            "order": i, "id": cid, "label": _label(cur, cid), "status": status, "status_now": st.now(cid),
            "prerequisite_for": [c for c in order if cid in cur.prereqs.get(c, [])],
            "why": (f"{_label(cur, cid)} is {status} on the Signal Ladder under this scenario"
                    + (f" and needed for {role['title']}." if cid in weight else ", and later steps build on it.")),
            "evidence_count": st.rows.get(cid, {}).get("evidence", 0),
            "resource": None if res is None else {"title": res.title, "provider": res.provider, "url": res.url,
                                                  "hours": res.hours, "cost": res.cost, "language": res.language,
                                                  "hrdc_verified": res.hrdc_verified, "checked": res.checked},
            "alternatives": len(options) - 1 if options else 0,
            "sdgs": _sdgs(cur, "skill", cid), "completed": cid in p.completed,
        })
    hours = sum(s["resource"]["hours"] for s in steps if s["resource"])
    left = sum(s["resource"]["hours"] for s in steps if s["resource"] and not s["completed"])
    contribution: dict[int, dict] = {}
    for s in steps:
        for t in s["sdgs"]:
            c = contribution.setdefault(t["sdg"], {"sdg": t["sdg"], "name": t["name"], "steps": []})
            c["steps"].append(s["label"])
    return {"role": {"isco": role["isco"], "title": role["title"], "match": role["match"]}, "steps": steps,
            "hours": hours, "hours_left": left, "weeks": round(left / p.pace, 1) if p.pace > 0 else None,
            "pace": p.pace, "done": sum(s["completed"] for s in steps),
            "sdg_contribution": sorted(contribution.values(), key=lambda c: c["sdg"])}


# ---------- market evidence and reasons (the CV flow and Your direction) ----------


RUNG_NAMES = {"1": "Talk: research, GitHub, Hacker News", "2": "Hiring abroad", "3": "Hiring in Malaysia"}
# DOSM's major occupation groups in everyday words, for "based on all professional and technician job ads"
GROUP_WORDS = {"1": "manager", "2": "professional", "3": "technician", "4": "clerical", "5": "service and sales",
               "6": "farming and fishing", "7": "trades", "8": "machine operator", "9": "elementary"}


def _share_movement(change_pct: int | None) -> str:
    """The Malaysian rung measured for a skill's whole occupation groups, in words. It follows the groups' share of
    all job openings against the previous quarter (relative change), the figures the Malaysian job market panel
    shows: a bigger share is higher demand relative to the rest of the market, even when the whole market shrinks.
    It never moves the status, so it is "up"/"down", never "rising fast"/"falling"."""
    if change_pct is None:
        return "no data"
    return ("up" if change_pct >= 5 else "slightly up" if change_pct >= 1 else "down" if change_pct <= -5
            else "slightly down" if change_pct <= -1 else "flat")


def _movement(rung: dict | None) -> str:
    """A rung's trend (a z-score against earlier months) in words. Only a rung strong enough to count on the ladder
    is "rising fast" or "falling"; smaller moves are "slightly", so the words never contradict the skill's status."""
    if not rung or rung.get("trend") is None:
        return "no data"
    if rung.get("active"):
        return "rising fast"
    if rung.get("declining"):
        return "falling"
    return "slightly up" if rung["trend"] >= 0.5 else "slightly down" if rung["trend"] <= -0.5 else "flat"


# a status in words people use
PLAIN = {"Act now": "in demand in Malaysia right now", "Emerging": "growing abroad, not yet in Malaysia",
         "Watch": "talked about, with no hiring behind it yet", "Stable": "steady", "Declining": "falling",
         "Stalled": "stalled after a burst of hype"}


def _title(e, skill: str) -> str:
    """Hiring posts are one long "Company | Role | Place | ..." line: keep the company and the role."""
    title = e["title"] or ""
    if e["kind"] == "hiring_post":
        parts = [p.strip() for p in title.split("|") if p.strip() and not p.strip().lower().startswith(("location", "http"))]
        title = " · ".join(parts[:2]) or f"A job post mentioning {skill}"
    return title if len(title) <= 90 else title[:89] + "…"


def malaysia_ads(conn, as_of: str):
    """A function giving, for a set of DOSM major groups, their online job ads in the latest published quarter
    against the quarter before: count, change, and share of all ads. None when two quarters aren't available."""
    import json

    from .periods import cutoff

    ads: dict[str, dict[str, int]] = {}
    urls: dict[str, str] = {}
    for r in conn.execute("SELECT period, metrics, url FROM raw_doc WHERE source = 'dosm_jmi' "
                          "AND kind = 'occupation_group_stat' AND published_at <= ?", (cutoff(as_of),)):
        ads.setdefault(r["period"], {})[json.loads(r["metrics"])["masco_major_group"]] = \
            int(json.loads(r["metrics"])["offerings"])
        urls[r["period"]] = r["url"]

    def figures(groups: list[str]) -> dict | None:
        usable = [p for p in sorted(ads) if ads[p].get("TOTAL") and all(g in ads[p] for g in groups)]
        if len(usable) < 2 or not groups:
            return None
        now, before = usable[-1], usable[-2]
        n, m = sum(ads[now][g] for g in groups), sum(ads[before][g] for g in groups)
        share, prev_share = n / ads[now]["TOTAL"], m / ads[before]["TOTAL"]
        return {"quarter": now, "previous": before, "ads": n, "previous_ads": m,
                "change_pct": round(100 * (n / m - 1)) if m else None,
                "share_change_pct": round(100 * (share / prev_share - 1)) if prev_share else None,
                "share_pct": round(100 * n / ads[now]["TOTAL"], 1),
                "previous_share_pct": round(100 * m / ads[before]["TOTAL"], 1),
                "groups": [GROUP_WORDS[g] for g in groups if g in GROUP_WORDS],
                "url": urls[now], "source": "DOSM Job Market Insights"}
    return figures


def malaysia_market(conn, as_of: str | None, groups: list[str]) -> dict | None:
    """The Malaysian job market for the given major groups, shown once above the skill cards (many skills share
    a group, so per-card figures would repeat): each group's job ads and change on the previous quarter, and all
    ads together. None without two published quarters."""
    if not as_of or not groups:
        return None
    figures = malaysia_ads(conn, as_of)
    total = figures(["TOTAL"])
    if not total:
        return None
    rows = [f for f in (figures([g]) for g in sorted(groups)) if f and f["quarter"] == total["quarter"]]
    return {"quarter": total["quarter"], "previous": total["previous"], "url": total["url"],
            "all": {"ads": total["ads"], "change_pct": total["change_pct"]},
            "groups": [{"group": f["groups"][0], "ads": f["ads"], "change_pct": f["change_pct"],
                        "share_pct": f["share_pct"], "previous_share_pct": f["previous_share_pct"],
                        # the same words as the skill cards' "Hired in Malaysia" row, from the same share figures
                        "movement": _share_movement(f["share_change_pct"])} for f in rows]}


def skill_signals(cur: Curated, conn, st, ids: set[str]) -> dict[str, dict]:
    """The market evidence behind each skill's status: what each rung of the Signal Ladder is doing and the
    strongest items it rests on (hiring posts first, then the highest-scoring stories and repo counts)."""
    if not st.id or not ids:
        return {}
    import json

    q = ",".join("?" * len(ids))
    ev_ids = {r["concept_id"]: json.loads(r["evidence_ids"]) for r in conn.execute(
        f"SELECT concept_id, evidence_ids FROM concept_status WHERE snapshot_id = ? AND concept_id IN ({q})",
        (st.id, *ids))}
    wanted = sorted({e for v in ev_ids.values() for e in v})
    items = {}
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        for r in conn.execute(f"SELECT * FROM evidence WHERE snapshot_id = ? AND id IN ({','.join('?' * len(chunk))})",
                              (st.id, *chunk)):
            items[r["id"]] = r
    malaysia = malaysia_ads(conn, st.as_of)

    def rung(k: str, r: dict | None) -> dict:
        r = r or {}
        out = {"rung": int(k), "name": RUNG_NAMES[k], "movement": _movement(r),
               "sources": [cur.sources[s].name for s in r.get("sources", []) if s in cur.sources], "groups": []}
        if r.get("level") == "group":
            # the DOSM occupation groups it is measured for, and their share of all openings vs the previous quarter
            fig = malaysia(r.get("groups") or [])
            out.update(groups=[GROUP_WORDS[g] for g in r.get("groups") or [] if g in GROUP_WORDS],
                       movement=_share_movement(fig["share_change_pct"] if fig else None),
                       share_pct=fig["share_pct"] if fig else None,
                       previous_share_pct=fig["previous_share_pct"] if fig else None,
                       previous=fig["previous"] if fig else None)
        return out

    out = {}
    for cid in ids:
        row = st.rows.get(cid)
        if not row:
            continue
        # a major group's job ads describe a whole group of jobs, not the skill: they're shown once, in the
        # Malaysian job market panel (malaysia_market), never as a skill's evidence
        evidence = sorted((items[e] for e in ev_ids.get(cid, []) if e in items and items[e]["kind"] != "occupation_group_stat"),
                          key=lambda e: (-cur.sources[e["source"]].rung if e["source"] in cur.sources else 0,
                                         -(e["value"] or 0)))
        out[cid] = {
            "status": row["status"], "projected": row["projected"],
            "rungs": [rung(k, row["rungs"].get(k)) for k in ("1", "2", "3")],
            "meaning": explain.MEANING.get(row["status"]),
            "evidence": [{"title": _title(e, cur.concepts[cid].label), "url": e["url"], "date": e["published_at"][:10],
                          "source": cur.sources[e["source"]].name if e["source"] in cur.sources else e["source"],
                          "value": e["value"], "value_label": e["value_label"]} for e in evidence[:3]],
            "evidence_count": len(evidence),
        }
    return out


def recommend(roles: list[dict]) -> dict | None:
    """The role to pursue: highest demand x match among roles you fit at least 40% (the Rising Bet rule), else
    the closest fit."""
    fit = [r for r in roles if r["match"] >= MIN_MATCH]
    return max(fit, key=lambda r: (r["demand"] * r["match"], r["match"])) if fit else (roles[0] if roles else None)


def reasons(role: dict, skills: dict[str, dict], sig: dict[str, dict]) -> list[dict]:
    """Why this role, as fixed templates over computed values. Each reason carries its evidence: CV quotes,
    Signal Ladder items, MyCOL, the SDG rationale."""
    out = []
    have, gaps = role["have"], role["gaps"]
    quotes: dict[str, list[str]] = {}       # one CV line can show several skills
    for h in have:
        if h["id"] in skills:
            quotes.setdefault(skills[h["id"]]["quote"], []).append(h["label"])
    out.append({"kind": "fit", "title": f"Fits your profile: you have {len(have)} of its {len(role['breakdown'])} skills",
                "text": ", ".join(h["label"] for h in have) + ".",
                "evidence": [{"type": "quote", "label": ", ".join(labels), "text": q} for q, labels in quotes.items()]})
    fam, fstat = role.get("family"), role.get("family_status")
    demand_ev = []
    if role.get("mycol"):
        demand_ev.append({"type": "source", "label": "MyCOL", "text": f"Malaysia's Critical Occupations List, {role['mycol']}"})
    if fam and fstat:
        text = f"Demand for {fam['label'].lower()} jobs is {PLAIN.get(fstat, fstat.lower())}. {explain.MEANING.get(fstat, '')}"
        if fam["id"] in sig:
            demand_ev += [{"type": "signal", **e} for e in sig[fam["id"]]["evidence"][:2]]
    else:
        text = "We don't have hiring data for this kind of job yet, so demand isn't scored."
    if role.get("mycol"):
        text += f" It is on Malaysia's Critical Occupations List ({role['mycol']})."
    out.append({"kind": "demand", "title": "Demand", "text": text.strip(), "evidence": demand_ev})
    rising = [r for r in role["breakdown"] if r["status"] in RISING
              or (sig.get(r["id"], {}).get("projected") or {}).get("moderate") in RISING]
    if rising:
        parts = []
        for r in rising:
            proj = (sig.get(r["id"], {}).get("projected") or {}).get("moderate")
            now = sig.get(r["id"], {}).get("status", r["status"])
            parts.append(f"{r['label']} is {PLAIN.get(now, now.lower())}"
                         + (f", and likely to be {PLAIN.get(proj, proj.lower()).removesuffix(' right now')} by 2028 if AI keeps its current pace"
                            if proj and proj != now else ""))
        out.append({"kind": "trend", "title": "Trending skills in this role", "text": "; ".join(parts) + ".",
                    "evidence": [{"type": "signal", "skill": r["label"], **e} for r in rising
                                 for e in sig.get(r["id"], {}).get("evidence", [])[:2]]})
    else:
        out.append({"kind": "trend", "title": "Trending skills in this role",
                    "text": "None of its skills is trending right now: demand is steady, not rising.", "evidence": []})
    if role.get("ai_exposure") is not None:
        out.append({"kind": "ai", "title": "AI and this job",
                    "text": f"AI can already do about {role['ai_exposure']}% of the everyday tasks in this job. The rest needs a person.",
                    "evidence": []})
    if role.get("sdgs"):
        t = role["sdgs"][0]
        out.append({"kind": "sdg", "title": f"SDG {t['sdg']}: {t['name']}", "text": t.get("rationale") or "",
                    "evidence": []})
    out.append({"kind": "gap", "title": "What to learn",
                "text": (f"{len(gaps)} skill{'s' if len(gaps) != 1 else ''} to add: {', '.join(g['label'] for g in gaps)}. "
                         "Your route is on The Route step.") if gaps else
                        "Nothing missing among the skills Kompas tracks. CV skills count 70% until you show them in practice.",
                "evidence": []})
    return out


def direction(m: dict) -> dict:
    """Whether to lead with staying or switching, from the share of tasks AI can do by the horizon (The Mirror's
    verdict): under 25% stay, 50% and over switch, in between both are open."""
    share = m["shares"]["moderate"] if m.get("shares") else m["exposed_share"]
    level = "high" if share >= 50 else "medium" if share >= 25 else "low"
    return {"level": level, "lead": {"low": "stay", "medium": "either", "high": "switch"}[level]}


def stay_option(cur: Curated, p: Profile, m: dict, g: dict, current: dict | None, sig: dict) -> dict | None:
    """Staying in the current job, as an option beside the switches: how much of it AI can do, its demand, and the
    rising skills that strengthen it."""
    if not p.occupation:
        return None
    sh = m.get("shares") or {"now": m["exposed_share"], "moderate": m["exposed_share"], "fast": m["exposed_share"]}
    out = [{"kind": "ai", "title": "AI and your job",
            "text": f"AI can do about {sh['now']}% of its tasks today and {sh['moderate']}% by 2028; "
                    f"{sh['fast']}% if AI moves fast.", "evidence": []}]
    if current:
        out += [x for x in reasons(current, {}, sig) if x["kind"] in ("demand", "trend")]
    add = [s for s in g["slots"] if s["state"] == "blank"][:3]
    gaps = [x["id"] for x in (current or {}).get("gaps", [])][:3]
    learn_ids = list(dict.fromkeys(gaps + [s["id"] for s in add]))[:4]
    learn = [_label(cur, cid) for cid in learn_ids]
    out.append({"kind": "gap", "title": "To strengthen it",
                "text": f"Add {', '.join(learn)}." if learn else "Keep your skills current: nothing rising is missing.",
                "evidence": []})
    return {"isco": p.occupation, "title": cur.role_titles.get(p.occupation, p.occupation),
            "match": current["match"] if current else None, "family": current.get("family") if current else None,
            "family_status": current.get("family_status") if current else None, "shares": sh,
            "learn": learn, "learn_ids": learn_ids, "reasons": out}


# ---------- the whole journey ----------


def build(cur: Curated, conn, snapshot_id: str, p: Profile) -> dict:
    st = Statuses(conn, snapshot_id)
    mycol = mycol_codes(conn, st.as_of)
    roles = score_roles(cur, st, p, mycol)
    bets = pick_bets(roles, p.occupation)
    first_bet = next((b for b in bets.values() if is_bet(b)), None)
    chosen = next((r for r in roles if r["isco"] == p.role), None) or first_bet or (roles[0] if roles else None)
    history = [Statuses(conn, row["id"]) for row in conn.execute(
        "SELECT id FROM snapshot WHERE as_of <= ? ORDER BY as_of DESC LIMIT 6", (st.as_of,)).fetchall()[::-1]]
    m, r = mirror(cur, st, p), route(cur, st, p, chosen)
    g = ghost(cur, st, p, roles)
    current = next((x for x in roles if x["isco"] == p.occupation), None)
    # an empty category shows its closest job instead, so that job needs its reasons too
    closest = [x for b in bets.values() if not is_bet(b) and b.get("closest")
               for x in roles if x["isco"] == b["closest"]["isco"]]
    options = [b for b in bets.values() if is_bet(b)] + closest + ([current] if current else [])
    sig = skill_signals(cur, conn, st, {s["id"] for o in options for s in o["breakdown"]}
                        | {o["family"]["id"] for o in options if o.get("family")})
    for o in options:
        if o is not current:
            o["reasons"] = reasons(o, {}, sig)
        # every option card carries its route and its demand over the last six snapshots (the sparkline)
        trend = [round(demand_index(h, role_skills(cur, o["isco"]), p.scenario), 3) for h in history]
        o["trend"] = trend
        o["growth"] = round(100 * (trend[-1] / trend[0] - 1)) if trend and trend[0] else 0
        o["trend_from"] = history[0].as_of if history else None
        o["route"] = route(cur, st, p, o)
    stay = stay_option(cur, p, m, g, current, sig)
    if current and stay:
        # staying means adding the skills that strengthen the job: that is its route
        strengthen = {**current, "gaps": [{"id": cid, "label": _label(cur, cid), "weight": 0.5,
                                           "status": st.get(cid, p.scenario)} for cid in stay["learn_ids"]]}
        current["route"] = route(cur, st, p, strengthen)
        if chosen is current:
            r = current["route"]
    return {
        "snapshot": {"id": st.id, "as_of": st.as_of}, "scenario": p.scenario, "sdgs": p.sdgs,
        "mirror": m, "ghost": g, "bets": bets, "roles": roles, "route": r,
        "stay": stay, "direction": direction(m),
        # what the live feed (/match) needs to follow this journey
        "feed_profile": {"skills": [{"id": s, "evidence": e} for s, e in p.skills.items() if s in cur.concepts],
                         "route": [s["id"] for s in (r or {"steps": []})["steps"]],
                         "exposed": m["exposed_capabilities"]},
    }


def ping(cur: Curated, conn, before_id: str, after_id: str, p: Profile) -> dict:
    """The change brief between two snapshots for one profile (PRD 5.7, FR-8.2)."""
    import json

    a, b = build(cur, conn, before_id, p), build(cur, conn, after_id, p)
    sa, sb = Statuses(conn, before_id), Statuses(conn, after_id)
    relevant = set(p.skills) | {s["id"] for s in (b["route"] or {"steps": []})["steps"]} \
        | {s["id"] for s in (a["route"] or {"steps": []})["steps"]} | set(b["mirror"]["exposed_capabilities"]) \
        | {s["id"] for s in b["ghost"]["slots"] + a["ghost"]["slots"]}
    rungs = {}
    for snap, sid in (("a", before_id), ("b", after_id)):
        rungs[snap] = {r["concept_id"]: json.loads(r["rungs"]) for r in
                       conn.execute("SELECT concept_id, rungs FROM concept_status WHERE snapshot_id = ?", (sid,))}
    skills = []
    for cid in sorted(relevant):
        before, after = sa.get(cid, p.scenario), sb.get(cid, p.scenario)
        now_before, now_after = sa.now(cid), sb.now(cid)
        if (before, now_before) != (after, now_after):
            skills.append({"id": cid, "label": _label(cur, cid), "from": now_before, "to": now_after,
                           "projected_from": before, "projected_to": after,
                           "reason": _reason(rungs["a"].get(cid, {}), rungs["b"].get(cid, {}))})
    bets = []
    for kind in ("safe", "rising", "impact"):
        x, y = (j["bets"][kind] if is_bet(j["bets"][kind]) else None for j in (a, b))
        if (x or {}).get("isco") != (y or {}).get("isco") or (x and y and x["match"] != y["match"]):
            bets.append({"kind": kind, "from": x and {"title": x["title"], "match": x["match"]},
                         "to": y and {"title": y["title"], "match": y["match"]}})
    order = lambda j: [s["id"] for s in (j["route"] or {"steps": []})["steps"]]
    slots = lambda j: {s["id"] for s in j["ghost"]["slots"]}
    slot_label = {s["id"]: s["label"] for j in (a, b) for s in j["ghost"]["slots"]}
    return {
        "from": a["snapshot"], "to": b["snapshot"], "skills": skills, "bets": bets,
        "route": {"from": order(a), "to": order(b), "changed": order(a) != order(b),
                  "labels": {s["id"]: s["label"] for j in (a, b) for s in (j["route"] or {"steps": []})["steps"]}},
        "ghost": {"new_slots": [{"id": i, "label": slot_label[i]} for i in sorted(slots(b) - slots(a))],
                  "gone_slots": [{"id": i, "label": slot_label[i]} for i in sorted(slots(a) - slots(b))]},
        "mirror": {"from": a["mirror"]["exposed_share"], "to": b["mirror"]["exposed_share"]},
        "changed": bool(skills or bets or order(a) != order(b) or slots(a) != slots(b)),
        "journey": b,
    }
