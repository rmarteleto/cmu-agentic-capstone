"""Plain-text SIG export parser — pure, no network."""
from sig_agent.ingestion.sig_text import parse_sig_text

_SAMPLE = """Question: Is encryption in place?
Answer: Yes
Comment: Yes, please refer to SOP #1000
-----------
Question: Multi-line item?
1. clause one
2. clause two

Answer: Yes
Comment: Refer to Vendor Tracking 2025.
-----------
Question: Answer only, no comment?
Answer: No
Comment:
-----------

"""


def test_parses_blocks(tmp_path):
    p = tmp_path / "sig.txt"
    p.write_text(_SAMPLE, encoding="utf-8")
    rows = parse_sig_text(str(p))
    assert len(rows) == 3


def test_merges_answer_and_comment(tmp_path):
    p = tmp_path / "sig.txt"
    p.write_text(_SAMPLE, encoding="utf-8")
    rows = parse_sig_text(str(p))
    # comment starting with the answer ("Yes...") is not duplicated
    assert rows[0]["answer"] == "Yes, please refer to SOP #1000."


def test_multiline_question_captured(tmp_path):
    p = tmp_path / "sig.txt"
    p.write_text(_SAMPLE, encoding="utf-8")
    rows = parse_sig_text(str(p))
    assert "clause one" in rows[1]["question"]
    assert "clause two" in rows[1]["question"]


def test_answer_without_comment(tmp_path):
    p = tmp_path / "sig.txt"
    p.write_text(_SAMPLE, encoding="utf-8")
    rows = parse_sig_text(str(p))
    assert rows[2]["answer"] == "No"
