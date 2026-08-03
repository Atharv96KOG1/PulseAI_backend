import pytest

from loom.repositories.analysis_repository import AnalysisRepository
from loom.services.analytics_service import AnalyticsService
from loom.views.response import ValidationReport


@pytest.fixture
def repo(tmp_path) -> AnalysisRepository:
    repository = AnalysisRepository(db_path=str(tmp_path / "test_loom.db"))
    repository.init_schema()
    return repository


def _validation_report(**overrides) -> ValidationReport:
    base = {"total_rows": 2, "processed": 2, "skipped": 0, "skip_reasons": {}}
    base.update(overrides)
    return ValidationReport(**base)


def test_save_and_get_analysis_roundtrip(repo, make_ticket):
    items = [make_ticket(ticket_id="1"), make_ticket(ticket_id="2")]
    analytics = AnalyticsService().compute(items, total_uploaded=2, skipped=0)

    analysis_id, ticket_row_ids = repo.save_analysis(_validation_report(), items, analytics, "a summary")

    assert len(ticket_row_ids) == 2
    record = repo.get_analysis(analysis_id)
    assert record is not None
    assert record["summary"] == "a summary"
    assert record["validation_report"]["total_rows"] == 2
    assert len(record["items"]) == 2
    assert {t["ticket_id"] for t in record["items"]} == {"1", "2"}


def test_get_analysis_returns_none_when_missing(repo):
    assert repo.get_analysis("does-not-exist") is None


def test_additional_issues_persisted(repo, make_ticket):
    from loom.models.taxonomy import Category, Theme, Urgency

    ticket = make_ticket(
        ticket_id="1",
        additional_issues=[
            {"category": Category.BILLING_PAYMENTS, "theme": Theme.FAILED_PAYMENT, "urgency": Urgency.LOW}
        ],
    )
    analytics = AnalyticsService().compute([ticket], total_uploaded=1, skipped=0)
    report = _validation_report(total_rows=1, processed=1)
    analysis_id, _ = repo.save_analysis(report, [ticket], analytics, "s")

    record = repo.get_analysis(analysis_id)
    issues = record["items"][0]["additional_issues"]
    assert len(issues) == 1
    assert issues[0]["category"] == Category.BILLING_PAYMENTS.value


def test_list_analyses_orders_newest_first(repo, make_ticket):
    items = [make_ticket(ticket_id="1")]
    analytics = AnalyticsService().compute(items, total_uploaded=1, skipped=0)
    report = _validation_report(total_rows=1, processed=1)
    first_id, _ = repo.save_analysis(report, items, analytics, "first")
    second_id, _ = repo.save_analysis(report, items, analytics, "second")

    listed = repo.list_analyses()
    ids = [row["id"] for row in listed]
    assert ids.index(second_id) < ids.index(first_id)


def test_list_analyses_in_range_filters_by_date(repo, make_ticket):
    items = [make_ticket(ticket_id="1")]
    analytics = AnalyticsService().compute(items, total_uploaded=1, skipped=0)
    analysis_id, _ = repo.save_analysis(_validation_report(total_rows=1, processed=1), items, analytics, "s")

    created_at = repo.get_analysis(analysis_id)["created_at"]
    today = created_at[:10]

    in_range = repo.list_analyses_in_range(today, today)
    assert any(r["analysis_id"] == analysis_id for r in in_range)

    out_of_range = repo.list_analyses_in_range("1999-01-01", "1999-01-02")
    assert out_of_range == []


def test_get_analysis_facts_lightweight(repo, make_ticket):
    items = [make_ticket(ticket_id="1")]
    analytics = AnalyticsService().compute(items, total_uploaded=1, skipped=0)
    analysis_id, _ = repo.save_analysis(
        _validation_report(total_rows=1, processed=1), items, analytics, "facts summary"
    )

    facts = repo.get_analysis_facts(analysis_id)
    assert facts["summary"] == "facts summary"
    assert facts["processed"] == 1
    assert "items" not in facts
