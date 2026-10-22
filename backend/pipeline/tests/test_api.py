from fastapi.testclient import TestClient

from kompas import db, snapshot
from kompas.api import create_app
from kompas.feed import refresh_live
from kompas.periods import utcnow

from .test_pipeline import seed


def test_api_end_to_end(conn, cur):
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
