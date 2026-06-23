"""Inspect ChromaDB collections — SOP passages and SIG Q/A pairs.

Usage:
    uv run python peek_chroma.py                    # first 5 of each
    uv run python peek_chroma.py --limit 10         # first N of each
    uv run python peek_chroma.py --collection sop   # only SOP corpus
    uv run python peek_chroma.py --collection sig   # only SIG corpus
    uv run python peek_chroma.py --query "encryption policy"  # semantic search
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


def _fmt_sop(ids, docs, metas):
    for i, (id_, doc, m) in enumerate(zip(ids, docs, metas), 1):
        print(f"\n[SOP {i}] id={id_}")
        print(f"  doc    : {m.get('document_id')}")
        print(f"  section: {m.get('section') or '(none)'}")
        print(f"  date   : {m.get('effective_date')}")
        print(f"  scope  : {m.get('scope')}  authority={m.get('authority_rank')}")
        print(f"  text   : {doc[:300]}")


def _fmt_sig(ids, docs, metas):
    for i, (id_, doc, m) in enumerate(zip(ids, docs, metas), 1):
        print(f"\n[SIG {i}] id={id_}")
        print(f"  doc    : {m.get('document_id')}")
        print(f"  date   : {m.get('effective_date')}")
        print(f"  Q      : {m.get('question','')[:150]}")
        print(f"  A      : {m.get('answer','')[:150]}")
        print(f"  comment: {m.get('comment','')[:150]}")


def main():
    p = argparse.ArgumentParser(description="Peek at ChromaDB corpus entries")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--collection", choices=["sop", "sig", "both"], default="both")
    p.add_argument("--query", default=None, help="semantic search query")
    args = p.parse_args()

    from sig_agent.ingestion.indexer import CorpusIndexer
    idx = CorpusIndexer()

    include = ["documents", "metadatas"]

    if args.collection in ("sop", "both"):
        print(f"{'='*60}")
        print(f"SOP CORPUS  ({idx.sop.count()} total passages)")
        print(f"{'='*60}")
        if args.query:
            from sig_agent.llm.client import get_embeddings
            emb = get_embeddings().embed_query(args.query)
            r = idx.sop.query(query_embeddings=[emb], n_results=args.limit,
                              include=include + ["distances"])
            _fmt_sop(r["ids"][0], r["documents"][0], r["metadatas"][0])
        else:
            r = idx.sop.get(limit=args.limit, include=include)
            _fmt_sop(r["ids"], r["documents"], r["metadatas"])

    if args.collection in ("sig", "both"):
        print(f"\n{'='*60}")
        print(f"SIG HISTORY  ({idx.sig.count()} total pairs)")
        print(f"{'='*60}")
        if args.query:
            from sig_agent.llm.client import get_embeddings
            emb = get_embeddings().embed_query(args.query)
            r2 = idx.sig.query(query_embeddings=[emb], n_results=args.limit,
                               include=include + ["distances"])
            _fmt_sig(r2["ids"][0], r2["documents"][0], r2["metadatas"][0])
        else:
            r2 = idx.sig.get(limit=args.limit, include=include)
            _fmt_sig(r2["ids"], r2["documents"], r2["metadatas"])


if __name__ == "__main__":
    sys.exit(main())
