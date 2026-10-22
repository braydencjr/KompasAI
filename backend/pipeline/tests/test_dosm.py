import json

import httpx
import pytest

from kompas import db, ingest, snapshot
from kompas.connectors import dosm
from kompas.ingest import DatasetInvalid, Options, start_run

from .conftest import jmi_workbook, mock_http

HEADER = "period,release_date,masco_code,occupation,offerings,source_url\n"
URL = "https://www.dosm.gov.my/portal-main/release-content/big-data-analytics-job-market-insights-q22026"


def csv_text(*lines: str) -> str:
    return HEADER + "".join(f"{l}\n" for l in lines)


GOOD = csv_text(
    f"2026Q1,2026-06-25,2411,Accountants,\"21,500\",{URL}",
    f"2026Q1,2026-06-25,4311,Accounts clerks,9000,{URL}",
    f"2026Q2,2026-08-18,2411,Accountants,22067,{URL}",
    f"2026Q2,2026-08-18,4311,Accounts clerks,9100,{URL}",
)


# ---------- manual CSV ----------


def test_valid_csv_passes(cur):
    rows, errors, warnings = dosm.validate_csv(GOOD, cur)
    assert errors == [] and warnings == [] and len(rows) == 4 and rows[0].offerings == 21500


@pytest.mark.parametrize("line, message", [
    (f"2026-Q2,2026-08-18,2411,Accountants,1,{URL}", "is not YYYYQn"),
    (f"2026Q2,18/08/2026,2411,Accountants,1,{URL}", "is not YYYY-MM-DD"),
    (f"2026Q2,2026-06-01,2411,Accountants,1,{URL}", "is not after the end of 2026Q2"),
    (f"2026Q2,2026-08-18,241,Accountants,1,{URL}", "not a 4-digit MASCO code"),
    (f"2026Q2,2026-08-18,2411,,1,{URL}", "occupation is empty"),
    (f"2026Q2,2026-08-18,2411,Accountants,-5,{URL}", "not a whole non-negative number"),
    (f"2026Q2,2026-08-18,2411,Accountants,12.5,{URL}", "not a whole non-negative number"),
    ("2026Q2,2026-08-18,2411,Accountants,1,http://example.com", "not an https URL"),
])
def test_invalid_rows_reject_the_file(cur, line, message):
    _, errors, _ = dosm.validate_csv(csv_text(line), cur)
    assert any(message in e for e in errors), errors


def test_duplicates_and_conflicting_release_dates_are_errors(cur):
    _, errors, _ = dosm.validate_csv(csv_text(
        f"2026Q2,2026-08-18,2411,Accountants,1,{URL}",
        f"2026Q2,2026-08-18,2411,Accountants,2,{URL}",
        f"2026Q2,2026-08-19,4311,Clerks,3,{URL}",
    ), cur)
    assert any("duplicate 2026Q2 2411" in e for e in errors)
    assert any("two release dates" in e for e in errors)
    assert dosm.validate_csv(HEADER, cur)[1] == ["no data rows"]
    assert "missing columns" in dosm.validate_csv("period,offerings\n2026Q2,1\n", cur)[1][0]


def test_missing_figures_unmapped_codes_and_gaps_are_warnings(cur):
    rows, errors, warnings = dosm.validate_csv(csv_text(
        f"2025Q3,2026-04-28,2411,Accountants,100,{URL}",
        f"2026Q1,2026-06-25,2411,Accountants,-,{URL}",
        f"2026Q2,2026-08-18,2411,Accountants,120,{URL}",
        f"2026Q2,2026-08-18,9999,Something,50,{URL}",
    ), cur)
    assert errors == []
    assert [r.masco_code for r in rows if r.period == "2026Q1"] == []            # "-" is not zero
    assert any("no offerings figure for 2026Q1 2411" in w for w in warnings)
    assert any("MASCO 9999 isn't in occupation_code_map.csv" in w for w in warnings)
    assert any("no rows for 2025Q4, 2026Q1" in w for w in warnings)
    assert any("occupations listed change between 2025Q3 and 2026Q2" in w for w in warnings)


def run_csv(conn, cur, path, **kw):
    return ingest.run_stream(conn, cur, "dosm_jmi", "occupations", Options(file=path, **kw))


def test_csv_import_is_atomic_idempotent_and_keeps_first_published_figures(conn, cur, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(GOOD + f"2026Q2,2026-08-18,2512,Developers,lots,{URL}\n")
    assert run_csv(conn, cur, bad)["status"] == "invalid"
    assert conn.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 0

    path = tmp_path / "dosm_jmi.csv"
    path.write_text(GOOD)
    assert run_csv(conn, cur, path)["status"] == "ok"
    doc = conn.execute("SELECT * FROM raw_doc WHERE id = 'dosm:2026Q2:2411'").fetchone()
    assert doc["published_at"] == "2026-08-18T15:59:59Z"                     # end of release day, Malaysia
    assert json.loads(doc["raw_payload"])["line"] == 4
    assert run_csv(conn, cur, path)["status"] == "no_change"                 # same file: nothing to do

    path.write_text(GOOD.replace("22067", "22500"))                          # DOSM revised a figure
    assert run_csv(conn, cur, path)["status"] == "no_change"
    assert json.loads(conn.execute("SELECT metrics FROM raw_doc WHERE id = 'dosm:2026Q2:2411'").fetchone()[0])["offerings"] == 22067
    vintages = [r[0] for r in conn.execute("SELECT value FROM artifact_metric WHERE artifact_id = 'dosm:2026Q2:2411'")]
    assert vintages == [22500]   # same release date, so the revision replaces that vintage's observation
    assert any(r["category"] == "revision" for r in conn.execute("SELECT category FROM ingest_error"))


def test_dry_run_validates_without_storing(conn, cur, tmp_path):
    path = tmp_path / "dosm_jmi.csv"
    path.write_text(GOOD)
    assert run_csv(conn, cur, path, dry_run=True)["status"] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM raw_doc").fetchone()[0] == 0


# ---------- release workbooks ----------

QUARTERS = ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]


def groups(total_q2=1000, elementary=("-", "-", 0, 40)):
    rows = {"Jumlah": dict(zip(QUARTERS, [960, 960, 960, total_q2]))}   # the reported groups add up
    for label, v in [("Managers", 100), ("Professionals", 400), ("Technicians and associate professionals", 200),
                     ("Clerical support workers", 100), ("Service and sales workers", 80),
                     ("Skilled agricultural, forestry, livestock and fishery workers", 0),
                     ("Craft and related trades workers", 40), ("Plant and machine operators and assemblers", 40)]:
        rows[label] = dict.fromkeys(QUARTERS, v)
    rows["Elementary Occupations"] = dict(zip(QUARTERS, elementary))
    rows["Unclassified"] = dict.fromkeys(QUARTERS, "-")
    return rows


def test_workbook_major_group_table_is_parsed():
    values = dosm.parse_groups_xlsx(jmi_workbook(groups()))
    assert values[("2026Q2", "TOTAL")] == 1000 and values[("2026Q2", "2")] == 400
    assert values[("2025Q3", "9")] is None and values[("2026Q1", "9")] == 0    # "-" is missing, 0 is zero
    assert ("2026Q2", "X") in values and values[("2026Q2", "X")] is None
    assert {p for p, _ in values} == set(QUARTERS)                               # monthly columns ignored


def test_workbook_layout_problems_are_caught():
    with pytest.raises(dosm.TableError, match="no job-offerings-by-occupation table"):
        dosm.parse_groups_xlsx(jmi_workbook(groups(), title_suffix="by State"))
    # 2024 and early 2025 workbooks title the same table "by Occupation"
    assert dosm.parse_groups_xlsx(jmi_workbook(groups(), title_suffix="by Occupation"))[("2026Q2", "2")] == 400
    rows = groups()
    rows["Astronauts"] = dict.fromkeys(QUARTERS, 1)
    with pytest.raises(dosm.TableError, match="unknown occupation group"):
        dosm.parse_groups_xlsx(jmi_workbook(rows))
    rows = groups()
    rows["Managers"]["2026Q2"] = "approx 100"
    with pytest.raises(dosm.TableError, match="unexpected value"):
        dosm.parse_groups_xlsx(jmi_workbook(rows))
    with pytest.raises(dosm.TableError, match="not a readable XLSX"):
        dosm.parse_groups_xlsx(b"%PDF-1.7 not a workbook")


def test_totals_that_dont_add_up_are_flagged():
    assert dosm.check_totals(dosm.parse_groups_xlsx(jmi_workbook(groups()))) == {}
    problems = dosm.check_totals(dosm.parse_groups_xlsx(jmi_workbook(groups(total_q2=2000))))
    assert problems == {"2026Q2": "2026Q2: groups add up to 1,000, published total is 2,000"}


ARCHIVE = """
<a class="x" href="/portal-main/release-content/jmi-q22026">
  18.08.2026 - Big Data Analytics: Job Market Insights, Second Quarter of 2026</a>
<a href="/portal-main/release-content/jmi-q12026">25.06.2026 - Big Data Analytics: Job Market Insights, First Quarter of 2026</a>
<a href="/portal-main/release-content/jmi-q42025">25.05.2026 - Big Data Analytics: Job Market Insights, Fourth Quarter of 2025</a>
<a href="/portal-main/release-content/other">01.01.2026 - Consumer Price Index, November 2025</a>
"""


def release_page(doc_id: int) -> str:
    return (f'<div>Upcoming release : 17 November 2026</div>'
            f'<a href="https://www.dosm.gov.my/portal-main/release-document-log?release_document_id={doc_id - 1}&cat=infographic&type=pdf">pdf</a>'
            f'<a href="https://www.dosm.gov.my/portal-main/release-document-log?release_document_id={doc_id}">data</a>')


def test_archive_and_release_pages_are_parsed():
    releases = dosm.parse_archive(ARCHIVE)
    assert [(r.slug, r.date, r.quarter) for r in releases] == [
        ("jmi-q22026", "2026-08-18", "2026Q2"), ("jmi-q12026", "2026-06-25", "2026Q1"),
        ("jmi-q42025", "2026-05-25", "2025Q4")]
    assert dosm.document_links(release_page(12)) == [
        "https://www.dosm.gov.my/portal-main/release-document-log?release_document_id=12"]
    assert dosm.upcoming_release(release_page(12)) == "2026-11-17"


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def dosm_site(workbooks: dict[str, bytes | None], fail: set[str] = frozenset(), dead: set[str] = frozenset()):
    """A fake dosm.gov.my: the archive above, one page per release, and each release's workbook."""
    ids = {"jmi-q42025": 10, "jmi-q12026": 20, "jmi-q22026": 30}

    def handler(request):
        path, q = request.url.path, request.url.params
        if path.startswith("/portal-main/release-archive/"):
            return httpx.Response(200, text=ARCHIVE)
        if path.startswith("/portal-main/release-content/"):
            slug = path.rsplit("/", 1)[1]
            if slug in fail:
                return httpx.Response(503)
            return httpx.Response(200, text=release_page(ids[slug]) if workbooks.get(slug) else "<p>no files</p>")
        if path == "/portal-main/release-document-log":
            slug = next(s for s, i in ids.items() if str(i) == q["release_document_id"])
            if slug in dead:
                return httpx.Response(404, text="gone")
            return httpx.Response(200, content=workbooks[slug], headers={"content-type": XLSX})
        return httpx.Response(404)

    return mock_http(handler, retries=0)


def run_groups(conn, cur, http, **kw):
    with start_run(conn, "dosm_jmi", "groups", "test") as run:
        dosm.ingest_groups(run, cur, Options(**kw), http=http)
    return run


def test_group_import_keeps_first_published_figures_and_records_revisions(conn, cur):
    early = groups()
    late = groups()
    late["Professionals"]["2026Q1"] = 410   # the Q2 release revises Q1
    site = dosm_site({"jmi-q12026": jmi_workbook({k: {q: v for q, v in r.items() if q <= "2026Q1"}
                                                  for k, r in early.items()}),
                      "jmi-q22026": jmi_workbook(late), "jmi-q42025": None})
    run = run_groups(conn, cur, site)
    assert run.status == "partial" or run.status == "ok"
    q1 = conn.execute("SELECT * FROM raw_doc WHERE id = 'dosmg:2026Q1:2'").fetchone()
    assert json.loads(q1["metrics"])["offerings"] == 400                     # first-published figure
    assert q1["published_at"] == "2026-06-25T15:59:59Z"                      # date of the release that first had it
    q2 = conn.execute("SELECT * FROM raw_doc WHERE id = 'dosmg:2026Q2:2'").fetchone()
    assert q2["published_at"] == "2026-08-18T15:59:59Z"
    vintages = conn.execute("SELECT observed_at, value FROM artifact_metric WHERE artifact_id = 'dosmg:2026Q1:2' "
                            "ORDER BY observed_at").fetchall()
    assert [(v["observed_at"], v["value"]) for v in vintages] == [("2026-06-25T15:59:59Z", 400), ("2026-08-18T15:59:59Z", 410)]
    assert not db.has_doc(conn, "dosmg:2025Q3:9")                             # "-" isn't stored as zero
    assert db.has_doc(conn, "dosmg:2026Q1:9")                                 # a published 0 is
    state = json.loads(run.checkpoint())
    assert state["imported"] == ["jmi-q12026", "jmi-q22026"]
    assert state["unusable"] == {"jmi-q42025": "no XLSX workbook attached"}
    assert state["upcoming_release"] == "2026-11-17"
    # nothing new next time: no workbook is downloaded again
    again = run_groups(conn, cur, site)
    assert again.status == "no_change" and again.counts["skipped"] == 3


def test_group_import_stops_at_an_unreachable_release(conn, cur):
    site = dosm_site({"jmi-q42025": jmi_workbook(groups()), "jmi-q12026": jmi_workbook(groups()),
                      "jmi-q22026": jmi_workbook(groups())}, fail={"jmi-q12026"})
    run = run_groups(conn, cur, site)
    assert run.status == "partial"
    assert json.loads(run.checkpoint())["imported"] == ["jmi-q42025"]       # Q2 waits for Q1


def test_group_stats_never_reach_skill_scoring(conn, cur):
    run_groups(conn, cur, dosm_site({"jmi-q22026": jmi_workbook(groups())}))
    result = snapshot.build(conn, cur, "2026-10-01")
    snap = conn.execute("SELECT sources FROM snapshot WHERE id = '2026-10-01'").fetchone()
    dosm_src = next(s for s in json.loads(snap["sources"]) if s["id"] == "dosm_jmi")
    assert dosm_src["latest_period"] is None          # rung 3 still has no occupation-level data
    assert result["statuses"].get("Act now", 0) == 0


def test_dead_attachment_marks_release_unusable_without_blocking_later_ones(conn, cur):
    # regression: DOSM's 2022 releases link attachments that answer 404; that stopped the whole import
    site = dosm_site({"jmi-q42025": jmi_workbook(groups()), "jmi-q12026": jmi_workbook(groups()),
                      "jmi-q22026": jmi_workbook(groups())}, dead={"jmi-q42025"})
    run = run_groups(conn, cur, site)
    state = json.loads(run.checkpoint())
    assert state["imported"] == ["jmi-q12026", "jmi-q22026"]
    assert state["unusable"] == {"jmi-q42025": "attachment 10 answers HTTP 404"}
    assert run.status == "ok"


def test_placeholder_quarters_after_the_release_are_ignored(conn, cur):
    # regression: the Q3 2025 workbook already had a 2025Q4 column filled with zeros; taken as the first
    # publication, those zeros would have become 2025Q4's figures for good
    early = {k: dict(r) for k, r in groups().items()}
    for r in early.values():
        r["2026Q2"] = 0
    site = dosm_site({"jmi-q12026": jmi_workbook(early), "jmi-q22026": jmi_workbook(groups())})
    run_groups(conn, cur, site)
    q2 = conn.execute("SELECT * FROM raw_doc WHERE id = 'dosmg:2026Q2:2'").fetchone()
    assert json.loads(q2["metrics"])["offerings"] == 400 and q2["published_at"] == "2026-08-18T15:59:59Z"


def test_quarter_that_does_not_add_up_waits_for_a_corrected_release(conn, cur):
    # regression: the Q3 2024 release published a total of 0 for 2024Q3 (groups add up to 301,623), and
    # the next release corrected it
    first = groups(total_q2=0)
    site = dosm_site({"jmi-q22026": jmi_workbook(first), "jmi-q42025": None,
                      "jmi-q12026": None})
    run_groups(conn, cur, site)
    assert not db.has_doc(conn, "dosmg:2026Q2:TOTAL") and not db.has_doc(conn, "dosmg:2026Q2:2")
    assert db.has_doc(conn, "dosmg:2026Q1:2")
    assert conn.execute("SELECT value FROM artifact_metric WHERE artifact_id = 'dosmg:2026Q2:TOTAL'").fetchone()[0] == 0
