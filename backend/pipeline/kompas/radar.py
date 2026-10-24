"""Radar: what is moving right now, straight from the raw records.

- repos: GitHub's Trending page (connectors/github_trending.py), grouped into categories, ranked by the stars
  each repository gained today or this week. The LLM reads each repository once (category, a plain-words line
  for non-programmers, the Kompas skill it relates to); rank changes compare with the previous scrape.
- keywords: open vocabulary. Words and word pairs from Hacker News titles, repo descriptions and repo topics,
  ranked by how much more often they appear in the last week than the earlier baseline would predict. There is
  no list of allowed terms; a term that matches a Kompas concept just gets linked to it.
- discussions: Hacker News stories ranked by points per hour.

Everything is measured against the newest data we hold (`as_of`), not the wall clock, so a paused poller shows
old but honest numbers instead of an empty page.
"""

import functools
import json
import logging
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import timedelta

from . import db, llm
from .connectors import github_trending, my_news
from .curated import Curated
from .periods import iso, parse, utcnow

log = logging.getLogger("kompas.radar")

CACHE_SECONDS = 30   # every open Radar page asks for the same numbers; computing them takes about a second
TRENDING_TTL = 3600   # GitHub updates Trending through the day; once an hour is plenty
DESCRIBE_BATCH = 30
OTHER = "Other"
MIN_NEW_CATEGORY = 3  # a category the LLM proposed becomes a tab once this many repositories are in it
RECENT_DAYS = 7
BASELINE_DAYS = 90
MIN_MENTIONS = 4
REPO_MIN_STARS = 20

STOP = set("""
a about above after again all also am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers him his how
i if in into is it its just like make me more most my new no nor not now of off on once one only or other our out
over own same she should so some such than that the their them then there these they this those through to too
under until up use used using very was we were what when where which while who why will with would you your
show hn ask tell launch why how what vs via per get got gets use uses open source free best top first last
pdf video blog post article github com org www http https html
years year critical data research meta people time way things work world system systems based license mit
""".split())
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:[.\-][A-Za-z0-9+#]+)*")


def _cached(fn):
    """Per-process cache of the last result for each (function, arguments), good for CACHE_SECONDS."""
    store: dict = {}

    @functools.wraps(fn)
    def wrapper(conn, cur, *args):
        hit = store.get(args)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        result = fn(conn, cur, *args)
        store[args] = (time.monotonic(), result)
        return result

    return wrapper


def _terms(text: str) -> set[str]:
    """Single words and adjacent word pairs (stop words break a pair)."""
    out, run = set(), []
    for tok in TOKEN.findall(text):
        low = tok.lower()
        if low in STOP or len(low) < 2:
            run = []
            continue
        out.add(low)
        run.append(low)
        if len(run) >= 2:
            out.add(f"{run[-2]} {run[-1]}")
        run = run[-1:]
    return out


def _topic_terms(topics: list[str]) -> set[str]:
    out = set()
    for t in topics:
        low = t.lower()
        if len(low) > 1 and not set(low.split("-")) & STOP:
            out.add(low.replace("-", " ") if low.count("-") == 1 else low)
    return out


def _as_of(conn, sql: str) -> str | None:
    row = conn.execute(sql).fetchone()
    return row[0] if row and row[0] else None


# ---------- repos ----------

_refreshing = threading.Lock()


def _describe(conn, cur: Curated, repos: list[dict]):
    """LLM reading for repositories that don't have one yet. A failure leaves them for the next scrape."""
    known = {r["full_name"] for r in conn.execute("SELECT full_name FROM repo_category")}
    todo = [{"full_name": r["full_name"], "description": r["description"], "language": r["language"]}
            for r in repos if r["full_name"] not in known]
    names = {r["full_name"] for r in todo}
    for i in range(0, len(todo), DESCRIBE_BATCH):
        out, error = llm.describe_repos(todo[i:i + DESCRIBE_BATCH], cur)
        if error:
            log.warning("describing trending repos failed: %s", error)
            return
        now = utcnow()
        for d in out:
            if d["full_name"] not in names:
                continue   # the model may only describe what it was given
            conn.execute("INSERT INTO repo_category (full_name, category, plain, skill_id, model, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (full_name) DO NOTHING",
                         (d["full_name"], d["category"].strip() or OTHER, d["plain"].strip(),
                          None if d["skill_id"] == llm.NONE else d["skill_id"], llm.MODEL, now))
        conn.commit()


def refresh_trending(conn, cur: Curated) -> dict:
    """Scrapes both periods and describes new repositories. Returns {since: repositories stored}."""
    stored = {}
    for since in github_trending.SINCE:
        repos, failed = github_trending.fetch(since)
        if failed:
            log.warning("trending %s: %d page(s) failed: %s", since, len(failed), ", ".join(failed))
        if not repos:
            stored[since] = 0
            continue
        now = utcnow()
        for r in repos:
            conn.execute("INSERT INTO trending_repo (scraped_at, since, full_name, description, language, stars, "
                         "forks, period_stars) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (now, since, r["full_name"], r["description"], r["language"], r["stars"], r["forks"],
                          r["period_stars"]))
        conn.commit()
        _describe(conn, cur, repos)
        stored[since] = len(repos)
    refresh_news(conn)
    describe_pending(conn, cur)   # headlines for the stories the hourly job just fetched
    return stored


def latest_scrape(conn) -> str | None:
    row = conn.execute("SELECT MAX(scraped_at) FROM trending_repo").fetchone()
    return row[0] if row and row[0] else None


def refresh_if_stale(cur: Curated, max_age: float = TRENDING_TTL) -> bool:
    """For the hourly job: scrapes unless a scrape newer than max_age seconds exists or one is running.
    Returns whether it scraped."""
    conn = db.connect()
    try:
        last = latest_scrape(conn)
        if last and (parse(utcnow()) - parse(last)).total_seconds() < max_age - 60:
            return False
        if not _refreshing.acquire(blocking=False):
            return False
        try:
            refresh_trending(conn, cur)
            return True
        finally:
            _refreshing.release()
    finally:
        conn.close()


def _refresh_in_background(cur: Curated):
    if not _refreshing.acquire(blocking=False):
        return   # one is already running

    def run():
        conn = db.connect()
        try:
            refresh_trending(conn, cur)
        except Exception:
            log.exception("trending refresh failed; serving the last good scrape")
        finally:
            conn.close()
            _refreshing.release()

    threading.Thread(target=run, daemon=True).start()


def _scrapes(conn, since: str) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT scraped_at FROM trending_repo WHERE since = ? "
                                       "ORDER BY scraped_at DESC LIMIT 2", (since,))]


def _ranked(rows, described: dict) -> list[dict]:
    """Rows of one scrape with category and rank within it; categories the LLM proposed that are still rare go
    to Other."""
    items = []
    for r in sorted(rows, key=lambda r: r["period_stars"], reverse=True):
        d = described.get(r["full_name"])
        items.append({**dict(r), "category": d["category"] if d else OTHER, "plain": d["plain"] if d else None,
                      "skill_id": d["skill_id"] if d else None})
    sizes: dict[str, int] = defaultdict(int)
    for i in items:
        sizes[i["category"]] += 1
    seen: dict[str, int] = defaultdict(int)
    for n, i in enumerate(items):
        if i["category"] not in llm.REPO_CATEGORIES and sizes[i["category"]] < MIN_NEW_CATEGORY:
            i["category"] = OTHER
        seen[i["category"]] += 1
        i["rank"], i["category_rank"] = n + 1, seen[i["category"]]
    return items


@_cached
def repos(conn, cur: Curated, since: str = "daily") -> dict:
    scrapes = _scrapes(conn, since)
    if not scrapes:
        if _refreshing.acquire(timeout=60):    # first run: wait for the scrape instead of showing nothing
            try:
                if not _scrapes(conn, since):
                    refresh_trending(conn, cur)
            finally:
                _refreshing.release()
        scrapes = _scrapes(conn, since)
        if not scrapes:
            return {"as_of": None, "since": since, "categories": [], "items": []}
    elif (parse(utcnow()) - parse(scrapes[0])).total_seconds() > TRENDING_TTL:
        _refresh_in_background(cur)
    described = {r["full_name"]: r for r in conn.execute("SELECT * FROM repo_category")}
    rows = lambda at: conn.execute("SELECT * FROM trending_repo WHERE since = ? AND scraped_at = ?",
                                   (since, at)).fetchall()
    items = _ranked(rows(scrapes[0]), described)
    before = {i["full_name"]: i for i in _ranked(rows(scrapes[1]), described)} if len(scrapes) > 1 else {}
    for i in items:
        was = before.get(i["full_name"])
        # same category then and now, or the comparison means nothing
        i["prev_category_rank"] = was["category_rank"] if was and was["category"] == i["category"] else None
        i["url"] = f"https://github.com/{i['full_name']}"
        c = cur.concepts.get(i.pop("skill_id") or "")
        i["skill"] = {"id": c.id, "label": c.label} if c else None
        i.pop("scraped_at", None)
    order = [c for c in (*llm.REPO_CATEGORIES, *sorted({i["category"] for i in items})) if c != OTHER] + [OTHER]
    counts = {c: sum(1 for i in items if i["category"] == c) for c in dict.fromkeys(order)}
    return {"as_of": scrapes[0], "since": since, "compared_to": scrapes[1] if len(scrapes) > 1 else None,
            "categories": [{"label": c, "count": n} for c, n in counts.items() if n],
            "items": items}


# ---------- keywords + discussions ----------


def _stories(conn, since: str, until: str) -> list[dict]:
    out = []
    for r in conn.execute("SELECT id, title, url, published_at, metrics FROM raw_doc WHERE source = 'hn_front' "
                          "AND kind = 'story' AND published_at >= ? AND published_at <= ?", (since, until)):
        m = json.loads(r["metrics"])
        out.append({"id": r["id"], "title": r["title"], "url": r["url"], "published_at": r["published_at"],
                    "points": m.get("points") or 0, "comments": m.get("comments") or 0,
                    "hn_url": m.get("hn_url") or r["url"]})
    return out


def _repo_docs(conn, since: str, until: str) -> list[dict]:
    return [{"id": r["id"], "title": r["title"], "url": r["url"], "published_at": r["published_at"],
             "text": f"{r['text'] or ''}", "topics": json.loads(r["topics"])}
            for r in conn.execute("SELECT id, title, url, text, topics, published_at FROM raw_doc WHERE kind = 'repo' "
                                  "AND published_at >= ? AND published_at <= ?", (since, until))]


@_cached
def keywords(conn, cur: Curated, limit: int = 20) -> dict:
    as_of = _as_of(conn, "SELECT MAX(published_at) FROM raw_doc WHERE source = 'hn_front'")
    if not as_of:
        return {"as_of": None, "items": []}
    end = parse(as_of)
    recent_from = iso(end - timedelta(days=RECENT_DAYS))
    base_from = iso(end - timedelta(days=BASELINE_DAYS))
    groups = {
        "hn": (_stories(conn, base_from, as_of), lambda d: _terms(d["title"])),
        "gh": (_repo_docs(conn, base_from, as_of), lambda d: _terms(d["text"]) | _topic_terms(d["topics"])),
    }
    # per source group, so a week with more repos than usual doesn't make repo words look "trending"
    recent, base, totals = Counter(), Counter(), {}
    per_term_recent: dict[str, Counter] = defaultdict(Counter)
    daily: dict[str, Counter] = defaultdict(Counter)
    evidence: dict[str, list[dict]] = defaultdict(list)
    scores: dict[str, float] = defaultdict(float)
    for g, (docs, extract) in groups.items():
        r_docs = [d for d in docs if d["published_at"] >= recent_from]
        b_docs = [d for d in docs if d["published_at"] < recent_from]
        totals[g] = (len(r_docs), len(b_docs))
        b_count = Counter(t for d in b_docs for t in extract(d))
        r_count = Counter()
        for d in r_docs:
            for t in extract(d):
                r_count[t] += 1
                daily[t][d["published_at"][:10]] += 1
                evidence[t].append(d)
        for t, n in r_count.items():
            per_term_recent[t][g] = n
            if n < MIN_MENTIONS or not b_docs:
                continue
            expected = b_count[t] / len(b_docs) * len(r_docs)
            scores[t] = max(scores[t], n / (expected + 1.0))
            recent[t] += n
            base[t] += b_count[t]
    ranked = sorted((t for t in scores if scores[t] > 1.3), key=lambda t: (scores[t], recent[t]), reverse=True)
    # drop a single word when a pair containing it accounts for most of its mentions
    keep = []
    for t in ranked:
        if " " not in t and any(" " in k and t in k.split() and recent[k] >= 0.7 * recent[t] for k in ranked):
            continue
        keep.append(t)
    labels = {c.label.lower(): cid for cid, c in cur.concepts.items()}
    days = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(RECENT_DAYS - 1, -1, -1)]
    items = []
    for t in keep[:limit]:
        best = sorted(evidence[t], key=lambda d: d.get("points", 0), reverse=True)[:2]
        items.append({
            "term": t, "mentions": recent[t], "baseline": base[t], "score": round(scores[t], 2),
            "change": round((scores[t] - 1) * 100), "new": base[t] == 0,
            "spark": [daily[t][d] for d in days], "concept_id": labels.get(t),
            "evidence": [{"title": d["title"], "url": d.get("hn_url") or d["url"]} for d in best],
        })
    return {"as_of": as_of, "window_days": RECENT_DAYS, "docs": {g: totals[g][0] for g in totals}, "items": items}


@_cached
def discussions(conn, cur: Curated, limit: int = 20) -> dict:
    as_of = _as_of(conn, "SELECT MAX(published_at) FROM raw_doc WHERE source = 'hn_front'")
    if not as_of:
        return {"as_of": None, "items": []}
    end = parse(as_of)
    stories = _stories(conn, iso(end - timedelta(days=3)), as_of)
    for s in stories:
        age_h = max((end - parse(s["published_at"])).total_seconds() / 3600, 0)
        s["points_per_hour"] = round(s["points"] / (age_h + 2), 1)
    stories.sort(key=lambda s: s["points_per_hour"], reverse=True)
    top = stories[:limit]
    trending = [k["term"] for k in keywords(conn, cur, 40)["items"]]
    for s in top:
        terms = _terms(s["title"])
        s["keywords"] = [t for t in trending if t in terms][:3]
    return {"as_of": as_of, "items": top}


# ---------- news from Malaysian outlets, Malaysian subreddits and Hacker News ----------

# days of each source's newest data that count as news; Hacker News has a longer window while its poller is paused
NEWS_DAYS = {"my_news": 1, "reddit": 1, "hn_front": 3}
NEWS_SOURCES = tuple(NEWS_DAYS)


def refresh_news(conn) -> dict[str, int]:
    """Fetches the Malaysian news feeds and subreddits and stores what they return. Hacker News has its own poller."""
    counts: dict[str, int] = defaultdict(int)
    for doc in my_news.fetch_news() + my_news.fetch_reddit():
        try:
            db.save_doc(conn, doc)
            counts[doc.source] += 1
        except ValueError as e:
            log.warning("skipped %s: %s", doc.id, e)
    conn.commit()
    return dict(counts)


def _news(conn) -> list[dict]:
    """Every source's stories from its last NEWS_DAYS of data (a source whose fetching paused keeps its last
    stories instead of disappearing), in one shape."""
    out = []
    for source in NEWS_SOURCES:
        latest = _as_of(conn, f"SELECT MAX(published_at) FROM raw_doc WHERE source = '{source}'")
        if not latest:
            continue
        since = iso(parse(latest) - timedelta(days=NEWS_DAYS[source]))
        for r in conn.execute("SELECT id, title, url, text, published_at, metrics FROM raw_doc WHERE source = ? "
                              "AND published_at >= ? AND published_at <= ?", (source, since, latest)):
            m = json.loads(r["metrics"])
            out.append({"id": r["id"], "source": source, "outlet": m.get("outlet") or "Hacker News",
                        "title": r["title"], "url": r["url"], "snippet": (r["text"] or "")[:240],
                        "published_at": r["published_at"], "points": m.get("points"), "comments": m.get("comments"),
                        "position": m.get("position"), "link": m.get("link")})
    return out


# ---------- plain words: news headlines and skill meanings ----------

STORY_BATCH = 30
SHOWN_CAREER = 2     # career score (0-3) a story needs to be shown; `relevant` is kept as career >= this
_describing = threading.Lock()


def _topic(key: str) -> str | None:
    """The event key, or None when the LLM gave none: such a story is its own event."""
    key = (key or "").strip().lower()
    return None if key in ("", "none", "n/a", "unknown") else key


def describe_pending(conn, cur: Curated) -> None:
    """Writes the missing plain-words text: headlines for recent stories, a meaning for each skill. Runs in the
    hourly job and, when something is missing, in the background of a request. A failure waits for the next run."""
    if not llm.available():
        return
    done = {r[0] for r in conn.execute("SELECT doc_id FROM story_plain")}
    unread = sorted((s for s in _news(conn) if s["id"] not in done), key=lambda s: s["published_at"], reverse=True)
    # one LLM call per run at most: the newest first, the rest wait for the next hour
    todo = [{"id": s["id"], "outlet": s["outlet"], "title": s["title"], **({"snippet": s["snippet"]} if s["snippet"] else {})}
            for s in unread[:STORY_BATCH]]
    skills = {cid for cid, c in cur.concepts.items() if c.kind == "skill"}
    if todo:
        since = iso(parse(utcnow()) - timedelta(days=2))
        topics = [r[0] for r in conn.execute("SELECT DISTINCT topic FROM story_plain WHERE topic IS NOT NULL "
                                             "AND created_at >= ? ORDER BY topic", (since,))]
        out, error = llm.describe_stories(todo, cur, topics)
        if error:
            log.warning("writing news headlines failed: %s", error)
        else:
            ids, now = {t["id"] for t in todo}, utcnow()
            for d in out:
                if d["id"] in ids and d["headline"].strip():
                    career = d["career"] if d["career"] in (0, 1, 2, 3) else 0
                    conn.execute("INSERT INTO story_plain (doc_id, headline, dek, skill_id, relevant, career, topic, model, "
                                 "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (doc_id) DO NOTHING",
                                 (d["id"], d["headline"].strip(), d["dek"].strip(),
                                  d["skill_id"] if d["skill_id"] in skills else None, int(career >= SHOWN_CAREER),
                                  career, _topic(d["topic"]), llm.MODEL, now))
            conn.commit()
    have = {r[0] for r in conn.execute("SELECT concept_id FROM concept_plain")}
    missing = [{"id": cid, "label": cur.concepts[cid].label} for cid in sorted(skills - have)]
    if missing:
        out, error = llm.describe_concepts(missing)
        if error:
            log.warning("writing skill meanings failed: %s", error)
            return
        now = utcnow()
        for d in out:
            if d["id"] in skills and d["plain"].strip():
                conn.execute("INSERT INTO concept_plain (concept_id, plain, model, created_at) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT (concept_id) DO NOTHING", (d["id"], d["plain"].strip(), llm.MODEL, now))
        conn.commit()


def _describe_in_background(cur: Curated):
    if not _describing.acquire(blocking=False):
        return

    def run():
        conn = db.connect()
        try:
            describe_pending(conn, cur)
        except Exception:
            log.exception("writing plain words failed")
        finally:
            conn.close()
            _describing.release()

    threading.Thread(target=run, daemon=True).start()


# ---------- the front page ----------


SOURCE_ORDER = {"my_news": 0, "reddit": 1, "hn_front": 2}   # which telling of an event to show: local news first
LIVE_PER_RUN = 10    # most new stories one hourly run sends to the live feed


def _heat(s: dict, now) -> float:
    """0..5: how fast a story is moving where it was posted. News sites give no counts; Reddit without a key gives
    only its hot order."""
    age_h = max((now - parse(s["published_at"])).total_seconds() / 3600, 0)
    if s["points"] is not None:
        return min(5.0, s["points"] / (age_h + 2) / 20)
    if s["position"] is not None:
        return max(0.0, 5 - 0.3 * s["position"])
    return 2.5


def _front_items(conn, cur: Curated) -> list[dict]:
    """Shown stories, one per event, best first. Only stories the LLM has read and scored SHOWN_CAREER or more:
    a story it hasn't read yet waits for the next hourly run instead of appearing unchecked."""
    plain = {r["doc_id"]: r for r in conn.execute("SELECT * FROM story_plain WHERE career >= ?", (SHOWN_CAREER,))}
    now = parse(utcnow())
    events: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for s in _news(conn):
        p = plain.get(s["id"])
        if p:
            events[p["topic"] or s["id"]].append((s, p))
    items = []
    for key, group in events.items():
        group.sort(key=lambda sp: (-sp[1]["career"], SOURCE_ORDER[sp[0]["source"]], sp[0]["published_at"]))
        s, p = group[0]
        outlets = sorted({g[0]["outlet"] for g in group})
        newest = max(g[0]["published_at"] for g in group)
        age_h = max((now - parse(newest)).total_seconds() / 3600, 0)
        c = cur.concepts.get(p["skill_id"] or "")
        items.append({
            "id": s["id"], "topic": p["topic"], "source": s["source"], "outlet": s["outlet"], "outlets": outlets,
            "headline": p["headline"], "dek": p["dek"], "title": s["title"], "url": s["url"],
            "published_at": s["published_at"], "first_seen": min(g[1]["created_at"] for g in group),
            "points": s["points"], "comments": s["comments"], "career": max(g[1]["career"] for g in group),
            "skill": {"id": c.id, "label": c.label} if c else None,
            # career matters most, then how widely it is covered, how fast it moves and how fresh it is
            "rank_score": round(10 * max(g[1]["career"] for g in group) + 3 * min(len(outlets) - 1, 3)
                                + max(_heat(g[0], now) for g in group) - 0.25 * age_h, 2),
        })
    items.sort(key=lambda i: i["rank_score"], reverse=True)
    # the same event under two topic keys (read in different batches): keep the better-ranked telling
    kept: list[dict] = []
    for i in items:
        words = _headline_words(i["headline"])
        if not any(_similar(words, _headline_words(k["headline"])) for k in kept):
            kept.append(i)
    return kept


def _headline_words(headline: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$]+", headline.lower()) if w not in STOP and len(w) > 2}


def _similar(a: set[str], b: set[str]) -> bool:
    """Headlines sharing most of their words are about the same event."""
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.6


@_cached
def front_page(conn, cur: Curated, limit: int = 40) -> dict:
    """The news queue: shown stories, one per event, best first. The page shows four at a time and rotates."""
    return {"as_of": utcnow(), "items": _front_items(conn, cur)[:limit]}


def fresh_news(cur: Curated, since: str) -> list[dict]:
    """Shown stories first read at or after `since`, for the live feed; at most LIVE_PER_RUN, best first."""
    conn = db.connect()
    try:
        return [i for i in _front_items(conn, cur) if i["first_seen"] >= since][:LIVE_PER_RUN]
    finally:
        conn.close()


# ---------- trends: skills on the Signal Ladder, grouped by family ----------

# how far up the Signal Ladder a status is; falling statuses sit below the ground floor
LADDER = {"Stable": 0, "Watch": 1, "Emerging": 2, "Act now": 3, "Declining": -1, "Stalled": -1}
COMPARE_DAYS = 90


def _statuses(conn, sid: str) -> dict[str, dict]:
    return {r["concept_id"]: {"status": r["status"], "rungs": json.loads(r["rungs"])}
            for r in conn.execute("SELECT concept_id, status, rungs FROM concept_status WHERE snapshot_id = ?", (sid,))}


def _snapshots(conn) -> tuple[dict | None, dict | None]:
    now = conn.execute("SELECT id, as_of FROM snapshot ORDER BY as_of DESC LIMIT 1").fetchone()
    if not now:
        return None, None
    cutoff = (parse(now["as_of"]) - timedelta(days=COMPARE_DAYS)).strftime("%Y-%m-%d")
    then = conn.execute("SELECT id, as_of FROM snapshot WHERE as_of <= ? ORDER BY as_of DESC LIMIT 1", (cutoff,)).fetchone()
    return dict(now), dict(then) if then else None


def _rung(r: dict, n: str) -> dict:
    x = r.get(n) or {}
    return {"active": bool(x.get("active")), "trend": x.get("trend"), "level": x.get("level")}


def _postings(conn) -> tuple[dict[str, dict], dict]:
    """What Malaysian job postings ask for, per skill: the sample of postings per role (role_requirement)."""
    per: dict[str, dict] = {}
    total_postings, roles = 0, 0
    for r in conn.execute("SELECT title, postings, skills FROM role_requirement"):
        roles += 1
        total_postings += r["postings"]
        for sk in json.loads(r["skills"]).get("skills", []):
            e = per.setdefault(sk["id"], {"postings": 0, "roles": [], "quote": None})
            e["postings"] += sk.get("count") or 0
            e["roles"].append({"title": r["title"], "count": sk.get("count") or 0, "of": r["postings"]})
            if not e["quote"] and sk.get("quotes"):
                e["quote"] = {"text": sk["quotes"][0]["text"], "role": r["title"]}
    for e in per.values():
        e["roles"].sort(key=lambda x: x["count"], reverse=True)
        e["roles"] = e["roles"][:3]
    return per, {"postings": total_postings, "roles": roles}


def _family(cur: Curated, cid: str) -> str:
    """The nearest ancestor that is a family (a skill's parent can be another skill or a capability)."""
    return next((a for a in cur.ancestors(cid) if a in cur.concepts and cur.concepts[a].kind == "family"), "other")


@_cached
def trends(conn, cur: Curated) -> dict:
    now, then = _snapshots(conn)
    if not now:
        return {"as_of": None, "compared_to": None, "families": [], "sample": None}
    st_now, st_then = _statuses(conn, now["id"]), _statuses(conn, then["id"]) if then else {}
    plain = {r["concept_id"]: r["plain"] for r in conn.execute("SELECT concept_id, plain FROM concept_plain")}
    postings, sample = _postings(conn)
    stories = front_page.__wrapped__(conn, cur, 60)["items"]
    news: dict[str, list[dict]] = defaultdict(list)
    for s in stories:
        if s["skill"]:
            news[s["skill"]["id"]].append({"headline": s["headline"], "url": s["url"], "points": s["points"]})
    for r in conn.execute("SELECT artifact_id, title, url, counts, concept_ids FROM feed_item WHERE kind = 'story'"):
        for cid in json.loads(r["concept_ids"]):
            if not any(n["url"] == r["url"] for n in news[cid]):
                news[cid].append({"headline": r["title"], "url": r["url"], "points": json.loads(r["counts"]).get("points")})
    repos: dict[str, list[dict]] = defaultdict(list)
    latest = conn.execute("SELECT MAX(scraped_at) FROM trending_repo WHERE since = 'daily'").fetchone()[0]
    if latest:
        for r in conn.execute("SELECT t.full_name, t.period_stars, c.plain, c.skill_id FROM trending_repo t "
                              "JOIN repo_category c ON c.full_name = t.full_name WHERE t.since = 'daily' "
                              "AND t.scraped_at = ? AND c.skill_id IS NOT NULL ORDER BY t.period_stars DESC", (latest,)):
            repos[r["skill_id"]].append({"name": r["full_name"], "plain": r["plain"], "stars_today": r["period_stars"],
                                         "url": f"https://github.com/{r['full_name']}"})
    if len(plain) < sum(1 for c in cur.concepts.values() if c.kind == "skill"):
        _describe_in_background(cur)

    families: dict[str, dict] = {}
    for cid, c in cur.concepts.items():
        if c.kind != "skill" or cid not in st_now:
            continue
        s_now, was = st_now[cid], (st_then.get(cid) or {}).get("status")
        step = LADDER[s_now["status"]] - LADDER[was] if was else 0
        talk, abroad, my = _rung(s_now["rungs"], "1"), _rung(s_now["rungs"], "2"), _rung(s_now["rungs"], "3")
        rising = [t for t in (talk["trend"], abroad["trend"]) if t and t > 0]
        score = 4 * max(step, 0) - 2 * max(-step, 0) + 2 * LADDER[s_now["status"]] + sum(rising) \
            + min(len(news[cid]), 5) * 0.3 + min(len(repos[cid]), 5) * 0.3
        fam_id = _family(cur, cid)
        fam = families.setdefault(fam_id, {
            "id": fam_id, "label": cur.concepts[fam_id].label if fam_id in cur.concepts else "Other skills",
            "status": (st_now.get(fam_id) or {}).get("status"), "skills": []})
        fam["skills"].append({
            "id": cid, "label": c.label, "plain": plain.get(cid), "status": s_now["status"],
            "was": was if step else None, "move": "up" if step > 0 else "down" if step < 0 else None,
            "score": round(score, 2),
            "ladder": {"talk": talk, "abroad": abroad,
                       "malaysia": {**my, "active": my["active"] and my["level"] == "concept"}},
            "postings": postings.get(cid),
            "evidence": {"news": news[cid][:3], "repos": repos[cid][:3]},
        })
    out = []
    for fam in families.values():
        fam["skills"].sort(key=lambda s: s["score"], reverse=True)
        fam["moving"] = sum(1 for s in fam["skills"] if s["move"] or s["status"] != "Stable")
        fam["score"] = round(sum(max(s["score"], 0) for s in fam["skills"][:3]), 2)
        out.append(fam)
    out.sort(key=lambda f: f["score"], reverse=True)
    return {"as_of": now["as_of"], "compared_to": then["as_of"] if then else None, "families": out, "sample": sample}


# ---------- the brief: the biggest shift, in two sentences ----------

BRIEF_INSTRUCTIONS = """You write the lead of a career intelligence page for working people in Malaysia, from the
facts given as JSON. Rules:
- `headline`: the biggest shift, at most 12 words, plain words, no hype, no question marks.
- `summary`: two sentences, at most 50 words: what moved, and how far it has got towards Malaysian hiring.
- Use only the facts. Name skills exactly as written. No numbers, dates or skills that aren't in the facts.
- "Hired abroad" rising is not Malaysian demand. If no skill is rising in Malaysian hiring, say Malaysian hiring
  hasn't followed yet, and don't call it a shift in "the job market" or "jobs": say it is in talk or hiring abroad.
  Job postings are a sample, never a count of openings."""
BRIEF_VERSION = "2"   # bump when the prompt or facts change, so old briefs aren't reused
BRIEF_SCHEMA = {"type": "object", "properties": {"headline": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["headline", "summary"]}


def _brief_facts(t: dict) -> tuple[dict, set[str]]:
    skills = [s | {"family": f["label"]} for f in t["families"] for s in f["skills"]]
    up = [s for s in skills if s["move"] == "up"]
    down = [s for s in skills if s["move"] == "down"]
    lead = max(t["families"], key=lambda f: sum(1 for s in f["skills"] if s["move"] == "up"), default=None)
    count = lambda rung: sum(1 for s in skills if s["ladder"][rung]["active"])
    facts = {
        "since": t["compared_to"], "as_of": t["as_of"],
        "climbed": [{"skill": s["label"], "from": s["was"], "to": s["status"], "family": s["family"]} for s in up],
        "fell": [{"skill": s["label"], "from": s["was"], "to": s["status"]} for s in down],
        "family_with_most_climbers": lead["label"] if lead else None,
        "skills_rising_in_talk": count("talk"), "skills_rising_in_hiring_abroad": count("abroad"),
        "skills_rising_in_malaysian_hiring": count("malaysia"),
        "status_meanings": {"Watch": "talked about, no hiring behind it yet",
                            "Emerging": "hiring abroad is rising, not yet in Malaysia",
                            "Act now": "hiring in Malaysia is rising"},
    }
    terms = {s["label"] for s in up + down} | ({lead["label"]} if lead else set())
    return facts, terms


def _template(facts: dict) -> dict:
    up = facts["climbed"]
    names = [c["skill"] for c in up[:3]]
    head = (f"{len(up)} skills climbed the Signal Ladder" if up else "No skill climbed the Signal Ladder")
    lead = f"{', '.join(names)} lead the climb" if names else "Talk and hiring held steady"
    my = ("Malaysian hiring hasn't followed yet." if not facts["skills_rising_in_malaysian_hiring"]
          else f"{facts['skills_rising_in_malaysian_hiring']} skills are rising in Malaysian hiring.")
    return {"headline": head, "summary": f"{lead}. {my}"}


@_cached
def brief(conn, cur: Curated) -> dict:
    from . import brief as checks   # the journey's post-check: unknown numbers and skills reject the text
    t = trends.__wrapped__(conn, cur)
    if not t["as_of"]:
        return {"as_of": None}
    facts, terms = _brief_facts(t)
    facts_text = json.dumps(facts, ensure_ascii=False)
    key = f"radar-brief:{BRIEF_VERSION}:" + db.content_hash(facts_text)
    row = conn.execute("SELECT payload FROM narration WHERE key = ?", (key,)).fetchone()
    if row:
        text = json.loads(row["payload"])
    else:
        text, by = _template(facts), "template"
        if llm.available():
            out, error = llm._generate(BRIEF_INSTRUCTIONS, f"<facts>\n{facts_text}\n</facts>", BRIEF_SCHEMA, None, thinking=0)
            if out:
                problem = checks.check(f"{out['headline']} {out['summary']}", facts_text, terms, cur)
                if problem is None:
                    text, by = {"headline": out["headline"].strip(), "summary": out["summary"].strip()}, llm.MODEL
                else:
                    log.info("radar brief rejected: %s", problem)
        text = {**text, "by": by}
        if by != "template":
            conn.execute("INSERT INTO narration (key, created_at, payload) VALUES (?, ?, ?) ON CONFLICT (key) DO NOTHING",
                         (key, utcnow(), json.dumps(text)))
            conn.commit()
    return {
        "as_of": t["as_of"], "compared_to": t["compared_to"], **text,
        "meters": {
            "talk": {"rising": facts["skills_rising_in_talk"]},
            "abroad": {"rising": facts["skills_rising_in_hiring_abroad"]},
            "malaysia": {"rising": facts["skills_rising_in_malaysian_hiring"], "sample": t["sample"]},
        },
        "climbed": len(facts["climbed"]), "fell": len(facts["fell"]),
    }
