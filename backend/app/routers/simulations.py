from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.llm import LLMError, LLMUnavailable, is_configured
from app.services.simulations import RubricItem, generate_simulation, run_brief

router = APIRouter(prefix="/simulations", tags=["simulations"])


class SimulationRequest(BaseModel):
    role_id: str
    title: str
    summary: str = ""
    skills: list[str] = []
    gaps: list[str] = []
    # skip the cache and write a new scenario
    fresh: bool = False


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
        return await generate_simulation(req.role_id, req.title, req.summary, req.skills, req.gaps, req.fresh)
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
