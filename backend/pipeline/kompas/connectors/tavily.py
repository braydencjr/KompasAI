"""Free courses for The Route's AI learning plan, found with Tavily's web search (tavily.com).

Tavily has a free plan (1,000 credits a month, no card); a basic search costs one credit, and a step uses up to two. Each search is limited to
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
# blogs and support sites on subdomains (support.khanacademy.org, news.freecodecamp.org) never get through, and the
# pattern keeps out search pages, tag pages, pricing and single lecture pages. Each site was checked with live searches.
FREE_SITES: dict[str, tuple[str, str]] = {
    "ocw.mit.edu": ("MIT OpenCourseWare", r"/courses/[^/]+/?"),                      # the course home, not its lectures
    "freecodecamp.org": ("freeCodeCamp", r"/learn/[^/]+.*"),
    "khanacademy.org": ("Khan Academy", r"/(?:math|computing|science|economics-finance-domain|humanities|college-careers-more)/(?!.*/[ave]/).+"),
    "learn.microsoft.com": ("Microsoft Learn", r"/(?:[a-z]{2}-[a-z]{2}/)?training/(?:paths|modules|courses)/[^/]+/?"),
    "cs50.harvard.edu": ("Harvard CS50", r"/.*"),
    "open.edu": ("OpenLearn (Open University)", r"/openlearn/(?!tag/|search|mod/).+"),
    "kaggle.com": ("Kaggle Learn", r"/learn/[^/]+/?"),
    # more free sources, added for everyday work skills Coursera was the only answer for
    "alison.com": ("Alison", r"/course/[^/]+/?"),                                    # free to study; a certificate costs extra
    "learn.saylor.org": ("Saylor Academy", r"/course/[^/]+/?"),
    "edu.gcfglobal.org": ("GCFGlobal LearnFree", r"/en/[^/]+/?"),
    "accountingcoach.com": ("AccountingCoach", r"/(?:[a-z-]+/(?:outline|explanation)|bookkeeping-training)/?"),
    "w3schools.com": ("W3Schools", r"/[a-z0-9_]+/?"),                                # a tutorial's home, not its pages
    "support.microsoft.com": ("Microsoft Support", r"/(?:[a-z]{2}-[a-z]{2}/)?(?:word|excel|powerpoint|outlook|onenote|teams|office)/?"),
    "learning.sap.com": ("SAP Learning", r"/(?:courses|learning-journeys)/[^/]+/?"),
    "trailhead.salesforce.com": ("Salesforce Trailhead", r"/content/learn/(?:modules|trails|projects)/[^/]+/?"),
    "academy.hubspot.com": ("HubSpot Academy", r"/courses/[^/]+/?"),
    "oyc.yale.edu": ("Open Yale Courses", r"/[a-z-]+/[a-z0-9-]+/?"),
    "huggingface.co": ("Hugging Face", r"/learn/[^/]+(?:/.*)?"),
    "learn.deeplearning.ai": ("DeepLearning.AI", r"/courses/[^/]+(?:/.*)?"),
    "developer.mozilla.org": ("MDN Web Docs", r"/[A-Za-z-]+/docs/Learn_web_development(?:/.*)?"),
    "openstax.org": ("OpenStax", r"/books/[^/]+(?:/pages/[^/]+)?/?"),
    "theodinproject.com": ("The Odin Project", r"/paths/[^/]+(?:/courses/[^/]+)?/?"),
    "applieddigitalskills.withgoogle.com": ("Google Applied Digital Skills", r"/c/[^/]+/en/[^/]+/?.*"),
}

# so one site with many pages on a topic (Alison has dozens) can't fill every slot
PER_SITE = 2

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


def search(queries: list[str], limit: int = 6, client: httpx.Client | None = None) -> list[dict]:
    """Free courses for a step, as the plan's course dicts (free: True): the step's first two search phrases, results
    merged, at most PER_SITE from one site. Raises FetchError when Tavily can't be reached or refuses the key; an empty
    list means it answered with nothing usable."""
    key = os.environ.get("TAVILY_API_KEY", "")
    phrases = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))[:2]
    if not key or not phrases:
        return []
    http = client or httpx.Client(timeout=10.0)
    out, seen, per_site = [], set(), {}
    try:
        for phrase in phrases:
            for r in _ask(http, key, phrase):
                url = r.get("url") if isinstance(r, dict) else None
                site = _site(url) if isinstance(url, str) else None
                title = _clean(r.get("title") or "") if site else ""
                if not site or not title or url in seen or per_site.get(site[0], 0) >= PER_SITE:
                    continue
                seen.add(url)
                per_site[site[0]] = per_site.get(site[0], 0) + 1
                out.append({"id": "free-" + hashlib.sha1(url.encode()).hexdigest()[:12], "title": title,
                            "provider": site[0], "platform": PLATFORM, "url": url, "workload": None, "free": True})
                if len(out) == limit:
                    return out
    finally:
        if client is None:
            http.close()
    return out


def _ask(http: httpx.Client, key: str, phrase: str) -> list:
    """One Tavily search (one credit), limited to the free sites."""
    try:
        resp = http.post(
            API, headers={"Authorization": f"Bearer {key}"},
            json={"query": f"{phrase} course", "search_depth": "basic", "max_results": 12,
                  "include_domains": sorted(FREE_SITES)},
        )
    except httpx.TimeoutException as e:
        raise FetchError("timeout", "Tavily timed out", API) from e
    except httpx.HTTPError as e:
        raise FetchError("network", f"Tavily unreachable: {e}", API) from e
    if resp.status_code != 200:
        category = "rate_limited" if resp.status_code in (429, 432, 433) else "client" if resp.status_code < 500 else "server"
        raise FetchError(category, f"Tavily answered {resp.status_code}", API, resp.status_code)
    try:
        results = resp.json().get("results", [])
    except ValueError as e:
        raise FetchError("parse", "Tavily sent something that isn't JSON", API) from e
    return results if isinstance(results, list) else []
