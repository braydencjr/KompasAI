"""Tags raw docs with concept ids using topics, dictionary and alias matching. No LLM, no embeddings."""

import json
import re
import sqlite3

from .curated import Curated
from .db import get_meta, set_meta

# Docs whose concept is fixed by how they were fetched (e.g. an arXiv query per concept).
PRE_ASSIGNED = ("paper", "paper_count", "repo_count", "occupation_stat", "occupation_group_stat", "paper_baseline",
                "critical_occupation", "shortage_assessment")


def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip())


class Tagger:
    def __init__(self, cur: Curated):
        self.cur = cur
        labels = {c.label.lower() for c in cur.concepts.values()}
        self.insensitive: dict[str, set[str]] = {}
        self.sensitive: dict[str, set[str]] = {}
        self.method: dict[str, str] = {}
        for a in cur.aliases:
            term = _norm(a.alias)
            key = term if a.case_sensitive else term.lower()
            (self.sensitive if a.case_sensitive else self.insensitive).setdefault(key, set()).add(a.concept_id)
            self.method[key] = "dictionary" if term.lower() in labels else "alias"
        self._ci = self._compile(self.insensitive, re.IGNORECASE)
        self._cs = self._compile(self.sensitive, 0)

    @staticmethod
    def _compile(terms: dict, flags: int):
        if not terms:
            return None
        # longest first so "Claude Code" wins over a shorter overlapping alias
        alts = sorted(terms, key=len, reverse=True)
        body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in alts)
        # a trailing hyphen is allowed so "LLM-based" and "RAG-powered" still match
        return re.compile(rf"(?<![\w/&.-])(?:{body})(?![\w/&])", flags)

    def find_all(self, text: str) -> list[tuple[str, str, str, int]]:
        """Every match as (concept_id, method, matched span, start offset)."""
        out = []
        if not text:
            return out
        for rx, table, fold in ((self._cs, self.sensitive, False), (self._ci, self.insensitive, True)):
            if rx is None:
                continue
            for m in rx.finditer(text):
                key = _norm(m.group(0))
                key = key.lower() if fold else key
                out.extend((cid, self.method[key], m.group(0), m.start()) for cid in table.get(key, ()))
        return out

    def tag_text(self, text: str) -> dict[str, tuple[str, str]]:
        """Returns concept_id -> (method, first matched span)."""
        out: dict[str, tuple[str, str]] = {}
        for cid, method, span, _ in self.find_all(text):
            out.setdefault(cid, (method, span))
        return out

    def tag_topics(self, topics: list[str]) -> dict[str, tuple[str, str]]:
        out = {}
        for t in topics:
            for cid, weak in self.cur.topic_index.get(t.lower(), ()):
                out.setdefault(cid, ("topic_weak" if weak else "topic", t))
        return out

    def tag_doc(self, doc: sqlite3.Row | dict) -> dict[str, tuple[str, str]]:
        metrics = json.loads(doc["metrics"]) if isinstance(doc["metrics"], str) else doc["metrics"]
        if doc["kind"] in PRE_ASSIGNED:
            cid = metrics.get("concept_id")
            return {cid: ("query", metrics.get("query", ""))} if cid in self.cur.concepts else {}
        topics = json.loads(doc["topics"]) if isinstance(doc["topics"], str) else doc["topics"]
        out = self.tag_topics(topics)
        for cid, hit in self.tag_text(f"{doc['title'] or ''}\n{doc['text'] or ''}").items():
            out.setdefault(cid, hit)
        return out


def retag(conn: sqlite3.Connection, cur: Curated, tagger: Tagger | None = None) -> int:
    """Tags every doc that changed since it was last tagged. A curated-table change retags everything."""
    tagger = tagger or Tagger(cur)
    if get_meta(conn, "tagged_curated_version") != cur.version:
        conn.execute("UPDATE raw_doc SET tagged_hash = NULL")
        set_meta(conn, "tagged_curated_version", cur.version)
    rows = conn.execute(
        "SELECT id, kind, title, text, topics, metrics, content_hash FROM raw_doc "
        "WHERE tagged_hash IS NULL OR tagged_hash != content_hash"
    ).fetchall()
    # three batched statements rather than three per document: on Postgres each statement is a network round
    # trip, and a dictionary change retags every stored document
    tags = [(r["id"], cid, method, span[:200]) for r in rows for cid, (method, span) in tagger.tag_doc(r).items()]
    conn.executemany("DELETE FROM tag WHERE doc_id = ?", [(r["id"],) for r in rows])
    conn.executemany("INSERT INTO tag (doc_id, concept_id, method, span) VALUES (?, ?, ?, ?)", tags)
    conn.executemany("UPDATE raw_doc SET tagged_hash = ? WHERE id = ?", [(r["content_hash"], r["id"]) for r in rows])
    conn.commit()
    return len(rows)
