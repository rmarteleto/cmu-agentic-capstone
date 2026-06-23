"""Retriever agent — thin agent wrapper around the HybridRetriever.

Owns the retrieval handoff (one-way communication downstream): it returns the
top-B SOP passages and SIG candidates plus whether the relevance gate was met.
"""
from __future__ import annotations

from ..retrieval import HybridRetriever, RetrievalResult


class RetrieverAgent:
    def __init__(self, retriever: HybridRetriever | None = None):
        self.retriever = retriever or HybridRetriever()

    def fetch(self, question: str) -> RetrievalResult:
        return self.retriever.retrieve(question)
