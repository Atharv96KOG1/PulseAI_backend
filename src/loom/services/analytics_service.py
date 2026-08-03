from collections import Counter

from loom.models.ticket import TicketClassification
from loom.views.response import AnalyticsResult, RankedCount


class AnalyticsService:
    """Pure Python arithmetic, zero AI calls — every dashboard number comes from here."""

    @staticmethod
    def _pct(count: int, denominator: int) -> float:
        return round(count / denominator * 100, 2) if denominator else 0.0

    def compute(
        self,
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

        top_categories = [
            RankedCount(name=name, count=count) for name, count in category_counts.most_common()
        ]
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
            processing_success_rate=self._pct(processed, total_uploaded),
            positive_pct=self._pct(sentiment_counts.get("Positive", 0), processed),
            neutral_pct=self._pct(sentiment_counts.get("Neutral", 0), processed),
            negative_pct=self._pct(sentiment_counts.get("Negative", 0), processed),
            average_sentiment_score=average_sentiment_score,
            high_urgency_count=urgency_counts.get("High", 0),
        )

    def merge(self, results: list[AnalyticsResult]) -> AnalyticsResult:
        """Combine several already-computed AnalyticsResult objects (e.g. one per
        saved analysis in a date range) into one. Every distribution and top-N
        list is recomputed from the merged counts — never averaged naively — so
        the result is identical to what compute() would have produced had every
        ticket from every analysis been processed together in one batch.
        """
        total_processed = sum(r.total_processed for r in results)
        total_skipped = sum(r.total_skipped for r in results)

        category_counts: Counter = Counter()
        sentiment_counts: Counter = Counter()
        theme_counts: Counter = Counter()
        urgency_counts: Counter = Counter()
        urgency_with_additional: Counter = Counter()
        for r in results:
            category_counts.update(r.category_distribution)
            sentiment_counts.update(r.sentiment_distribution)
            theme_counts.update(r.theme_frequency)
            urgency_counts.update(r.urgency_distribution)
            urgency_with_additional.update(r.urgency_distribution_with_additional)

        actionable_count = sum(r.actionable_count for r in results)

        weighted_score_sum = sum(r.average_sentiment_score * r.total_processed for r in results)
        average_sentiment_score = round(weighted_score_sum / total_processed, 3) if total_processed else 0.0

        top_categories = [
            RankedCount(name=name, count=count) for name, count in category_counts.most_common()
        ]
        top_themes = [RankedCount(name=name, count=count) for name, count in theme_counts.most_common()]

        return AnalyticsResult(
            total_processed=total_processed,
            total_skipped=total_skipped,
            category_distribution=dict(category_counts),
            sentiment_distribution=dict(sentiment_counts),
            theme_frequency=dict(theme_counts),
            urgency_distribution=dict(urgency_counts),
            urgency_distribution_with_additional=dict(urgency_with_additional),
            actionable_count=actionable_count,
            top_categories=top_categories,
            top_themes=top_themes,
            processing_success_rate=self._pct(total_processed, total_processed + total_skipped),
            positive_pct=self._pct(sentiment_counts.get("Positive", 0), total_processed),
            neutral_pct=self._pct(sentiment_counts.get("Neutral", 0), total_processed),
            negative_pct=self._pct(sentiment_counts.get("Negative", 0), total_processed),
            average_sentiment_score=average_sentiment_score,
            high_urgency_count=urgency_counts.get("High", 0),
        )
