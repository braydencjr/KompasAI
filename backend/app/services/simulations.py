"""Generates hands-on work simulations with Claude and converts them to the frontend's format.

Claude writes the scenario; code checks it. Spreadsheet answers are computed by the frontend's
formula engine from the formulas Claude gives (never from Claude's arithmetic), calendars must have
a valid arrangement, and code tasks ship a reference solution the frontend runs against the tests.
"""

import itertools
import json
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.services.llm import LLMError, generate

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
HOURS = list(range(9, 17))
CORE_TOOLS = {"sheet", "calendar", "code"}


# ---------- what Claude fills in ----------


class SheetColumn(BaseModel):
    label: str
    fmt: Literal["text", "num", "rm", "pct", "dec"]


class SheetCell(BaseModel):
    value: str = Field(description="Text shown in a given cell, e.g. '1,200,000' or '8%'. Empty for answer cells.")
    answer: Optional[str] = Field(
        description="Only for cells the user fills in: the correct formula (e.g. '=B2*(1+C2)') or a literal "
        "text answer ('Yes'/'No'). null for given cells."
    )


class Sheet(BaseModel):
    name: str = Field(description="File name, e.g. 'q4_forecast.xlsx'")
    columns: list[SheetColumn]
    rows: list[list[SheetCell]]


class BusyBlock(BaseModel):
    person: str
    day: int = Field(description="0 = Mon … 4 = Fri")
    hours: list[int] = Field(description="Busy start hours, 9–16")


class Meeting(BaseModel):
    id: str
    title: str
    people: list[str]
    deadline_day: Optional[int] = Field(description="Must finish by this day (0–4), with deadline_hour")
    deadline_hour: Optional[int] = Field(description="Must finish by this hour (10–17) on deadline_day")
    deadline_label: Optional[str] = Field(description="e.g. 'Thu 12:00'")
    after: Optional[str] = Field(description="id of a meeting that must happen before this one")


class Calendar(BaseModel):
    busy: list[BusyBlock]
    events: list[Meeting]


class CodeTest(BaseModel):
    label: str
    args_json: str = Field(description="JSON array of the arguments, e.g. '[{\"amount\": 100}, 3]'")
    expected_json: str = Field(description="JSON of the expected return value")


class Code(BaseModel):
    fn: str = Field(description="Function name")
    starter: str = Field(description="Starter code: comments describing the inputs, the signature, a placeholder return")
    solution: str = Field(description="A correct implementation of the same function")
    tests: list[CodeTest]


class Table(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class AiReply(BaseModel):
    text: str
    table: Optional[Table]
    steps: Optional[list[str]]
    note: Optional[str]


class RubricItem(BaseModel):
    label: str
    keywords: list[str] = Field(description="Lowercase words or numbers a brief covering this item would contain")


class Prompt(BaseModel):
    rubric: list[RubricItem]
    weak: AiReply = Field(description="Reply to a vague brief: generic, or asks what the user wants")
    partial: AiReply = Field(description="Reply to an incomplete brief: plausible but flawed; note explains the flaw")
    strong: AiReply = Field(description="Reply to a complete brief: specific and correct")


class Segment(BaseModel):
    text: str
    issue: Optional[str] = Field(description="What's wrong with this segment, or null if it's fine")


class Review(BaseModel):
    artifact_name: str
    format: Literal["prose", "code"]
    source_title: str
    source: Table = Field(description="The true data the draft must be checked against")
    segments: list[Segment]
    verdict: Literal["approve", "send back"]


class Feedback(BaseModel):
    high: str
    mid: str
    low: str


class GenTask(BaseModel):
    id: str
    tool: Literal["sheet", "calendar", "code", "prompt", "review"]
    title: str
    competency: str
    gap: Optional[str] = Field(description="Exact name of the user's skill gap this task builds, or null")
    minutes: int
    from_name: str
    from_role: str
    subject: str
    brief: str
    requirements: list[str]
    feedback: Feedback = Field(description="The sender's one-sentence reaction to strong, partial and weak work")
    ai_name: Optional[str] = Field(description="prompt/review tasks only: generic name of the AI tool")
    why: Optional[str] = Field(description="prompt/review tasks only: how this kind of AI tool is changing the work")
    sheet: Optional[Sheet]
    calendar: Optional[Calendar]
    code: Optional[Code]
    prompt: Optional[Prompt]
    review: Optional[Review]


class GenSimulation(BaseModel):
    setting: str = Field(description="e.g. 'Monday 09:00 · Week 1 · Group finance'")
    welcome_from: str
    welcome_text: str
    tasks: list[GenTask]


SYSTEM = """You design short, hands-on work simulations for Kompas, a career app for working adults in Malaysia. \
A user who is considering a role spends about 20 minutes doing four real pieces of its work, then gets a performance report.

Produce exactly four tasks, in this order:
1–2. Core work. Each uses one tool: "sheet" (numbers and analysis), "calendar" (coordinating people and deadlines) \
or "code" (a small JavaScript function; only for technical roles). Pick what the role really does day to day; prefer two different tools.
3. "prompt": the user briefs an AI tool that is arriving in this field, to get a piece of work done.
4. "review": an AI tool has produced a draft with planted mistakes; the user must catch them before it goes out.
Tasks 3–4 show how the work is changing, so the user can practise directing and checking AI.

Rules for every task:
- Everything is fictional: people (Malaysian names), organisations (generic, e.g. "a regional bank"), and figures \
made up for the exercise. Never cite real market statistics, surveys or real AI products; give AI tools generic names \
like "Forecast Assistant".
- Self-contained: everything the user needs is in the brief, requirements and data. Pitch it at a capable new joiner \
in week one; each task takes 4–8 minutes.
- Requirements spell out exactly what counts as done. Where natural, tie a task to one of the user's skill gaps and \
set `gap` to that gap's exact name.
- `feedback` is the sender's one-sentence reaction to strong, partial and weak work.
- Fill only the field for the task's tool (sheet, calendar, code, prompt or review); set the others to null. \
ai_name and why are only for prompt and review tasks.
- Plain English, short sentences.

sheet: 2–5 data rows; the first column holds row labels. Row 1 is the header row, so the first data row is \
spreadsheet row 2 and columns are A, B, C…. Include 4–10 answer cells: value "" and answer set to a formula starting \
with "=" that uses cell references (A1 style), + - * / ^ and SUM, AVERAGE, MIN, MAX, ROUND, ABS, or a literal Yes/No \
for judgement cells. Given cells have answer null and show numbers like "1,200,000" or "8%". Answer formulas may use \
other answer cells. The requirements state every formula in words. Column fmt: rm (money), pct (percentages, \
stored as fractions), num, dec (2 decimals), text.

calendar: days are Mon–Fri (0–4); every meeting lasts one hour and starts between 9 and 16. Use 2–3 meetings and 2–4 \
people. Make it a real puzzle: at least one arrangement satisfies every busy block, deadline and ordering, but most \
naive choices fail. deadline_day + deadline_hour = the meeting must finish by then; `after` = id of a meeting that \
must come first. The requirements state every constraint.

code: a small, pure JavaScript function (no imports, async, I/O or randomness). The starter has comments describing \
the inputs, the signature and a placeholder return; the solution is correct; 5–7 tests cover normal and edge cases, \
with args_json a JSON array of arguments and expected_json the JSON result.

prompt: the brief says what to get from the AI tool, which only knows what the user tells it. The rubric lists 4–5 \
essentials of a good brief, each with lowercase keywords a brief covering it would contain (write numbers without \
thousands separators too). Replies: weak (generic, or asks what they want), partial (plausible but wrong because the \
brief was incomplete, with a note explaining why), strong (specific and correct, with a table or steps).

review: source is the true data. segments are the AI draft: 5–8 sentences (prose) or code lines (code, keep the \
indentation). Exactly 3 segments have an issue explaining what's wrong (a number that contradicts the source, an \
invented fact, an overclaim, a missing control…); the rest have issue null. verdict is "send back"."""


def _user_prompt(title: str, summary: str, skills: list[str], gaps: list[str]) -> str:
    return (
        f"Role: {title}\n"
        f"What the role does: {summary or 'not given'}\n"
        f"User's current skills: {', '.join(skills) or 'not given'}\n"
        f"User's skill gaps for this role: {', '.join(gaps) or 'not given'}\n\n"
        "Write the simulation."
    )


# ---------- checks ----------


def _calendar_problems(cal: Calendar) -> list[str]:
    people = {b.person for b in cal.busy} | {p for e in cal.events for p in e.people}
    busy = {(b.person, b.day, h) for b in cal.busy for h in b.hours}
    ids = {e.id for e in cal.events}
    problems = []
    if not 1 <= len(cal.events) <= 3:
        problems.append("calendar needs 1–3 meetings")
    for e in cal.events:
        if e.after and e.after not in ids:
            problems.append(f"meeting {e.id} comes after unknown meeting {e.after}")
    if problems or not people:
        return problems

    slots = [(d, h) for d in range(len(DAYS)) for h in HOURS]

    def ok(e: Meeting, slot: tuple[int, int], placed: dict[str, tuple[int, int]]) -> bool:
        d, h = slot
        if any((p, d, h) in busy for p in e.people):
            return False
        if e.deadline_day is not None and e.deadline_hour is not None:
            if d > e.deadline_day or (d == e.deadline_day and h + 1 > e.deadline_hour):
                return False
        if e.after and placed[e.after] >= slot:
            return False
        return slot not in placed.values()

    for combo in itertools.product(slots, repeat=len(cal.events)):
        placed = {e.id: s for e, s in zip(cal.events, combo)}
        if all(ok(e, placed[e.id], {k: v for k, v in placed.items() if k != e.id}) for e in cal.events):
            return []
    return ["calendar has no valid arrangement"]


def problems(sim: GenSimulation) -> list[str]:
    found = []
    if len(sim.tasks) != 4:
        return [f"expected 4 tasks, got {len(sim.tasks)}"]
    tools = [t.tool for t in sim.tasks]
    if tools[0] not in CORE_TOOLS or tools[1] not in CORE_TOOLS or tools[2:] != ["prompt", "review"]:
        found.append(f"task order should be core, core, prompt, review; got {tools}")

    for t in sim.tasks:
        part = getattr(t, t.tool)
        if part is None:
            found.append(f"task {t.id} is missing its {t.tool} content")
            continue
        if t.tool in ("prompt", "review") and not (t.ai_name and t.why):
            found.append(f"task {t.id} needs ai_name and why")
        if t.tool == "sheet":
            if any(len(r) != len(part.columns) for r in part.rows):
                found.append(f"task {t.id}: every sheet row needs {len(part.columns)} cells")
            if not any(c.answer for r in part.rows for c in r):
                found.append(f"task {t.id}: sheet has no answer cells")
        elif t.tool == "calendar":
            found += [f"task {t.id}: {p}" for p in _calendar_problems(part)]
        elif t.tool == "code":
            for test in part.tests:
                try:
                    if not isinstance(json.loads(test.args_json), list):
                        found.append(f"task {t.id}: test args must be a JSON array")
                    json.loads(test.expected_json)
                except json.JSONDecodeError:
                    found.append(f"task {t.id}: test '{test.label}' has invalid JSON")
        elif t.tool == "prompt":
            if not 3 <= len(part.rubric) <= 6:
                found.append(f"task {t.id}: rubric needs 3–6 items")
        elif t.tool == "review":
            issues = sum(1 for s in part.segments if s.issue)
            if issues < 2 or issues == len(part.segments):
                found.append(f"task {t.id}: review needs 2+ planted issues and some correct segments")
    return found


# ---------- conversion to the frontend's Simulation type ----------


def _reply(r: AiReply) -> dict:
    out: dict = {"text": r.text}
    if r.table:
        out["table"] = r.table.model_dump()
    if r.steps:
        out["steps"] = r.steps
    if r.note:
        out["note"] = r.note
    return out


def _task(t: GenTask) -> dict:
    out: dict = {
        "id": t.id,
        "tool": t.tool,
        "title": t.title,
        "competency": t.competency,
        "minutes": t.minutes,
        "from": t.from_name,
        "fromRole": t.from_role,
        "subject": t.subject,
        "brief": t.brief,
        "requirements": t.requirements,
        "review": t.feedback.model_dump(),
    }
    if t.gap:
        out["gap"] = t.gap
    if t.tool in ("prompt", "review"):
        out["aiName"] = t.ai_name
        out["why"] = t.why

    if t.tool == "sheet":
        s = t.sheet
        out["sheet"] = {
            "name": s.name,
            "columns": [c.model_dump() for c in s.columns],
            # answer cells carry the solution formula; the frontend computes the expected value from it
            "rows": [[c.value if c.answer is None else {"solution": c.answer} for c in r] for r in s.rows],
        }
    elif t.tool == "calendar":
        c = t.calendar
        people = sorted({b.person for b in c.busy} | {p for e in c.events for p in e.people})
        busy = {p: [[] for _ in DAYS] for p in people}
        for b in c.busy:
            if 0 <= b.day < len(DAYS):
                busy[b.person][b.day] = sorted(set(busy[b.person][b.day]) | set(b.hours))
        events = []
        for e in c.events:
            ev: dict = {"id": e.id, "title": e.title, "people": e.people}
            if e.deadline_day is not None and e.deadline_hour is not None:
                label = e.deadline_label or f"{DAYS[e.deadline_day]} {e.deadline_hour:02d}:00"
                ev["deadline"] = {"day": e.deadline_day, "hour": e.deadline_hour, "label": label}
            if e.after:
                ev["after"] = e.after
            events.append(ev)
        out.update(days=DAYS, hours=HOURS, busy=busy, events=events)
    elif t.tool == "code":
        c = t.code
        out.update(
            fn=c.fn,
            helpers=[],
            starter=c.starter,
            solution=c.solution,
            tests=[{"label": x.label, "args": json.loads(x.args_json), "expected": json.loads(x.expected_json)} for x in c.tests],
        )
    elif t.tool == "prompt":
        p = t.prompt
        out["rubric"] = [r.model_dump() for r in p.rubric]
        out["replies"] = {"weak": _reply(p.weak), "partial": _reply(p.partial), "strong": _reply(p.strong)}
    elif t.tool == "review":
        r = t.review
        out.update(
            artifactName=r.artifact_name,
            format=r.format,
            source={"title": r.source_title, **r.source.model_dump()},
            segments=[{"text": s.text, **({"issue": s.issue} if s.issue else {})} for s in r.segments],
            verdict=r.verdict,
        )
    return out


def to_frontend(sim: GenSimulation, role_id: str, title: str) -> dict:
    return {
        "roleId": role_id,
        "title": title,
        "setting": sim.setting,
        "welcome": {"from": sim.welcome_from, "text": sim.welcome_text},
        "tasks": [_task(t) for t in sim.tasks],
        "generated": True,
    }


# ---------- entry point ----------

ATTEMPTS = 2
_cache: dict[tuple[str, str], dict] = {}


async def generate_simulation(
    role_id: str, title: str, summary: str, skills: list[str], gaps: list[str], fresh: bool = False
) -> dict:
    key = (role_id, title)
    if not fresh and key in _cache:
        return _cache[key]

    messages = [{"role": "user", "content": _user_prompt(title, summary, skills, gaps)}]
    for _ in range(ATTEMPTS):
        sim = await generate(GenSimulation, system=SYSTEM, messages=messages)
        found = problems(sim)
        if not found:
            result = to_frontend(sim, role_id, title)
            _cache[key] = result
            return result
        # one more try, telling Claude exactly what to fix
        messages = messages + [
            {"role": "assistant", "content": sim.model_dump_json()},
            {"role": "user", "content": "Fix these problems and return the whole simulation again:\n- " + "\n- ".join(found)},
        ]
    raise LLMError("The AI couldn't produce a valid simulation; try again.")


# ---------- the live "Direct the AI" assistant ----------


class BriefResult(BaseModel):
    reply: AiReply
    covered: list[bool] = Field(description="One entry per rubric item: does the user's brief so far provide it?")


def _brief_system(ai_name: str, field: str, task: str, rubric: list[RubricItem]) -> str:
    items = "\n".join(f"{i + 1}. {r.label} (e.g. mentions: {', '.join(r.keywords[:6])})" for i, r in enumerate(rubric))
    return f"""You are {ai_name}, an AI tool used by {field} teams, inside a training simulation. \
The user is practising how to brief an AI tool well.

Reply to the user's latest message exactly as this tool would. You only know what is in this conversation: you \
cannot see their files, systems or data. If the brief leaves out something important, do what a real tool does: make \
a reasonable attempt and clearly label any assumed or illustrative figures, or ask one short clarifying question. \
Never cite real market statistics. Keep it short: text of 80 words or fewer, plus an optional table (6 rows or fewer) \
or steps (7 or fewer), and an optional one-sentence note for caveats.

Separately, grade the user's brief so far (all their messages together) against this rubric. covered has one entry \
per item, true only if the brief clearly provides it:
{items}

(For grading only, the user's assignment was: {task})"""


async def run_brief(
    ai_name: str, field: str, task: str, rubric: list[RubricItem], history: list[tuple[str, str]], prompt: str
) -> dict:
    messages: list[dict] = []
    for user_text, reply_text in history:
        messages += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}]
    messages.append({"role": "user", "content": prompt})

    result = await generate(
        BriefResult, system=_brief_system(ai_name, field, task, rubric), messages=messages, effort="low", max_tokens=4000
    )
    covered = (result.covered + [False] * len(rubric))[: len(rubric)]
    return {"reply": _reply(result.reply), "covered": covered}
