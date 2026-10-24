"""The whole ESCO skills catalogue (about 14,000 skills and 87,000 alternative names), stored in esco_skill, so a
skill outside Kompas's own list is matched in our database instead of through ESCO's search API, which is slow
during an upload and is sometimes down for days.

ESCO publishes the classification as a zip of CSV files (CC BY 4.0) about once a year. `kompas esco-catalogue`
downloads a version and loads its skills_en.csv; `--file` loads a skills_en.csv downloaded by hand.

search() ranks skills by the words a name shares with a skill's preferred or alternative names, rare words
counting for more ("data entry" ~ "maintain data entry requirements"). It only proposes candidates: the LLM still
picks the one that is the same skill, or none (kompas/open_skills.py).
"""

import csv
import io
import json
import math
import re
import threading
import time
import zipfile
from collections import defaultdict

from ..http import Http
from ..periods import utcnow

VERSION = "v1.2.1"
URL = "https://ec.europa.eu/esco/download/ESCO%20dataset%20-%20{v}%20-%20classification%20-%20en%20-%20csv.zip"
SOURCE = "ESCO (European Commission, CC BY 4.0)"
BATCH = 1000
INDEX_TTL = 3600     # the index is rebuilt at most this often (a new catalogue version is loaded once a year)

STOP = {"a", "an", "and", "the", "of", "to", "for", "in", "on", "with", "or", "at", "by", "use", "using"}


def _stem(w: str) -> str:
    for suffix, repl in (("ies", "y"), ("ing", ""), ("es", ""), ("s", "")):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)] + repl
    return w


def words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9+#]+", text.lower()) if w not in STOP]


# ---------- loading ----------


def rows_from_csv(text: str, version: str) -> list[tuple]:
    now = utcnow()
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("status") != "released" or not r.get("conceptUri") or not r.get("preferredLabel"):
            continue
        alts = sorted({a.strip() for a in (r.get("altLabels") or "").split("\n") if a.strip()})
        kind = "knowledge" if r.get("skillType", "").endswith("knowledge") else "skill"
        out.append((r["conceptUri"], r["preferredLabel"].strip(), json.dumps(alts), kind, r.get("reuseLevel") or None,
                    (r.get("description") or "")[:1000], version, now))
    return out


def load(conn, text: str, version: str) -> int:
    """Upserts the skills of one skills_en.csv. Returns how many were stored."""
    rows = rows_from_csv(text, version)
    for i in range(0, len(rows), BATCH):
        conn.executemany(
            "INSERT INTO esco_skill (uri, label, alt_labels, skill_type, reuse_level, description, version, loaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (uri) DO UPDATE SET label = excluded.label, "
            "alt_labels = excluded.alt_labels, skill_type = excluded.skill_type, reuse_level = excluded.reuse_level, "
            "description = excluded.description, version = excluded.version, loaded_at = excluded.loaded_at",
            rows[i:i + BATCH])
        conn.commit()
    _index.clear()
    return len(rows)


def download(version: str = VERSION, http: Http | None = None) -> str:
    """skills_en.csv of one ESCO version, from the classification zip."""
    http = http or Http(timeout=300, retries=2)
    data = http.get(URL.format(v=version.replace(" ", "%20"))).content
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == "skills_en.csv")
        return z.read(name).decode("utf-8")


# ---------- searching ----------

_index: dict = {}
_lock = threading.Lock()


def _build(conn) -> dict | None:
    skills, postings = [], defaultdict(list)       # postings: word -> [(skill index, label index)]
    labels: list[list[set[str]]] = []
    for r in conn.execute("SELECT uri, label, alt_labels, skill_type FROM esco_skill"):
        names = [r["label"], *json.loads(r["alt_labels"])]
        sets = [set(words(n)) for n in names]
        i = len(skills)
        skills.append({"uri": r["uri"], "label": r["label"], "type": r["skill_type"]})
        labels.append(sets)
        for j, ws in enumerate(sets):
            for w in ws:
                postings[w].append((i, j))
    if not skills:
        return None
    df = {w: len({i for i, _ in p}) for w, p in postings.items()}
    idf = {w: math.log(len(skills) / n) for w, n in df.items()}
    return {"skills": skills, "labels": labels, "postings": postings, "idf": idf, "built": time.monotonic()}


def index(conn) -> dict | None:
    """The in-memory search index over esco_skill, or None when the catalogue hasn't been loaded."""
    with _lock:
        if not _index or time.monotonic() - _index.get("built", 0) > INDEX_TTL:
            built = _build(conn)
            _index.clear()
            if built:
                _index.update(built)
        return _index or None


def search(ix: dict, name: str, limit: int = 8) -> list[dict]:
    """ESCO's closest skills to a name, best first, in the shape ESCO's search API returns ({uri, label, type})."""
    q = set(words(name))
    if not q:
        return []
    idf = ix["idf"]
    q_weight = sum(idf.get(w, 0) for w in q) or 1
    best: dict[int, float] = {}
    for w in q:
        for i, j in ix["postings"].get(w, ()):
            if i in best and best[i] >= 2:
                continue
            ws = ix["labels"][i][j]
            shared = sum(idf.get(x, 0) for x in q & ws)
            l_weight = sum(idf.get(x, 0) for x in ws) or 1
            score = 0.7 * shared / q_weight + 0.3 * shared / l_weight + (1.0 if ws == q else 0) + (0.02 if j == 0 else 0)
            if score > best.get(i, 0):
                best[i] = score
    top = sorted(best, key=lambda i: (-best[i], len(ix["skills"][i]["label"])))[:limit]
    return [dict(ix["skills"][i]) for i in top]
