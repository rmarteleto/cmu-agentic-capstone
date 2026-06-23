"""Typed data models exchanged between agents.

These objects are the *vocabulary* of the system. They flow across the
SharedState blackboard so that the Orchestrator, Interpreter, Critic and
Synthesizer all operate on the same, fully-traceable structures.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Provenance:
    """Audit metadata attached to every chunk during ingestion.

    Drives the deterministic precedence rule:
    newest effective date > narrowest scope > highest authority.
    """
    source: str                      # "SOP" or "SIG"
    document_id: str                 # e.g. SOP number / SIG filename
    section: str = ""                # parent section (structure-aware chunk)
    version: str = ""
    effective_date: Optional[date] = None
    scope: str = "global"            # "global" | "business_unit" | "system" ...
    authority_rank: int = 0          # higher = more authoritative document class
    source_url: str = ""             # link back to source document


# Narrower scope wins ties — lower number == narrower.
SCOPE_SPECIFICITY = {"global": 0, "division": 1, "business_unit": 2, "system": 3, "control": 4}


@dataclass
class Passage:
    """A retrieved chunk (SOP policy unit or SIG Q/A pair)."""
    text: str
    provenance: Provenance
    score: float = 0.0               # fused hybrid-search relevance score
    passage_id: str = field(default_factory=_new_id)


@dataclass
class Candidate:
    """A historical SIG answer proposed as a starting point."""
    question: str
    answer: str
    provenance: Provenance
    comment: str = ""    # SOP citation or clarification from original SIG response
    score: float = 0.0


@dataclass
class ReasoningNode:
    """A node in the Tree-of-Thoughts: a partial verification state."""
    depth: int
    thought: str                     # the hypothesis being explored
    draft_answer: str = ""
    citations: list[Provenance] = field(default_factory=list)
    critic_score: float = 0.0        # 1..5 from Compliance Critic
    scope_score: float = 0.0         # sub-score used for the hard prune
    heuristic_passed: bool = True    # deterministic pre-filter result
    node_id: str = field(default_factory=_new_id)
    parent_id: Optional[str] = None


@dataclass
class Branch:
    """A root-to-leaf path through the reasoning tree (beam member)."""
    nodes: list[ReasoningNode] = field(default_factory=list)
    branch_id: str = field(default_factory=_new_id)

    @property
    def leaf(self) -> ReasoningNode:
        return self.nodes[-1]

    @property
    def cumulative_score(self) -> float:
        if not self.nodes:
            return 0.0
        return sum(n.critic_score for n in self.nodes) / len(self.nodes)


class AnswerStatus(str, Enum):
    VALIDATED_FROM_HISTORY = "validated_from_history"
    SYNTHESIZED_NEW = "synthesized_new"          # must be human-checked
    ESCALATED = "escalated"                      # M6: "no match" / abstained — corpus repair, not output approval


@dataclass
class FinalAnswer:
    question: str
    answer: str
    status: AnswerStatus
    citations: list[Provenance] = field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = True
    notes: str = ""


@dataclass
class QuestionTask:
    """One questionnaire item dispatched by the Orchestrator."""
    question: str
    row_index: Optional[int] = None              # for spreadsheet output
    task_id: str = field(default_factory=_new_id)
