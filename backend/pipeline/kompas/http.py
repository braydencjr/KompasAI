import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

USER_AGENT = "KompasAI/0.1 (SDC XMUM hackathon research prototype)"

RETRYABLE_STATUS = (429, 500, 502, 503, 504)


class FetchError(Exception):
    """A request that failed for good. `category` is one of: network, timeout, rate_limited, server,
    client, parse. Client errors (4xx other than rate limits) are never retried."""

    def __init__(self, category: str, message: str, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.category, self.url, self.status = category, url, status


class Http:
    """Small sync HTTP client: a minimum gap between requests, plus bounded retry with jittered backoff.

    Retries network errors, timeouts, 429/5xx and rate-limited 403s. Honours Retry-After (seconds or an
    HTTP date) and GitHub's x-ratelimit-reset. A wait longer than max_wait isn't slept through: the request
    fails as rate_limited so the run can stop and resume later instead of hanging."""

    def __init__(self, min_interval: float = 0.0, headers: dict | None = None, timeout: float = 30.0,
                 backoff: float = 1.0, retries: int = 4, max_wait: float = 300.0, on_retry=None,
                 sleep=time.sleep, rng: random.Random | None = None, transport: httpx.BaseTransport | None = None):
        self.min_interval = min_interval
        self.backoff = backoff      # base wait when a server throttles without saying how long
        self.retries = retries
        self.max_wait = max_wait
        self.on_retry = on_retry    # called once per retry, e.g. to count retries on an ingestion run
        self.sleep = sleep
        self.rng = rng or random.Random()
        self._last = 0.0
        self._lock = threading.Lock()
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            timeout=httpx.Timeout(timeout, connect=10.0), follow_redirects=True, transport=transport,
        )

    def _throttle(self):
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                resp = self.client.get(url, params=params)
            except httpx.TimeoutException as e:
                err, wait = FetchError("timeout", f"timed out: {type(e).__name__}", url), None
            except httpx.TransportError as e:
                err, wait = FetchError("network", f"network error: {type(e).__name__}", url), None
            else:
                if resp.status_code < 400:
                    return resp
                limited = resp.status_code == 429 or _rate_limited(resp)
                if not limited and resp.status_code not in RETRYABLE_STATUS:
                    raise FetchError("client", f"HTTP {resp.status_code}", url, resp.status_code)
                err = FetchError("rate_limited" if limited else "server", f"HTTP {resp.status_code}", url,
                                 resp.status_code)
                wait = _retry_after(resp)
            if attempt == self.retries:
                raise err
            if wait is None:
                base = self.backoff * 2 ** (attempt + 1)
                wait = base / 2 + self.rng.uniform(0, base / 2)
            else:
                wait += self.rng.uniform(0, 1)
            if wait > self.max_wait:
                raise FetchError(err.category, f"{err} (server asked to wait {wait:.0f}s)", url, err.status)
            if self.on_retry:
                self.on_retry()
            self.sleep(wait)
        raise RuntimeError("unreachable")

    def get_json(self, url: str, params: dict | None = None):
        resp = self.get(url, params)
        try:
            return resp.json()
        except ValueError as e:
            raise FetchError("parse", "response is not valid JSON", url, resp.status_code) from e

    def close(self):
        self.client.close()


def _rate_limited(resp: httpx.Response) -> bool:
    return resp.status_code == 403 and (
        resp.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in resp.text.lower()
    )


def _retry_after(resp: httpx.Response) -> float | None:
    """Seconds the server asked us to wait, or None if it didn't say."""
    value = resp.headers.get("retry-after")
    if value:
        try:
            return max(float(value), 0.0)
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)
    if resp.headers.get("x-ratelimit-reset") and resp.headers.get("x-ratelimit-remaining") == "0":
        try:
            return max(float(resp.headers["x-ratelimit-reset"]) - time.time() + 1, 1.0)
        except ValueError:
            return None
    return None
