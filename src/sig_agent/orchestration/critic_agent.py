"""Compliance Critic — independent validator (CrewAI role).

The central reliability mechanism: a SEPARATE actor from the Interpreter, so
the system never grades its own draft. Scores each node 1-5 on semantic
alignment, scope completeness, and document authority, and pairs the LLM
judgement with deterministic attribute checks (effective date present, scope
applicable). Two-way communication: its verdict flows back to the controller
to keep or prune the branch.
"""
from __future__ import annotations

from datetime import date

from ..state.models import ReasoningNode
from ..llm import complete_json

_SYSTEM = (
    "You are a Compliance Critic auditing a draft SIG answer for a SOC2 vendor. "
    "Score the draft against the cited SOP on three axes, each 1-5: "
    "semantic_alignment (does it truly answer the control asked?), "
    "scope_completeness (does the cited policy fully cover the question's scope?), "
    "authority (is the citation from an authoritative, current policy?). "
    "Be skeptical of answers that are topically close but govern a different "
    "control. Respond ONLY as JSON: "
    '{"semantic_alignment": n, "scope_completeness": n, "authority": n, "reason": "..."}.'
)


class ComplianceCriticAgent:
    def __init__(self, use_crewai: bool = True):
        self._crew_agent = None
        if use_crewai:
            self._crew_agent = self._build_crew_agent()

    def _build_crew_agent(self):
        try:
            from crewai import Agent
            from ..llm import get_chat_model
            return Agent(
                role="Compliance Critic",
                goal="Independently validate draft answers against active SOPs and prune weak reasoning.",
                backstory="A rigorous auditor whose job is to catch confidently-wrong, well-sourced answers.",
                llm=get_chat_model(temperature=0.0),
                allow_delegation=False,
                verbose=False,
            )
        except Exception:
            return None

    def critique(self, question: str, node: ReasoningNode) -> tuple[float, float]:
        """Return (overall_critic_score, scope_completeness_subscore)."""
        # Deterministic heuristic checks first (cheap, no tokens).
        det_penalty = 0.0
        if not node.citations:
            det_penalty += 1.5
        elif not any(c.effective_date for c in node.citations):
            det_penalty += 0.5

        cites = "; ".join(
            f"{c.document_id} {c.section} (v{c.version}, {c.effective_date})"
            for c in node.citations
        ) or "NONE"
        user = (
            f"SIG question:\n{question}\n\n"
            f"Draft answer:\n{node.draft_answer}\n\n"
            f"Cited SOP passages: {cites}\n"
            f"Hypothesis: {node.thought}"
        )
        data = complete_json(_SYSTEM, user, temperature=0.0)
        sem = float(data.get("semantic_alignment", 1))
        scope = float(data.get("scope_completeness", 1))
        auth = float(data.get("authority", 1))
        overall = max(0.0, (sem + scope + auth) / 3.0 - det_penalty)
        return overall, scope
