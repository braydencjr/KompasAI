"""Turns raw docs into one time series per (concept, source): the concept's share of that source per period.

Only data public before the cutoff is used: complete periods for monthly sources, released
quarters for DOSM.
"""

import json
from collections import defaultdict
from dataclasses import dataclass

from .config import Params
from .curated import Curated
from .periods import available_at


@dataclass(frozen=True)
class Point:
    period: str
    value: float        # share of the source in that period
    raw_count: float    # mentions / repos / papers / offerings behind the value
    available_at: str


Series = dict[tuple[str, str], list[Point]]


def build_series(conn, cur: Curated, cutoff: str, params: Params) -> Series:
    out: Series = {}
    _text(conn, out, "hn_front", "story", cutoff, min_points=params.hn_min_points)
    _text(conn, out, "hn_hiring", "hiring_post", cutoff)
    _github(conn, cur, out, cutoff)
    _arxiv(conn, out, cutoff)
    _dosm(conn, cur, out, cutoff)
    return out


def _complete(period: str, cutoff: str) -> bool:
    return available_at(period) <= cutoff


def _emit(out: Series, source: str, totals: dict[str, float], counts: dict[str, dict[str, float]],
          avail: dict[str, str] | None = None):
    periods = sorted(totals)
    for cid, by_period in counts.items():
        if not any(by_period.values()):
            continue
        out[(cid, source)] = [
            Point(p, (by_period.get(p, 0) / totals[p]) if totals[p] else 0.0, by_period.get(p, 0),
                  (avail or {}).get(p) or available_at(p))
            for p in periods
        ]


def _text(conn, out: Series, source: str, kind: str, cutoff: str, min_points: int | None = None):
    where = "d.source = ? AND d.kind = ? AND d.published_at <= ?"
    args: list = [source, kind, cutoff]
    if min_points is not None:
        where += " AND CAST(json_extract(d.metrics, '$.points') AS INTEGER) >= ?"
        args.append(min_points)
    totals = {
        r["period"]: r["n"]
        for r in conn.execute(f"SELECT d.period, COUNT(*) n FROM raw_doc d WHERE {where} GROUP BY d.period", args)
        if _complete(r["period"], cutoff)
    }
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    for r in conn.execute(
        f"SELECT d.period, t.concept_id, COUNT(*) n FROM raw_doc d JOIN tag t ON t.doc_id = d.id "
        f"WHERE {where} GROUP BY d.period, t.concept_id", args
    ):
        if r["period"] in totals:
            counts[r["concept_id"]][r["period"]] = r["n"]
    _emit(out, source, totals, counts)


def _github(conn, cur: Curated, out: Series, cutoff: str):
    per_topic: dict[str, dict[str, int]] = defaultdict(dict)
    for r in conn.execute(
        "SELECT period, metrics FROM raw_doc WHERE source = 'github' AND kind = 'repo_count' AND published_at <= ?",
        (cutoff,),
    ):
        m = json.loads(r["metrics"])
        per_topic[r["period"]][m["topic"]] = m["count"]
    totals = {p: sum(t.values()) for p, t in per_topic.items()}
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    for c in cur.concepts.values():
        for p, topics in per_topic.items():
            n = sum(topics.get(t, 0) for t in c.github_topics)
            if c.github_topics:
                counts[c.id][p] = n
    _emit(out, "github", totals, counts)


def _arxiv(conn, out: Series, cutoff: str):
    totals, counts = {}, defaultdict(dict)
    for r in conn.execute(
        "SELECT kind, period, metrics FROM raw_doc WHERE source = 'arxiv' "
        "AND kind IN ('paper_baseline', 'paper_count') AND published_at <= ?", (cutoff,)
    ):
        m = json.loads(r["metrics"])
        if r["kind"] == "paper_baseline":
            totals[r["period"]] = m["count"]
        else:
            counts[m["concept_id"]][r["period"]] = m["count"]
    _emit(out, "arxiv", totals, {c: {p: v for p, v in by.items() if p in totals} for c, by in counts.items()})


def _dosm(conn, cur: Curated, out: Series, cutoff: str):
    offerings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # period -> isco -> n
    totals: dict[str, float] = defaultdict(float)
    avail: dict[str, str] = {}
    for r in conn.execute(
        "SELECT period, published_at, metrics FROM raw_doc WHERE source = 'dosm_jmi' "
        "AND kind = 'occupation_stat' AND published_at <= ?", (cutoff,)
    ):
        m = json.loads(r["metrics"])
        totals[r["period"]] += m["offerings"]
        avail[r["period"]] = max(avail.get(r["period"], ""), r["published_at"])
        isco = cur.occupation_codes.get(("MASCO", m["masco_code"]))
        if isco:  # unmapped codes still count toward the total
            offerings[r["period"]][isco] += m["offerings"]
    for cid, occs in cur.concept_occupations.items():
        series = []
        for p in sorted(totals):
            share = sum(w * offerings[p].get(isco, 0) for isco, w in occs) / totals[p] if totals[p] else 0.0
            raw = sum(offerings[p].get(isco, 0) for isco, _ in occs)
            series.append(Point(p, share, raw, avail[p]))
        if any(pt.raw_count for pt in series):
            out[(cid, "dosm_jmi")] = series
