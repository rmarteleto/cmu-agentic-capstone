"""Chroma indexer — builds and maintains the two corpora.

Two collections: SOP policy units (ground truth) and SIG Q/A pairs (candidate
answers). Embeddings use the same model later used to embed incoming questions
(enforced via llm.get_embeddings). Provenance is stored as Chroma metadata so
it round-trips into retrieval and the precedence engine.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..config import settings
from ..state.models import Passage, Candidate, Provenance


def _prov_to_meta(p: Provenance) -> dict:
    return {
        "source": p.source,
        "document_id": p.document_id,
        "section": p.section,
        "version": p.version,
        "effective_date": p.effective_date.isoformat() if p.effective_date else "",
        "scope": p.scope,
        "authority_rank": p.authority_rank,
        "source_url": p.source_url,
    }


def meta_to_prov(m: dict) -> Provenance:
    ed = m.get("effective_date") or ""
    return Provenance(
        source=m.get("source", ""),
        document_id=m.get("document_id", ""),
        section=m.get("section", ""),
        version=m.get("version", ""),
        effective_date=date.fromisoformat(ed) if ed else None,
        scope=m.get("scope", "global"),
        authority_rank=int(m.get("authority_rank", 0) or 0),
        source_url=m.get("source_url", ""),
    )


class CorpusIndexer:
    def __init__(self):
        import chromadb
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._embed = None
        self.sop = self._client.get_or_create_collection(settings.sop_collection)
        self.sig = self._client.get_or_create_collection(settings.sig_collection)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._embed is None:
            from ..llm import get_embeddings
            self._embed = get_embeddings()
        return self._embed.embed_documents(texts)

    def index_sop(self, passages: list[Passage]) -> int:
        if not passages:
            return 0
        self.sop.upsert(
            ids=[p.passage_id for p in passages],
            documents=[p.text for p in passages],
            embeddings=self._embed_texts([p.text for p in passages]),
            metadatas=[_prov_to_meta(p.provenance) for p in passages],
        )
        return len(passages)

    def index_sig(self, candidates: list[Candidate]) -> int:
        if not candidates:
            return 0
        # Embed the *question* so semantic lookup matches incoming questions.
        docs = [f"Q: {c.question}\nA: {c.answer}" for c in candidates]
        self.sig.upsert(
            ids=[c.provenance.document_id + ":" + str(i) for i, c in enumerate(candidates)],
            documents=docs,
            embeddings=self._embed_texts([c.question for c in candidates]),
            metadatas=[
                {**_prov_to_meta(c.provenance), "question": c.question,
                 "answer": c.answer, "comment": c.comment}
                for c in candidates
            ],
        )
        return len(candidates)
