"""The single stateless /analyze endpoint. Orchestrates the pipeline stages;
contains no business logic of its own.
"""

import io
import logging

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response

from loom import config
from loom.analytics.aggregate import compute_analytics
from loom.db import get_analysis, list_analyses, save_analysis
from loom.pipeline.classify import classify_all
from loom.pipeline.summarize import build_summary_facts, generate_executive_summary
from loom.pipeline.validate import validate_csv
from loom.rag.answer import NoEmbeddingsError, answer_question
from loom.rag.vector_store import save_ticket_embeddings
from loom.reports.pdf_report import build_weekly_report_pdf
from loom.schemas.rag import QueryRequest, QueryResponse
from loom.schemas.response import AnalyzeResponse, ValidationReport
from loom.services.embeddings_client import embed_texts
from loom.services.llm_client import AuthLLMError, TransientLLMError
from loom.utils.errors import ErrorCode, FileValidationError

logger = logging.getLogger("loom.api")

router = APIRouter()


async def _embed_and_save_tickets(analysis_id: str, items: list, ticket_row_ids: list) -> None:
    try:
        embed_inputs = [
            f"{item.feedback_text}\n"
            f"Category: {item.primary_category.value} | Theme: {item.primary_theme.value}"
            for item in items
        ]
        vectors = await embed_texts(embed_inputs)
        rows = [
            {
                "ticket_id": ticket_row_id,
                "analysis_id": analysis_id,
                "feedback_text": item.feedback_text,
                "primary_category": item.primary_category.value,
                "primary_theme": item.primary_theme.value,
                "embedding": vector,
            }
            for ticket_row_id, item, vector in zip(ticket_row_ids, items, vectors, strict=True)
        ]
        save_ticket_embeddings(rows)
    except (AuthLLMError, TransientLLMError) as exc:
        logger.error(
            "Ticket embedding failed for analysis %s (%s); /query will be unavailable", analysis_id, exc
        )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)  # noqa: B008 (FastAPI idiom)
) -> AnalyzeResponse:
    content = await file.read()

    if len(content) > config.MAX_UPLOAD_SIZE:
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
    analytics = compute_analytics(items, total_uploaded=validation.total_rows, skipped=validation.skipped)

    validation_report = ValidationReport(
        total_rows=validation.total_rows,
        processed=len(items),
        skipped=validation.skipped,
        skip_reasons=validation.skip_reasons,
    )

    facts = build_summary_facts(analytics, validation_report)
    summary = await generate_executive_summary(facts)

    analysis_id, ticket_row_ids = save_analysis(validation_report, items, analytics, summary)

    background_tasks.add_task(_embed_and_save_tickets, analysis_id, items, ticket_row_ids)

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
async def report(analysis_id: str) -> Response:
    record = get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

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
async def history_detail(analysis_id: str) -> dict:
    record = get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    for item in record["items"]:
        item["actionable"] = bool(item["actionable"])

    return record
