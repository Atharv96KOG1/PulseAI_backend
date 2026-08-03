from fastapi.responses import Response

from loom.services.report_service import ReportService


class ReportController:
    """Handles GET /report/{analysis_id}: render one saved analysis as a PDF."""

    def __init__(self, report_service: ReportService):
        self.report_service = report_service

    async def report(self, analysis_id: str, record: dict) -> Response:
        pdf_bytes = self.report_service.build_weekly_report_pdf(record)
        filename = f"loom-weekly-report-{analysis_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
