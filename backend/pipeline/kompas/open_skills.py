"""Skills outside Kompas's concept list, resolved to ESCO (the EU's skills taxonomy, ~14,000 skills).

A CV or a job posting names a skill Kompas doesn't track ("search engine optimisation", "patient triage"). The
ESCO search API returns the closest ESCO skills; the LLM picks the one that is the same skill, or none, and may
only pick from what ESCO returned. The result is stored in open_skill and becomes a concept with origin "esco",
so CVs and postings that name it match each other, and kompas/open_signal.py can measure it in the raw data.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .curated import Concept, Curated
from .connectors import esco_catalogue
from .http import FetchError, Http
from .periods import utcnow

log = logging.getLogger("kompas.open_skills")

SEARCH = "https://ec.europa.eu/esco/api/search"
CANDIDATES = 8
PICK_BATCH = 12
SOURCE = "ESCO (European Commission, CC BY 4.0)"


def skill_id(uri: str) -> str:
    return "esco-" + uri.rstrip("/").rsplit("/", 1)[-1]


# skills found in CVs and postings that aren't Kompas's own: an ESCO skill ("esco-..."), or, when ESCO has no
# skill that is the same, the name itself ("name-..."), measured by that name in the raw data
OPEN_PREFIXES = ("esco-", "name-")


def is_open(cid) -> bool:
    return str(cid).startswith(OPEN_PREFIXES)


def name_id(name: str) -> str:
    return "name-" + re.sub(r"[^a-z0-9]+", "-", _key(name)).strip("-")


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
    """ESCO's closest skills per name: from the stored catalogue (esco_skill) when it is loaded, which needs no
    network; otherwise from ESCO's search API, cached in esco_lookup (ESCO changes once a year or so)."""
    keys = sorted({f"{CANDIDATES}|{_key(n)}" for n in names if _key(n)})
    if not keys:
        return {}
    ix = esco_catalogue.index(conn)
    if ix:
        return {k.split("|", 1)[1]: esco_catalogue.search(ix, k.split("|", 1)[1], CANDIDATES) for k in keys}
    q = ",".join("?" * len(keys))
    out = {r["query"]: json.loads(r["payload"])
           for r in conn.execute(f"SELECT query, payload FROM esco_lookup WHERE query IN ({q})", keys)}
    missing = [k for k in keys if k not in out]
    if missing and esco_down():
        missing = []      # recently unreachable: use what's cached and don't make the request wait on it
    if missing:
        http = http or Http(timeout=8, retries=1)

        def one(k: str):
            try:
                return k, _search(http, k.split("|", 1)[1])
            except FetchError:
                return k, None      # not cached: tried again next time
        with ThreadPoolExecutor(max_workers=6) as pool:
            found = list(pool.map(one, missing))
        if all(v is None for _, v in found):
            _down_until[0] = time.monotonic() + DOWN_FOR
            log.warning("ESCO search unreachable; skipping it for %d minutes", DOWN_FOR // 60)
        now = utcnow()
        rows = [(k, now, json.dumps(v)) for k, v in found if v is not None]
        conn.executemany("INSERT INTO esco_lookup (query, fetched_at, payload) VALUES (?, ?, ?) ON CONFLICT (query) "
                         "DO UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload", rows)
        conn.commit()
        out.update({k: v for k, v in found if v is not None})
    return {k.split("|", 1)[1]: v for k, v in out.items()}


DOWN_FOR = 600        # seconds ESCO is left alone after every search in a batch failed
_down_until = [0.0]


def esco_down() -> bool:
    return time.monotonic() < _down_until[0]


def _concept(cid: str, label: str, uri: str) -> Concept:
    return Concept(cid, label[0].upper() + label[1:], "skill", None, uri or None, (), (), (),
                   origin="name" if cid.startswith("name-") else "esco")


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
    version = catalogue_version(conn)
    remembered = _remembered(conn, names, version)
    asked = [n for n in dict.fromkeys(names) if _key(n) not in remembered]
    found = candidates(conn, asked, http) if asked else {}
    items = [{"name": n, "candidates": found.get(_key(n), [])} for n in asked]
    out = {n: remembered.get(_key(n)) or None for n in names}
    if version:   # with the stored catalogue, no candidates at all is a definite "no ESCO skill is this"
        _remember(conn, [(i["name"], None) for i in items if not i["candidates"]], version)
    items = [i for i in items if i["candidates"]]
    if not items:
        return out, ("the ESCO skills catalogue is unreachable, so skills outside Kompas's list will be matched on "
                     "your next visit" if esco_down() else None)
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
    out.update({name: skill_id(uri) for name, uri, _ in chosen})
    if not error:    # the model answered every batch: remember its "none"s too
        picked = {_key(n) for n, _, _ in chosen}
        _remember(conn, [(n, skill_id(u)) for n, u, _ in chosen]
                  + [(i["name"], None) for i in items if _key(i["name"]) not in picked], version)
    return out, error and f"skills outside Kompas's list were matched by exact name only ({error})"


def catalogue_version(conn) -> str:
    """The stored ESCO catalogue's version ('' when matching goes through the live API): picks are remembered
    per version, so a new catalogue gets a fresh look."""
    row = conn.execute("SELECT MAX(version) FROM esco_skill").fetchone()
    return (row[0] if row else None) or ""


def _remembered(conn, names: list[str], version: str) -> dict[str, str]:
    """name key -> ESCO skill id, or '' for a remembered "no ESCO skill is this"."""
    keys = sorted({_key(n) for n in names if _key(n)})
    if not keys or not version:
        return {}
    q = ",".join("?" * len(keys))
    return {r["name_key"]: r["skill_id"] or "" for r in conn.execute(
        f"SELECT name_key, skill_id FROM esco_pick WHERE version = ? AND name_key IN ({q})", (version, *keys))}


def _remember(conn, picks: list[tuple[str, str | None]], version: str) -> None:
    if not picks or not version:
        return
    now = utcnow()
    conn.executemany("INSERT INTO esco_pick (name_key, version, skill_id, picked_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (name_key, version) DO UPDATE SET skill_id = excluded.skill_id, picked_at = excluded.picked_at",
                     [(_key(n), version, sid, now) for n, sid in picks if _key(n)])
    conn.commit()


def unmatched_for_good(conn, names: list[str]) -> set[str]:
    """Names the model has looked at against the stored catalogue and found no ESCO skill for."""
    version = catalogue_version(conn)
    got = _remembered(conn, names, version)
    return {n for n in names if got.get(_key(n)) == ""}


def register_names(conn, cur: Curated, names: list[str]) -> dict[str, str]:
    """Skills no catalogue has ("data entry"), kept under their own name so they can be measured by it.
    Returns name -> skill id."""
    out = {n: name_id(n) for n in names if len(_key(n)) >= 3}
    if not out:
        return {}
    now = utcnow()
    conn.executemany(
        "INSERT INTO open_skill (id, label, esco_uri, names, created_at) VALUES (?, ?, '', ?, ?) ON CONFLICT (id) DO NOTHING",
        [(cid, n.strip(), json.dumps([_key(n)]), now) for n, cid in out.items()])
    conn.commit()
    _add(cur, {cid: _concept(cid, n.strip(), "") for n, cid in out.items()})
    return out


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
    if any(i not in cur.concepts and is_open(i) for i in ids):
        load_into(cur, conn, force=True)


def names(conn, ids: list[str]) -> dict[str, list[str]]:
    """Each ESCO skill's label and the names texts used for it: the terms to search the raw data for."""
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {r["id"]: sorted({_key(r["label"]), *json.loads(r["names"])})
            for r in conn.execute(f"SELECT id, label, names FROM open_skill WHERE id IN ({q})", ids)}
