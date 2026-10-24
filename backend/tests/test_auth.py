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
