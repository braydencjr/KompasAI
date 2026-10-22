from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from kompas.http import FetchError, _retry_after

from .conftest import mock_http


def sequence(*responses):
    calls = []

    def handler(request):
        calls.append(request)
        r = responses[min(len(calls), len(responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    return handler, calls


def test_retries_server_errors_then_succeeds():
    handler, calls = sequence(httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"ok": 1}))
    retries, waits = [], []
    http = mock_http(handler, on_retry=lambda: retries.append(1), sleep=waits.append)
    assert http.get_json("https://example.test/x") == {"ok": 1}
    assert len(calls) == 3 and len(retries) == 2
    # jittered exponential backoff: within [base/2, base] for base = 2, 4
    assert 1 <= waits[0] <= 2 and 2 <= waits[1] <= 4


def test_permanent_client_errors_are_not_retried():
    handler, calls = sequence(httpx.Response(404))
    with pytest.raises(FetchError) as e:
        mock_http(handler).get("https://example.test/missing")
    assert e.value.category == "client" and e.value.status == 404 and len(calls) == 1


def test_rate_limit_retry_after_seconds_is_honoured():
    handler, calls = sequence(httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200))
    waits = []
    mock_http(handler, sleep=waits.append).get("https://example.test/")
    assert 7 <= waits[0] <= 8   # Retry-After plus at most 1 s of jitter


def test_retry_after_http_date_is_parsed():
    # regression: Retry-After may be an HTTP date; float() on it used to crash the fetch
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    assert 25 <= _retry_after(httpx.Response(503, headers={"retry-after": when})) <= 31
    assert _retry_after(httpx.Response(503, headers={"retry-after": "soon"})) is None


def test_github_style_403_rate_limit_is_retried():
    reset = str(int(datetime.now(timezone.utc).timestamp()) + 5)
    limited = httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset},
                             text="API rate limit exceeded")
    handler, calls = sequence(limited, httpx.Response(200))
    mock_http(handler).get("https://api.github.test/search")
    assert len(calls) == 2
    # a 403 that isn't a rate limit is permanent
    handler, calls = sequence(httpx.Response(403, text="forbidden"))
    with pytest.raises(FetchError) as e:
        mock_http(handler).get("https://api.github.test/search")
    assert e.value.category == "client" and len(calls) == 1


def test_wait_longer_than_max_wait_fails_instead_of_hanging():
    handler, calls = sequence(httpx.Response(429, headers={"retry-after": "3600"}))
    waits = []
    with pytest.raises(FetchError) as e:
        mock_http(handler, max_wait=60, sleep=waits.append).get("https://example.test/")
    assert e.value.category == "rate_limited" and waits == [] and len(calls) == 1


def test_retries_are_bounded_and_errors_categorised():
    handler, calls = sequence(httpx.ConnectTimeout("slow"))
    with pytest.raises(FetchError) as e:
        mock_http(handler, retries=2).get("https://example.test/")
    assert e.value.category == "timeout" and len(calls) == 3
    handler, calls = sequence(httpx.ConnectError("refused"))
    with pytest.raises(FetchError) as e:
        mock_http(handler, retries=1).get("https://example.test/")
    assert e.value.category == "network" and len(calls) == 2
    handler, _ = sequence(httpx.Response(500))
    with pytest.raises(FetchError) as e:
        mock_http(handler, retries=1).get("https://example.test/")
    assert e.value.category == "server"


def test_malformed_json_is_a_parse_error():
    handler, _ = sequence(httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(FetchError) as e:
        mock_http(handler).get_json("https://example.test/")
    assert e.value.category == "parse"
