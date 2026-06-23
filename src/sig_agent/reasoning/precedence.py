"""Deterministic precedence rules — kept as a TOOL, not an agent.

Conflict resolution must be reproducible and auditable, so it is pure code:
    1. newest effective date wins
    2. else narrowest applicable scope wins
    3. else highest document authority wins
If still tied, we cannot safely decide -> escalate to a human who reviews the
conflicting passages side by side.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..state.models import Passage, Provenance, SCOPE_SPECIFICITY


class PrecedenceOutcome(str, Enum):
    RESOLVED = "resolved"
    ESCALATE = "escalate"


@dataclass
class PrecedenceResult:
    outcome: PrecedenceOutcome
    winner: Passage | None
    rationale: str


def resolve_precedence(passages: list[Passage]) -> PrecedenceResult:
    if not passages:
        return PrecedenceResult(PrecedenceOutcome.ESCALATE, None, "no passages to compare")
    if len(passages) == 1:
        return PrecedenceResult(PrecedenceOutcome.RESOLVED, passages[0], "single authoritative passage")

    # Rule 1: newest effective date
    dated = [p for p in passages if p.provenance.effective_date]
    if dated:
        newest = max(p.provenance.effective_date for p in dated)
        top = [p for p in dated if p.provenance.effective_date == newest]
        if len(top) == 1:
            return PrecedenceResult(PrecedenceOutcome.RESOLVED, top[0],
                                    f"newest effective date {newest.isoformat()}")
    else:
        top = list(passages)

    # Rule 2: narrowest applicable scope (higher specificity value == narrower)
    def spec(p: Passage) -> int:
        return SCOPE_SPECIFICITY.get(p.provenance.scope, 0)

    narrowest = max(spec(p) for p in top)
    top = [p for p in top if spec(p) == narrowest]
    if len(top) == 1:
        return PrecedenceResult(PrecedenceOutcome.RESOLVED, top[0],
                                f"narrowest scope '{top[0].provenance.scope}'")

    # Rule 3: highest document authority
    highest = max(p.provenance.authority_rank for p in top)
    top = [p for p in top if p.provenance.authority_rank == highest]
    if len(top) == 1:
        return PrecedenceResult(PrecedenceOutcome.RESOLVED, top[0],
                                f"highest authority rank {highest}")

    return PrecedenceResult(PrecedenceOutcome.ESCALATE, None,
                            "unresolvable conflict after all precedence rules")
