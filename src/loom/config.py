from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_MODEL: str = ""
    API_KEY: str = ""
    BATCH_SIZE: int = 10
    MAX_CONCURRENCY: int = 5
    LONG_TICKET_WORD_LIMIT: int = 300
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024
    REQUEST_TIMEOUT: float = 30.0
    SUMMARY_MODEL: str = ""
    LOG_LEVEL: str = "INFO"
    REMOVE_URLS: bool = False
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    RAG_TOP_K: int = 8
    PG_DSN: str = "postgresql://localhost:5544/loom_vectors"

    @model_validator(mode="after")
    def _defaults_and_required(self) -> "Settings":
        if not self.SUMMARY_MODEL:
            self.SUMMARY_MODEL = self.LLM_MODEL
        if not self.LLM_MODEL:
            raise RuntimeError("LLM_MODEL environment variable is required")
        if not self.API_KEY:
            raise RuntimeError("API_KEY environment variable is required")
        return self


_settings = Settings()

LLM_MODEL = _settings.LLM_MODEL
API_KEY = _settings.API_KEY
BATCH_SIZE = _settings.BATCH_SIZE
MAX_CONCURRENCY = _settings.MAX_CONCURRENCY
LONG_TICKET_WORD_LIMIT = _settings.LONG_TICKET_WORD_LIMIT
MAX_UPLOAD_SIZE = _settings.MAX_UPLOAD_SIZE
REQUEST_TIMEOUT = _settings.REQUEST_TIMEOUT
SUMMARY_MODEL = _settings.SUMMARY_MODEL
LOG_LEVEL = _settings.LOG_LEVEL
REMOVE_URLS = _settings.REMOVE_URLS
EMBEDDING_MODEL = _settings.EMBEDDING_MODEL
EMBEDDING_DIMENSIONS = _settings.EMBEDDING_DIMENSIONS
RAG_TOP_K = _settings.RAG_TOP_K
PG_DSN = _settings.PG_DSN
