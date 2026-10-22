"""Period helpers. Monthly periods are 'YYYY-MM', quarterly 'YYYYQn'. All timestamps are UTC ISO strings."""

from datetime import date, datetime, timedelta, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts: str) -> datetime:
    if len(ts) == 10:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def cutoff(as_of: str) -> str:
    """A snapshot dated D sees everything published at or before D 00:00 UTC."""
    return f"{as_of}T00:00:00Z"


def month_of(ts: str) -> str:
    return ts[:7]


def quarter_of(ts: str) -> str:
    return f"{ts[:4]}Q{(int(ts[5:7]) - 1) // 3 + 1}"


def period_of(ts: str, grain: str) -> str:
    return month_of(ts) if grain == "month" else quarter_of(ts)


def period_start(period: str) -> date:
    if "Q" in period:
        y, q = period.split("Q")
        return date(int(y), (int(q) - 1) * 3 + 1, 1)
    y, m = period.split("-")
    return date(int(y), int(m), 1)


def next_period_start(period: str) -> date:
    start = period_start(period)
    months = 3 if "Q" in period else 1
    m = start.month - 1 + months
    return date(start.year + m // 12, m % 12 + 1, 1)


def period_end(period: str) -> date:
    return next_period_start(period) - timedelta(days=1)


def available_at(period: str) -> str:
    """A period's aggregate is only known once the period is over."""
    return f"{next_period_start(period).isoformat()}T00:00:00Z"


def months(since: str, until: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' between two months."""
    out, cur = [], period_start(since)
    end = period_start(until)
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        cur = next_period_start(cur.strftime("%Y-%m"))
    return out


def last_complete_months(n: int, today: date | None = None) -> tuple[str, str]:
    """(since, until) covering the n months before the current one."""
    today = today or datetime.now(timezone.utc).date()
    y, m = today.year, today.month
    m -= 1
    until = date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    k = until.year * 12 + until.month - 1 - (n - 1)
    return date(k // 12, k % 12 + 1, 1).strftime("%Y-%m"), until.strftime("%Y-%m")


def quarters_between(a: str, b: str) -> float:
    return (parse(b) - parse(a)).days / 91.31
