"""Request model for the /query (RAG) endpoint."""

from pydantic import BaseModel


class QueryRequest(BaseModel):
    analysis_id: str
    question: str
