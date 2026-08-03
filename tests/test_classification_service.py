from loom.services.classification_service import ClassificationService
from loom.services.summarization_service import SummarizationService
from loom.services.text_preprocessing_service import TextPreprocessingService


class _StubLLMService:
    """Duck-typed stand-in for LLMService: returns canned JSON, no network calls."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def complete_structured(self, **kwargs):
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]

    async def complete_text(self, **kwargs):
        return ""


VALID_JSON = """{
  "primary_category": "Account & Access",
  "primary_theme": "Login Failure",
  "sentiment": "Negative",
  "sentiment_score": -0.7,
  "urgency": "High",
  "actionable": true,
  "additional_issues": []
}"""


def _classification_service(llm_stub) -> ClassificationService:
    summarization_service = SummarizationService(
        llm_service=llm_stub, model="test-model", summary_model="test-model", request_timeout=5.0
    )
    return ClassificationService(
        llm_service=llm_stub,
        summarization_service=summarization_service,
        preprocessor=TextPreprocessingService(),
        model="test-model",
        max_concurrency=3,
        long_ticket_word_limit=300,
        request_timeout=5.0,
        remove_urls=False,
    )


async def test_classify_ticket_succeeds_on_first_valid_response():
    stub = _StubLLMService([VALID_JSON])
    service = _classification_service(stub)

    result = await service.classify_ticket("T1", "I can't log in", display_text="I can't log in")

    assert result.ticket_id == "T1"
    assert result.primary_theme.value == "Login Failure"
    assert stub.calls == 1


async def test_classify_ticket_repairs_code_fenced_json_without_extra_call():
    fenced = f"```json\n{VALID_JSON}\n```"
    stub = _StubLLMService([fenced])
    service = _classification_service(stub)

    result = await service.classify_ticket("T2", "text")

    assert result.primary_theme.value == "Login Failure"
    assert stub.calls == 1  # coercion is free, no second model call needed


async def test_classify_ticket_retries_once_then_falls_back_to_valid_json():
    stub = _StubLLMService(["not json at all", VALID_JSON])
    service = _classification_service(stub)

    result = await service.classify_ticket("T3", "text")

    assert result.primary_theme.value == "Login Failure"
    assert stub.calls == 2


async def test_classify_ticket_falls_back_to_safe_default_after_repeated_failures():
    stub = _StubLLMService(["garbage", "still garbage"])
    service = _classification_service(stub)

    result = await service.classify_ticket("T4", "text", display_text="original text")

    assert result.is_unclassifiable() is True
    assert result.feedback_text == "original text"


async def test_classify_all_processes_every_row_independently(monkeypatch):
    from loom.models.validation import RowRecord

    stub = _StubLLMService([VALID_JSON])
    service = _classification_service(stub)
    rows = [
        RowRecord(ticket_id=str(i), raw_feedback=f"issue {i}", source=None, date=None, word_count=2)
        for i in range(5)
    ]

    results = await service.classify_all(rows)

    assert len(results) == 5
    assert {r.ticket_id for r in results} == {str(i) for i in range(5)}
