"""Structure-aware chunking.

SOP material is split on section boundaries so each chunk stays a coherent
policy unit, and ingestion metadata (parent section, doc id, version, date,
scope, authority) is retained on every chunk — this is what later powers the
deterministic precedence rule. Historical SIGs are kept as Q/A pairs.

Chunk size and overlap are controlled by CHUNK_MAX_WORDS / CHUNK_OVERLAP_WORDS in config.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ..state.models import Passage, Candidate, Provenance

# Matches headings like "4.2 Access Control" or "Section 4.2 - Access Control".
_SECTION_RE = re.compile(
    r"^\s*(?:section\s+)?(\d+(?:\.\d+)*)[\.\)]?\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

def _word_windows(text: str) -> list[str]:
    """Split text into overlapping word-count windows."""
    from ..config import settings
    max_words = settings.chunk_max_words
    overlap = settings.chunk_overlap_words
    words = text.split()
    if len(words) <= max_words:
        return [text]
    windows = []
    step = max_words - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + max_words])
        windows.append(chunk)
        if start + max_words >= len(words):
            break
    return windows


def structure_aware_chunk(
    text: str,
    document_id: str,
    version: str = "",
    effective_date: Optional[date] = None,
    scope: str = "global",
    authority_rank: int = 0,
    source_url: str = "",
) -> list[Passage]:
    """Split a SOP document into section-aligned passages with provenance."""
    matches = list(_SECTION_RE.finditer(text))
    passages: list[Passage] = []

    if not matches:
        for window in _word_windows(text):
            passages.append(_make_passage(
                window, document_id, "", version,
                effective_date, scope, authority_rank, source_url))
        return passages

    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section_label = f"{m.group(1)} {m.group(2).strip()}"
        body = text[start:end].strip()
        for window in _word_windows(body):
            passages.append(_make_passage(
                window, document_id, section_label, version,
                effective_date, scope, authority_rank, source_url))
    return passages


def _make_passage(text, doc_id, section, version, eff, scope, auth, url) -> Passage:
    return Passage(
        text=text,
        provenance=Provenance(
            source="SOP", document_id=doc_id, section=section, version=version,
            effective_date=eff, scope=scope, authority_rank=auth, source_url=url,
        ),
    )


def sig_pairs_from_rows(
    rows: list[dict], document_id: str, effective_date: Optional[date] = None,
    source_url: str = "",
) -> list[Candidate]:
    """Turn historical SIG rows ({'question','answer'}) into Candidates."""
    out: list[Candidate] = []
    for r in rows:
        q, a = r.get("question", "").strip(), r.get("answer", "").strip()
        if not q or not a:
            continue
        out.append(Candidate(
            question=q, answer=a,
            comment=r.get("comment", "").strip(),
            provenance=Provenance(
                source="SIG", document_id=document_id, effective_date=effective_date,
                authority_rank=0, source_url=source_url,
            ),
        ))
    return out
