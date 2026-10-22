"""GitHub (rung 1). Two modes, kept apart on purpose:

- backfill: number of new repos per topic per month. A repo's creation date never changes,
  so these counts are safe to use in historical snapshots.
- poll: the top recent repos per topic with their *current* star counts, recorded as
  timestamped observations. Star counts are never used for periods before they were observed.
"""

import os
from datetime import datetime, timedelta, timezone

from ..curated import Curated
from ..db import has_doc, record_metric, upsert_doc
from ..http import Http
from ..periods import available_at, month_of, months, period_end, period_start, utcnow

API = "https://api.github.com"


def client() -> Http:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # search API: 30 requests/min with a token, 10/min without
    return Http(min_interval=2.1 if token else 6.5, headers=headers)


def search_url(topic: str, period: str) -> str:
    return (f"https://github.com/search?type=repositories&q=topic%3A{topic}+created%3A"
            f"{period_start(period)}..{period_end(period)}")


def backfill(conn, cur: Curated, since: str, until: str, http: Http | None = None, force: bool = False) -> int:
    """Skips topic-months already fetched unless force=True, so an interrupted run can resume."""
    http = http or client()
    n = 0
    for period in months(since, until):
        for topic in cur.all_topics():
            if not force and has_doc(conn, f"ghc:{topic}:{period}"):
                continue
            data = http.get(f"{API}/search/repositories", {
                "q": f"topic:{topic} created:{period_start(period)}..{period_end(period)}",
                "per_page": 1,
            }).json()
            upsert_doc(conn, {
                "id": f"ghc:{topic}:{period}",
                "source": "github",
                "kind": "repo_count",
                "url": search_url(topic, period),
                "title": f"New repositories tagged '{topic}' in {period}",
                "text": "",
                "published_at": available_at(period),
                "period": period,
                "metrics": {"topic": topic, "count": data.get("total_count", 0)},
            })
            n += 1
            conn.commit()
    return n


def repo_doc(r: dict) -> dict:
    created = r["created_at"]
    return {
        "id": f"gh:{r['full_name']}",
        "source": "github",
        "kind": "repo",
        "url": r["html_url"],
        "title": r["full_name"],
        "text": r.get("description") or "",
        "topics": r.get("topics") or [],
        "published_at": created,
        "period": month_of(created),
        "metrics": {"stars": r.get("stargazers_count", 0), "language": r.get("language")},
    }


def poll(conn, cur: Curated, per_topic: int = 10, recent_days: int = 30, http: Http | None = None) -> list[str]:
    """Live: most-starred repos created in the last recent_days, per tracked topic. Returns new doc ids."""
    http = http or client()
    since = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date().isoformat()
    observed_at, new = utcnow(), []
    for topic in cur.all_topics():
        data = http.get(f"{API}/search/repositories", {
            "q": f"topic:{topic} created:>={since}", "sort": "stars", "order": "desc", "per_page": per_topic,
        }).json()
        for r in data.get("items", []):
            doc = repo_doc(r)
            if upsert_doc(conn, doc):
                new.append(doc["id"])
            record_metric(conn, doc["id"], "stars", r.get("stargazers_count", 0), observed_at)
        conn.commit()
    return new
