"""ILO's Generative AI exposure index (Gmyrek et al., 2025, "Generative AI and Jobs: A Refined Global Index of
Occupational Exposure", ILO Working Paper 140; CC BY 4.0).

Every ISCO-08 4-digit occupation, its tasks as ISCO-08 describes them, and each task's exposure score (0-1: how much
of the task generative AI could do, from a worker survey, expert review and a model trained on both). MASCO 2020
follows ISCO-08, so the scores apply to Malaysian job codes directly.

`kompas ilo-sync` downloads the task-level file the authors publish into the ilo_task table. It is reference data:
The Mirror shows the published scores where the index has the job, and kompas/exposure.py has the LLM score other
jobs' tasks against the most similar published ones.
"""

import json
import re
import time
from dataclasses import dataclass
from statistics import fmean, pstdev

from ..http import Http
from ..periods import utcnow

URL = "https://pgmyrek.github.io/2025_GenAI_scores_ISCO08/output_data.json"
PAPER = "https://www.ilo.org/node/706766"
SOURCE = "ILO Generative AI exposure index (2025)"
# the paper's task bands (Very Low < 0.25 <= Low < 0.5 <= Medium < 0.75 <= High); 0.5 is where it starts counting
# a task as exposed (its exposure gradients all need mean + SD >= 0.5)
EXPOSED_AT = 0.5

_OCC = re.compile(r"^(\d{4}) - (.+)$")
_TASK = re.compile(r"^\( ([\d.]+) \) - (.+)$")


def band(score: float) -> str:
    return "High" if score >= 0.75 else "Medium" if score >= 0.5 else "Low" if score >= 0.25 else "Very Low"


def _repair(text: str) -> str:
    """Some of the file's tasks carry UTF-8 read as Mac Roman ("establishment‚Äôs"): read it back as UTF-8."""
    if "‚Ä" not in text and "√" not in text:
        return text
    try:
        return text.encode("mac_roman").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def parse(tree: dict) -> list[dict]:
    rows, counts = [], {}

    def walk(node: dict, occ: tuple[str, str, str] | None):
        name = node.get("name", "")
        m = _OCC.match(name)
        if m:
            occ = (m.group(1), _repair(m.group(2)).strip(), node.get("risk") or "")
        t = _TASK.match(name)
        if t and occ:
            counts[occ[0]] = counts.get(occ[0], 0) + 1
            rows.append({"isco": occ[0], "task_no": counts[occ[0]], "occupation": occ[1], "gradient": occ[2],
                         "task": _repair(t.group(2)).strip().rstrip(";.").strip(), "score": float(t.group(1)),
                         "band": node.get("risk") or band(float(t.group(1)))})
        for c in node.get("children", []):
            walk(c, occ)

    walk(tree, None)
    return rows


def sync(conn, http: Http | None = None) -> dict[str, int]:
    """Replaces the published rows (origin 'ilo'); the LLM's scored tasks for other jobs are kept."""
    rows = parse((http or Http()).get_json(URL))
    if len({r["isco"] for r in rows}) < 400:
        raise ValueError(f"the ILO file has only {len(rows)} tasks; keeping the stored copy")
    now = utcnow()
    conn.execute("DELETE FROM ilo_task WHERE origin = 'ilo'")
    conn.executemany(
        "INSERT INTO ilo_task (isco, task_no, occupation, gradient, task, score, band, origin, basis, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'ilo', '[]', ?)",
        [(r["isco"], r["task_no"], r["occupation"], r["gradient"], r["task"], r["score"], r["band"], now) for r in rows])
    conn.commit()
    return {"occupations": len({r["isco"] for r in rows}), "tasks": len(rows)}


@dataclass(frozen=True)
class Task:
    isco: str
    no: int
    occupation: str
    label: str
    score: float
    band: str
    origin: str          # ilo | llm
    basis: tuple = ()    # llm: the ILO tasks it was scored against, as (isco, task_no, score)

    @property
    def id(self) -> str:
        return f"ilo:{self.isco}:{self.no}"


@dataclass(frozen=True)
class Occupation:
    isco: str
    title: str
    gradient: str | None
    mean: float
    sd: float
    origin: str


class Index:
    """The ilo_task table in memory (a few thousand rows), reloaded after TTL seconds."""

    TTL = 600

    def __init__(self):
        self.tasks: dict[str, list[Task]] = {}
        self.occupations: dict[str, Occupation] = {}
        self.loaded = 0.0

    def load(self, conn, force: bool = False) -> "Index":
        if not force and self.tasks and time.monotonic() - self.loaded < self.TTL:
            return self
        tasks: dict[str, list[Task]] = {}
        gradients: dict[str, str | None] = {}
        for r in conn.execute("SELECT * FROM ilo_task ORDER BY isco, task_no"):
            basis = tuple(tuple(b) for b in json.loads(r["basis"] or "[]"))
            tasks.setdefault(r["isco"], []).append(Task(r["isco"], r["task_no"], r["occupation"], r["task"],
                                                        r["score"], r["band"] or band(r["score"]), r["origin"], basis))
            gradients.setdefault(r["isco"], r["gradient"])
        self.occupations = {
            isco: Occupation(isco, ts[0].occupation, gradients[isco], round(fmean(t.score for t in ts), 3),
                             round(pstdev([t.score for t in ts]), 3), ts[0].origin)
            for isco, ts in tasks.items()}
        self.tasks, self.loaded = tasks, time.monotonic()
        return self

    def published(self) -> list[Task]:
        return [t for ts in self.tasks.values() for t in ts if t.origin == "ilo"]


INDEX = Index()
