import io

import pandas as pd
from fastapi import BackgroundTasks, HTTPException, UploadFile

from loom.models.ticket import TicketClassification
from loom.repositories.analysis_repository import AnalysisRepository
from loom.services.analytics_service import AnalyticsService
from loom.services.classification_service import ClassificationService
from loom.services.summarization_service import SummarizationService
from loom.services.task_service import BackgroundTaskService
from loom.services.validation_service import ValidationService
from loom.utils.errors import ErrorCode, FileValidationError
from loom.views.response import AnalyzeResponse, ValidationReport


class AnalysisController:
    """Handles POST /analyze: validate → classify → aggregate → summarize → save."""

    def __init__(
        self,
        validation_service: ValidationService,
        classification_service: ClassificationService,
        analytics_service: AnalyticsService,
        summarization_service: SummarizationService,
        analysis_repository: AnalysisRepository,
        task_service: BackgroundTaskService,
        max_upload_size: int,
    ):
        self.validation_service = validation_service
        self.classification_service = classification_service
        self.analytics_service = analytics_service
        self.summarization_service = summarization_service
        self.analysis_repository = analysis_repository
        self.task_service = task_service
        self.max_upload_size = max_upload_size

    async def analyze(self, background_tasks: BackgroundTasks, file: UploadFile) -> AnalyzeResponse:
        content = await file.read()

        if len(content) > self.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail={"code": ErrorCode.EMPTY_CSV, "message": "File exceeds maximum upload size"},
            )

        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.EMPTY_CSV, "message": f"Could not parse CSV: {exc}"},
            ) from exc

        try:
            validation = self.validation_service.validate_csv(df)
        except FileValidationError as exc:
            raise HTTPException(
                status_code=400, detail={"code": exc.code, "message": exc.message}
            ) from exc

        items: list[TicketClassification] = await self.classification_service.classify_all(validation.rows)
        out_of_scope_count = sum(1 for item in items if item.is_unclassifiable())

        analytics = self.analytics_service.compute(
            items, total_uploaded=validation.total_rows, skipped=validation.skipped
        )

        validation_report = ValidationReport(
            total_rows=validation.total_rows,
            processed=len(items),
            skipped=validation.skipped,
            skip_reasons=validation.skip_reasons,
        )

        facts = self.summarization_service.build_summary_facts(
            analytics, validation_report, out_of_scope_count=out_of_scope_count
        )
        summary = await self.summarization_service.generate_executive_summary(facts)

        analysis_id, ticket_row_ids = self.analysis_repository.save_analysis(
            validation_report, items, analytics, summary
        )

        background_tasks.add_task(
            self.task_service.embed_and_save_tickets, analysis_id, items, ticket_row_ids
        )

        return AnalyzeResponse(
            analysis_id=analysis_id,
            validation_report=validation_report,
            items=items,
            analytics=analytics,
            summary=summary,
        )
