import pytest

from kompas import curated, db
from kompas.periods import available_at, months


@pytest.fixture
def cur():
    return curated.load()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("KOMPAS_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("KOMPAS_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    c = db.connect()
    yield c
    c.close()


def add_hiring(conn, period: str, n_total: int, n_matching: int, phrase: str):
    """Synthetic test data: n_total hiring posts in a month, n_matching of them mentioning phrase."""
    for i in range(n_total):
        text = f"Backend engineer, remote. We use {phrase} daily." if i < n_matching else "Backend engineer, Go."
        db.upsert_doc(conn, {
            "id": f"hnh:{period}:{i}", "source": "hn_hiring", "kind": "hiring_post",
            "url": "https://news.ycombinator.com/", "title": text[:40], "text": text,
            "published_at": f"{period}-02T12:00:00Z", "period": period, "metrics": {},
        })


def add_github_counts(conn, cur, period: str, topic_counts: dict[str, int], default: int = 100):
    for t in cur.all_topics():
        db.upsert_doc(conn, {
            "id": f"ghc:{t}:{period}", "source": "github", "kind": "repo_count", "url": "https://github.com/search",
            "title": f"New repositories tagged '{t}' in {period}", "text": "",
            "published_at": available_at(period), "period": period,
            "metrics": {"topic": t, "count": topic_counts.get(t, default)},
        })


def add_dosm(conn, period: str, release_date: str, rows: dict[str, int]):
    for code, n in rows.items():
        db.upsert_doc(conn, {
            "id": f"dosm:{period}:{code}", "source": "dosm_jmi", "kind": "occupation_stat",
            "url": "https://www.dosm.gov.my/", "title": f"Occupation {code}", "text": "",
            "published_at": f"{release_date}T00:00:00Z", "period": period,
            "metrics": {"masco_code": code, "offerings": n},
        })


__all__ = ["add_hiring", "add_github_counts", "add_dosm", "months"]
