import json
from datetime import datetime, timezone

import httpx
import pytest

from kompas import db
from kompas.connectors import arxiv, github, hn
from kompas.http import FetchError
from kompas.ingest import Options, start_run

from .conftest import mock_http, routes


def feed(total: int, entries: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>{total}</opensearch:totalResults>{entries}
</feed>"""


PAPER = """
  <entry>
    <id>http://arxiv.org/abs/2609.01234v2</id>
    <updated>2026-09-20T10:00:00Z</updated>
    <published>2026-09-03T17:59:59Z</published>
    <title>Retrieval-Augmented
      Generation at Scale</title>
    <summary>We study retrieval-augmented generation.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link href="http://arxiv.org/abs/2609.01234v2" rel="alternate" type="text/html"/>
    <arxiv:primary_category term="cs.CL"/>
    <category term="cs.CL"/><category term="cs.AI"/>
  </entry>"""


# ---------- arXiv ----------


def test_arxiv_normalisation_keeps_provenance():
    total, papers = arxiv.parse(feed(42, PAPER))
    p = papers[0]
    assert total == 42
    assert (p["id"], p["arxiv_id"]) == ("2609.01234v2", "2609.01234")
    assert p["title"] == "Retrieval-Augmented Generation at Scale"
    assert p["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert p["categories"] == ["cs.CL", "cs.AI"] and p["primary_category"] == "cs.CL"


def test_arxiv_error_feeds_and_bad_xml_are_errors():
    err = feed(1, "<entry><id>http://arxiv.org/api/errors</id><title>Error</title><summary>bad query</summary></entry>")
    with pytest.raises(FetchError) as e:
        arxiv.parse(err)
    assert e.value.category == "client"
    with pytest.raises(FetchError) as e:
        arxiv.parse("<feed><unclosed>")
    assert e.value.category == "parse"


def arxiv_handler(baseline_totals: list[int], concept_total: int = 7):
    def handler(request):
        q = request.url.params["search_query"]
        if q.startswith("(cat:"):
            return httpx.Response(200, text=feed(baseline_totals.pop(0) if len(baseline_totals) > 1 else baseline_totals[0]))
        if 'abs:"retrieval-augmented generation"' in q:
            return httpx.Response(200, text=feed(concept_total, PAPER))
        return httpx.Response(200, text=feed(0))
    return handler


def test_arxiv_ingest_stores_counts_papers_and_checkpoint(conn, cur):
    http = mock_http(arxiv_handler([9000]))
    with start_run(conn, "arxiv", "monthly", "test") as run:
        arxiv.ingest(run, cur, Options(since="2026-09", until="2026-09"), top_n=1, http=http)
    assert json.loads(conn.execute("SELECT metrics FROM raw_doc WHERE id = 'axb:2026-09'").fetchone()[0])["count"] == 9000
    rag = conn.execute("SELECT * FROM raw_doc WHERE id = 'axc:rag:2026-09'").fetchone()
    assert json.loads(rag["metrics"])["count"] == 7
    paper = conn.execute("SELECT * FROM raw_doc WHERE id = 'ax:2609.01234v2:rag'").fetchone()
    assert paper["source_id"] == "2609.01234" and paper["updated_at"] == "2026-09-20T10:00:00Z"
    assert json.loads(paper["metrics"])["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert run.checkpoint() == "2026-09"
    # second run: everything already stored, nothing re-fetched
    calls = []
    http = mock_http(lambda r: calls.append(r) or httpx.Response(500))
    with start_run(conn, "arxiv", "monthly", "test") as run:
        arxiv.ingest(run, cur, Options(since="2026-09", until="2026-09"), http=http)
    assert calls == [] and run.status == "no_change"


def test_arxiv_zero_denominator_is_not_stored(conn, cur):
    # arXiv sometimes answers with an empty feed; zero papers in four busy categories isn't a real count
    http = mock_http(arxiv_handler([0]))
    with start_run(conn, "arxiv", "monthly", "test") as run:
        arxiv.ingest(run, cur, Options(since="2026-09", until="2026-09"), top_n=1, http=http)
    assert not db.has_doc(conn, "axb:2026-09")
    assert run.status == "partial" and run.checkpoint() is None
    assert db.has_doc(conn, "axc:rag:2026-09")    # the concept counts are still fine


def test_arxiv_search_pages_and_detects_short_answers(monkeypatch):
    monkeypatch.setattr(arxiv, "PAGE_SIZE", 1)
    starts = []

    def handler(request):
        starts.append(int(request.url.params["start"]))
        return httpx.Response(200, text=feed(5, PAPER if len(starts) < 3 else ""))

    total, papers, complete = arxiv.search(mock_http(handler), "q", 4)
    assert starts == [0, 1, 2] and len(papers) == 2 and total == 5 and complete is False


# ---------- GitHub ----------


def github_handler(counts: dict[str, int], incomplete: set[str] = frozenset()):
    def handler(request):
        topic = request.url.params["q"].split()[0].removeprefix("topic:")
        return httpx.Response(200, json={"total_count": counts.get(topic, 3), "incomplete_results": topic in incomplete,
                                         "items": []})
    return handler


def test_github_counts_are_idempotent_and_keep_observations(conn, cur):
    opts = Options(since="2026-08", until="2026-08")
    with start_run(conn, "github", "counts", "test") as run:
        github.ingest_counts(run, cur, opts, http=mock_http(github_handler({"rag": 40})))
    n = conn.execute("SELECT COUNT(*) FROM raw_doc WHERE kind = 'repo_count'").fetchone()[0]
    assert n == len(cur.all_topics()) and run.checkpoint() == "2026-08" and run.status == "ok"
    # forced re-fetch: same rows, the new count wins in the document, both counts stay as observations
    with start_run(conn, "github", "counts", "test") as run:
        github.ingest_counts(run, cur, Options(since="2026-08", until="2026-08", force=True),
                             http=mock_http(github_handler({"rag": 44})))
    assert conn.execute("SELECT COUNT(*) FROM raw_doc WHERE kind = 'repo_count'").fetchone()[0] == n
    assert json.loads(conn.execute("SELECT metrics FROM raw_doc WHERE id = 'ghc:rag:2026-08'").fetchone()[0])["count"] == 44
    obs = [r["value"] for r in conn.execute(
        "SELECT value FROM artifact_metric WHERE artifact_id = 'ghc:rag:2026-08' ORDER BY observed_at")]
    assert sorted(obs) == [40, 44] or obs == [44]   # two observations unless both runs hit the same second
    assert run.counts["updated"] == 1


def test_github_incomplete_results_make_the_run_partial(conn, cur):
    with start_run(conn, "github", "counts", "test") as run:
        github.ingest_counts(run, cur, Options(since="2026-08", until="2026-08"),
                             http=mock_http(github_handler({}, incomplete={"rag"})))
    assert run.status == "partial"
    assert json.loads(conn.execute("SELECT metrics FROM raw_doc WHERE id = 'ghc:rag:2026-08'").fetchone()[0])["incomplete"]


def test_github_repeated_failures_stop_the_run_but_keep_committed_months(conn, cur):
    def handler(request):
        return httpx.Response(200, json={"total_count": 5}) if "2026-07" in request.url.params["q"] else httpx.Response(422)

    with pytest.raises(FetchError):
        with start_run(conn, "github", "counts", "test") as run:
            github.ingest_counts(run, cur, Options(since="2026-07", until="2026-08"), http=mock_http(handler))
    assert run.status == "partial" and run.checkpoint() == "2026-07"
    assert db.has_doc(conn, "ghc:rag:2026-07") and not db.has_doc(conn, "ghc:rag:2026-08")


REPO = {"id": 99, "full_name": "acme/agent-kit", "html_url": "https://github.com/acme/agent-kit", "description": "Agents",
        "topics": ["ai-agents"], "language": "Python", "created_at": "2026-10-10T08:00:00Z",
        "updated_at": "2026-10-20T08:00:00Z", "pushed_at": "2026-10-20T07:00:00Z", "stargazers_count": 900,
        "forks_count": 10, "owner": {"login": "acme", "avatar_url": "https://avatars.test/1"}}


def test_github_poll_records_star_observations_without_owner_data(conn, cur):
    def handler(request):
        items = [REPO] if request.url.params["q"].startswith("topic:ai-agents") else []
        return httpx.Response(200, json={"total_count": len(items), "incomplete_results": False, "items": items})

    with start_run(conn, "github", "live", "test") as run:
        new = github.poll(run, cur, http=mock_http(handler))
        run.commit()
    assert new == ["gh:acme/agent-kit"]
    row = conn.execute("SELECT * FROM raw_doc WHERE id = 'gh:acme/agent-kit'").fetchone()
    assert row["source_id"] == "99" and row["updated_at"] == "2026-10-20T08:00:00Z"
    assert row["published_at"] == "2026-10-10T08:00:00Z"
    assert "owner" not in json.loads(row["raw_payload"])
    assert conn.execute("SELECT value FROM artifact_metric WHERE artifact_id = 'gh:acme/agent-kit'").fetchone()[0] == 900


# ---------- Hacker News ----------


def hit(i: int, created: int, title: str | None = "Show HN: SQL tool", points: int = 150) -> dict:
    return {"objectID": str(i), "title": title, "url": f"https://x.test/{i}", "created_at_i": created,
            "points": points, "num_comments": 3, "author": "someone"}


def test_hn_front_splits_windows_past_the_algolia_cap(conn, cur):
    lo = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    queries = []

    def handler(request):
        f = request.url.params["numericFilters"].split(",")
        a, b = int(f[0].split(">=")[1]), int(f[1].split("<")[1])
        queries.append((a, b))
        if b - a > 4 * 86400:      # pretend wide windows hold more than Algolia returns
            return httpx.Response(200, json={"hits": [], "nbHits": 1500, "nbPages": 1})
        hits = [hit(a, a + 60)]
        return httpx.Response(200, json={"hits": hits, "nbHits": 1, "nbPages": 1})

    with start_run(conn, "hn_front", "backfill", "test") as run:
        hn.ingest_front(run, cur, Options(since="2026-09", until="2026-09"), http=mock_http(handler))
    stored = conn.execute("SELECT COUNT(*) FROM raw_doc WHERE source = 'hn_front'").fetchone()[0]
    assert stored > 4 and run.status == "ok"
    narrow = [q for q in queries if q[1] - q[0] <= 4 * 86400]
    assert stored == len(narrow) and len(narrow) > len(queries) - len(narrow) and queries[0][0] == lo
    assert run.checkpoint() == "2026-10-01T00:00:00Z"
    payload = json.loads(conn.execute("SELECT raw_payload FROM raw_doc LIMIT 1").fetchone()[0])
    assert "author" not in payload


def test_hn_front_truncated_and_malformed_hits_are_reported(conn, cur):
    def handler(request):
        a = int(request.url.params["numericFilters"].split(",")[0].split(">=")[1])
        bad = {"objectID": "x", "title": "Broken"}                         # no created_at_i
        return httpx.Response(200, json={"hits": [hit(a, a + 60), bad, hit(a + 1, a + 61, title=None)],
                                         "nbHits": 5, "nbPages": 1})

    with start_run(conn, "hn_front", "backfill", "test") as run:
        hn.ingest_front(run, cur, Options(since="2026-09", until="2026-09"), http=mock_http(handler))
    assert run.status == "partial" and run.counts["failed"] > 0 and run.counts["skipped"] > 0
    assert run.checkpoint() is None          # incomplete windows don't move the checkpoint
    assert any("reported 5 stories but returned 3" in r for r in run.partial_reasons)


def test_hn_hiring_redacts_emails_and_skips_deleted_comments(conn, cur):
    created = int(datetime(2025, 9, 1, 15, tzinfo=timezone.utc).timestamp())
    thread = {"objectID": "500", "title": "Ask HN: Who is hiring? (September 2025)", "created_at_i": created}
    children = [
        {"id": 501, "parent_id": 500, "created_at_i": created + 600, "author": "recruiter",
         "text": "Acme | Remote | We use <i>Claude Code</i>. Email jobs@acme.io"},
        {"id": 502, "parent_id": 500, "created_at_i": created + 700, "text": None},   # deleted
    ]
    http = mock_http(routes({
        "/api/v1/search_by_date": httpx.Response(200, json={"hits": [thread]}),
        "/api/v1/items/500": httpx.Response(200, json={"id": 500, "children": children}),
    }))
    with start_run(conn, "hn_hiring", "threads", "test") as run:
        hn.ingest_hiring(run, cur, Options(since="2025-09", until="2025-09"), http=http)
    row = conn.execute("SELECT * FROM raw_doc WHERE id = 'hnh:501'").fetchone()
    assert "jobs@acme.io" not in row["text"] and "[email]" in row["text"]
    assert "jobs@acme.io" not in row["raw_payload"] and "recruiter" not in row["raw_payload"]
    assert json.loads(row["metrics"]) == {"thread_id": "500", "parent_id": "500"}
    assert run.counts["skipped"] == 1 and run.checkpoint() == "2025-09"


def test_hn_hiring_missing_thread_is_partial(conn, cur):
    http = mock_http(routes({"/api/v1/search_by_date": httpx.Response(200, json={"hits": []})}))
    with start_run(conn, "hn_hiring", "threads", "test") as run:
        hn.ingest_hiring(run, cur, Options(since="2025-09", until="2025-09"), http=http)
    assert run.status == "partial" and run.checkpoint() is None


def test_hn_poll_isolates_bad_items(conn, cur):
    now = int(datetime.now(timezone.utc).timestamp())
    http = mock_http(routes({
        "/v0/topstories.json": httpx.Response(200, json=[1, 2, 3, 4]),
        "/v0/item/1.json": httpx.Response(200, json={"id": 1, "type": "story", "title": "Ok", "time": now, "score": 50}),
        "/v0/item/2.json": httpx.Response(500),
        "/v0/item/3.json": httpx.Response(200, text="null"),   # Firebase answers null for an unavailable item
        "/v0/item/4.json": httpx.Response(200, json={"id": 4, "type": "story", "title": "Gone", "time": now,
                                                     "dead": True}),
    }), retries=0)
    with start_run(conn, "hn_front", "live", "test") as run:
        new = hn.poll_front(run, cur, http=http)
        run.commit()
    assert new == ["hn:1"] and run.status == "partial", run.findings
    assert run.counts["failed"] == 1 and run.counts["skipped"] == 2, run.findings
    assert conn.execute("SELECT value FROM artifact_metric WHERE artifact_id = 'hn:1'").fetchone()[0] == 50
