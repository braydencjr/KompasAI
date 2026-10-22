"""Role skill links (concept_occupation.csv) drafted from ESCO, for review.

The match score is only as good as the list of skills each role needs. Hand-drafting that list left most roles
with two or three skills and many skills linked to no role. ESCO lists every occupation's essential and optional
skills, but in its own words ("utilise machine learning", "Python (computer programming)"), so turning them into
Kompas skill ids is a reading task: Gemini proposes each link citing one ESCO item, and this module checks it.

- The cited item must be one of the role's ESCO items (the schema allows nothing else; checked again here).
- The weight comes from ESCO, not the model: essential 1.0, optional 0.5.
- Nothing is applied: the draft goes to curated/concept_occupation.draft.csv for a person to review, then
  `kompas links-apply` merges the rows they kept.
"""

import csv
import re
from pathlib import Path

from . import config, llm
from .curated import Curated

WEIGHT = {"essential": 1.0, "optional": 0.5}
DRAFT_COLUMNS = ("concept_id", "isco_code", "weight", "status", "current_weight", "esco_items", "reason", "keep")


def esco_items(path: Path | None = None) -> dict[str, list[dict]]:
    """role ISCO -> its ESCO items, from occupation_skill_esco.csv (written by `kompas esco-skills`)."""
    path = path or config.CURATED_DIR / "occupation_skill_esco.csv"
    out: dict[str, list[dict]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["isco_code"] and not r["isco_code"].startswith("#"):
                out.setdefault(r["isco_code"], []).append(r)
    return out


def check(cur: Curated, isco: str, items: list[dict], proposed: list[dict]) -> tuple[list[dict], int]:
    """Keeps proposals that cite a real ESCO item of this role and name a Kompas skill. One row per skill, at the
    highest weight any cited item gives it. Returns (rows, number dropped)."""
    # a role citing two ESCO occupations can list the same item twice (essential in one, optional in the other)
    by_label: dict[str, list[dict]] = {}
    for i in items:
        by_label.setdefault(i["skill"], []).append(i)
    rows: dict[str, dict] = {}
    dropped = 0
    for p in proposed:
        cited = re.sub(r"\s*[\[(](essential|optional)[^\])]*[\])]\s*", "", p.get("esco_item", "")).strip()
        found = by_label.get(cited)
        cid = p.get("skill_id", "")
        if not found or cid not in cur.concepts or cur.concepts[cid].kind != "skill":
            dropped += 1
            continue
        row = rows.setdefault(cid, {"concept_id": cid, "isco_code": isco, "weight": 0.0, "cited": [], "reason": []})
        row["weight"] = max(row["weight"], *(WEIGHT[i["relation"]] for i in found))
        row["cited"] += [f"{i['skill']} ({i['relation']}, {i['esco_occupation']})" for i in found]
        row["reason"].append(p.get("reason", "").strip())
    return [{"concept_id": r["concept_id"], "isco_code": isco, "weight": r["weight"],
             "esco_items": "; ".join(dict.fromkeys(r["cited"])), "reason": " ".join(x for x in r["reason"] if x)}
            for r in rows.values()], dropped


def draft(cur: Curated, items_by_role: dict[str, list[dict]], client=None) -> dict:
    """Asks Gemini role by role. Returns {"rows", "dropped", "errors"}; a role whose call failed is reported, not
    guessed."""
    rows, dropped, errors = [], 0, {}
    for isco in sorted(items_by_role):
        if isco not in cur.role_titles:
            errors[isco] = "not in occupation_code_map.csv"
            continue
        items = items_by_role[isco]
        occupations = sorted({i["esco_occupation"] for i in items})
        proposed, error = llm.draft_role_links(cur.role_titles[isco], occupations, items, cur, client=client)
        if error:
            errors[isco] = error
            continue
        kept, n = check(cur, isco, items, proposed)
        rows += kept
        dropped += n
    return {"rows": compare(cur, rows), "dropped": dropped, "errors": errors}


def compare(cur: Curated, rows: list[dict]) -> list[dict]:
    """Marks each drafted link against today's file, and adds today's skill links ESCO doesn't support, so the
    reviewer sees every change in one place."""
    current = {(cid, isco): w for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "skill"
               for isco, w in occs}
    out = []
    for r in rows:
        before = current.get((r["concept_id"], r["isco_code"]))
        status = "new" if before is None else "same" if before == r["weight"] else "weight changed"
        out.append({**r, "status": status, "current_weight": before if before is not None else "", "keep": "yes"})
    drafted = {(r["concept_id"], r["isco_code"]) for r in rows}
    for (cid, isco), w in sorted(current.items(), key=lambda x: (x[0][1], x[0][0])):
        if (cid, isco) not in drafted:
            out.append({"concept_id": cid, "isco_code": isco, "weight": w, "status": "no ESCO item",
                        "current_weight": w, "esco_items": "", "reason": "hand-drafted; ESCO lists nothing for it",
                        "keep": "yes"})
    return sorted(out, key=lambda r: (r["isco_code"], -float(r["weight"]), r["concept_id"]))


def write_draft(rows: list[dict], path: Path | None = None) -> Path:
    path = path or config.CURATED_DIR / "concept_occupation.draft.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DRAFT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerow({"concept_id": f"# Drafted by {llm.MODEL} from ESCO (kompas links-draft). Review every row: set keep to "
                    "'no' to reject it, then run `kompas links-apply`. Weights come from ESCO (essential 1.0, optional 0.5)."})
        w.writerows(rows)
    return path


def apply(cur: Curated, draft_path: Path | None = None, out: Path | None = None) -> dict[str, int]:
    """Rewrites concept_occupation.csv: family links unchanged, skill links = the draft rows kept, each with its
    ESCO citation as the note."""
    draft_path = draft_path or config.CURATED_DIR / "concept_occupation.draft.csv"
    out = out or config.CURATED_DIR / "concept_occupation.csv"
    with draft_path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["concept_id"] and not r["concept_id"].startswith("#")]
    kept = [r for r in rows if r["keep"].strip().lower() in ("yes", "y", "true", "1")]
    families = [(cid, isco, w) for cid, occs in cur.concept_occupations.items() if cur.concepts[cid].kind == "family"
                for isco, w in occs]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["concept_id", "isco_code", "weight", "note"])
        w.writerow(["# Family links are hand-drafted (they carry Malaysian occupation demand). Skill links are drafted "
                    f"from ESCO by {llm.MODEL}, checked and reviewed (kompas links-draft / links-apply); the note "
                    "cites the ESCO item(s). Essential 1.0 / optional 0.5.", "", "", ""])
        for cid, isco, weight in families:
            w.writerow([cid, isco, weight, ""])
        for r in kept:
            note = f"ESCO: {r['esco_items']}" if r["esco_items"] else "hand-drafted; no ESCO item"
            w.writerow([r["concept_id"], r["isco_code"], float(r["weight"]), note])
    return {"kept": len(kept), "rejected": len(rows) - len(kept), "families": len(families)}
