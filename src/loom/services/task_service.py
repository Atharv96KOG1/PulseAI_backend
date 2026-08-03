import logging

from loom.models.ticket import TicketClassification
from loom.repositories.vector_repository import VectorRepository
from loom.services.embedding_service import EmbeddingService
from loom.services.llm_service import AuthLLMError, TransientLLMError

logger = logging.getLogger("loom.task_service")


class BackgroundTaskService:
    """Work scheduled to run after a response has already been sent back to
    the client, so the caller never waits on it.
    """

    def __init__(self, embedding_service: EmbeddingService, vector_repository: VectorRepository):
        self.embedding_service = embedding_service
        self.vector_repository = vector_repository

    async def embed_and_save_tickets(
        self, analysis_id: str, items: list[TicketClassification], ticket_row_ids: list[str]
    ) -> None:
        """Embed every ticket from one analysis and persist the vectors for RAG.
        Runs after /analyze has already responded — a failure here only means
        /query is unavailable for this analysis, never that /analyze itself failed.
        """
        try:
            embed_inputs = [
                f"{item.feedback_text}\n"
                f"Category: {item.primary_category.value} | Theme: {item.primary_theme.value}"
                for item in items
            ]
            vectors = await self.embedding_service.embed_texts(embed_inputs)
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
            self.vector_repository.save_ticket_embeddings(rows)
        except (AuthLLMError, TransientLLMError) as exc:
            logger.error(
                "Ticket embedding failed for analysis %s (%s); /query will be unavailable", analysis_id, exc
            )
