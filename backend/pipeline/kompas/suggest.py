"""LLM-suggested aliases for trending items that matched no skill, approved by a person.

    kompas suggest            ask Gemini about the most popular unmatched items; check and store its answers
    kompas suggestions        list suggestions waiting for review
    kompas approve 3 7        add those aliases to curated/concept_alias.csv
    kompas reject 4           drop a suggestion

The model never tags anything itself. Code checks every suggestion first: the skill must exist, the alias must
appear in the item word for word and must actually tag it under the tagger's rules, and it can't be generic or
already in the dictionary. A person approves what's left, and only then does it reach the curated CSV, so the
pipeline stays reproducible from the CSVs alone. Each suggestion records how many stored items the alias would
tag, so an alias that's too broad is visible before it's approved.
"""

import csv
import json
import re
from datetime import timedelta

from . import config, curated, llm
from .curated import Curated
from .periods import iso, parse, utcnow
from .tag import Tagger, retag

GENERIC = {"ai", "llm", "llms", "ml", "data", "agent", "agents", "tool", "tools", "app", "apps", "api", "apis",
           "model", "models", "code", "coding", "open source", "software", "cloud", "web", "dev", "bot", "chatbot"}
TEXT_KINDS = ("story", "repo", "hiring_post")


def candidates(conn, cur: Curated, limit: int, days: int) -> list[dict]:
    """Most popular stories and repos from the last `days` days that match no skill and haven't been asked about."""
    retag(conn, cur)
    since = iso(parse(utcnow()) - timedelta(days=days))
    rows = conn.execute(
        """
        SELECT d.id, d.kind, d.title, d.text, d.topics,
               COALESCE(CAST(json_extract(d.metrics, '$.points') AS REAL),
                        CAST(json_extract(d.metrics, '$.stars') AS REAL), 0) AS score
        FROM raw_doc d
        LEFT JOIN tag t ON t.doc_id = d.id
        LEFT JOIN alias_suggestion s ON s.doc_id = d.id
        WHERE d.kind IN ('story', 'repo') AND t.doc_id IS NULL AND s.doc_id IS NULL AND d.published_at >= ?
        ORDER BY score DESC LIMIT ?
        """, (since, limit)).fetchall()
    return [{"id": r["id"], "kind": r["kind"], "title": r["title"] or "", "topics": json.loads(r["topics"]),
             "description": (r["text"] or "")[:300], "score": r["score"]} for r in rows]


def _matches(alias: str, case_sensitive: bool, text: str) -> bool:
    key = alias if case_sensitive else alias.lower()
    rx = Tagger._compile({key: {"x"}}, 0 if case_sensitive else re.IGNORECASE)
    return bool(rx.search(text))


def reach(conn, alias: str, case_sensitive: bool) -> int:
    """How many stored stories, repos and job posts the alias would tag."""
    rows = conn.execute(
        f"SELECT title, text FROM raw_doc WHERE kind IN ({','.join('?' * len(TEXT_KINDS))}) "
        "AND (title LIKE ? OR text LIKE ?)", (*TEXT_KINDS, f"%{alias}%", f"%{alias}%")).fetchall()
    return sum(_matches(alias, case_sensitive, f"{r['title'] or ''}\n{r['text'] or ''}") for r in rows)


def check(s: dict, item: dict, cur: Curated) -> str | None:
    """Why a suggestion can't be used, or None if it passes every check."""
    cid, alias = s.get("skill_id"), (s.get("alias") or "").strip()
    if cid not in cur.concepts or cur.concepts[cid].kind == "family":
        return f"unknown skill {cid!r}"
    if not 2 <= len(alias) <= 60:
        return "alias is empty or too long"
    if alias.lower() in GENERIC:
        return f"'{alias}' is too generic"
    text = f"{item['title']}\n{item['description']}"
    if alias.lower() not in (text + "\n" + " ".join(item["topics"])).lower():
        return f"'{alias}' doesn't appear in the item"
    if not _matches(alias, bool(s.get("case_sensitive")), text):
        return f"'{alias}' wouldn't tag this item (only in topics, or not a whole word)"
    for a in cur.aliases:
        if a.alias.lower() == alias.lower():
            return f"'{alias}' is already an alias of {a.concept_id}"
    if alias.lower() == cur.concepts[cid].label.lower():
        return f"'{alias}' is already the skill's name"
    return None


def suggest(conn, cur: Curated, limit: int = 50, days: int = 90, batch: int = 25, client=None) -> dict:
    """Asks the model about up to `limit` unmatched items and stores checked suggestions. Items the model
    can't place are stored as no_match, so they aren't asked about again."""
    items = candidates(conn, cur, limit, days)
    counts = {"asked": 0, "pending": 0, "no_match": 0, "rejected_by_checks": 0}
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        answers, error = llm.suggest_aliases(
            [{k: it[k] for k in ("id", "title", "topics", "description")} for it in chunk], cur, client)
        if error:
            conn.commit()
            return {**counts, "error": error}
        counts["asked"] += len(chunk)
        by_item = {a.get("item_id"): a for a in answers}
        now = utcnow()
        for it in chunk:
            a = by_item.get(it["id"]) or {"skill_id": llm.NONE}
            if a.get("skill_id") == llm.NONE:
                status, note, cid, alias, n = "no_match", None, None, None, None
            else:
                cid, alias = a.get("skill_id"), (a.get("alias") or "").strip()
                note = check(a, it, cur)
                status = "rejected_by_checks" if note else "pending"
                n = None if note else reach(conn, alias, bool(a.get("case_sensitive")))
            counts[status] += 1
            conn.execute(
                "INSERT OR REPLACE INTO alias_suggestion (doc_id, item_title, concept_id, alias, case_sensitive, "
                "reason, model, status, check_note, reach, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (it["id"], it["title"][:300], cid, alias, int(bool(a.get("case_sensitive"))), (a.get("reason") or "")[:300],
                 llm.MODEL, status, note, n, now))
        conn.commit()
    return counts


def pending(conn, all_: bool = False) -> list:
    where = "" if all_ else "WHERE status = 'pending'"
    return conn.execute(f"SELECT * FROM alias_suggestion {where} ORDER BY concept_id, reach DESC, id").fetchall()


def approve(conn, ids: list[int]) -> list[str]:
    """Appends the suggestions' aliases to concept_alias.csv. The tables are re-validated afterwards; if they
    no longer validate, the file is restored and nothing is approved."""
    rows = [conn.execute("SELECT * FROM alias_suggestion WHERE id = ?", (i,)).fetchone() for i in ids]
    missing = [i for i, r in zip(ids, rows) if r is None or r["status"] != "pending"]
    if missing:
        raise ValueError(f"not pending: {missing}")
    path = config.CURATED_DIR / "concept_alias.csv"
    before = path.read_text(encoding="utf-8")
    with path.open("a", newline="", encoding="utf-8") as f:
        if before and not before.endswith("\n"):
            f.write("\n")
        w = csv.writer(f, lineterminator="\n")
        for r in rows:
            w.writerow([r["alias"], r["concept_id"], "true" if r["case_sensitive"] else "false"])
    errors = curated.validate(curated.load())
    if errors:
        path.write_text(before, encoding="utf-8")
        raise ValueError("concept_alias.csv no longer validates, nothing changed: " + "; ".join(errors))
    now = utcnow()
    conn.executemany("UPDATE alias_suggestion SET status = 'approved', decided_at = ? WHERE id = ?",
                     [(now, i) for i in ids])
    conn.commit()
    return [f"{r['alias']} -> {r['concept_id']}" for r in rows]


def reject(conn, ids: list[int]) -> int:
    n = conn.executemany("UPDATE alias_suggestion SET status = 'rejected', decided_at = ? WHERE id = ? AND status = 'pending'",
                         [(utcnow(), i) for i in ids]).rowcount
    conn.commit()
    return n
