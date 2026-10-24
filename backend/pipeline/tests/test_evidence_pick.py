from kompas import db, evidence_pick

TASK, WHY = "Allocate bills", "Bill capture and coding is automated by document extraction"
CUTOFF = "2026-10-01T00:00:00Z"


def doc(conn, id, title, text="", source="arxiv", kind="paper", published="2026-09-03T00:00:00Z", concept="document-ai"):
    db.upsert_doc(conn, {"id": id, "source": source, "kind": kind, "url": f"https://example.com/{id}", "title": title,
                         "text": text, "published_at": published, "period": published[:7], "metrics": {}})
    conn.execute("INSERT INTO tag (doc_id, concept_id, method) VALUES (?, ?, 'dictionary')", (id, concept))
    conn.commit()


def stored(id, title, kind="paper", source="arxiv"):
    return {"id": id, "source": source, "kind": kind, "title": title, "url": None, "published_at": "2026-09-03T00:00:00Z",
            "value": None, "value_label": None, "coverage_note": None}


COUNT = stored("count-1", "arXiv papers on Document understanding and extraction, 2026-09", kind="paper_count")
GREEK = stored("greek", "Blockchain-Enabled Secure Logging for Fiscal Electronic Mechanisms: the Greek eSEND and myDATA Tax Systems")


def model(answer):
    calls = []

    def generate(system, contents, schema, client):
        calls.append(contents)
        return answer, None
    return generate, calls


def test_words_find_records_about_the_task_and_drop_the_rest(conn):
    doc(conn, "ocr", "Developing an OCR model for Extracting Information from Invoices")
    doc(conn, "bills", "Supplier bill capture", text="Coding of supplier bills with document extraction", source="github", kind="repo")
    doc(conn, "react", "Hiring a frontend engineer", text="React and TypeScript", source="hn_hiring", kind="hiring_post")
    items = evidence_pick.pool(conn, "document-ai", CUTOFF, [GREEK], {})
    ids = [e["id"] for e in evidence_pick.shortlist(TASK, WHY, items)]
    assert ids[0] == "bills" and "ocr" in ids
    assert "greek" not in ids and "react" not in ids


def test_the_pool_is_wider_than_what_is_attached_to_the_status(conn):
    doc(conn, "old", "Bill extraction with layout models", published="2026-03-01T00:00:00Z")      # not in `stored`
    doc(conn, "future", "Bill capture, a later paper", published="2026-12-01T00:00:00Z")           # after the snapshot
    ids = {e["id"] for e in evidence_pick.pool(conn, "document-ai", CUTOFF, [GREEK], {})}
    assert ids == {"greek", "old"}


def test_capability_wide_counts_are_never_task_evidence_but_always_returned(conn, monkeypatch):
    doc(conn, "ocr", "Developing an OCR model for Extracting Information from Invoices")
    monkeypatch.setattr(evidence_pick.llm, "_generate", lambda *a: (None, "no key"))
    out = evidence_pick.pick(conn, "2026-09-01", "document-ai", TASK, WHY, [COUNT, GREEK], CUTOFF)
    assert [e["id"] for e in out["evidence"]] == ["ocr"]
    assert [e["id"] for e in out["overall"]] == ["count-1"]
    assert "snippet" not in out["evidence"][0]


def test_two_tasks_of_one_capability_get_different_evidence(conn, monkeypatch):
    doc(conn, "ocr", "Extracting information from invoices with OCR")
    doc(conn, "forms", "Filling forms from source documents with extraction models")
    monkeypatch.setattr(evidence_pick.llm, "_generate", lambda *a: (None, "no key"))
    bills = evidence_pick.pick(conn, "s", "document-ai", "Issue sales invoices", "Invoices are generated from data", [], CUTOFF)
    forms = evidence_pick.pick(conn, "s", "document-ai", "Fill out forms", "Form filling is automated by extraction models", [], CUTOFF)
    assert bills["evidence"][0]["id"] == "ocr" and forms["evidence"][0]["id"] == "forms"


def test_model_picks_are_limited_to_the_shortlist(conn, monkeypatch):
    doc(conn, "ocr", "Developing an OCR model for Extracting Information from Invoices")
    generate, _ = model({"picks": [{"id": "ocr", "why": "A tool that does exactly this."},
                                   {"id": "made-up", "why": "Not a stored record."},
                                   {"id": "ocr", "why": "Twice."}]})
    monkeypatch.setattr(evidence_pick.llm, "_generate", generate)
    out = evidence_pick.pick(conn, "s", "document-ai", TASK, WHY, [], CUTOFF)
    assert [e["id"] for e in out["evidence"]] == ["ocr"] and out["evidence"][0]["why"] == "A tool that does exactly this."
    assert out["specific"] is True and out["method"] == "ai"


def test_model_picks_are_cached_per_task(conn, monkeypatch):
    doc(conn, "ocr", "Developing an OCR model for Extracting Information from Invoices")
    generate, calls = model({"picks": [{"id": "ocr", "why": "OCR for invoices."}]})
    monkeypatch.setattr(evidence_pick.llm, "_generate", generate)
    evidence_pick.pick(conn, "s", "document-ai", TASK, WHY, [], CUTOFF)
    evidence_pick.pick(conn, "s", "document-ai", TASK, WHY, [], CUTOFF)
    assert len(calls) == 1
    evidence_pick.pick(conn, "s", "document-ai", "Issue sales invoices", WHY, [], CUTOFF)
    assert len(calls) == 2


def test_nothing_in_common_means_no_model_call_and_no_evidence(conn, monkeypatch):
    doc(conn, "react", "Hiring a frontend engineer", text="React and TypeScript")
    generate, calls = model({"picks": []})
    monkeypatch.setattr(evidence_pick.llm, "_generate", generate)
    out = evidence_pick.pick(conn, "s", "document-ai", "Negotiate contracts", "Contract review is automated", [GREEK], CUTOFF)
    assert out["specific"] is False and out["evidence"] == [] and calls == []


def test_without_a_model_words_are_used_and_nothing_is_cached(conn, monkeypatch):
    doc(conn, "ocr", "Developing an OCR model for Extracting Information from Invoices")
    monkeypatch.setattr(evidence_pick.llm, "_generate", lambda *a: (None, "no Gemini API key configured"))
    out = evidence_pick.pick(conn, "s", "document-ai", TASK, WHY, [], CUTOFF)
    assert out["method"] == "keywords" and out["evidence"][0]["id"] == "ocr"
    generate, calls = model({"picks": [{"id": "ocr", "why": "OCR for invoices."}]})
    monkeypatch.setattr(evidence_pick.llm, "_generate", generate)      # a key added later takes over
    assert evidence_pick.pick(conn, "s", "document-ai", TASK, WHY, [], CUTOFF)["method"] == "ai" and len(calls) == 1
