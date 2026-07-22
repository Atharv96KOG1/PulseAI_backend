import io
import logging

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

import config
from analytics.aggregate import compute_analytics
from pipeline.classify import classify_all
from pipeline.summarize import build_summary_facts, generate_executive_summary
from pipeline.validate import validate_csv
from schemas.response import AnalyzeResponse, ValidationReport
from utils.errors import ErrorCode, FileValidationError

logger = logging.getLogger("loom.api")

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> AnalyzeResponse:  # noqa: B008 (FastAPI idiom)
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

    return AnalyzeResponse(
        validation_report=validation_report,
        items=items,
        analytics=analytics,
        summary=summary,
    )
