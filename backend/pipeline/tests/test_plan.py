import pytest

from kompas import plan

ROUTE = {
    "role": {"isco": "2133", "title": "Environmental and ESG specialist"},
    "steps": [
        {"order": 1, "id": "ghg-accounting", "label": "GHG accounting", "status": "Emerging", "why": "needed",
         "resource": {"title": "GHG Protocol Corporate Standard", "url": "https://ghgprotocol.org/"}},
        {"order": 2, "id": "data-visualisation", "label": "Data visualisation", "status": "Stable", "why": "needed",
         "resource": None},
    ],
}
CATALOG = {"fetched_at": "2026-10-24T00:00:00+00:00", "courses": [
    {"id": "c1", "name": "Greenhouse Gas Emissions Accounting", "slug": "ghg", "workload": "8h", "partners": ["Uni A"], "languages": ["en"]},
    {"id": "c2", "name": "Data Visualisation Basics", "slug": "dataviz", "workload": "6h", "partners": ["Uni B"], "languages": ["en"]},
]}


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def generate(system, contents, schema, client):
        calls.append(system)
        if system is plan.PLAN_INSTRUCTIONS:
            return {"summary": "First emissions, then charts.", "steps": [
                {"skill_id": "ghg-accounting", "goal": "Measure emissions", "learn": ["Scopes"], "practice": "An inventory",
                 "weeks": 3, "queries": ["greenhouse gas emissions"]},
                {"skill_id": "data-visualisation", "goal": "Show data", "learn": ["Charts"], "practice": "A dashboard",
                 "weeks": 99, "queries": ["data visualisation"]},
            ]}, None
        # the picker tries to slip in a course that wasn't a search result
        return {"picks": [{"skill_id": "ghg-accounting", "course_ids": ["c1", "made-up"], "note": "fits"},
                          {"skill_id": "data-visualisation", "course_ids": ["c2"], "note": "fits"}]}, None

    monkeypatch.setattr(plan.llm, "_generate", generate)
    monkeypatch.setattr(plan.coursera, "catalog", lambda conn: CATALOG)
    return calls


def test_plan_keeps_only_real_courses(conn, fake):
    out = plan.build(conn, ROUTE, ROUTE["role"], ["Excel"])
    ghg, viz = out["steps"]
    assert [c["id"] for c in ghg["courses"]] == ["c1"]                 # "made-up" was dropped
    assert ghg["courses"][0]["url"] == "https://www.coursera.org/learn/ghg"
    assert viz["weeks"] == 12                                          # clamped to a sane range
    assert ghg["resource"]["title"] == "GHG Protocol Corporate Standard"
    assert out["summary"] and out["cached"] is False


def test_plan_is_cached(conn, fake):
    plan.build(conn, ROUTE, ROUTE["role"], ["Excel"])
    again = plan.build(conn, ROUTE, ROUTE["role"], ["Excel"])
    assert again["cached"] is True and len(fake) == 2                 # two model calls, once


def test_no_gaps_means_no_plan(conn):
    with pytest.raises(plan.PlanUnavailable):
        plan.build(conn, {"role": ROUTE["role"], "steps": []}, ROUTE["role"], [])


FREE = {"id": "free-1", "title": "Intro to Emissions Accounting", "provider": "MIT OpenCourseWare", "platform": "Free",
        "url": "https://ocw.mit.edu/courses/emissions/", "workload": None, "free": True}


def test_free_courses_come_first_and_are_flagged(conn, fake, monkeypatch):
    monkeypatch.setattr(plan.tavily, "enabled", lambda: True)
    monkeypatch.setattr(plan.tavily, "search", lambda queries, limit: [FREE] if "greenhouse gas emissions" in queries else [])

    def generate(system, contents, schema, client):
        if system is plan.PLAN_INSTRUCTIONS:
            return {"summary": "s", "steps": [
                {"skill_id": "ghg-accounting", "goal": "g", "learn": ["x"], "practice": "p", "weeks": 3,
                 "queries": ["greenhouse gas emissions"]},
                {"skill_id": "data-visualisation", "goal": "g", "learn": ["x"], "practice": "p", "weeks": 2,
                 "queries": ["data visualisation"]}]}, None
        return {"picks": [{"skill_id": "ghg-accounting", "course_ids": ["c1", "free-1"], "note": "n"},
                          {"skill_id": "data-visualisation", "course_ids": ["c2"], "note": "n"}]}, None

    monkeypatch.setattr(plan.llm, "_generate", generate)
    ghg, viz = plan.build(conn, ROUTE, ROUTE["role"], ["Excel"])["steps"]
    assert [c["id"] for c in ghg["courses"]] == ["free-1", "c1"] and ghg["courses"][0]["free"] is True
    assert [c["id"] for c in viz["courses"]] == ["c2"]


def test_free_search_failing_does_not_break_the_plan(conn, fake, monkeypatch):
    from kompas.http import FetchError

    def boom(queries, limit):
        raise FetchError("client", "Tavily answered 401", "https://api.tavily.com/search", 401)

    monkeypatch.setattr(plan.tavily, "enabled", lambda: True)
    monkeypatch.setattr(plan.tavily, "search", boom)
    out = plan.build(conn, ROUTE, ROUTE["role"], ["Excel"])
    assert [c["id"] for c in out["steps"][0]["courses"]] == ["c1"] and "unavailable" in out["note"]
