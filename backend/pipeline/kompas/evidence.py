"""Collects the records behind each concept's status, so every status on screen is traceable."""

import json
from collections import defaultdict

from .aggregate import Series
from .curated import Curated
from .score import ConceptState


class EvidenceSet:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self.by_concept: dict[str, list[str]] = defaultdict(list)

    def add(self, cid: str, item: dict):
        existing = self.items.setdefault(item["id"], {**item, "concept_ids": []})
        if cid not in existing["concept_ids"]:
            existing["concept_ids"].append(cid)
        if item["id"] not in self.by_concept[cid]:
            self.by_concept[cid].append(item["id"])


def _item(row, value=None, value_label=None, title=None) -> dict:
    return {
        "id": row["id"], "source": row["source"], "kind": row["kind"], "title": title or row["title"],
        "url": row["url"], "published_at": row["published_at"], "value": value, "value_label": value_label,
    }


def collect(conn, cur: Curated, series: Series, states: dict[str, ConceptState], cutoff: str) -> EvidenceSet:
    ev = EvidenceSet()
    for cid, st in states.items():
        for source, ss in st.sources.items():
            if ss.latest_period is None:
                continue
            periods = [pt.period for pt in series[(cid, source)]][-2:]
            getattr(_Collect, source)(conn, cur, ev, cid, periods, cutoff)
        if st.rungs[3].level == "family" and st.family_id:
            fam_periods = [pt.period for pt in series.get((st.family_id, "dosm_jmi"), [])][-1:]
            if fam_periods:
                _Collect.dosm_jmi(conn, cur, ev, cid, fam_periods, cutoff, occupations_of=st.family_id)
    return ev


class _Collect:
    @staticmethod
    def hn_front(conn, cur, ev, cid, periods, cutoff):
        rows = conn.execute(
            f"SELECT d.* FROM raw_doc d JOIN tag t ON t.doc_id = d.id WHERE t.concept_id = ? AND d.source = 'hn_front' "
            f"AND d.published_at <= ? AND d.period IN ({','.join('?' * len(periods))}) "
            "ORDER BY CAST(json_extract(d.metrics, '$.points') AS INTEGER) DESC LIMIT 3",
            (cid, cutoff, *periods),
        ).fetchall()
        for r in rows:
            ev.add(cid, _item(r, json.loads(r["metrics"]).get("points"), "points"))

    @staticmethod
    def hn_hiring(conn, cur, ev, cid, periods, cutoff):
        rows = conn.execute(
            "SELECT d.* FROM raw_doc d JOIN tag t ON t.doc_id = d.id WHERE t.concept_id = ? AND d.source = 'hn_hiring' "
            "AND d.published_at <= ? AND d.period = ? ORDER BY d.published_at DESC LIMIT 3",
            (cid, cutoff, periods[-1]),
        ).fetchall()
        for r in rows:
            ev.add(cid, _item(r, None, "job post"))

    @staticmethod
    def github(conn, cur, ev, cid, periods, cutoff):
        period, topics = periods[-1], cur.concepts[cid].github_topics
        rows = conn.execute(
            f"SELECT * FROM raw_doc WHERE source = 'github' AND kind = 'repo_count' AND period = ? "
            f"AND id IN ({','.join('?' * len(topics))})",
            (period, *[f"ghc:{t}:{period}" for t in topics]),
        ).fetchall()
        total = sum(json.loads(r["metrics"])["count"] for r in rows)
        if rows:
            top = max(rows, key=lambda r: json.loads(r["metrics"])["count"])
            ev.add(cid, {
                "id": f"ghc:{cid}:{period}", "source": "github", "kind": "repo_count",
                "title": f"{total:,} new repositories tagged {', '.join(topics)} in {period}",
                "url": top["url"], "published_at": top["published_at"], "value": total, "value_label": "repos",
            })
        # individual repos, using only star counts observed before the cutoff
        for r in conn.execute(
            """
            SELECT d.*, (SELECT value FROM artifact_metric m WHERE m.artifact_id = d.id AND m.name = 'stars'
                         AND m.observed_at <= ? ORDER BY m.observed_at DESC LIMIT 1) AS stars
            FROM raw_doc d JOIN tag t ON t.doc_id = d.id
            WHERE t.concept_id = ? AND d.kind = 'repo' AND d.published_at <= ?
            ORDER BY stars DESC LIMIT 3
            """, (cutoff, cid, cutoff),
        ):
            if r["stars"] is not None:
                ev.add(cid, _item(r, r["stars"], "stars"))

    @staticmethod
    def arxiv(conn, cur, ev, cid, periods, cutoff):
        period = periods[-1]
        count = conn.execute("SELECT * FROM raw_doc WHERE id = ?", (f"axc:{cid}:{period}",)).fetchone()
        if count:
            ev.add(cid, _item(count, json.loads(count["metrics"])["count"], "papers"))
        for r in conn.execute(
            "SELECT * FROM raw_doc WHERE source = 'arxiv' AND kind = 'paper' AND id LIKE ? AND period = ? "
            "AND published_at <= ? LIMIT 3", (f"ax:%:{cid}", period, cutoff),
        ):
            ev.add(cid, _item(r, None, "paper"))

    @staticmethod
    def dosm_jmi(conn, cur, ev, cid, periods, cutoff, occupations_of=None):
        isco = {i for i, _ in cur.concept_occupations.get(occupations_of or cid, [])}
        codes = [code for (system, code), i in cur.occupation_codes.items() if system == "MASCO" and i in isco]
        if not codes:
            return
        for r in conn.execute(
            f"SELECT * FROM raw_doc WHERE source = 'dosm_jmi' AND period = ? AND published_at <= ? "
            f"AND json_extract(metrics, '$.masco_code') IN ({','.join('?' * len(codes))}) "
            "ORDER BY CAST(json_extract(metrics, '$.offerings') AS INTEGER) DESC LIMIT 4",
            (periods[-1], cutoff, *codes),
        ):
            n = json.loads(r["metrics"])["offerings"]
            ev.add(cid, _item(r, n, "online job offerings", f"{r['title']}: {n:,} online job offerings ({r['period']})"))
