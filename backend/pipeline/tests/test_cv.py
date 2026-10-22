import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.genai import types

from kompas import cv, llm
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
    "skills": [
        # semantic match: the CV never says "accounts payable" in this line
        {"name": "Invoice matching", "skill_id": "accounts-payable",
         "quote": "match them against purchase orders and goods receipts"},
        {"name": "Variance dashboards", "skill_id": "data-visualisation",
         "quote": "Built a monthly variance dashboard in Power BI"},
        {"name": "BlackLine", "skill_id": "none", "quote": "BlackLine"},
        # invented quote: must be discarded
        {"name": "Python", "skill_id": "python", "quote": "automated reconciliations with Python scripts"},
    ],
}


def test_llm_semantic_matches_are_kept_and_invented_quotes_dropped(conn, cur):
    fake = FakeGemini(ANSWER)
    profile = cv.analyse(SAMPLE, cur, conn, client=fake)
    ids = {s["id"]: s for s in profile["skills"]}

    assert profile["method"] == "llm" and profile["model"] == "gemini-2.5-flash"
    assert ids["accounts-payable"]["found_by"] == "llm"
    assert ids["data-visualisation"]["quote"] == "Built a monthly variance dashboard in Power BI"
    assert "python" not in ids                                  # quote isn't in the CV
    assert profile["discarded_unverified"] == 1
    assert profile["unrecognised"] == [{"name": "BlackLine", "quote": "BlackLine"}]
    assert profile["jobs"][0]["occupation"]["title"] == "Accounting associate"
    # the closed lists are enforced by the schema sent to the model
    schema = fake.calls[0]["config"].response_json_schema
    assert "accounts-payable" in schema["properties"]["skills"]["items"]["properties"]["skill_id"]["enum"]
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
    assert profile["llm_note"] == "Gemini declined to process this CV"


def test_exposure_and_best_fit_roles(conn, cur):
    profile = cv.analyse(SAMPLE, cur, conn, client=FakeGemini(ANSWER))
    exposed = {e["id"]: e for e in profile["exposed"]}
    assert "document-ai" in exposed                            # reaches accounts payable
    assert exposed["document-ai"]["because"][0]["skill"] == "Accounts payable"

    roles = profile["roles"]
    held = {s["id"] for s in profile["skills"]}
    assert roles and roles == sorted(roles, key=lambda r: r["match"], reverse=True)
    for r in roles:
        assert r["gaps"] and not held & {g["id"] for g in r["gaps"]}   # a best fit always has something to learn
        assert {h["id"] for h in r["have"]} <= held
        assert 0 < r["match"] <= 70                                     # claimed skills count 0.7 (FR-4.2)


def test_match_formula(cur):
    # Accountant: month-end close (1.0), reconciliation/excel/sap/modelling/GHG/standards/AI risk (0.5 each)
    roles = {r["isco"]: r for r in cv.match_roles(cur, {"month-end-close", "reconciliation", "excel", "sap-erp"}, {})}
    assert roles["2411"]["match"] == round(100 * 0.7 * (1.0 + 0.5 * 3) / (1.0 + 0.5 * 7))


def test_no_personal_data_in_the_prompt_contract(cur):
    assert "Never extract or mention the person's name" in llm._system(cur)
    props = llm._schema(cur)["properties"]
    assert set(props) == {"summary", "jobs", "skills"}         # nowhere to put a name, age or email


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
