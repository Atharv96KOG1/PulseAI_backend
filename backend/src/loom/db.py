import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

DB_PATH = "loom.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    total_rows INTEGER NOT NULL,
    processed INTEGER NOT NULL,
    skipped INTEGER NOT NULL,
    skip_reasons TEXT NOT NULL,
    summary TEXT NOT NULL,
    analytics TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(id) ON DELETE CASCADE,
    ticket_id TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    primary_category TEXT NOT NULL,
    primary_theme TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    urgency TEXT NOT NULL,
    actionable INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS additional_issue (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL REFERENCES ticket(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    theme TEXT NOT NULL,
    urgency TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticket_analysis_id ON ticket(analysis_id);
CREATE INDEX IF NOT EXISTS idx_issue_ticket_id ON additional_issue(ticket_id);
"""


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db_connection() as conn:
        conn.executescript(SCHEMA)


def save_analysis(validation_report, items, analytics, summary) -> tuple[str, list[str]]:
    """Persist an analysis run. Returns (analysis_id, ticket_row_ids) — the row ids
    are aligned with `items` order and are the keys embeddings attach to.
    """
    analysis_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()
    ticket_row_ids = []

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO analysis (
                id, created_at, total_rows, processed, skipped, skip_reasons, summary, analytics
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                created_at,
                validation_report.total_rows,
                validation_report.processed,
                validation_report.skipped,
                json.dumps(validation_report.skip_reasons),
                summary,
                analytics.model_dump_json(),
            ),
        )

        for item in items:
            ticket_row_id = str(uuid.uuid4())
            ticket_row_ids.append(ticket_row_id)
            conn.execute(
                """
                INSERT INTO ticket (
                    id, analysis_id, ticket_id, feedback_text, primary_category,
                    primary_theme, sentiment, sentiment_score, urgency, actionable
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_row_id,
                    analysis_id,
                    item.ticket_id,
                    item.feedback_text,
                    item.primary_category.value,
                    item.primary_theme.value,
                    item.sentiment.value,
                    item.sentiment_score,
                    item.urgency.value,
                    int(item.actionable),
                ),
            )

            for issue in item.additional_issues:
                conn.execute(
                    """
                    INSERT INTO additional_issue (id, ticket_id, category, theme, urgency)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        ticket_row_id,
                        issue.category.value,
                        issue.theme.value,
                        issue.urgency.value,
                    ),
                )

    return analysis_id, ticket_row_ids


def get_analysis_facts(analysis_id: str) -> dict | None:
    """Lightweight fetch of an analysis's aggregate facts only (no ticket rows).
    Grounds RAG answers in the full dashboard analytics, not just the
    semantically retrieved excerpts, without the cost of joining every ticket.
    """
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT created_at, total_rows, processed, skipped, summary, analytics
            FROM analysis WHERE id = ?
            """,
            (analysis_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "created_at": row["created_at"],
        "total_rows": row["total_rows"],
        "processed": row["processed"],
        "skipped": row["skipped"],
        "summary": row["summary"],
        "analytics": json.loads(row["analytics"]),
    }


def get_analysis(analysis_id: str) -> dict | None:
    with get_db_connection() as conn:
        analysis_row = conn.execute("SELECT * FROM analysis WHERE id = ?", (analysis_id,)).fetchone()
        if analysis_row is None:
            return None

        ticket_rows = conn.execute("SELECT * FROM ticket WHERE analysis_id = ?", (analysis_id,)).fetchall()

        tickets = []
        for ticket_row in ticket_rows:
            issue_rows = conn.execute(
                "SELECT category, theme, urgency FROM additional_issue WHERE ticket_id = ?",
                (ticket_row["id"],),
            ).fetchall()
            tickets.append({**dict(ticket_row), "additional_issues": [dict(r) for r in issue_rows]})

        return {
            "analysis_id": analysis_row["id"],
            "created_at": analysis_row["created_at"],
            "validation_report": {
                "total_rows": analysis_row["total_rows"],
                "processed": analysis_row["processed"],
                "skipped": analysis_row["skipped"],
                "skip_reasons": json.loads(analysis_row["skip_reasons"]),
            },
            "analytics": json.loads(analysis_row["analytics"]),
            "summary": analysis_row["summary"],
            "items": tickets,
        }


def list_analyses() -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, created_at, total_rows, processed, skipped FROM analysis ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
