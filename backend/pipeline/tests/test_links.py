import csv

from kompas import links
from tests.test_cv import FakeGemini


def item(skill, relation="optional", occupation="software developer"):
    return {"isco_code": "2512", "esco_occupation": occupation, "esco_occupation_uri": "", "relation": relation,
            "skill_type": "knowledge", "skill": skill, "skill_uri": ""}


ITEMS = [item("Python (computer programming)"), item("utilise machine learning"), item("TypeScript"),
         item("use software libraries", "essential"), item("SQL", "essential"),
         item("SQL", "optional", "data scientist")]


def test_check_keeps_cited_links_and_takes_weight_from_esco(cur):
    proposed = [
        {"esco_item": "Python (computer programming)", "skill_id": "python", "reason": "a language"},
        {"esco_item": "utilise machine learning", "skill_id": "machine-learning", "reason": "the technique"},
        {"esco_item": "SQL", "skill_id": "sql", "reason": "named"},
        {"esco_item": "write Rust daily", "skill_id": "rust", "reason": "invented item"},      # not an ESCO item
        {"esco_item": "TypeScript", "skill_id": "finance-accounting", "reason": "a family"},    # not a skill
        {"esco_item": "TypeScript", "skill_id": "made-up", "reason": "unknown id"},
    ]
    rows, dropped = links.check(cur, "2512", ITEMS, proposed)
    by_id = {r["concept_id"]: r for r in rows}
    assert dropped == 3
    assert by_id["python"]["weight"] == 0.5                  # optional in ESCO
    assert by_id["sql"]["weight"] == 1.0                     # essential somewhere wins
    assert "utilise machine learning" in by_id["machine-learning"]["esco_items"]


def test_draft_compares_with_the_current_file(cur, tmp_path):
    fake = FakeGemini({"links": [{"esco_item": "Python (computer programming)", "skill_id": "python", "reason": "r"},
                                 {"esco_item": "TypeScript", "skill_id": "typescript", "reason": "r"}]})
    result = links.draft(cur, {"2512": ITEMS}, client=fake)
    links.write_draft(result["rows"], tmp_path / "draft.csv")         # every field fits the draft's columns
    rows = {(r["concept_id"], r["isco_code"]): r for r in result["rows"]}
    def expected(cid):          # both are optional in ESCO (0.5); the status says how that compares with the file
        current = dict(cur.concept_occupations.get(cid, [])).get("2512")
        return "new" if current is None else "same" if current == 0.5 else "weight changed"
    assert rows[("python", "2512")]["status"] == expected("python")
    assert rows[("typescript", "2512")]["status"] == expected("typescript")
    assert rows[("sql", "2512")]["status"] == "no ESCO item"          # hand link the model didn't cite
    # the schema only lets the model cite this role's ESCO items
    schema = fake.calls[0]["config"].response_json_schema
    assert set(schema["properties"]["links"]["items"]["properties"]["esco_item"]["enum"]) == {i["skill"] for i in ITEMS}


def test_apply_keeps_families_and_reviewed_rows(cur, tmp_path):
    draft = tmp_path / "draft.csv"
    rows = [{"concept_id": "python", "isco_code": "2512", "weight": 0.5, "status": "weight changed", "current_weight": 1.0,
             "esco_items": "Python (computer programming) (optional, software developer)", "reason": "", "keep": "yes"},
            {"concept_id": "sql", "isco_code": "2512", "weight": 0.5, "status": "no ESCO item", "current_weight": 0.5,
             "esco_items": "", "reason": "", "keep": "no"}]
    links.write_draft(rows, draft)
    out = tmp_path / "concept_occupation.csv"
    counts = links.apply(cur, draft, out)
    assert counts == {"kept": 1, "rejected": 1, "families": sum(
        len(o) for cid, o in cur.concept_occupations.items() if cur.concepts[cid].kind == "family")}
    with out.open() as f:
        written = [r for r in csv.DictReader(f) if not r["concept_id"].startswith("#")]
    assert {"concept_id": "python", "isco_code": "2512", "weight": "0.5",
            "note": "ESCO: Python (computer programming) (optional, software developer)"} in written
    assert not any(r["concept_id"] == "sql" for r in written)
