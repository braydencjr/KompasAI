"""JSearch (OpenWeb Ninja; also sold through RapidAPI): live job postings from Google for Jobs, which gathers them from
JobStreet, LinkedIn, Indeed and employers' own sites. Used for a role's "Open jobs" panel: real postings, each linking
to the original, so nothing about a job is invented.

The free plan allows 200 requests a month, so each search is cached for a day (job_cache table). Without a key
(JSEARCH_API_KEY in backend/.env) the panel falls back to links that search the job boards directly. A key from
app.openwebninja.com works directly; one from RapidAPI works through its gateway (tried second).
"""

import json
import os
from datetime import datetime, timedelta, timezone

from ..http import FetchError, Http

# (url, headers for a key): OpenWeb Ninja first, then RapidAPI's gateway
PROVIDERS = (
    ("https://api.openwebninja.com/jsearch/search-v2", lambda key: {"x-api-key": key}),
    ("https://jsearch.p.rapidapi.com/search", lambda key: {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}),
)
CACHE_HOURS = 24
SOURCE = "Google for Jobs, via JSearch"


def available() -> bool:
    return bool(os.environ.get("JSEARCH_API_KEY"))


def _cache(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS job_cache (query TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, payload TEXT NOT NULL)")


def _job(j: dict) -> dict:
    """One posting, in the fields the panel shows. JSearch has renamed some fields over time: read either."""
    place = j.get("job_location") or ", ".join(x for x in (j.get("job_city"), j.get("job_state")) if x) or j.get("job_country") or ""
    low, high, cur = j.get("job_min_salary"), j.get("job_max_salary"), j.get("job_salary_currency")
    salary = j.get("job_salary_string") or None
    if not salary and (low or high):
        span = f"{low:,.0f}–{high:,.0f}" if low and high else f"{(low or high):,.0f}"
        salary = f"{cur or ''} {span}{' / ' + j['job_salary_period'].lower() if j.get('job_salary_period') else ''}".strip()
    return {
        "id": j.get("job_id"),
        "title": j.get("job_title") or "",
        "employer": j.get("employer_name") or "",
        "location": place,
        "remote": bool(j.get("job_is_remote")),
        "type": j.get("job_employment_type"),
        "posted": (j.get("job_posted_at_datetime_utc") or "")[:10] or None,
        "url": j.get("job_apply_link") or j.get("job_google_link"),
        "via": j.get("job_publisher"),
        "salary": salary,
        "description": (j.get("job_description") or "")[:4000],
    }


def search(conn, query: str, country: str = "my", http: Http | None = None) -> dict:
    """Postings for `query` in `country` from the last month: {"jobs", "fetched_at", "source", "cached"}. Raises
    FetchError when the API can't be reached; returns no jobs without a key."""
    if not available():
        return {"jobs": [], "fetched_at": None, "source": SOURCE, "cached": False, "note": "no JSearch API key configured"}
    _cache(conn)
    key = f"{country}|{query.lower()}"
    row = conn.execute("SELECT fetched_at, payload FROM job_cache WHERE query = ?", (key,)).fetchone()
    now = datetime.now(timezone.utc)
    if row and now - datetime.fromisoformat(row["fetched_at"]) < timedelta(hours=CACHE_HOURS):
        return {"jobs": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "source": SOURCE, "cached": True}
    params = {"query": f"{query} in Malaysia" if country == "my" else query, "country": country, "num_pages": 1,
              "date_posted": "month"}
    body, error = None, None
    for url, headers in PROVIDERS:
        try:
            body = (http or Http(headers=headers(os.environ["JSEARCH_API_KEY"]), timeout=25)).get_json(url, params)
            break
        except FetchError as e:     # a key from one provider is refused by the other: try the next
            error = e
    if body is None:
        raise error or FetchError("api", "JSearch could not be reached")
    if body.get("status") not in (None, "OK"):
        raise FetchError("api", f"JSearch answered {body.get('status')}: {body.get('error') or body.get('message')}")
    data = body.get("data") or []
    jobs = [_job(j) for j in (data.get("jobs", []) if isinstance(data, dict) else data)]
    fetched = now.isoformat(timespec="seconds")
    conn.execute("INSERT INTO job_cache (query, fetched_at, payload) VALUES (?, ?, ?) ON CONFLICT (query) DO UPDATE SET "
                 "fetched_at = excluded.fetched_at, payload = excluded.payload", (key, fetched, json.dumps(jobs)))
    conn.commit()
    return {"jobs": jobs, "fetched_at": fetched, "source": SOURCE, "cached": False}
