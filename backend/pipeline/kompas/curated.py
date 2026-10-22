"""Loads and validates the hand-curated tables in pipeline/curated/."""

import csv
import hashlib
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


@dataclass(frozen=True)
class Alias:
    alias: str
    concept_id: str
    case_sensitive: bool


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
             "capability_skill.csv"]
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

    return Curated(sources, concepts, aliases, codes, titles, role_titles, concept_occ, cap_skills, version)


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
    return errors
