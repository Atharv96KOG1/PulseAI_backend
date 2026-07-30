"""Background tasks scheduled via FastAPI's BackgroundTasks — work that runs
after a response has already been sent back to the client, so the caller
never waits on it.
"""

import logging

from loom.rag.vector_store import save_ticket_embeddings
from loom.schemas.ticket import TicketClassification
from loom.services.embeddings_client import embed_texts
from loom.services.llm_client import AuthLLMError, TransientLLMError

logger = logging.getLogger("loom.tasks")


async def embed_and_save_tickets(
    analysis_id: str, items: list[TicketClassification], ticket_row_ids: list[str]
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
