"""Helpers shared by the MCP tool layer and the REST adapter."""
from __future__ import annotations

from ..config import settings
from ..state.models import FinalAnswer
from .types import AnswerDict


def answer_to_dict(ans: FinalAnswer) -> AnswerDict:
    """Serialize a FinalAnswer into the stable MCP/REST contract."""
    return {
        "question": ans.question,
        "answer": ans.answer,
        "status": ans.status.value,
        "needs_human_review": ans.needs_human_review,
        "confidence": round(ans.confidence, 3),
        "citations": [
            {
                "document_id": c.document_id,
                "section": c.section,
                "version": c.version,
                "effective_date": c.effective_date.isoformat() if c.effective_date else None,
                "scope": c.scope,
                "url": c.sharepoint_url,
            }
            for c in ans.citations
        ],
        "notes": ans.notes,
    }


def check_api_key(provided: str | None) -> bool:
    """True if the request key matches SIG_API_KEY (or no key is configured)."""
    expected = settings.api_key
    return (not expected) or provided == expected
