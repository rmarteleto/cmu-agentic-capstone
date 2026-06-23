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

from datetime import date
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
    """Raised mid-search when surviving branches carry conflicting citations
    that the deterministic precedence rules cannot resolve.

    Addresses the M4 review note: a citation conflict can surface before the
    final synthesis node (e.g. at depth 2, Reconciliation & Scope), so the
    human-escalation gate must be able to trigger early rather than letting the
    controller silently pick the higher-scored of two conflicting branches.
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
        # Seed depth-1 nodes from the top-B SOP passages that survive the
        # cheap deterministic pre-filter.
        frontier: list[Branch] = []
        for passage in passages[: settings.branch_factor]:
            if not self.heuristic_prefilter(passage, candidates):
                state.log(f"prefilter pruned passage {passage.passage_id}")
                continue
            node = self.generate(question, passage, None)
            node.depth = 1
            state.register_node(node)
            score, scope = self.critique(question, node)
            node.critic_score, node.scope_score = score, scope
            if scope < self.min_score:
                state.log(f"pruned node {node.node_id} scope={scope} < {self.min_score}")
                continue
            frontier.append(Branch(nodes=[node]))

        if not frontier:
            return None
        frontier = self._beam(frontier)
        self._check_branch_conflicts(frontier, state, depth=1)

        # Expand depth 2..D.
        for depth in range(2, self.D + 1):
            expanded: list[Branch] = []
            for branch in frontier:
                for passage in passages[: settings.branch_factor]:
                    child = self.generate(question, passage, branch.leaf)
                    child.depth = depth
                    child.parent_id = branch.leaf.node_id
                    state.register_node(child)
                    score, scope = self.critique(question, child)
                    child.critic_score, child.scope_score = score, scope
                    if scope < self.min_score:
                        state.log(f"pruned node {child.node_id} at d{depth}")
                        continue
                    new_branch = Branch(nodes=branch.nodes + [child])
                    state.register_branch(new_branch)
                    expanded.append(new_branch)
            if not expanded:
                break
            frontier = self._beam(expanded)
            # Check for unresolvable citation conflicts as soon as the beam is
            # formed at this depth — before proceeding toward final synthesis.
            self._check_branch_conflicts(frontier, state, depth=depth)

        return max(frontier, key=lambda b: b.cumulative_score) if frontier else None

    def _beam(self, branches: list[Branch]) -> list[Branch]:
        """Keep the W highest-scoring branches (beam width)."""
        return sorted(branches, key=lambda b: b.cumulative_score, reverse=True)[: self.W]

    def _check_branch_conflicts(self, branches: list[Branch],
                                state: SharedState, depth: int) -> None:
        """Escalate early if surviving branches disagree on an unresolvable basis.

        A conflict requires BOTH (a) branches that reach materially different
        draft answers, and (b) at least two distinct cited SOP documents. Merely
        citing different but complementary passages is not a conflict. When such
        a disagreement exists, the deterministic precedence engine is asked to
        rank the competing citations; if it returns ESCALATE (an unbreakable
        tie), we stop and route to the human gate immediately.
        """
        if len(branches) < 2:
            return
        distinct_answers = {
            (b.leaf.draft_answer or "").strip().lower()
            for b in branches if (b.leaf.draft_answer or "").strip()
        }
        passages_by_doc: dict[str, Passage] = {}
        for b in branches:
            for prov in b.leaf.citations:
                passages_by_doc.setdefault(
                    prov.document_id, Passage(text="", provenance=prov))
        if len(distinct_answers) < 2 or len(passages_by_doc) < 2:
            return  # branches agree, or share a single source — no conflict

        result = resolve_precedence(list(passages_by_doc.values()))
        if result.outcome == PrecedenceOutcome.ESCALATE:
            note = (f"Conflicting citations across reasoning branches at depth "
                    f"{depth} ({self.DEPTH_LABELS.get(depth, '')}): {result.rationale}. "
                    f"Sources: {sorted(passages_by_doc)}.")
            state.log(f"EARLY ESCALATION @ d{depth}: {note}")
            raise EarlyEscalation(note, depth)
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
