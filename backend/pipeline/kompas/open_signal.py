"""Signal Ladder statuses for skills the snapshots don't score: ESCO skills found in CVs and job postings.

A snapshot only scores the curated concepts (they have aliases and topics). Any other skill is measured here, on
request, from the same raw records and with the same rules (kompas/score.py): every Hacker News story and "Who is
hiring?" post published before the snapshot date is searched for the skill's names, monthly counts become shares
of their source, and the trend decides rung 1 (talk) and rung 2 (hiring abroad). There's no Malaysian rung: DOSM
publishes per occupation, not per skill. Results are stored per snapshot in open_status, so each skill is measured
once per snapshot.
"""

import json
import re
from collections import defaultdict

from . import open_skills
from .aggregate import Point, _complete
from .config import PARAMS, Params
from .periods import available_at, cutoff, utcnow
from .score import _rungs, project, source_state, status_from

# (source, kind, rung, HN points floor applies)
SOURCES = (("hn_front", "story", 1, True), ("hn_hiring", "hiring_post", 2, False))
EVIDENCE = 3
MIN_TERM = 3


def _pattern(terms: list[str]) -> re.Pattern | None:
    terms = [t for t in terms if len(t) >= MIN_TERM]
    if not terms:
        return None
    body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w/&.-])(?:{body})(?![\w/&])", re.IGNORECASE)


def _title(doc) -> str:
    title = doc["title"] or ""
    if doc["kind"] == "hiring_post":
        parts = [p.strip() for p in title.split("|") if p.strip()][:2]
        title = " · ".join(parts) or "A job post"
    return title if len(title) <= 120 else title[:119] + "…"


def measure(conn, snapshots: list[tuple[str, str]], ids: list[str], p: Params = PARAMS) -> None:
    """Measures each ESCO skill in `ids` for each (snapshot id, as_of) that hasn't got it yet, in one pass over
    the raw records, and stores the results."""
    ids = sorted({i for i in ids if i.startswith("esco-")})
    if not ids or not snapshots:
        return
    q = ",".join("?" * len(ids))
    sids = [s for s, _ in snapshots]
    have = {(r["snapshot_id"], r["concept_id"]) for r in conn.execute(
        f"SELECT snapshot_id, concept_id FROM open_status WHERE concept_id IN ({q}) "
        f"AND snapshot_id IN ({','.join('?' * len(sids))})", (*ids, *sids))}
    todo = [(sid, as_of) for sid, as_of in snapshots if any((sid, i) not in have for i in ids)]
    if not todo:
        return
    terms = open_skills.names(conn, ids)
    patterns = {cid: _pattern(t) for cid, t in terms.items()}
    patterns = {cid: rx for cid, rx in patterns.items() if rx}
    latest = cutoff(max(a for _, a in todo))
    like = sorted({t for cid in patterns for t in terms[cid] if len(t) >= MIN_TERM})

    # every record that could mention one of the skills, up to the latest snapshot, then exact matching here
    docs: dict[str, list] = {}
    totals: dict[str, list[tuple[str, str]]] = {}
    for source, kind, _rung, floor in SOURCES:
        where = "source = ? AND kind = ? AND published_at <= ?"
        args: list = [source, kind, latest]
        if floor:
            where += " AND CAST(json_extract(metrics, '$.points') AS INTEGER) >= ?"
            args.append(p.hn_min_points)
        totals[source] = [(r["period"], r["published_at"]) for r in conn.execute(
            f"SELECT period, published_at FROM raw_doc WHERE {where}", args)]
        if like:
            match = " OR ".join("LOWER(COALESCE(title, '') || ' ' || COALESCE(text, '')) LIKE ?" for _ in like)
            docs[source] = conn.execute(
                f"SELECT id, kind, title, text, url, period, published_at, metrics FROM raw_doc WHERE {where} "
                f"AND ({match})", [*args, *(f"%{t}%" for t in like)]).fetchall()
        else:
            docs[source] = []

    hits: dict[str, list[tuple[str, object]]] = defaultdict(list)    # cid -> [(source, doc)]
    for source, rows in docs.items():
        for d in rows:
            text = f"{d['title'] or ''}\n{d['text'] or ''}"
            for cid, rx in patterns.items():
                if rx.search(text):
                    hits[cid].append((source, d))

    now = utcnow()
    out = []
    for sid, as_of in todo:
        cut = cutoff(as_of)
        for cid in ids:
            if (sid, cid) in have:
                continue
            states = []
            for source, _kind, rung, _floor in SOURCES:
                per = defaultdict(int)
                for period, published in totals[source]:
                    if published <= cut:
                        per[period] += 1
                periods = sorted(x for x in per if _complete(x, cut))
                counts = defaultdict(int)
                for s, d in hits.get(cid, []):
                    if s == source and d["published_at"] <= cut:
                        counts[d["period"]] += 1
                if not any(counts.get(x) for x in periods):
                    continue
                pts = [Point(x, counts.get(x, 0) / per[x] if per[x] else 0.0, counts.get(x, 0), available_at(x))
                       for x in periods]
                states.append((source_state(source, pts, "count", p), rung))
            rungs = _rungs(states)
            status = status_from(rungs)
            seen = [(s, d) for s, d in hits.get(cid, []) if d["published_at"] <= cut]
            # hiring posts first (newest), then the most upvoted stories
            seen = (sorted((x for x in seen if x[0] == "hn_hiring"), key=lambda x: x[1]["published_at"], reverse=True)
                    + sorted((x for x in seen if x[0] != "hn_hiring"),
                             key=lambda x: json.loads(x[1]["metrics"] or "{}").get("points") or 0, reverse=True))
            evidence = [{"id": d["id"], "source": s, "kind": d["kind"], "title": _title(d), "url": d["url"],
                         "published_at": d["published_at"],
                         "value": json.loads(d["metrics"] or "{}").get("points") if s == "hn_front" else None,
                         "value_label": "points" if s == "hn_front" else None} for s, d in seen[:EVIDENCE]]
            out.append((sid, cid, status, json.dumps(project(status, as_of, p)),
                        json.dumps({str(k): v.to_dict() for k, v in rungs.items()}),
                        json.dumps({"items": evidence, "count": len(seen)}), now))
    conn.executemany(
        "INSERT INTO open_status (snapshot_id, concept_id, status, projected, rungs, evidence, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (snapshot_id, concept_id) DO NOTHING", out)
    conn.commit()


def rows(conn, snapshot_id: str) -> dict[str, dict]:
    """Stored statuses for one snapshot, in journey.Statuses' row shape plus the evidence items."""
    out = {}
    for r in conn.execute("SELECT * FROM open_status WHERE snapshot_id = ?", (snapshot_id,)):
        ev = json.loads(r["evidence"])
        out[r["concept_id"]] = {"status": r["status"], "projected": json.loads(r["projected"]),
                                "rungs": json.loads(r["rungs"]), "family_status": None, "evidence": ev["count"],
                                "open_evidence": ev["items"]}
    return out
