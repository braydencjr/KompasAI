"""Which of your skills cover a role's skill, by meaning rather than by id.

A role asks for "Hire staff" and your CV says "Recruit personnel": different ids, same skill. Each skill's label is
embedded once (Gemini, 256 dimensions) and stored in skill_embedding, as reference data. A skill you lack counts as
covered by the most similar skill you have when they are similar enough: from FLOOR the credit grows with the
similarity, to full credit at FULL. The cutoffs come from checking pairs by hand: related skills score 0.92 and up
("Recruit personnel" ~ "Hire staff" 0.94), unrelated ones below, but short labels bunch near it ("English" ~ "Excel"
0.91), so FLOOR is strict and some true pairs are missed.
"""

import json
import logging
import math

from google import genai

from . import llm
from .curated import Curated
from .periods import utcnow

log = logging.getLogger("kompas.similar")

MODEL = "gemini-embedding-001"
DIMENSIONS = 256
BATCH = 100
FLOOR, FULL = 0.92, 0.97        # similarity at which credit starts (50%) and is complete (100%)

_vec: dict[str, list[float]] = {}     # concept id -> unit vector, for the skills ensure() has seen


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def ensure(conn, cur: Curated, ids, client: genai.Client | None = None) -> None:
    """Loads the stored embeddings of these skills, and embeds and stores the ones that are missing. If the model
    can't be reached the skills simply have no similarity (they match by id only)."""
    ids = [i for i in dict.fromkeys(ids) if i in cur.concepts and cur.concepts[i].kind == "skill" and i not in _vec]
    if not ids:
        return
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in conn.execute(f"SELECT skill_id, vector FROM skill_embedding WHERE model = ? AND skill_id IN "
                              f"({','.join('?' * len(chunk))})", (MODEL, *chunk)):
            _vec[r["skill_id"]] = json.loads(r["vector"])
    todo = [i for i in ids if i not in _vec]
    if not todo or (client is None and not llm.available()):
        return
    client = client or genai.Client()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            out = client.models.embed_content(model=MODEL, contents=[cur.concepts[c].label for c in chunk],
                                              config={"task_type": "SEMANTIC_SIMILARITY",
                                                      "output_dimensionality": DIMENSIONS})
        except Exception as e:      # an embedding outage must not stop the journey
            log.warning("embedding failed: %s", e)
            return
        rows = []
        for c, e in zip(chunk, out.embeddings):
            _vec[c] = _unit(list(e.values))
            rows.append((c, MODEL, json.dumps([round(x, 5) for x in _vec[c]]), utcnow()))
        conn.executemany("INSERT INTO skill_embedding (skill_id, model, vector, created_at) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT (skill_id) DO UPDATE SET model = excluded.model, vector = excluded.vector", rows)
        conn.commit()


def credit(similarity: float) -> float:
    """0 below FLOOR, then 50% rising to 100% at FULL."""
    if similarity < FLOOR:
        return 0.0
    return min(1.0, 0.5 + 0.5 * (similarity - FLOOR) / (FULL - FLOOR))


def closest(cid: str, have: list[str]) -> tuple[str, float] | None:
    """The skill you have that is most like `cid`, with its similarity, or None."""
    v = _vec.get(cid)
    if not v:
        return None
    best = max(((h, sum(a * b for a, b in zip(v, _vec[h]))) for h in have if h in _vec and h != cid),
               key=lambda x: x[1], default=None)
    return best
