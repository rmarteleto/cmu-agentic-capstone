"""Beam search controller with stub Interpreter/Critic (no LLM/network).

Verifies the framework-agnostic reasoning core: bounds (W, D), pruning below
the critic threshold, deterministic pre-filter, and best-branch selection.
"""
from datetime import date

from sig_agent.config import settings
from sig_agent.state.models import Passage, Candidate, Provenance, ReasoningNode
from sig_agent.state.shared_state import SharedState
from sig_agent.reasoning.beam_search import BeamSearchController, date_heuristic_prefilter


def _passage(doc, score=1.0, eff=None):
    return Passage(text=f"policy {doc}", score=score,
                   provenance=Provenance(source="SOP", document_id=doc, effective_date=eff))


def make_controller(score_for):
    def generate(question, passage, parent):
        depth = (parent.depth + 1) if parent else 1
        return ReasoningNode(depth=depth, thought=f"map {passage.provenance.document_id}",
                             draft_answer="draft", citations=[passage.provenance],
                             parent_id=parent.node_id if parent else None)

    def critique(question, node):
        s = score_for(node.citations[0].document_id if node.citations else "")
        return s, s
    return BeamSearchController(generate=generate, critique=critique)


def test_respects_beam_width_and_depth():
    passages = [_passage(f"SOP-{i}", score=1.0) for i in range(5)]
    ctrl = make_controller(lambda doc: 5.0)
    state = SharedState("q")
    best = ctrl.run("q", passages, [], state)
    assert best is not None
    # depth never exceeds D
    assert best.leaf.depth <= settings.max_depth
    assert len(best.nodes) == settings.max_depth


def test_prunes_below_threshold():
    passages = [_passage("GOOD", score=1.0), _passage("BAD", score=1.0)]
    # GOOD scores high, BAD below the min scope threshold
    ctrl = make_controller(lambda doc: 5.0 if doc == "GOOD" else 1.0)
    state = SharedState("q")
    best = ctrl.run("q", passages, [], state)
    assert best is not None
    assert all(n.citations[0].document_id == "GOOD" for n in best.nodes)


def test_all_pruned_returns_none():
    passages = [_passage("X", score=1.0)]
    ctrl = make_controller(lambda doc: 0.0)  # everything below threshold
    state = SharedState("q")
    assert ctrl.run("q", passages, [], state) is None


def test_date_heuristic_prefilter_prunes_stale_sop():
    sop = _passage("SOP-OLD", eff=date(2022, 1, 1))
    newer_sig = Candidate(question="q", answer="a",
                          provenance=Provenance(source="SIG", document_id="SIG-1",
                                                effective_date=date(2024, 1, 1)))
    # SOP predates an unchanged newer SIG answer -> prune (return False = drop)
    assert date_heuristic_prefilter(sop, [newer_sig]) is False
    # No SIG dates -> keep
    assert date_heuristic_prefilter(sop, []) is True


# ---- M4 review note: early escalation on conflicting branch citations ----
import pytest
from datetime import date as _date
from sig_agent.reasoning.beam_search import EarlyEscalation


def _conflicting_controller():
    """Two passages tie on every precedence rule but yield different answers."""
    passages = [
        Passage(text="p", score=1.0, provenance=Provenance(
            source="SOP", document_id="SOP-A", effective_date=_date(2025, 1, 1),
            scope="system", authority_rank=2)),
        Passage(text="p", score=1.0, provenance=Provenance(
            source="SOP", document_id="SOP-B", effective_date=_date(2025, 1, 1),
            scope="system", authority_rank=2)),
    ]

    def generate(question, passage, parent):
        depth = (parent.depth + 1) if parent else 1
        doc = passage.provenance.document_id
        # Different sources produce materially different draft answers.
        return ReasoningNode(depth=depth, thought=f"map {doc}",
                             draft_answer=f"answer-from-{doc}",
                             citations=[passage.provenance],
                             parent_id=parent.node_id if parent else None)

    def critique(question, node):
        return 5.0, 5.0  # both strong; neither prunes -> both survive the beam

    return BeamSearchController(generate=generate, critique=critique), passages


def test_conflicting_citations_escalate_early():
    ctrl, passages = _conflicting_controller()
    state = SharedState("q")
    with pytest.raises(EarlyEscalation) as exc:
        ctrl.run("q", passages, [], state)
    assert exc.value.depth == 1            # fires as soon as the beam forms
    assert any("EARLY ESCALATION" in e for e in state.event_log)


def test_same_answer_different_sources_does_not_escalate():
    """Complementary citations (same answer) must NOT trigger escalation."""
    passages = [
        Passage(text="p", score=1.0, provenance=Provenance(
            source="SOP", document_id="SOP-A", effective_date=_date(2025, 1, 1))),
        Passage(text="p", score=1.0, provenance=Provenance(
            source="SOP", document_id="SOP-B", effective_date=_date(2025, 1, 1))),
    ]

    def generate(question, passage, parent):
        depth = (parent.depth + 1) if parent else 1
        return ReasoningNode(depth=depth, thought="t", draft_answer="same answer",
                             citations=[passage.provenance],
                             parent_id=parent.node_id if parent else None)

    ctrl = BeamSearchController(generate=generate, critique=lambda q, n: (5.0, 5.0))
    state = SharedState("q")
    best = ctrl.run("q", passages, [], state)   # must complete, no exception
    assert best is not None
