"""Loads and validates the hand-curated tables in pipeline/curated/."""

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

STATUSES = ("Watch", "Emerging", "Act now", "Stable", "Declining", "Stalled")


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    rung: int
    grain: str          # month | quarter
    volume: str         # count | share
    url: str
    licence_note: str
    coverage_note: str


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    kind: str           # skill | capability | family
    parent_id: str | None
    esco_uri: str | None
    arxiv_terms: tuple[str, ...]
    github_topics: tuple[str, ...]
    weak_topics: tuple[str, ...] = ()   # written "~topic": counted for trends, too generic for the feed
    # curated (concepts.csv) | esco: a skill found in a CV or job posting and resolved to ESCO at run time
    # (kompas/open_skills.py). ESCO skills have no aliases or topics, so snapshots don't score them:
    # kompas/open_signal.py measures them from the raw data on request instead.
    origin: str = "curated"


@dataclass(frozen=True)
class Alias:
    alias: str
    concept_id: str
    case_sensitive: bool


@dataclass(frozen=True)
class Task:
    isco: str
    occupation: str          # ESCO occupation standing for the ISCO group
    occupation_uri: str
    label: str
    uri: str


@dataclass(frozen=True)
class TaskRule:
    capability_id: str
    pattern: str
    rationale: str


@dataclass(frozen=True)
class SdgTag:
    sdg: int
    target: str
    rationale: str


@dataclass(frozen=True)
class Resource:
    skill_id: str
    title: str
    provider: str
    url: str
    hours: float
    cost: str               # free | free-to-audit | low-cost | paid
    language: str
    hrdc_verified: bool
    checked: str


@dataclass
class Curated:
    sources: dict[str, Source]
    concepts: dict[str, Concept]
    aliases: list[Alias]
    occupation_codes: dict[tuple[str, str], str]           # (system, code) -> ISCO-08
    occupation_titles: dict[str, str]                       # ISCO-08 -> title
    role_titles: dict[str, str]                             # ISCO-08 -> readable role name ("Accountant")
    concept_occupations: dict[str, list[tuple[str, float]]] # concept -> [(ISCO, weight)]
    capability_skills: dict[str, list[tuple[str, str]]]     # capability -> [(skill, rationale)]
    version: str
    topic_index: dict[str, list[tuple[str, bool]]] = field(default_factory=dict)  # topic -> [(concept, weak)]
    # user journey tables (The Mirror, Three Bets, The Route)
    tasks: dict[str, list[Task]] = field(default_factory=dict)                   # ISCO -> ESCO tasks
    task_rules: list[TaskRule] = field(default_factory=list)                     # capability bridge to tasks
    sdg_tags: dict[tuple[str, str], list[SdgTag]] = field(default_factory=dict)  # (role|skill, id) -> tags
    resources: dict[str, list[Resource]] = field(default_factory=dict)           # skill -> learning resources
    prereqs: dict[str, list[str]] = field(default_factory=dict)                  # skill -> skills it requires
    # role skills measured from live Malaysian job postings (kompas/requirements.py): ISCO -> [(skill, importance)]
    posting_roles: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    posting_meta: dict[str, dict] = field(default_factory=dict)                  # ISCO -> {title, postings, fetched_at}

    def __post_init__(self):
        for c in self.concepts.values():
            for t in c.github_topics:
                self.topic_index.setdefault(t, []).append((c.id, t in c.weak_topics))

    def ancestors(self, concept_id: str) -> list[str]:
        out, cur = [], self.concepts[concept_id].parent_id
        while cur and cur not in out:
            out.append(cur)
            cur = self.concepts[cur].parent_id if cur in self.concepts else None
        return out

    def all_topics(self) -> list[str]:
        return sorted(self.topic_index)

    def curated_ids(self, *kinds: str) -> list[str]:
        """Concept ids from concepts.csv (not ESCO skills added at run time), optionally of the given kinds."""
        return sorted(cid for cid, c in self.concepts.items() if c.origin == "curated" and (not kinds or c.kind in kinds))


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
            if any((v or "").strip() for v in row.values()) and not (row.get(next(iter(row))) or "").startswith("#")
        ]


def _split(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split("|") if p.strip())


def load(directory: Path | None = None) -> Curated:
    d = directory or config.CURATED_DIR
    files = ["sources.csv", "concepts.csv", "concept_alias.csv", "occupation_code_map.csv", "concept_occupation.csv",
             "capability_skill.csv", "occupation_task.csv", "capability_task_rule.csv", "sdg_tag.csv", "resource.csv",
             "skill_prereq.csv"]
    files = [f for f in files if (d / f).exists()]
    version = hashlib.sha256(b"".join((d / f).read_bytes() for f in files)).hexdigest()[:12]

    sources = {
        r["id"]: Source(r["id"], r["name"], int(r["rung"]), r["grain"], r["volume"], r["url"],
                        r["licence_note"], r["coverage_note"])
        for r in _rows(d / "sources.csv")
    }
    concepts = {}
    for r in _rows(d / "concepts.csv"):
        topics = _split(r["github_topics"])
        concepts[r["id"]] = Concept(
            r["id"], r["label"], r["kind"], r["parent_id"] or None, r["esco_uri"] or None, _split(r["arxiv_terms"]),
            tuple(t.lstrip("~") for t in topics), tuple(t.lstrip("~") for t in topics if t.startswith("~")),
        )
    aliases = [
        Alias(r["alias"], r["concept_id"], r["case_sensitive"].lower() == "true")
        for r in _rows(d / "concept_alias.csv")
    ]
    codes, titles, role_titles = {}, {}, {}
    for r in _rows(d / "occupation_code_map.csv"):
        codes[(r["source_system"], r["source_code"])] = r["isco_code"]
        titles.setdefault(r["isco_code"], r["source_title"])
        role_titles.setdefault(r["isco_code"], r["role_title"] or r["source_title"])
    concept_occ: dict[str, list[tuple[str, float]]] = {}
    for r in _rows(d / "concept_occupation.csv"):
        concept_occ.setdefault(r["concept_id"], []).append((r["isco_code"], float(r["weight"])))

    cap_skills: dict[str, list[tuple[str, str]]] = {}
    for r in _rows(d / "capability_skill.csv"):
        cap_skills.setdefault(r["capability_id"], []).append((r["skill_id"], r["rationale"]))

    cur = Curated(sources, concepts, aliases, codes, titles, role_titles, concept_occ, cap_skills, version)
    for r in _optional(d / "occupation_task.csv"):
        cur.tasks.setdefault(r["isco_code"], []).append(
            Task(r["isco_code"], r["esco_occupation"], r["esco_occupation_uri"], r["task"], r["task_uri"]))
    cur.task_rules = [TaskRule(r["capability_id"], r["task_pattern"], r["rationale"])
                      for r in _optional(d / "capability_task_rule.csv")]
    for r in _optional(d / "sdg_tag.csv"):
        cur.sdg_tags.setdefault((r["entity_type"], r["entity_id"]), []).append(
            SdgTag(int(r["sdg"]), r["target"], r["rationale"]))
    for r in _optional(d / "resource.csv"):
        cur.resources.setdefault(r["skill_id"], []).append(Resource(
            r["skill_id"], r["title"], r["provider"], r["url"], float(r["est_hours"]), r["cost"], r["language"],
            r["hrdc_verified"].lower() == "true", r["checked"]))
    for r in _optional(d / "skill_prereq.csv"):
        cur.prereqs.setdefault(r["skill_id"], []).append(r["requires_id"])
    return cur


def _optional(path: Path) -> list[dict]:
    return _rows(path) if path.exists() else []


def validate(cur: Curated) -> list[str]:
    errors = []
    for c in cur.concepts.values():
        if c.kind not in ("skill", "capability", "family"):
            errors.append(f"concept {c.id}: unknown kind {c.kind!r}")
        if c.parent_id and c.parent_id not in cur.concepts:
            errors.append(f"concept {c.id}: parent {c.parent_id!r} does not exist")
        if c.id in cur.ancestors(c.id):
            errors.append(f"concept {c.id}: parent cycle")
    seen = set()
    for a in cur.aliases:
        if a.concept_id not in cur.concepts:
            errors.append(f"alias {a.alias!r}: concept {a.concept_id!r} does not exist")
        key = (a.alias if a.case_sensitive else a.alias.lower(), a.concept_id)
        if key in seen:
            errors.append(f"alias {a.alias!r} -> {a.concept_id}: duplicate")
        seen.add(key)
    for cid, occs in cur.concept_occupations.items():
        if cid not in cur.concepts:
            errors.append(f"concept_occupation: concept {cid!r} does not exist")
        for isco, w in occs:
            if isco not in cur.occupation_titles:
                errors.append(f"concept_occupation {cid}: ISCO {isco} missing from occupation_code_map.csv")
            if w not in (0.5, 1.0):
                errors.append(f"concept_occupation {cid}/{isco}: weight must be 1.0 or 0.5")
    for cap, links in cur.capability_skills.items():
        if cur.concepts.get(cap) is None or cur.concepts[cap].kind != "capability":
            errors.append(f"capability_skill: {cap!r} is not a capability concept")
        for skill, _ in links:
            if skill not in cur.concepts:
                errors.append(f"capability_skill {cap}: skill {skill!r} does not exist")
    for s in cur.sources.values():
        if s.grain not in ("month", "quarter") or s.volume not in ("count", "share"):
            errors.append(f"source {s.id}: bad grain/volume")
    labels = [t.label for tasks in cur.tasks.values() for t in tasks]
    for isco in cur.tasks:
        if isco not in cur.role_titles:
            errors.append(f"occupation_task: ISCO {isco} isn't in occupation_code_map.csv")
    for rule in cur.task_rules:
        c = cur.concepts.get(rule.capability_id)
        if c is None or c.kind != "capability":
            errors.append(f"capability_task_rule: {rule.capability_id!r} is not a capability concept")
        if labels and not any(task_matches(rule.pattern, l) for l in labels):
            errors.append(f"capability_task_rule: '{rule.pattern}' matches no task")
    for (kind, eid), tags in cur.sdg_tags.items():
        if kind == "skill" and eid not in cur.concepts:
            errors.append(f"sdg_tag: skill {eid!r} does not exist")
        if kind == "role" and eid not in cur.role_titles:
            errors.append(f"sdg_tag: role {eid!r} isn't in occupation_code_map.csv")
        for t in tags:
            if not 1 <= t.sdg <= 17 or not t.target.startswith(f"{t.sdg}."):
                errors.append(f"sdg_tag {kind} {eid}: target {t.target} doesn't belong to SDG {t.sdg}")
    if cur.sdg_tags:
        for cid, c in cur.concepts.items():
            if c.kind == "skill" and ("skill", cid) not in cur.sdg_tags:
                errors.append(f"sdg_tag: skill {cid} has no SDG link (FR-7.1)")
        for isco in cur.role_titles:
            if ("role", isco) not in cur.sdg_tags:
                errors.append(f"sdg_tag: role {isco} has no SDG link (FR-7.1)")
    for skill, items in cur.resources.items():
        if skill not in cur.concepts:
            errors.append(f"resource: skill {skill!r} does not exist")
        for r in items:
            if not r.url.startswith("https://") or r.cost not in ("free", "free-to-audit", "low-cost", "paid"):
                errors.append(f"resource {r.title!r}: bad url or cost")
    for skill, reqs in cur.prereqs.items():
        for req in reqs:
            if skill not in cur.concepts or req not in cur.concepts:
                errors.append(f"skill_prereq: {skill} -> {req} names an unknown skill")
    return errors


def task_matches(pattern: str, label: str) -> bool:
    """A capability rule applies to a task when its pattern appears in the task label as whole words."""
    return re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", label, re.IGNORECASE) is not None
