import logging

from loom import config
from loom.db import get_analysis_facts
from loom.prompts.rag_prompt import RAG_SYSTEM_PROMPT, build_user_prompt
from loom.rag.vector_store import has_embeddings, search_similar_tickets
from loom.schemas.rag import QueryResponse, RetrievedTicket
from loom.services.embeddings_client import embed_texts
from loom.services.llm_client import AuthLLMError, TransientLLMError, complete_text, with_backoff

logger = logging.getLogger("loom.rag")


class NoEmbeddingsError(Exception):
    """Raised when an analysis has no ticket embeddings yet (e.g. run before RAG was added)."""


async def answer_question(analysis_id: str, question: str) -> QueryResponse:
    if not has_embeddings(analysis_id):
        raise NoEmbeddingsError(analysis_id)

    facts = get_analysis_facts(analysis_id) or {
        "analytics": {},
        "summary": "",
        "processed": 0,
        "total_rows": 0,
    }

    [question_embedding] = await embed_texts([question])
    retrieved = search_similar_tickets(analysis_id, question_embedding, config.RAG_TOP_K)

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
        raw = await with_backoff(
            lambda: complete_text(
                model=config.SUMMARY_MODEL,
                system_prompt=RAG_SYSTEM_PROMPT,
                user_prompt=build_user_prompt(question, [c for c, _ in retrieved], facts),
                timeout=config.REQUEST_TIMEOUT,
            )
        )
        answer = raw.strip() or "The model returned an empty answer for this question."
    except (AuthLLMError, TransientLLMError) as exc:
        logger.error("RAG answer generation failed for analysis %s (%s)", analysis_id, exc)
        answer = "Unable to generate an answer right now; please retry."

    return QueryResponse(answer=answer, retrieved_tickets=retrieved_tickets)
