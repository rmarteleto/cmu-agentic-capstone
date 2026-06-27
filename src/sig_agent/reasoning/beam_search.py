"""Tree-of-Thoughts beam search — the reasoning controller (LangChain role).

This is the graph-based, iterative core of the architecture. The controller:
  * expands the frontier by asking the Interpreter for candidate thoughts
    (branching factor B = top-B retrieved SOP chunks),
  * applies a cheap DETERMINISTIC heuristic pre-filter before any LLM critic
    call (mitigates branch explosion / token latency),
  * scores survivors with the Compliance Critic,
  * prunes branches below CRITIC_MIN_SCORE on scope completeness,
  * keeps only the top-W branches (beam width) at each depth,
  * checks for unresolvable citation conflicts AT EACH DEPTH and escalates
    early (M4 review note) rather than waiting for final synthesis,
  * runs to depth D, then returns the best terminal branch.

The Interpreter and Critic are injected (CrewAI agents in production), so this
controller is framework-agnostic and unit-testable with stubs.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from difflib import SequenceMatcher
from typing import Callable, Optional

from ..config import settings
from ..state.models import Branch, ReasoningNode, Passage, Candidate
from ..state.shared_state import SharedState
from .precedence import resolve_precedence, PrecedenceOutcome

# Injected callables (CrewAI agents wrap these in production):
#   generate(question, passage, parent) -> ReasoningNode
#   critique(question, node) -> (critic_score, scope_score)
GenerateFn = Callable[[str, Passage, Optional[ReasoningNode]], ReasoningNode]
CritiqueFn = Callable[[str, ReasoningNode], tuple]


class EarlyEscalation(Exception):
    """Raised mid-search for truly unrecoverable conditions (e.g. empty corpus
    after all branches are pruned).  Citation conflicts between branches are now
    handled by merging citations and annotating the winning branch's thought
    rather than raising this exception — see _check_branch_conflicts.
    """

    def __init__(self, note: str, depth: int):
        super().__init__(note)
        self.note = note
        self.depth = depth


class BeamSearchController:
    DEPTH_LABELS = {1: "Intent Mapping", 2: "Reconciliation & Scope", 3: "Final Synthesis"}

    def __init__(self, generate: GenerateFn, critique: CritiqueFn,
                 heuristic_prefilter: Optional[Callable[[Passage, list], bool]] = None):
        self.generate = generate
        self.critique = critique
        self.heuristic_prefilter = heuristic_prefilter or (lambda passage, cands: True)
        self.W = settings.beam_width
        self.D = settings.max_depth
        self.min_score = settings.critic_min_score

    def run(self, question: str, passages: list[Passage],
            candidates: list[Candidate], state: SharedState) -> Optional[Branch]:
        B = settings.branch_factor
        workers = settings.beam_max_workers

        # Depth 1 — fan out over the top-B passages in parallel.
        d1_passages = [p for p in passages[:B]
                       if self.heuristic_prefilter(p, candidates)
                       or state.log(f"prefilter pruned passage {p.passage_id}") or False]

        def _expand_d1(passage: Passage) -> Optional[Branch]:
            try:
                node = self.generate(question, passage, None)
                node.depth = 1
                state.register_node(node)
                score, scope = self.critique(question, node)
                node.critic_score, node.scope_score = score, scope
                if scope < self.min_score:
                    state.log(f"pruned node {node.node_id} scope={scope} < {self.min_score}")
                    return None
                return Branch(nodes=[node])
            except Exception as exc:
                state.log(f"d1 branch error (passage={passage.passage_id}): {exc}")
                return None

        with ThreadPoolExecutor(max_workers=workers) as ex:
            frontier = [b for b in ex.map(_expand_d1, d1_passages) if b is not None]

        if not frontier:
            return None
        frontier = self._beam(frontier)
        self._check_branch_conflicts(frontier, state, depth=1)

        # Depths 2..D — fan out over every (branch, passage) pair in parallel.
        for depth in range(2, self.D + 1):
            pairs = [(branch, passage)
                     for branch in frontier
                     for passage in passages[:B]]

            def _expand_pair(args: tuple, _depth: int = depth) -> Optional[Branch]:
                branch, passage = args
                try:
                    child = self.generate(question, passage, branch.leaf)
                    child.depth = _depth
                    child.parent_id = branch.leaf.node_id
                    state.register_node(child)
                    score, scope = self.critique(question, child)
                    child.critic_score, child.scope_score = score, scope
                    if scope < self.min_score:
                        state.log(f"pruned node {child.node_id} at d{_depth}")
                        return None
                    new_branch = Branch(nodes=branch.nodes + [child])
                    state.register_branch(new_branch)
                    return new_branch
                except Exception as exc:
                    state.log(f"d{_depth} branch error (passage={passage.passage_id}): {exc}")
                    return None

            with ThreadPoolExecutor(max_workers=workers) as ex:
                expanded = [b for b in ex.map(_expand_pair, pairs) if b is not None]

            if not expanded:
                break
            frontier = self._beam(expanded)
            self._check_branch_conflicts(frontier, state, depth=depth)

        return max(frontier, key=lambda b: b.cumulative_score) if frontier else None

    def _beam(self, branches: list[Branch]) -> list[Branch]:
        """Keep the W highest-scoring branches (beam width)."""
        return sorted(branches, key=lambda b: b.cumulative_score, reverse=True)[: self.W]

    def _check_branch_conflicts(self, branches: list[Branch],
                                state: SharedState, depth: int) -> None:
        """Detect and handle citation conflicts at each beam depth.

        Two tiers:
        1. **Similar answers** (SequenceMatcher ratio >= threshold): branches
           are complementary — same policy, different phrasing. Merge all
           citations into the best-scoring branch and continue without
           escalating.
        2. **Different answers** from ≥2 distinct SOP docs: apply deterministic
           precedence. If precedence resolves the tie, continue normally. If
           unresolvable, merge all citations into the best branch and annotate
           its thought with a multi-source note so the Synthesizer can present
           each perspective with its citation rather than abstaining.

        EarlyEscalation is no longer raised here; the "unresolvable conflict"
        path now produces a richer answer instead of a blank.
        """
        if len(branches) < 2:
            return

        labeled = [
            (b, (b.leaf.draft_answer or "").strip().lower())
            for b in branches
            if (b.leaf.draft_answer or "").strip()
        ]
        if len(labeled) < 2:
            return

        passages_by_doc: dict[str, Passage] = {}
        for b in branches:
            for prov in b.leaf.citations:
                passages_by_doc.setdefault(
                    prov.document_id, Passage(text="", provenance=prov))

        # Pairwise similarity across all surviving draft answers.
        answers = [a for _, a in labeled]
        max_sim = max(
            SequenceMatcher(None, a1, a2).ratio()
            for i, a1 in enumerate(answers)
            for a2 in answers[i + 1:]
        )

        def _merge_citations(target: Branch, sources: list[Branch]) -> None:
            seen: set[tuple[str, str]] = {
                (p.document_id, p.section) for p in target.leaf.citations
            }
            for src in sources:
                for prov in src.leaf.citations:
                    key = (prov.document_id, prov.section)
                    if key not in seen:
                        seen.add(key)
                        target.leaf.citations.append(prov)

        threshold = settings.answer_similarity_threshold
        if max_sim >= threshold:
            # Complementary passages — keep best branch, absorb all citations.
            best = max(branches, key=lambda b: b.cumulative_score)
            others = [b for b in branches if b is not best]
            _merge_citations(best, others)
            state.log(
                f"branch answers complementary (similarity={max_sim:.2f} >= "
                f"{threshold}) @ d{depth}: merged {len(passages_by_doc)} "
                f"citation sources into best branch"
            )
            return

        # Answers are materially different — only a real conflict if ≥2 docs.
        if len(passages_by_doc) < 2:
            return

        result = resolve_precedence(list(passages_by_doc.values()))
        if result.outcome == PrecedenceOutcome.ESCALATE:
            # Unresolvable by rules: keep best branch, merge all citations, and
            # annotate the thought so the Synthesizer presents every perspective
            # with its source rather than issuing a blank "no match".
            best = max(branches, key=lambda b: b.cumulative_score)
            others = [b for b in branches if b is not best]
            _merge_citations(best, others)
            source_ids = sorted(passages_by_doc)
            best.leaf.thought = (
                f"[Multiple sources with differing context — present each "
                f"perspective with its citation: {', '.join(source_ids)}] "
                + best.leaf.thought
            )
            state.log(
                f"citation conflict @ d{depth}: unresolvable by precedence — "
                f"merged citations from {source_ids} into best branch for "
                f"multi-source synthesis"
            )
            return

        state.log(f"branch citation conflict @ d{depth} resolved: {result.rationale}")


def date_heuristic_prefilter(passage: Passage, candidates: list[Candidate]) -> bool:
    """Cheap MCP-layer filter: if an unchanged historical SIG answer post-dates
    the SOP chunk, the policy hasn't moved past the prior answer — deterministically
    prune this branch and skip the expensive LLM generator/critic calls.
    Returns True to KEEP the branch, False to prune.
    """
    sop_date = passage.provenance.effective_date
    if not sop_date or not candidates:
        return True
    newest_sig = max((c.provenance.effective_date for c in candidates
                      if c.provenance.effective_date), default=None)
    if newest_sig and sop_date < newest_sig:
        return False
    return True
