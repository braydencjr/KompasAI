import httpx
import pytest

from kompas.connectors import tavily
from kompas.http import FetchError


def client(status=200, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.request = request
        return httpx.Response(status, json=body if body is not None else {})
    return httpx.Client(transport=httpx.MockTransport(handler)), handler


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


def test_only_https_course_pages_on_free_sites_are_kept():
    body = {"results": [
        {"title": "  Intro to Python  ", "url": "https://ocw.mit.edu/courses/6-0001/"},
        {"title": "Not a course page", "url": "https://ocw.mit.edu/about/"},
        {"title": "Wrong site", "url": "https://evil.example.com/courses/x"},
        {"title": "Lookalike host", "url": "https://ocw.mit.edu.evil.example.com/courses/x"},
        {"title": "Plain http", "url": "http://ocw.mit.edu/courses/x"},
        {"title": "Kaggle competition", "url": "https://www.kaggle.com/competitions/titanic"},
        {"title": "Intro to SQL", "url": "https://www.kaggle.com/learn/intro-to-sql"},
        {"title": "Content request", "url": "https://support.khanacademy.org/hc/en-us/community/posts/1-finance"},
        {"title": "Week 1", "url": "https://ocw.mit.edu/courses/18-642/pages/week-1"},
        {"title": "Core finance", "url": "https://www.khanacademy.org/economics-finance-domain/core-finance"},
        {"title": "An article", "url": "https://www.khanacademy.org/computing/intro/unit/a/next-steps"},
        {"title": "Forum", "url": "https://forum.freecodecamp.org/t/help/1"},
        {"title": "Intro to Python", "url": "https://ocw.mit.edu/courses/6-0001/"},
        {"title": "", "url": "https://www.freecodecamp.org/learn/"},
    ]}
    http, handler = client(body=body)
    out = tavily.search(["python"], limit=5, client=http)
    assert [c["title"] for c in out] == ["Intro to Python", "Intro to SQL", "Core finance"]
    assert out[0]["free"] is True and out[0]["provider"] == "MIT OpenCourseWare" and out[0]["platform"] == "Free"
    assert handler.request.headers["authorization"] == "Bearer tvly-test"
    assert b"ocw.mit.edu" in handler.request.content     # the search itself is limited to the free sites


def test_titles_are_shortened():
    http, _ = client(body={"results": [{"title": "x" * 500, "url": "https://ocw.mit.edu/courses/long/"}]})
    assert len(tavily.search(["x"], client=http)[0]["title"]) == tavily.TITLE_MAX


def test_errors_become_fetch_errors():
    http, _ = client(status=401)
    with pytest.raises(FetchError) as e:
        tavily.search(["python"], client=http)
    assert e.value.category == "client" and e.value.status == 401
    http, _ = client(status=429)
    with pytest.raises(FetchError) as e:
        tavily.search(["python"], client=http)
    assert e.value.category == "rate_limited"


def test_no_key_means_no_search(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY")
    assert not tavily.enabled() and tavily.search(["python"]) == []
