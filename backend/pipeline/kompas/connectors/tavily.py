"""Free courses for The Route's AI learning plan, found with Tavily's web search (tavily.com).

Tavily has a free plan (1,000 credits a month, no card); a basic search costs one credit. Each search is limited to
sites that teach for free (FREE_SITES), and a result is only used when its link is https, on one of those sites,
and on a course page of that site (not a forum, a blog or a lecture inside a course). Web search results are untrusted text: only the title (shortened) and the link
are kept, and the AI picks a course by id from what survived, so it can't add a course of its own.

Needs TAVILY_API_KEY in backend/.env; without it (or with KOMPAS_TAVILY=0) this source is simply skipped.
"""

import hashlib
import os
import re
from urllib.parse import urlparse

import httpx

from ..http import FetchError

API = "https://api.tavily.com/search"
PLATFORM = "Free"

# host -> (provider shown to the user, the path pattern of a course page). The host must match exactly, so forums,
# blogs and support sites on subdomains (support.khanacademy.org, news.freecodecamp.org) never get through.
FREE_SITES: dict[str, tuple[str, str]] = {
    "ocw.mit.edu": ("MIT OpenCourseWare", r"/courses/[^/]+/?"),                      # the course home, not its lectures
    "freecodecamp.org": ("freeCodeCamp", r"/learn/[^/]+.*"),
    "khanacademy.org": ("Khan Academy", r"/(?:math|computing|science|economics-finance-domain|humanities|college-careers-more)/(?!.*/[ave]/).+"),
    "learn.microsoft.com": ("Microsoft Learn", r"/(?:[a-z]{2}-[a-z]{2}/)?training/(?:paths|modules|courses)/[^/]+/?"),
    "cs50.harvard.edu": ("Harvard CS50", r"/.*"),
    "open.edu": ("OpenLearn (Open University)", r"/openlearn/.+"),
    "kaggle.com": ("Kaggle Learn", r"/learn/[^/]+/?"),
}

TITLE_MAX = 110


def enabled() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY")) and os.environ.get("KOMPAS_TAVILY", "1") != "0"


def _site(url: str) -> tuple[str, str] | None:
    """(provider, host) when `url` is an https course page on a free site, else None."""
    try:
        u = urlparse(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.")
    site = FREE_SITES.get(host)
    if site and u.scheme == "https" and re.fullmatch(site[1], u.path):
        return site[0], host
    return None


def _clean(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:TITLE_MAX]


def search(queries: list[str], limit: int = 4, client: httpx.Client | None = None) -> list[dict]:
    """Free courses matching the first query, as the plan's course dicts (free: True). Raises FetchError when Tavily
    can't be reached or refuses the key; an empty list means it answered with nothing usable."""
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key or not queries:
        return []
    http = client or httpx.Client(timeout=10.0)
    try:
        resp = http.post(
            API, headers={"Authorization": f"Bearer {key}"},
            json={"query": f"{queries[0]} course", "search_depth": "basic", "max_results": 10,
                  "include_domains": sorted(FREE_SITES)},
        )
    except httpx.TimeoutException as e:
        raise FetchError("timeout", "Tavily timed out", API) from e
    except httpx.HTTPError as e:
        raise FetchError("network", f"Tavily unreachable: {e}", API) from e
    finally:
        if client is None:
            http.close()
    if resp.status_code != 200:
        category = "rate_limited" if resp.status_code in (429, 432, 433) else "client" if resp.status_code < 500 else "server"
        raise FetchError(category, f"Tavily answered {resp.status_code}", API, resp.status_code)
    try:
        results = resp.json().get("results", [])
    except ValueError as e:
        raise FetchError("parse", "Tavily sent something that isn't JSON", API) from e

    out, seen = [], set()
    for r in results if isinstance(results, list) else []:
        url = r.get("url") if isinstance(r, dict) else None
        site = _site(url) if isinstance(url, str) else None
        title = _clean(r.get("title") or "") if site else ""
        if not site or not title or url in seen:
            continue
        seen.add(url)
        out.append({"id": "free-" + hashlib.sha1(url.encode()).hexdigest()[:12], "title": title, "provider": site[0],
                    "platform": PLATFORM, "url": url, "workload": None, "free": True})
        if len(out) == limit:
            break
    return out
