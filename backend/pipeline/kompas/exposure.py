"""How exposed a job's tasks are to generative AI: the ILO's published scores where the index lists the job,
otherwise the LLM's scores for the job's tasks, anchored on the index.

The index (connectors/ilo.py) is reference data, not a closed list. For a job it doesn't have, such as a CV job no
ISCO-08 code fits ("prompt engineer"), the LLM writes the job's main tasks and scores each one against the most
similar ILO-scored tasks, which it must cite, as the ILO itself scored ISCO-08 with a model shown its scored
examples. A score outside the range of the tasks it cites is dropped. The result is stored in ilo_task (origin
'llm') with its references, so each job is estimated once and later requests read it like the published scores.
"""

import json
import re

from . import llm
from .connectors import ilo
from .periods import utcnow

REFERENCES = 40
TOLERANCE = 0.06        # the prompt allows 0.05 either side of the cited range; a little slack for rounding
MIN_TASKS = 3
_WORD = re.compile(r"[a-z]{3,}")
_STOP = {"and", "the", "for", "with", "other", "related", "workers", "professionals", "associate", "not",
         "elsewhere", "classified", "specialist", "officer", "executive", "senior", "junior", "assistant"}


def custom_id(title: str) -> str:
    """The code of a job the index doesn't list, from its title: "x-prompt-engineer"."""
    return "x-" + "-".join(re.findall(r"[a-z0-9]+", title.lower()))[:48]


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def references(idx: ilo.Index, title: str, near: str | None = None, k: int = REFERENCES) -> list[ilo.Task]:
    """The published tasks most like the job: its ISCO minor group's (when a nearby code is known), then the
    occupations and tasks sharing most words with its title. Always some of the highest and lowest scored, so the
    model sees the whole scale."""
    words = _words(title)
    published = idx.published()
    by_overlap = sorted(published, key=lambda t: (-len(words & _words(f"{t.occupation} {t.label}")), -t.score))
    group = [t for t in published if near and t.isco.startswith(near[:3])]
    scale = sorted(published, key=lambda t: t.score)
    picked: dict[str, ilo.Task] = {}
    for t in [*group[:16], *by_overlap[: k - 8], *scale[:4], *scale[-4:]]:
        picked.setdefault(t.id, t)
    return list(picked.values())[:k]


def check(tasks: list[dict], refs: dict[str, ilo.Task]) -> list[tuple[str, float, list[ilo.Task]]]:
    """The estimates that hold up: cite 2+ listed references and score within their range."""
    out = []
    for t in tasks:
        cited = [refs[r] for r in dict.fromkeys(t.get("refs") or []) if r in refs]
        score = t.get("score")
        if len(cited) < 2 or not isinstance(score, (int, float)) or not (t.get("task") or "").strip():
            continue
        lo, hi = min(c.score for c in cited), max(c.score for c in cited)
        if lo - TOLERANCE <= score <= hi + TOLERANCE:
            out.append((t["task"].strip().rstrip("."), round(float(score), 3), cited))
    return out


def estimate(conn, title: str, near: str | None = None, client=None) -> tuple[str | None, str | None]:
    """Scores the tasks of a job the index doesn't list and stores them. Returns (its code, None), or
    (None, reason) when the model can't be used or too few estimates hold up."""
    idx = ilo.INDEX.load(conn)
    code = custom_id(title)
    if code in idx.tasks:
        return code, None
    pool = references(idx, title, near)
    refs = {f"R{i}": t for i, t in enumerate(pool, start=1)}
    listing = [{"ref": r, "occupation": t.occupation, "task": t.label, "score": t.score} for r, t in refs.items()]
    result, error = llm.score_tasks(title, listing, client=client)
    if result is None:
        return None, error
    held = check(result, refs)
    if len(held) < MIN_TASKS:
        return None, f"only {len(held)} of {len(result)} task estimates matched their ILO references"
    now = utcnow()
    conn.execute("DELETE FROM ilo_task WHERE isco = ?", (code,))
    conn.executemany(
        "INSERT INTO ilo_task (isco, task_no, occupation, gradient, task, score, band, origin, basis, created_at) "
        "VALUES (?, ?, ?, NULL, ?, ?, ?, 'llm', ?, ?)",
        [(code, n, title.strip(), task, score, ilo.band(score),
          json.dumps([[c.isco, c.no, c.score] for c in cited]), now)
         for n, (task, score, cited) in enumerate(held, start=1)])
    conn.commit()
    ilo.INDEX.load(conn, force=True)
    return code, None


_links: dict[str, dict] = {}     # cache key -> links, so a journey's many roles cost no round trips
_why: dict[str, str] = {}        # task id -> the plain sentence The Mirror shows for it
MAX_WHY_WORDS = 24


def _plain(text: str) -> str | None:
    """A task's sentence, if it is plain: short, no numbers, no scores or research names."""
    text = (text or "").strip()
    if not text or len(text.split()) > MAX_WHY_WORDS or re.search(r"\d|\bILO\b|\bscore|\bexposure\b", text, re.I):
        return None
    return text if text.endswith((".", "!", "?")) else text + "."


def capability_links(conn, cur, tasks: list[ilo.Task], client=None, cached_only: bool = False) -> dict[str, list[tuple[str, str]]]:
    """task id -> [(capability id, rationale)]: which tracked AI capability each task relies on, so The Mirror can
    follow the capability's Signal Ladder status. Written once per job by the LLM with each task's plain sentence
    (why()), and stored. cached_only: don't ask the model now (an unlinked job then has no capability links: its
    tasks keep their ILO scores). Without a model, the curated pattern rules (capability_task_rule.csv) apply."""
    import hashlib

    from .curated import task_matches

    if not tasks:
        return {}
    caps = [{"id": cid, "label": cur.concepts[cid].label} for cid in cur.curated_ids("capability")]
    key = "caps2:" + hashlib.sha256(json.dumps([[t.id, t.label, t.score] for t in tasks] + caps).encode()).hexdigest()[:24]
    if key in _links:
        return _links[key]
    row = conn.execute("SELECT payload FROM narration WHERE key = ?", (key,)).fetchone()
    if row:
        payload = json.loads(row["payload"])
        _why.update(payload["why"])
        _links[key] = {k: [tuple(x) for x in v] for k, v in payload["links"].items()}
        return _links[key]
    if cached_only:
        return {}
    links, _error = llm.link_capabilities([{"id": t.id, "task": t.label, "exposure": t.score} for t in tasks], caps,
                                          client=client)
    if links is None:
        return {t.id: [(r.capability_id, r.rationale) for r in cur.task_rules if task_matches(r.pattern, t.label)]
                for t in tasks}
    known, valid = {c["id"] for c in caps}, {t.id for t in tasks}
    out: dict[str, list[tuple[str, str]]] = {t.id: [] for t in tasks}
    why: dict[str, str] = {}
    for link in links:
        if link.get("task_id") not in valid:
            continue
        if link.get("capability_id") in known:
            out[link["task_id"]].append((link["capability_id"], (link.get("rationale") or "").strip().rstrip(".")))
        if _plain(link.get("why")):
            why[link["task_id"]] = _plain(link["why"])
    conn.execute("INSERT INTO narration (key, created_at, payload) VALUES (?, ?, ?) ON CONFLICT (key) DO NOTHING",
                 (key, utcnow(), json.dumps({"links": out, "why": why})))
    conn.commit()
    _why.update(why)
    _links[key] = out
    return out


# when the model hasn't written a task's sentence: what its score means, in plain words
BAND_WHY = {"High": "AI can already do most of this.", "Medium": "AI can already do a good part of this.",
            "Low": "AI can help with parts of this, but it mostly needs you.",
            "Very Low": "This needs a person. AI can help only a little."}


def why(task: ilo.Task) -> str:
    """The plain sentence for a task: how much of it AI can do, and why."""
    return _why.get(task.id) or BAND_WHY.get(task.band, BAND_WHY["Low"])
