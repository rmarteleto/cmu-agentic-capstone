"""Orchestrator — planner + beam-search controller (LangChain role).

Coordination strategy (hybrid):
  * SEQUENTIAL backbone per item:  retrieve -> interpret/critique (beam) ->
    precedence -> synthesize.
  * GRAPH-BASED, iterative core:   the Tree-of-Thoughts beam search.
  * PARALLEL fan-out:              questionnaire items run concurrently.

It owns the M6 abstention gate: when grounding is missing, the critic is not
confident, or a citation conflict cannot be resolved at any beam depth, it
returns "no match" (abstains) rather than gating each item to a person. Humans
remediate the corpora behind those gaps. All shared reasoning state lives on
SharedState.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from ..config import settings
from ..state.models import QuestionTask, FinalAnswer, AnswerStatus
from ..state.shared_state import SharedState
from ..reasoning.beam_search import (
    BeamSearchController, date_heuristic_prefilter, EarlyEscalation,
)
from ..reasoning.precedence import resolve_precedence
from ..reasoning.guardrails import classify_input
from .interpreter_agent import InterpreterAgent
from .critic_agent import ComplianceCriticAgent
from .synthesizer_agent import SynthesizerAgent
from .retriever_agent import RetrieverAgent


class Orchestrator:
    def __init__(
        self,
        retriever: Optional[RetrieverAgent] = None,
        interpreter: Optional[InterpreterAgent] = None,
        critic: Optional[ComplianceCriticAgent] = None,
        synthesizer: Optional[SynthesizerAgent] = None,
        max_workers: int = 4,
    ):
        self.retriever = retriever or RetrieverAgent()
        self.interpreter = interpreter or InterpreterAgent()
        self.critic = critic or ComplianceCriticAgent()
        self.synthesizer = synthesizer or SynthesizerAgent()
        self.max_workers = max_workers
        self.controller = BeamSearchController(
            generate=self.interpreter.generate,
            critique=self.critic.critique,
            heuristic_prefilter=date_heuristic_prefilter,
        )

    # ---- single questionnaire item ----------------------------------
    def answer_question(self, question: str, row_index: Optional[int] = None) -> FinalAnswer:
        # 0. Input guardrail (M6): normalize + classify. Malformed / out-of-scope
        #    / injection prompts are rejected up front (abstain, no LLM spend).
        verdict = classify_input(question)
        question = verdict.normalized or question
        state = SharedState(question)
        if not verdict.accepted:
            state.log(f"input rejected: {verdict.reason}")
            return self.synthesizer.synthesize(
                question, branch=None, matched_candidate=None, escalated=True,
                escalation_note=f"Input rejected by guardrail: {verdict.reason}.")

        # 1. Retrieve (one-way handoff downstream).
        result = self.retriever.fetch(question)
        state.log(f"retrieved {len(result.sop_passages)} SOP / "
                  f"{len(result.sig_candidates)} SIG (max_rel={result.max_relevance:.2f})")

        # Relevance gate: weak matches -> "no match" (abstain), never a forced answer.
        if not result.is_match or not result.sop_passages:
            return self.synthesizer.synthesize(
                question, branch=None, matched_candidate=None, escalated=True,
                escalation_note="No passage cleared the relevance threshold (no match); "
                                "remediate the corpus so this control is covered.")

        # 2. Deterministic precedence over the SOP passages — OBSERVABILITY ONLY.
        #    Conflict *resolution* belongs to the beam search, which checks for a
        #    real conflict (different answers AND different cited docs) at each
        #    depth. Escalating here on any precedence tie would be too blunt:
        #    the top-B passages are frequently complementary, not competing.
        prec = resolve_precedence(result.sop_passages)
        state.log(f"precedence(observability): {prec.outcome.value} — {prec.rationale}")

        # 3. Tree-of-Thoughts beam search (graph-based core).
        # Conflicting citations can surface mid-search (e.g. depth 2), so the
        # controller may abstain early rather than waiting for synthesis.
        try:
            best = self.controller.run(
                question, result.sop_passages, result.sig_candidates, state)
        except EarlyEscalation as esc:
            return self.synthesizer.synthesize(
                question, branch=None, matched_candidate=None, escalated=True,
                escalation_note=f"Unresolvable citation conflict (no match): {esc.note}")
        if best is None:
            return self.synthesizer.synthesize(
                question, branch=None, matched_candidate=None, escalated=True,
                escalation_note="All reasoning branches were pruned below threshold (no match).")

        # 4. Synthesize final, cited answer.
        top_candidate = max(result.sig_candidates, key=lambda c: c.score, default=None)
        answer = self.synthesizer.synthesize(question, best, top_candidate)
        answer.notes += f" | {state.snapshot()}"
        return answer

    # ---- full questionnaire (parallel fan-out) -----------------------
    def answer_questionnaire(self, tasks: list[QuestionTask]) -> list[FinalAnswer]:
        results: list[tuple[int, FinalAnswer]] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self.answer_question, t.question, t.row_index): i
                for i, t in enumerate(tasks)
            }
            for fut in as_completed(futures):
                results.append((futures[fut], fut.result()))
        results.sort(key=lambda x: x[0])
        return [a for _, a in results]
