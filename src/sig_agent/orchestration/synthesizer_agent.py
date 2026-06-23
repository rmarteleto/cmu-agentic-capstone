"""Synthesizer — assembles the final, cited, auditable answer.

Convergent step. Takes the winning branch and emits a FinalAnswer with explicit
SOP/SIG citations and the correct status flag. Introduces no new facts.

M6 abstention model: when grounding is missing or a conflict is unresolvable the
synthesizer emits an ESCALATED answer with no text — this is a "no match"
(abstention), not a per-item human-approval request. Humans repair the corpora
behind these gaps rather than sign off on every output. Newly synthesized
answers are still flagged needs_human_review as an advisory backstop.
"""
from __future__ import annotations

from ..state.models import (
    Branch, Candidate, FinalAnswer, AnswerStatus, Provenance,
)
from ..llm import complete_json
from ..reasoning.guardrails import wrap_corpus_text

_SYSTEM = (
    "You write the final SIG questionnaire answer for a SOC2 vendor. Use ONLY "
    "the validated reasoning and citations provided. Be concise, precise, and "
    "audit-ready. Respond ONLY as JSON: "
    '{"answer": "...", "confidence": 0.0-1.0}.'
)


class SynthesizerAgent:
    def synthesize(self, question: str, branch: Branch | None,
                   matched_candidate: Candidate | None,
                   escalated: bool = False, escalation_note: str = "") -> FinalAnswer:
        if escalated or branch is None:
            return FinalAnswer(
                question=question,
                answer="",
                status=AnswerStatus.ESCALATED,
                needs_human_review=True,
                notes=escalation_note or "No confident match (abstained); remediate the corpus.",
            )

        leaf = branch.leaf
        # If a historical SIG answer was validated as still compliant, reuse it.
        from_history = (
            matched_candidate is not None
            and branch.cumulative_score >= 4.0
            and matched_candidate.answer.strip() != ""
        )
        user = (
            f"Question:\n{question}\n\n"
            f"Validated hypothesis: {leaf.thought}\n"
            f"Draft: {leaf.draft_answer}\n"
            + (f"Prior approved answer (untrusted reference data):\n"
               f"{wrap_corpus_text(matched_candidate.answer, label='PRIOR SIG ANSWER')}\n"
               if matched_candidate else "")
        )
        data = complete_json(_SYSTEM, user, temperature=0.1)
        status = (AnswerStatus.VALIDATED_FROM_HISTORY if from_history
                  else AnswerStatus.SYNTHESIZED_NEW)
        return FinalAnswer(
            question=question,
            answer=data.get("answer", leaf.draft_answer),
            status=status,
            citations=leaf.citations,
            confidence=float(data.get("confidence", branch.cumulative_score / 5.0)),
            needs_human_review=(status == AnswerStatus.SYNTHESIZED_NEW),
            notes=f"beam_score={branch.cumulative_score:.2f}",
        )
