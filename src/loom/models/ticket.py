"""Pydantic models for per-ticket classification.

`LLMClassification` is the exact shape requested from the model (a pure
enumeration block, no `ticket_id` — the backend assigns that). `TicketClassification`
extends it with the backend-assigned `ticket_id` and is what the API returns.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loom.models.taxonomy import CATEGORY_THEMES, Category, Sentiment, Theme, Urgency


class AdditionalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    theme: Theme
    urgency: Urgency

    @model_validator(mode="after")
    def theme_belongs_to_category(self) -> "AdditionalIssue":
        if self.theme not in CATEGORY_THEMES[self.category]:
            raise ValueError(
                f"theme '{self.theme.value}' does not belong to category '{self.category.value}'"
            )
        return self


class LLMClassification(BaseModel):
    """The exact schema the model is asked to produce.

    `sentiment_score` is a numeric field by explicit product decision, overriding
    the "no continuous sentiment score" rule in CLAUDE.md/Loom_Source_of_Truth.md.
    It must stay sign-consistent with `sentiment` (enforced below) so the two
    never contradict each other on the dashboard.
    """

    model_config = ConfigDict(extra="forbid")

    primary_category: Category
    primary_theme: Theme
    sentiment: Sentiment
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    urgency: Urgency
    actionable: bool
    additional_issues: list[AdditionalIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def primary_theme_belongs_to_category(self) -> "LLMClassification":
        if self.primary_theme not in CATEGORY_THEMES[self.primary_category]:
            raise ValueError(
                f"primary_theme '{self.primary_theme.value}' does not belong to "
                f"primary_category '{self.primary_category.value}'"
            )
        return self

    @model_validator(mode="after")
    def sentiment_score_matches_sentiment(self) -> "LLMClassification":
        score = self.sentiment_score
        if self.sentiment == Sentiment.POSITIVE and score <= 0.1:
            raise ValueError("sentiment_score must be > 0.1 when sentiment is 'Positive'")
        if self.sentiment == Sentiment.NEGATIVE and score >= -0.1:
            raise ValueError("sentiment_score must be < -0.1 when sentiment is 'Negative'")
        if self.sentiment == Sentiment.NEUTRAL and not (-0.1 <= score <= 0.1):
            raise ValueError("sentiment_score must be within [-0.1, 0.1] when sentiment is 'Neutral'")
        return self


class TicketClassification(LLMClassification):
    """The full per-ticket output returned by the API.

    `feedback_text` is the cleaned, PII-redacted ticket text. It is attached
    by the backend for display in the dashboard's Feedback Explorer only —
    it is never part of `LLMClassification`, so it is never requested from
    or produced by the model.
    """

    ticket_id: str
    feedback_text: str = ""

    @classmethod
    def fallback(cls, ticket_id: str, feedback_text: str = "") -> "TicketClassification":
        """The valid fallback shape emitted when a ticket cannot be classified."""
        return cls(
            ticket_id=ticket_id,
            feedback_text=feedback_text,
            primary_category=Category.OTHER,
            primary_theme=Theme.UNCLEAR,
            sentiment=Sentiment.NEUTRAL,
            sentiment_score=0.0,
            urgency=Urgency.LOW,
            actionable=False,
            additional_issues=[],
        )

    def is_unclassifiable(self) -> bool:
        """True when this item carries the fallback shape — either the model flagged
        the ticket as out-of-scope (non-English/spam/unintelligible) or the repair
        contract was exhausted after a real classification failure. Both cases carry
        no real signal about the ticket.
        """
        reference = TicketClassification.fallback(self.ticket_id, self.feedback_text)
        return (
            self.primary_category == reference.primary_category
            and self.primary_theme == reference.primary_theme
            and self.sentiment == reference.sentiment
            and self.sentiment_score == reference.sentiment_score
            and self.urgency == reference.urgency
            and self.actionable == reference.actionable
            and self.additional_issues == reference.additional_issues
        )
