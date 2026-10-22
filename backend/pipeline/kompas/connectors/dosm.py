"""DOSM Job Market Insights (rung 3). Imported from a CSV built from each quarterly release's data file.

Expected columns (one row per occupation per quarter):
    period,release_date,masco_code,occupation,offerings,source_url
    2026Q2,2026-08-14,2411,Accountants,22067,https://www.dosm.gov.my/...

release_date is the day the release went public; it decides which snapshots may use the row.
"""

import csv
from pathlib import Path

from .. import config
from ..curated import Curated
from ..db import upsert_doc

COLUMNS = ("period", "release_date", "masco_code", "occupation", "offerings", "source_url")


def import_csv(conn, cur: Curated, path: Path | None = None) -> int:
    path = path or config.MANUAL_DIR / "dosm_jmi.csv"
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        n = 0
        for row in reader:
            if not row["period"].strip() or row["period"].startswith("#"):
                continue
            period, code = row["period"].strip(), row["masco_code"].strip()
            upsert_doc(conn, {
                "id": f"dosm:{period}:{code}",
                "source": "dosm_jmi",
                "kind": "occupation_stat",
                "url": row["source_url"].strip(),
                "title": row["occupation"].strip(),
                "text": "",
                "published_at": f"{row['release_date'].strip()}T00:00:00Z",
                "period": period,
                "metrics": {"masco_code": code, "offerings": int(row["offerings"].replace(",", ""))},
            })
            n += 1
    conn.commit()
    return n
