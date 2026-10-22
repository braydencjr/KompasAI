"""Hacker News: front-page buzz (rung 1) and "Who is hiring?" threads (rung 2, tech only).

Backfill uses the Algolia search API; the live loop uses the official Firebase API.

Documents:
- hn:<item id>    a story with 100+ points (points are refreshed while the story is in the overlap window)
- hnh:<item id>   one top-level comment in a monthly hiring thread = one job post. Email addresses are
                  replaced with "[email]"; commenters' usernames aren't kept.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .. import config
from ..curated import Curated
from ..document import Document, redact_emails, utc
from ..http import FetchError, Http
from ..ingest import Breaker, Options, Run, later, month_window
from ..periods import iso, month_of, next_period_start, parse, period_start, last_complete_months

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"
ALGOLIA_CAP = 1000            # Algolia never returns more than this many hits for one query
MIN_WINDOW = timedelta(hours=1)


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<p>|<br\s*/?>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def story_doc(hit_id: str, title: str, url: str | None, text: str | None, created: int, points: int,
              comments: int) -> Document:
    published = utc(created)
    hn_url = f"https://news.ycombinator.com/item?id={hit_id}"
    return Document(
        id=f"hn:{hit_id}", source="hn_front", kind="story", source_id=str(hit_id), url=url or hn_url, title=title,
        text=clean_html(text), published_at=published, period=month_of(published),
        metrics={"points": points, "comments": comments, "hn_url": hn_url},
        raw_payload={"id": str(hit_id), "title": title, "url": url, "text": text, "created_at_i": created,
                     "points": points, "num_comments": comments},
    )


# ---------- front page (backfill) ----------


def _front_window(run: Run, http: Http, breaker: Breaker, start: datetime, stop: datetime, min_points: int) -> bool:
    """Fetches every story in [start, stop). Splits the window when it holds more than Algolia will return.
    Returns False if anything in the window couldn't be fetched."""
    def page(n: int) -> dict:
        return http.get_json(f"{ALGOLIA}/search_by_date", {
            "tags": "story",
            "numericFilters": f"created_at_i>={int(start.timestamp())},created_at_i<{int(stop.timestamp())},"
                              f"points>={min_points}",
            "hitsPerPage": ALGOLIA_CAP, "page": n,
        })

    ref = f"hn_front:{iso(start)}..{iso(stop)}"
    try:
        data = page(0)
    except FetchError as e:
        breaker.failed(ref, e)
        return False
    breaker.ok()
    if not isinstance(data.get("hits"), list) or not isinstance(data.get("nbHits"), int):
        run.fail(ref, "parse", "Algolia response has no hits/nbHits")
        return False
    if data["nbHits"] > ALGOLIA_CAP and stop - start > MIN_WINDOW:
        mid = start + (stop - start) / 2
        return (_front_window(run, http, breaker, start, mid, min_points)
                & _front_window(run, http, breaker, mid, stop, min_points))
    seen, n = 0, 0
    while True:
        for h in data["hits"]:
            seen += 1
            if not h.get("title"):
                run.skip()
                continue
            try:
                doc = story_doc(h["objectID"], h["title"], h.get("url"), h.get("story_text"), h["created_at_i"],
                                h.get("points") or 0, h.get("num_comments") or 0)
            except (KeyError, ValueError) as e:
                run.fail(f"hn:{h.get('objectID')}", "parse", f"bad story record: {e}")
                continue
            run.save(doc)
        n += 1
        if n >= data.get("nbPages", 0):
            break
        try:
            data = page(n)
        except FetchError as e:
            breaker.failed(ref, e)
            return False
    if seen < min(data["nbHits"], ALGOLIA_CAP):
        run.partial(f"{ref}: Algolia reported {data['nbHits']} stories but returned {seen}")
        return False
    if data["nbHits"] > ALGOLIA_CAP:
        run.partial(f"{ref}: more than {ALGOLIA_CAP} stories in one hour; only the first {ALGOLIA_CAP} were returned")
        return False
    return True


def ingest_front(run: Run, cur: Curated, opts: Options, min_points: int | None = None, http: Http | None = None):
    """Stories with at least min_points, fetched in one-week windows. The checkpoint is the end of the last
    fully fetched window; incremental runs start HN_OVERLAP_DAYS before it so points can settle."""
    http = http or run.http(min_interval=0.2)
    breaker = Breaker(run)
    min_points = min_points or config.PARAMS.hn_min_points
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cp = run.checkpoint()
    if opts.since and opts.until:
        start = datetime.combine(period_start(opts.since), datetime.min.time(), timezone.utc)
        end = min(datetime.combine(next_period_start(opts.until), datetime.min.time(), timezone.utc), today)
    elif cp:
        start, end = parse(cp) - timedelta(days=config.HN_OVERLAP_DAYS), today
    else:
        start, end = datetime.combine(period_start(last_complete_months(opts.months)[0]), datetime.min.time(),
                                      timezone.utc), today
    blocked = False
    while start < end:
        stop = min(start + timedelta(days=7), end)
        blocked |= not _front_window(run, http, breaker, start, stop, min_points)
        if blocked:
            run.commit()
        else:
            cp = later(cp, iso(stop))
            run.commit(cursor=cp)
        start = stop


# ---------- hiring threads ----------


def hiring_threads(http: Http, since: str, until: str) -> list[dict]:
    lo = int(datetime.combine(period_start(since), datetime.min.time(), timezone.utc).timestamp())
    hi = int(datetime.combine(next_period_start(until), datetime.min.time(), timezone.utc).timestamp())
    data = http.get_json(f"{ALGOLIA}/search_by_date", {
        "tags": "story,author_whoishiring",
        "numericFilters": f"created_at_i>={lo},created_at_i<{hi}",
        "hitsPerPage": 100,
    })
    if not isinstance(data.get("hits"), list):
        raise FetchError("parse", "Algolia response has no hits")
    threads = [h for h in data["hits"] if "who is hiring" in (h.get("title") or "").lower()]
    return sorted(threads, key=lambda h: h["created_at_i"])


def hiring_doc(c: dict, thread_id: str, period: str) -> Document:
    text = redact_emails(clean_html(c.get("text")))
    published = utc(c["created_at_i"])
    return Document(
        id=f"hnh:{c['id']}", source="hn_hiring", kind="hiring_post", source_id=str(c["id"]),
        url=f"https://news.ycombinator.com/item?id={c['id']}", title=text.split("\n", 1)[0][:200], text=text,
        published_at=published, period=period,
        metrics={"thread_id": thread_id, "parent_id": str(c.get("parent_id") or thread_id)},
        raw_payload={"id": c["id"], "parent_id": c.get("parent_id"), "created_at_i": c["created_at_i"], "text": text},
    )


def ingest_hiring(run: Run, cur: Curated, opts: Options, http: Http | None = None):
    """Top-level comments of each monthly "Ask HN: Who is hiring?" thread; one comment = one job post.

    The checkpoint is the last month whose thread was fetched once it had stopped getting posts
    (HN_THREAD_FINAL_DAYS old). Younger threads are fetched again on the next run."""
    http = http or run.http(min_interval=0.5)
    breaker = Breaker(run)
    ms, refetch = month_window(run, opts)
    cp, blocked = run.checkpoint(), False
    threads = {}
    for t in hiring_threads(http, ms[0], ms[-1]):
        threads.setdefault(month_of(utc(t["created_at_i"])), t)
    now = datetime.now(timezone.utc)
    for period in ms:
        thread = threads.get(period)
        if thread is None:
            run.partial(f"no 'Who is hiring?' thread found for {period}")
            blocked = True
            continue
        if cp and period <= cp and period not in refetch:
            run.skip()
            continue
        try:
            item = http.get_json(f"{ALGOLIA}/items/{thread['objectID']}")
        except FetchError as e:
            breaker.failed(f"thread:{thread['objectID']}", e)
            blocked = True
            continue
        breaker.ok()
        for c in item.get("children") or []:
            if not c.get("text") or not c.get("created_at_i"):
                run.skip()   # deleted, dead or empty comments
                continue
            try:
                doc = hiring_doc(c, thread["objectID"], period)
            except (KeyError, ValueError) as e:
                run.fail(f"hnh:{c.get('id')}", "parse", f"bad comment record: {e}")
                continue
            run.save(doc)
        final = now - datetime.fromtimestamp(thread["created_at_i"], timezone.utc) >= timedelta(
            days=config.HN_THREAD_FINAL_DAYS)
        blocked |= not final
        if blocked:
            run.commit()
        else:
            cp = later(cp, period)
            run.commit(cursor=cp)


# ---------- live ----------


def poll_front(run: Run, cur: Curated, limit: int = 60, http: Http | None = None) -> list[str]:
    """Live: current top stories from the official API. Returns ids of docs that are new. One unreadable
    item doesn't stop the poll; it's recorded as a failed record."""
    http = http or run.http()
    ids = http.get_json(f"{FIREBASE}/topstories.json")
    if not isinstance(ids, list):
        raise FetchError("parse", "topstories is not a list")

    def fetch(item_id):
        try:
            return item_id, http.get_json(f"{FIREBASE}/item/{item_id}.json"), None
        except FetchError as e:
            return item_id, None, e

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, ids[:limit]))
    new = []
    for item_id, it, err in results:
        if err:
            run.fail(f"hn:{item_id}", err.category, str(err))
            continue
        if not it or it.get("type") != "story" or not it.get("title") or it.get("dead") or it.get("deleted"):
            run.skip()
            continue
        try:
            doc = story_doc(str(it["id"]), it["title"], it.get("url"), it.get("text"), it["time"],
                            it.get("score") or 0, it.get("descendants") or 0)
        except (KeyError, ValueError) as e:
            run.fail(f"hn:{item_id}", "parse", f"bad item: {e}")
            continue
        result = run.save(doc)
        if result == "failed":
            continue
        if result == "inserted":
            new.append(doc.id)
        run.observe(doc.id, "points", it.get("score") or 0)
    return new
