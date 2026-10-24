"""Skills outside Kompas's concept list, resolved to ESCO (the EU's skills taxonomy, ~14,000 skills).

A CV or a job posting names a skill Kompas doesn't track ("search engine optimisation", "patient triage"). The
ESCO search API returns the closest ESCO skills; the LLM picks the one that is the same skill, or none, and may
only pick from what ESCO returned. The result is stored in open_skill and becomes a concept with origin "esco",
so CVs and postings that name it match each other, and kompas/open_signal.py can measure it in the raw data.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .curated import Concept, Curated
from .http import FetchError, Http
from .periods import utcnow

SEARCH = "https://ec.europa.eu/esco/api/search"
CANDIDATES = 8
PICK_BATCH = 12
SOURCE = "ESCO (European Commission, CC BY 4.0)"


def skill_id(uri: str) -> str:
    return "esco-" + uri.rstrip("/").rsplit("/", 1)[-1]


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _search(http: Http, name: str) -> list[dict]:
    body = http.get_json(SEARCH, {"text": name, "type": "skill", "language": "en", "limit": CANDIDATES,
                                  "full": "false"})
    out = []
    for r in (body.get("_embedded") or {}).get("results", []):
        label = (r.get("preferredLabel") or {}).get("en") or r.get("title")
        if r.get("uri") and label:
            out.append({"uri": r["uri"], "label": label,
                        "type": ((r.get("hasSkillType") or [""])[0]).rsplit("/", 1)[-1]})
    return out


def candidates(conn, names: list[str], http: Http | None = None) -> dict[str, list[dict]]:
    """ESCO's closest skills per name, cached in esco_lookup (ESCO changes once a year or so)."""
    keys = sorted({f"{CANDIDATES}|{_key(n)}" for n in names if _key(n)})
    if not keys:
        return {}
    q = ",".join("?" * len(keys))
    out = {r["query"]: json.loads(r["payload"])
           for r in conn.execute(f"SELECT query, payload FROM esco_lookup WHERE query IN ({q})", keys)}
    missing = [k for k in keys if k not in out]
    if missing:
        http = http or Http(timeout=15)

        def one(k: str):
            try:
                return k, _search(http, k.split("|", 1)[1])
            except FetchError:
                return k, None      # not cached: tried again next time
        with ThreadPoolExecutor(max_workers=6) as pool:
            found = list(pool.map(one, missing))
        now = utcnow()
        rows = [(k, now, json.dumps(v)) for k, v in found if v is not None]
        conn.executemany("INSERT INTO esco_lookup (query, fetched_at, payload) VALUES (?, ?, ?) ON CONFLICT (query) "
                         "DO UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload", rows)
        conn.commit()
        out.update({k: v for k, v in found if v is not None})
    return {k.split("|", 1)[1]: v for k, v in out.items()}


def _concept(cid: str, label: str, uri: str) -> Concept:
    return Concept(cid, label[0].upper() + label[1:], "skill", None, uri, (), (), (), origin="esco")


def register(conn, cur: Curated, picks: list[tuple[str, str, str]]) -> None:
    """picks: (name used in the text, ESCO uri, ESCO label). Adds new skills and the names they were found under."""
    if not picks:
        return
    ids = sorted({skill_id(uri) for _, uri, _ in picks})
    q = ",".join("?" * len(ids))
    names = {r["id"]: set(json.loads(r["names"])) for r in
             conn.execute(f"SELECT id, names FROM open_skill WHERE id IN ({q})", ids)}
    labels = {}
    for name, uri, label in picks:
        cid = skill_id(uri)
        names.setdefault(cid, set()).add(_key(name))
        labels[cid] = (label, uri)
    now = utcnow()
    conn.executemany(
        "INSERT INTO open_skill (id, label, esco_uri, names, created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) "
        "DO UPDATE SET names = excluded.names",
        [(cid, labels[cid][0], labels[cid][1], json.dumps(sorted(names[cid])), now) for cid in labels])
    conn.commit()
    _add(cur, {cid: _concept(cid, label, uri) for cid, (label, uri) in labels.items()})


def _add(cur: Curated, new: dict[str, Concept]) -> None:
    """Copy and swap, never mutate: background threads add skills while requests iterate cur.concepts."""
    new = {cid: c for cid, c in new.items() if cid not in cur.concepts}
    if new:
        cur.concepts = {**cur.concepts, **new}


def resolve(conn, cur: Curated, names: list[str], context: str = "a CV", client=None,
            http: Http | None = None) -> tuple[dict[str, str | None], str | None]:
    """(name -> ESCO skill id, or None when ESCO has nothing that is that skill; why the model couldn't pick, or
    None). Without the model only an exact ESCO label counts, which leaves most skills unmatched: say so."""
    found = candidates(conn, names, http)
    items = [{"name": n, "candidates": found.get(_key(n), [])} for n in dict.fromkeys(names)]
    items = [i for i in items if i["candidates"]]
    if not items:
        return {n: None for n in names}, None
    # in parallel batches: one call over 40 skills takes long enough to matter during a CV upload
    batches = [items[i:i + PICK_BATCH] for i in range(0, len(items), PICK_BATCH)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda b: llm.pick_esco(b, context, client=client), batches))
    picks = [p for got, _ in answers if got is not None for p in got] if any(got is not None for got, _ in answers) else None
    error = next((e for got, e in answers if got is None), None)
    if picks is not None and error:    # some batches answered: the rest fall back to exact names below
        answered = {_key(p.get("name") or "") for p in picks}
        picks += [{"name": i["name"], "uri": next((c["uri"] for c in i["candidates"]
                                                    if _key(c["label"]) == _key(i["name"])), llm.NONE)}
                  for i in items if _key(i["name"]) not in answered]
    if picks is None:   # no model: only an exact ESCO label counts
        picks = [{"name": i["name"], "uri": next((c["uri"] for c in i["candidates"]
                                                  if _key(c["label"]) == _key(i["name"])), llm.NONE)} for i in items]
    # the model may change a name's case or spacing: match on the normalised name
    by_key = {_key(i["name"]): (i["name"], {c["uri"]: c["label"] for c in i["candidates"]}) for i in items}
    chosen = []
    for p in picks:
        name, cands = by_key.get(_key(p.get("name") or ""), (None, {}))
        if name and p.get("uri") in cands:
            chosen.append((name, p["uri"], cands[p["uri"]]))
    register(conn, cur, chosen)
    out = {n: None for n in names}
    out.update({name: skill_id(uri) for name, uri, _ in chosen})
    return out, error and f"skills outside Kompas's list were matched by exact name only ({error})"


_loaded = [0.0]
TTL = 120


def load_into(cur: Curated, conn, force: bool = False) -> None:
    """Adds every stored ESCO skill to cur.concepts (other API processes may have added some)."""
    if not force and time.monotonic() - _loaded[0] < TTL:
        return
    _add(cur, {r["id"]: _concept(r["id"], r["label"], r["esco_uri"])
               for r in conn.execute("SELECT id, label, esco_uri FROM open_skill")})
    _loaded[0] = time.monotonic()


def ensure_known(cur: Curated, conn, ids) -> None:
    if any(i not in cur.concepts and str(i).startswith("esco-") for i in ids):
        load_into(cur, conn, force=True)


def names(conn, ids: list[str]) -> dict[str, list[str]]:
    """Each ESCO skill's label and the names texts used for it: the terms to search the raw data for."""
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {r["id"]: sorted({_key(r["label"]), *json.loads(r["names"])})
            for r in conn.execute(f"SELECT id, label, names FROM open_skill WHERE id IN ({q})", ids)}
