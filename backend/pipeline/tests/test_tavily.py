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


def test_more_free_sites_are_accepted_only_on_course_pages():
    ok = [
        "https://alison.com/course/microsoft-word-for-everyday-use",
        "https://learn.saylor.org/course/prdv003",
        "https://edu.gcfglobal.org/en/word/",
        "https://accountingcoach.com/accounting-basics/outline",
        "https://www.w3schools.com/typescript",
        "https://support.microsoft.com/en-us/excel",
        "https://learning.sap.com/courses/financial-statement-reporting",
        "https://trailhead.salesforce.com/content/learn/modules/salesforce-business-analyst-certification-prep",
        "https://academy.hubspot.com/courses/inbound-marketing",
        "https://huggingface.co/learn/llm-course/chapter1/1",
        "https://learn.deeplearning.ai/courses/chatgpt-prompt-eng/lesson/dfbds/introduction",
        "https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting",
        "https://openstax.org/books/statistics/pages/1-introduction",
        "https://www.theodinproject.com/paths/full-stack-javascript/courses/react",
        "https://applieddigitalskills.withgoogle.com/c/college-and-continuing-education/en/g-suite-certification-slides-part-1/",
        "https://oyc.yale.edu/economics/econ-252-08",
    ]
    no = [
        "https://alison.com/tag/microsoft-word",                      # a list of courses, not a course
        "https://alison.com/careers/finance/financial-analyst",
        "https://staging-test.alison.com/course/something",           # not the real site
        "https://learn.saylor.org/enrol/index.php",
        "https://edu.gcfglobal.org/en",
        "https://accountingcoach.com/pro",                            # the paid plan
        "https://www.w3schools.com/typescript/typescript_classes.php",
        "https://grow.google/certificates/data-analytics",            # delivered on Coursera: not free
        "https://huggingface.co/datasets/utahnlp/knows-benchmark",
        "https://discuss.huggingface.co/t/how-to-learn/1",
        "https://assets.openstax.org/oscms-prodcms/media/documents/Stats.pdf",
        "https://trailhead.salesforce.com/credentials/businessanalyst",
        "https://academy.hubspot.com/courses",
        "https://www.open.edu/openlearn/tag/index.php",
    ]
    assert [u for u in ok if tavily._site(u) is None] == []
    assert [u for u in no if tavily._site(u) is not None] == []


def test_two_phrases_are_merged_and_no_site_fills_every_place():
    def handler(request: httpx.Request) -> httpx.Response:
        handler.queries.append(__import__("json").loads(request.content)["query"])
        first = handler.queries[-1].startswith("word")
        urls = ([f"https://alison.com/course/word-{i}" for i in range(5)] if first
                else ["https://alison.com/course/word-0", "https://learn.saylor.org/course/prdv003", "https://edu.gcfglobal.org/en/word/"])
        return httpx.Response(200, json={"results": [{"title": u.rsplit("/", 1)[-1] or "t", "url": u} for u in urls]})

    handler.queries = []
    http = httpx.Client(transport=httpx.MockTransport(handler))
    out = tavily.search(["word processing", "microsoft word", "third phrase is not used"], limit=6, client=http)
    assert handler.queries == ["word processing course", "microsoft word course"]      # two credits, no more
    assert [c["provider"] for c in out] == ["Alison", "Alison", "Saylor Academy", "GCFGlobal LearnFree"]
    assert len({c["url"] for c in out}) == len(out)
