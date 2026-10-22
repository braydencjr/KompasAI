"""Hacker News: front-page buzz (rung 1) and "Who is hiring?" threads (rung 2, tech only).

Backfill uses the Algolia search API; the live loop uses the official Firebase API.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ..curated import Curated
from ..db import upsert_doc
from ..http import Http
from ..periods import iso, month_of, next_period_start, period_start

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<p>|<br\s*/?>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _ts(epoch: int) -> str:
    return iso(datetime.fromtimestamp(epoch, timezone.utc))


def story_doc(hit_id: str, title: str, url: str | None, text: str | None, created: str, points: int, comments: int) -> dict:
    return {
        "id": f"hn:{hit_id}",
        "source": "hn_front",
        "kind": "story",
        "url": url or f"https://news.ycombinator.com/item?id={hit_id}",
        "title": title,
        "text": clean_html(text),
        "published_at": created,
        "period": month_of(created),
        "metrics": {"points": points, "comments": comments, "hn_url": f"https://news.ycombinator.com/item?id={hit_id}"},
    }


def backfill_front(conn, cur: Curated, since: str, until: str, min_points: int = 100, http: Http | None = None) -> int:
    """Stories with at least min_points, fetched in one-week windows (Algolia caps a query at 1,000 hits)."""
    http = http or Http(min_interval=0.2)
    start = datetime.combine(period_start(since), datetime.min.time(), timezone.utc)
    end = datetime.combine(next_period_start(until), datetime.min.time(), timezone.utc)
    n = 0
    while start < end:
        stop = min(start + timedelta(days=7), end)
        page = 0
        while True:
            data = http.get(f"{ALGOLIA}/search_by_date", {
                "tags": "story",
                "numericFilters": f"created_at_i>={int(start.timestamp())},created_at_i<{int(stop.timestamp())},points>={min_points}",
                "hitsPerPage": 1000,
                "page": page,
            }).json()
            for h in data["hits"]:
                if not h.get("title"):
                    continue
                upsert_doc(conn, story_doc(h["objectID"], h["title"], h.get("url"), h.get("story_text"),
                                           _ts(h["created_at_i"]), h.get("points") or 0, h.get("num_comments") or 0))
                n += 1
            page += 1
            if page >= data.get("nbPages", 0):
                break
        conn.commit()
        start = stop
    return n


def hiring_threads(http: Http, since: str, until: str) -> list[dict]:
    lo = int(datetime.combine(period_start(since), datetime.min.time(), timezone.utc).timestamp())
    hi = int(datetime.combine(next_period_start(until), datetime.min.time(), timezone.utc).timestamp())
    data = http.get(f"{ALGOLIA}/search_by_date", {
        "tags": "story,author_whoishiring",
        "numericFilters": f"created_at_i>={lo},created_at_i<{hi}",
        "hitsPerPage": 100,
    }).json()
    return [h for h in data["hits"] if "who is hiring" in (h.get("title") or "").lower()]


def backfill_hiring(conn, cur: Curated, since: str, until: str, http: Http | None = None) -> int:
    """Top-level comments of each monthly "Ask HN: Who is hiring?" thread; one comment = one job post."""
    http = http or Http(min_interval=0.5)
    n = 0
    for thread in hiring_threads(http, since, until):
        item = http.get(f"{ALGOLIA}/items/{thread['objectID']}").json()
        period = month_of(_ts(thread["created_at_i"]))
        for c in item.get("children") or []:
            text = clean_html(c.get("text"))
            if not text or not c.get("created_at_i"):
                continue
            upsert_doc(conn, {
                "id": f"hnh:{c['id']}",
                "source": "hn_hiring",
                "kind": "hiring_post",
                "url": f"https://news.ycombinator.com/item?id={c['id']}",
                "title": text.split("\n", 1)[0][:200],
                "text": text,
                "published_at": _ts(c["created_at_i"]),
                "period": period,
                "metrics": {"thread_id": thread["objectID"]},
            })
            n += 1
        conn.commit()
    return n


def poll_front(conn, cur: Curated, limit: int = 60, http: Http | None = None) -> list[str]:
    """Live: current top stories from the official API. Returns ids of docs that are new."""
    http = http or Http()
    ids = http.get(f"{FIREBASE}/topstories.json").json()[:limit]
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(lambda i: http.get(f"{FIREBASE}/item/{i}.json").json(), ids))
    new = []
    for it in items:
        if not it or it.get("type") != "story" or not it.get("title") or it.get("dead") or it.get("deleted"):
            continue
        doc = story_doc(str(it["id"]), it["title"], it.get("url"), it.get("text"), _ts(it["time"]),
                        it.get("score") or 0, it.get("descendants") or 0)
        if upsert_doc(conn, doc):
            new.append(doc["id"])
    conn.commit()
    return new
