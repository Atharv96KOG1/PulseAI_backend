"""Postgres + pgvector-backed embedding store for RAG.

This is the hybrid half of the persistence split: `db.py` (SQLite) still owns
`analysis`/`ticket`/`additional_issue` — the classification data. This module
owns only `ticket_embedding` and is the sole place cosine-similarity search
happens. Unlike the SQLite+numpy approach it replaces, ranking runs *inside
the database* via pgvector's `<=>` operator, backed by an HNSW index — this
is what makes it a real vector database rather than a BLOB column with an
application-side linear scan.

Rows are denormalized (ticket_id, analysis_id, feedback_text, category, theme
all live directly on this table) because this is a separate database from
`db.py`'s SQLite file — there is no cross-database JOIN to lean on.
"""

from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from loom import config


def _schema() -> str:
    # VECTOR(N) fixes the column's dimensionality at creation time, so it
    # must match config.EMBEDDING_MODEL's actual output width exactly.
    return f"""
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS ticket_embedding (
        ticket_id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        feedback_text TEXT NOT NULL,
        primary_category TEXT NOT NULL,
        primary_theme TEXT NOT NULL,
        embedding VECTOR({config.EMBEDDING_DIMENSIONS}) NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_ticket_embedding_analysis_id ON ticket_embedding (analysis_id);

    CREATE INDEX IF NOT EXISTS idx_ticket_embedding_hnsw
        ON ticket_embedding USING hnsw (embedding vector_cosine_ops);
    """


@contextmanager
def get_connection():
    conn = psycopg.connect(config.PG_DSN, autocommit=True)
    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()


def init_vector_db() -> None:
    with get_connection() as conn:
        conn.execute(_schema())


def save_ticket_embeddings(rows: list[dict]) -> None:
    """Persist one embedding row per ticket. Each dict needs: ticket_id,
    analysis_id, feedback_text, primary_category, primary_theme, embedding
    (list[float]). Re-running for the same ticket_id overwrites the vector —
    a batch can safely be re-embedded after a partial failure.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.cursor().executemany(
            """
            INSERT INTO ticket_embedding
                (ticket_id, analysis_id, feedback_text, primary_category, primary_theme, embedding)
            VALUES (%(ticket_id)s, %(analysis_id)s, %(feedback_text)s,
                    %(primary_category)s, %(primary_theme)s, %(embedding)s)
            ON CONFLICT (ticket_id) DO UPDATE SET
                feedback_text = EXCLUDED.feedback_text,
                primary_category = EXCLUDED.primary_category,
                primary_theme = EXCLUDED.primary_theme,
                embedding = EXCLUDED.embedding
            """,
            rows,
        )


def has_embeddings(analysis_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM ticket_embedding WHERE analysis_id = %s LIMIT 1", (analysis_id,)
        ).fetchone()
    return row is not None


def search_similar_tickets(
    analysis_id: str, query_embedding: list[float], k: int
) -> list[tuple[dict, float]]:
    """Top-k cosine-similarity search, ranked entirely in SQL.

    `embedding <=> %s` is pgvector's cosine *distance* (0 = identical,
    2 = opposite); `1 - distance` converts it back to a 0..1 similarity
    score, matching what RetrievedTicket.score / the Ask panel's "% match"
    have always expected — the storage swap changes nothing downstream.

    The query vector needs an explicit `::vector` cast: psycopg adapts a
    plain Python list as a generic array, and `<=>` isn't defined between
    `vector` and `double precision[]`. The INSERT above doesn't need this —
    assigning into a `VECTOR(N)` column casts implicitly.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticket_id, feedback_text, primary_category, primary_theme,
                   1 - (embedding <=> %(query)s::vector) AS score
            FROM ticket_embedding
            WHERE analysis_id = %(analysis_id)s
            ORDER BY embedding <=> %(query)s::vector
            LIMIT %(k)s
            """,
            {"query": query_embedding, "analysis_id": analysis_id, "k": k},
        ).fetchall()

    return [
        (
            {
                "ticket_id": row[0],
                "feedback_text": row[1],
                "primary_category": row[2],
                "primary_theme": row[3],
            },
            float(row[4]),
        )
        for row in rows
    ]
