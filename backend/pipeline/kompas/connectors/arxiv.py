"""arXiv (rung 1). Queries per concept instead of downloading every paper: the result count is the
signal, and the top few papers become evidence. arXiv asks for at most one request every 3 seconds."""

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from ..curated import Curated
from ..db import has_doc, upsert_doc
from ..http import Http
from ..periods import available_at, month_of, months, period_end, period_start

API = "https://export.arxiv.org/api/query"
CATEGORIES = ("cs.AI", "cs.CL", "cs.LG", "cs.CV")
NS = {"a": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}


def date_filter(period: str) -> str:
    return f"submittedDate:[{period_start(period):%Y%m%d}0000 TO {period_end(period):%Y%m%d}2359]"


def concept_query(terms: tuple[str, ...]) -> str:
    phrases = " OR ".join(f'abs:"{t}"' for t in terms)
    cats = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    return f"({phrases}) AND ({cats})"


def parse(xml_text: str) -> tuple[int, list[dict]]:
    root = ET.fromstring(xml_text)
    total = int(root.findtext("os:totalResults", "0", NS))
    papers = []
    for e in root.findall("a:entry", NS):
        link = next((l.get("href") for l in e.findall("a:link", NS) if l.get("rel") == "alternate"), None)
        papers.append({
            "id": e.findtext("a:id", "", NS).rsplit("/", 1)[-1],
            "title": " ".join(e.findtext("a:title", "", NS).split()),
            "summary": " ".join(e.findtext("a:summary", "", NS).split()),
            "published": e.findtext("a:published", "", NS),
            "url": link or e.findtext("a:id", "", NS),
        })
    return total, papers


def backfill(conn, cur: Curated, since: str, until: str, top_n: int = 3, http: Http | None = None,
             force: bool = False) -> int:
    """Skips months and concepts already fetched unless force=True, so an interrupted run can resume."""
    # arXiv throttles with 429s even within its 3-second rule; wait 20 s, 40 s, ... before giving up
    http = http or Http(min_interval=3.1, backoff=10, retries=6)
    cats = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    n = 0
    for period in months(since, until):
        if force or not has_doc(conn, f"axb:{period}"):
            _fetch_baseline(conn, http, cats, period)
        for c in cur.concepts.values():
            if not c.arxiv_terms or (not force and has_doc(conn, f"axc:{c.id}:{period}")):
                continue
            _fetch_concept(conn, http, c, period, top_n)
            n += 1
            conn.commit()
    return n


def _fetch_baseline(conn, http: Http, cats: str, period: str):
    total, _ = parse(http.get(API, {"search_query": f"({cats}) AND {date_filter(period)}", "max_results": 1}).text)
    upsert_doc(conn, {
        "id": f"axb:{period}", "source": "arxiv", "kind": "paper_baseline", "url": API,
        "title": f"All papers in {', '.join(CATEGORIES)}, {period}", "text": "",
        "published_at": available_at(period), "period": period, "metrics": {"count": total},
    })
    conn.commit()


def _fetch_concept(conn, http: Http, c, period: str, top_n: int):
    q = concept_query(c.arxiv_terms)
    full_query = f"{q} AND {date_filter(period)}"
    count, papers = parse(http.get(API, {
        "search_query": full_query, "max_results": top_n, "sortBy": "relevance",
    }).text)
    upsert_doc(conn, {
        "id": f"axc:{c.id}:{period}", "source": "arxiv", "kind": "paper_count",
        "url": f"{API}?{urlencode({'search_query': full_query, 'max_results': 20})}",
        "title": f"arXiv papers on {c.label}, {period}",
        "text": "", "published_at": available_at(period), "period": period,
        "metrics": {"concept_id": c.id, "count": count, "query": q},
    })
    for p in papers:
        upsert_doc(conn, {
            "id": f"ax:{p['id']}:{c.id}", "source": "arxiv", "kind": "paper", "url": p["url"],
            "title": p["title"], "text": p["summary"], "published_at": p["published"],
            "period": month_of(p["published"]), "metrics": {"concept_id": c.id, "query": q},
        })
