from datetime import datetime, timedelta, timezone

import pytest

from kompas.document import Document, TimestampError, release_day_end, redact_emails, utc, utc_or_none


def test_timestamps_normalise_to_utc():
    assert utc("2026-09-01T12:00:00Z") == "2026-09-01T12:00:00Z"
    assert utc("2026-09-01T20:00:00+08:00") == "2026-09-01T12:00:00Z"
    assert utc("2026-09-01T12:00:00.123456Z") == "2026-09-01T12:00:00Z"
    assert utc(1756728000) == "2025-09-01T12:00:00Z"
    assert utc(datetime(2026, 9, 1, 20, tzinfo=timezone(timedelta(hours=8)))) == "2026-09-01T12:00:00Z"


def test_naive_and_malformed_timestamps_are_rejected_not_guessed():
    for bad in ("2026-09-01T12:00:00", "2026-09-01", datetime(2026, 9, 1), "yesterday", "", None, -5, True):
        with pytest.raises(TimestampError):
            utc(bad)
    # a documented timezone can be named explicitly
    assert utc("2026-09-01T08:00:00", assume=timezone(timedelta(hours=8))) == "2026-09-01T00:00:00Z"
    assert utc_or_none(None) is None
    with pytest.raises(TimestampError):
        utc_or_none("not a date")


def test_release_day_counts_from_end_of_day_in_malaysia():
    # 18 Aug 2026 23:59:59 MYT: a snapshot dated the 18th (cutoff 00:00Z) can't see it, the 19th can
    assert release_day_end("2026-08-18") == "2026-08-18T15:59:59Z"


def test_emails_are_redacted():
    assert redact_emails("Apply: jobs@acme.io or jane.doe+hn@mail.example.com") == "Apply: [email] or [email]"
    assert redact_emails(None) is None


def test_documents_without_publication_time_are_refused():
    doc = Document(id="x:1", source="x", kind="story", source_id="1", url=None, title="t", text="",
                   published_at=None, period="2026-09")
    with pytest.raises(ValueError, match="publication time unknown"):
        doc.validate()
    doc.published_at = "2026-09-01 12:00"
    with pytest.raises(ValueError, match="not a normalised UTC timestamp"):
        doc.validate()
