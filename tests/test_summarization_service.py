from loom.services.summarization_service import SummarizationService
from loom.views.response import AnalyticsResult, RankedCount, ValidationReport


class _StubLLMService:
    def __init__(self, text_response: str = ""):
        self.text_response = text_response

    async def complete_text(self, **kwargs):
        return self.text_response


def _analytics(**overrides) -> AnalyticsResult:
    base = dict(
        total_processed=2,
        total_skipped=0,
        category_distribution={"Billing & Payments": 2},
        sentiment_distribution={"Negative": 2},
        theme_frequency={"Failed Payment": 2},
        urgency_distribution={"High": 2},
        urgency_distribution_with_additional={"High": 2},
        actionable_count=2,
        top_categories=[RankedCount(name="Billing & Payments", count=2)],
        top_themes=[RankedCount(name="Failed Payment", count=2)],
        processing_success_rate=100.0,
        positive_pct=0.0,
        neutral_pct=0.0,
        negative_pct=100.0,
        average_sentiment_score=-0.7,
        high_urgency_count=2,
    )
    base.update(overrides)
    return AnalyticsResult(**base)


def _validation_report() -> ValidationReport:
    return ValidationReport(total_rows=2, processed=2, skipped=0, skip_reasons={})


def test_build_summary_facts_includes_out_of_scope_count():
    facts = SummarizationService.build_summary_facts(_analytics(), _validation_report(), out_of_scope_count=3)
    assert facts["out_of_scope_count"] == 3
    assert facts["total_processed"] == 2
    assert facts["top_category"] == "Billing & Payments"


def test_build_summary_facts_defaults_out_of_scope_to_zero():
    facts = SummarizationService.build_summary_facts(_analytics(), _validation_report())
    assert facts["out_of_scope_count"] == 0


async def test_generate_executive_summary_uses_llm_when_available():
    service = SummarizationService(
        llm_service=_StubLLMService("A real generated summary."),
        model="m",
        summary_model="m",
        request_timeout=5.0,
    )
    facts = SummarizationService.build_summary_facts(_analytics(), _validation_report())
    summary = await service.generate_executive_summary(facts)
    assert summary == "A real generated summary."


async def test_generate_executive_summary_falls_back_when_llm_empty():
    service = SummarizationService(
        llm_service=_StubLLMService(""), model="m", summary_model="m", request_timeout=5.0
    )
    facts = SummarizationService.build_summary_facts(_analytics(), _validation_report(), out_of_scope_count=1)
    summary = await service.generate_executive_summary(facts)
    assert "out of scope" in summary
    assert "Billing & Payments" in summary


async def test_summarize_long_ticket_returns_original_on_empty_response():
    service = SummarizationService(
        llm_service=_StubLLMService(""), model="m", summary_model="m", request_timeout=5.0
    )
    result = await service.summarize_long_ticket("the original redacted text")
    assert result == "the original redacted text"
