import io
import logging

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from loom.analytics.aggregate import compute_analytics, merge_analytics
from loom.api.deps import get_analysis_record, get_settings
from loom.config import Settings
from loom.db import get_analysis, list_analyses, list_analyses_in_range, save_analysis
from loom.pipeline.classify import classify_all
from loom.pipeline.summarize import build_summary_facts, generate_executive_summary
from loom.pipeline.validate import validate_csv
from loom.rag.answer import NoEmbeddingsError, answer_question
from loom.reports.pdf_report import build_weekly_report_pdf
from loom.schemas.rag import QueryRequest, QueryResponse
from loom.schemas.response import (
    AnalysisRef,
    AnalyticsResult,
    AnalyzeResponse,
    RangeSummaryResponse,
    ValidationReport,
)
from loom.schemas.ticket import is_unclassifiable
from loom.tasks import embed_and_save_tickets
from loom.utils.errors import ErrorCode, FileValidationError

logger = logging.getLogger("loom.api")

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI idiom)
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    content = await file.read()

    if len(content) > settings.MAX_UPLOAD_SIZE:
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
        validation = validate_csv(df)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    items = await classify_all(validation.rows)
    out_of_scope_count = sum(1 for item in items if is_unclassifiable(item))

    analytics = compute_analytics(items, total_uploaded=validation.total_rows, skipped=validation.skipped)

    validation_report = ValidationReport(
        total_rows=validation.total_rows,
        processed=len(items),
        skipped=validation.skipped,
        skip_reasons=validation.skip_reasons,
    )

    facts = build_summary_facts(analytics, validation_report, out_of_scope_count=out_of_scope_count)
    summary = await generate_executive_summary(facts)

    analysis_id, ticket_row_ids = save_analysis(validation_report, items, analytics, summary)

    background_tasks.add_task(embed_and_save_tickets, analysis_id, items, ticket_row_ids)

    return AnalyzeResponse(
        analysis_id=analysis_id,
        validation_report=validation_report,
        items=items,
        analytics=analytics,
        summary=summary,
    )


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    if get_analysis(request.analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        return await answer_question(request.analysis_id, request.question)
    except NoEmbeddingsError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": ErrorCode.ANALYSIS_NOT_INDEXED,
                "message": "This analysis has no embeddings yet (it may predate the RAG feature). "
                "Re-run the analysis to enable Q&A.",
            },
        ) from exc


@router.get("/report/{analysis_id}")
async def report(analysis_id: str, record: dict = Depends(get_analysis_record)) -> Response:
    pdf_bytes = build_weekly_report_pdf(record)
    filename = f"loom-weekly-report-{analysis_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history")
async def history() -> list[dict]:
    return list_analyses()


@router.get("/history/{analysis_id}")
async def history_detail(record: dict = Depends(get_analysis_record)) -> dict:
    for item in record["items"]:
        item["actionable"] = bool(item["actionable"])

    return record


@router.get("/summary/range", response_model=RangeSummaryResponse)
async def summary_for_range(
    start: str = Query(..., description="Start date, inclusive (e.g. 2026-07-01)"),
    end: str = Query(..., description="End date, inclusive (e.g. 2026-07-31)"),
) -> RangeSummaryResponse:
    """A combined executive summary spanning every analysis saved within a
    date range — e.g. one narrative covering several weeks' worth of
    /analyze uploads instead of reading each one separately.
    """
    records = list_analyses_in_range(start, end)
    if not records:
        raise HTTPException(status_code=404, detail=f"No saved analyses found between {start} and {end}")

    combined_analytics = merge_analytics([AnalyticsResult(**r["analytics"]) for r in records])

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

    facts = build_summary_facts(combined_analytics, validation_report)
    summary = await generate_executive_summary(facts)

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

