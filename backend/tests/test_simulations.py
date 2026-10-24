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
    SheetRow,
    compile_formula,
    Table,
    problems,
    to_frontend,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-anthropic-api-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(sims.ai_cache, "PATH", tmp_path / "ai_cache.db")


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
    rows=[SheetRow(key="revenue", cells=[SheetCell(value="Revenue", answer=None), SheetCell(value="100", answer=None),
                                         SheetCell(value="", answer="=[revenue@B]*2")])],
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


def test_row_key_formulas_compile_to_a1():
    rows = {"revenue": 0, "growth": 1, "cash": 3}
    assert compile_formula("=[revenue]*(1+[growth@B])", 2, rows) == "=C2*(1+B3)"
    assert compile_formula("=[cash@prev]+[revenue]", 3, rows) == "=C5+D2"
    assert compile_formula("=SUM([revenue]:[cash])", 1, rows) == "=SUM(B2:B5)"


def test_sheet_with_a_broken_formula_is_rejected():
    sim = valid_sim()
    sim.tasks[0].sheet.rows[0].cells[2].answer = "=[nope]*2"
    assert any("unknown row key" in p for p in problems(sim))
    sim.tasks[0].sheet.rows[0].cells[2].answer = "=[revenue@A]*2"     # column A is the label
    assert any("text used in a calculation" in p for p in problems(sim))



def test_columns_can_be_named_by_label():
    rows = {"revenue": 0, "growth": 1}
    labels = ["Item", "Q3 2024 Actual", "Q4 2024 Forecast"]
    assert compile_formula("=[revenue@Q3 2024 Actual]*(1+[growth@q3 2024 actual])", 2, rows, labels) == "=B2*(1+B3)"


def test_a_shortened_column_label_still_resolves():
    labels = ["Item", "Actual Year 0", "Forecast Year 1"]
    assert compile_formula("=[revenue@Forecast]", 1, {"revenue": 0}, labels) == "=C2"


def test_ai_cache_round_trip():
    from app.services import ai_cache
    assert ai_cache.get("practice", ["Accountant", "Excel"]) is None
    ai_cache.put("practice", ["Accountant", "Excel"], {"title": "A task"})
    assert ai_cache.get("practice", ["Accountant", "Excel"]) == {"title": "A task"}
    assert ai_cache.get("simulation", ["Accountant", "Excel"]) is None     # kinds are kept apart


def test_ai_only_simulation_needs_prompt_review_prompt_review():
    # the usual mix (core, core, prompt, review) is not an AI-only day
    assert any("prompt, review, prompt, review" in p for p in problems(valid_sim(), ai_only=True))
