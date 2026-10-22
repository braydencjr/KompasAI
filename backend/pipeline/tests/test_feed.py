import itertools

from kompas import db
from kompas.config import Params
from kompas.explain import MEANING, RELATION_LABEL, explain, summary
from kompas.feed import rank
from kompas.periods import iso, parse, utcnow
from kompas.tag import retag


def story(conn, sid: str, title: str, text: str, points: int, hours_ago: float):
    published = iso(parse(utcnow()) - __import__("datetime").timedelta(hours=hours_ago))
    db.upsert_doc(conn, {
        "id": f"hn:{sid}", "source": "hn_front", "kind": "story", "url": "https://example.com", "title": title,
        "text": text, "published_at": published, "period": published[:7], "metrics": {"points": points},
    })


def test_feed_needs_title_match_and_freshness(conn, cur):
    story(conn, "1", "Show HN: A faster SQL formatter", "", 300, 3)             # in title, fresh
    story(conn, "2", "Make cursed fonts", "written in Python", 900, 3)           # only in body text
    story(conn, "3", "Postgres tips", "", 900, 24 * 5)                           # too old for the live feed
    story(conn, "4", "Tiny SQL thing", "", 40, 1)                                # below front-page level
    conn.commit()
    retag(conn, cur)
    titles = [i["title"] for i in rank(conn, utcnow(), Params())]
    assert titles == ["Show HN: A faster SQL formatter"]


def test_every_relation_and_status_has_a_message():
    for rel, status in itertools.product(RELATION_LABEL, MEANING):
        msg = explain(rel, "Power BI", status, None, None)
        assert msg["headline"] and msg["meaning"] and msg["action"]


def test_family_demand_is_explained():
    msg = explain("route", "Agentic coding workflows", "Emerging", "Software development", "Act now")
    assert "Software development roles are in demand in Malaysia" in msg["meaning"]


def test_summary_reads_as_a_sentence():
    assert summary([]).startswith("Quiet week")
    s = [{"status": "Act now", "label": "Power BI", "relation": "route"}]
    assert summary(s) == "Worth acting on: Malaysian employers are hiring for Power BI."
