"""Picks, from the records stored for an AI capability, the ones that bear on ONE task.

The evidence panel used to show every record behind a capability, whatever task you had clicked: a card about
"Allocate bills" listed a paper on Greek tax systems because it matched the word "invoice". Now the panel asks for a
task and gets only the records that speak to it, each with a sentence on how.

The pool is every stored record tagged to the capability up to the snapshot's date (not just the few attached to its
status), cut to the 20 that share most words with the task. The capability's overall counts (papers and new repos per
month) are returned separately as `overall`: they describe the whole AI, so every task card can show the same ones.

Gemini chooses among the shortlisted records by id (ids that weren't in the list are dropped, so it can't add evidence of
its own) and the answer is cached per snapshot, capability and task. Without a Gemini key, records are ranked by the
words they share with the task and its reason. When nothing fits, the answer is an empty list with specific=False:
better no evidence than a record about something else.
"""

import hashlib
import json
import re
from datetime import datetime, timezone

from . import llm

MAX_PICKS = 4
SHORTLIST = 20
POOL_LIMIT = 600
STATS = ("paper_count", "repo_count")       # counts for the whole capability, not documents about a task
NOT_DOCUMENTS = STATS + ("paper_baseline", "occupation_stat", "occupation_group_stat", "critical_occupation",
                         "shortage_assessment")

INSTRUCTIONS = """You choose evidence for one job task. You get the task, the AI capability said to be able to do it
(with the reason), and a numbered list of stored records (papers, code repositories, news, job posts).
Choose up to 4 records that speak directly to AI doing THIS task, or the very kind of work it describes. Skip a record
that only shares a word with it or is about a different use. Choose none when nothing fits: an empty answer is right.
`why`: one short, plain sentence on how the record bears on this task. Use only the ids given."""

SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "why": {"type": "string"}},
        "required": ["id", "why"],
    }}},
    "required": ["picks"],
}

STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "is", "of", "to", "in", "on", "by", "a", "an",
        "or", "as", "at", "it", "be", "can", "do", "does", "using", "use", "based", "new", "via", "data", "tasks",
        "task", "automated", "automatically", "automates", "automate"}


def _words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if len(w) < 3 or w in STOP:
            continue
        # bills -> bill, extraction and extracting -> extract, invoice and invoices -> invoic
        out.add(re.sub(r"e$", "", re.sub(r"(ing|ions|ion|ed|es|s)$", "", w)) if len(w) > 4 else w)
    return out


def _hits(task_words: set[str], reason_words: set[str], e: dict) -> tuple[int, list[str]]:
    words = _words((e.get("title") or "") + " " + (e.get("snippet") or ""))
    hit_task, hit_reason = sorted(words & task_words), sorted((words & reason_words) - task_words)
    return 2 * len(hit_task) + len(hit_reason), hit_task + hit_reason


def shortlist(task: str, why: str, items: list[dict]) -> list[dict]:
    """The records sharing most words with the task (its own words count double) and the capability's reason, newest
    first among equals. Records with nothing in common are left out."""
    mine, reason = _words(task), _words(why)
    scored = [(score, e["published_at"], e) for e in items if (score := _hits(mine, reason, e)[0])]
    scored.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [e for _, _, e in scored[:SHORTLIST]]


def by_keywords(task: str, why: str, items: list[dict]) -> list[dict]:
    """The shortlist as the answer, each with the words it matched on (used when no model is available)."""
    mine, reason = _words(task), _words(why)
    return [{**e, "why": "Matches your task on: " + ", ".join(_hits(mine, reason, e)[1])}
            for e in shortlist(task, why, items)[:MAX_PICKS]]


def by_model(task: str, why: str, items: list[dict], client=None) -> list[dict] | None:
    """Gemini's picks, or None when the model can't be used (no key, rate limit, an answer that isn't usable)."""
    listing = [{"id": e["id"], "source": e["source"], "title": e["title"], "extract": (e.get("snippet") or "")[:200]}
               for e in items]
    facts = {"task": task, "capability_reason": why, "records": listing}
    out, error = llm._generate(INSTRUCTIONS, json.dumps(facts, ensure_ascii=False), SCHEMA, client)
    if error or not isinstance(out, dict):
        return None
    real = {e["id"]: e for e in items}
    picks, seen = [], set()
    for p in out.get("picks", []):
        if isinstance(p, dict) and p.get("id") in real and p["id"] not in seen and isinstance(p.get("why"), str):
            seen.add(p["id"])
            picks.append({**real[p["id"]], "why": p["why"].strip()[:220]})
    return picks[:MAX_PICKS]


def _cache(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS evidence_pick_cache (key TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                 "payload TEXT NOT NULL)")


def pool(conn, cid: str, cutoff: str, stored: list[dict], notes: dict[str, str | None]) -> list[dict]:
    """Every record tagged to the capability that was public by the snapshot's date, plus the ones attached to its
    status. Capability-wide counts aren't documents, so they stay out."""
    rows = conn.execute(
        "SELECT d.id, d.source, d.kind, d.url, d.title, d.published_at, substr(d.text, 1, 400) AS snippet "
        "FROM raw_doc d JOIN tag t ON t.doc_id = d.id WHERE t.concept_id = ? AND d.published_at <= ? "
        "ORDER BY d.published_at DESC LIMIT ?", (cid, cutoff, POOL_LIMIT)).fetchall()
    items = {e["id"]: e for e in stored if e["kind"] not in NOT_DOCUMENTS}
    for r in rows:
        if r["kind"] not in NOT_DOCUMENTS and r["id"] not in items:
            items[r["id"]] = {"id": r["id"], "source": r["source"], "kind": r["kind"], "title": r["title"],
                              "url": r["url"], "published_at": r["published_at"], "value": None, "value_label": None,
                              "coverage_note": notes.get(r["source"]), "snippet": r["snippet"]}
    return list(items.values())


def pick(conn, snapshot: str, cid: str, task: str, why: str, stored: list[dict], cutoff: str,
         notes: dict[str, str | None] | None = None, client=None) -> dict:
    """{"evidence": [records with a `why`], "specific": bool, "overall": [capability-wide counts], "method"}."""
    key = hashlib.sha256(json.dumps(["v2", snapshot, cid, task, why], ensure_ascii=False).encode()).hexdigest()[:32]
    overall = [e for e in stored if e["kind"] in STATS]
    _cache(conn)
    row = conn.execute("SELECT payload FROM evidence_pick_cache WHERE key = ?", (key,)).fetchone()
    if row:
        return {**json.loads(row["payload"]), "overall": overall}
    candidates = shortlist(task, why, pool(conn, cid, cutoff, stored, notes or {}))
    # nothing shares a word with the task: no need to ask a model, and nothing to cache
    picks, method = ([], "keywords") if not candidates else (by_model(task, why, candidates, client), "ai")
    if picks is None:           # no model: use the words, and don't cache so a key added later takes over
        picks, method = by_keywords(task, why, candidates), "keywords"
    picks = [{k: v for k, v in e.items() if k != "snippet"} for e in picks]
    result = {"evidence": picks, "specific": bool(picks), "method": method}
    if method == "ai":
        conn.execute("INSERT INTO evidence_pick_cache (key, created_at, payload) VALUES (?, ?, ?) ON CONFLICT (key) "
                     "DO UPDATE SET created_at = excluded.created_at, payload = excluded.payload",
                     (key, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(result)))
        conn.commit()
    return {**result, "overall": overall}
