"""Accounts, sign-in sessions and saved progress, in a small SQLite file (backend/data/users.db, git-ignored).

Passwords are stored only as scrypt hashes with a random salt per user. A sign-in gives the browser a random token;
only the token's SHA-256 is stored, so a copy of the database can't be used to sign in as anyone. Tokens expire after
SESSION_DAYS. Progress is a JSON blob per user (what's been ticked off, simulation results) that the app saves
while signed in and restores on the next sign-in.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION_DAYS = 30
PASSWORD_MIN, PASSWORD_MAX = 8, 128
MAX_PROGRESS_BYTES = 100_000
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(Exception):
    """Something the person can fix (the message is safe to show them)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _path() -> Path:
    return Path(os.getenv("AUTH_DB_PATH", Path(__file__).resolve().parents[2] / "data" / "users.db"))


def _conn() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, "
        "password_hash TEXT NOT NULL, created_at TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL "
        "REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS progress (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
        "data TEXT NOT NULL, updated_at TEXT NOT NULL);"
    )
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


# ---------- passwords and tokens ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


# a real hash to check against when the email is unknown, so a wrong email takes as long as a wrong password
_DUMMY = hash_password(secrets.token_urlsafe(8))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def _start_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(_now()),))
    conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                 (_token_hash(token), user_id, _iso(_now() + timedelta(days=SESSION_DAYS))))
    return token


# ---------- accounts ----------


def clean_email(email: str) -> str:
    e = email.strip().lower()
    if len(e) > 254 or not EMAIL_RE.match(e):
        raise AccountError("Enter a valid email address.")
    return e


def check_password(password: str) -> None:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise AccountError(f"Use a password of {PASSWORD_MIN} to {PASSWORD_MAX} characters.")


def sign_up(email: str, password: str, name: str) -> tuple[str, dict]:
    email = clean_email(email)
    check_password(password)
    name = name.strip()[:40] or email.split("@")[0][:40]
    with _conn() as conn:
        try:
            cur = conn.execute("INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                               (email, name, hash_password(password), _iso(_now())))
        except sqlite3.IntegrityError:
            raise AccountError("An account with this email already exists. Sign in instead.", 409)
        token = _start_session(conn, cur.lastrowid)
        return token, {"id": cur.lastrowid, "email": email, "name": name}


def sign_in(email: str, password: str) -> tuple[str, dict]:
    wrong = AccountError("Wrong email or password.", 401)
    try:
        email = clean_email(email)
    except AccountError:
        verify_password(password, _DUMMY)
        raise wrong
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not verify_password(password, row["password_hash"] if row else _DUMMY) or not row:
            raise wrong
        return _start_session(conn, row["id"]), _user(row)


def user_for(token: str) -> dict | None:
    if not token:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token), _iso(_now()))).fetchone()
    return _user(row) if row else None


def sign_out(token: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ---------- saved progress ----------


def get_progress(user_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT data, updated_at FROM progress WHERE user_id = ?", (user_id,)).fetchone()
    return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]} if row else None


def put_progress(user_id: int, data: dict) -> str:
    blob = json.dumps(data, separators=(",", ":"))
    if len(blob.encode()) > MAX_PROGRESS_BYTES:
        raise AccountError("That's more progress than can be saved.", 413)
    now = _iso(_now())
    with _conn() as conn:
        conn.execute("INSERT INTO progress (user_id, data, updated_at) VALUES (?, ?, ?) ON CONFLICT (user_id) "
                     "DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at", (user_id, blob, now))
    return now
