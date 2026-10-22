"""MyCOL: Malaysia's Critical Occupations List (TalentCorp and the Critical Skills Monitoring Committee).

Each edition is a PDF report. Two tables are imported:
- the final list of critical occupations (MASCO 2020, 4 digits), checked against the count the report
  states ("consists of 37 critical occupations"); kind critical_occupation;
- Appendix 1, the "top-down" shortage indicators per occupation (indicators available, how many passed
  their threshold); kind shortage_assessment. It covers many more occupations than the final list.

An edition is a judgement made once, not a time series, so neither kind feeds trend scoring. They are
Malaysian evidence at occupation level, and the official MASCO 2020 codes and titles in them are used to
cross-check pipeline/curated/occupation_code_map.csv (findings are reported; nothing is marked verified).

TalentCorp's site doesn't allow scripted downloads, so editions are listed by hand in
data/manual/mycol_editions.csv (edition, file, published_date, source_url, date_basis) and the PDFs saved
next to it. published_date is when the edition was public; date_basis says how that is known.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import config
from ..curated import Curated
from ..document import Document, release_day_end
from ..ingest import DatasetInvalid, Options, Run

MANIFEST_COLUMNS = ("edition", "file", "published_date", "source_url", "date_basis")
LIST_ROW = re.compile(r"^([1-9]\d{3}) ([A-Z][^\d%]*?)\s*$")
SHORTAGE_ROW = re.compile(r"^([1-9]\d{3}) (.+?) (\d+) (\d+) (\d+)%\s*$")


@dataclass
class Edition:
    edition: str
    stated_count: int | None
    critical: list[tuple[str, str, int]] = field(default_factory=list)          # code, title, page
    new: set[str] = field(default_factory=set)
    every: set[str] = field(default_factory=set)
    shortage: list[tuple[str, str, int, int, int, int]] = field(default_factory=list)  # code, title, avail, passed, pct, page


def _lists(pages: list[str]) -> list[tuple[str, int, list[tuple[str, str]]]]:
    """Every 'MASCO 4D | Job Title' list in the report: (caption, page, rows). The caption is the nearest
    preceding non-empty line that isn't the column header."""
    out = []
    for no, text in enumerate(pages, start=1):
        lines = [l.strip() for l in text.splitlines()]
        i = 0
        while i < len(lines):
            if re.fullmatch(r"MASCO 4D Job Title", lines[i]):
                caption = next((l for l in reversed(lines[:i]) if l), "")
                rows, j = [], i + 1
                while j < len(lines) and (m := LIST_ROW.match(lines[j])):
                    rows.append((m.group(1), m.group(2).strip()))
                    j += 1
                out.append((caption, no, rows))
                i = j
            else:
                i += 1
    return out


def parse_report(pages: list[str]) -> tuple[Edition, list[str]]:
    """(edition, errors). Errors mean the report doesn't have the expected structure."""
    errors = []
    text = "\n".join(pages)
    editions = re.findall(r"MyCOL\)?\s*(\d{4}/\d{4})", "\n".join(pages[:3]))
    if not editions:
        return Edition("", None), ["no 'MyCOL YYYY/YYYY' edition found on the first pages"]
    stated = {int(n) for n in re.findall(r"consists of (\d+) critical occupations", text)}
    if len(stated) > 1:
        errors.append(f"the report states different list sizes: {sorted(stated)}")
    ed = Edition(max(set(editions), key=editions.count), stated.pop() if len(stated) == 1 else None)

    lists = _lists(pages)
    final = [l for l in lists if re.search(r"final critical occupations list", l[0], re.I)]
    if not final:
        errors.append("no 'Final Critical Occupations List' table found")
    else:
        caption, page, rows = final[0]
        ed.critical = [(c, t, page) for c, t in rows]
    for caption, _, rows in lists:
        if re.search(r"new in the mycol", caption, re.I):
            ed.new = {c for c, _ in rows}
        if re.search(r"appeared in every", caption, re.I):
            ed.every = {c for c, _ in rows}

    in_appendix = False
    for no, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            line = line.strip()
            if re.match(r"APPENDIX 1\b", line, re.I):
                in_appendix = True
            elif re.match(r"APPENDIX 2\b", line, re.I):
                in_appendix = False
            elif in_appendix and (m := SHORTAGE_ROW.match(line)):
                code, title, avail, passed, pct = m.group(1), m.group(2), *map(int, m.group(3, 4, 5))
                if passed > avail or avail == 0:
                    errors.append(f"page {no}: {code} has {passed} of {avail} indicators passing")
                elif abs(round(100 * passed / avail) - pct) > 1:
                    errors.append(f"page {no}: {code} shows {pct}% but {passed}/{avail} is {100 * passed / avail:.0f}%")
                ed.shortage.append((code, title.strip(), avail, passed, pct, no))
    if not ed.shortage:
        errors.append("no Appendix 1 shortage-indicator rows found")

    codes = [c for c, _, _ in ed.critical]
    if len(codes) != len(set(codes)):
        errors.append("the critical list repeats an occupation code")
    if ed.critical and ed.stated_count is not None and len(ed.critical) != ed.stated_count:
        errors.append(f"the report says {ed.stated_count} critical occupations but its table lists {len(ed.critical)}")
    shortage_codes = [s[0] for s in ed.shortage]
    if len(shortage_codes) != len(set(shortage_codes)):
        errors.append("Appendix 1 repeats an occupation code")
    stray = (ed.new | ed.every) - set(codes)
    if stray:
        errors.append(f"occupations marked new/in every edition but not on the final list: {sorted(stray)}")
    return ed, errors


def read_pdf(data: bytes) -> list[str]:
    from pypdf import PdfReader

    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]


def _norm_title(t: str) -> str:
    t = t.lower().replace("organisation", "organization").replace("book-keeping", "bookkeeping")
    t = re.sub(r"\bn\.?e\.?c\.?|not elsewhere classified", "nec", t)
    t = re.sub(r"\bapplications\b", "application", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def check_code_map(cur: Curated, titles: dict[str, str], edition: str) -> tuple[list[str], list[str]]:
    """(confirmed codes, findings) comparing occupation_code_map.csv's MASCO rows with an edition's
    official MASCO 2020 codes and titles."""
    by_title = {}
    for code, title in titles.items():
        by_title.setdefault(_norm_title(title), code)
    confirmed, findings = [], []
    for (system, code), isco in sorted(cur.occupation_codes.items()):
        if system != "MASCO":
            continue
        mine = cur.occupation_titles.get(isco, "")
        theirs = titles.get(code)
        if theirs and _norm_title(theirs) == "unclassified":
            continue   # MyCOL labels some residual codes (e.g. 2529) "Unclassified": nothing to compare
        if theirs and _norm_title(theirs) == _norm_title(mine):
            confirmed.append(code)
        elif theirs:
            findings.append(f"occupation_code_map: MASCO {code} is '{mine}' in our map but '{theirs}' in MyCOL {edition}")
        elif (other := by_title.get(_norm_title(mine))):
            findings.append(f"occupation_code_map: '{mine}' is MASCO {other} in MyCOL {edition} (MASCO 2020), "
                            f"not {code}; MASCO and ISCO codes differ here")
    return confirmed, findings


def read_manifest(path: Path) -> tuple[list[dict], list[str]]:
    errors, rows = [], []
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    missing = set(MANIFEST_COLUMNS) - set(reader.fieldnames or ())
    if missing:
        return [], [f"{path.name}: missing columns {', '.join(sorted(missing))}"]
    for line, r in enumerate(reader, start=2):
        r = {k: (v or "").strip() for k, v in r.items() if k}
        if not any(r.values()) or r["edition"].startswith("#"):
            continue
        if not re.fullmatch(r"\d{4}/\d{4}", r["edition"]):
            errors.append(f"line {line}: edition {r['edition']!r} is not YYYY/YYYY")
        try:
            date.fromisoformat(r["published_date"])
        except ValueError:
            errors.append(f"line {line}: published_date {r['published_date']!r} is not YYYY-MM-DD")
        if not r["date_basis"]:
            errors.append(f"line {line}: date_basis is empty; say how the publication date is known")
        if not (path.parent / r["file"]).is_file():
            errors.append(f"line {line}: {r['file']} not found next to {path.name}")
        rows.append(r)
    if not rows and not errors:
        errors.append(f"{path.name} lists no editions")
    return rows, errors


def ingest_editions(run: Run, cur: Curated, opts: Options):
    manifest = Path(opts.file or config.MANUAL_DIR / "mycol_editions.csv")
    entries, errors = read_manifest(manifest)
    if errors:
        raise DatasetInvalid(errors)
    state = json.loads(run.checkpoint() or "{}")
    for entry in entries:
        data = (manifest.parent / entry["file"]).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if state.get(entry["edition"]) == digest and not opts.force:
            run.skip()
            continue
        ed, problems = parse_report(read_pdf(data))
        if ed.edition and ed.edition != entry["edition"]:
            problems.append(f"{entry['file']} is MyCOL {ed.edition}, but the manifest says {entry['edition']}")
        if problems:
            raise DatasetInvalid([f"{entry['file']}: {p}" for p in problems])
        published = release_day_end(entry["published_date"])
        period = entry["published_date"][:7]
        provenance = {"file": entry["file"], "sha256": digest, "edition": ed.edition, "source_url": entry["source_url"],
                      "published_date": entry["published_date"], "date_basis": entry["date_basis"]}
        shortage = {s[0]: s for s in ed.shortage}
        for code, title, page in ed.critical:
            s = shortage.get(code)
            run.save(Document(
                id=f"mycol:{ed.edition}:{code}", source="mycol", kind="critical_occupation",
                source_id=f"{ed.edition}:{code}", url=entry["source_url"] or None, title=title, text="",
                published_at=published, period=period,
                metrics={"masco_code": code, "edition": ed.edition, "new_in_edition": code in ed.new,
                         "in_every_edition": code in ed.every,
                         "shortage_indicators": {"available": s[2], "passing": s[3], "percent": s[4]} if s else None},
                raw_payload={**provenance, "table": "Final Critical Occupations List", "page": page,
                             "masco_code": code, "title": title},
            ))
        critical = {c for c, _, _ in ed.critical}
        for code, title, avail, passed, pct, page in ed.shortage:
            run.save(Document(
                id=f"mycolsh:{ed.edition}:{code}", source="mycol", kind="shortage_assessment",
                source_id=f"{ed.edition}:{code}", url=entry["source_url"] or None, title=title, text="",
                published_at=published, period=period,
                metrics={"masco_code": code, "edition": ed.edition, "indicators_available": avail,
                         "indicators_passing": passed, "percent_passing": pct, "on_final_list": code in critical},
                raw_payload={**provenance, "table": "Appendix 1: top-down shortage occupations", "page": page,
                             "masco_code": code, "title": title, "available": avail, "passing": passed, "percent": pct},
            ))
        titles = {s[0]: s[1] for s in ed.shortage} | {c: t for c, t, _ in ed.critical}
        confirmed, findings = check_code_map(cur, titles, ed.edition)
        for f in findings:
            run.warn("occupation_code_map.csv", "mapping", f)
        state[ed.edition] = digest
        run.detail.setdefault("editions", {})[ed.edition] = {
            "critical": len(ed.critical), "shortage_rows": len(ed.shortage), "new": len(ed.new),
            "code_map_confirmed": confirmed, "code_map_findings": len(findings)}
        run.commit(cursor=json.dumps(state, sort_keys=True))
