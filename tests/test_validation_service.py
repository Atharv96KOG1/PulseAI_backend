import pandas as pd
import pytest

from loom.services.validation_service import ValidationService
from loom.utils.errors import ErrorCode, FileValidationError


@pytest.fixture
def service() -> ValidationService:
    return ValidationService(long_ticket_word_limit=5)


def test_missing_feedback_column_raises(service):
    df = pd.DataFrame({"other": ["x"]})
    with pytest.raises(FileValidationError) as exc_info:
        service.validate_csv(df)
    assert exc_info.value.code == ErrorCode.MISSING_FEEDBACK_COLUMN


def test_empty_csv_raises(service):
    df = pd.DataFrame({"feedback": []})
    with pytest.raises(FileValidationError) as exc_info:
        service.validate_csv(df)
    assert exc_info.value.code == ErrorCode.EMPTY_CSV


def test_all_rows_blank_raises_no_valid_feedback(service):
    df = pd.DataFrame({"feedback": ["", None, "   "]})
    with pytest.raises(FileValidationError) as exc_info:
        service.validate_csv(df)
    assert exc_info.value.code == ErrorCode.NO_VALID_FEEDBACK


def test_blank_rows_are_skipped_not_fatal(service):
    df = pd.DataFrame({"feedback": ["real feedback here", "", None]})
    result = service.validate_csv(df)
    assert result.total_rows == 3
    assert result.skipped == 2
    assert result.skip_reasons["empty_or_null_feedback"] == 2
    assert len(result.rows) == 1


def test_row_ids_default_to_row_index_when_no_id_column(service):
    df = pd.DataFrame({"feedback": ["a", "b"]})
    result = service.validate_csv(df)
    assert [row.ticket_id for row in result.rows] == ["0", "1"]


def test_explicit_id_column_used_when_present(service):
    df = pd.DataFrame({"id": ["A1", "A2"], "feedback": ["a", "b"]})
    result = service.validate_csv(df)
    assert [row.ticket_id for row in result.rows] == ["A1", "A2"]


def test_duplicate_feedback_flagged_but_kept(service):
    df = pd.DataFrame({"feedback": ["same text", "same text"]})
    result = service.validate_csv(df)
    assert len(result.rows) == 2
    assert "duplicate" in result.rows[1].warnings
    assert "duplicate" not in result.rows[0].warnings


def test_long_ticket_flagged_over_word_limit(service):
    long_text = " ".join(["word"] * 10)  # limit is 5
    df = pd.DataFrame({"feedback": [long_text]})
    result = service.validate_csv(df)
    assert "long" in result.rows[0].warnings


def test_short_ticket_not_flagged_long(service):
    df = pd.DataFrame({"feedback": ["short text"]})
    result = service.validate_csv(df)
    assert "long" not in result.rows[0].warnings
