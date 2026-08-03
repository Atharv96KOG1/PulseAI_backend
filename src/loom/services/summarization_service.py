import json
import logging

from loom.prompts.summarization import SummarizationPrompt
from loom.services.llm_service import AuthLLMError, LLMService, TransientLLMError
from loom.views.response import AnalyticsResult, ValidationReport

logger = logging.getLogger("loom.summarization_service")


class SummarizationService:
    def __init__(self, llm_service: LLMService, model: str, summary_model: str, request_timeout: float):
        self.llm_service = llm_service
        self.model = model
        self.summary_model = summary_model
        self.request_timeout = request_timeout

    async def summarize_long_ticket(self, redacted_text: str) -> str:
        """Summarize a long ticket before classification. Falls back to the
        original (redacted) text if the summarization call is unrecoverable —
        classification still runs on the full text rather than failing the ticket.
        """
        try:
            raw = await LLMService.with_backoff(
                lambda: self.llm_service.complete_text(
                    model=self.model,
                    system_prompt=SummarizationPrompt.LONG_TICKET_SYSTEM_PROMPT,
                    user_prompt=redacted_text,
                    timeout=self.request_timeout,
                )
            )
            summary = raw.strip()
            return summary or redacted_text
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error("Long-ticket summarization failed (%s); classifying full text instead", exc)
            return redacted_text

    @staticmethod
    def build_summary_facts(
        analytics: AnalyticsResult, validation_report: ValidationReport, out_of_scope_count: int = 0
    ) -> dict:
        """Assemble the Python-computed aggregate facts handed to the executive
        summary prompt. The narration model may only reference these values.

        `out_of_scope_count` is how many processed items came back with the
        fallback shape (Category "Other" / Theme "Unclear") — either the ticket
        text wasn't real product feedback (a stray question, spam, gibberish) or
        classification failed after every repair attempt. They still count as
        processed and still appear in every distribution above; this count only
        tells the narration model to name them explicitly instead of describing
        them like ordinary low-urgency feedback.
        """
        top_category = analytics.top_categories[0].name if analytics.top_categories else "N/A"
        top_theme = analytics.top_themes[0].name if analytics.top_themes else "N/A"
        return {
            "total_uploaded": validation_report.total_rows,
            "total_processed": analytics.total_processed,
            "total_skipped": analytics.total_skipped,
            "out_of_scope_count": out_of_scope_count,
            "processing_success_rate_pct": analytics.processing_success_rate,
            "category_distribution": analytics.category_distribution,
            "sentiment_distribution": analytics.sentiment_distribution,
            "theme_frequency": analytics.theme_frequency,
            "urgency_distribution": analytics.urgency_distribution,
            "top_category": top_category,
            "top_theme": top_theme,
            "top_categories": [rc.model_dump() for rc in analytics.top_categories[:5]],
            "top_themes": [rc.model_dump() for rc in analytics.top_themes[:5]],
            "positive_pct": analytics.positive_pct,
            "neutral_pct": analytics.neutral_pct,
            "negative_pct": analytics.negative_pct,
            "average_sentiment_score": analytics.average_sentiment_score,
            "high_urgency_count": analytics.high_urgency_count,
            "actionable_count": analytics.actionable_count,
        }

    @staticmethod
    def _fallback_summary(facts: dict) -> str:
        """Deterministic templated narrative used only if the LLM call itself
        is unavailable. Still built entirely from Python-computed facts.
        """
        return (
            f"Processed {facts['total_processed']} of {facts['total_uploaded']} submitted feedback items "
            f"({facts['processing_success_rate_pct']}% processing success rate). "
            f"The most common category was {facts['top_category']}, and the most common theme was "
            f"{facts['top_theme']}. Sentiment was {facts['positive_pct']}% positive, "
            f"{facts['neutral_pct']}% neutral, and {facts['negative_pct']}% negative "
            f"(average sentiment score {facts['average_sentiment_score']:+.2f}). "
            f"{facts['high_urgency_count']} tickets were flagged High urgency, and "
            f"{facts['actionable_count']} were marked actionable."
            + (
                f" {facts['out_of_scope_count']} submission(s) were out of scope — unrelated to the "
                "product (e.g. general questions, spam, or unintelligible text) rather than actionable "
                "feedback."
                if facts["out_of_scope_count"]
                else ""
            )
        )

    async def generate_executive_summary(self, facts: dict) -> str:
        try:
            raw = await LLMService.with_backoff(
                lambda: self.llm_service.complete_text(
                    model=self.summary_model,
                    system_prompt=SummarizationPrompt.EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
                    user_prompt=json.dumps(facts, indent=2),
                    timeout=self.request_timeout,
                )
            )
            return raw.strip() or self._fallback_summary(facts)
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error("Executive summary generation failed (%s); using templated fallback", exc)
            return self._fallback_summary(facts)
