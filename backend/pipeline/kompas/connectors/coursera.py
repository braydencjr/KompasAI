"""Coursera's public course catalogue, for The Route's AI learning plan.

The catalogue API (api.coursera.org/api/courses.v1) needs no key but no longer offers search, so the whole catalogue
(about 25,000 courses, every field from accounting to nursing) is downloaded in pages of 1,000, cached for a week
(course_cache table) and searched here. When Coursera can't be reached, the last cached copy is used.

Only real catalogue entries are ever shown: the AI picks from search results by id, and the link is built from the
course's own slug. Kompas links out to each course; it copies nothing else.
"""

import json
import math
import re
from datetime import datetime, timedelta, timezone

from ..http import FetchError, Http

API = "https://api.coursera.org/api/courses.v1"
PAGE = 1000
MAX_PAGES = 60          # a guard: the catalogue is about 26 pages today
CACHE_DAYS = 7
PROVIDER = "Coursera"

_index: dict[str, tuple] = {}   # fetched_at -> (courses, word -> how many course names contain it)


def _cache(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS course_cache (provider TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, "
                 "payload TEXT NOT NULL)")


def _fetch(http: Http) -> list[dict]:
    courses, start = [], 0
    for _ in range(MAX_PAGES):
        body = http.get_json(API, {"start": start, "limit": PAGE, "includes": "partnerIds",
                                   "fields": "name,slug,workload,partnerIds,primaryLanguages,partners.v1(name)"})
        partners = {p["id"]: p["name"] for p in body.get("linked", {}).get("partners.v1", [])}
        for c in body.get("elements", []):
            if not c.get("slug") or not c.get("name"):
                continue
            courses.append({"id": c["id"], "name": c["name"], "slug": c["slug"], "workload": c.get("workload"),
                            "partners": [partners[p] for p in c.get("partnerIds", []) if p in partners],
                            "languages": c.get("primaryLanguages") or []})
        nxt = body.get("paging", {}).get("next")
        if not nxt:
            break
        start = int(nxt)
    if not courses:
        raise FetchError("parse", "Coursera answered without courses", API)
    return courses


def catalog(conn, http: Http | None = None) -> dict:
    """{"courses", "fetched_at", "cached"}. Raises FetchError only when Coursera can't be reached and nothing is
    cached."""
    _cache(conn)
    row = conn.execute("SELECT fetched_at, payload FROM course_cache WHERE provider = ?", (PROVIDER,)).fetchone()
    now = datetime.now(timezone.utc)
    if row and now - datetime.fromisoformat(row["fetched_at"]) < timedelta(days=CACHE_DAYS):
        return {"courses": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "cached": True}
    try:
        courses = _fetch(http or Http(timeout=30, retries=1))
    except FetchError:
        if row:     # stale beats nothing: the links still point at real courses
            return {"courses": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "cached": True}
        raise
    fetched = now.isoformat(timespec="seconds")
    conn.execute("INSERT INTO course_cache (provider, fetched_at, payload) VALUES (?, ?, ?) ON CONFLICT (provider) "
                 "DO UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload",
                 (PROVIDER, fetched, json.dumps(courses)))
    conn.commit()
    return {"courses": courses, "fetched_at": fetched, "cached": False}


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


STOP = {"and", "the", "for", "with", "of", "to", "in", "a", "an", "on", "your", "how", "using", "introduction", "intro"}


def search(cat: dict, queries: list[str], limit: int = 8) -> list[dict]:
    """Courses whose names best match any of `queries` (e.g. ["financial modelling", "excel financial model"]).
    Each query word scores by how rare it is in course names, so "modelling" counts for more than "data"; a name
    containing the whole phrase scores most. English courses only."""
    key = cat["fetched_at"]
    if key not in _index:
        _index.clear()
        courses = [c for c in cat["courses"] if not c["languages"] or "en" in c["languages"]]
        df: dict[str, int] = {}
        for c in courses:
            c["_words"] = set(_words(c["name"]))
            for w in c["_words"]:
                df[w] = df.get(w, 0) + 1
        _index[key] = (courses, df)
    courses, df = _index[key]
    n = len(courses) or 1

    best: dict[str, float] = {}
    for q in queries:
        words = [w for w in _words(q) if w not in STOP]
        if not words:
            continue
        phrase = " ".join(words)
        idf = {w: math.log(n / (1 + df.get(w, 0))) for w in words}
        for c in courses:
            hit = [w for w in words if w in c["_words"]]
            # most of the query has to be there: one common word alone isn't a match
            if len(hit) < max(1, math.ceil(len(words) * 0.6)):
                continue
            score = sum(idf[w] for w in hit) + (3 if phrase in " ".join(_words(c["name"])) else 0)
            best[c["id"]] = max(best.get(c["id"], 0), score)
    by_id = {c["id"]: c for c in courses}
    ranked = sorted(best, key=lambda i: (-best[i], len(by_id[i]["name"])))[:limit]
    return [public(by_id[i]) for i in ranked]


def public(c: dict) -> dict:
    """A course as the API returns it."""
    return {"id": c["id"], "title": c["name"], "provider": ", ".join(c["partners"][:2]) or PROVIDER,
            "platform": PROVIDER, "url": f"https://www.coursera.org/learn/{c['slug']}", "workload": c.get("workload")}
