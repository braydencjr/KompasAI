"""arXiv (rung 1). Queries per concept instead of downloading every paper: the result count is the
signal, and the top few papers become evidence. arXiv asks for at most one request every 3 seconds.

Documents:
- axb:<month>             all papers in the tracked categories that month (the denominator)
- axc:<concept>:<month>   papers matching the concept that month (the count)
- ax:<id>v<n>:<concept>   a top paper for that concept. The same paper can appear under several concepts;
                          each is its own query hit, and source_id (the arXiv id without version) is shared.
"""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from ..curated import Curated
from ..db import has_doc
from ..document import Document, utc, utc_or_none
from ..http import FetchError, Http
from ..ingest import Breaker, Options, Run, later, month_window
from ..periods import available_at, month_of, period_end, period_start

API = "https://export.arxiv.org/api/query"
CATEGORIES = ("cs.AI", "cs.CL", "cs.LG", "cs.CV")
NS = {"a": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/",
      "arxiv": "http://arxiv.org/schemas/atom"}
PAGE_SIZE = 100   # arXiv allows up to 2000 per request; small pages keep each response cheap


def date_filter(period: str) -> str:
    return f"submittedDate:[{period_start(period):%Y%m%d}0000 TO {period_end(period):%Y%m%d}2359]"


def concept_query(terms: tuple[str, ...]) -> str:
    phrases = " OR ".join(f'abs:"{t}"' for t in terms)
    cats = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    return f"({phrases}) AND ({cats})"


def parse(xml_text: str) -> tuple[int, list[dict]]:
    """(total results, papers on this page). Raises FetchError for malformed feeds and for the error
    entry arXiv returns (with HTTP 200) when it rejects a query."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise FetchError("parse", f"arXiv returned malformed XML: {e}") from e
    total = root.findtext("os:totalResults", None, NS)
    if total is None or not total.strip().isdigit():
        raise FetchError("parse", "arXiv feed has no totalResults")
    entries = root.findall("a:entry", NS)
    if len(entries) == 1 and entries[0].findtext("a:title", "", NS).strip() == "Error":
        raise FetchError("client", "arXiv rejected the query: " + " ".join(entries[0].findtext("a:summary", "", NS).split()))
    papers = []
    for e in entries:
        link = next((l.get("href") for l in e.findall("a:link", NS) if l.get("rel") == "alternate"), None)
        versioned = e.findtext("a:id", "", NS).rsplit("/abs/", 1)[-1]
        primary = e.find("arxiv:primary_category", NS)
        papers.append({
            "id": versioned.rsplit("/", 1)[-1],
            "arxiv_id": re.sub(r"v\d+$", "", versioned),
            "title": " ".join(e.findtext("a:title", "", NS).split()),
            "summary": " ".join(e.findtext("a:summary", "", NS).split()),
            "published": e.findtext("a:published", "", NS),
            "updated": e.findtext("a:updated", "", NS),
            "url": link or e.findtext("a:id", "", NS),
            "authors": [" ".join(a.findtext("a:name", "", NS).split()) for a in e.findall("a:author", NS)],
            "categories": [c.get("term") for c in e.findall("a:category", NS) if c.get("term")],
            "primary_category": primary.get("term") if primary is not None else None,
        })
    return int(total), papers


def search(http: Http, query: str, max_results: int, sort: str = "relevance") -> tuple[int, list[dict], bool]:
    """(total, papers, complete). Pages through results until max_results papers or the end. `complete`
    is False when arXiv returned fewer papers than it said exist (it sometimes drops entries)."""
    total, papers, start = 0, [], 0
    while True:
        n = min(PAGE_SIZE, max_results - len(papers))
        if n <= 0:
            break
        total, page = parse(http.get(API, {"search_query": query, "start": start, "max_results": n,
                                           "sortBy": sort}).text)
        papers.extend(page)
        start += len(page)
        if not page or start >= total:
            break
    return total, papers, len(papers) >= min(max_results, total)


def ingest(run: Run, cur: Curated, opts: Options, top_n: int = 3, http: Http | None = None):
    """Monthly counts per concept plus the top papers. Resumable: units already stored are skipped (unless
    in the overlap window or --force), and the checkpoint advances one fully fetched month at a time."""
    # arXiv throttles with 429s even within its 3-second rule; wait 20 s, 40 s, ... before giving up
    http = http or run.http(min_interval=3.1, backoff=10, retries=6)
    breaker = Breaker(run)
    cats = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    ms, refetch = month_window(run, opts)
    cp, blocked = run.checkpoint(), False
    for period in ms:
        force, ok = period in refetch, True
        if force or not has_doc(run.conn, f"axb:{period}"):
            ok &= _fetch_baseline(run, http, breaker, cats, period)
            run.commit()
        else:
            run.skip()
        for c in cur.concepts.values():
            if not c.arxiv_terms:
                continue
            if not force and has_doc(run.conn, f"axc:{c.id}:{period}"):
                run.skip()
                continue
            ok &= _fetch_concept(run, http, breaker, c, period, top_n)
            run.commit()
        blocked |= not ok
        if not blocked:
            cp = later(cp, period)
            run.commit(cursor=cp)


def _fetch_baseline(run: Run, http: Http, breaker: Breaker, cats: str, period: str) -> bool:
    doc_id = f"axb:{period}"
    query = f"({cats}) AND {date_filter(period)}"
    try:
        total, _ = parse(http.get(API, {"search_query": query, "max_results": 1}).text)
        if total == 0:
            # thousands of papers appear in these categories every month; zero is arXiv's intermittent
            # empty answer, not a real count, so ask once more before giving up
            total, _ = parse(http.get(API, {"search_query": query, "max_results": 1}).text)
    except FetchError as e:
        breaker.failed(doc_id, e)
        return False
    breaker.ok()
    if total == 0:
        run.fail(doc_id, "truncated", f"arXiv returned 0 papers for all of {', '.join(CATEGORIES)} in {period}; "
                 "not stored, because a zero denominator would be wrong")
        return False
    run.save(Document(
        id=doc_id, source="arxiv", kind="paper_baseline", source_id=period, url=API,
        title=f"All papers in {', '.join(CATEGORIES)}, {period}", text="",
        published_at=available_at(period), period=period, metrics={"count": total},
        raw_payload={"search_query": query, "totalResults": total},
    ))
    return True


def _fetch_concept(run: Run, http: Http, breaker: Breaker, c, period: str, top_n: int) -> bool:
    doc_id = f"axc:{c.id}:{period}"
    q = concept_query(c.arxiv_terms)
    full_query = f"{q} AND {date_filter(period)}"
    try:
        count, papers, complete = search(http, full_query, top_n)
        if not complete:
            count, papers, complete = search(http, full_query, top_n)
    except FetchError as e:
        breaker.failed(doc_id, e)
        return False
    breaker.ok()
    if not complete:
        run.partial(f"{doc_id}: arXiv reported {count} papers but returned only {len(papers)} of the top {top_n}")
    run.save(Document(
        id=doc_id, source="arxiv", kind="paper_count", source_id=f"{c.id}:{period}",
        url=f"{API}?{urlencode({'search_query': full_query, 'max_results': 20})}",
        title=f"arXiv papers on {c.label}, {period}", text="", published_at=available_at(period), period=period,
        metrics={"concept_id": c.id, "count": count, "query": q},
        raw_payload={"search_query": full_query, "totalResults": count},
    ))
    for p in papers:
        try:
            published = utc(p["published"])
            doc = Document(
                id=f"ax:{p['id']}:{c.id}", source="arxiv", kind="paper", source_id=p["arxiv_id"], url=p["url"],
                title=p["title"], text=p["summary"], published_at=published, updated_at=utc_or_none(p["updated"]),
                period=month_of(published),
                metrics={"concept_id": c.id, "query": q, "authors": p["authors"], "categories": p["categories"],
                         "primary_category": p["primary_category"]},
                raw_payload=p,
            )
        except ValueError as e:
            run.fail(f"ax:{p.get('id')}", "parse", f"bad paper record: {e}")
            continue
        run.save(doc)
    return True
