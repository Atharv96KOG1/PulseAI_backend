from fastapi import HTTPException

from loom.repositories.analysis_repository import AnalysisRepository
from loom.services.analytics_service import AnalyticsService
from loom.services.summarization_service import SummarizationService
from loom.views.response import AnalysisRef, AnalyticsResult, RangeSummaryResponse, ValidationReport


class SummaryController:
    """Handles GET /summary/range: one combined executive summary spanning
    every analysis saved within a date range.
    """

    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        analytics_service: AnalyticsService,
        summarization_service: SummarizationService,
    ):
        self.analysis_repository = analysis_repository
        self.analytics_service = analytics_service
        self.summarization_service = summarization_service

    async def summary_for_range(self, start: str, end: str) -> RangeSummaryResponse:
        records = self.analysis_repository.list_analyses_in_range(start, end)
        if not records:
            raise HTTPException(status_code=404, detail=f"No saved analyses found between {start} and {end}")

        combined_analytics = self.analytics_service.merge(
            [AnalyticsResult(**r["analytics"]) for r in records]
        )

        skip_reasons: dict[str, int] = {}
        for record in records:
            for reason, count in record["skip_reasons"].items():
                skip_reasons[reason] = skip_reasons.get(reason, 0) + count

        validation_report = ValidationReport(
            total_rows=sum(record["total_rows"] for record in records),
            processed=combined_analytics.total_processed,
            skipped=combined_analytics.total_skipped,
            skip_reasons=skip_reasons,
        )

        facts = self.summarization_service.build_summary_facts(combined_analytics, validation_report)
        summary = await self.summarization_service.generate_executive_summary(facts)

        return RangeSummaryResponse(
            start=start,
            end=end,
            analyses_included=[
                AnalysisRef(analysis_id=record["analysis_id"], created_at=record["created_at"])
                for record in records
            ],
            validation_report=validation_report,
            analytics=combined_analytics,
            summary=summary,
        )
