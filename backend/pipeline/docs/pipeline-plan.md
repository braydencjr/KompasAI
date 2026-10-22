# Kompas Signal Pipeline: Implementation Plan

> Scope: **Part 1, the signal pipeline**, plus the snapshot format it writes. Part 2 (the per-user matcher) appears at the end as an optional phase.
> Based on PRD v1.1 §8, with these changes: a lean build (no database, no orchestrator), a **skill-concept layer** between trending artifacts and job demand, and a **trending feed**.

---

## 1. What the pipeline does

```
Fetch → Tag → Aggregate → Score → Snapshot → Diff
```

- **Input:** public sources (GitHub, Hacker News, arXiv, DOSM, MyCOL) and the curated CSV tables.
- **Output:** one folder per snapshot date in `data/snapshots/<as_of>/`. It holds ladder statuses for each skill concept, an evidence trail, a trending feed, and what changed since the previous snapshot.
- **Run model:** CLI commands, run by hand or by GitHub Actions cron. Raw data and snapshots are committed to the repo, so the demo works offline and any snapshot can be rebuilt from the repo alone.

### Core rules

1. **Artifacts never get a status.** A repo, tool or news item counts as evidence for one or more **concepts**. Only concepts climb the ladder.
2. **Closed world.** Only concepts listed in `curated/concepts.csv` are scored. Each one links to ESCO where possible.
3. **No look-ahead.** A snapshot dated D uses only records with `published_at ≤ D`.
4. **No LLM in this pipeline** (PRD FR-10.2). Tagging uses dictionary and alias matching, plus human review of anything left unmatched.

---

## 2. Repository layout

```
pipeline/
  pyproject.toml                 # Python 3.12, uv; deps: httpx, pandas, pydantic, tenacity, pytest
  kompas/
    cli.py                       # entry point: `kompas <command>`
    models.py                    # pydantic models: RawDoc, Artifact, Evidence, snapshot schema
    asof.py                      # publication-date filter
    connectors/
      base.py                    # Connector protocol: fetch(since, until) -> list[RawDoc]
      arxiv.py
      hn_front.py                # HN stories with high points (rung 1)
      hn_hiring.py               # "Who is hiring?" comments (rung 2, tech)
      github.py                  # new repos by topic (backfill) + star-gain polling (live)
      dosm.py                    # Job Market Insights file import (rung 3)
      mycol.py                   # critical-occupations import (catalogue flag)
    tag.py                       # text/topics -> concept ids (dictionary, alias)
    aggregate.py                 # per concept × source × period values
    score.py                     # smoothing, trend, rung activation, status
    snapshot.py                  # writes data/snapshots/<as_of>/
    diff.py                      # compares two snapshots -> changes.json
    feed.py                      # ranks trending artifacts
    match.py                     # Part 2 (optional): profile × snapshot
  curated/                       # hand-made, reviewed in PRs
    sources.csv
    concepts.csv
    concept_alias.csv
    concept_occupation.csv
    occupation_code_map.csv
  tests/
    fixtures/                    # recorded API responses, one per connector
data/
  raw/<source>/<period>.jsonl.gz # committed; never edited after it is written
  snapshots/<as_of>/*.json       # committed; the app reads these
  review/unmatched.csv           # trending items that matched no concept
docs/pipeline-plan.md            # this file
```

Add to `.gitignore`: `pipeline/.venv/`, `**/__pycache__/`, `data/cache/`.

---

## 3. Snapshot format (the contract with the rest of the team)

**Publish this first, together with a hand-written stub snapshot, so frontend and API work can start straight away.**

`data/snapshots/<as_of>/` contains:

**`snapshot.json`**
```json
{
  "id": "2026-07-01",
  "as_of": "2026-07-01",
  "created_at": "2026-10-22T10:00:00Z",
  "sources": [
    { "id": "dosm_jmi", "latest_period": "2026Q1", "coverage_note": "Online ads from major private recruitment platforms only" }
  ],
  "params": { "z_active": 1.5, "min_mentions": 5, "smoothing": 2, "fast_lead_factor": 0.5, "default_lead_quarters": 4 }
}
```

**`concepts.json`**: one entry per scored concept
```json
{
  "id": "agentic-coding",
  "label": "Agentic coding workflows",
  "parent_id": "ai-assisted-dev",
  "esco_uri": null,
  "status": "Emerging",
  "family_status": "Act now",
  "projected": { "moderate": "Emerging", "fast": "Act now" },
  "rungs": {
    "1": { "active": true,  "trend": 2.4, "low_confidence": false, "sources": ["github", "hn_front", "arxiv"] },
    "2": { "active": true,  "trend": 1.7, "low_confidence": false, "sources": ["hn_hiring"] },
    "3": { "active": false, "trend": 0.3, "low_confidence": false, "sources": ["dosm_jmi"], "level": "family" }
  },
  "evidence_ids": ["gh:mattpocock/skills", "hnh:2026-06:41234567", "dosm:2026Q1:2512"]
}
```
Allowed `status` values: `Watch | Emerging | Act now | Stable | Declining | Stalled`. `Stalled` is a stretch goal (see §6.4).

**`evidence.json`**
```json
{ "id": "gh:mattpocock/skills", "source": "github", "kind": "repo", "title": "mattpocock/skills",
  "url": "https://github.com/mattpocock/skills", "published_at": "2026-06-12", "value": 8123,
  "value_label": "stars", "concept_ids": ["agentic-coding"] }
```

**`feed.json`**: trending artifacts, ranked
```json
{ "artifact_id": "gh:mattpocock/skills", "title": "...", "url": "...", "kind": "repo",
  "momentum": 0.92, "concept_ids": ["agentic-coding"], "published_at": "2026-06-12" }
```

**`changes.json`**: compared with the previous snapshot
```json
{ "from": "2026-04-01", "to": "2026-07-01",
  "changes": [ { "concept_id": "power-bi", "from": "Emerging", "to": "Act now",
                 "reason": "rung 3 activated", "evidence_ids": ["dosm:2026Q1:2411"] } ] }
```

The Next.js app can read these files directly with `fs` in a server component. No API is needed for the demo.

---

## 4. Curated tables

| File | Columns | Prelim target |
|---|---|---|
| `sources.csv` | id, name, rung, grain (month/quarter), url, licence_note, coverage_note | 6 rows |
| `concepts.csv` | id, label, kind (`skill`/`capability`/`family`), parent_id, esco_uri, arxiv_query, github_topics | 60–100 concepts, covering finance/ops (Aisyah) **and** tech (CS-grad persona) |
| `concept_alias.csv` | alias, concept_id, case_sensitive | ~300 aliases (tool and brand names: `Claude Code`, `Cursor` → `agentic-coding`; `Power BI` → `data-visualisation`) |
| `concept_occupation.csv` | concept_id, isco_code, weight (1.0 essential / 0.5 optional) | Derived from ESCO occupation-skill links where `esco_uri` is set; hand-written for new concepts |
| `occupation_code_map.csv` | source_system (`MASCO`), source_code, source_title, isco_code | The ~30 occupations reachable from the demo personas, plus anything DOSM lists in its top occupations |

`kind = capability` rows form the **capability bridge**: what AI can do, e.g. `document-ai`. Whoever builds the Mirror links these to occupation tasks in a separate table, using the same concept ids.

---

## 5. Connectors

Every connector implements `fetch(since, until) -> list[RawDoc]` and writes `data/raw/<source>/<period>.jsonl.gz`. A period that is already on disk is skipped unless `--force` is passed, so re-running is always safe.

`RawDoc = {id, source, url, title, text, topics[], published_at, fetched_at, metrics{}, content_hash}`

| Connector | Rung | Grain | Backfill | Endpoint and method | Notes |
|---|---|---|---|---|---|
| `arxiv` | 1 | month | 12–24 months | `export.arxiv.org/api/query`: for each concept's `arxiv_query`, add `submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]`, `max_results=5`. Read `opensearch:totalResults` as the count; the top 5 papers become evidence. One baseline query per month, using the category filter only, gives the denominator. | Wait 3 s between requests, one connection at a time. About 100 concepts × 12 months ≈ 1 hour, run once. |
| `hn_front` | 1 | month | 12 months | Algolia `search_by_date?tags=story&numericFilters=created_at_i>=A,created_at_i<B,points>=100`, split into week windows (results are capped at 1,000 per query) | Points settle within days of posting, so look-ahead leakage is negligible. |
| `hn_hiring` | 2 (tech) | month | 12 threads | Find threads with `search_by_date?tags=story,author_whoishiring`, then `items/<id>` for the comments | Coverage note: tech-heavy, US-centric. |
| `github` | 1 | month | 12 months | **Backfill:** `search/repositories?q=topic:<t> created:<range>` and read `total_count` (a repo's creation date never changes, so there is no leakage). **Live:** poll the top repos for each topic every day and store `stargazers_count` so star gains can be computed. | Use a token: the search API allows 30 requests/min. **Don't use current star counts in historical snapshots**: that would leak future information. |
| `dosm` | 3 | quarter | Every JMI release available (~2022→) | Download the "Data JMI" file for each release into `data/cache/dosm/`, then parse it into occupation rows | `published_at` = the release date, not the end of the quarter. Format still to be confirmed (Phase 0). |
| `mycol` | — | edition | 2 editions | Import the occupation list by hand → `critical` flag | Anchors the role catalogue; not used as a trend. |

**Deferred:** Hugging Face Hub, and a rung-2 non-tech source (Indeed Hiring Lab tracker, if Phase 0 confirms it). Without the second one, rung 2 for non-tech concepts stays empty. That's acceptable, because rung 3 (DOSM) still covers them. State this gap openly in the coverage notes.

---

## 6. Processing stages

### 6.1 Tag (`tag.py`)
For each raw doc, matching runs in this order:
1. **Topics** (GitHub): exact match against `concepts.github_topics`.
2. **Dictionary:** whole-word, case-insensitive match against concept labels and ESCO labels.
3. **Alias:** match against `concept_alias.csv`.
4. Anything unmatched with high momentum is appended to `data/review/unmatched.csv` (artifact, title, url, momentum). A person adds an alias or a concept, then re-runs. No embeddings in the prelim.

Each match is recorded as `{doc_id, concept_id, method, matched_span}`.

### 6.2 Aggregate (`aggregate.py`)
For each concept × source × period:
- **Text sources** (HN, arXiv): `value = matched docs / total docs` in the period, with `raw_count` kept alongside.
- **GitHub:** `value = new repos with the concept's topics / all new repos across the tracked topics`.
- **DOSM:** occupation offerings → shares → distributed to concepts via `concept_occupation` (MASCO → ISCO through `occupation_code_map`). A concept's value is the weighted sum over its occupations. Also produce a **family-level** value by summing over the concept's parent.
- When a concept appears in several sources on the same rung, it is active on that rung if **any** source is active. Record which sources were active.

### 6.3 Score (`score.py`)
For each concept × source series, using only periods with `published_at ≤ as_of`:
1. Smooth with a 2-period rolling mean.
2. If there are at least 4 earlier periods: `trend = (v_t − mean(v_{t−k..t−1})) / (std + ε)`, with `k = min(8, available)`.
   Otherwise: `trend = v_t / v_{t−1} − 1`, set `low_confidence = true`, and use a threshold of +0.5 instead of +1.5.
3. **Active** if `trend ≥ 1.5` **and** the volume floor is met (`raw_count ≥ 5` for text sources; share ≥ 0.5% for DOSM).
4. **Status** (first rule that matches wins):
   - trend ≤ −1.5 on rung 2 or rung 3 → `Declining`
   - rung 3 active → `Act now`
   - rung 2 active → `Emerging`
   - rung 1 active → `Watch`
   - otherwise → `Stable`
5. **Family status:** apply the same rules to the parent concept's rung-3 series. This is how a concept with no direct Malaysian demand shows "Software development · Act now".

### 6.4 Scenarios and Stalled
- **Projection (for the Ghost CV):** a `Watch` or `Emerging` concept is projected one step up if `lead_time × factor ≤ horizon`. Here `lead_time` defaults to 4 quarters, `factor` is 1.0 for Moderate and 0.5 for Fast, and the horizon runs to 2028. The defaults are written into `snapshot.params` and labelled as defaults in the UI. Replace them with measured lead times only if the backfill yields enough examples.
- **Stalled (stretch goal):** rung 1 has been active for longer than `2 × lead_time` with no rung-2 activity → `Stalled`.

### 6.5 Feed (`feed.py`)
`momentum` = star gain per day (GitHub, live) or points per hour since posting (HN), normalised within each source to 0–1. Keep the top 50 tagged artifacts. In historical snapshots, the feed uses only HN items (points are final) and repos created in that period ranked by creation count. It never uses current stars.

### 6.6 Snapshot and diff
`kompas snapshot --as-of D` runs Tag → Aggregate → Score → Feed for date D and writes the folder. `kompas diff A B` writes `changes.json` into B's folder, listing every concept whose `status`, `family_status` or `projected` value changed, with the evidence that caused it.

---

## 7. CLI

```
kompas fetch <source> [--since YYYY-MM] [--until YYYY-MM] [--force]
kompas backfill                     # every source, full history
kompas snapshot --as-of 2026-07-01
kompas diff 2026-04-01 2026-07-01
kompas review                       # prints the unmatched queue, sorted by momentum
kompas validate                     # checks curated CSVs (ids, parents, aliases point to real concepts)
```

---

## 8. Build phases

Effort is shown in working days for one person. Exact dates depend on the submission deadline (PRD §16, still open).

### Phase 0: Verify the data (days 1–2)
- [ ] Download two or three DOSM "Data JMI" files. Record the format, which occupation-code level they use, and how far back the history goes.
- [ ] Confirm that MASCO 2020 codes map onto ISCO-08 4-digit codes. Find DOSM's MASCO documentation.
- [ ] Download the ESCO bulk CSV (pin the version). Check which languages it includes; Malay and Chinese labels are probably missing, so update PRD NFR-4 if so.
- [ ] Decide on a rung-2 non-tech source: check the Indeed Hiring Lab tracker, or accept the gap.
- [ ] Create a GitHub token and confirm the search rate limits.

**Done when:** every row in the §5 table is confirmed, replaced or explicitly deferred, and the PRD is updated wherever an assumption turned out wrong.

### Phase 1: Skeleton and contract (days 2–3)
- [ ] Create `pipeline/` with uv, pydantic models for the snapshot schema, and a CLI skeleton.
- [ ] Hand-write a stub snapshot in `data/snapshots/stub/` using Aisyah's concepts and realistic values.
- [ ] Share the §3 format with the team.

**Done when:** the frontend can render the stub snapshot.

### Phase 2: Curated tables v0 (days 3–5; can run alongside Phase 3)
- [ ] `concepts.csv`: 60+ concepts. Start from the skills and gaps already in `app/data/bets.ts`, then add capabilities (document AI, reconciliation automation, forecasting, support assistants, report generation, code generation, agentic coding).
- [ ] `concept_alias.csv`: 150+ aliases to begin with.
- [ ] `occupation_code_map.csv` and `concept_occupation.csv` for the demo occupations.
- [ ] `kompas validate` passes.

**Done when:** every skill and gap shown for Aisyah in the current UI has a concept id.

### Phase 3: Connectors and backfill (days 4–8)
Order: `dosm` → `arxiv` → `hn_hiring` → `github` → `hn_front` → `mycol`.
- [ ] Each connector has a recorded fixture and a test that parses it.
- [ ] `kompas backfill` completes, and the raw data is committed.

**Done when:** `data/raw/` holds at least 12 months of each monthly source and every available DOSM quarter.

### Phase 4: Tag, aggregate, score, snapshot (days 7–10)
- [ ] Implement §6.1–6.3 and §6.6.
- [ ] Tests: golden values for the trend and status rules; **a look-ahead test** that fails if any value in snapshot D has `published_at > D`.
- [ ] Produce snapshots for the first day of each month across the backfill range.

**Done when:** each of Aisyah's concepts has a status backed by real evidence, and a spot-check of 20 random tag matches finds at most 2 wrong.

### Phase 5: Feed, diff, demo pair (days 10–12)
- [ ] Implement §6.5 and the diff. Start the daily GitHub star polling **as early as possible**, so live momentum has history by demo day.
- [ ] Review `changes.json` across consecutive snapshots and **choose the demo pair**: two real snapshots where something Aisyah cares about changed. Write down why that pair was chosen.

**Done when:** loading the "before" and then the "after" snapshot in the app visibly changes the bets, the Ghost CV or the Route.

### Phase 6: Operations and documentation (days 12–13)
- [ ] `.github/workflows/pipeline.yml`:
  - daily: `fetch github` + `fetch hn_front`
  - monthly: `fetch hn_hiring` + `fetch arxiv`
  - manual trigger: `fetch dosm`
  - Each run then takes a snapshot and commits it back to the repo.
- [ ] Pipeline section in the README covering sources, licences, coverage notes, the no-LLM statement and how to rebuild.

### Phase 7 (optional): Part 2 matcher (days 13–15)
`match.py`: takes a profile (concept ids with an evidence level, plus task ids) and a snapshot, and returns:
- a personal feed: artifacts that affect the user's tasks (through capability concepts) or boost their skills and Route concepts;
- ladder statuses for the bet-scoring weights in PRD FR-4.2;
- a personal subset of `changes.json` for the Ping.

---

## 9. Risks specific to this plan

| Risk | Mitigation |
|---|---|
| DOSM files lack occupation detail, or the format changes between releases | Phase 0 finds out early. Fallback: hand-enter the top occupations from each release page into a CSV and disclose that in the coverage notes. |
| Look-ahead from GitHub star counts | Backfill counts repo creations only. Star gains come only from the live polling log. The look-ahead test enforces this. |
| Too few aliases, so viral items go untagged | Review the unmatched queue weekly. Once a mapping is approved, alias matching handles it automatically from then on. |
| Rung 2 empty for non-tech concepts | Disclose it. Rung 3 still gives Aisyah real signals. |
| Real data doesn't move between snapshots | Run the backfill early and pick the demo pair from the actual diffs (Phase 5). |
| arXiv rate limit makes the backfill slow | Run it once, commit the raw data, and fetch only new months afterwards. |
