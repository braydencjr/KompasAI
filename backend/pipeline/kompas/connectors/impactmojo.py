"""ImpactMojo (impactmojo.in): free, open development-education courses, read live from its public API for the
learning steps of The Route. No key is needed. The course list is cached for a day (course_cache table); when the
API can't be reached, the last cached copy is used.

Each course is matched to skills with the same Tagger the pipeline uses, over its title, tags and description.
Acronym-only matches are ignored: in development writing "DBT" is Direct Benefit Transfer and "ML" is often not
machine learning. Content is CC BY-NC-ND 4.0, so Kompas only links out to each course and credits ImpactMojo.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from ..curated import Curated, Resource
from ..http import FetchError, Http
from ..tag import Tagger

API = "https://www.impactmojo.in/api/v1/courses"
CACHE_HOURS = 24
PROVIDER = "ImpactMojo"

_matched: dict[tuple, dict[str, list[Resource]]] = {}   # (fetched_at, curated version) -> skill -> courses


def enabled() -> bool:
    """On unless KOMPAS_IMPACTMOJO=0 (tests and offline demos)."""
    return os.environ.get("KOMPAS_IMPACTMOJO", "1") != "0"


def _cache(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS course_cache (provider TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, "
                 "payload TEXT NOT NULL)")


def courses(conn, http: Http | None = None) -> dict:
    """The course list: {"courses", "fetched_at", "cached"}. Raises FetchError only when the API can't be reached
    and nothing is cached."""
    _cache(conn)
    row = conn.execute("SELECT fetched_at, payload FROM course_cache WHERE provider = ?", (PROVIDER,)).fetchone()
    now = datetime.now(timezone.utc)
    if row and now - datetime.fromisoformat(row["fetched_at"]) < timedelta(hours=CACHE_HOURS):
        return {"courses": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "cached": True}
    try:
        body = (http or Http(timeout=10, retries=1)).get_json(API)
    except FetchError:
        if row:     # stale beats nothing: the links still point at real courses
            return {"courses": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "cached": True}
        raise
    items = body.get("courses") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise FetchError("parse", "ImpactMojo answered without a course list", API)
    fetched = now.isoformat(timespec="seconds")
    conn.execute("INSERT INTO course_cache (provider, fetched_at, payload) VALUES (?, ?, ?) ON CONFLICT (provider) "
                 "DO UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload",
                 (PROVIDER, fetched, json.dumps(items)))
    conn.commit()
    return {"courses": items, "fetched_at": fetched, "cached": False}


def _hours(c: dict) -> float:
    """The API gives no duration: a flagship course is taken as 8 h, a 101 deck as about 3 h per 100 slides."""
    if c.get("tier") == "flagship":
        return 8.0
    return max(1.0, round((c.get("slides") or 100) / 33))


def _acronym(span: str) -> bool:
    return span.isupper() and len(span) <= 4


def match(cur: Curated, items: list[dict], checked: str, tagger: Tagger | None = None) -> dict[str, list[Resource]]:
    """skill -> ImpactMojo courses that teach it. Practice workbooks are left out: they repeat their course."""
    tagger = tagger or Tagger(cur)
    out: dict[str, list[Resource]] = {}
    for c in items:
        url, title = c.get("url") or "", c.get("title") or ""
        if not url.startswith("https://") or not title or "Practice Workbook" in title:
            continue
        text = "\n".join([title, " ".join(c.get("tags") or []), c.get("description") or ""])
        skills = {cid for cid, _, span, _ in tagger.find_all(text)
                  if cur.concepts[cid].kind == "skill" and not _acronym(span)}
        for cid in sorted(skills):
            if all(r.url != url for r in out.get(cid, [])):
                out.setdefault(cid, []).append(Resource(cid, title, PROVIDER, url, _hours(c), "free", "en", False, checked))
    return out


def resources(cur: Curated, conn, http: Http | None = None) -> dict[str, list[Resource]]:
    """skill -> live ImpactMojo courses; empty when switched off. Raises FetchError as courses() does."""
    if not enabled():
        return {}
    found = courses(conn, http)
    key = (found["fetched_at"], cur.version)
    if key not in _matched:
        _matched.clear()
        _matched[key] = match(cur, found["courses"], found["fetched_at"][:10])
    return _matched[key]
