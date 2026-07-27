"""OpenAI client wrapper: structured-output calls, typed errors, and
short-backoff retry for transient failures.

This module owns all direct contact with the LLM provider. Nothing outside
`pipeline/` and `services/` should import the OpenAI SDK directly.
"""

import asyncio
import logging
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel

from loom import config

logger = logging.getLogger("loom.llm_client")


class TransientLLMError(Exception):
    """429 / 5xx / timeout / connection errors — safe to retry with backoff."""


class AuthLLMError(Exception):
    """Authentication failures — never retried."""


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=config.API_KEY)


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic v2 model into an OpenAI strict-mode JSON schema.

    Strict mode requires every object to set `additionalProperties: false` and
    list every property as required (including ones with a default), and
    forbids leftover `default` keys. This walks the schema (and its $defs)
    to enforce that shape.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def _tighten(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                _tighten(value)
        elif isinstance(node, list):
            for item in node:
                _tighten(item)

    _tighten(schema)
    for definition in defs.values():
        _tighten(definition)
    if defs:
        schema["$defs"] = defs
    return schema


async def complete_structured(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    timeout: float,
) -> str:
    """One structured-output call. Returns raw JSON text. Raises TransientLLMError/AuthLLMError."""
    try:
        response = await _client().chat.completions.create(
            model=model,
            temperature=0,
            timeout=timeout,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
        return response.choices[0].message.content or ""
    except AuthenticationError as exc:
        raise AuthLLMError(str(exc)) from exc
    except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc:
        raise TransientLLMError(str(exc)) from exc


async def complete_text(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
) -> str:
    """One free-text completion call (used for summarization/narration)."""
    try:
        response = await _client().chat.completions.create(
            model=model,
            temperature=0,
            timeout=timeout,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except AuthenticationError as exc:
        raise AuthLLMError(str(exc)) from exc
    except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc:
        raise TransientLLMError(str(exc)) from exc


async def with_backoff(fn, *, max_attempts: int = 3, base_delay: float = 0.5):
    """Retry `fn` (an async callable) on TransientLLMError with short backoff.
    AuthLLMError is never retried and propagates immediately.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except TransientLLMError:
            attempt += 1
            if attempt >= max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Transient LLM error, retrying in %.1fs (attempt %d/%d)", delay, attempt, max_attempts
            )
            await asyncio.sleep(delay)
