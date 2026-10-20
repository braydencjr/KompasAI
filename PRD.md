# Kompas — Product Requirements Document

> **Working name:** Kompas (placeholder — final name TBD)
> **Event:** SDC XMUM Hackathon — Domain 1: The Aiversecity Future-Ready Workforce
> **Status:** Draft v1.0 · Preliminary round
> **Tagline:** *AI watches the market. You grow.*

---

## 1. Summary

Kompas is an always-on career signal engine for working adults and students. A user uploads a resume (and optionally work samples or a GitHub link). Kompas builds an evidence-based skills profile, shows which parts of their work AI is reaching and which remain human-led, projects their resume into the future under different AI-disruption scenarios, and offers three distinct career "bets" — each with an explainable match score, a clear skills gap, an SDG link, and a learning route built from free or low-cost resources.

Behind the product, an ingestion engine continuously pulls signals from AI research, open-source activity and job-market data, and tracks each skill as it climbs a **Signal Ladder** from research buzz to real Malaysian job demand. This separates hype from real opportunity. When the data moves, Kompas tells the user what changed and re-plans their route.

**One-line pitch:** *Kompas shows you which parts of your work AI is reaching, what your resume looks like in 2028, and three bets you could make — then pings you when the world moves.*

---

## 2. Problem

- AI is changing which jobs exist faster than training programmes and skills frameworks can be updated. In Malaysia, 56% of professionals already use AI tools at work but only 26% have received formal training (Hays Asia Salary Guide 2025, cited in the brief). MOSTI has said more than 600,000 workers will need reskilling within three to five years.
- New AI tools, models and skills emerge every week. **No student or working adult can monitor this firehose and still have time to grow.**
- Most of what they do see is hype. They cannot tell which trends will become real local job demand and which will fade.
- Existing career advice is static: a one-time assessment or a list that is outdated by the time it is published.
- A recommended skill is not necessarily a skill the person will enjoy, and committing months to the wrong path is expensive.

**Core insight:** People do not need more information. They need something that watches the signals for them, filters hype from real demand, and translates it into *their* next step — while leaving the decision with them.

---

## 3. Goals and non-goals

### 3.1 Goals
| # | Goal | Measure |
|---|---|---|
| G1 | A new user gets from resume to ranked future roles and an actionable route in minutes | Median time-to-first-bets < 3 minutes in usability test |
| G2 | Every recommendation is transparent about its source | 100% of skills, roles and resources shown with source + date |
| G3 | Output visibly changes when trend data changes | Snapshot swap re-orders bets/route in live demo |
| G4 | SDG link is meaningful, not decorative | SDG lens changes which bet ranks first for at least one persona |
| G5 | AI never invents jobs, courses or statistics | 0 items shown that are not traceable to a stored source record |
| G6 | Humans stay in charge of career decisions | User can contest any AI judgement; no final decisions made by the system |

### 3.2 Non-goals (out of scope)
- Creating full course content (per brief).
- Payment systems or real recruitment integrations (per brief).
- Making hiring decisions or ranking candidates for employers.
- Using real personal data or real CVs — demo uses synthetic profiles only.
- A hosted coding sandbox. The Taste Test links to real repositories; it does not run code for the user.

---

## 4. Target users

| Persona | Moment of need | Input |
|---|---|---|
| **Working adult at risk** (lead persona) | Hears "AI will take your job", doesn't know what that means for *their* tasks | Resume, optional work samples |
| **Fresh graduate / career switcher** | Deciding where to go next | Resume or transcript, project links |
| **Final-year student** | Choosing electives, final-year project, internship | Resume / syllabus, GitHub |
| **Career centre / HR-L&D (secondary)** | Advising many people at once | Aggregated view (future scope) |

### 4.1 Demo persona (synthetic)
**Aisyah, 27** — accounts executive at a shared-services centre in Kuala Lumpur. Five years' experience in accounts payable, reconciliation and month-end close. Curious about AI, worried about her role, has no time to follow trends.

Additional synthetic personas for testing: a final-year electrical engineering student, a 45-year-old customer-support team lead, a fresh computer science graduate, and a TVET diploma holder in mechatronics.

---

## 5. User journey

The journey has seven named moments. Each maps to one or more of the brief's must-have features.

### 5.1 The Mirror — "Your work, split"
1. User uploads a resume (PDF/DOCX) and optionally a GitHub URL or portfolio file.
2. Kompas extracts experience, job titles, skills and projects, and writes a short candidate summary.
3. Each job title is mapped to a standard occupation; its tasks are pulled from the occupation's task list.
4. Tasks are shown as **cards** in two piles: **AI-exposed** and **Your human edge**. Each card shows the reason and the signal behind it (e.g., "document-extraction models · Emerging · 3 sources · Oct 2026").
5. A headline gives the share of tasks in each pile, labelled as an estimate under the current scenario.
6. **Contest a card:** the user can move a card to the other pile and give a short reason. The profile updates. The override is stored and respected in all later steps.

*Must-haves covered: #1 Skills profile intake. Principle: human-centred.*

### 5.2 The Ghost CV — "Your resume in 2028"
1. Kompas renders the user's own resume, projected forward.
2. Skills with declining signals **fade**. **Blank slots** appear where top matching roles require skills the user lacks and the market is moving towards.
3. A toggle switches between **Moderate** and **Fast** AI-adoption scenarios; the ghost updates live.
4. Every faded line and blank slot links to its Signal Ladder status and evidence.
5. A persistent banner: *"Projections are estimates based on current signals, not predictions."*

*Must-haves covered: #6 Handling uncertainty, #2 trend layer (personalised).*

### 5.3 The Ladder — "Hype or real?"
1. Tapping any skill opens its Signal Ladder view: which rungs it has reached, its velocity, and its status (Watch / Emerging / Act now / Declining).
2. An evidence trail lists the underlying records: papers, repositories, job-posting statistics — each with source name, link and date.
3. A coverage note explains each source's limits (e.g., which job sites a dataset covers).

*Must-haves covered: #2 AI-trend signal layer.*

### 5.4 Three Bets — "Pick your future, not a job list"
1. Kompas presents three role cards:
   - **Safe Bet** — highest match among roles whose key skills hold up under both scenarios.
   - **Rising Bet** — fastest-growing role above a minimum match threshold.
   - **Impact Bet** — best combination of match and alignment with the SDGs the user selected.
2. Each card shows an explainable match score with a breakdown (skills matched, skills missing, weighting) and the role's SDG tags with a one-line rationale.
3. **SDG lens:** user selects the goals they care about; the Impact Bet and full ranking re-order.
4. "See all roles" opens the full ranked list.

*Must-haves covered: #3 Future-role matching, #5 SDG mapping.*

### 5.5 Taste Test — "Try it before you bet on it"
1. For any bet, Kompas offers a short starter task (≈1 hour) drawn from a real, trending open-source repository related to the bet's key skill — e.g., a beginner-labelled issue or the project's own quickstart.
2. After trying it, the user rates it: **Loved it / Meh / Not for me**.
3. The rating adjusts an interest weight for that skill cluster; the bets reshuffle accordingly.

*Extends #3 matching with interest; integrates trending-project data. Good-to-have: learner motivation.*

### 5.6 The Route — "Fill your Ghost CV"
1. User chooses a bet. Kompas generates an ordered learning route that fills the Ghost CV's blank slots.
2. Each step: skill, resource (free / low-cost / HRD Corp-claimable where verified), provider, link, estimated hours, and the ladder evidence for why this step is here.
3. Steps are ordered by prerequisite first, then by ladder priority (Act now before Emerging before Watch).
4. As steps are marked complete, ghost lines turn solid. The route's SDG contribution is summarised.

*Must-haves covered: #4 Personalised reskilling pathway, #5 SDG mapping. Good-to-have: progress tracking.*

### 5.7 The Ping — "The world moved. Here's what changed for you."
1. When a new data snapshot changes a user's statuses, bets or route, Kompas generates a change brief: what moved, why, evidence, and the re-ordered route.
2. In the demo, the presenter switches from the previous snapshot to the current one live.

*Brief's success criterion: output visibly changes when trend data changes. Good-to-have: automatic re-planning.*

---

## 6. Must-have coverage matrix

| Brief must-have | Kompas feature | Section |
|---|---|---|
| 1. Skills profile intake | The Mirror (resume + work samples + contest) | 5.1, 7.1 |
| 2. AI-trend signal layer | Ingestion engine + Signal Ladder | 5.3, 8 |
| 3. Future-role matching | Three Bets + full ranked list | 5.4, 7.4 |
| 4. Personalised reskilling pathway | The Route | 5.6, 7.6 |
| 5. SDG mapping | SDG tags + SDG lens + route SDG summary | 5.4, 5.6, 7.7 |
| 6. Handling uncertainty | Ghost CV scenario toggle + estimate labels | 5.2, 8.6 |

| Good-to-have | Coverage |
|---|---|
| Employer/HR view | Future scope (aggregated view) |
| Automatic re-planning | The Ping |
| Inclusive design | ESCO multilingual labels enable EN/BM/ZH skill names; mobile-first UI |
| Learner motivation | Route progress, Ghost CV filling in |
| Fairness checks | No demographic inputs; counterfactual test (7.9) |
| SDG contribution view | Route SDG summary (person level) |

---

## 7. Functional requirements

### 7.1 Profile intake
- **FR-1.1** Accept PDF and DOCX resumes up to 5 MB.
- **FR-1.2** Accept an optional GitHub profile/repo URL and optional work-sample files (PDF, DOCX, MD).
- **FR-1.3** Extract: job titles, employers (optional), durations, education, listed skills, projects.
- **FR-1.4** Map each extracted skill to a taxonomy skill (ESCO) using dictionary match first, then embedding similarity. Unmatched phrases are kept as free-text and flagged.
- **FR-1.5** Tag each profile skill with evidence level: **Claimed** (resume only) or **Demonstrated** (supported by a work sample or repository).
- **FR-1.6** Generate a ≤ 80-word candidate summary. The summary may only reference items extracted from the user's own files.
- **FR-1.7** Collect no age, gender, ethnicity, nationality or photo. Strip these if present in the upload before processing.
- **FR-1.8** User can edit, add or remove any extracted skill.

### 7.2 Task exposure (The Mirror)
- **FR-2.1** Map each job title to a standard occupation (ESCO or O*NET) with a confidence score; let the user confirm or change the match.
- **FR-2.2** Pull that occupation's task list.
- **FR-2.3** For each task, compute an exposure score from the capabilities it relies on (via the capability bridge, 8.4) and those capabilities' signal strength.
- **FR-2.4** Classify tasks as **AI-exposed** (score ≥ threshold) or **Human edge**; show reason and evidence per card.
- **FR-2.5** Show the share of tasks per pile, labelled with the active scenario and "estimate".
- **FR-2.6** User can contest any card; store the override with the user's reason; overrides take precedence everywhere downstream.

### 7.3 Ghost CV
- **FR-3.1** Render the user's resume skills with visual state: solid (stable/rising), faded (declining), blank slot (in-demand gap).
- **FR-3.2** Blank slots = top-N missing skills from the user's top-matching roles whose status is Emerging or Act now under the active scenario.
- **FR-3.3** Scenario toggle (Moderate / Fast) recomputes states without a page reload.
- **FR-3.4** Each state links to its ladder evidence.

### 7.4 Matching and Three Bets
- **FR-4.1** Role catalogue is limited to roles in stored sources (ESCO occupations, MyCOL list, and roles observed in ingested postings). The LLM may not create roles.
- **FR-4.2** Match score (explainable):
  - For each skill *s* required by role *r*: weight *w(s)* = importance (essential 1.0, optional 0.5) × demand multiplier from ladder status (Act now 1.2, Emerging 1.1, Stable 1.0, Watch 0.9, Declining 0.7).
  - User coverage *c(s)* = 1.0 Demonstrated, 0.7 Claimed, 0 missing.
  - **Match(r) = Σ w(s)·c(s) / Σ w(s)**, shown as a percentage with the per-skill breakdown.
  - Weights are configuration, documented and visible in an "How is this calculated?" panel.
- **FR-4.3** Bet selection:
  - **Safe Bet:** argmax Match(r) where ≥ 70% of the role's essential-skill weight is in skills that are not Declining under either scenario.
  - **Rising Bet:** argmax (role trend velocity × Match(r)) where Match(r) ≥ 40%.
  - **Impact Bet:** argmax (SDG alignment with user-selected goals × Match(r)) where Match(r) ≥ 40%.
  - If one role wins two categories, take the next best for the second.
- **FR-4.4** Interest weight from Taste Test ratings multiplies bet scores (Loved 1.15, Meh 0.9, Not for me 0.6) for the affected skill cluster.
- **FR-4.5** Full ranked list available, sortable by match, trend and SDG alignment.

### 7.5 Taste Test
- **FR-5.1** For each bet's top missing skill, show 1–3 starter tasks from real public repositories surfaced by the ingestion engine (e.g., issues labelled for beginners, or the project's quickstart).
- **FR-5.2** Each task shows repo name, link, last activity date, and estimated effort.
- **FR-5.3** Capture a 3-option rating and optional comment; apply FR-4.4.
- **FR-5.4** Kompas does not host, run or grade code.

### 7.6 The Route
- **FR-6.1** Resource catalogue contains only stored, verified entries: title, provider, URL, cost (free / low-cost / paid), estimated hours, language, HRD Corp-claimable flag (set only when verified), date checked.
- **FR-6.2** Route = ordered steps covering the chosen bet's missing skills; ordering by prerequisite graph, then ladder priority.
- **FR-6.3** Show total estimated time and a suggested weekly pace the user can adjust.
- **FR-6.4** Each step shows why it is there (ladder evidence) and its SDG tags.
- **FR-6.5** Progress tracking: mark steps complete; Ghost CV updates.

### 7.7 SDG mapping
- **FR-7.1** Every role and every skill in the catalogue has ≥ 1 SDG tag with a one-line rationale and a reference (e.g., green-skill classification, sector mapping).
- **FR-7.2** The mapping table is curated, versioned and visible to users ("Why is this linked to SDG 7?").
- **FR-7.3** SDG lens: user selects goals; Impact Bet and rankings recompute.
- **FR-7.4** Route summary shows which SDGs the chosen path contributes to and through which steps.

### 7.8 The Ping (re-planning)
- **FR-8.1** On each new snapshot, diff every active user's skill statuses, bets and route against the previous snapshot.
- **FR-8.2** If anything material changed, generate a change brief: what changed, evidence, new route order.
- **FR-8.3** Demo mode: presenter can switch the active snapshot from a control panel.

### 7.9 Fairness
- **FR-9.1** No demographic attributes are used as inputs to any score.
- **FR-9.2** Counterfactual test in CI: for each synthetic persona, vary name, gender markers and age-implying dates; assert bets and scores are unchanged (tolerance 0).
- **FR-9.3** Publish the test result in the repo README.

### 7.10 AI disclosure and guardrails
- **FR-10.1** Disclose the language model(s) used, in the UI footer and README.
- **FR-10.2** LLM roles are limited to: extraction from user files, skill-phrase extraction from ingested text, and writing explanations of already-computed results.
- **FR-10.3** Any LLM-extracted phrase must appear verbatim in its source text; otherwise it is discarded.
- **FR-10.4** Any LLM-written explanation may only reference entity IDs present in the computed result; a post-check rejects outputs that mention unknown roles, courses or numbers.
- **FR-10.5** Every displayed skill, role, resource and statistic carries a source and date.

---

## 8. Signal ingestion engine

The ingestion engine is the core of Kompas and the focus of the preliminary demo.

### 8.1 Design principles
1. **Provenance on every record** — source, URL, published date, fetched date.
2. **Versioned snapshots** — every run produces a dated snapshot; any two can be diffed or replayed.
3. **Closed world** — skills and roles come only from the taxonomy or verbatim source text.

### 8.2 Source registry

| Rung | Source | Cadence | What we extract | Access notes |
|---|---|---|---|---|
| 1 · Research buzz | arXiv API (AI categories, e.g. cs.CL, cs.LG, cs.CV) | Daily | Capability terms from titles/abstracts | Metadata CC0; ≤ 1 request / 3 s, single connection |
| 1 · Research buzz | Hugging Face Hub (model listings by task tag) | Daily | New-model counts per task/capability | Verify current endpoint and fields |
| 1–2 · Open-source | Trending public repositories (GitHub search by topic, stars, recent activity) | Daily/weekly | Repo topics, languages, beginner-labelled issues (for Taste Test) | Use official API; respect rate limits |
| 2 · Global adoption | Hacker News "Who is hiring?" via public Algolia HN API | Monthly | Skill mentions in job posts | No key needed; tech/US-heavy bias — disclose |
| 3 · Malaysian demand | DOSM Job Market Insights (job vacancies advertised online) | Quarterly | Vacancies by occupation, skills, field of study | Covers four recruitment sites only — disclose. Access via OpenDOSM API if catalogued; else table extraction from quarterly release |
| Anchor | MyCOL 2024/2025 (TalentCorp) | Per edition | Critical occupation list (66 occupations) | Import once per edition |
| Taxonomy | ESCO API (skills, occupations, multilingual labels) | Pinned version | Normalisation backbone | Free, no key; lags new AI skills — handled by candidate queue |
| Tasks | O*NET / ESCO occupation descriptions | Pinned version | Task lists per occupation | Public datasets |

**Not used:** scraping commercial job boards (e.g. JobStreet, LinkedIn) — terms-of-service risk.

### 8.3 Pipeline stages
1. **Fetch** — one connector per source implementing `fetch(since) -> list[RawDocument]`. Raw payloads stored unmodified with a content hash (idempotent re-runs).
2. **Extract** — two passes:
   - *Pass A, dictionary:* match against ESCO labels + team-maintained alias table.
   - *Pass B, LLM:* extract remaining skill/capability phrases; discard any phrase not found verbatim in the source text.
3. **Normalise** — embed unmatched phrases; map to an ESCO skill if cosine similarity ≥ threshold (start 0.80, tune on a labelled sample). Below threshold → **candidate emerging-skill queue**.
4. **Review** — a team member approves or rejects queue items into the alias table. Approved new terms become tracked "emerging skills".
5. **Aggregate** — per skill, source, period: `share = mentions / total documents`.
6. **Score** — compute velocity and ladder status (8.5).
7. **Snapshot** — write a dated snapshot of all statuses with evidence IDs and the source versions used.
8. **Diff & notify** — compare to previous snapshot; trigger The Ping.

### 8.4 Capability bridge
Rung-1 sources describe AI *capabilities* (e.g., document understanding, code generation, speech recognition), not job skills. A curated, versioned table maps:
- capability → affected ESCO skills
- capability → affected occupation tasks

The table is small (target 15–25 capabilities), documented, and cited. The **structure** is curated; the **values** flowing through it are live.

### 8.5 Signal Ladder scoring
For skill *s*, source *r*, period *t*:
- `share(s,r,t) = mentions / total_docs(r,t)`
- `velocity(s,r,t) = (share(t) − mean(share over previous k periods)) / (std + ε)`
- A rung is **active** if velocity ≥ +1.5 **and** mentions ≥ minimum count (start 5 per period).
- **Status:**
  - Active on rung 1 only → **Watch** (speculative)
  - Active on rung 2 → **Emerging**
  - Active on rung 3 → **Act now**
  - velocity ≤ −1.5 on rung 2 or 3 → **Declining**
  - otherwise → **Stable**
- Apply simple smoothing (rolling mean over 2 periods) before scoring to reduce noise.

### 8.6 Scenarios
- **Lead time:** with enough history, measure the typical periods between a skill's rung-1 activation and its rung-3 activation.
- **Moderate scenario:** uses observed lead time and current velocities.
- **Fast scenario:** compresses lead time (default factor 0.5) and amplifies exposure scores (default ×1.3, capped).
- Until enough history exists, scenario parameters are documented defaults and labelled as such.

### 8.7 Scheduling and operations
- GitHub Actions cron: rung-1 daily, HN monthly (after thread posts), DOSM by manual trigger per release.
- Failed fetch → keep last good snapshot active; log and surface "data as of <date>" in UI.
- All snapshots committed or stored with metadata so the demo can run offline.

---

## 9. Data model

```
source(id, name, rung, cadence, url, licence_note, coverage_note)
raw_document(id, source_id, url, published_at, fetched_at, content_hash, text)
skill(id, esco_uri, label_en, label_ms, label_zh, aliases[], is_emerging)
capability(id, name, description)
capability_skill(capability_id, skill_id, rationale, reference)
occupation(id, esco_uri, onet_code, title, mycol_flag)
occupation_task(id, occupation_id, task_text)
task_capability(task_id, capability_id)
skill_mention(id, document_id, skill_id, matched_span, method, confidence)
candidate_skill(id, phrase, first_seen, mention_count, status)  -- review queue
signal(skill_id, source_id, period, mentions, share, velocity)
snapshot(id, created_at, source_versions_json, scenario_params_json)
skill_status(snapshot_id, skill_id, scenario, rung, status, evidence_ids[])
role_skill(occupation_id, skill_id, importance)
sdg_tag(entity_type, entity_id, sdg_number, rationale, reference)
resource(id, title, provider, url, cost_tier, est_hours, language, hrdc_verified, checked_at)
resource_skill(resource_id, skill_id)
repo(id, full_name, url, topics[], last_activity, stars)
starter_task(id, repo_id, title, url, est_minutes, skill_id)

user_profile(id, summary, created_at)               -- synthetic only
profile_skill(profile_id, skill_id, evidence_level, source_file)
task_override(profile_id, task_id, user_pile, reason)
interest_rating(profile_id, skill_cluster, rating)
route(id, profile_id, occupation_id, snapshot_id)
route_step(route_id, order, skill_id, resource_id, est_hours, completed)
```

---

## 10. System architecture

```
[Sources] → Connectors → Raw store → Extract (dict + verified LLM) → Normalise (ESCO + embeddings)
        → Candidate queue (human review) → Aggregate → Ladder scoring → Snapshot → Diff/Ping
                                                                         │
[User files] → Profile extractor → Skill mapping → Task exposure ──────────┤
                                                                         ▼
                                              Matching / Bets / Ghost CV / Route API
                                                                         │
                                                                    Web frontend
```

### 10.1 Proposed stack
| Layer | Choice | Reason |
|---|---|---|
| Ingestion & scoring | Python | Data tooling, NLP libraries |
| Storage | DuckDB or SQLite (single file) | Simple, portable, demo can run offline |
| Embeddings | sentence-transformers (open model) | Free, runs locally or on Runpod |
| LLM | **TBD — must be disclosed** | Extraction + explanations only |
| API | FastAPI | Lightweight, typed |
| Frontend | React / Next.js, mobile-first | Card-based UI, scenario toggles |
| Scheduling | GitHub Actions cron | Free, visible in repo |
| Hosting | Replit (app) / Runpod (model inference) | Event sponsors |

---

## 11. Non-functional requirements
- **NFR-1 Performance:** resume upload to The Mirror in ≤ 20 s; scenario toggle ≤ 1 s.
- **NFR-2 Transparency:** source + date on every displayed fact; "How is this calculated?" on every score.
- **NFR-3 Privacy:** synthetic data only in demo; uploaded files deleted after processing in demo mode; no demographic fields stored.
- **NFR-4 Accessibility & inclusion:** mobile-first; low-bandwidth mode (no heavy charts by default); skill labels in EN with BM/ZH from ESCO where available.
- **NFR-5 Reliability:** UI always shows the active snapshot date; failed ingestion never blanks the product.
- **NFR-6 Reproducibility:** any snapshot can be re-scored from stored raw documents.

---

## 12. Preliminary round scope

### 12.1 Build live (demo)
1. Upload synthetic resume → **The Mirror** (task split, contest a card).
2. **Ghost CV** with Moderate/Fast toggle.
3. **Three Bets** with explainable match scores.
4. **The Ping**: switch snapshot → bets and Ghost CV change.

Backed by a working ingestion pipeline on at least 2–3 sources (arXiv + HN + one Malaysian source or MyCOL), with the Signal Ladder evidence view.

### 12.2 In proposal with mockups
Taste Test, The Route, SDG lens, HR/career-centre aggregate view.

### 12.3 Demo script (≈3 minutes)
1. *(20 s)* Problem: "Trends move daily; Aisyah can't track them."
2. *(40 s)* Upload Aisyah's resume → The Mirror. Contest one card.
3. *(40 s)* Ghost CV. Toggle Moderate → Fast. Tap a blank slot → Ladder evidence with dates.
4. *(40 s)* Three Bets. Open the match breakdown. Switch SDG lens → Impact Bet changes.
5. *(30 s)* The Ping: switch to the new data snapshot → bets and ghost update, change brief appears.
6. *(10 s)* "AI watches the market. You grow."

---

## 13. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Malaysian demand data not available via API | Rung 3 harder to automate | Quarterly table extraction as dated import; MyCOL as anchor |
| Source format changes / outages | Demo breaks | Cached snapshots; offline demo mode |
| Source bias (HN US-tech heavy; DOSM covers 4 sites) | Misleading trends | Coverage notes in UI; only rung 3 can trigger "Act now" |
| Taxonomy lags new AI skills | Emerging skills missed | Candidate queue + human review |
| LLM invents roles, courses, statistics | Rule violation, trust loss | Closed catalogue; verbatim span check; post-check on explanations |
| Small counts look like trends | False signals | Minimum count, smoothing, z-score threshold |
| Task-exposure estimate over-trusted | Anxiety, poor decisions | Estimate labels, two scenarios, contestable cards |
| Scope creep (Playground → sandbox) | Missed deadline | Taste Test = links + rating only |
| Match quality poor | Weak recommendations | Explainable weights; tune on synthetic personas; user can edit profile |

**Hardest risk to name to judges:** reliable, updatable Malaysian demand data and preventing AI from inventing jobs or courses. Both have the mitigations above.

---

## 14. Success metrics

### Preliminary (judging)
- All six must-haves explained in proposal; four journey moments demoed live.
- Snapshot swap visibly changes output.
- Every on-screen fact traceable to a source and date.

### Product (post-hackathon)
- Time from upload to first bets < 3 minutes.
- ≥ 70% of test users say they understand *why* each bet was suggested.
- ≥ 50% of test users change their initial choice after the Taste Test or SDG lens (evidence the features influence decisions).
- Counterfactual fairness test: 0 score changes.

---

## 15. Milestones
*(Dates to be filled once the submission deadline is confirmed.)*

| Phase | Deliverable |
|---|---|
| M1 | ESCO skills loaded; alias table; capability bridge (15–25 capabilities) |
| M2 | arXiv + Hugging Face + HN connectors; raw store |
| M3 | Extraction (dictionary + verified LLM); normalisation; candidate queue |
| M4 | Aggregation, Signal Ladder scoring, snapshots, diff |
| M5 | Malaysian demand import (DOSM / MyCOL) |
| M6 | Profile extraction, task exposure, matching, Three Bets |
| M7 | Frontend: Mirror, Ghost CV, Bets, Ping; demo mode |
| M8 | Synthetic personas, fairness test, README, proposal, rehearsal |

---

## 16. Open questions (team input needed)
1. **Final product name** — Kompas, Haluan, SignalPath, Arah, or other.
2. **Lead persona for the pitch** — working adult (Aisyah) or final-year student.
3. **LLM choice and hosting** — which model, where it runs (must be disclosed).
4. **DOSM data access** — confirm whether Job Market Insights skills tables are in the OpenDOSM catalogue.
5. **Capability bridge contents** — which 15–25 AI capabilities to track.
6. **Team size, roles and submission deadline** — to fix milestone dates and confirm demo scope.
7. **Submission format and length limits** — to size the proposal.

---

## 17. References
- Domain brief: *The Aiversecity Future-Ready Workforce Domain — Problem Statement & Marking Rubric* (SDC XMUM Hackathon).
- arXiv API Terms of Use — https://info.arxiv.org/help/api/tou.html
- ESCO Web Service API — https://esco.ec.europa.eu/en/use-esco/use-esco-services-api/esco-web-service-api
- OpenDOSM API — https://developer.data.gov.my/static-api/opendosm
- DOSM Job Vacancies Advertised Online — https://www.dosm.gov.my/portal-main/release-content/job-vacancies-landscape-in-malaysia-first-quarter-of-2022
- Hacker News Search API (Algolia) — https://hn.algolia.com/api
- MyMahir Malaysia Critical Occupations List (MyCOL) 2024/2025 — TalentCorp
- UN Sustainable Development Goals — https://sdgs.un.org/goals
