"""Hybrid dual-corpus retrieval with reranking and a relevance gate.

Per the M3/M4 design:
  * Semantic similarity (Chroma) catches rephrased questions.
  * BM25 keyword arm preserves exact-term matching (control IDs, acronyms).
  * Scores are fused, then a cross-encoder reranker re-scores for *true*
    relevance to defeat the "topically close but wrong control" failure mode.
  * A relevance threshold treats weak matches as "no match found", which the
    Orchestrator routes to fresh synthesis with a human flag.
The retriever returns the top-B candidates from EACH corpus so the reasoning
core can still detect conflicts and compare scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings
from ..state.models import Passage, Candidate
from ..ingestion.indexer import CorpusIndexer, meta_to_prov


@dataclass
class RetrievalResult:
    sop_passages: list[Passage] = field(default_factory=list)
    sig_candidates: list[Candidate] = field(default_factory=list)
    max_relevance: float = 0.0          # best fused score across corpora

    @property
    def is_match(self) -> bool:
        return self.max_relevance >= settings.relevance_threshold


def _minmax(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


class HybridRetriever:
    def __init__(self, indexer: CorpusIndexer | None = None, reranker=None):
        self.indexer = indexer or CorpusIndexer()
        # Build the cross-encoder reranker by default (settings.enable_reranker).
        # build_reranker() returns None if sentence-transformers is unavailable,
        # so retrieval degrades gracefully to the fused hybrid score.
        if reranker is None and settings.enable_reranker:
            reranker = build_reranker()
        self._reranker = reranker          # optional cross-encoder
        self._embed = None

    # ---- public API ---------------------------------------------------
    def retrieve(self, question: str) -> RetrievalResult:
        k = settings.branch_factor
        sop = self._search_collection(self.indexer.sop, question, k, corpus="SOP")
        sig = self._search_collection(self.indexer.sig, question, k, corpus="SIG")

        sop = self._rerank(question, sop)
        sig = self._rerank(question, sig)

        passages = [self._to_passage(d, m, s) for d, m, s in sop]
        candidates = [self._to_candidate(m, s) for _, m, s in sig]

        best = max([p.score for p in passages] + [c.score for c in candidates] + [0.0])
        return RetrievalResult(sop_passages=passages, sig_candidates=candidates,
                               max_relevance=best)

    # ---- internals ----------------------------------------------------
    def _embed_query(self, text: str) -> list[float]:
        if self._embed is None:
            from ..llm import get_embeddings
            self._embed = get_embeddings()
        return self._embed.embed_query(text)

    def _search_collection(self, collection, question, k, corpus):
        """Return list of (document, metadata, fused_score)."""
        res = collection.query(
            query_embeddings=[self._embed_query(question)],
            n_results=max(k * 3, k),       # over-fetch, then rerank/trim to k
            include=["documents", "metadatas", "distances"],
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        if not docs:
            return []
        # cosine distance -> similarity, normalised
        sem = _minmax([1.0 - d for d in dists])
        kw = self._bm25_scores(question, docs)
        fused = [
            settings.semantic_weight * s + settings.keyword_weight * w
            for s, w in zip(sem, kw)
        ]
        ranked = sorted(zip(docs, metas, fused), key=lambda t: t[2], reverse=True)
        return ranked[:k]

    @staticmethod
    def _bm25_scores(question: str, docs: list[str]) -> list[float]:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return [0.0 for _ in docs]
        corpus = [d.lower().split() for d in docs]
        bm25 = BM25Okapi(corpus)
        raw = bm25.get_scores(question.lower().split())
        return _minmax(list(raw))

    def _rerank(self, question, ranked):
        """Cross-encoder reranking for true relevance (optional)."""
        if not ranked or self._reranker is None:
            return ranked
        pairs = [(question, d) for d, _, _ in ranked]
        scores = self._reranker.predict(pairs)
        norm = _minmax(list(scores))
        rescored = [(d, m, ns) for (d, m, _), ns in zip(ranked, norm)]
        return sorted(rescored, key=lambda t: t[2], reverse=True)

    @staticmethod
    def _to_passage(doc, meta, score) -> Passage:
        return Passage(text=doc, provenance=meta_to_prov(meta), score=float(score))

    @staticmethod
    def _to_candidate(meta, score) -> Candidate:
        return Candidate(
            question=meta.get("question", ""),
            answer=meta.get("answer", ""),
            provenance=meta_to_prov(meta),
            score=float(score),
        )


def build_reranker():
    """Lazily construct a local cross-encoder reranker if available."""
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception:
        return None
