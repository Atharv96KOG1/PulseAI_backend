"""OpenAI embeddings client wrapper: one batched call, typed errors.

Sibling to llm_client.py — this module owns direct contact with the
embeddings endpoint. Nothing outside `rag/` should call this directly.
"""

from functools import lru_cache

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from loom import config
from loom.services.llm_client import AuthLLMError, TransientLLMError


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=config.API_KEY)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts in one call. Raises TransientLLMError/AuthLLMError."""
    if not texts:
        return []
    try:
        response = await _client().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    except AuthenticationError as exc:
        raise AuthLLMError(str(exc)) from exc
    except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc:
        raise TransientLLMError(str(exc)) from exc
    return [item.embedding for item in response.data]
