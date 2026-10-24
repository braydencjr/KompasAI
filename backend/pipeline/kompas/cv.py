"""CV upload -> skills profile (PRD 5.1 / FR-1). The file is read in memory and never stored (NFR-3).

The LLM reads the CV against reference data, not a closed list: skills Kompas tracks keep their ids, any other
skill is resolved to ESCO (kompas/open_skills.py), and jobs map to any ISCO-08 occupation in the ILO's index, or
are scored against it when none fits (kompas/exposure.py). Every item must quote the CV verbatim or it is dropped
(FR-10.3). The dictionary tagger always runs too, as a safety net and as the fallback without an API key.
"""

import io
import re
import zipfile
from collections import Counter
from html import unescape

from . import exposure, journey, llm, narrate, open_skills, requirements
from .connectors import ilo
from .curated import Curated
from .tag import Tagger

MAX_BYTES = 5 * 1024 * 1024
MAX_CHARS = 60_000      # ~15 pages of text; longer isn't a CV
TEXT_TYPES = (".txt", ".md")


class UnsupportedFile(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        xml = re.sub(r"</w:p>|<w:br/>", "\n", xml).replace("<w:tab/>", "\t")
        return unescape(re.sub(r"<[^>]+>", "", xml))
    if name.endswith(TEXT_TYPES):
        return data.decode("utf-8", errors="replace")
    raise UnsupportedFile("Upload a PDF, DOCX, TXT or MD file.")


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("•", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def verbatim(quote: str, cv_norm: str) -> bool:
    q = _norm(quote)
    return len(q) >= 3 and q in cv_norm


def _line_around(text: str, start: int) -> str:
    """The CV line containing a dictionary match, used as its quote."""
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", start)
    line = text[a: b if b != -1 else len(text)].strip(" \t-•*")
    return line if len(line) <= 160 else line[max(0, start - a - 60): start - a + 100].strip()


RISING, FALLING = ("Act now", "Emerging"), ("Declining", "Stalled")
TOP_ROLES = 5
HEADER_WORDS = {"resume", "cv", "curriculum", "vitae", "profile", "synthetic", "sample"}


def _words(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[^\W\d_]{2,}", s)}


def checked_summary(summary: str | None, text: str, known: set[str]) -> str | None:
    """The model's summary, or None if it repeats a word from the CV's first line (almost always the name) that
    isn't a skill or job word. The prompt forbids names; this checks instead of trusting it (FR-10.3)."""
    if not summary:
        return None
    first = next((line for line in text.splitlines() if line.strip()), "")
    name = _words(first) - HEADER_WORDS - known
    return None if _words(summary) & name else summary


def _family(cur: Curated, cid: str) -> dict | None:
    """The nearest job family above a skill (Power BI -> Data and analytics)."""
    fam = next((a for a in cur.ancestors(cid) if a in cur.concepts and cur.concepts[a].kind == "family"), None)
    return {"id": fam, "label": cur.concepts[fam].label} if fam else None


def _sources(cur: Curated, conn) -> list[dict]:
    """Each trend source with the date of the newest record it delivered: what the statuses rest on."""
    latest = {r[0]: r[1] for r in conn.execute("SELECT source, MAX(published_at) FROM raw_doc GROUP BY source")}
    return [{"id": s.id, "name": s.name, "rung": s.rung, "data_as_of": (latest.get(s.id) or "")[:10] or None}
            for s in cur.sources.values()]


def insights(skills: list[dict], roles: list[dict], exposed: list[dict]) -> list[dict]:
    """Short findings for the top of the profile. Fixed templates over computed values (like explain.py), so
    every sentence traces back to a number on the page."""
    out = []
    families = Counter(s["family"]["label"] for s in skills if s["family"])
    if families:
        label, k = families.most_common(1)[0]
        out.append({"kind": "focus", "text": f"Your strongest area is {label.lower()}: {k} of your {len(skills)} skills."})
    rising = [s["label"] for s in skills if s["status"] in RISING]
    falling = [s["label"] for s in skills if s["status"] in FALLING]
    if rising:
        verb = "is" if len(rising) == 1 else "are"
        out.append({"kind": "rising", "text": f"{len(rising)} of your skills {verb} rising in demand: {', '.join(rising)}."})
    elif any(s["status"] for s in skills):
        out.append({"kind": "rising", "text": "None of your skills shows rising demand in this snapshot."})
    if falling:
        out.append({"kind": "falling", "text": f"Demand is falling for {', '.join(falling)}."})
    touched = sorted({b["skill"] for e in exposed for b in e["because"]})
    if touched:
        out.append({"kind": "ai", "text": f"AI is learning work tied to {len(touched)} of your skills: {', '.join(touched)}."})
    if roles:
        r = roles[0]
        out.append({"kind": "fit", "text": f"Closest fit: {r['title']} at {r['match']}%, "
                                           f"with {len(r['have'])} of its {len(r['breakdown'])} tracked skills."})
    return out


def score(found: dict[str, dict], cur: Curated, conn, st: "journey.Statuses") -> dict:
    """Everything about a CV that depends on the market data rather than the CV itself: each skill's status, the
    AI capabilities that reach it, the best-fit roles and the evidence. `found` maps concept id -> how the CV shows
    it ({"quote", "found_by"}). Run at upload, and again by rescore() when the data moves on."""
    have_ids = {cid for cid in found if cur.concepts[cid].kind == "skill"}
    profile = journey.Profile(skills={cid: "claimed" for cid in have_ids})
    task_links = journey.prepare(cur, conn, [st], profile)    # measures ESCO skills before they're read below

    def item(cid: str, info: dict) -> dict:
        row = st.rows.get(cid)
        return {"id": cid, "label": cur.concepts[cid].label, "status": st.measured(cid),
                "projected": row["projected"] if row else None, "evidence_count": row["evidence"] if row else 0,
                "family": _family(cur, cid), **info}

    skills = [item(cid, info) for cid, info in found.items() if cur.concepts[cid].kind == "skill"]
    # AI capabilities the CV names (document AI, anomaly detection): tools the person has used, not skills a role asks for
    ai_tools = [item(cid, info) for cid, info in found.items() if cur.concepts[cid].kind == "capability"]
    have = {s["id"] for s in skills}

    exposed = []
    for cap, links in cur.capability_skills.items():
        hit = [(skill, why) for skill, why in links if skill in have]
        if hit:
            exposed.append({"id": cap, "label": cur.concepts[cap].label, "status": st.measured(cap),
                            "because": [{"skill": cur.concepts[s].label, "why": why} for s, why in hit]})

    # the same scorer as the Three Bets, so a role's match is the same number on every step
    mycol = journey.mycol_codes(conn, st.as_of or "9999-12-31")
    scored = journey.score_roles(cur, st, profile, mycol, task_links)
    roles = [r for r in scored if r["match"] > 0][:TOP_ROLES]
    # market evidence for your skills, the shown roles' skills and their job families
    sig = journey.skill_signals(cur, conn, st, have | {b["id"] for r in roles for b in r["breakdown"]}
                  | {r["family"]["id"] for r in roles if r.get("family")})
    # where the data is silent, the LLM's estimate (flagged as one), so a skill isn't just "No data yet"
    journey.estimate_signals(conn, cur, sig, {s["id"]: s["label"] for s in skills})
    by_id = {s["id"]: s for s in skills}
    for r in roles:
        r["reasons"] = journey.reasons(r, by_id, sig)
    # the reasons rewritten from their evidence (postings, ILO scores, signals, your CV), checked; else templates
    narrate.apply(cur, conn, roles, {cid: s["quote"] for cid, s in by_id.items() if s.get("quote")}, sig, mode="sync")
    pick = journey.recommend(roles)
    return {
        "skills": skills, "ai_tools": ai_tools, "exposed": exposed, "roles": roles,
        "recommended": pick["isco"] if pick else None, "signals": sig,
        "insights": insights(skills, roles, exposed),
        "snapshot": {"id": st.id, "as_of": st.as_of} if st.id else None,
        "trace": {
            "signals": {"measured": sum(s["status"] is not None for s in skills), "of": len(skills),
                        "sources": _sources(cur, conn)},
            "roles": {"scored": len(scored), "catalogue": len(cur.role_titles), "shown": len(roles)},
        },
    }


def rescore(profile: dict, cur: Curated, conn) -> dict:
    """What the CV said, matched against the market: each skill's status, the AI that reaches it, the best-fit roles
    with their reasons, the evidence and the Malaysian job market. Step 2 of an upload (after read()), and how a
    profile saved in the browser stays current: the CV itself is never stored, so what it said (skills with their
    quotes, jobs, summary) is kept and everything else is recomputed against the latest snapshot."""
    open_skills.load_into(cur, conn)
    found = {s["id"]: {k: s[k] for k in ("quote", "found_by", "name", "group") if k in s}
             for s in [*profile.get("skills", []), *profile.get("ai_tools", [])]
             if isinstance(s, dict) and s.get("id") in cur.concepts}
    st = journey.Statuses.latest(conn)
    scored = score(found, cur, conn, st)
    have = {s["id"] for s in scored["skills"]}
    # the occupation groups behind your skills' "Hired in Malaysia" signal, for the one Malaysian job market panel
    groups = {g for cid in have for r3 in [(st.rows.get(cid) or {}).get("rungs", {}).get("3") or {}]
              if r3.get("level") == "group" for g in r3.get("groups") or []}
    trace = {**(profile.get("trace") or {}), **scored["trace"]}
    return {**profile, **{k: v for k, v in scored.items() if k != "trace"},
            "malaysia_market": journey.malaysia_market(conn, st.as_of, sorted(groups)), "trace": trace}


MAX_GROUPS = 6


def group_skills(skills: list[dict], unrecognised: list[dict]) -> list[dict]:
    """The CV's skills in the broad groups the reader put them in (a dictionary match without one goes under its
    job family), largest first: [{name, skills: [ids], untracked: [names]}]. For display only; matching uses the
    skills themselves."""
    groups: dict[str, dict] = {}
    names = {}       # one spelling per group, whatever case the reader used

    def group(name: str | None) -> dict:
        name = (name or "").strip() or "Other skills"
        key = name.lower()
        names.setdefault(key, name[0].upper() + name[1:])
        return groups.setdefault(key, {"name": names[key], "skills": [], "untracked": []})
    for s in skills:
        group(s.get("group") or (s["family"]["label"] if s.get("family") else None))["skills"].append(s["id"])
    for u in unrecognised:
        group(u.get("group"))["untracked"].append(u["name"])
    return sorted(groups.values(), key=lambda g: (-len(g["skills"]), -len(g["untracked"]), g["name"]))


def read(text: str, cur: Curated, conn, client=None) -> dict:
    """Step 1 of an upload: what the CV says. Its skills (Kompas's, or ESCO's for the rest), the AI tools it names,
    its jobs mapped to occupations, and a summary, each with a verbatim quote. Nothing about the market yet, so
    the skills can be shown while rescore() matches them."""
    cv_norm = _norm(text)
    idx = ilo.INDEX.load(conn)
    open_skills.load_into(cur, conn)
    found: dict[str, dict] = {}
    unrecognised, jobs, discarded = [], [], 0

    extraction, llm_error = llm.extract_cv(text, cur, {i: o.title for i, o in idx.occupations.items()
                                                       if o.origin == "ilo"}, client=client)
    if extraction:
        others = []
        for s in extraction["skills"]:
            if not verbatim(s["quote"], cv_norm):
                discarded += 1
                continue
            if s["skill_id"] in cur.concepts:
                found.setdefault(s["skill_id"], {"quote": s["quote"], "found_by": "llm", "name": s["name"],
                                                 "group": s.get("group")})
            else:
                others.append(s)
        # skills Kompas doesn't track: the ESCO skill that is the same skill, when there is one
        esco, why = open_skills.resolve(conn, cur, [s["name"] for s in others], "a CV", client=client) if others else ({}, None)
        llm_error = llm_error or why
        for s in others:
            if esco.get(s["name"]):
                found.setdefault(esco[s["name"]], {"quote": s["quote"], "found_by": "llm", "name": s["name"],
                                                   "group": s.get("group")})
            else:
                unrecognised.append({"name": s["name"], "quote": s["quote"], "group": s.get("group")})
        for j in extraction["jobs"]:
            if not verbatim(j["quote"], cv_norm):
                discarded += 1
                continue
            isco = j["occupation"] if j["occupation"] in idx.occupations or j["occupation"] in cur.role_titles else None
            if (isco is None or j.get("occupation_fit") == "loose") and j["title"].strip() and not jobs:
                # no ISCO-08 occupation describes the latest job (the one The Mirror reads): score its own tasks
                # against the ILO's most similar ones, starting from the nearest group (stored, so once per job)
                code, why = exposure.estimate(conn, j["title"], near=isco, client=client)
                isco = code or isco
                if why:
                    llm_error = llm_error or f"couldn't score '{j['title']}': {why}"
            jobs.append({"title": j["title"], "employer": j["employer"], "period": j["period"], "quote": j["quote"],
                         "occupation": {"isco": isco, "title": journey.occupation_title(cur, isco) or j["title"]}
                         if isco else None})

    # explicit tool and skill names the model may have skipped; the only extractor without an API key
    for cid, _method, _span, start in Tagger(cur).find_all(text):
        if cur.concepts[cid].kind != "family":
            found.setdefault(cid, {"quote": _line_around(text, start), "found_by": "dictionary"})

    # what Malaysian postings ask for in your own job, measured in the background for the journey that follows
    if jobs and jobs[0]["occupation"]:
        requirements.ensure_async(cur, jobs[0]["occupation"]["isco"])

    def item(cid: str) -> dict:
        return {"id": cid, "label": cur.concepts[cid].label, "family": _family(cur, cid), **found[cid]}
    skills = [item(cid) for cid in found if cur.concepts[cid].kind == "skill"]
    ai_tools = [item(cid) for cid in found if cur.concepts[cid].kind == "capability"]
    method = "llm" if extraction else "dictionary"
    groups = group_skills(skills, unrecognised)
    return {
        "method": method,
        "model": llm.MODEL if extraction else None,
        "llm_note": llm_error,
        "summary": checked_summary(extraction["summary"], text,
                                   _words(" ".join([*(s["label"] for s in skills), *(j["title"] for j in jobs)])))
                   if extraction else None,
        "jobs": jobs,
        "skills": skills,
        "ai_tools": ai_tools,
        "unrecognised": unrecognised,
        "groups": groups,
        "discarded_unverified": discarded,
        # what each stage did, with real counts, for "How Kompas read this"
        "trace": {
            "text": {"chars": len(text), "lines": sum(1 for line in text.splitlines() if line.strip())},
            "reader": {"method": method, "model": llm.MODEL if extraction else None, "note": llm_error},
            "skills": {"llm": sum(i["found_by"] == "llm" for i in found.values()),
                       "dictionary": sum(i["found_by"] == "dictionary" for i in found.values()),
                       "dropped_unverified": discarded, "unrecognised": len(unrecognised),
                       "ai_tools": len(ai_tools)},
            "jobs": {"found": len(jobs), "mapped": sum(1 for j in jobs if j["occupation"])},
        },
    }


def analyse(text: str, cur: Curated, conn, client=None) -> dict:
    """Both steps at once: read() then rescore()."""
    return rescore(read(text, cur, conn, client=client), cur, conn)
