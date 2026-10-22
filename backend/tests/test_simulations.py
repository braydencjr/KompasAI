import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import simulations as sims
from app.services.simulations import (
    AiReply,
    Calendar,
    Code,
    CodeTest,
    Feedback,
    GenSimulation,
    GenTask,
    Meeting,
    BusyBlock,
    Prompt,
    Review,
    RubricItem,
    Segment,
    Sheet,
    SheetCell,
    SheetColumn,
    Table,
    problems,
    to_frontend,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-anthropic-api-key")
    sims._cache.clear()


def task(tool, **parts):
    base = dict(
        id=f"t-{tool}",
        tool=tool,
        title="Task",
        competency="Skill",
        gap=None,
        minutes=5,
        from_name="Farid Hassan",
        from_role="CFO",
        subject="Subject",
        brief="Brief",
        requirements=["Do it"],
        feedback=Feedback(high="Great", mid="OK", low="Not yet"),
        ai_name="Forecast Assistant" if tool in ("prompt", "review") else None,
        why="AI is changing this" if tool in ("prompt", "review") else None,
        sheet=None,
        calendar=None,
        code=None,
        prompt=None,
        review=None,
    )
    base.update(parts)
    return GenTask(**base)


def reply(text):
    return AiReply(text=text, table=None, steps=None, note=None)


SHEET = Sheet(
    name="f.xlsx",
    columns=[SheetColumn(label="Item", fmt="text"), SheetColumn(label="Q3", fmt="rm"), SheetColumn(label="Q4", fmt="rm")],
    rows=[[SheetCell(value="Revenue", answer=None), SheetCell(value="100", answer=None), SheetCell(value="", answer="=B2*2")]],
)

CALENDAR = Calendar(
    busy=[BusyBlock(person="Farid", day=0, hours=[9, 10])],
    events=[
        Meeting(id="prep", title="Prep", people=["Farid"], deadline_day=None, deadline_hour=None, deadline_label=None, after=None),
        Meeting(id="review", title="Review", people=["Farid"], deadline_day=3, deadline_hour=12, deadline_label="Thu 12:00", after="prep"),
    ],
)

PROMPT = Prompt(
    rubric=[RubricItem(label=l, keywords=[l.lower()]) for l in ("Context", "Numbers", "Format")],
    weak=reply("What do you need?"),
    partial=reply("Here's a guess."),
    strong=reply("Here it is."),
)

REVIEW = Review(
    artifact_name="Draft",
    format="prose",
    source_title="Model",
    source=Table(columns=["A"], rows=[["1"]]),
    segments=[Segment(text="Fine.", issue=None), Segment(text="Wrong.", issue="x"), Segment(text="Made up.", issue="y")],
    verdict="send back",
)


def valid_sim():
    return GenSimulation(
        setting="Monday",
        welcome_from="Farid Hassan",
        welcome_text="Hi",
        tasks=[task("sheet", sheet=SHEET), task("calendar", calendar=CALENDAR), task("prompt", prompt=PROMPT), task("review", review=REVIEW)],
    )


def test_valid_simulation_has_no_problems():
    assert problems(valid_sim()) == []


def test_wrong_task_order_is_rejected():
    sim = valid_sim()
    sim.tasks = [sim.tasks[2], sim.tasks[1], sim.tasks[0], sim.tasks[3]]
    assert any("task order" in p for p in problems(sim))


def test_unsolvable_calendar_is_rejected():
    busy_all_week = [BusyBlock(person="Farid", day=d, hours=list(range(9, 17))) for d in range(5)]
    sim = valid_sim()
    sim.tasks[1].calendar = Calendar(busy=busy_all_week, events=CALENDAR.events)
    assert any("no valid arrangement" in p for p in problems(sim))


def test_code_tests_must_be_json():
    code = Code(fn="f", starter="function f(){}", solution="function f(){return 1}", tests=[CodeTest(label="x", args_json="nope", expected_json="1")])
    sim = valid_sim()
    sim.tasks[0] = task("code", code=code)
    assert any("invalid JSON" in p for p in problems(sim))


def test_conversion_matches_frontend_shape():
    out = to_frontend(valid_sim(), "fpa-analyst", "FP&A Analyst")
    sheet, cal, prompt, review = out["tasks"]
    assert out["generated"] is True and out["welcome"] == {"from": "Farid Hassan", "text": "Hi"}
    # answer cells carry the formula; the frontend computes the expected value
    assert sheet["sheet"]["rows"][0] == ["Revenue", "100", {"solution": "=B2*2"}]
    assert cal["busy"]["Farid"][0] == [9, 10]
    assert cal["events"][1] == {
        "id": "review",
        "title": "Review",
        "people": ["Farid"],
        "deadline": {"day": 3, "hour": 12, "label": "Thu 12:00"},
        "after": "prep",
    }
    assert prompt["replies"]["weak"] == {"text": "What do you need?"}
    assert review["segments"][0] == {"text": "Fine."}
    assert review["source"]["title"] == "Model"


def test_status_reports_ai_off_with_placeholder_key():
    assert client.get("/api/simulations/status").json() == {"ai": False}


def test_generate_returns_503_without_a_key():
    r = client.post("/api/simulations", json={"role_id": "x", "title": "Analyst"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_brief_returns_503_without_a_key():
    r = client.post(
        "/api/simulations/brief",
        json={"ai_name": "A", "field": "Finance", "task": "t", "rubric": [{"label": "x", "keywords": ["x"]}], "prompt": "hi"},
    )
    assert r.status_code == 503
