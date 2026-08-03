from collections import Counter

import pandas as pd

from loom.models.validation import RowRecord, ValidationResult
from loom.utils.errors import ErrorCode, FileValidationError
from loom.utils.text import TextInspector


class ValidationService:
    def __init__(self, long_ticket_word_limit: int):
        self.long_ticket_word_limit = long_ticket_word_limit

    @staticmethod
    def _clean_optional(value) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        return text or None

    def validate_csv(self, df: pd.DataFrame) -> ValidationResult:
        if "feedback" not in df.columns:
            raise FileValidationError(
                ErrorCode.MISSING_FEEDBACK_COLUMN, "Missing required 'feedback' column"
            )

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

            if TextInspector.contains_html(text):
                warnings.append("html")
            if TextInspector.contains_markdown(text):
                warnings.append("markdown")

            wc = TextInspector.word_count(text)
            if wc > self.long_ticket_word_limit:
                warnings.append("long")

            dedup_key = " ".join(text.split()).lower()
            if dedup_key in seen_texts:
                warnings.append("duplicate")
            else:
                seen_texts.add(dedup_key)

            ticket_id = self._clean_optional(row.get("id")) if has_id else None
            if ticket_id is None:
                ticket_id = str(idx)

            rows.append(
                RowRecord(
                    ticket_id=ticket_id,
                    raw_feedback=text,
                    source=self._clean_optional(row.get("source")) if has_source else None,
                    date=self._clean_optional(row.get("date")) if has_date else None,
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
