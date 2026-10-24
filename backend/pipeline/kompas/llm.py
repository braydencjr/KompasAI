"""CV extraction with Gemini (PRD FR-1.3). The model only *labels* what the CV says: every item carries a
verbatim quote that is checked afterwards, and skills and jobs must map onto Kompas's own closed lists."""

import json
import logging
import os

import httpx
from google import genai
from google.genai import errors, types

from .curated import Curated

log = logging.getLogger("kompas.llm")

MODEL = "gemini-2.5-flash"   # disclosed in the UI and README (PRD FR-10.1)
NONE = "none"

INSTRUCTIONS = """Read the CV. Extract the person's skills and group related ones into one category (2 to 4 plain words).
Return each category with the skills under it. A skill has a `name` (its usual standard name) and a `quote` copied
exactly from the CV, character for character (3 to 25 words).

Also return each job (title, employer, period, a `quote`) with the ISCO-08 code from the list below it belongs to
or "none" (`occupation_fit`: "exact" if the job plainly is that occupation, "loose" if only the nearest group), and
a `summary` of at most 60 words addressed to the person ("You ..."). Never include the person's name or contact
details.

Occupation codes:
{occupations}"""


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _schema(cur: Curated) -> dict:
    quote = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "jobs": {"type": "array", "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "employer": {"type": "string"},
                               # ~430 codes is more than Gemini takes as an enum: checked afterwards (cv.analyse)
                               "period": {"type": "string"}, "occupation": {"type": "string"},
                               "occupation_fit": {"type": "string", "enum": ["exact", "loose"]},
                               "quote": quote},
                "required": ["title", "employer", "period", "occupation", "occupation_fit", "quote"],
            }},
            "categories": {"type": "array", "items": {
                "type": "object",
                "properties": {"category": {"type": "string"}, "skills": {"type": "array", "items": {
                    "type": "object", "properties": {"name": {"type": "string"}, "quote": quote},
                    "required": ["name", "quote"]}}},
                "required": ["category", "skills"],
            }},
        },
        "required": ["summary", "jobs", "categories"],
    }


def _system(cur: Curated, occupations: dict[str, str] | None = None) -> str:
    listing = "\n".join(f"- {code}: {title}" for code, title in sorted((occupations or cur.role_titles).items()))
    return INSTRUCTIONS.format(occupations=listing)


def _generate(system: str, contents: str, schema: dict, client: genai.Client | None,
              thinking: int | None = None) -> tuple[dict | None, str | None]:
    """One structured-output call. Returns (parsed JSON, None) or (None, reason) when the model can't be used,
    so callers can fall back or report it. thinking: the model's thinking budget in tokens (None: its default);
    small for choosing from given options, so the CV upload stays within its time limit."""
    if client is None and not available():
        return None, "no Gemini API key configured"
    try:
        client = client or genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0,
                thinking_config=None if thinking is None else types.ThinkingConfig(thinking_budget=thinking),
            ),
        )
    except errors.ClientError as e:
        log.warning("Gemini client error %s: %s", e.code, e.message)
        if e.code in (401, 403) or e.status == "PERMISSION_DENIED":
            return None, "Gemini API key was rejected"
        if e.code == 429:
            return None, "Gemini rate limit reached"
        return None, f"Gemini API error {e.code}"
    except errors.ServerError as e:
        log.warning("Gemini server error %s: %s", e.code, e.message)
        return None, f"Gemini is unavailable ({e.code})"
    except (httpx.TransportError, OSError):
        return None, "could not reach the Gemini API"

    candidate = (response.candidates or [None])[0]
    finish = candidate.finish_reason if candidate else None
    if finish == types.FinishReason.SAFETY or (response.prompt_feedback and response.prompt_feedback.block_reason):
        return None, "Gemini declined to process this input"
    if finish == types.FinishReason.MAX_TOKENS:
        return None, "Gemini's answer was cut off"
    if not response.text:
        return None, "Gemini returned no answer"
    try:
        return json.loads(response.text), None
    except json.JSONDecodeError:
        return None, "Gemini returned malformed JSON"


def extract_cv(text: str, cur: Curated, occupations: dict[str, str] | None = None,
               client: genai.Client | None = None) -> tuple[dict | None, str | None]:
    """Returns (extraction, None) or (None, reason) when the model can't be used, so callers can fall back.
    occupations: ISCO-08 code -> title, every occupation the job may map to (the ILO index's list)."""
    occupations = {**(occupations or {}), **cur.role_titles}
    result, error = _generate(_system(cur, occupations), f"<cv>\n{text}\n</cv>", _schema(cur), client, thinking=0)
    if error == "Gemini declined to process this input":
        error = "Gemini declined to process this CV"
    if result:      # one flat list for the matching below; each skill keeps its category as its `group`
        result["skills"] = [{"name": s["name"], "skill_id": NONE, "group": c["category"].strip(), "quote": s["quote"]}
                            for c in result.get("categories") or [] for s in c.get("skills") or []]
    return result, error


# ---------- alias suggestions for the review queue ----------

SUGGEST_INSTRUCTIONS = """You help maintain Kompas's skills dictionary. Kompas tags trending Hacker News stories and GitHub
repositories with skills by matching words (aliases) in their titles, topics and descriptions. The items below
matched no skill. For each item, decide whether it is mainly about one of the skills listed below.

Rules:
- Answer "none" unless the item is clearly and mainly about that skill. Most items are general tech news: "none".
- `alias`: the exact phrase from the item (title, topics or description), copied character for character, that
  names the skill: a tool, product, library, standard or technique (e.g. "LangGraph" for LLM agents, "dbt" for
  data engineering). It must be specific: wherever this phrase appears in other items, it should mean this skill.
  Never a generic word ("AI", "data", "agent", "tool", "open source") and never a company name on its own.
- `case_sensitive`: true when the phrase is also an everyday word or a short acronym (e.g. "Rust", "RAG").
- `reason`: one short sentence.

Skills:
{skills}"""


def _suggest_schema(cur: Curated) -> dict:
    ids = [NONE] + sorted(cid for cid, c in cur.concepts.items() if c.kind != "family")
    return {
        "type": "object",
        "properties": {"suggestions": {"type": "array", "items": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}, "skill_id": {"type": "string", "enum": ids},
                           "alias": {"type": "string"}, "case_sensitive": {"type": "boolean"},
                           "reason": {"type": "string"}},
            "required": ["item_id", "skill_id", "alias", "case_sensitive", "reason"],
        }}},
        "required": ["suggestions"],
    }


def suggest_aliases(items: list[dict], cur: Curated, client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """items: [{id, title, topics, description}]. Returns (suggestions, None) or (None, reason). Suggestions are
    unverified model output: kompas.suggest checks every one before a person sees it."""
    skills = "\n".join(f"- {cid}: {c.label}" for cid, c in sorted(cur.concepts.items()) if c.kind != "family")
    contents = "<items>\n" + json.dumps(items, ensure_ascii=False, indent=1) + "\n</items>"
    result, error = _generate(SUGGEST_INSTRUCTIONS.format(skills=skills), contents, _suggest_schema(cur), client)
    if error:
        return None, error
    return result.get("suggestions") or [], None


# ---------- role skill links from ESCO, for review ----------

LINK_INSTRUCTIONS = """You help maintain Kompas's role catalogue: which of Kompas's skills each role needs. The evidence is
the role's skills and knowledge in ESCO, the EU's occupation taxonomy. For each ESCO item below that IS one of
Kompas's skills, give a link. Skip every other item: most items match no Kompas skill.

Rules:
- `esco_item`: the ESCO item, exactly as listed. `skill_id`: the Kompas skill it is.
- Link only when anyone with the ESCO item certainly has the Kompas skill: the same skill, a named tool or
  language for it ("Python (computer programming)" is python), or a technique that is the skill ("utilise
  machine learning" is machine-learning).
- Never link a broad item to a specific skill: "computer programming" is not Python, "database" is not SQL,
  "statistics" is not forecasting, "accounting" is not month-end close.
- Watch for same names that mean different things: "ML (computer programming)" is a programming language, not
  machine learning.
- Use the most specific Kompas skill (an item about Power BI is power-bi, not data-visualisation).
- `reason`: one short sentence.

Kompas skills:
{skills}"""


# Gemini refuses schemas whose enums branch too much; past this many ESCO items the citation is a free string,
# still checked against the role's items afterwards (kompas.links.check)
MAX_ENUM_ITEMS = 80


def _link_schema(items: list[str], skill_ids: list[str]) -> dict:
    item = {"type": "string", "enum": items} if len(items) <= MAX_ENUM_ITEMS else {"type": "string"}
    return {
        "type": "object",
        "properties": {"links": {"type": "array", "items": {
            "type": "object",
            "properties": {"esco_item": item,
                           "skill_id": {"type": "string", "enum": skill_ids},
                           "reason": {"type": "string"}},
            "required": ["esco_item", "skill_id", "reason"],
        }}},
        "required": ["links"],
    }


def draft_role_links(role: str, esco_occupations: list[str], items: list[dict], cur: Curated,
                     client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """items: [{skill, relation, skill_type}] from occupation_skill_esco.csv. Returns (links, None) or (None, reason).
    Links are unverified model output: kompas.links checks every one before a person reviews the draft."""
    skills = {cid: c.label for cid, c in sorted(cur.concepts.items()) if c.kind == "skill"}
    # the tag goes first, so the model copies the label alone
    listing = "\n".join(f"- [{i['relation']} {i['skill_type']}] {i['skill']}" for i in items)
    contents = (f"<role>{role}</role>\n<esco_occupations>{', '.join(esco_occupations)}</esco_occupations>\n"
                f"<esco_items>\n{listing}\n</esco_items>")
    system = LINK_INSTRUCTIONS.format(skills="\n".join(f"- {cid}: {label}" for cid, label in skills.items()))
    result, error = _generate(system, contents, _link_schema(sorted({i["skill"] for i in items}), list(skills)), client)
    if error:
        return None, error
    return result.get("links") or [], None


# ---------- ESCO skills for what Kompas doesn't track (kompas/open_skills.py) ----------

ESCO_INSTRUCTIONS = """Each item is a skill as it is named in {context}, with the skills ESCO (the EU's skills taxonomy)
returned when searched for that name. For each item, pick the candidate that is that skill, or "none".

Pick it when the candidate is:
- the same skill in other words. ESCO names skills as actions: "solve problems" is problem solving, "think
  critically" is critical thinking, "recruit employees" is recruitment, "interview people" is interviewing,
  "use spreadsheets software" is spreadsheet skills.
- the tool or method named, or the skill a named feature or technique directly belongs to: "VLOOKUP" and "pivot
  tables" are "use spreadsheets software"; "Adobe InDesign" is the desktop publishing tool, if listed.
Answer "none" when every candidate is a different skill, a much broader field, or only shares words ("manage
email hosting service" is not search engine optimisation; "perform scientific research" is not "research" in an
HR role unless that is what it means). Never pick a candidate tied to a particular industry or product ("advise customers
on vehicle's extra services", "recommend footwear products to customers", "prepare audit schemes for ships") unless
the item names that industry or product: answer "none" instead. Copy the
item id and the uri exactly as given."""


def pick_esco(items: list[dict], context: str, client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """items: [{name, candidates: [{uri, label, type}]}]. Returns ([{name, uri}], None) or (None, reason). The uri is
    checked against that item's candidates afterwards."""
    schema = {"type": "object", "properties": {"picks": {"type": "array", "items": {
        "type": "object", "properties": {"item": {"type": "string"}, "uri": {"type": "string"}},
        "required": ["item", "uri"]}}}, "required": ["picks"]}
    # answered by id, not by name: the model tends to write the ESCO label back instead of the item's name
    ids = {f"S{n}": i["name"] for n, i in enumerate(items, start=1)}
    listing = [{"item": k, **i} for k, i in zip(ids, items)]
    contents = "<items>\n" + json.dumps(listing, ensure_ascii=False, indent=1) + "\n</items>"
    result, error = _generate(ESCO_INSTRUCTIONS.format(context=context), contents, schema, client, thinking=0)
    if error and error != "no Gemini API key configured":
        import time
        time.sleep(2)       # one retry: a rate limit or a busy model shouldn't drop every skill to "not tracked"
        result, error = _generate(ESCO_INSTRUCTIONS.format(context=context), contents, schema, client, thinking=0)
    if error:
        return None, error
    return [{"name": ids[p["item"]], "uri": p.get("uri")} for p in result.get("picks") or [] if p.get("item") in ids], None


# ---------- what Malaysian job postings ask for (kompas/requirements.py) ----------

POSTING_INSTRUCTIONS = """You read real job postings for one role and list the skills each posting asks for.

Rules:
- List every skill the posting requires or prefers, usually 5 to 15: languages, frameworks, tools, methods,
  knowledge, standards, certifications. Not benefits, the company's own duties, soft claims ("passionate",
  "team player") or years of experience.
- Most skills in a posting are NOT in the tracked list below. List them anyway, with skill_id "none": the list only
  tells you which id to use when a skill is one Kompas tracks.
- `quote`: a short phrase copied from that posting exactly, character for character (2 to 20 words), that asks
  for the skill. Never paraphrase a quote.
- `skill_id`: a tracked id only when the item IS that skill; never the nearest one. Otherwise "none".
- `name`: the skill's usual standard name ("C#", ".NET", "search engine optimisation", "SAP", "IFRS").
- Copy each posting's id exactly, and include every posting.

Tracked skill ids (for skill_id only):
{skills}"""


def extract_postings(postings: list[dict], cur: Curated, client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """postings: [{id, title, text}]. Returns ([{posting_id, skills: [{name, skill_id, quote}]}], None) or (None, reason).
    Quotes are unverified: kompas.requirements checks each against its posting."""
    ids = [NONE] + cur.curated_ids("skill")
    schema = {"type": "object", "properties": {"postings": {"type": "array", "items": {
        "type": "object", "properties": {
            "posting_id": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "skill_id": {"type": "string", "enum": ids}, "quote": {"type": "string"}},
                "required": ["name", "skill_id", "quote"]}}},
        "required": ["posting_id", "skills"]}}}, "required": ["postings"]}
    skills = "\n".join(f"- {cid}: {cur.concepts[cid].label}" for cid in ids[1:])
    contents = "<postings>\n" + json.dumps(postings, ensure_ascii=False, indent=1) + "\n</postings>"
    result, error = _generate(POSTING_INSTRUCTIONS.format(skills=skills), contents, schema, client)
    return (None, error) if error else (result.get("postings") or [], None)


# ---------- task exposure for jobs the ILO index doesn't list (kompas/exposure.py) ----------

EXPOSURE_INSTRUCTIONS = """You estimate how exposed an occupation's tasks are to generative AI, the way the ILO's
2025 exposure index does, using the index's own scored tasks as your reference.

The scale (0 to 1) is how much of the task generative AI could do: below 0.25 very low, 0.25 to 0.5 low,
0.5 to 0.75 medium, 0.75 and above high.

Rules:
- List the occupation's 5 to 8 main tasks, one short sentence each, in the style of the reference tasks.
- Score each task by comparing it with the reference tasks: cite 2 to 4 references (their `ref` ids) that are the
  most similar work. Your score must lie between the lowest and highest score of the references you cite,
  give or take 0.05.
- Only cite references from the list."""


def score_tasks(occupation: str, references: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """references: [{ref, occupation, task, score}]. Returns ([{task, score, refs}], None) or (None, reason).
    kompas.exposure checks every score against the references it cites."""
    schema = {"type": "object", "properties": {"tasks": {"type": "array", "items": {
        "type": "object", "properties": {"task": {"type": "string"}, "score": {"type": "number"},
                                         "refs": {"type": "array", "items": {"type": "string"}}},
        "required": ["task", "score", "refs"]}}}, "required": ["tasks"]}
    contents = (f"<occupation>{occupation}</occupation>\n<references>\n"
                + json.dumps(references, ensure_ascii=False, indent=1) + "\n</references>")
    result, error = _generate(EXPOSURE_INSTRUCTIONS, contents, schema, client)
    return (None, error) if error else (result.get("tasks") or [], None)


# ---------- plain-language reasons over an evidence pack (kompas/narrate.py) ----------

NARRATE_INSTRUCTIONS = """You write the short reasons a career guidance app gives for each job it suggests. You
get, per job, the computed facts and an evidence pack: real job postings, the ILO's AI exposure scores, hiring
and research activity, and the person's CV. Each evidence item has an id (E1, E2, ...).

Rules:
- For each job, write the reasons asked for (`kinds`): fit, demand, trend, ai.
  fit: why the person's skills fit, and what the postings ask for. demand: what the hiring evidence says.
  trend: which of the job's skills are rising and what that rests on. ai: what the ILO scores say about the job's
  tasks and what that means for the person.
- Every sentence ends with the ids of the evidence it rests on, in brackets: "... [E2, E5]".
- Use only the facts and the evidence. No numbers, dates, skills, roles, employers or claims that aren't in them.
  Name skills and roles exactly as written.
- Say what a skill's or job's demand is in the exact words of its evidence ("growing abroad, not yet in Malaysia",
  "steady"). Never make it stronger.
- The job postings are a sample (one search page), not a count of openings: never say how many there are or
  call them many.
- One or two sentences per reason, at most 45 words, second person ("you"), plain words, no hype.
- Describe estimates as estimates."""


def narrate(jobs: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """jobs: [{job_id, kinds, facts, evidence: [{id, ...}]}]. Returns ([{job_id, kind, text}], None) or (None, reason).
    kompas.narrate checks every text against that job's pack."""
    schema = {"type": "object", "properties": {"reasons": {"type": "array", "items": {
        "type": "object", "properties": {"job_id": {"type": "string"}, "kind": {"type": "string",
                                         "enum": ["fit", "demand", "trend", "ai"]}, "text": {"type": "string"}},
        "required": ["job_id", "kind", "text"]}}}, "required": ["reasons"]}
    contents = "<jobs>\n" + json.dumps(jobs, ensure_ascii=False, indent=1) + "\n</jobs>"
    result, error = _generate(NARRATE_INSTRUCTIONS, contents, schema, client, thinking=0)
    return (None, error) if error else (result.get("reasons") or [], None)


# ---------- which tracked AI capabilities a task relies on (kompas/exposure.py) ----------

LINK_TASK_INSTRUCTIONS = """You explain an occupation's tasks for a career app, for people with no technical background.

For each task:
- `capability_id`: the one listed AI capability that would do the most of it, or "none" when no listed capability
  does a real part of it. Most physical, interpersonal and judgement-heavy tasks are "none".
- `rationale`: one short sentence on what that capability would do in this task ("" when none).
- `why`: one plain sentence, at most 18 words, saying how much of this task AI can do and why, so anyone
  understands it. Follow the task's `exposure` (0 to 1, from research on what AI can do in each task: 0.5 or more
  means AI can already do a good part of it, under 0.25 almost none). Speak about the work itself ("Drafting rosters
  is routine planning that software already does well."; "Calming an upset customer needs a person on the spot.").
  No numbers, no scores, no research names, no jargon.
Copy each task id exactly."""


def link_capabilities(tasks: list[dict], capabilities: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """tasks: [{id, task, exposure}]; capabilities: [{id, label}]. Returns ([{task_id, capability_id, rationale, why}],
    None) or (None, reason). Ids and texts are checked afterwards."""
    ids = [NONE] + [c["id"] for c in capabilities]
    schema = {"type": "object", "properties": {"links": {"type": "array", "items": {
        "type": "object", "properties": {"task_id": {"type": "string"},
                                         "capability_id": {"type": "string", "enum": ids},
                                         "rationale": {"type": "string"}, "why": {"type": "string"}},
        "required": ["task_id", "capability_id", "rationale", "why"]}}}, "required": ["links"]}
    contents = (f"<capabilities>\n{json.dumps(capabilities, ensure_ascii=False, indent=1)}\n</capabilities>\n"
                f"<tasks>\n{json.dumps(tasks, ensure_ascii=False, indent=1)}\n</tasks>")
    result, error = _generate(LINK_TASK_INSTRUCTIONS, contents, schema, client, thinking=512)
    return (None, error) if error else (result.get("links") or [], None)


# ---------- the CV's skill groups, merged into a few broad ones (kompas/cv.py) ----------

GROUP_INSTRUCTIONS = """A CV's skills were sorted into too many small groups. Merge them into at most {n} broad categories
a recruiter would use, each 2 to 4 plain words ("Recruitment and HR", "Customer service", "Office software",
"Design and marketing"). Put related groups together; never name a category "General", "Other" or "Skills".
Map every group, copying its name exactly."""


def merge_groups(groups: dict[str, list[str]], n: int, client: genai.Client | None = None) -> tuple[dict[str, str] | None, str | None]:
    """groups: group name -> the skills in it. Returns ({group: category}, None) or (None, reason)."""
    schema = {"type": "object", "properties": {"categories": {"type": "array", "items": {
        "type": "object", "properties": {"group": {"type": "string"}, "category": {"type": "string"}},
        "required": ["group", "category"]}}}, "required": ["categories"]}
    contents = "<groups>\n" + json.dumps(groups, ensure_ascii=False, indent=1) + "\n</groups>"
    result, error = _generate(GROUP_INSTRUCTIONS.format(n=n), contents, schema, client, thinking=0)
    if error:
        return None, error
    return {c["group"]: c["category"].strip() for c in result.get("categories") or []
            if c.get("group") in groups and (c.get("category") or "").strip()}, None


# ---------- estimates where the market data is silent (kompas/journey.py estimate_signals) ----------

ESTIMATE_INSTRUCTIONS = """For each skill, judge how its demand is moving, for the rungs asked about. Our exact-name search found
nothing for it, which is not evidence of no demand. Each skill comes with `related` records (id, title, snippet) found
by looser matching on its words. List a record in `evidence` only if it is really about this skill or a close
neighbour of it (the same tool, task or field), not merely mentioning one of its words in passing: a job post that
says "good communication skills" is not evidence about communication. Only ids given, at most 3. Most general or
soft skills have no such record: return an empty list. Add what
you know of the labour market. Rung 1 is how much it is talked about (research, GitHub, tech news), rung 2 is hiring
abroad, rung 3 is hiring in Malaysia. Give a movement for each asked rung, an overall status, and one plain sentence
(max 20 words, no numbers) on why. Use "flat" when you have no real signal either way."""

MOVEMENTS = ["rising fast", "slightly up", "flat", "slightly down", "falling"]
STATUSES = ["Act now", "Emerging", "Watch", "Stable", "Declining", "Stalled"]


def estimate_signals(skills: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """skills: [{id, label, rungs: [1|2|3], status, related: [{id, title, snippet}]}]. Returns ([{id, status, rungs:
    [{rung, movement}], basis, evidence: [record ids]}], None) or (None, reason)."""
    schema = {"type": "object", "properties": {"skills": {"type": "array", "items": {
        "type": "object", "properties": {
            "id": {"type": "string"}, "status": {"type": "string", "enum": STATUSES}, "basis": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "rungs": {"type": "array", "items": {"type": "object", "properties": {
                "rung": {"type": "integer"}, "movement": {"type": "string", "enum": MOVEMENTS}},
                "required": ["rung", "movement"]}}},
        "required": ["id", "status", "basis", "rungs", "evidence"]}}}, "required": ["skills"]}
    contents = "<skills>\n" + json.dumps(skills, ensure_ascii=False, indent=1) + "\n</skills>"
    result, error = _generate(ESTIMATE_INSTRUCTIONS, contents, schema, client, thinking=0)
    return (None, error) if error else (result.get("skills") or [], None)


# ---------- the 2028 trend of skills the data is silent on (kompas/journey.py judge_trends) ----------

TREND_INSTRUCTIONS = """Judge each skill's value by 2028, for someone who has it today, given how AI and the job market are moving:
- "up": demand for it grows, or it becomes worth more.
- "ai": AI can already do or will soon do much of the work this skill covers.
- "fade": demand for it is shrinking.
- "hold": it stays about as valuable as it is.
Use your knowledge of the labour market. Use "hold" when you have no real reason to say otherwise. `why` is one plain
sentence (max 20 words, no numbers) for the person."""

TRENDS = ["up", "ai", "fade", "hold"]


def judge_trends(skills: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """skills: [{id, label}]. Returns ([{id, trend, why}], None) or (None, reason)."""
    schema = {"type": "object", "properties": {"skills": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "string"}, "trend": {"type": "string", "enum": TRENDS},
                                         "why": {"type": "string"}},
        "required": ["id", "trend", "why"]}}}, "required": ["skills"]}
    contents = "<skills>\n" + json.dumps(skills, ensure_ascii=False) + "\n</skills>"
    result, error = _generate(TREND_INSTRUCTIONS, contents, schema, client, thinking=0)
    return (None, error) if error else (result.get("skills") or [], None)


# ---------- GitHub Trending repositories, for Radar ----------

REPO_CATEGORIES = ("AI agents & coding tools", "Models & AI infrastructure", "Developer tools", "Data & analytics",
                   "Security", "Apps & self-hosted")

REPO_INSTRUCTIONS = """You describe trending GitHub repositories for people planning their careers, most of whom are
not programmers. For each repository:
- `category`: one of the categories below. Only if none fits at all, write a new category of 1 to 3 plain words.
- `plain`: what it is and who would use it, in at most 18 plain words. No jargon; spell out acronyms. Start
  with what it does ("Turns ...", "A guide to ..."), never with "This is" or "This tool".
- `skill_id`: the Kompas skill below that someone would learn by working with it, or "none". Most repositories: "none".

Categories:
{categories}

Kompas skills:
{skills}"""


def describe_repos(repos: list[dict], cur: Curated, client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """repos: [{full_name, description, language}]. Returns ([{full_name, category, plain, skill_id}], None) or
    (None, reason)."""
    skills = {cid: c.label for cid, c in sorted(cur.concepts.items()) if c.kind == "skill"}
    schema = {
        "type": "object",
        "properties": {"repos": {"type": "array", "items": {
            "type": "object",
            "properties": {"full_name": {"type": "string"}, "category": {"type": "string"},
                           "plain": {"type": "string"}, "skill_id": {"type": "string", "enum": [NONE, *skills]}},
            "required": ["full_name", "category", "plain", "skill_id"],
        }}},
        "required": ["repos"],
    }
    system = REPO_INSTRUCTIONS.format(categories="\n".join(f"- {c}" for c in REPO_CATEGORIES),
                                      skills="\n".join(f"- {cid}: {label}" for cid, label in skills.items()))
    contents = "<repos>\n" + json.dumps(repos, ensure_ascii=False, indent=1) + "\n</repos>"
    result, error = _generate(system, contents, schema, client, thinking=0)
    if error:
        return None, error
    return result.get("repos") or [], None


# ---------- Radar: news headlines and skill meanings in plain words ----------

STORY_INSTRUCTIONS = """You are the editor of a career newspaper for working people in Malaysia, most of whom are
not programmers. You get stories from Malaysian news sites, Malaysian subreddits and Hacker News, each with its
`outlet`, its title as published and sometimes a `snippet`. Titles may be in Malay or Manglish. For each story:
- `headline`: a clear newspaper headline in English, in sentence case (only the first word and names capitalised),
  at most 12 words, that a non-programmer understands. Say what happened. No jargon, no clickbait, no question
  marks. Common terms stay as they are (AI, IPO, EV, 5G); spell out rarer acronyms. Use only what the title and
  snippet say. For a Reddit post, say what the person is asking or sharing ("Fresh engineering graduate weighs
  RM3,000 offer in Penang").
- `dek`: one sentence, at most 22 words: what it means for people's work or careers. If the title doesn't say
  enough to know, say what the story is about instead. Never invent facts. Start with the substance, never with
  "This story", "This news", "This article" or "The story".
- `skill_id`: the Kompas skill below the story is mainly about, or "none".
- `career`: how much it matters to a working person in Malaysia planning their career:
  3 = directly about jobs, pay, hiring, layoffs, job offers, skills in demand, or AI changing how people work.
  2 = an industry or employer change likely to affect Malaysian workers (a sector booming or shrinking, a big
      Malaysian employer expanding, closing or merging, a regulation that changes how companies work).
  1 = business or technology background without a work angle: daily market moves (ringgit, Bursa, oil, Wall
      Street), earnings, board appointments, foreign company news, airline routes, gadget launches.
  0 = not about work: politics, crime, sport, entertainment, food, lifestyle, personal stories.
  A new AI model, developer tool, library or programming-language release is 1, unless it changes how
  non-programmers do their work (then 2). A software vulnerability is 1, unless a Malaysian organisation or a
  service most people use is affected (then 2). Most stories are 0 or 1; give 3 rarely.
- `topic`: a short lowercase key for the event, 2 to 5 words joined by hyphens ("waze-ban-malaysia",
  "maxis-buys-astro-broadband"). Stories about the same event get the same key, also across outlets. If a story
  is about one of the recent topics listed below, reuse that key exactly.

Recent topics:
{topics}

Kompas skills:
{skills}"""


def describe_stories(stories: list[dict], cur: Curated, recent_topics: list[str] | None = None,
                     client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """stories: [{id, outlet, title, snippet?}]. Returns ([{id, headline, dek, skill_id, career, topic}], None) or
    (None, reason). recent_topics: keys given to earlier stories, so a story about the same event reuses its key."""
    skills = {cid: c.label for cid, c in sorted(cur.concepts.items()) if c.kind == "skill"}
    schema = {"type": "object", "properties": {"stories": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "headline": {"type": "string"}, "dek": {"type": "string"},
                       "skill_id": {"type": "string", "enum": [NONE, *skills]},
                       "career": {"type": "integer", "enum": [0, 1, 2, 3]}, "topic": {"type": "string"}},
        "required": ["id", "headline", "dek", "skill_id", "career", "topic"],
    }}}, "required": ["stories"]}
    system = STORY_INSTRUCTIONS.format(skills="\n".join(f"- {cid}: {label}" for cid, label in skills.items()),
                                       topics="\n".join(f"- {t}" for t in recent_topics or []) or "(none yet)")
    contents = "<stories>\n" + json.dumps(stories, ensure_ascii=False, indent=1) + "\n</stories>"
    result, error = _generate(system, contents, schema, client, thinking=0)
    return (None, error) if error else (result.get("stories") or [], None)


CONCEPT_INSTRUCTIONS = """For each skill, write `plain`: what it is and what people do with it at work, in one
sentence of at most 16 plain words, for someone with no technical background. Spell out acronyms. No hype."""


def describe_concepts(concepts: list[dict], client: genai.Client | None = None) -> tuple[list[dict] | None, str | None]:
    """concepts: [{id, label}]. Returns ([{id, plain}], None) or (None, reason)."""
    schema = {"type": "object", "properties": {"skills": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "string"}, "plain": {"type": "string"}},
        "required": ["id", "plain"]}}}, "required": ["skills"]}
    contents = "<skills>\n" + json.dumps(concepts, ensure_ascii=False, indent=1) + "\n</skills>"
    result, error = _generate(CONCEPT_INSTRUCTIONS, contents, schema, client, thinking=0)
    return (None, error) if error else (result.get("skills") or [], None)
