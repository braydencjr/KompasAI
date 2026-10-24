import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.genai import types

from kompas import cv, journey, llm
from kompas.api import create_app

SAMPLE = (Path(__file__).resolve().parent / "fixtures" / "sample-cv.txt").read_text()


class FakeGemini:
    """Stands in for genai.Client: returns a canned structured-output answer."""

    def __init__(self, answer: dict, finish_reason=types.FinishReason.STOP):
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)
        self._answer, self._finish = answer, finish_reason

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self._answer), prompt_feedback=None,
                               candidates=[SimpleNamespace(finish_reason=self._finish)])


ANSWER = {
    "summary": "Accounts executive with five years in shared services.",
    "jobs": [{"title": "Accounts Executive", "employer": "Northwind Shared Services", "period": "2022 - present",
              "occupation": "3313", "quote": "Accounts Executive, Northwind Shared Services"}],
    "categories": [
        {"category": "Finance and accounting", "skills": [
            {"name": "Invoice matching", "quote": "match them against purchase orders and goods receipts"},
            {"name": "BlackLine", "quote": "BlackLine"},
            # invented quote: must be discarded
            {"name": "Python", "quote": "automated reconciliations with Python scripts"}]},
    ],
}


def test_llm_semantic_matches_are_kept_and_invented_quotes_dropped(conn, cur):
    fake = FakeGemini(ANSWER)
    profile = cv.analyse(SAMPLE, cur, conn, client=fake)
    names = {u["name"]: u for u in profile["unrecognised"]}

    assert profile["method"] == "llm" and profile["model"] == "gemini-2.5-flash"
    assert "Python" not in names                                # quote isn't in the CV
    assert profile["discarded_unverified"] == 1
    assert names["BlackLine"]["group"] == "Finance and accounting"   # each skill keeps its category
    assert profile["jobs"][0]["occupation"]["title"] == "Accounting associate"
    assert fake.calls[0]["model"] == "gemini-2.5-flash"


def test_dictionary_safety_net_adds_explicit_tools(conn, cur):
    profile = cv.analyse(SAMPLE, cur, conn, client=FakeGemini(ANSWER))
    ids = {s["id"]: s for s in profile["skills"]}
    assert ids["sap-erp"]["found_by"] == "dictionary"          # "SAP S/4HANA" named explicitly
    assert "SAP S/4HANA" in ids["sap-erp"]["quote"]


def test_without_api_key_falls_back_to_dictionary(conn, cur, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    profile = cv.analyse(SAMPLE, cur, conn)
    assert profile["method"] == "dictionary"
    assert profile["llm_note"] == "no Gemini API key configured"
    assert {"excel", "power-bi", "reconciliation", "month-end-close", "accounts-payable"} <= {s["id"] for s in profile["skills"]}


def test_safety_block_falls_back(conn, cur):
    profile = cv.analyse(SAMPLE, cur, conn, client=FakeGemini(ANSWER, finish_reason=types.FinishReason.SAFETY))
    assert profile["method"] == "dictionary"
    assert profile["llm_note"] == "Gemini declined to process this resume"


def test_exposure_and_best_fit_roles(conn, cur):
    profile = cv.analyse(SAMPLE, cur, conn, client=FakeGemini(ANSWER))
    exposed = {e["id"]: e for e in profile["exposed"]}
    assert "document-ai" in exposed                            # reaches accounts payable
    assert exposed["document-ai"]["because"][0]["skill"] == "Accounts payable"

    roles = profile["roles"]
    held = {s["id"] for s in profile["skills"]}
    assert roles and roles == sorted(roles, key=lambda r: r["match"], reverse=True)
    for r in roles:
        assert not held & {g["id"] for g in r["gaps"]}
        assert {h["id"] for h in r["have"]} <= held
        assert 0 < r["match"] <= 70                                     # claimed skills count 0.7 (FR-4.2)
        assert sum(b["coverage"] > 0 for b in r["breakdown"]) == len(r["have"])


def _profile_with(conn, cur, monkeypatch, text):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    return cv.analyse(text, cur, conn)


def test_roles_you_already_cover_are_best_fits(conn, cur):
    # the bug this guards: roles with no gaps were dropped, so a data scientist was shown "Database administrator"
    have = {cid: "claimed" for cid, _ in journey.role_skills(cur, "4311")}       # every skill of the clerk role
    roles = journey.score_roles(cur, journey.Statuses.latest(conn), journey.Profile(skills=have), {})
    assert roles[0]["isco"] == "4311" and roles[0]["covered"] and roles[0]["match"] == 70


def test_capabilities_are_not_listed_as_skills(conn, cur, monkeypatch):
    text = "Analyst. Set up document AI to extract invoice data, then reconciled accounts in Excel every month."
    profile = _profile_with(conn, cur, monkeypatch, text)
    kinds = {s["id"]: cur.concepts[s["id"]].kind for s in profile["skills"]}
    assert set(kinds.values()) == {"skill"}
    assert all(cur.concepts[t["id"]].kind == "capability" for t in profile["ai_tools"])


def test_unmeasured_status_is_null_not_stable(conn, cur, monkeypatch):
    profile = _profile_with(conn, cur, monkeypatch, SAMPLE)     # empty test DB: no snapshot yet
    assert profile["snapshot"] is None
    assert all(s["status"] is None for s in profile["skills"])
    assert all(r["family_status"] is None for r in profile["roles"])
    assert profile["trace"]["signals"]["measured"] == 0
    assert profile["trace"]["reader"]["note"] == "no Gemini API key configured"


def test_summary_that_names_the_person_is_dropped():
    text = "Wei Ling Tan\nData Scientist, Kampung Analytics\nBuilt forecasting models in Python"
    known = {"data", "scientist", "python", "forecasting"}
    assert cv.checked_summary("Wei Ling built forecasting models in Python.", text, known) is None
    assert cv.checked_summary("You built forecasting models in Python.", text, known) is not None
    # a job title on the first line isn't a name
    assert cv.checked_summary("You work as a data scientist.", "Data Scientist\nPython", known) is not None


def test_match_formula(conn, cur):
    # Accountant: month-end close (1.0), reconciliation/excel/sap/modelling/GHG/standards/AI risk (0.5 each)
    have = {"month-end-close": "claimed", "reconciliation": "claimed", "excel": "claimed", "sap-erp": "claimed"}
    st = journey.Statuses.latest(conn)
    roles = {r["isco"]: r for r in journey.score_roles(cur, st, journey.Profile(skills=have), {})}
    assert roles["2411"]["match"] == round(100 * 0.7 * (1.0 + 0.5 * 3) / (1.0 + 0.5 * 7))


def test_no_personal_data_in_the_prompt_contract(cur):
    assert "Never include the person's name" in llm._system(cur)
    props = llm._schema(cur)["properties"]
    assert set(props) == {"summary", "jobs", "categories"}         # nowhere to put a name, age or email


def test_docx_text_extraction():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   '<w:document><w:body><w:p><w:r><w:t>Power BI &amp; SQL</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>Month-end close</w:t></w:r></w:p></w:body></w:document>')
    assert cv.extract_text("cv.docx", buf.getvalue()).split("\n")[:2] == ["Power BI & SQL", "Month-end close"]


def test_upload_endpoint(conn, cur, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    client = TestClient(create_app(live_mode=False, replay=False))
    r = client.post("/profile/extract", files={"file": ("cv.txt", SAMPLE.encode(), "text/plain")})
    assert r.status_code == 200 and r.json()["file"] == "cv.txt"
    assert client.post("/profile/extract", files={"file": ("cv.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post("/profile/extract", files={"file": ("cv.txt", b"too short", "text/plain")}).status_code == 422
