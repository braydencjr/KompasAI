"""Generated simulations and mini projects, kept on disk so each is written by the AI once and survives restarts.

A small SQLite file (backend/data/ai_cache.db, git-ignored). Entries expire after CACHE_DAYS so scenarios don't
go stale forever; asking for a "fresh" one simply overwrites the entry.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DAYS = 30
PATH = Path(os.getenv("AI_CACHE_PATH", Path(__file__).resolve().parents[2] / "data" / "ai_cache.db"))


def _conn() -> sqlite3.Connection:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS ai_cache (kind TEXT NOT NULL, key TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "payload TEXT NOT NULL, PRIMARY KEY (kind, key))")
    return conn


def _key(parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:32]


def get(kind: str, parts) -> dict | None:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT created_at, payload FROM ai_cache WHERE kind = ? AND key = ?",
                               (kind, _key(parts))).fetchone()
    except sqlite3.Error:
        return None     # a cache that can't be read just means writing it again
    if not row or datetime.now(timezone.utc) - datetime.fromisoformat(row[0]) > timedelta(days=CACHE_DAYS):
        return None
    return json.loads(row[1])


def put(kind: str, parts, value: dict) -> None:
    try:
        with _conn() as conn:
            conn.execute("INSERT INTO ai_cache (kind, key, created_at, payload) VALUES (?, ?, ?, ?) ON CONFLICT (kind, key) "
                         "DO UPDATE SET created_at = excluded.created_at, payload = excluded.payload",
                         (kind, _key(parts), datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(value)))
    except sqlite3.Error:
        pass
