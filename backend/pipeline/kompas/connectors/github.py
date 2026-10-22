"""GitHub (rung 1). Two modes, kept apart on purpose:

- counts (backfill): number of new repos per topic per month. A repo's creation date never changes,
  so these counts can be used in historical snapshots. Each fetch is also kept as a timestamped
  observation, because a count can still drift (repos deleted or tagged later) and history shouldn't be
  overwritten by a re-fetch.
- poll (live): the top recent repos per topic with their *current* star counts, recorded as
  timestamped observations. Star counts are never used for periods before they were observed, and
  past star counts are never reconstructed from today's numbers.
"""

import os
from datetime import datetime, timedelta, timezone

from ..curated import Curated
from ..db import has_doc
from ..document import Document, utc, utc_or_none
from ..http import FetchError, Http
from ..ingest import Breaker, Options, Run, later, month_window
from ..periods import available_at, month_of, period_end, period_start, utcnow

API = "https://api.github.com"
REPO_FIELDS = ("id", "full_name", "html_url", "description", "topics", "language", "created_at", "updated_at",
               "pushed_at", "stargazers_count", "forks_count", "archived", "fork")


def client(run: Run | None = None) -> Http:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # search API: 30 requests/min with a token, 10/min without
    kwargs = dict(min_interval=2.1 if token else 6.5, headers=headers)
    return run.http(**kwargs) if run else Http(**kwargs)


def search_url(topic: str, period: str) -> str:
    return (f"https://github.com/search?type=repositories&q=topic%3A{topic}+created%3A"
            f"{period_start(period)}..{period_end(period)}")


def _count(http: Http, topic: str, period: str) -> dict:
    data = http.get_json(f"{API}/search/repositories", {
        "q": f"topic:{topic} created:{period_start(period)}..{period_end(period)}", "per_page": 1,
    })
    if not isinstance(data, dict) or not isinstance(data.get("total_count"), int):
        raise FetchError("parse", "search response has no total_count")
    return data


def ingest_counts(run: Run, cur: Curated, opts: Options, http: Http | None = None):
    """Monthly new-repo counts per tracked topic. Skips topic-months already stored (outside the overlap
    window), so an interrupted run resumes where it stopped."""
    http = http or client(run)
    breaker = Breaker(run)
    ms, refetch = month_window(run, opts)
    cp, blocked = run.checkpoint(), False
    for period in ms:
        ok = True
        for topic in cur.all_topics():
            doc_id = f"ghc:{topic}:{period}"
            if period not in refetch and has_doc(run.conn, doc_id):
                run.skip()
                continue
            try:
                data = _count(http, topic, period)
                if data.get("incomplete_results"):
                    data = _count(http, topic, period)   # GitHub timed out internally; ask once more
            except FetchError as e:
                breaker.failed(doc_id, e)
                ok = False
                continue
            breaker.ok()
            metrics = {"topic": topic, "count": data["total_count"]}
            if data.get("incomplete_results"):
                metrics["incomplete"] = True
                run.partial(f"{doc_id}: GitHub says the count may be incomplete")
            run.save(Document(
                id=doc_id, source="github", kind="repo_count", source_id=f"{topic}:{period}",
                url=search_url(topic, period), title=f"New repositories tagged '{topic}' in {period}", text="",
                published_at=available_at(period), period=period, metrics=metrics,
                raw_payload={"total_count": data["total_count"], "incomplete_results": data.get("incomplete_results")},
            ))
            run.observe(doc_id, "count", data["total_count"])
            run.commit()
        blocked |= not ok
        if not blocked:
            cp = later(cp, period)
            run.commit(cursor=cp)


def repo_doc(r: dict) -> Document:
    created = utc(r["created_at"])
    return Document(
        id=f"gh:{r['full_name']}", source="github", kind="repo", source_id=str(r.get("id") or r["full_name"]),
        url=r["html_url"], title=r["full_name"], text=r.get("description") or "", topics=r.get("topics") or [],
        published_at=created, updated_at=utc_or_none(r.get("updated_at")), period=month_of(created),
        metrics={"stars": r.get("stargazers_count", 0), "language": r.get("language")},
        # the owner object (logins, avatars, URLs) isn't needed, so it isn't kept
        raw_payload={k: r.get(k) for k in REPO_FIELDS},
    )


def poll(run: Run, cur: Curated, per_topic: int = 10, recent_days: int = 30, http: Http | None = None) -> list[str]:
    """Live: most-starred repos created in the last recent_days, per tracked topic. Returns new doc ids."""
    http = http or client(run)
    breaker = Breaker(run)
    since = (datetime.now(timezone.utc) - timedelta(days=recent_days)).date().isoformat()
    observed_at, new = utcnow(), []
    for topic in cur.all_topics():
        try:
            data = http.get_json(f"{API}/search/repositories", {
                "q": f"topic:{topic} created:>={since}", "sort": "stars", "order": "desc", "per_page": per_topic,
            })
        except FetchError as e:
            breaker.failed(f"topic:{topic}", e)
            continue
        breaker.ok()
        if data.get("incomplete_results"):
            run.partial(f"topic:{topic}: GitHub says the search results may be incomplete")
        for r in data.get("items") or []:
            try:
                doc = repo_doc(r)
            except (KeyError, ValueError) as e:
                run.fail(f"gh:{r.get('full_name')}", "parse", f"bad repository record: {e}")
                continue
            result = run.save(doc)
            if result == "failed":
                continue
            if result == "inserted":
                new.append(doc.id)
            run.observe(doc.id, "stars", r.get("stargazers_count", 0), observed_at)
        run.commit()
    return new
