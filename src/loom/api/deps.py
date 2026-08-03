from functools import lru_cache

from fastapi import HTTPException, Path

from loom.config import Settings
from loom.controllers.analysis_controller import AnalysisController
from loom.controllers.history_controller import HistoryController
from loom.controllers.query_controller import QueryController
from loom.controllers.report_controller import ReportController
from loom.controllers.summary_controller import SummaryController
from loom.repositories.analysis_repository import AnalysisRepository
from loom.repositories.vector_repository import VectorRepository
from loom.services.analytics_service import AnalyticsService
from loom.services.classification_service import ClassificationService
from loom.services.embedding_service import EmbeddingService
from loom.services.llm_service import LLMService
from loom.services.rag_service import RagService
from loom.services.report_service import ReportService
from loom.services.summarization_service import SummarizationService
from loom.services.task_service import BackgroundTaskService
from loom.services.text_preprocessing_service import TextPreprocessingService
from loom.services.validation_service import ValidationService


class Container:
    """The app's whole dependency graph, wired once."""

    def __init__(self):
        self.settings = Settings()

        # Repositories
        self.analysis_repository = AnalysisRepository()
        self.vector_repository = VectorRepository(
            dsn=self.settings.PG_DSN, embedding_dimensions=self.settings.EMBEDDING_DIMENSIONS
        )

        # Low-level services
        self.llm_service = LLMService(api_key=self.settings.API_KEY)
        self.embedding_service = EmbeddingService(
            api_key=self.settings.API_KEY, model=self.settings.EMBEDDING_MODEL
        )
        self.text_preprocessing_service = TextPreprocessingService()

        # Business services
        self.validation_service = ValidationService(
            long_ticket_word_limit=self.settings.LONG_TICKET_WORD_LIMIT
        )
        self.summarization_service = SummarizationService(
            llm_service=self.llm_service,
            model=self.settings.LLM_MODEL,
            summary_model=self.settings.SUMMARY_MODEL,
            request_timeout=self.settings.REQUEST_TIMEOUT,
        )
        self.classification_service = ClassificationService(
            llm_service=self.llm_service,
            summarization_service=self.summarization_service,
            preprocessor=self.text_preprocessing_service,
            model=self.settings.LLM_MODEL,
            max_concurrency=self.settings.MAX_CONCURRENCY,
            long_ticket_word_limit=self.settings.LONG_TICKET_WORD_LIMIT,
            request_timeout=self.settings.REQUEST_TIMEOUT,
            remove_urls=self.settings.REMOVE_URLS,
        )
        self.analytics_service = AnalyticsService()
        self.report_service = ReportService()
        self.task_service = BackgroundTaskService(
            embedding_service=self.embedding_service, vector_repository=self.vector_repository
        )
        self.rag_service = RagService(
            analysis_repository=self.analysis_repository,
            vector_repository=self.vector_repository,
            embedding_service=self.embedding_service,
            llm_service=self.llm_service,
            summary_model=self.settings.SUMMARY_MODEL,
            request_timeout=self.settings.REQUEST_TIMEOUT,
            top_k=self.settings.RAG_TOP_K,
        )

        # Controllers
        self.analysis_controller = AnalysisController(
            validation_service=self.validation_service,
            classification_service=self.classification_service,
            analytics_service=self.analytics_service,
            summarization_service=self.summarization_service,
            analysis_repository=self.analysis_repository,
            task_service=self.task_service,
            max_upload_size=self.settings.MAX_UPLOAD_SIZE,
        )
        self.query_controller = QueryController(
            analysis_repository=self.analysis_repository, rag_service=self.rag_service
        )
        self.report_controller = ReportController(report_service=self.report_service)
        self.history_controller = HistoryController(analysis_repository=self.analysis_repository)
        self.summary_controller = SummaryController(
            analysis_repository=self.analysis_repository,
            analytics_service=self.analytics_service,
            summarization_service=self.summarization_service,
        )


container = Container()

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return container.settings


def get_analysis_repository() -> AnalysisRepository:
    return container.analysis_repository


def get_analysis_record(
    analysis_id: str = Path(...),
) -> dict:
    record = container.analysis_repository.get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return record


def get_analysis_controller() -> AnalysisController:
    return container.analysis_controller


def get_query_controller() -> QueryController:
    return container.query_controller


def get_report_controller() -> ReportController:
    return container.report_controller


def get_history_controller() -> HistoryController:
    return container.history_controller


def get_summary_controller() -> SummaryController:
    return container.summary_controller


def get_validation_service() -> ValidationService:
    return container.validation_service


def get_classification_service() -> ClassificationService:
    return container.classification_service


def get_analytics_service() -> AnalyticsService:
    return container.analytics_service


def get_summarization_service() -> SummarizationService:
    return container.summarization_service


def get_vector_repository() -> VectorRepository:
    return container.vector_repository
