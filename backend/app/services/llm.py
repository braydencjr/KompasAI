import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import ANTHROPIC_MODEL

# The value shipped in .env.example; treated the same as no key at all.
API_KEY_PLACEHOLDER = "your-anthropic-api-key"

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """No usable API key, so AI features are switched off."""


class LLMError(Exception):
    """The model call failed or returned nothing usable."""


def is_configured() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return bool(key) and key != API_KEY_PLACEHOLDER


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        # generation can take a minute; one retry keeps a stuck request from hanging the UI for long
        _client = anthropic.AsyncAnthropic(timeout=180.0, max_retries=1)
    return _client


async def generate(
    output: type[T],
    *,
    system: str,
    messages: list[dict],
    effort: str = "medium",
    max_tokens: int = 16000,
) -> T:
    """Calls Claude and returns its answer parsed into `output`."""
    if not is_configured():
        raise LLMUnavailable("AI features are not configured: set ANTHROPIC_API_KEY in backend/.env.")

    try:
        response = await _get_client().beta.messages.parse(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=output,
            output_config={"effort": effort},
            # if a safety classifier declines, the API retries on its recommended fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise LLMUnavailable("The Anthropic API key was rejected.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("The AI service is busy; try again in a moment.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"The AI request failed ({e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the AI service.") from e
    except ValidationError as e:
        raise LLMError("The AI returned an answer in an unexpected format.") from e

    if response.stop_reason == "refusal":
        raise LLMError("The AI declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The AI's answer was cut off.")
    if response.parsed_output is None:
        raise LLMError("The AI returned an answer in an unexpected format.")
    return response.parsed_output
