"""Stage 5: batch classification.

Implements the exact repair contract: validate -> coerce (free) -> re-prompt
(one retry) -> fallback. Every ticket leaves this module with a valid
TicketClassification, success or fallback — never an exception.
"""

import asyncio
import logging
import re

from pydantic import ValidationError

from loom import config
from loom.pipeline.preprocess import normalize_text, redact_pii
from loom.pipeline.summarize import summarize_long_ticket
from loom.pipeline.validate import RowRecord
from loom.prompts.classification import CLASSIFICATION_SYSTEM_PROMPT, build_reprompt_nudge
from loom.schemas.ticket import LLMClassification, TicketClassification, fallback_classification
from loom.services.llm_client import (
    AuthLLMError,
    TransientLLMError,
    build_strict_json_schema,
    complete_structured,
    with_backoff,
)

logger = logging.getLogger("loom.classify")

_SCHEMA = build_strict_json_schema(LLMClassification)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _validate(raw: str) -> tuple[LLMClassification | None, str | None]:
    try:
        return LLMClassification.model_validate_json(raw), None
    except (ValidationError, ValueError) as exc:
        return None, str(exc)


def _coerce(raw: str) -> str | None:
    """Free, deterministic repair: strip code fences, trim, extract outermost JSON object."""
    text = _FENCE_RE.sub("", raw).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


async def _call_model(cleaned_text: str, nudge: str = "") -> str:
    return await with_backoff(
        lambda: complete_structured(
            model=config.LLM_MODEL,
            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
            user_prompt=cleaned_text + nudge,
            schema=_SCHEMA,
            schema_name="ticket_classification",
            timeout=config.REQUEST_TIMEOUT,
        )
    )


async def classify_ticket(ticket_id: str, cleaned_text: str, display_text: str = "") -> TicketClassification:
    try:
        raw = await _call_model(cleaned_text)
    except (AuthLLMError, TransientLLMError) as exc:
        logger.error("Ticket %s: initial classification call failed (%s); using fallback", ticket_id, exc)
        return fallback_classification(ticket_id, display_text)

    parsed, error = _validate(raw)

    if parsed is None:
        coerced = _coerce(raw)
        if coerced is not None:
            parsed, error = _validate(coerced)

    if parsed is None:
        try:
            raw2 = await _call_model(cleaned_text, build_reprompt_nudge(error or "unknown error"))
            parsed, error = _validate(raw2)
            if parsed is None:
                coerced2 = _coerce(raw2)
                if coerced2 is not None:
                    parsed, error = _validate(coerced2)
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error("Ticket %s: re-prompt call failed (%s); using fallback", ticket_id, exc)
            parsed = None

    if parsed is None:
        logger.error(
            "Ticket %s: classification unrecoverable after repair; using fallback (%s)", ticket_id, error
        )
        return fallback_classification(ticket_id, display_text)

    return TicketClassification(ticket_id=ticket_id, feedback_text=display_text, **parsed.model_dump())


async def _safe_process(row: RowRecord) -> TicketClassification:
    redacted = ""
    try:
        cleaned = normalize_text(row.raw_feedback, remove_urls=config.REMOVE_URLS)
        redacted = redact_pii(cleaned)
        text_for_classification = redacted
        if row.word_count > config.LONG_TICKET_WORD_LIMIT:
            text_for_classification = await summarize_long_ticket(redacted)
        return await classify_ticket(row.ticket_id, text_for_classification, display_text=redacted)
    except Exception:
        logger.exception("Ticket %s: unexpected error in pipeline; using fallback", row.ticket_id)
        return fallback_classification(row.ticket_id, redacted)


async def classify_all(rows: list[RowRecord]) -> list[TicketClassification]:
    """Process rows in batches of BATCH_SIZE, bounding in-flight concurrency
    to MAX_CONCURRENCY. One ticket's failure never affects another (batch
    independence is enforced inside `_safe_process`, which never raises).
    """
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)

    async def _bounded(row: RowRecord) -> TicketClassification:
        async with semaphore:
            return await _safe_process(row)

    results: list[TicketClassification] = []
    for i in range(0, len(rows), config.BATCH_SIZE):
        batch = rows[i : i + config.BATCH_SIZE]
        batch_results = await asyncio.gather(*[_bounded(row) for row in batch])
        results.extend(batch_results)
    return results
