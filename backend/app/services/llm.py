import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import ANTHROPIC_MODEL, GEMINI_MODEL

# The value shipped in .env.example; treated the same as no key at all.
API_KEY_PLACEHOLDER = "your-anthropic-api-key"

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """No usable API key, so AI features are switched off."""


class LLMError(Exception):
    """The model call failed or returned nothing usable."""


def _claude_key() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return bool(key) and key != API_KEY_PLACEHOLDER


def _gemini_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def provider() -> str | None:
    """Claude when its key is set, else Gemini (the key the signal engine already uses), else none."""
    return "claude" if _claude_key() else "gemini" if _gemini_key() else None


def model_name() -> str | None:
    return {"claude": ANTHROPIC_MODEL, "gemini": GEMINI_MODEL}.get(provider() or "")


def is_configured() -> bool:
    return provider() is not None


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
    """Calls the configured model and returns its answer parsed into `output`."""
    which = provider()
    if which is None:
        raise LLMUnavailable("AI features are not configured: set ANTHROPIC_API_KEY or GEMINI_API_KEY in backend/.env.")
    if which == "gemini":
        return await _gemini(output, system=system, messages=messages, max_tokens=max_tokens)

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


async def _gemini(output: type[T], *, system: str, messages: list[dict], max_tokens: int) -> T:
    """The same call on Gemini: structured JSON output, validated against `output`."""
    from google import genai
    from google.genai import errors, types

    contents = [types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
                for m in messages]
    try:
        response = await genai.Client().aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=output.model_json_schema(),
                max_output_tokens=max(max_tokens, 32000),
            ),
        )
    except errors.ClientError as e:
        if e.code in (401, 403):
            raise LLMUnavailable("The Gemini API key was rejected.") from e
        if e.code == 429:
            raise LLMError("The AI service is busy; try again in a moment.") from e
        raise LLMError(f"The AI request failed ({e.code}).") from e
    except errors.ServerError as e:
        raise LLMError(f"The AI service is unavailable ({e.code}).") from e
    except OSError as e:
        raise LLMError("Could not reach the AI service.") from e

    candidate = (response.candidates or [None])[0]
    if candidate and candidate.finish_reason == types.FinishReason.MAX_TOKENS:
        raise LLMError("The AI's answer was cut off.")
    if candidate and candidate.finish_reason == types.FinishReason.SAFETY:
        raise LLMError("The AI declined this request.")
    try:
        return output.model_validate_json(response.text or "")
    except ValidationError as e:
        raise LLMError("The AI returned an answer in an unexpected format.") from e
