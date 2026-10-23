"""ESCO (European Skills, Competences, Qualifications and Occupations), the EU's occupation taxonomy.

Used for The Mirror: each catalogue occupation's *essential skills and competences* in ESCO stand in for the
tasks of the job ("prepare financial statements", "manage accounts"). Knowledge items ("tax legislation") are
left out because they aren't tasks.

`kompas esco-sync` fetches them from the public ESCO API and writes curated/occupation_task.csv, so the file can be
reviewed like the other curated tables and The Mirror works offline. The ESCO occupation chosen for each ISCO
group is set by hand in curated/occupation_esco.csv.

Also used for role skill links: `kompas esco-skills` writes each role's essential and optional ESCO skills and
knowledge to curated/occupation_skill_esco.csv, the evidence `kompas links-draft` cites (see kompas/links.py).
A role can cite extra ESCO occupations (curated/role_esco_extra.csv) when ESCO files the closest one under
another ISCO group, e.g. "data scientist" under 2511 for the Statistician / data scientist role.

And for finding a job by what people call it: `kompas esco-aliases` writes every ESCO occupation under each
catalogue ISCO group, with its alternative labels ("software engineer", "programmer" for software developer), to
curated/occupation_alias.csv. The job search on the You step matches against them.
"""

import csv
from pathlib import Path

from .. import config
from ..http import FetchError, Http

API = "https://ec.europa.eu/esco/api/resource"
SKILL = "http://data.europa.eu/esco/skill-type/skill"
COLUMNS = ("isco_code", "esco_occupation", "esco_occupation_uri", "task", "task_uri")
SKILL_COLUMNS = ("isco_code", "esco_occupation", "esco_occupation_uri", "relation", "skill_type", "skill", "skill_uri")
ALIAS_COLUMNS = ("isco_code", "alias", "esco_occupation")


def choices(path: Path | None = None) -> dict[str, str]:
    path = path or config.CURATED_DIR / "occupation_esco.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return {r["isco_code"].strip(): r["esco_title"].strip() for r in csv.DictReader(f)
                if r["isco_code"] and not r["isco_code"].startswith("#")}


def _occupation(http: Http, isco: str, title: str) -> tuple[dict, dict]:
    """The ESCO occupation titled `title` under ISCO group `isco`, and its detail record."""
    group = http.get_json(f"{API}/concept", {"uri": f"http://data.europa.eu/esco/isco/C{isco}", "language": "en"})
    occupations = group.get("_links", {}).get("narrowerOccupation", [])
    occ = next((o for o in occupations if o["title"].lower() == title.lower()), None)
    if occ is None:
        raise FetchError("parse", f"ESCO has no occupation '{title}' under ISCO {isco} "
                                  f"(found: {', '.join(o['title'] for o in occupations)})")
    return occ, http.get_json(f"{API}/occupation", {"uri": occ["uri"], "language": "en"})


def fetch_tasks(http: Http, isco: str, title: str) -> list[dict]:
    occ, detail = _occupation(http, isco, title)
    skills = detail.get("_links", {}).get("hasEssentialSkill", [])
    return [{"isco_code": isco, "esco_occupation": occ["title"], "esco_occupation_uri": occ["uri"],
             "task": s["title"], "task_uri": s["uri"]} for s in skills if s.get("skillType") == SKILL]


def fetch_skills(http: Http, role: str, isco: str, title: str) -> list[dict]:
    """Every essential and optional skill and knowledge item of an ESCO occupation, filed under `role`."""
    occ, detail = _occupation(http, isco, title)
    links = detail.get("_links", {})
    return [{"isco_code": role, "esco_occupation": occ["title"], "esco_occupation_uri": occ["uri"],
             "relation": relation, "skill_type": (s.get("skillType") or "").rsplit("/", 1)[-1],
             "skill": s["title"], "skill_uri": s["uri"]}
            for relation, key in (("essential", "hasEssentialSkill"), ("optional", "hasOptionalSkill"))
            for s in links.get(key, [])]


def evidence(path: Path | None = None) -> list[tuple[str, str, str]]:
    """(role ISCO, ISCO group to look in, ESCO title) for every ESCO occupation a role's skill links may cite:
    The Mirror's choice for the role plus the extras in role_esco_extra.csv."""
    out = [(isco, isco, title) for isco, title in sorted(choices().items())]
    path = path or config.CURATED_DIR / "role_esco_extra.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            out += [(r["isco_code"].strip(), r["esco_isco"].strip(), r["esco_title"].strip()) for r in csv.DictReader(f)
                    if r["isco_code"] and not r["isco_code"].startswith("#")]
    return out


def sync(http: Http | None = None, out: Path | None = None) -> dict[str, int]:
    """Writes occupation_task.csv. Fails without writing if any occupation can't be fetched, so a partial
    file never replaces a complete one."""
    http = http or Http(min_interval=0.3)
    rows, counts = [], {}
    for isco, title in sorted(choices().items()):
        tasks = fetch_tasks(http, isco, title)
        counts[isco] = len(tasks)
        rows.extend(sorted(tasks, key=lambda t: t["task"]))
    out = out or config.CURATED_DIR / "occupation_task.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerow({"isco_code": "# Essential ESCO skills/competences per occupation, used as task cards in The Mirror. "
                    "Generated by `kompas esco-sync` from the ESCO API (CC BY 4.0, European Commission); don't edit by hand."})
        w.writerows(rows)
    return counts


def sync_skills(http: Http | None = None, out: Path | None = None) -> dict[str, int]:
    """Writes occupation_skill_esco.csv. Like sync(), fails without writing if any occupation can't be fetched."""
    http = http or Http(min_interval=0.3)
    rows, counts = [], {}
    for role, isco, title in evidence():
        items = fetch_skills(http, role, isco, title)
        counts[f"{role} {title}"] = len(items)
        rows.extend(sorted(items, key=lambda i: (i["relation"], i["skill"].lower())))
    out = out or config.CURATED_DIR / "occupation_skill_esco.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SKILL_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerow({"isco_code": "# Essential and optional ESCO skills/knowledge per role: the evidence for role skill links. "
                    "Generated by `kompas esco-skills` from the ESCO API (CC BY 4.0, European Commission); don't edit by hand."})
        w.writerows(rows)
    return counts


def fetch_aliases(http: Http, isco: str) -> list[dict]:
    """Every ESCO occupation under ISCO group `isco`: its title and its English alternative labels."""
    group = http.get_json(f"{API}/concept", {"uri": f"http://data.europa.eu/esco/isco/C{isco}", "language": "en"})
    rows = []
    for occ in group.get("_links", {}).get("narrowerOccupation", []):
        detail = http.get_json(f"{API}/occupation", {"uri": occ["uri"], "language": "en"})
        labels = {occ["title"], *(detail.get("alternativeLabel", {}).get("en") or [])}
        rows += [{"isco_code": isco, "alias": a.strip().lower(), "esco_occupation": occ["title"]}
                 for a in labels if a and a.strip()]
    return rows


def sync_aliases(isco_codes: list[str], http: Http | None = None, out: Path | None = None) -> dict[str, int]:
    """Writes occupation_alias.csv. Like sync(), fails without writing if any group can't be fetched."""
    http = http or Http(min_interval=0.3)
    rows, counts = [], {}
    for isco in sorted(set(isco_codes)):
        found = {(r["alias"], r["esco_occupation"]): r for r in fetch_aliases(http, isco)}
        counts[isco] = len(found)
        rows.extend(sorted(found.values(), key=lambda r: (r["esco_occupation"], r["alias"])))
    out = out or config.CURATED_DIR / "occupation_alias.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ALIAS_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerow({"isco_code": "# What people call the jobs in each catalogue ISCO group: every ESCO occupation in the group "
                    "and its alternative labels. Generated by `kompas esco-aliases` from the ESCO API (CC BY 4.0, "
                    "European Commission); don't edit by hand."})
        w.writerows(rows)
    return counts


def aliases(path: Path | None = None) -> dict[str, list[str]]:
    """ISCO group -> the names people use for its jobs. Empty until `kompas esco-aliases` has run."""
    path = path or config.CURATED_DIR / "occupation_alias.csv"
    if not path.exists():
        return {}
    out: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["isco_code"] and not r["isco_code"].startswith("#"):
                out.setdefault(r["isco_code"].strip(), []).append(r["alias"].strip())
    return {k: sorted(set(v)) for k, v in out.items()}
