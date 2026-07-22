"""Stage 6: deterministic analytics. Pure Python — NO LLM imports allowed
in this module or package. This separation is load-bearing: every number
here is computed, never generated.
"""

from collections import Counter

from schemas.response import AnalyticsResult, RankedCount
from schemas.ticket import TicketClassification


def _pct(count: int, denominator: int) -> float:
    return round(count / denominator * 100, 2) if denominator else 0.0


def compute_analytics(
    items: list[TicketClassification],
    total_uploaded: int,
    skipped: int,
) -> AnalyticsResult:
    """Aggregates over the PRIMARY issue of processed (valid) tickets only.
    `additional_issues` are rolled into the urgency-with-additional view but
    are otherwise excluded from headline metrics to avoid double-counting.
    """
    processed = len(items)

    category_counts = Counter(item.primary_category.value for item in items)
    sentiment_counts = Counter(item.sentiment.value for item in items)
    theme_counts = Counter(item.primary_theme.value for item in items)
    urgency_counts = Counter(item.urgency.value for item in items)

    urgency_with_additional = Counter(urgency_counts)
    for item in items:
        for issue in item.additional_issues:
            urgency_with_additional[issue.urgency.value] += 1

    actionable_count = sum(1 for item in items if item.actionable)
    average_sentiment_score = (
        round(sum(item.sentiment_score for item in items) / processed, 3) if processed else 0.0
    )

    top_categories = [RankedCount(name=name, count=count) for name, count in category_counts.most_common()]
    top_themes = [RankedCount(name=name, count=count) for name, count in theme_counts.most_common()]

    return AnalyticsResult(
        total_processed=processed,
        total_skipped=skipped,
        category_distribution=dict(category_counts),
        sentiment_distribution=dict(sentiment_counts),
        theme_frequency=dict(theme_counts),
        urgency_distribution=dict(urgency_counts),
        urgency_distribution_with_additional=dict(urgency_with_additional),
        actionable_count=actionable_count,
        top_categories=top_categories,
        top_themes=top_themes,
        processing_success_rate=_pct(processed, total_uploaded),
        positive_pct=_pct(sentiment_counts.get("Positive", 0), processed),
        neutral_pct=_pct(sentiment_counts.get("Neutral", 0), processed),
        negative_pct=_pct(sentiment_counts.get("Negative", 0), processed),
        average_sentiment_score=average_sentiment_score,
        high_urgency_count=urgency_counts.get("High", 0),
    )
