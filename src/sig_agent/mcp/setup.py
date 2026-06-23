"""Build the MCP server and register the sig_* tools.

Mirrors RocketSmith's mcp/setup.py: a single setup_server() assembles the
FastMCP instance and attaches every tool the agents (agents/*.md) are allowed
to call. Tool names are domain-prefixed (sig_*) just as RocketSmith uses
openrocket_*, cadsmith_*, prusaslicer_*.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import service
from .types import AnswerDict


def setup_server() -> FastMCP:
    server = FastMCP(
        name="sig_agent",
        instructions=(
            "Answers Standardized Information Gathering (SIG) questionnaire items "
            "for a SOC2 FinTech vendor, grounded in SOPs and historical SIGs. Every "
            "answer carries citations and a confidence score. When grounding is "
            "missing or sources conflict, the agent abstains ('no match', status "
            "'escalated') rather than guessing — those gaps point to corpora that "
            "need human remediation, not per-answer approval."
        ),
    )

    @server.tool()
    def sig_answer_question(question: str) -> AnswerDict:
        """Answer a single SIG questionnaire item end-to-end.

        Runs retrieval -> interpretation -> compliance critique -> precedence ->
        synthesis. Returns answer, status, needs_human_review, confidence, citations.
        """
        return service.answer_question(question)

    @server.tool()
    def sig_answer_batch(questions: list[str]) -> list[AnswerDict]:
        """Answer many SIG items at once (parallel). Use for questionnaire sections."""
        return service.answer_batch(questions)

    @server.tool()
    def sig_retrieve(question: str) -> dict:
        """Dual-corpus hybrid retrieval only (SOP passages + SIG candidates)."""
        return service.retrieve(question)

    @server.tool()
    def sig_ingest(sop_paths: list[str] | None = None, sig_paths: list[str] | None = None) -> dict:
        """Rebuild the vector index from local SOP/SIG files (human-led memory update)."""
        return service.ingest(sop_paths=sop_paths, sig_paths=sig_paths)

    return server
