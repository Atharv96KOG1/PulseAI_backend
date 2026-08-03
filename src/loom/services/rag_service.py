import logging

from loom.prompts.rag_prompt import RagPrompt
from loom.repositories.analysis_repository import AnalysisRepository
from loom.repositories.vector_repository import VectorRepository
from loom.services.embedding_service import EmbeddingService
from loom.services.llm_service import AuthLLMError, LLMService, TransientLLMError
from loom.views.rag import QueryResponse, RetrievedTicket

logger = logging.getLogger("loom.rag_service")


class NoEmbeddingsError(Exception):
    """Raised when an analysis has no ticket embeddings yet (e.g. run before RAG was added)."""


class RagService:
    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        vector_repository: VectorRepository,
        embedding_service: EmbeddingService,
        llm_service: LLMService,
        summary_model: str,
        request_timeout: float,
        top_k: int,
    ):
        self.analysis_repository = analysis_repository
        self.vector_repository = vector_repository
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.summary_model = summary_model
        self.request_timeout = request_timeout
        self.top_k = top_k

    async def answer_question(self, analysis_id: str, question: str) -> QueryResponse:
        if not self.vector_repository.has_embeddings(analysis_id):
            raise NoEmbeddingsError(analysis_id)

        facts = self.analysis_repository.get_analysis_facts(analysis_id) or {
            "analytics": {},
            "summary": "",
            "processed": 0,
            "total_rows": 0,
        }

        [question_embedding] = await self.embedding_service.embed_texts([question])
        retrieved = self.vector_repository.search_similar_tickets(analysis_id, question_embedding, self.top_k)

        retrieved_tickets = [
            RetrievedTicket(
                ticket_id=c["ticket_id"],
                feedback_text=c["feedback_text"],
                primary_category=c["primary_category"],
                primary_theme=c["primary_theme"],
                score=score,
            )
            for c, score in retrieved
        ]

        try:
            raw = await LLMService.with_backoff(
                lambda: self.llm_service.complete_text(
                    model=self.summary_model,
                    system_prompt=RagPrompt.SYSTEM_PROMPT,
                    user_prompt=RagPrompt.build_user_prompt(question, [c for c, _ in retrieved], facts),
                    timeout=self.request_timeout,
                )
            )
            answer = raw.strip() or "The model returned an empty answer for this question."
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error("RAG answer generation failed for analysis %s (%s)", analysis_id, exc)
            answer = "Unable to generate an answer right now; please retry."

        return QueryResponse(answer=answer, retrieved_tickets=retrieved_tickets)
