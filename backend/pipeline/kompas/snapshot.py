"""Builds a dated snapshot (statuses, evidence, feed), diffs it against the previous one, exports JSON."""

import json
import shutil

from . import config
from .aggregate import build_series
from .config import PARAMS, Params
from .curated import Curated
from .evidence import collect
from .feed import rank
from .periods import cutoff, utcnow
from .score import score_all
from .tag import retag

TRACKED_FIELDS = ("status", "family_status", "projected.moderate", "projected.fast")


def build(conn, cur: Curated, as_of: str, p: Params = PARAMS, export: bool = False) -> dict:
    """Scores a snapshot into the database. export=True also writes JSON copies to data/snapshots/."""
    retag(conn, cur)
    cut = cutoff(as_of)
    series = build_series(conn, cur, cut, p)
    states = score_all(series, cur, as_of, p)
    ev = collect(conn, cur, series, states, cut)
    feed = rank(conn, cut, p)

    sources = []
    for s in cur.sources.values():
        periods = sorted({pt.period for (c, src), pts in series.items() if src == s.id for pt in pts})
        last = conn.execute(
            "SELECT MAX(finished_at) AS t FROM fetch_log WHERE source = ? AND ok = 1 AND started_at < ?", (s.id, cut)
        ).fetchone()["t"]
        sources.append({
            "id": s.id, "name": s.name, "rung": s.rung, "grain": s.grain,
            "latest_period": periods[-1] if periods else None, "periods": len(periods),
            "last_fetched_at": last, "coverage_note": s.coverage_note, "licence_note": s.licence_note,
        })

    snap = {"id": as_of, "as_of": as_of, "created_at": utcnow(), "params": p.to_dict(),
            "sources": sources, "curated_version": cur.version}
    concepts = []
    for cid, st in states.items():
        c = cur.concepts[cid]
        concepts.append({
            "id": cid, "label": c.label, "kind": c.kind, "parent_id": c.parent_id, "esco_uri": c.esco_uri,
            "status": st.status, "family_id": st.family_id, "family_status": st.family_status,
            "projected": st.projected,
            "rungs": {str(k): r.to_dict() for k, r in st.rungs.items()},
            "evidence_ids": ev.by_concept.get(cid, []),
        })

    _write(conn, snap, concepts, list(ev.items.values()), feed)
    prev = conn.execute("SELECT id FROM snapshot WHERE as_of < ? ORDER BY as_of DESC LIMIT 1", (as_of,)).fetchone()
    changes = diff(conn, prev["id"], as_of) if prev else {"from": None, "to": as_of, "changes": []}
    conn.commit()
    if export:
        export_json(snap, concepts, list(ev.items.values()), feed, changes)
    return {"id": as_of, "concepts": len(concepts), "evidence": len(ev.items), "feed": len(feed),
            "changes": len(changes["changes"]), "statuses": _count(concepts)}


def _count(concepts: list[dict]) -> dict:
    out: dict[str, int] = {}
    for c in concepts:
        out[c["status"]] = out.get(c["status"], 0) + 1
    return out


def _write(conn, snap: dict, concepts: list[dict], evidence: list[dict], feed: list[dict]):
    sid = snap["id"]
    for table in ("concept_status", "evidence", "snapshot_feed", "change"):
        conn.execute(f"DELETE FROM {table} WHERE snapshot_id = ?", (sid,))
    conn.execute("DELETE FROM snapshot WHERE id = ?", (sid,))
    conn.execute(
        "INSERT INTO snapshot (id, as_of, created_at, params, sources, curated_version) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, snap["as_of"], snap["created_at"], json.dumps(snap["params"]), json.dumps(snap["sources"]),
         snap["curated_version"]),
    )
    conn.executemany(
        "INSERT INTO concept_status (snapshot_id, concept_id, status, family_id, family_status, projected, rungs, "
        "evidence_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(sid, c["id"], c["status"], c["family_id"], c["family_status"], json.dumps(c["projected"]),
          json.dumps(c["rungs"]), json.dumps(c["evidence_ids"])) for c in concepts],
    )
    conn.executemany(
        "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(sid, e["id"], e["source"], e["kind"], e["title"], e["url"], e["published_at"], e["value"],
          e["value_label"], json.dumps(e["concept_ids"])) for e in evidence],
    )
    conn.executemany("INSERT INTO snapshot_feed VALUES (?, ?, ?)",
                     [(sid, i, json.dumps(item)) for i, item in enumerate(feed)])


def _field(row, name: str):
    if name.startswith("projected."):
        return json.loads(row["projected"]).get(name.split(".", 1)[1])
    return row[name]


def _reason(old_rungs: dict, new_rungs: dict) -> str:
    parts = []
    for k in ("3", "2", "1"):
        o, n = old_rungs.get(k, {}), new_rungs.get(k, {})
        if n.get("active") and not o.get("active"):
            parts.append(f"rung {k} activated ({', '.join(n.get('active_sources') or n.get('sources') or [])})")
        elif o.get("active") and not n.get("active"):
            parts.append(f"rung {k} no longer active")
        if n.get("declining") and not o.get("declining"):
            parts.append(f"rung {k} declining")
    return "; ".join(parts) or "trend moved"


def diff(conn, a: str, b: str) -> dict:
    old = {r["concept_id"]: r for r in conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ? ORDER BY concept_id", (a,))}
    new = {r["concept_id"]: r for r in conn.execute("SELECT * FROM concept_status WHERE snapshot_id = ? ORDER BY concept_id", (b,))}
    changes = []
    for cid, n in new.items():
        o = old.get(cid)
        if o is None:
            continue
        for f in TRACKED_FIELDS:
            before, after = _field(o, f), _field(n, f)
            if before != after:
                changes.append({
                    "concept_id": cid, "field": f, "from": before, "to": after,
                    "reason": _reason(json.loads(o["rungs"]), json.loads(n["rungs"])),
                    "evidence_ids": json.loads(n["evidence_ids"]),
                })
    conn.execute("DELETE FROM change WHERE snapshot_id = ?", (b,))
    conn.executemany(
        "INSERT INTO change VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(b, a, c["concept_id"], c["field"], c["from"], c["to"], c["reason"], json.dumps(c["evidence_ids"]))
         for c in changes],
    )
    return {"from": a, "to": b, "changes": changes}


def export_json(snap, concepts, evidence, feed, changes):
    out = config.snapshot_dir() / snap["id"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, data in (("snapshot", snap), ("concepts", concepts), ("evidence", evidence), ("feed", feed),
                       ("changes", changes)):
        (out / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
