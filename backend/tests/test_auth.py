import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth
from app.services import accounts


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "users.db"))
    auth._tries.clear()


client = TestClient(app)
PERSON = {"email": "Aisyah@Example.com", "password": "correct horse", "name": "Aisyah"}


def sign_up(**over):
    return client.post("/api/auth/signup", json={**PERSON, **over})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_sign_up_then_me_and_sign_in():
    r = sign_up()
    assert r.status_code == 200 and r.json()["user"]["email"] == "aisyah@example.com"
    token = r.json()["token"]
    assert client.get("/api/auth/me", headers=bearer(token)).json()["user"]["name"] == "Aisyah"
    again = client.post("/api/auth/login", json={"email": " AISYAH@example.com ", "password": PERSON["password"]})
    assert again.status_code == 200 and again.json()["token"] != token


def test_password_is_never_stored_in_the_clear():
    sign_up()
    with accounts._conn() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert PERSON["password"] not in stored and stored.startswith("scrypt$")
    assert accounts.verify_password(PERSON["password"], stored) and not accounts.verify_password("nope nope", stored)


def test_tokens_are_stored_hashed():
    token = sign_up().json()["token"]
    with accounts._conn() as conn:
        assert [r[0] for r in conn.execute("SELECT token_hash FROM sessions")] == [accounts._token_hash(token)]


def test_wrong_credentials_get_the_same_answer():
    sign_up()
    wrong_pw = client.post("/api/auth/login", json={"email": PERSON["email"], "password": "not the password"})
    no_user = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "not the password"})
    assert wrong_pw.status_code == no_user.status_code == 401 and wrong_pw.json() == no_user.json()


def test_sign_up_checks_email_and_password_and_duplicates():
    assert sign_up(email="not-an-email").status_code == 400
    assert sign_up(password="short").status_code == 400
    assert sign_up().status_code == 200
    assert sign_up(email="aisyah@example.com").status_code == 409


def test_sign_out_ends_the_session():
    token = sign_up().json()["token"]
    assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_no_token_or_a_made_up_one_is_refused():
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=bearer("made-up")).status_code == 401
    assert client.put("/api/auth/progress", json={"data": {}}).status_code == 401


def test_progress_is_saved_per_person():
    a = sign_up().json()["token"]
    b = sign_up(email="other@example.com").json()["token"]
    assert client.get("/api/auth/progress", headers=bearer(a)).json()["data"] is None
    assert client.put("/api/auth/progress", headers=bearer(a), json={"data": {"completed": ["sql"]}}).status_code == 200
    assert client.get("/api/auth/progress", headers=bearer(a)).json()["data"] == {"completed": ["sql"]}
    assert client.get("/api/auth/progress", headers=bearer(b)).json()["data"] is None


def test_oversized_progress_is_refused():
    token = sign_up().json()["token"]
    r = client.put("/api/auth/progress", headers=bearer(token), json={"data": {"x": "y" * 200_000}})
    assert r.status_code == 413


def test_too_many_tries_are_slowed_down():
    codes = [client.post("/api/auth/login", json={"email": "a@b.co", "password": "wrong wrong"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


# ---------- Google ----------


from app.services import google_auth


def fake_google(monkeypatch, sub="g-1", email="aisyah@example.com", name="Aisyah G"):
    monkeypatch.setattr(google_auth, "verify", lambda credential: {"sub": sub, "email": email, "name": name})


def google(credential="x" * 20):
    return client.post("/api/auth/google", json={"credential": credential})


def test_google_creates_an_account_then_signs_back_in(monkeypatch):
    fake_google(monkeypatch)
    first = google()
    assert first.status_code == 200 and first.json()["user"] == {"id": 1, "email": "aisyah@example.com", "name": "Aisyah G"}
    again = google()
    assert again.json()["user"]["id"] == 1 and again.json()["token"] != first.json()["token"]
    # a Google account has no password to sign in with
    assert client.post("/api/auth/login", json={"email": "aisyah@example.com", "password": "anything at all"}).status_code == 401


def test_google_takes_over_a_password_account_for_the_same_email(monkeypatch):
    mine = sign_up().json()
    fake_google(monkeypatch)
    assert google().json()["user"]["id"] == mine["user"]["id"]
    # the unverified password sign-up no longer works, and its old session is over
    assert client.post("/api/auth/login", json={"email": PERSON["email"], "password": PERSON["password"]}).status_code == 401
    assert client.get("/api/auth/me", headers=bearer(mine["token"])).status_code == 401


def test_a_bad_google_token_is_refused(monkeypatch):
    def refuse(credential):
        raise google_auth.GoogleAuthError("Google couldn't confirm this sign-in. Try again.")

    monkeypatch.setattr(google_auth, "verify", refuse)
    assert google().status_code == 400


def test_google_is_off_without_a_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/api/auth/config").json() == {"google_client_id": None}
    assert google().status_code == 400
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    assert client.get("/api/auth/config").json() == {"google_client_id": "abc.apps.googleusercontent.com"}


def test_tokens_google_rejects_or_cant_check_are_refused(monkeypatch):
    from google.auth.exceptions import TransportError

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mine.apps.googleusercontent.com")
    for problem in (ValueError("Token has wrong audience"), TransportError("no network")):
        def check(credential, request, audience, _p=problem):
            assert audience == "mine.apps.googleusercontent.com"     # the token must be meant for this app
            raise _p

        monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", check)
        assert google().status_code == 400


def test_unverified_google_emails_are_refused(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mine.apps.googleusercontent.com")
    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", lambda *a, **k: {
        "iss": "https://accounts.google.com", "sub": "g-9", "email": "x@example.com", "email_verified": False})
    assert google().status_code == 400


def test_a_verified_google_token_signs_in(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mine.apps.googleusercontent.com")
    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", lambda *a, **k: {
        "iss": "accounts.google.com", "sub": "g-9", "email": "New@Example.com", "email_verified": True, "name": "New Person"})
    r = google()
    assert r.status_code == 200 and r.json()["user"]["email"] == "new@example.com"


# ---------- Google popup (access token) ----------


class Answer:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def fake_google_http(monkeypatch, aud="mine.apps.googleusercontent.com", email_verified=True, calls=None):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mine.apps.googleusercontent.com")

    def get(url, params=None, headers=None, timeout=None):
        if calls is not None:
            calls.append(url)
        if url == google_auth.TOKENINFO:
            return Answer(200, {"aud": aud})
        return Answer(200, {"sub": "g-7", "email": "Pop@Example.com", "email_verified": email_verified, "name": "Pop Up"})

    monkeypatch.setattr(google_auth.requests, "get", get)


def google_popup(token="t" * 20):
    return client.post("/api/auth/google", json={"access_token": token})


def test_popup_sign_in_with_a_token_made_for_this_app(monkeypatch):
    fake_google_http(monkeypatch)
    r = google_popup()
    assert r.status_code == 200 and r.json()["user"]["email"] == "pop@example.com"


def test_popup_token_made_for_another_app_is_refused(monkeypatch):
    calls = []
    fake_google_http(monkeypatch, aud="someone-elses.apps.googleusercontent.com", calls=calls)
    assert google_popup().status_code == 400
    assert google_auth.USERINFO not in calls          # nothing is read from a token that isn't ours


def test_popup_with_an_unverified_email_is_refused(monkeypatch):
    fake_google_http(monkeypatch, email_verified=False)
    assert google_popup().status_code == 400


def test_popup_when_google_cant_be_reached(monkeypatch):
    import requests as rq

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mine.apps.googleusercontent.com")

    def down(*a, **k):
        raise rq.ConnectionError("no network")

    monkeypatch.setattr(google_auth.requests, "get", down)
    assert google_popup().status_code == 400


def test_google_needs_some_token():
    assert client.post("/api/auth/google", json={}).status_code == 400
