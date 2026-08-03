from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from loom import config
from loom.utils.errors import ErrorCode, FileValidationError
from loom.utils.text import contains_html, contains_markdown, word_count


@dataclass
class RowRecord:
    ticket_id: str
    raw_feedback: str
    source: str | None
    date: str | None
    word_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    rows: list[RowRecord]
    total_rows: int
    skipped: int
    skip_reasons: dict[str, int]


def _clean_optional(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def validate_csv(df: pd.DataFrame) -> ValidationResult:
    if "feedback" not in df.columns:
        raise FileValidationError(ErrorCode.MISSING_FEEDBACK_COLUMN, "Missing required 'feedback' column")

    total_rows = len(df)
    if total_rows == 0:
        raise FileValidationError(ErrorCode.EMPTY_CSV, "CSV file has no data rows")

    has_id = "id" in df.columns
    has_source = "source" in df.columns
    has_date = "date" in df.columns

    rows: list[RowRecord] = []
    skip_reasons: Counter[str] = Counter()
    seen_texts: set[str] = set()

    for idx, row in df.iterrows():
        raw = row.get("feedback")
        if raw is None or (isinstance(raw, float) and pd.isna(raw)) or not str(raw).strip():
            skip_reasons["empty_or_null_feedback"] += 1
            continue

        text = str(raw)
        warnings: list[str] = []

        if contains_html(text):
            warnings.append("html")
        if contains_markdown(text):
            warnings.append("markdown")

        wc = word_count(text)
        if wc > config.LONG_TICKET_WORD_LIMIT:
            warnings.append("long")

        dedup_key = " ".join(text.split()).lower()
        if dedup_key in seen_texts:
            warnings.append("duplicate")
        else:
            seen_texts.add(dedup_key)

        ticket_id = _clean_optional(row.get("id")) if has_id else None
        if ticket_id is None:
            ticket_id = str(idx)

        rows.append(
            RowRecord(
                ticket_id=ticket_id,
                raw_feedback=text,
                source=_clean_optional(row.get("source")) if has_source else None,
                date=_clean_optional(row.get("date")) if has_date else None,
                word_count=wc,
                warnings=warnings,
            )
        )

    if not rows:
        raise FileValidationError(
            ErrorCode.NO_VALID_FEEDBACK, "No valid feedback rows found after row validation"
        )

    return ValidationResult(
        rows=rows,
        total_rows=total_rows,
        skipped=sum(skip_reasons.values()),
        skip_reasons=dict(skip_reasons),
    )
