"""CV upload -> skills profile (PRD 5.1 / FR-1). The file is read in memory and never stored (NFR-3).

The LLM labels the CV against Kompas's closed lists; every item must quote the CV verbatim or it is dropped
(FR-10.3). The dictionary tagger always runs too, as a safety net and as the fallback without an API key.
"""

import io
import re
import zipfile
from html import unescape

from . import llm
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


def _statuses(conn) -> dict[str, str]:
    row = conn.execute("SELECT id FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
    if not row:
        return {}
    return {r["concept_id"]: r["status"] for r in
            conn.execute("SELECT concept_id, status FROM concept_status WHERE snapshot_id = ?", (row["id"],))}



def analyse(text: str, cur: Curated, conn, client=None) -> dict:
    cv_norm = _norm(text)
    status = _statuses(conn)
    skills: dict[str, dict] = {}
    unrecognised, jobs, discarded = [], [], 0

    extraction, llm_error = llm.extract_cv(text, cur, client=client)
    if extraction:
        for s in extraction["skills"]:
            if not verbatim(s["quote"], cv_norm):
                discarded += 1
                continue
            if s["skill_id"] in cur.concepts:
                skills.setdefault(s["skill_id"], {"quote": s["quote"], "found_by": "llm"})
            else:
                unrecognised.append({"name": s["name"], "quote": s["quote"]})
        for j in extraction["jobs"]:
            if not verbatim(j["quote"], cv_norm):
                discarded += 1
                continue
            isco = j["occupation"] if j["occupation"] in cur.occupation_titles else None
            jobs.append({"title": j["title"], "employer": j["employer"], "period": j["period"], "quote": j["quote"],
                         "occupation": {"isco": isco, "title": cur.role_titles[isco]} if isco else None})

    # explicit tool and skill names the model may have skipped; the only extractor without an API key
    for cid, _method, _span, start in Tagger(cur).find_all(text):
        if cur.concepts[cid].kind != "family":
            skills.setdefault(cid, {"quote": _line_around(text, start), "found_by": "dictionary"})

    have = set(skills)
    exposed = []
    for cap, links in cur.capability_skills.items():
        hit = [(skill, why) for skill, why in links if skill in have]
        if hit:
            exposed.append({"id": cap, "label": cur.concepts[cap].label,
                            "because": [{"skill": cur.concepts[s].label, "why": why} for s, why in hit]})

    return {
        "method": "llm" if extraction else "dictionary",
        "model": llm.MODEL if extraction else None,
        "llm_note": llm_error,
        "summary": extraction["summary"] if extraction else None,
        "jobs": jobs,
        "skills": [{"id": cid, "label": cur.concepts[cid].label, "status": status.get(cid), **info}
                   for cid, info in skills.items()],
        "unrecognised": unrecognised,
        "discarded_unverified": discarded,
        "exposed": exposed,
        "roles": match_roles(cur, have, status),
    }


# PRD FR-4.2: a skill's weight is importance x demand; a CV skill is "claimed" (0.7), not yet demonstrated (1.0)
DEMAND = {"Act now": 1.2, "Emerging": 1.1, "Stable": 1.0, "Watch": 0.9, "Declining": 0.7, "Stalled": 0.7}
CLAIMED = 0.7


def match_roles(cur: Curated, have: set[str], status: dict[str, str], n: int = 4) -> list[dict]:
    """Roles ranked by Match(r) = sum(w*c) / sum(w). Roles the user already covers completely are left out:
    "best fit" means the next role, and a role with no gaps has nothing to learn."""
    roles = []
    for isco, title in cur.role_titles.items():
        skills = [(cid, w) for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "skill"
                  for i, w in occs if i == isco]
        if len(skills) < 2:
            continue
        weight = {cid: w * DEMAND.get(status.get(cid, "Stable"), 1.0) for cid, w in skills}
        total = sum(weight.values())
        matched = sum(weight[cid] * CLAIMED for cid in weight if cid in have)
        gaps = [cid for cid in sorted(weight, key=weight.get, reverse=True) if cid not in have]
        if not matched or not gaps:
            continue
        # the job family's own demand stands in for the role's (Malaysian demand is measured per occupation)
        families = [(w, cid) for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "family"
                    for i, w in occs if i == isco]
        family = max(families)[1] if families else None
        item = lambda cid: {"id": cid, "label": cur.concepts[cid].label, "status": status.get(cid)}
        roles.append({
            "isco": isco, "title": title, "occupation": cur.occupation_titles[isco],
            "match": round(100 * matched / total), "demand": status.get(family) if family else None,
            "have": [item(cid) for cid in weight if cid in have], "gaps": [item(cid) for cid in gaps],
        })
    return sorted(roles, key=lambda r: r["match"], reverse=True)[:n]
