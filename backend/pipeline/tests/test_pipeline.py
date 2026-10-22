import json

from kompas import snapshot
from kompas.config import snapshot_dir
from kompas.periods import months

from .conftest import add_dosm, add_github_counts, add_hiring

MONTHS = months("2025-07", "2026-06")


def seed(conn, cur):
    # agentic coding: flat in hiring posts, then a jump in June 2026
    for m in MONTHS:
        add_hiring(conn, m, 100, 30 if m == "2026-06" else 5, "Claude Code")
        add_github_counts(conn, cur, m, {"claude-code": 900 if m >= "2026-05" else 100})
    # finance occupations: flat, then accounting demand rises in 2026Q2 (released mid-August)
    quarters = [("2025Q3", "2025-11-14"), ("2025Q4", "2026-02-13"), ("2026Q1", "2026-05-15"),
                ("2026Q2", "2026-08-14"), ("2025Q2", "2025-08-15"), ("2025Q1", "2025-05-16")]
    for q, released in quarters:
        boost = 3 if q == "2026Q2" else 1
        add_dosm(conn, q, released, {"2411": 2000 * boost, "4311": 1500 * boost, "2512": 2000, "9999": 20000})
    conn.commit()


def test_no_look_ahead(conn, cur):
    seed(conn, cur)
    snapshot.build(conn, cur, "2026-07-01", export=True)
    for e in json.loads((snapshot_dir() / "2026-07-01" / "evidence.json").read_text()):
        assert e["published_at"] <= "2026-07-01T00:00:00Z", e["id"]
    # the DOSM 2026Q2 release came out in August, so July must not see it
    snap = json.loads((snapshot_dir() / "2026-07-01" / "snapshot.json").read_text())
    dosm = next(s for s in snap["sources"] if s["id"] == "dosm_jmi")
    assert dosm["latest_period"] == "2026Q1"


def test_ladder_and_ping(conn, cur):
    seed(conn, cur)
    snapshot.build(conn, cur, "2026-07-01", export=True)
    result = snapshot.build(conn, cur, "2026-09-01", export=True)

    concepts = {c["id"]: c for c in json.loads((snapshot_dir() / "2026-09-01" / "concepts.json").read_text())}
    agentic = concepts["agentic-coding"]
    assert agentic["status"] == "Emerging"                 # rung 2 (hiring posts) active
    assert agentic["rungs"]["3"]["level"] == "family"      # Malaysian demand only at family level
    assert concepts["reconciliation"]["status"] == "Act now"

    assert result["changes"] > 0
    changes = json.loads((snapshot_dir() / "2026-09-01" / "changes.json").read_text())["changes"]
    assert any(c["concept_id"] == "reconciliation" and c["to"] == "Act now" for c in changes)


def test_rebuild_is_deterministic(conn, cur):
    seed(conn, cur)
    snapshot.build(conn, cur, "2026-09-01", export=True)
    first = (snapshot_dir() / "2026-09-01" / "concepts.json").read_text()
    snapshot.build(conn, cur, "2026-09-01", export=True)
    assert (snapshot_dir() / "2026-09-01" / "concepts.json").read_text() == first
