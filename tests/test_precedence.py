"""Deterministic precedence engine — pure logic, no LLM/network."""
from datetime import date

from sig_agent.state.models import Passage, Provenance
from sig_agent.reasoning.precedence import resolve_precedence, PrecedenceOutcome


def _p(doc, eff=None, scope="global", auth=0):
    return Passage(text="x", provenance=Provenance(
        source="SOP", document_id=doc, effective_date=eff, scope=scope, authority_rank=auth))


def test_single_passage_resolves():
    r = resolve_precedence([_p("SOP-1")])
    assert r.outcome == PrecedenceOutcome.RESOLVED
    assert r.winner.provenance.document_id == "SOP-1"


def test_newest_date_wins():
    old = _p("OLD", eff=date(2023, 1, 1))
    new = _p("NEW", eff=date(2025, 1, 1))
    r = resolve_precedence([old, new])
    assert r.outcome == PrecedenceOutcome.RESOLVED
    assert r.winner.provenance.document_id == "NEW"


def test_narrowest_scope_breaks_date_tie():
    same = date(2025, 1, 1)
    broad = _p("BROAD", eff=same, scope="global")
    narrow = _p("NARROW", eff=same, scope="system")
    r = resolve_precedence([broad, narrow])
    assert r.winner.provenance.document_id == "NARROW"


def test_authority_breaks_scope_tie():
    same = date(2025, 1, 1)
    low = _p("LOW", eff=same, scope="system", auth=1)
    high = _p("HIGH", eff=same, scope="system", auth=5)
    r = resolve_precedence([low, high])
    assert r.winner.provenance.document_id == "HIGH"


def test_unresolvable_escalates():
    same = date(2025, 1, 1)
    a = _p("A", eff=same, scope="system", auth=3)
    b = _p("B", eff=same, scope="system", auth=3)
    r = resolve_precedence([a, b])
    assert r.outcome == PrecedenceOutcome.ESCALATE
    assert r.winner is None
