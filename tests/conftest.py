import pytest

from loom.models.taxonomy import Category, Sentiment, Theme, Urgency
from loom.models.ticket import TicketClassification


@pytest.fixture
def make_ticket():
    """Factory fixture: build a valid TicketClassification with sane defaults,
    overriding only the fields a test cares about.
    """

    def _make(
        ticket_id: str = "T1",
        feedback_text: str = "sample feedback",
        primary_category: Category = Category.BILLING_PAYMENTS,
        primary_theme: Theme = Theme.FAILED_PAYMENT,
        sentiment: Sentiment = Sentiment.NEGATIVE,
        sentiment_score: float = -0.8,
        urgency: Urgency = Urgency.HIGH,
        actionable: bool = True,
        additional_issues: list | None = None,
    ) -> TicketClassification:
        return TicketClassification(
            ticket_id=ticket_id,
            feedback_text=feedback_text,
            primary_category=primary_category,
            primary_theme=primary_theme,
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            urgency=urgency,
            actionable=actionable,
            additional_issues=additional_issues or [],
        )

    return _make
