import pytest
from pydantic import ValidationError

from loom.models.taxonomy import Category, Sentiment, Theme, Urgency
from loom.models.ticket import LLMClassification, TicketClassification


def _valid_kwargs(**overrides) -> dict:
    base = {
        "primary_category": Category.ACCOUNT_ACCESS,
        "primary_theme": Theme.LOGIN_FAILURE,
        "sentiment": Sentiment.NEGATIVE,
        "sentiment_score": -0.6,
        "urgency": Urgency.HIGH,
        "actionable": True,
        "additional_issues": [],
    }
    base.update(overrides)
    return base


def test_valid_classification_passes():
    LLMClassification(**_valid_kwargs())


def test_theme_must_belong_to_category():
    with pytest.raises(ValidationError):
        LLMClassification(**_valid_kwargs(primary_category=Category.BILLING_PAYMENTS))


def test_positive_sentiment_requires_score_above_threshold():
    with pytest.raises(ValidationError):
        LLMClassification(
            **_valid_kwargs(sentiment=Sentiment.POSITIVE, sentiment_score=0.05)
        )


def test_negative_sentiment_requires_score_below_threshold():
    with pytest.raises(ValidationError):
        LLMClassification(
            **_valid_kwargs(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.05)
        )


def test_neutral_sentiment_requires_score_near_zero():
    with pytest.raises(ValidationError):
        LLMClassification(**_valid_kwargs(sentiment=Sentiment.NEUTRAL, sentiment_score=0.5))


def test_sentiment_score_out_of_range_rejected():
    with pytest.raises(ValidationError):
        LLMClassification(**_valid_kwargs(sentiment_score=1.5))


def test_additional_issue_theme_must_belong_to_its_own_category():
    with pytest.raises(ValidationError):
        LLMClassification(
            **_valid_kwargs(
                additional_issues=[
                    {
                        "category": Category.BILLING_PAYMENTS,
                        "theme": Theme.LOGIN_FAILURE,
                        "urgency": Urgency.LOW,
                    }
                ]
            )
        )


def test_unknown_field_rejected_strict_mode():
    with pytest.raises(ValidationError):
        LLMClassification(**_valid_kwargs(unexpected_field="nope"))


def test_fallback_is_always_valid_and_marked_unclassifiable():
    fallback = TicketClassification.fallback("T99", "some out-of-scope text")
    assert fallback.primary_category == Category.OTHER
    assert fallback.primary_theme == Theme.UNCLEAR
    assert fallback.is_unclassifiable() is True


def test_real_classification_is_not_unclassifiable(make_ticket):
    real = make_ticket()
    assert real.is_unclassifiable() is False
