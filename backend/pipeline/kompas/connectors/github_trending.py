"""GitHub's Trending page (github.com/trending), for Radar. There is no API, so the HTML is parsed; when GitHub
changes the markup a scrape returns nothing and Radar keeps serving the last good one.

The front page lists only 8 to 25 repositories, so a scrape also reads a few language pages and merges them:
a repository keeps its best (lowest) position and the stars it gained in the period.
"""

import html
import re

from ..http import FetchError, Http

URL = "https://github.com/trending"
# the front page plus the languages with the most trending repositories; together roughly 60-90 repos
LANGUAGES = ("", "python", "typescript", "javascript", "go", "rust", "jupyter-notebook")
SINCE = ("daily", "weekly")
PERIOD_WORDS = {"daily": "today", "weekly": "this week"}

ARTICLE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
NAME = re.compile(r'<h2 class="h3 lh-condensed">.*?href="/([^/"]+/[^/"]+)"', re.S)
DESC = re.compile(r'<p class="col-9[^"]*">(.*?)</p>', re.S)
LANG = re.compile(r'itemprop="programmingLanguage">([^<]+)<')
STARS = re.compile(r'href="/[^"]+/stargazers"[^>]*>(?:\s*<svg.*?</svg>)?\s*([\d,]+)', re.S)
FORKS = re.compile(r'href="/[^"]+/forks"[^>]*>(?:\s*<svg.*?</svg>)?\s*([\d,]+)', re.S)
GAINED = re.compile(r"([\d,]+) stars (?:today|this week|this month)")


def _int(m) -> int:
    return int(m.group(1).replace(",", "")) if m else 0


def parse(page: str) -> list[dict]:
    out = []
    for i, block in enumerate(ARTICLE.findall(page)):
        name = NAME.search(block)
        if not name:
            continue
        desc = DESC.search(block)
        lang = LANG.search(block)
        out.append({
            "full_name": name.group(1), "position": i + 1,
            "description": html.unescape(re.sub(r"<[^>]+>|\s+", " ", desc.group(1))).strip() if desc else "",
            "language": lang.group(1).strip() if lang else None,
            "stars": _int(STARS.search(block)), "forks": _int(FORKS.search(block)),
            "period_stars": _int(GAINED.search(block)),
        })
    return out


def fetch(since: str, http: Http | None = None) -> tuple[list[dict], list[str]]:
    """Merged trending list for one period, and the pages that failed."""
    http = http or Http(min_interval=1.0, headers={"Accept": "text/html"})
    merged: dict[str, dict] = {}
    failed = []
    for lang in LANGUAGES:
        url = f"{URL}/{lang}" if lang else URL
        try:
            repos = parse(http.get(url, {"since": since}).text)
        except FetchError:
            failed.append(url)
            continue
        if not repos:
            failed.append(url)   # an empty page means the markup changed or GitHub served a challenge
        for r in repos:
            have = merged.get(r["full_name"])
            if not have or r["period_stars"] > have["period_stars"]:
                merged[r["full_name"]] = r
    return sorted(merged.values(), key=lambda r: r["period_stars"], reverse=True), failed
