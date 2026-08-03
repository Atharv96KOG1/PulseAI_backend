"""Data shapes produced by ValidationService."""

from dataclasses import dataclass, field


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
