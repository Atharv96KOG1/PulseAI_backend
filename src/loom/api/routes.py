import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import Response

from loom.api.deps import (
    get_analysis_controller,
    get_analysis_record,
    get_history_controller,
    get_query_controller,
    get_report_controller,
    get_summary_controller,
)
from loom.controllers.analysis_controller import AnalysisController
from loom.controllers.history_controller import HistoryController
from loom.controllers.query_controller import QueryController
from loom.controllers.report_controller import ReportController
from loom.controllers.summary_controller import SummaryController
from loom.models.rag import QueryRequest
from loom.views.rag import QueryResponse
from loom.views.response import AnalyzeResponse, RangeSummaryResponse

logger = logging.getLogger("loom.api")

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    controller: AnalysisController = Depends(get_analysis_controller),
) -> AnalyzeResponse:
    return await controller.analyze(background_tasks, file)


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest, controller: QueryController = Depends(get_query_controller)
) -> QueryResponse:
    return await controller.query(request)


@router.get("/report/{analysis_id}")
async def report(
    analysis_id: str,
    record: dict = Depends(get_analysis_record),
    controller: ReportController = Depends(get_report_controller),
) -> Response:
    return await controller.report(analysis_id, record)


@router.get("/history")
async def history(controller: HistoryController = Depends(get_history_controller)) -> list[dict]:
    return await controller.history()


@router.get("/history/{analysis_id}")
async def history_detail(
    record: dict = Depends(get_analysis_record),
    controller: HistoryController = Depends(get_history_controller),
) -> dict:
    return await controller.history_detail(record)


@router.get("/summary/range", response_model=RangeSummaryResponse)
async def summary_for_range(
    start: str = Query(..., description="Start date, inclusive (e.g. 2026-07-01)"),
    end: str = Query(..., description="End date, inclusive (e.g. 2026-07-31)"),
    controller: SummaryController = Depends(get_summary_controller),
) -> RangeSummaryResponse:
    """A combined executive summary spanning every analysis saved within a
    date range — e.g. one narrative covering several weeks' worth of
    /analyze uploads instead of reading each one separately.
    """
    return await controller.summary_for_range(start, end)
