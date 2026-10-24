"""Malaysian news sites and Malaysian subreddits, for the news on AI Live Trend (kompas/radar.py).

- my_news: RSS feeds of Malaysian business and technology outlets. Articles carry no popularity count, so
  Radar ranks them by recency, and by how many outlets and subreddits cover the same story.
- reddit: each subreddit's "hot" listing. Without a key the public RSS feed is read: it keeps Reddit's hot
  order (`position`) but has no vote counts, and Reddit rate-limits it, so it is fetched once an hour. With
  REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET set (a Reddit "script" app) the official API is used instead and
  adds each post's votes and comments.

Pinned weekly threads and picture or video posts are skipped here; whether a story matters to people's work is
decided afterwards by the LLM. A feed that fails is skipped and logged: one outlet being down never empties
the news.
"""

import hashlib
import html
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from ..document import Document
from ..http import FetchError, Http
from ..periods import iso, month_of

log = logging.getLogger("kompas.my_news")

FEEDS = {
    "https://www.malaymail.com/feed/rss/money": "Malay Mail",
    "https://www.malaymail.com/feed/rss/tech-gadgets": "Malay Mail",
    "https://www.freemalaysiatoday.com/category/business/feed/": "Free Malaysia Today",
    "https://vulcanpost.com/feed/": "Vulcan Post",
    "https://www.soyacincau.com/feed/": "SoyaCincau",
    "https://www.lowyat.net/feed/": "Lowyat.NET",
    "https://www.digitalnewsasia.com/rss.xml": "Digital News Asia",
}
SUBREDDITS = ("malaysia", "MalaysianPF")
PER_FEED = 5          # newest articles kept per outlet: a signal needs the freshest few, not the whole feed
PER_SUBREDDIT = 10    # top "hot" posts kept per subreddit
USER_AGENT = "kompas-career-app/0.1 (career guidance for Malaysian workers)"
ATOM = "{http://www.w3.org/2005/Atom}"
MYT = timezone(timedelta(hours=8))   # feeds that give no zone are Malaysian time
PINNED = re.compile(r"weekly|daily thread|megathread|random discussion|quick questions", re.I)
MEDIA = ("i.redd.it", "v.redd.it", "i.imgur.com", "imgur.com", "youtube.com", "youtu.be")


def _http() -> Http:
    return Http(min_interval=1.0, retries=2, max_wait=60, headers={"User-Agent": USER_AGENT})


def _text(value: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>|\s+", " ", value or "")).strip()


def _when(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if value[:4].isdigit() else parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return iso(dt if dt.tzinfo else dt.replace(tzinfo=MYT))


def norm_url(url: str) -> str:
    """The same article under different tracking parameters or a trailing slash is one URL."""
    p = urlsplit(url.strip())
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}"


# ---------- news sites ----------


def parse_rss(xml: str, outlet: str) -> list[Document]:
    out = []
    for item in ET.fromstring(xml).iter("item"):
        link = (item.findtext("link") or "").strip()
        title = _text(item.findtext("title"))
        published = _when(item.findtext("pubDate"))
        if not link or not title or not published:
            continue
        out.append(Document(
            id="mynews:" + hashlib.sha1(norm_url(link).encode()).hexdigest()[:16], source="my_news", kind="article",
            source_id=link, url=link, title=title, text=_text(item.findtext("description"))[:600],
            published_at=published, period=month_of(published), metrics={"outlet": outlet},
        ))
    return out


def fetch_news(http: Http | None = None) -> list[Document]:
    http = http or _http()
    docs = []
    for url, outlet in FEEDS.items():
        try:
            docs.extend(sorted(parse_rss(http.get(url).text, outlet), key=lambda d: d.published_at, reverse=True)[:PER_FEED])
        except (FetchError, ET.ParseError) as e:
            log.warning("%s: %s", url, e)
    return docs


# ---------- Reddit ----------


def _reddit_doc(sub: str, post_id: str, title: str, url: str, published: str, link: str | None, metrics: dict) -> Document:
    return Document(id=f"rd:{post_id}", source="reddit", kind="post", source_id=post_id, url=url, title=title,
                    text="", published_at=published, period=month_of(published),
                    metrics={"outlet": f"r/{sub}", "subreddit": sub, "link": link, **metrics})


def parse_reddit_atom(xml: str, sub: str) -> list[Document]:
    out = []
    for i, entry in enumerate(ET.fromstring(xml).iter(f"{ATOM}entry")):
        post_id = (entry.findtext(f"{ATOM}id") or "").removeprefix("t3_")
        permalink = entry.find(f"{ATOM}link")
        title = _text(entry.findtext(f"{ATOM}title"))
        published = _when(entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated"))
        if not post_id or permalink is None or not title or not published or PINNED.search(title):
            continue
        # the post's own link ("[link]" in the entry): an article it shares, a picture, or the post itself
        content = entry.findtext(f"{ATOM}content") or ""
        shared = re.search(r'<a href="([^"]+)">\[link\]</a>', html.unescape(content))
        link = shared.group(1) if shared else None
        if link and urlsplit(link).netloc.lower().removeprefix("www.") in MEDIA:
            continue   # a picture or a video: nothing to read
        if link and "reddit.com" in link:
            link = None   # a text post links to itself
        if i < 3 and published < iso(datetime.now(timezone.utc) - timedelta(days=3)):
            continue   # an old post at the top of "hot" is a pinned one; the RSS feed has no pinned flag
        out.append(_reddit_doc(sub, post_id, title, permalink.get("href"), published, link, {"position": i + 1}))
    return out


def _reddit_api(http: Http, sub: str, cid: str, secret: str) -> list[Document]:
    token = http.client.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret),
                             data={"grant_type": "client_credentials"}).json()["access_token"]
    data = http.client.get(f"https://oauth.reddit.com/r/{sub}/hot", params={"limit": 25},
                           headers={"Authorization": f"Bearer {token}"}).json()
    out = []
    for i, c in enumerate(data["data"]["children"]):
        p = c["data"]
        if p.get("stickied") or p.get("is_video") or p.get("post_hint") == "image":
            continue
        link = None if p.get("is_self") else p.get("url")
        published = iso(datetime.fromtimestamp(p["created_utc"], timezone.utc))
        out.append(_reddit_doc(sub, p["id"], html.unescape(p["title"]), f"https://www.reddit.com{p['permalink']}",
                               published, link, {"position": i + 1, "points": p["score"], "comments": p["num_comments"]}))
    return out


def fetch_reddit(http: Http | None = None) -> list[Document]:
    http = http or _http()
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    docs = []
    for sub in SUBREDDITS:
        try:
            posts = (_reddit_api(http, sub, cid, secret) if cid and secret
                     else parse_reddit_atom(http.get(f"https://www.reddit.com/r/{sub}/hot/.rss", {"limit": 25}).text, sub))
            docs.extend(posts[:PER_SUBREDDIT])
        except (FetchError, ET.ParseError, KeyError, ValueError) as e:
            log.warning("r/%s: %s", sub, e)
    return docs
