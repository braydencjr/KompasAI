from fastapi.testclient import TestClient

from kompas import db, snapshot
from kompas.api import create_app
from kompas.feed import refresh_live
from kompas.periods import utcnow

from .test_pipeline import seed


def test_api_end_to_end(conn, cur, monkeypatch):
    seed(conn, cur)
    snapshot.build(conn, cur, "2026-07-01")
    snapshot.build(conn, cur, "2026-09-01")

    # a live repo observation, then a feed refresh, as the GitHub poller would do
    db.upsert_doc(conn, {
        "id": "gh:example/agent-skills", "source": "github", "kind": "repo", "url": "https://github.com/example/agent-skills",
        "title": "example/agent-skills", "text": "Skills for coding agents", "topics": ["agent-skills"],
        "published_at": utcnow(), "period": utcnow()[:7], "metrics": {"stars": 500},
    })
    db.record_metric(conn, "gh:example/agent-skills", "stars", 500)
    conn.commit()
    from kompas.tag import retag
    retag(conn, cur)
    events = refresh_live(conn, snapshot.PARAMS)
    assert [e["type"] for e in events] == ["new"]

    client = TestClient(create_app(live_mode=False, replay=False))
    assert client.get("/health").json()["latest_snapshot"]["id"] == "2026-09-01"
    assert client.get("/concepts/reconciliation").json()["status"] == "Act now"
    assert client.get("/concepts/reconciliation/evidence").json()["evidence"]

    # for one clicked task: only records that bear on it (words, since no model is reachable in tests)
    from kompas import evidence_pick
    monkeypatch.setattr(evidence_pick.llm, "_generate", lambda *args: (None, "no Gemini API key configured"))
    picked = client.get("/concepts/reconciliation/evidence",
                        params={"task": "Match bank statements", "why": "Statement matching is automated"}).json()
    assert picked["task"] == "Match bank statements" and picked["method"] == "keywords"
    assert picked["specific"] == bool(picked["evidence"]) and all(e["why"] for e in picked["evidence"])

    feed = client.get("/feed").json()
    assert feed["items"][0]["concepts"][0]["id"] == "agentic-coding"
    assert feed["items"][0]["stars"] == 500
    assert feed["items"][0]["description"] == "Skills for coding agents"

    r = client.post("/match", json={"skills": [{"id": "reconciliation"}], "route": ["agentic-coding"]})
    body = r.json()
    card = body["signals"][0]
    assert card["concept_id"] == "agentic-coding"
    assert card["relation_label"] == "On your learning route"
    assert card["headline"] == "Agentic coding workflows is getting attention"
    assert card["meaning"] and card["action"]
    assert card["items"][0]["title"] == "example/agent-skills"
    assert card["ladder"]["abroad"] is True                 # rung 2 active in the seeded hiring posts
    assert card["ladder"]["malaysia"] in (None, "family")   # Malaysian demand only at family level
    assert body["summary"]
    assert any(c["concept_id"] == "reconciliation" for c in body["ping"])

    assert client.post("/match", json={"skills": [{"id": "made-up-skill"}]}).status_code == 422



def test_rescore_recomputes_market_data_and_keeps_what_the_cv_said(conn, cur):
    seed(conn, cur)
    snapshot.build(conn, cur, "2026-09-01")
    client = TestClient(create_app(live_mode=False, replay=False))
    stale = {
        "file": "cv.pdf", "summary": "Kept as is", "jobs": [{"title": "Analyst"}],
        "skills": [{"id": "reconciliation", "label": "Reconciliation", "status": "Declining", "quote": "Monthly recs",
                    "found_by": "llm"},
                   {"id": "not-a-concept", "quote": "x"}],
        "roles": [], "signals": {}, "snapshot": {"id": "old", "as_of": "2020-01-01"},
        "trace": {"text": {"chars": 10, "lines": 1}},
    }
    r = client.post("/profile/rescore", json=stale)
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["summary"] == "Kept as is" and fresh["jobs"] == stale["jobs"]
    assert [s["id"] for s in fresh["skills"]] == ["reconciliation"]   # unknown concepts are dropped
    assert fresh["skills"][0]["quote"] == "Monthly recs"               # the CV's evidence is kept
    assert fresh["skills"][0]["status"] == "Act now"                   # the status comes from today's snapshot
    assert fresh["snapshot"]["id"] == "2026-09-01"
    assert fresh["trace"]["text"] == {"chars": 10, "lines": 1} and "roles" in fresh["trace"]
    assert client.post("/profile/rescore", json={"nope": 1}).status_code == 422


def test_snapshots_build_endpoint(conn, cur):
    seed(conn, cur)
    client = TestClient(create_app(live_mode=False, replay=False))
    r = client.post("/snapshots/build?as_of=2026-10-24")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["snapshot"]["id"] == "2026-10-24"
    assert client.get("/snapshots/latest").json()["id"] == "2026-10-24"

