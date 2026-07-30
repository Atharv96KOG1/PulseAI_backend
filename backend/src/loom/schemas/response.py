"""Pydantic models for the /analyze API response payload."""

from pydantic import BaseModel

from loom.schemas.ticket import TicketClassification


class ValidationReport(BaseModel):
    total_rows: int
    processed: int
    skipped: int
    skip_reasons: dict[str, int]


class RankedCount(BaseModel):
    name: str
    count: int


class AnalyticsResult(BaseModel):
    total_processed: int
    total_skipped: int
    category_distribution: dict[str, int]
    sentiment_distribution: dict[str, int]
    theme_frequency: dict[str, int]
    urgency_distribution: dict[str, int]
    urgency_distribution_with_additional: dict[str, int]
    actionable_count: int
    top_categories: list[RankedCount]
    top_themes: list[RankedCount]
    processing_success_rate: float
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    average_sentiment_score: float
    high_urgency_count: int


class AnalyzeResponse(BaseModel):
    analysis_id: str
    validation_report: ValidationReport
    items: list[TicketClassification]
    analytics: AnalyticsResult
    summary: str


class AnalysisRef(BaseModel):
    analysis_id: str
    created_at: str


class RangeSummaryResponse(BaseModel):
    start: str
    end: str
    analyses_included: list[AnalysisRef]
    validation_report: ValidationReport
    analytics: AnalyticsResult
    summary: str
