"""OpenAI embeddings client: one batched call, typed errors.

Sibling to LLMService — this class owns direct contact with the embeddings
endpoint. Nothing outside services/repositories should call it directly.
"""

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from loom.services.llm_service import AuthLLMError, TransientLLMError


class EmbeddingService:
    def __init__(self, api_key: str, model: str):
        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts in one call. Raises TransientLLMError/AuthLLMError."""
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(model=self.model, input=texts)
        except AuthenticationError as exc:
            raise AuthLLMError(str(exc)) from exc
        except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as exc:
            raise TransientLLMError(str(exc)) from exc
        return [item.embedding for item in response.data]
