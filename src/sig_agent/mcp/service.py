"""Service layer: one Orchestrator instance + the tool-facing functions.

The MCP tool registrations (setup.py) and the REST adapter (rest_api.py) both
call into here, so behaviour is identical across transports.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import settings
from ..orchestration import Orchestrator
from ..state.models import QuestionTask
from .utils import answer_to_dict
from .types import AnswerDict


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    """Lazily build a single Orchestrator (agents + clients are reused)."""
    return Orchestrator(max_workers=settings.max_workers)


def answer_question(question: str) -> AnswerDict:
    """Answer one SIG question through the full multi-agent pipeline."""
    return answer_to_dict(get_orchestrator().answer_question(question))


def answer_batch(questions: list[str]) -> list[AnswerDict]:
    """Answer many questions (parallel fan-out inside the Orchestrator)."""
    tasks = [QuestionTask(question=q, row_index=i + 2) for i, q in enumerate(questions)]
    answers = get_orchestrator().answer_questionnaire(tasks)
    return [answer_to_dict(a) for a in answers]


def retrieve(question: str) -> dict:
    """Run only dual-corpus hybrid retrieval (for the retriever subagent)."""
    result = get_orchestrator().retriever.fetch(question)
    return {
        "question": question,
        "is_match": result.is_match,
        "max_relevance": round(result.max_relevance, 3),
        "sop_passages": [
            {"document_id": p.provenance.document_id, "section": p.provenance.section,
             "score": round(p.score, 3), "text": p.text[:500]}
            for p in result.sop_passages
        ],
        "sig_candidates": [
            {"question": c.question, "answer": c.answer, "score": round(c.score, 3)}
            for c in result.sig_candidates
        ],
    }


def ingest(sop_paths: list[str] | None = None, sig_paths: list[str] | None = None) -> dict:
    """Rebuild the vector index (human-led memory update)."""
    from ..ingestion.pipeline import ingest_sops, ingest_sigs
    out: dict = {}
    if sop_paths:
        out["sop_passages_indexed"] = ingest_sops(sop_paths)
    if sig_paths:
        out["sig_pairs_indexed"] = ingest_sigs(sig_paths)
    return out
