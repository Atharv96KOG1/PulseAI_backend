"""Shared error codes and exception types used across the pipeline and API."""


class ErrorCode:
    MISSING_FEEDBACK_COLUMN = 4001
    EMPTY_CSV = 4002
    NO_VALID_FEEDBACK = 4003
    INVALID_LLM_RESPONSE = 4004
    ANALYSIS_NOT_INDEXED = 4005
    AI_PROVIDER_UNAVAILABLE = 5001


class FileValidationError(Exception):
    """Raised for file-level validation failures that must reject the upload."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
