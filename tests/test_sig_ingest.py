"""SIG-history ingestion building blocks — pure logic, no network/Chroma."""
from datetime import date

from sig_agent.ingestion.chunking import sig_pairs_from_rows


def test_sig_pairs_built_from_rows():
    rows = [
        {"question": "Do you encrypt data at rest?", "answer": "Yes, AES-256."},
        {"question": "MFA enforced?", "answer": "Yes, for all admins."},
    ]
    cands = sig_pairs_from_rows(rows, document_id="sig_2025.xlsx",
                                effective_date=date(2025, 1, 1))
    assert len(cands) == 2
    assert cands[0].provenance.source == "SIG"
    assert cands[0].provenance.document_id == "sig_2025.xlsx"
    assert cands[0].answer == "Yes, AES-256."


def test_sig_pairs_skip_incomplete_rows():
    rows = [
        {"question": "Only a question", "answer": ""},
        {"question": "", "answer": "orphan answer"},
        {"question": "Valid?", "answer": "Yes."},
    ]
    cands = sig_pairs_from_rows(rows, document_id="d")
    assert len(cands) == 1
    assert cands[0].question == "Valid?"
