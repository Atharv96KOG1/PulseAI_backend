from fastapi import HTTPException

from loom.models.rag import QueryRequest
from loom.repositories.analysis_repository import AnalysisRepository
from loom.services.rag_service import NoEmbeddingsError, RagService
from loom.utils.errors import ErrorCode
from loom.views.rag import QueryResponse


class QueryController:
    """Handles POST /query: ask a free-form question about a saved analysis."""

    def __init__(self, analysis_repository: AnalysisRepository, rag_service: RagService):
        self.analysis_repository = analysis_repository
        self.rag_service = rag_service

    async def query(self, request: QueryRequest) -> QueryResponse:
        if self.analysis_repository.get_analysis(request.analysis_id) is None:
            raise HTTPException(status_code=404, detail="Analysis not found")

        try:
            return await self.rag_service.answer_question(request.analysis_id, request.question)
        except NoEmbeddingsError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": ErrorCode.ANALYSIS_NOT_INDEXED,
                    "message": "This analysis has no embeddings yet (it may predate the RAG "
                    "feature). Re-run the analysis to enable Q&A.",
                },
            ) from exc
