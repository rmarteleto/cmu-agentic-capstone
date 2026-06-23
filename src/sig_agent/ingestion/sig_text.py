"""Parser for plain-text SIG history exports.

Historical SIGs are sometimes exported as a flat text file: one block per item,
blocks separated by a dashed rule, each block carrying ``Question:``, ``Answer:``
and ``Comment:`` markers (the Comment usually holds the SOP citation). Returns
{'question', 'answer', 'comment'} rows; comment is stored as separate metadata.
"""
from __future__ import annotations

import re

_SEP = re.compile(r"^-{3,}\s*$", re.MULTILINE)          # the "-----------" rule
_MARKER = re.compile(r"^\s*(Question|Answer|Comment)\s*:\s*(.*)$", re.IGNORECASE)


def parse_sig_text(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    rows: list[dict] = []
    for block in _SEP.split(raw):
        if block.strip():
            rec = _parse_block(block)
            if rec:
                rows.append(rec)
    return rows


def _parse_block(block: str) -> dict | None:
    fields = {"question": [], "answer": [], "comment": []}
    cur = None
    for line in block.splitlines():
        m = _MARKER.match(line)
        if m:
            cur = m.group(1).lower()
            fields[cur].append(m.group(2))
        elif cur:                       # continuation of a multi-line field
            fields[cur].append(line)

    q = " ".join(x.strip() for x in fields["question"]).strip()
    a = " ".join(x.strip() for x in fields["answer"]).strip()
    c = " ".join(x.strip() for x in fields["comment"]).strip()
    if not q:
        return None
    if a and c:
        # If the comment already restates the answer ("Yes, please refer..."),
        # keep the richer comment; otherwise join answer + comment.
        answer = c if c.lower().startswith(a.lower()) else f"{a}. {c}"
    else:
        answer = a or c
    if not answer:
        return None
    return {"question": q, "answer": answer, "comment": c}
