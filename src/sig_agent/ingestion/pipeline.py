"""Ingestion pipeline: local/Azure files -> chunk -> embed -> Chroma.

Run this whenever compliance updates SOPs or SIG history. Keeping
ingestion explicit (rather than autonomous corpus rewriting) is the
human-led, auditable update path chosen in M2.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from .chunking import structure_aware_chunk, sig_pairs_from_rows
from .indexer import CorpusIndexer

log = logging.getLogger(__name__)


def ingest_sops(docx_paths: list[str], indexer: CorpusIndexer | None = None) -> int:
    """Index SOP .docx files from local paths into the SOP corpus."""
    from docx import Document
    indexer = indexer or CorpusIndexer()
    total = 0
    log.info("SOP ingest start — %d file(s)", len(docx_paths))
    for path in docx_paths:
        try:
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            doc_id = os.path.splitext(os.path.basename(path))[0]
            eff = _file_date(path)
            passages = structure_aware_chunk(
                text, document_id=doc_id, effective_date=eff, source_url=path,
            )
            indexed = indexer.index_sop(passages)
            total += indexed
            log.info("  [ok] %s  words=%d  chunks=%d  date=%s",
                     doc_id, len(text.split()), indexed, eff)
        except Exception as exc:
            log.error("  [ERROR] %s: %s", path, exc)
    log.info("SOP ingest complete — %d passages indexed", total)
    return total


def ingest_sigs(xlsx_paths: list[str], indexer: CorpusIndexer | None = None) -> int:
    """Index historical (filled) SIG workbooks as candidate answers.

    The SIG-history corpus makes ``validated_from_history`` reachable and
    feeds the date heuristic pre-filter. Each source is a prior questionnaire —
    either an ``.xlsx`` workbook (question + answer columns) or a ``.txt`` export
    (Question/Answer/Comment blocks). The file's modified date stands in as the
    effective date for precedence/heuristic comparisons.
    """
    indexer = indexer or CorpusIndexer()
    total = 0
    log.info("SIG ingest start — %d file(s)", len(xlsx_paths))
    for path in xlsx_paths:
        try:
            rows = _read_sig_rows(path)
            eff = _file_date(path)
            candidates = sig_pairs_from_rows(
                rows, document_id=os.path.basename(path),
                effective_date=eff, source_url=path,
            )
            indexed = indexer.index_sig(candidates)
            total += indexed
            log.info("  [ok] %s  pairs=%d  date=%s", os.path.basename(path), indexed, eff)
        except Exception as exc:
            log.error("  [ERROR] %s: %s", path, exc)
    log.info("SIG ingest complete — %d Q/A pairs indexed", total)
    return total


def _read_sig_rows(path: str) -> list[dict]:
    """Read SIG Q/A rows from a .txt export or an .xlsx workbook."""
    if path.lower().endswith(".txt"):
        from .sig_text import parse_sig_text
        return parse_sig_text(path)
    from ..io import read_qa_pairs
    return read_qa_pairs(path)


def _file_date(path: str) -> date | None:
    try:
        return date.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None
