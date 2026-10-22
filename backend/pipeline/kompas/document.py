"""The canonical document every connector produces, and the timestamp rules that go with it.

A Document maps onto one row of `raw_doc`:

    Document field   raw_doc column   meaning
    id               id               Kompas key, deterministic per source (see each connector)
    source_id        source_id        the source's own identifier (HN item id, repo full name, arXiv id, ...)
    url              url              canonical public URL of the record
    title, text      title, text      text used for tagging
    published_at     published_at     when the source made it public (UTC); drives the no-look-ahead rule
    updated_at       updated_at       source-reported last update, if the source has one
    metrics          metrics          source-specific structured fields (the "metadata")
    raw_payload      raw_payload      the source record as received, minus fields we choose not to keep

Observation times (first_seen_at, last_seen_at, fetched_at) are set by the database layer, never by
connectors, so publication time and observation time can't be mixed up.

Timestamps are stored as 'YYYY-MM-DDTHH:MM:SSZ'. A timestamp without a timezone is rejected rather than
guessed, and a missing publication time is never replaced with the fetch time.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MYT = timezone(timedelta(hours=8), "MYT")


class TimestampError(ValueError):
    pass


def utc(value, *, assume: timezone | None = None) -> str:
    """Normalises a source timestamp to a UTC string.

    Accepts aware datetimes, epoch seconds and ISO 8601 strings with 'Z' or an offset. A naive value
    (no timezone) raises TimestampError unless `assume` names the timezone the source documents."""
    if isinstance(value, bool) or value is None or value == "":
        raise TimestampError(f"no timestamp: {value!r}")
    if isinstance(value, (int, float)):
        if value < 0 or value > 32503680000:  # year 3000
            raise TimestampError(f"epoch out of range: {value!r}")
        return datetime.fromtimestamp(value, timezone.utc).strftime(UTC_FORMAT)
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        try:
            dt = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s)
        except ValueError as e:
            raise TimestampError(f"not an ISO 8601 timestamp: {value!r}") from e
    else:
        raise TimestampError(f"unsupported timestamp type: {type(value).__name__}")
    if dt.tzinfo is None:
        if assume is None:
            raise TimestampError(f"timestamp has no timezone: {value!r}")
        dt = dt.replace(tzinfo=assume)
    return dt.astimezone(timezone.utc).strftime(UTC_FORMAT)


def utc_or_none(value, *, assume: timezone | None = None) -> str | None:
    """Like utc(), but an absent value stays None. A present but malformed value still raises."""
    if value is None or value == "":
        return None
    return utc(value, assume=assume)


def release_day_end(day: date | str) -> str:
    """Publication time for an official release known only by its date (DOSM, Malaysia).

    The exact release hour isn't published in a machine-readable way, so the release counts as public at
    the end of that day in Malaysian time: a snapshot dated the release day doesn't see it, the next one does.
    This errs late, never early."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return datetime.combine(d, time(23, 59, 59), MYT).astimezone(timezone.utc).strftime(UTC_FORMAT)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def redact_emails(text: str | None) -> str | None:
    """Job posts often carry recruiters' addresses; tagging doesn't need them, so they aren't kept."""
    return _EMAIL.sub("[email]", text) if text else text


@dataclass
class Document:
    id: str
    source: str
    kind: str
    source_id: str | None
    url: str | None
    title: str | None
    text: str | None
    published_at: str | None
    period: str
    topics: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    updated_at: str | None = None
    raw_payload: dict | list | None = None

    def validate(self):
        """Raises ValueError if the document can't be stored safely."""
        if not self.id or not self.source or not self.kind:
            raise ValueError("document needs id, source and kind")
        if self.published_at is None:
            raise ValueError(f"{self.id}: publication time unknown; it can't be placed in time")
        for name in ("published_at", "updated_at"):
            v = getattr(self, name)
            if v is not None and not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", v):
                raise ValueError(f"{self.id}: {name} {v!r} is not a normalised UTC timestamp")
        if not re.fullmatch(r"\d{4}-\d\d|\d{4}Q[1-4]", self.period or ""):
            raise ValueError(f"{self.id}: bad period {self.period!r}")

    def payload_json(self) -> str | None:
        if self.raw_payload is None:
            return None
        return json.dumps(self.raw_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        """Builds a Document from the plain dicts older code and tests pass to db.upsert_doc."""
        return cls(
            id=d["id"], source=d["source"], kind=d["kind"], source_id=d.get("source_id"), url=d.get("url"),
            title=d.get("title"), text=d.get("text"), published_at=d["published_at"], period=d["period"],
            topics=list(d.get("topics") or []), metrics=dict(d.get("metrics") or {}),
            updated_at=d.get("updated_at"), raw_payload=d.get("raw_payload"),
        )
