from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector


class VectorRepository:
    """All reads/writes against the `ticket_embedding` table."""

    def __init__(self, dsn: str, embedding_dimensions: int):
        self.dsn = dsn
        self.embedding_dimensions = embedding_dimensions

    def _schema(self) -> str:
        # VECTOR(N) fixes the column's dimensionality at creation time, so it
        # must match the embedding model's actual output width exactly.
        return f"""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS ticket_embedding (
            ticket_id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            feedback_text TEXT NOT NULL,
            primary_category TEXT NOT NULL,
            primary_theme TEXT NOT NULL,
            embedding VECTOR({self.embedding_dimensions}) NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ticket_embedding_analysis_id ON ticket_embedding (analysis_id);

        CREATE INDEX IF NOT EXISTS idx_ticket_embedding_hnsw
            ON ticket_embedding USING hnsw (embedding vector_cosine_ops);
        """

    @contextmanager
    def _connection(self):
        conn = psycopg.connect(self.dsn, autocommit=True)
        register_vector(conn)
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(self._schema())

    def save_ticket_embeddings(self, rows: list[dict]) -> None:
        """Persist one embedding row per ticket. Each dict needs: ticket_id,
        analysis_id, feedback_text, primary_category, primary_theme, embedding
        (list[float]). Re-running for the same ticket_id overwrites the vector —
        a batch can safely be re-embedded after a partial failure.
        """
        if not rows:
            return
        with self._connection() as conn:
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

    def has_embeddings(self, analysis_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM ticket_embedding WHERE analysis_id = %s LIMIT 1", (analysis_id,)
            ).fetchone()
        return row is not None

    def search_similar_tickets(
        self, analysis_id: str, query_embedding: list[float], k: int
    ) -> list[tuple[dict, float]]:
        """Top-k cosine-similarity search, ranked entirely in SQL.

        `embedding <=> %s` is pgvector's cosine *distance* (0 = identical,
        2 = opposite); `1 - distance` converts it back to a 0..1 similarity
        score, matching what RetrievedTicket.score / the Ask panel's "% match"
        have always expected.

        The query vector needs an explicit `::vector` cast: psycopg adapts a
        plain Python list as a generic array, and `<=>` isn't defined between
        `vector` and `double precision[]`. The INSERT above doesn't need this —
        assigning into a `VECTOR(N)` column casts implicitly.
        """
        with self._connection() as conn:
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
