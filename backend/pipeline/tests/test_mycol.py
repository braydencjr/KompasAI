import json

import pytest

from kompas import ingest
from kompas.connectors import mycol
from kompas.ingest import Options

COVER = "CRITICAL OCCUPATIONS LIST (MyCOL) 2022/2023: SECTORS DEEP DIVE"
LIST_PAGE = """53
The MyCOL 2022/2023 consists of 3 critical occupations at the MASCO 4-digit level (Table 9).
Table 9: 2022/2023 Final Critical Occupations List
MASCO 4D Job Title
1211 Finance Managers
2512 Software Developers
8332 Heavy Truck And Lorry Drivers
"""
NEW_PAGE = """54
Table 10: Occupations that are new in the MyCOL
MASCO 4D Job Title
8332 Heavy Truck And Lorry Drivers

Table 11: Occupations that have appeared in every MyCOL
MASCO 4D Job Title
1211 Finance Managers
2512 Software Developers
"""
APPENDIX = """185
APPENDIX 1: TOP-DOWN SHORTAGE OCCUPATIONS
MASCO
Code
1121 Managing Directors And Chief Executives 12 7 58%
1211 Finance Managers 12 6 50%
2121 Mathematicians, Actuaries And Statisticians 3 2 67%
2529 Unclassified 1 1 100%
4311 Accounting And Book-Keeping Clerks 11 6 55%
"""
END = "190\nAPPENDIX 2: ECONOMIC SECTORS COVERED IN 2022/2023 MyCOL\n1234 Not A Shortage Row 1 1 100%"
PAGES = [COVER, LIST_PAGE, NEW_PAGE, APPENDIX, END]


def test_report_is_parsed():
    ed, errors = mycol.parse_report(PAGES)
    assert errors == []
    assert ed.edition == "2022/2023" and ed.stated_count == 3
    assert [c for c, _, _ in ed.critical] == ["1211", "2512", "8332"]
    assert ed.new == {"8332"} and ed.every == {"1211", "2512"}
    assert [s[0] for s in ed.shortage] == ["1121", "1211", "2121", "2529", "4311"]   # stops at Appendix 2
    assert ed.shortage[1] == ("1211", "Finance Managers", 12, 6, 50, 4)


@pytest.mark.parametrize("change, message", [
    (lambda p: p[:1] + [p[1].replace("consists of 3", "consists of 4")] + p[2:], "says 4 critical occupations but its table lists 3"),
    (lambda p: p[:1] + [p[1].replace("Final Critical", "Draft")] + p[2:], "no 'Final Critical Occupations List'"),
    (lambda p: p[:3] + [p[3].replace("12 6 50%", "12 6 80%")] + p[4:], "shows 80% but 6/12 is 50%"),
    (lambda p: p[:3] + [p[3].replace("3 2 67%", "3 5 67%")] + p[4:], "5 of 3 indicators passing"),
    (lambda p: p[:3] + [""] + p[4:], "no Appendix 1 shortage-indicator rows"),
    (lambda p: ["A report", p[1].replace("The MyCOL 2022/2023", "The list"), "notes"] + p[3:],
     "no 'MyCOL YYYY/YYYY' edition"),
])
def test_structural_problems_are_errors(change, message):
    _, errors = mycol.parse_report(change(list(PAGES)))
    assert any(message in e for e in errors), errors


def test_code_map_cross_check(cur):
    ed, _ = mycol.parse_report(PAGES)
    titles = {s[0]: s[1] for s in ed.shortage} | {c: t for c, t, _ in ed.critical}
    confirmed, findings = mycol.check_code_map(cur, titles, ed.edition)
    assert {"1211", "2512", "4311"} <= set(confirmed)          # "Book-Keeping" matches "bookkeeping"
    assert any("is MASCO 1121 in MyCOL 2022/2023 (MASCO 2020), not 1120" in f for f in findings)
    assert any("not 2120" in f for f in findings)
    assert not any("2529" in f for f in findings)                # an "Unclassified" label says nothing


def manifest(tmp_path, **override):
    row = {"edition": "2022/2023", "file": "mycol.pdf", "published_date": "2023-09-21", "source_url": "",
           "date_basis": "upload time in the file name"} | override
    (tmp_path / "mycol.pdf").write_bytes(b"%PDF-1.7 stand-in")
    path = tmp_path / "mycol_editions.csv"
    path.write_text(",".join(row) + "\n" + ",".join(row.values()) + "\n")
    return path


def test_import_is_idempotent_and_dated_by_the_manifest(conn, cur, tmp_path, monkeypatch):
    monkeypatch.setattr(mycol, "read_pdf", lambda data: PAGES)
    path = manifest(tmp_path)
    out = ingest.run_stream(conn, cur, "mycol", "editions", Options(file=path))
    assert out["status"] == "ok" and out["counts"]["inserted"] == 3 + 5
    doc = conn.execute("SELECT * FROM raw_doc WHERE id = 'mycol:2022/2023:8332'").fetchone()
    assert doc["published_at"] == "2023-09-21T15:59:59Z" and doc["period"] == "2023-09"
    assert json.loads(doc["metrics"])["new_in_edition"] is True
    assert json.loads(doc["raw_payload"])["date_basis"] == "upload time in the file name"
    sh = json.loads(conn.execute("SELECT metrics FROM raw_doc WHERE id = 'mycolsh:2022/2023:1211'").fetchone()[0])
    assert sh == {"masco_code": "1211", "edition": "2022/2023", "indicators_available": 12, "indicators_passing": 6,
                  "percent_passing": 50, "on_final_list": True}
    findings = [r["message"] for r in conn.execute("SELECT message FROM ingest_error WHERE category = 'mapping'")]
    assert len(findings) == 2
    assert ingest.run_stream(conn, cur, "mycol", "editions", Options(file=path))["status"] == "no_change"


def test_manifest_and_edition_mismatches_are_invalid(conn, cur, tmp_path, monkeypatch):
    monkeypatch.setattr(mycol, "read_pdf", lambda data: PAGES)
    out = ingest.run_stream(conn, cur, "mycol", "editions", Options(file=manifest(tmp_path, date_basis="")))
    assert out["status"] == "invalid" and "date_basis is empty" in out["error"]
    out = ingest.run_stream(conn, cur, "mycol", "editions", Options(file=manifest(tmp_path, edition="2024/2025")))
    assert out["status"] == "invalid" and "is MyCOL 2022/2023, but the manifest says 2024/2025" in out["error"]
    assert conn.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 0


def test_real_report_if_present(cur):
    """Parses the actual 2022/2023 PDF when it's in data/manual/ (skipped otherwise)."""
    from kompas import config

    pdf = config.MANUAL_DIR / "Critical-Occupations-List-MyCOL-20222023-1695267153.pdf"
    if not pdf.exists():
        pytest.skip("MyCOL 2022/2023 PDF not downloaded")
    ed, errors = mycol.parse_report(mycol.read_pdf(pdf.read_bytes()))
    assert errors == [] and ed.edition == "2022/2023"
    assert len(ed.critical) == ed.stated_count == 37 and len(ed.shortage) == 183 and len(ed.new) == 9
