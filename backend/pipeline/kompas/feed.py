"""Trending feed: tagged artifacts ranked by momentum.

Momentum is how fast something is gaining attention right now:
- HN story: points per hour since posting (with a 2-hour offset so brand-new posts don't spike).
- GitHub repo: stars gained per day between observations; with only one observation, stars per
  day since the repo was created.
Each source is normalised to 0..1 separately, because points and stars aren't comparable.
Only items that name a skill in their title or repo topics qualify.
"""

import json
from datetime import timedelta

from .config import Params
from .periods import iso, parse, utcnow


def _strong_concepts(conn, ids: list[str], titles: dict[str, str]) -> dict[str, list[str]]:
    """Concepts named in an item's title or repo topics. A passing mention in body text is too weak
    to put an item in someone's feed (it still counts toward trend statistics)."""
    out: dict[str, list[str]] = {i: [] for i in ids}
    for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
        for t in conn.execute(
            f"SELECT doc_id, concept_id, method, span FROM tag WHERE doc_id IN ({','.join('?' * len(chunk))})", chunk
        ):
            if t["method"] == "topic" or (t["span"] and t["span"].lower() in titles[t["doc_id"]].lower()):
                out[t["doc_id"]].append(t["concept_id"])
    return out


def _hn_candidates(conn, since: str, until: str, p: Params) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source, kind, title, url, published_at, metrics FROM raw_doc "
        "WHERE source = 'hn_front' AND kind = 'story' AND published_at >= ? AND published_at <= ?",
        (since, until),
    ).fetchall()
    strong = _strong_concepts(conn, [r["id"] for r in rows], {r["id"]: r["title"] for r in rows})
    out = []
    for r in rows:
        points = json.loads(r["metrics"]).get("points") or 0
        if not strong[r["id"]] or points < p.feed_min_points:
            continue
        age_h = max((parse(until) - parse(r["published_at"])).total_seconds() / 3600, 0)
        out.append(_candidate(r, strong[r["id"]], points / (age_h + 2), "points/hour", {"points": points}))
    return out


def _repo_candidates(conn, since: str, until: str, p: Params) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source, kind, title, url, published_at, text FROM raw_doc "
        "WHERE kind = 'repo' AND published_at >= ? AND published_at <= ?", (since, until),
    ).fetchall()
    strong = _strong_concepts(conn, [r["id"] for r in rows], {r["id"]: r["title"] for r in rows})
    window_start = iso(parse(until) - timedelta(hours=48))
    out = []
    for r in rows:
        if not strong[r["id"]]:
            continue
        obs = conn.execute(
            "SELECT observed_at, value FROM artifact_metric WHERE artifact_id = ? AND name = 'stars' "
            "AND observed_at <= ? ORDER BY observed_at", (r["id"], until),
        ).fetchall()
        if not obs:
            continue  # no star count observed before this moment: unusable without look-ahead
        recent = [o for o in obs if o["observed_at"] >= window_start]
        first, last = (recent[0], recent[-1]) if len(recent) >= 2 else (None, obs[-1])
        span_days = (parse(last["observed_at"]) - parse(first["observed_at"])).total_seconds() / 86400 if first else 0
        if first and span_days >= 1 / 24:
            rate = (last["value"] - first["value"]) / span_days
        else:
            age_days = max((parse(last["observed_at"]) - parse(r["published_at"])).total_seconds() / 86400, 1)
            rate = last["value"] / age_days
        if rate < p.feed_min_stars_per_day or last["value"] < p.feed_min_stars:
            continue
        out.append(_candidate(r, strong[r["id"]], rate, "stars/day",
                              {"stars": int(last["value"]), "description": (r["text"] or "")[:160]}))
    return out


def _candidate(r, concept_ids: list[str], rate: float, label: str, counts: dict) -> dict:
    return {
        "artifact_id": r["id"], "source": r["source"], "kind": r["kind"], "title": r["title"], "url": r["url"],
        "published_at": r["published_at"], "momentum_raw": round(rate, 3), "momentum_label": label,
        "concept_ids": sorted(set(concept_ids)), **counts,
    }


def rank(conn, until: str, p: Params) -> list[dict]:
    hn_since = iso(parse(until) - timedelta(hours=p.feed_hn_hours))
    repo_since = iso(parse(until) - timedelta(days=p.feed_window_days))
    items = []
    for group in (_hn_candidates(conn, hn_since, until, p), _repo_candidates(conn, repo_since, until, p)):
        top = max((c["momentum_raw"] for c in group), default=0) or 1
        for c in group:
            c["momentum"] = round(c["momentum_raw"] / top, 4)
        items.extend(group)
    items.sort(key=lambda c: c["momentum"], reverse=True)
    return items[: p.feed_size]


def refresh_live(conn, p: Params) -> list[dict]:
    """Re-ranks the live feed and returns events for items that are new or rising (+25% momentum)."""
    now = utcnow()
    events = []
    ranked = rank(conn, now, p)
    for item in ranked:
        prev = conn.execute("SELECT momentum_raw FROM feed_item WHERE artifact_id = ?", (item["artifact_id"],)).fetchone()
        kind = "new" if prev is None else ("rising" if item["momentum_raw"] > prev["momentum_raw"] * 1.25 else None)
        conn.execute(
            """
            INSERT INTO feed_item (artifact_id, source, kind, title, url, published_at, momentum, momentum_raw,
                                   momentum_label, concept_ids, counts, first_seen, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET momentum = excluded.momentum, momentum_raw = excluded.momentum_raw,
              title = excluded.title, concept_ids = excluded.concept_ids, counts = excluded.counts,
              updated_at = excluded.updated_at
            """,
            (item["artifact_id"], item["source"], item["kind"], item["title"], item["url"], item["published_at"],
             item["momentum"], item["momentum_raw"], item["momentum_label"], json.dumps(item["concept_ids"]),
             json.dumps({k: item[k] for k in ("points", "stars", "description") if k in item}), now, now),
        )
        if kind:
            cur = conn.execute(
                "INSERT INTO feed_event (at, type, artifact_id, payload) VALUES (?, ?, ?, ?)",
                (now, kind, item["artifact_id"], json.dumps(item)),
            )
            events.append({"seq": cur.lastrowid, "type": kind, "at": now, "item": item})
    keep = {i["artifact_id"] for i in ranked}
    for row in conn.execute("SELECT artifact_id FROM feed_item").fetchall():
        if row["artifact_id"] not in keep:
            conn.execute("DELETE FROM feed_item WHERE artifact_id = ?", (row["artifact_id"],))
    conn.commit()
    return events
