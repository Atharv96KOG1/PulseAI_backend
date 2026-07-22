import os

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _get_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


LLM_MODEL = os.getenv("LLM_MODEL", "")
API_KEY = os.getenv("API_KEY", "")
BATCH_SIZE = _get_int("BATCH_SIZE", 10)
MAX_CONCURRENCY = _get_int("MAX_CONCURRENCY", 5)
LONG_TICKET_WORD_LIMIT = _get_int("LONG_TICKET_WORD_LIMIT", 300)
MAX_UPLOAD_SIZE = _get_int("MAX_UPLOAD_SIZE", 10 * 1024 * 1024)
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30"))
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL") or LLM_MODEL
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
REMOVE_URLS = _get_bool("REMOVE_URLS", False)

if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is required")
if not API_KEY:
    raise RuntimeError("API_KEY environment variable is required")
