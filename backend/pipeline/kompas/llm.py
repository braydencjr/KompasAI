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

INSTRUCTIONS = """You read a CV and extract a skills profile for Kompas, a career guidance tool.

Rules:
- Extract only what the CV states. Every item needs a `quote`: a short phrase copied from the CV exactly,
  character for character (3 to 25 words), that shows the item. Never paraphrase a quote.
- Map each skill to the closest skill id from the list below, or "none" if nothing fits. Match by meaning:
  "matched supplier invoices to purchase orders" is accounts payable even though it doesn't say so.
  A tool or method the person used counts; a vague claim ("hard-working", "team player") is not a skill.
- Map each job to the closest occupation code from the list below, or "none".
- Never extract or mention the person's name, age, date of birth, gender, ethnicity, nationality, religion,
  marital status, photo, or contact details.
- `summary`: at most 80 words about their experience and skills, using only items you extracted.

Skill ids:
{skills}

Occupation codes:
{occupations}"""


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _schema(cur: Curated) -> dict:
    skill_ids = [NONE] + sorted(cid for cid, c in cur.concepts.items() if c.kind != "family")
    isco = [NONE] + sorted(cur.occupation_titles)
    quote = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "jobs": {"type": "array", "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "employer": {"type": "string"},
                               "period": {"type": "string"}, "occupation": {"type": "string", "enum": isco},
                               "quote": quote},
                "required": ["title", "employer", "period", "occupation", "quote"],
            }},
            "skills": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "skill_id": {"type": "string", "enum": skill_ids},
                               "quote": quote},
                "required": ["name", "skill_id", "quote"],
            }},
        },
        "required": ["summary", "jobs", "skills"],
    }


def _system(cur: Curated) -> str:
    skills = "\n".join(f"- {cid}: {c.label}" for cid, c in sorted(cur.concepts.items()) if c.kind != "family")
    occupations = "\n".join(f"- {code}: {title}" for code, title in sorted(cur.occupation_titles.items()))
    return INSTRUCTIONS.format(skills=skills, occupations=occupations)


def extract_cv(text: str, cur: Curated, client: genai.Client | None = None) -> tuple[dict | None, str | None]:
    """Returns (extraction, None) or (None, reason) when the model can't be used, so callers can fall back."""
    if client is None and not available():
        return None, "no Gemini API key configured"
    try:
        client = client or genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY
        response = client.models.generate_content(
            model=MODEL,
            contents=f"<cv>\n{text}\n</cv>",
            config=types.GenerateContentConfig(
                system_instruction=_system(cur),
                response_mime_type="application/json",
                response_json_schema=_schema(cur),
                temperature=0,
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
        return None, "Gemini declined to process this CV"
    if finish == types.FinishReason.MAX_TOKENS:
        return None, "Gemini's answer was cut off"
    if not response.text:
        return None, "Gemini returned no answer"
    try:
        return json.loads(response.text), None
    except json.JSONDecodeError:
        return None, "Gemini returned malformed JSON"
