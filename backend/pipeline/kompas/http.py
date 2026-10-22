import time

import httpx

USER_AGENT = "KompasAI/0.1 (SDC XMUM hackathon research prototype)"


class Http:
    """Small sync HTTP client: a minimum gap between requests, plus retry with backoff."""

    def __init__(self, min_interval: float = 0.0, headers: dict | None = None, timeout: float = 30.0,
                 backoff: float = 1.0, retries: int = 4):
        self.min_interval = min_interval
        self.backoff = backoff      # base wait when a server throttles without saying how long
        self.retries = retries
        self._last = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=timeout, follow_redirects=True
        )

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        retries = self.retries
        for attempt in range(retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.client.get(url, params=params)
            except httpx.TransportError:
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)
                continue
            if resp.status_code < 400:
                return resp
            if attempt < retries and (resp.status_code in (429, 500, 502, 503, 504) or _rate_limited(resp)):
                time.sleep(_retry_after(resp, attempt, self.backoff))
                continue
            resp.raise_for_status()
        raise RuntimeError("unreachable")

    def close(self):
        self.client.close()


def _rate_limited(resp: httpx.Response) -> bool:
    return resp.status_code == 403 and (
        resp.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in resp.text.lower()
    )


def _retry_after(resp: httpx.Response, attempt: int, backoff: float = 1.0) -> float:
    if "retry-after" in resp.headers:
        return min(float(resp.headers["retry-after"]), 120)
    if resp.headers.get("x-ratelimit-reset"):
        return min(max(float(resp.headers["x-ratelimit-reset"]) - time.time() + 1, 1), 120)
    return min(backoff * 2 ** (attempt + 1), 300)
