"""Shared MCP response types (the tool I/O contract)."""
from __future__ import annotations

from typing import TypedDict


class CitationDict(TypedDict):
    document_id: str
    section: str
    version: str
    effective_date: str | None
    scope: str
    url: str


class AnswerDict(TypedDict):
    question: str
    answer: str
    status: str               # validated_from_history | synthesized_new | escalated
    needs_human_review: bool
    confidence: float
    citations: list[CitationDict]
    notes: str
