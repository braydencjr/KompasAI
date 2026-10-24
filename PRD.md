# Kompas — Product Requirements Document

> **Working name:** Kompas (final name TBD — shortlist: KompasKerja, KompasAI)
> **Event:** SDC XMUM Hackathon — Domain 1: The Aiversecity Future-Ready Workforce
> **Status:** Draft v1.2 · Preliminary round
> **Tagline:** *AI watches the market. You grow.*

### Changes in v1.2 (backend data pipeline)
1. **Data anchors the answer; the LLM fills the gaps.** The data pipeline is still the source of truth. Where it has nothing to say (a skill no source mentions, a job outside the official lists), the LLM now gives a judgement instead of the app showing "No data yet". Each such judgement is based on related records we hold, can only point to records we actually fetched, and is cached so it is made once.
2. **CV reading is one simple step.** One LLM call reads the CV and returns skills already grouped into categories (each skill with a quote from the CV). The extra "merge categories" step and the long list of tracked skills in the prompt are gone, which makes it faster.
3. **Any skill can be tracked, not only our list.** Skills outside our dictionary are matched to the ESCO skills list on demand and measured in the same stored records, so they get a status too.
4. **Official AI-exposure scores added.** The ILO's published task-level scores are now the base for The Mirror. Jobs the ILO does not list get LLM-estimated task scores anchored on the most similar official ones.
5. **Role requirements come from real Malaysian job ads** (where enough are found), not only from our hand-made list.
6. **Skills are matched by meaning** as well as by name when scoring how well you fit a role.
7. **Reasons shown for each suggested job are written by the LLM from the evidence and then checked.** A reason that cites anything outside its evidence falls back to a fixed template.
8. **Speed rules:** the LLM calls that only choose or sort run without extended thinking, results are cached, and the browser waits up to 2 minutes for the CV steps.

### Changes in v1.1
1. **Demo scope fixed:** SDG lens and a static Route view are now built live (previously contradicted the demo script).
2. **Persona–data fit fixed:** added non-tech demand sources and finance/operations capabilities so the lead persona (an accounts executive) gets real rising-role signals, not only software-engineering ones.
3. **Malaysian demand redesigned:** demand is measured at *occupation* level from official sources, then translated into skills through ESCO's occupation-to-skill links (with a MASCO → ISCO → ESCO code translation step).
4. **History backfill added:** connectors fetch 6–12 months of past data once, so trend scores have a baseline and the demo uses real past snapshots.
5. **No LLM in bulk ingestion for the prelim:** ingestion uses dictionary + alias + meaning-based matching only. The LLM is limited to resume extraction and explanations.
6. **Plain-language glossary** added (Appendix A) for team members and for writing the judges' proposal.

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
| G4 | SDG link is meaningful, not decorative | SDG lens changes which bet ranks first for the lead persona, live |
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

**Why a non-tech lead persona:** it targets the brief's core concern (hundreds of thousands of Malaysian workers needing reskilling) and avoids the common "CS student looking for a tech job" pitch. It also forces the data design to work beyond software roles (see 8.2).

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
1. Tapping any skill opens its Signal Ladder view: which rungs it has reached, how fast it is moving, and its status (Watch / Emerging / Act now / Declining).
2. An evidence trail lists the underlying records: papers, repositories, job-demand statistics — each with source name, link and date.
3. A coverage note explains each source's limits (e.g., which job sites a dataset covers, or that a source is tech-heavy).

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
2. In the demo, the presenter switches from a real earlier snapshot (built by the history backfill, 8.3) to the current one, live.

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
| 6. Handling uncertainty | Ghost CV scenario toggle + estimate labels | 5.2, 8.7 |

| Good-to-have | Coverage |
|---|---|
| Employer/HR view | Future scope (aggregated view) — mockup in prelim |
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
- **FR-1.3** Extract with one LLM call: the CV's skills grouped into broad categories (the model decides the categories, 2 to 4 words each), job titles, employers, durations and a short summary. Output must be structured and every extracted item must carry a quote that appears in the uploaded text.
- **FR-1.4** Map each extracted skill to a taxonomy skill. Skills in our dictionary are matched by name and alias. Any other skill is looked up in the ESCO skills list; the LLM may pick only from what ESCO returns, or say none. A matched ESCO skill becomes a skill we can track from then on. Unmatched phrases are kept as free text and flagged.
- **FR-1.5** Tag each profile skill with evidence level: **Claimed** (resume only) or **Demonstrated** (supported by a work sample or repository).
- **FR-1.6** Generate a ≤ 80-word candidate summary. The summary may only reference items extracted from the user's own files.
- **FR-1.7** Collect no age, gender, ethnicity, nationality or photo. Strip these if present in the upload before processing.
- **FR-1.8** User can edit, add or remove any extracted skill.

### 7.2 Task exposure (The Mirror)
- **FR-2.1** Map each job title to a standard occupation (ESCO or O*NET) with a confidence score; let the user confirm or change the match.
- **FR-2.2** Pull that occupation's task list, with the ILO's published AI-exposure score for each task. For a job the ILO does not list, the LLM writes the job's main tasks and scores each against the most similar published tasks, citing them. A score outside the range of the tasks it cites is dropped. The result is stored and marked as an estimate, so each job is estimated once.
- **FR-2.3** For each task, compute an exposure score from the capabilities it relies on (via the capability bridge, 8.5) and those capabilities' signal strength.
- **FR-2.4** Classify tasks as **AI-exposed** (score ≥ threshold) or **Human edge**; show reason and evidence per card.
- **FR-2.5** Show the share of tasks per pile, labelled with the active scenario and "estimate".
- **FR-2.6** User can contest any card; store the override with the user's reason; overrides take precedence everywhere downstream.

### 7.3 Ghost CV
- **FR-3.1** Render the user's resume skills with visual state: solid (stable/rising), faded (declining), blank slot (in-demand gap).
- **FR-3.2** Blank slots = top-N missing skills from the user's top-matching roles whose status is Emerging or Act now under the active scenario.
- **FR-3.3** Scenario toggle (Moderate / Fast) recomputes states without a page reload.
- **FR-3.4** Each state links to its ladder evidence.
- **FR-3.5** A skill with no measured evidence and no linked AI capability is not left as "stays the same" by default. The LLM judges its 2028 direction (worth more, AI takes over, fading, or holds) with a one-line reason, shown on hover. Measured and curated results always take priority. The judgement is cached.

### 7.4 Matching and Three Bets
- **FR-4.1** Role catalogue is limited to roles in stored sources (ESCO occupations, MyCOL list, and occupations present in ingested demand data). The LLM may not create roles. A role's required skills come from its live Malaysian job ads when at least 5 are found (a skill asked for by at least half of the ads is essential, by at least a fifth optional); otherwise from the hand-made list.
- **FR-4.2** Match score (explainable):
  - For each skill *s* required by role *r*: weight *w(s)* = importance (essential 1.0, optional 0.5) × demand multiplier from ladder status (Act now 1.2, Emerging 1.1, Stable 1.0, Watch 0.9, Declining 0.7).
  - User coverage *c(s)* = 1.0 Demonstrated, 0.7 Claimed, 0 missing. A missing skill still earns partial credit when you have a skill that means almost the same (for example "Recruit personnel" for "Hire staff"). Similarity is judged by comparing stored meaning-vectors of the skill names; credit starts at 50% for a close match and reaches 100% for a near-identical one. Unrelated skills get nothing.
  - **Match(r) = Σ w(s)·c(s) / Σ w(s)**, shown as a percentage with the per-skill breakdown.
  - Weights are configuration, documented and visible in a "How is this calculated?" panel.
- **FR-4.3** Bet selection:
  - **Safe Bet:** highest Match(r) where ≥ 70% of the role's essential-skill weight is in skills that are not Declining under either scenario.
  - **Rising Bet:** highest (role demand trend × Match(r)) where Match(r) ≥ 40%.
  - **Impact Bet:** highest (SDG alignment with user-selected goals × Match(r)) where Match(r) ≥ 40%.
  - If one role wins two categories, take the next best for the second.
- **FR-4.4** Interest weight from Taste Test ratings multiplies bet scores (Loved 1.15, Meh 0.9, Not for me 0.6) for the affected skill cluster.
- **FR-4.5** Full ranked list available, sortable by match, trend and SDG alignment.

### 7.5 Taste Test
- **FR-5.1** For each bet's top missing skill, show 1–3 starter tasks from real public repositories surfaced by the ingestion engine (e.g., issues labelled for beginners, or the project's quickstart).
- **FR-5.2** Each task shows repo name, link, last activity date, and estimated effort.
- **FR-5.3** Capture a 3-option rating and optional comment; apply FR-4.4.
- **FR-5.4** Kompas does not host, run or grade code.
- **FR-5.5** For non-technical skills (e.g., ESG reporting), starter tasks may come from curated public exercises or datasets instead of code repositories; each must still cite a real source.

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
- **Note:** the lens itself is simple to build; the effort is in curating the mapping table with rationales. Budget time for the table, prioritising roles and skills reachable from the demo personas.

### 7.8 The Ping (re-planning)
- **FR-8.1** On each new snapshot, compare every active user's skill statuses, bets and route against the previous snapshot.
- **FR-8.2** If anything material changed, generate a change brief: what changed, evidence, new route order.
- **FR-8.3** Demo mode: presenter can switch the active snapshot from a control panel.

### 7.9 Fairness
- **FR-9.1** No demographic attributes are used as inputs to any score.
- **FR-9.2** Counterfactual test in CI: for each synthetic persona, vary name, gender markers and age-implying dates; assert bets and scores are unchanged (tolerance 0).
- **FR-9.3** Publish the test result in the repo README.

### 7.10 AI disclosure and guardrails
- **FR-10.1** Disclose the language model(s) used, in the UI footer and README.
- **FR-10.2** LLM use is limited to: (a) extraction from the user's own uploaded files, (b) writing plain-language explanations of already-computed results, and (c) filling gaps where our data is silent (estimating a job's task exposure, a skill's trend, or which related records bear on a skill). Gap-filling is always based on stored records, never replaces measured data, and its output is cached. **The LLM is not used in bulk ingestion in the preliminary build** (see 8.4).
- **FR-10.3** Any LLM-extracted item must appear in its source text; otherwise it is discarded.
- **FR-10.4** Any LLM-written explanation may only reference entity IDs present in the computed result; a post-check rejects outputs that mention unknown roles, courses or numbers. For job reasons, every sentence must cite its evidence, and a reason that fails the check keeps its fixed template.
- **FR-10.5** Every displayed skill, role, resource and statistic carries a source and date.

---

## 8. Signal ingestion engine

The ingestion engine is the core of Kompas and the focus of the preliminary demo.

### 8.1 Design principles
1. **Provenance on every record** — source, URL, published date, fetched date.
2. **Versioned snapshots** — every run produces a dated snapshot; any two can be compared or replayed.
3. **Data first, LLM for gaps** — skills and roles come from the taxonomy or matched source text, and measured results are never overwritten. Where the data has nothing, the LLM may give a judgement that can cite only records we hold (see 8.9).
4. **History first** — every connector supports fetching past periods, so trends are measured against a real baseline from day one.

### 8.2 Source registry

The ladder has three rungs. Each rung must include at least one source that covers **non-tech** roles, so personas like Aisyah get real signals.

| Rung | Source | Level | Cadence | Covers non-tech? | Access notes |
|---|---|---|---|---|---|
| 1 · Research buzz | arXiv API (AI categories, e.g. cs.CL, cs.LG, cs.CV) | Capability | Daily | Yes, via capability bridge (e.g. document understanding affects finance tasks) | Metadata CC0; ≤ 1 request / 3 s, single connection; supports date-range queries |
| 1 · Research buzz | Hugging Face Hub (new models by task tag) | Capability | Daily | Yes, via capability bridge | Verify current endpoint and fields |
| 1–2 · Open source | Trending public repositories (official GitHub API, by topic/activity) | Skill | Weekly | Partly (finance/ESG/data topics exist) | Also feeds Taste Test |
| 2 · Global adoption (tech) | Hacker News "Who is hiring?" via public Algolia HN API | Skill | Monthly | **No — tech-heavy** | Disclose bias; used only for tech skills |
| 2 · Regional adoption (all occupations) | Singapore MOM job vacancy rate by occupation (data.gov.sg) | Occupation | Quarterly | **Yes** | Open Data Licence; API access; long history available |
| 3 · Malaysian demand | DOSM job-vacancy releases (Job Market Insights; vacancies by occupation) | Occupation | Quarterly | **Yes** | Use whatever machine-readable form exists; else a once-per-release table import. Covers four recruitment sites only — disclose |
| 3 · Malaysian demand | MyCOL 2024/2025 (TalentCorp critical occupations) | Occupation | Per edition | **Yes** | Import once per edition; anchors role catalogue |
| Tasks · AI exposure | ILO generative-AI exposure index (task-level scores for every ISCO-08 job; CC BY 4.0) | Occupation task | Pinned version | Yes | Downloaded once into the database; MASCO follows ISCO-08 so scores apply to Malaysian jobs |
| Role skills | Live Malaysian job ads (Google for Jobs via JSearch) | Occupation | Refreshed weekly per role | Yes | Used only to list the skills a role asks for, never to trend skills; cached |
| Taxonomy | ESCO API (skills, occupations, occupation→skill links, multilingual labels) | — | Pinned version | — | Free, no key; lags new AI skills |
| Tasks | O*NET / ESCO occupation descriptions | — | Pinned version | — | Public datasets |

**Rules on sources:**
- **Updatable sources only for trends.** A one-off downloaded dataset (e.g., a public job-postings dataset from a data-sharing site) may be used **only as historical background**, never as the sole source for a rung — the brief says hard-coded lists alone do not count.
- **No scraping of commercial job boards** (e.g., JobStreet, LinkedIn) — terms-of-service risk.
- **Verify before building:** the exact machine-readable availability of DOSM vacancy data and the Singapore occupation code crosswalk must be confirmed in M1.

### 8.3 History backfill
- On first setup, a one-time **backfill script** fetches the past **6–12 months** from each source that supports it:
  - arXiv: date-range queries by month.
  - Hacker News: the past 6–12 monthly "Who is hiring?" threads.
  - data.gov.sg / DOSM / MyCOL: all past quarterly releases or editions available.
- The backfill produces one snapshot per historical period. This gives:
  - enough periods to compute trend scores (8.6);
  - **real** earlier snapshots for The Ping demo, instead of staged data.
- After backfill, connectors run incrementally on their normal cadence.

### 8.4 Pipeline stages (preliminary build)
1. **Fetch** — one connector per source implementing `fetch(since, until) -> list[RawDocument]`. Raw payloads stored unmodified with a content hash (re-runs are safe).
2. **Match (no LLM)** — three steps, in order:
   - **Dictionary match** against ESCO skill labels.
   - **Alias match** against a team-maintained alias table (e.g., "Power BI" → data visualisation; "ERP automation" → ESCO equivalent).
   - **Meaning-based match** (embeddings) for remaining phrases, accepted only above a similarity threshold (start 0.80). Spot-check a sample of matches each run, because meaning-based matching can mis-match (e.g. "prompt engineering" landing on a theatre skill).
3. **Candidate queue** — phrases that match nothing are stored as candidate emerging skills. For the prelim, this queue is **seeded with a small set of real examples** and the team approves entries into the alias table; this is stated openly in the pitch.
4. **Occupation → skill translation (rungs 2–3, occupation-level sources)**:
   - Translate source occupation codes to ESCO occupations: **MASCO (Malaysia) → ISCO-08 → ESCO**; Singapore occupation codes → ISCO-08 → ESCO. (MASCO is based on the international ISCO standard; ESCO occupations link to ISCO codes.)
   - Distribute each occupation's demand signal to its skills using ESCO's occupation-to-skill links (essential skills weight 1.0, optional 0.5).
   - A skill's rung-3 demand = weighted sum across all occupations that require it.
5. **Aggregate** — per skill, source, period: `share = mentions / total documents` for text sources; normalised demand index for occupation-level sources.
6. **Score** — compute trend and ladder status (8.6).
7. **Snapshot** — write a dated snapshot of all statuses with evidence IDs and the source versions used.
8. **Compare & notify** — compare to previous snapshot; trigger The Ping.

**Post-prelim (final round) option:** add an LLM pass to propose new skill phrases from unmatched text into the candidate queue, keeping the verbatim check and human approval.

### 8.5 Capability bridge
Rung-1 sources describe AI *capabilities*, not job skills. A curated, versioned table maps:
- capability → affected ESCO skills
- capability → affected occupation tasks

Target 15–25 capabilities, **explicitly including business and finance-relevant ones**, for example:
- Document understanding and extraction (invoices, receipts, forms)
- Automated reconciliation and anomaly detection
- Forecasting from tabular data
- Conversational assistants for customer support
- Report and summary generation
- Code generation (for tech personas)

And the rising human-plus-AI skills they create demand for, mapped to ESCO where possible, e.g. financial data analytics, ERP/process automation oversight, ESG and sustainability reporting, AI audit and compliance, data quality management.

The **structure** of the bridge is curated and documented; the **values** flowing through it are live.

### 8.6 Signal Ladder scoring
For skill *s*, source *r*, period *t*:
- **Trend score** = how unusual this period is compared with the recent past:
  `trend(s,r,t) = (value(t) − mean(previous k periods)) / (std + ε)` with k = 4–12 periods from the backfill.
  - If fewer than 4 periods exist for a source, use simple growth vs the previous period and mark the status **low confidence**.
- Apply a 2-period rolling average before scoring to reduce noise.
- A rung is **active** if trend ≥ +1.5 **and** the skill clears a minimum volume (start: 5 mentions per period for text sources; a minimum demand share for occupation sources).
- **Status:**
  - Active on rung 1 only → **Watch** (speculative)
  - Active on rung 2 → **Emerging**
  - Active on rung 3 → **Act now**
  - trend ≤ −1.5 on rung 2 or 3 → **Declining**
  - otherwise → **Stable**
- Only rung 3 (Malaysian demand) can produce **Act now**.

### 8.7 Scenarios
- **Lead time:** using the backfill history, measure the typical number of periods between a skill's rung-1 activation and its rung-3 activation.
- **Moderate scenario:** observed lead time and current trend scores.
- **Fast scenario:** compresses lead time (default factor 0.5) and amplifies task exposure scores (default ×1.3, capped at 1.0).
- Where history is too short to measure lead time, scenario parameters are documented defaults, labelled as such in the UI.

### 8.8 Scheduling and operations
- GitHub Actions scheduled jobs: rung-1 daily, open-source weekly, Hacker News monthly, quarterly sources by manual trigger per release.
- Failed fetch → keep last good snapshot active; log and show "data as of <date>" in the UI.
- All snapshots stored with metadata so the demo can run offline.

### 8.9 Reference data and LLM-filled gaps
The stored records stay the evidence. Around them, the backend does these things on request, and stores the result so each is done once:

1. **Skills outside our list.** A skill from a CV or a job ad is matched to ESCO, then counted in the same stored Hacker News and hiring-post records using the same scoring rules as tracked skills. It gets a "talked about" and a "hired abroad" signal. There is no per-skill Malaysian signal, because DOSM publishes by occupation, not by skill.
2. **Silence is not "no demand".** If a skill has no signal on a rung, the LLM is shown related records (found by looser matching on the words in its name) and picks only the ones that really bear on the skill, such as the same tool or field. It then estimates the movement on the missing rungs. Only the records it was shown can be cited, and a record that merely mentions a word in passing does not count. Measured rungs and evidence are never changed.
3. **2028 direction for unmeasured skills** — see FR-3.5.
4. **Job exposure for jobs the ILO does not list** — see FR-2.2.
5. **Meaning-based skill matching** — see FR-4.2. Each skill name is turned into a stored meaning-vector once. Matching uses a strict cutoff because short names can look falsely alike (for example "English" and "Excel"), so some true matches are missed rather than risk false ones.
6. **Job reasons.** The LLM rewrites each reason (fit, demand, trend, AI) from an evidence pack and a checker rejects any that go beyond it.

**Speed.** One CV upload makes a handful of LLM calls in order: read the CV, match other skills to ESCO, (if needed) estimate the current job's tasks, fill signal gaps, write reasons. Calls that only choose or sort run with extended thinking off, and every result above is cached, so a repeat of the same CV is much faster.

**Known limits.**
- Role suggestions depend on roles that have a skill list. Only a small set (mostly finance and tech, plus roles whose job ads have been fetched) does today, so a profile from retail or customer service sees low match scores. Generating skill lists for more roles is planned, not built.
- Gap-filling judgements are the model's opinion anchored on our records, not measurements. They are not labelled differently in the UI at present.

---

## 9. Data model

```
source(id, name, rung, level, cadence, url, licence_note, coverage_note)
raw_document(id, source_id, url, published_at, fetched_at, content_hash, text)
skill(id, esco_uri, label_en, label_ms, label_zh, aliases[], is_emerging)
capability(id, name, description)
capability_skill(capability_id, skill_id, rationale, reference)
occupation(id, esco_uri, isco_code, onet_code, title, mycol_flag)
occupation_code_map(source_system, source_code, isco_code, esco_uri)   -- MASCO/SSOC → ISCO → ESCO
occupation_task(id, occupation_id, task_text)
task_capability(task_id, capability_id)
occupation_demand(occupation_id, source_id, period, value, normalised_index)
skill_mention(id, document_id, skill_id, matched_span, method, confidence)  -- method: dictionary | alias | embedding
candidate_skill(id, phrase, first_seen, mention_count, status)             -- review queue
signal(skill_id, source_id, period, value, trend, low_confidence)
snapshot(id, period, created_at, source_versions_json, scenario_params_json)
skill_status(snapshot_id, skill_id, scenario, rung, status, evidence_ids[])
role_skill(occupation_id, skill_id, importance)
ilo_task(isco, task_no, occupation, task, score, band, origin, basis)       -- ILO scores; origin ilo | llm (estimated, with the tasks it cites)
open_skill(id, label, esco_uri, names[])                                    -- ESCO skills found in CVs and ads
open_status(snapshot_id, concept_id, status, projected, rungs, evidence)    -- their measured status per snapshot
skill_embedding(skill_id, model, vector)                                    -- meaning-vector of a skill name
narration(key, payload, created_at)                                         -- cached LLM outputs (reasons, estimates, trends)
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
[Sources] → Connectors (+ one-time history backfill) → Raw store
        → Match: dictionary → alias → embedding (no LLM) → Candidate queue (human review)
        → Occupation→skill translation (MASCO/SSOC → ISCO → ESCO)
        → Aggregate → Ladder scoring → Snapshot → Compare / Ping
                                                     │
[User files] → LLM extraction (verified) → Skill mapping → Task exposure ─┤
                                                     ▼
                         Matching / Bets / Ghost CV / Route / SDG lens API
                                                     │
                                               Web frontend
```

### 10.1 Proposed stack
| Layer | Choice | Reason |
|---|---|---|
| Ingestion & scoring | Python | Data tooling, NLP libraries |
| Storage | DuckDB or SQLite (single file) | Simple, portable, demo can run offline |
| Embeddings | sentence-transformers (open model) | Free, runs locally or on Runpod |
| LLM | **TBD — must be disclosed.** Choose a current, fast, instruction-following model; open-weights hosted on Runpod (event sponsor) is a good option | Resume extraction + explanations only |
| API | FastAPI | Lightweight, typed |
| Frontend | React / Next.js, mobile-first | Card-based UI, scenario and SDG toggles |
| Scheduling | GitHub Actions | Free, visible in repo |
| Hosting | Replit (app) / Runpod (model inference) | Event sponsors |

---

## 11. Non-functional requirements
- **NFR-1 Performance:** resume upload to The Mirror in ≤ 20 s for a cached or small CV (a first-time large CV can take about half a minute, as it makes several LLM calls); scenario and SDG toggles ≤ 1 s.
- **NFR-2 Transparency:** source + date on every displayed fact; "How is this calculated?" on every score.
- **NFR-3 Privacy:** synthetic data only in demo; uploaded files deleted after processing in demo mode; no demographic fields stored.
- **NFR-4 Accessibility & inclusion:** mobile-first; low-bandwidth mode (no heavy charts by default); skill labels in EN with BM/ZH from ESCO where available.
- **NFR-5 Reliability:** UI always shows the active snapshot date; failed ingestion never blanks the product.
- **NFR-6 Reproducibility:** any snapshot can be re-scored from stored raw documents.
- **NFR-7 Cost:** bulk ingestion runs without paid API calls (no LLM in ingestion for the prelim). Per-user LLM and embedding calls are cached so repeats cost nothing.

---

## 12. Preliminary round scope

### 12.1 Build live (demo)
1. Upload synthetic resume → **The Mirror** (task split, contest a card).
2. **Ghost CV** with Moderate/Fast toggle.
3. **Three Bets** with explainable match scores.
4. **SDG lens** — interactive; switching goals changes the Impact Bet.
5. **The Route** — rendered as a clean, static step list when a bet is selected (ordering and resources real; progress tracking not required).
6. **The Ping** — switch from a real earlier snapshot (from backfill) to the current one → bets, Ghost CV and route change.

Backed by a working ingestion pipeline with history backfill on at least: arXiv (rung 1), one all-occupations source (rung 2 or 3: Singapore MOM or DOSM), and MyCOL, plus Hacker News for tech skills. Signal Ladder evidence view live.

### 12.2 In proposal with mockups
Taste Test, HR/career-centre aggregate view, progress tracking on the Route.

### 12.3 Demo script (≈3 minutes)
1. *(20 s)* Problem: "Trends move daily; Aisyah can't track them."
2. *(40 s)* Upload Aisyah's resume → The Mirror. Contest one card.
3. *(35 s)* Ghost CV. Toggle Moderate → Fast. Tap a blank slot → Ladder evidence with dates.
4. *(40 s)* Three Bets. Open the match breakdown. Switch the SDG lens → Impact Bet changes. Select a bet → Route appears.
5. *(30 s)* The Ping: switch to the newer snapshot → bets, ghost and route update; change brief appears.
6. *(15 s)* "AI watches the market. You grow."

---

## 13. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Tech-heavy sources give non-tech personas no rising roles | Lead-persona demo fails | All-occupation sources on rungs 2–3; finance/operations capabilities in bridge (8.2, 8.5) |
| Malaysian vacancy data not machine-readable at skill level | Rung 3 harder to automate | Measure demand at occupation level; translate to skills via ESCO links; once-per-release table import as fallback |
| Occupation code translation (MASCO/SSOC → ISCO → ESCO) incomplete | Some demand lost | Verify crosswalks in M1; manual mapping for demo-relevant occupations; log unmapped codes |
| Not enough history for trend scores | Statuses meaningless | One-time backfill of 6–12 months; low-confidence flag if < 4 periods |
| Source format changes / outages | Demo breaks | Cached snapshots; offline demo mode |
| Source bias (HN tech-heavy; DOSM covers 4 sites) | Misleading trends | Coverage notes in UI; only rung 3 can trigger "Act now" |
| Taxonomy lags new AI skills | Emerging skills missed | Alias table + candidate queue with human review |
| Embedding mis-matches | Wrong skills counted | Similarity threshold; spot-check samples each run |
| LLM invents roles, courses, statistics | Rule violation, trust loss | Closed catalogue; verbatim check; post-check on explanations; no LLM in ingestion |
| SDG mapping takes longer than expected | Lens feels thin | Prioritise roles/skills reachable from demo personas |
| Task-exposure estimate over-trusted | Anxiety, poor decisions | Estimate labels, two scenarios, contestable cards |
| Scope creep (Taste Test → sandbox) | Missed deadline | Taste Test = links + rating only; mockup in prelim |

**Hardest risks to name to judges:** (1) reliable, updatable Malaysian demand data, and (2) preventing AI from inventing jobs or courses. Both have the mitigations above.

---

## 14. Success metrics

### Preliminary (judging)
- All six must-haves explained in proposal; six journey moments demoed live (12.1).
- Snapshot swap (real historical data) visibly changes output.
- SDG lens changes the Impact Bet live.
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
| M1 | **Verify data access** (DOSM machine-readable formats, Singapore occupation data, code crosswalks); load ESCO; alias table; capability bridge incl. finance/operations |
| M2 | Connectors for arXiv, HN, one all-occupation source, MyCOL; **history backfill script** |
| M3 | Matching (dictionary → alias → embedding); seeded candidate queue; occupation → skill translation |
| M4 | Aggregation, trend scoring, Signal Ladder, historical snapshots, snapshot comparison |
| M5 | Profile extraction (LLM, verified), task exposure, matching, Three Bets |
| M6 | SDG mapping table (demo-relevant roles/skills first); SDG lens; static Route |
| M7 | Frontend: Mirror, Ghost CV, Bets, SDG lens, Route, Ping; demo mode |
| M8 | Synthetic personas, fairness test, README, proposal, rehearsal |

---

## 16. Open questions (team input needed)
1. **Final product name** — shortlist: KompasKerja (clearest, local), KompasAI (tech feel without narrowing audience).
2. **LLM choice and hosting** — pick a current model (check what is available now); must be disclosed.
3. **Data access checks (M1):**
   - Is DOSM vacancy-by-occupation data available in CSV/Excel or via the OpenDOSM catalogue?
   - Can Singapore occupation codes and MASCO codes be reliably translated to ISCO-08?
4. **Capability bridge contents** — confirm the 15–25 capabilities, ensuring finance/operations coverage.
5. **Team size, roles and submission deadline** — to fix milestone dates and confirm demo scope.
6. **Submission format and length limits** — to size the proposal.

*Resolved in v1.1:* lead persona = Aisyah (working adult at risk).

---

## 17. References
- Domain brief: *The Aiversecity Future-Ready Workforce Domain — Problem Statement & Marking Rubric* (SDC XMUM Hackathon).
- arXiv API Terms of Use — https://info.arxiv.org/help/api/tou.html
- ESCO Web Service API — https://esco.ec.europa.eu/en/use-esco/use-esco-services-api/esco-web-service-api
- OpenDOSM API — https://developer.data.gov.my/static-api/opendosm
- DOSM Job Vacancies Advertised Online — https://www.dosm.gov.my/portal-main/release-content/job-vacancies-landscape-in-malaysia-first-quarter-of-2022
- Singapore MOM Job Vacancy Rate by Occupation (data.gov.sg) — https://data.gov.sg/datasets/d_1e10046c33418c507bb2483c26dca489/view
- Hacker News Search API (Algolia) — https://hn.algolia.com/api
- MyMahir Malaysia Critical Occupations List (MyCOL) 2024/2025 — TalentCorp
- UN Sustainable Development Goals — https://sdgs.un.org/goals

---

## Appendix A — Plain-language glossary

Use this for onboarding team members and when writing the judges' proposal (which should avoid these terms where possible).

| Term | Plain meaning |
|---|---|
| Signal Ladder | Three steps a skill climbs: research buzz → global/regional jobs → Malaysian jobs |
| Rung | One step on the Signal Ladder |
| Trend score (z-score) | "How unusual is this period compared with normal?" Big positive = rising fast |
| Backfill | Fetching past months of data once, so there is history to compare against |
| Snapshot | A saved, dated copy of all results, so "before" and "after" can be compared |
| Ping | The message telling a user what changed when new data arrives |
| ESCO | The EU's free dictionary of jobs and the skills each job needs |
| MASCO | Malaysia's official list of occupation codes |
| ISCO-08 | The international occupation code standard that links MASCO and ESCO |
| Capability bridge | Our table linking what AI can do (e.g. read invoices) to the skills and tasks it affects |
| Dictionary / alias match | Matching a word to a skill by exact name, or by a known nickname ("Power BI" → data visualisation) |
| Embedding match | Matching words by meaning, not spelling ("ML" ≈ "machine learning") |
| Candidate queue | New, unknown skill terms waiting for a human to approve them |
| Match score | The share of a role's important skills the user already has, weighted by how in-demand each skill is |
| Scenario | A "what if" setting: moderate vs fast AI adoption |
| Counterfactual fairness test | Changing a fake person's name, gender or age and checking the results don't change |
