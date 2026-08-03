import asyncio
import logging
import re

from pydantic import ValidationError

from loom.models.ticket import LLMClassification, TicketClassification
from loom.models.validation import RowRecord
from loom.prompts.classification import ClassificationPrompt
from loom.services.llm_service import AuthLLMError, LLMService, TransientLLMError
from loom.services.summarization_service import SummarizationService
from loom.services.text_preprocessing_service import TextPreprocessingService

logger = logging.getLogger("loom.classification_service")

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ClassificationService:
    def __init__(
        self,
        llm_service: LLMService,
        summarization_service: SummarizationService,
        preprocessor: TextPreprocessingService,
        model: str,
        max_concurrency: int,
        long_ticket_word_limit: int,
        request_timeout: float,
        remove_urls: bool,
    ):
        self.llm_service = llm_service
        self.summarization_service = summarization_service
        self.preprocessor = preprocessor
        self.model = model
        self.max_concurrency = max_concurrency
        self.long_ticket_word_limit = long_ticket_word_limit
        self.request_timeout = request_timeout
        self.remove_urls = remove_urls
        self._schema = LLMService.build_strict_json_schema(LLMClassification)

    @staticmethod
    def _validate(raw: str) -> tuple[LLMClassification | None, str | None]:
        try:
            return LLMClassification.model_validate_json(raw), None
        except (ValidationError, ValueError) as exc:
            return None, str(exc)

    @staticmethod
    def _coerce(raw: str) -> str | None:
        """Free, deterministic repair: strip code fences, trim, extract outermost JSON object."""
        text = _FENCE_RE.sub("", raw).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        return text[start : end + 1]

    async def _call_model(self, cleaned_text: str, nudge: str = "") -> str:
        return await LLMService.with_backoff(
            lambda: self.llm_service.complete_structured(
                model=self.model,
                system_prompt=ClassificationPrompt.SYSTEM_PROMPT,
                user_prompt=cleaned_text + nudge,
                schema=self._schema,
                schema_name="ticket_classification",
                timeout=self.request_timeout,
            )
        )

    async def classify_ticket(
        self, ticket_id: str, cleaned_text: str, display_text: str = ""
    ) -> TicketClassification:
        try:
            raw = await self._call_model(cleaned_text)
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error("Ticket %s: initial classification call failed (%s); using fallback", ticket_id, exc)
            return TicketClassification.fallback(ticket_id, display_text)

        parsed, error = self._validate(raw)

        if parsed is None:
            coerced = self._coerce(raw)
            if coerced is not None:
                parsed, error = self._validate(coerced)

        if parsed is None:
            try:
                raw2 = await self._call_model(
                    cleaned_text, ClassificationPrompt.build_reprompt_nudge(error or "unknown error")
                )
                parsed, error = self._validate(raw2)
                if parsed is None:
                    coerced2 = self._coerce(raw2)
                    if coerced2 is not None:
                        parsed, error = self._validate(coerced2)
            except (AuthLLMError, TransientLLMError) as exc:
                logger.error("Ticket %s: re-prompt call failed (%s); using fallback", ticket_id, exc)
                parsed = None

        if parsed is None:
            logger.error(
                "Ticket %s: classification unrecoverable after repair; using fallback (%s)", ticket_id, error
            )
            return TicketClassification.fallback(ticket_id, display_text)

        return TicketClassification(ticket_id=ticket_id, feedback_text=display_text, **parsed.model_dump())

    async def _safe_process(self, row: RowRecord) -> TicketClassification:
        redacted = ""
        try:
            cleaned = self.preprocessor.normalize_text(row.raw_feedback, remove_urls=self.remove_urls)
            redacted = self.preprocessor.redact_pii(cleaned)
            text_for_classification = redacted
            if row.word_count > self.long_ticket_word_limit:
                text_for_classification = await self.summarization_service.summarize_long_ticket(redacted)
            return await self.classify_ticket(row.ticket_id, text_for_classification, display_text=redacted)
        except Exception:
            logger.exception("Ticket %s: unexpected error in pipeline; using fallback", row.ticket_id)
            return TicketClassification.fallback(row.ticket_id, redacted)

    async def classify_all(self, rows: list[RowRecord]) -> list[TicketClassification]:
        """Process all rows with in-flight concurrency bounded to max_concurrency.
        One ticket's failure never affects another (independence is enforced
        inside `_safe_process`, which never raises).
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _bounded(row: RowRecord) -> TicketClassification:
            async with semaphore:
                return await self._safe_process(row)

        return await asyncio.gather(*[_bounded(row) for row in rows])
