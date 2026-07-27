"""Pydantic models for the /query (RAG) endpoint."""

from pydantic import BaseModel


class QueryRequest(BaseModel):
    analysis_id: str
    question: str


class RetrievedTicket(BaseModel):
    ticket_id: str
    feedback_text: str
    primary_category: str
    primary_theme: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    retrieved_tickets: list[RetrievedTicket]
