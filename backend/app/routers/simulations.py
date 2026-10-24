from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm import LLMError, LLMUnavailable, is_configured
from app.services.simulations import RubricItem, coach, generate_practice, generate_simulation, grade_doc, run_brief

router = APIRouter(prefix="/simulations", tags=["simulations"])


class SimulationRequest(BaseModel):
    role_id: str
    title: str
    summary: str = ""
    skills: list[str] = []
    gaps: list[str] = []
    # skip the cache and write a new scenario
    fresh: bool = False
    # four AI-tool tasks (brief, check, brief, check) instead of two core tasks and two AI ones
    ai_only: bool = False


class PracticeRequest(BaseModel):
    role: str = Field(description="The job the route leads to")
    skill: str
    goal: str = ""
    learn: list[str] = []
    project: str = Field("", description="The plan's mini project idea for this stop")
    fresh: bool = False


class DocGradeRequest(BaseModel):
    brief: str
    requirements: list[str] = []
    checklist: list[str] = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=8000)


class Turn(BaseModel):
    prompt: str
    reply: str


class BriefRequest(BaseModel):
    ai_name: str
    field: str = Field(description="The role or field the AI tool is used in")
    task: str = Field(description="What the user was asked to get from the AI tool")
    rubric: list[RubricItem]
    history: list[Turn] = []
    prompt: str = Field(min_length=1, max_length=4000)


def _fail(e: Exception):
    # 503 tells the frontend to use its built-in sample; 502 means the AI call itself went wrong
    if isinstance(e, LLMUnavailable):
        raise HTTPException(503, str(e)) from e
    raise HTTPException(502, str(e)) from e


@router.get("/status")
async def status() -> dict:
    return {"ai": is_configured()}


@router.post("")
async def create_simulation(req: SimulationRequest) -> dict:
    try:
        return await generate_simulation(req.role_id, req.title, req.summary, req.skills, req.gaps, req.fresh, req.ai_only)
    except (LLMUnavailable, LLMError) as e:
        _fail(e)


@router.post("/practice")
async def practice(req: PracticeRequest) -> dict:
    """One hands-on mini project for a stop on The Route: a spreadsheet, code or document task, checked like the
    simulation's tasks."""
    try:
        return await generate_practice(req.role, req.skill, req.goal, req.learn, req.project, req.fresh)
    except (LLMUnavailable, LLMError) as e:
        _fail(e)


@router.post("/grade-doc")
async def grade_document(req: DocGradeRequest) -> dict:
    """AI review of a written task: which checklist points the document covers, and feedback. The page falls back
    to keyword matching when this fails."""
    try:
        return await grade_doc(req.brief, req.requirements, req.checklist, req.text)
    except (LLMUnavailable, LLMError) as e:
        _fail(e)


class CoachRequest(BaseModel):
    sender: str
    sender_role: str = ""
    title: str
    brief: str
    requirements: list[str] = []
    material: str = Field("", max_length=6000, description="What's on the learner's screen, answers hidden")
    evidence: list[str] = Field([], max_length=8, description="What the automatic check said about their last attempt")
    history: list[Turn] = Field([], max_length=12)
    question: str = Field(min_length=1, max_length=600)


@router.post("/coach")
async def coach_help(req: CoachRequest) -> dict:
    try:
        return await coach(req.sender, req.sender_role, req.title, req.brief, req.requirements, req.material,
                           req.evidence, [(t.prompt, t.reply) for t in req.history], req.question)
    except (LLMUnavailable, LLMError) as e:
        _fail(e)


@router.post("/brief")
async def brief(req: BriefRequest) -> dict:
    try:
        return await run_brief(
            req.ai_name, req.field, req.task, req.rubric, [(t.prompt, t.reply) for t in req.history], req.prompt
        )
    except (LLMUnavailable, LLMError) as e:
        _fail(e)
