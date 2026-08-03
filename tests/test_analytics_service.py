from loom.models.taxonomy import Category, Sentiment, Theme, Urgency
from loom.services.analytics_service import AnalyticsService


def test_compute_basic_distributions(make_ticket):
    items = [
        make_ticket(ticket_id="1", sentiment=Sentiment.POSITIVE, sentiment_score=0.5, urgency=Urgency.LOW),
        make_ticket(ticket_id="2", sentiment=Sentiment.NEGATIVE, sentiment_score=-0.8, urgency=Urgency.HIGH),
        make_ticket(ticket_id="3", sentiment=Sentiment.NEGATIVE, sentiment_score=-0.4, urgency=Urgency.HIGH),
    ]
    result = AnalyticsService().compute(items, total_uploaded=3, skipped=0)

    assert result.total_processed == 3
    assert result.total_skipped == 0
    assert result.sentiment_distribution == {"Positive": 1, "Negative": 2}
    assert result.high_urgency_count == 2
    assert result.processing_success_rate == 100.0
    assert result.positive_pct == round(1 / 3 * 100, 2)
    assert result.negative_pct == round(2 / 3 * 100, 2)
    assert result.average_sentiment_score == round((0.5 - 0.8 - 0.4) / 3, 3)


def test_compute_handles_zero_items():
    result = AnalyticsService().compute([], total_uploaded=0, skipped=0)
    assert result.total_processed == 0
    assert result.processing_success_rate == 0.0
    assert result.average_sentiment_score == 0.0


def test_compute_counts_additional_issues_in_urgency_with_additional(make_ticket):
    ticket = make_ticket(
        urgency=Urgency.LOW,
        additional_issues=[
            {"category": Category.BILLING_PAYMENTS, "theme": Theme.FAILED_PAYMENT, "urgency": Urgency.HIGH}
        ],
    )
    result = AnalyticsService().compute([ticket], total_uploaded=1, skipped=0)
    assert result.urgency_distribution == {"Low": 1}
    assert result.urgency_distribution_with_additional == {"Low": 1, "High": 1}
    # Primary headline metric must NOT double-count the additional issue.
    assert result.high_urgency_count == 0


def test_merge_matches_computing_everything_at_once(make_ticket):
    service = AnalyticsService()
    batch_a = [make_ticket(ticket_id="1", sentiment_score=-0.5)]
    batch_b = [
        make_ticket(ticket_id="2", sentiment_score=0.7, sentiment=Sentiment.POSITIVE),
        make_ticket(ticket_id="3", sentiment_score=-0.9),
    ]

    result_a = service.compute(batch_a, total_uploaded=1, skipped=0)
    result_b = service.compute(batch_b, total_uploaded=2, skipped=0)
    merged = service.merge([result_a, result_b])

    combined_direct = service.compute(batch_a + batch_b, total_uploaded=3, skipped=0)

    assert merged.total_processed == combined_direct.total_processed
    assert merged.category_distribution == combined_direct.category_distribution
    assert merged.average_sentiment_score == combined_direct.average_sentiment_score
    assert merged.positive_pct == combined_direct.positive_pct
    assert merged.negative_pct == combined_direct.negative_pct


def test_merge_weights_by_ticket_count_not_naive_average(make_ticket):
    service = AnalyticsService()
    # 1 ticket at -1.0, then 3 tickets at +1.0 — naive average of averages
    # would give 0.0; weighted average must favor the larger batch.
    small = service.compute(
        [make_ticket(ticket_id="1", sentiment_score=-1.0, sentiment=Sentiment.NEGATIVE)],
        total_uploaded=1,
        skipped=0,
    )
    large = service.compute(
        [
            make_ticket(ticket_id=str(i), sentiment_score=1.0, sentiment=Sentiment.POSITIVE)
            for i in range(2, 5)
        ],
        total_uploaded=3,
        skipped=0,
    )
    merged = service.merge([small, large])
    assert merged.average_sentiment_score == 0.5
