---
name: hybrid-retrieval
description: Use when fetching grounding evidence for a SIG question from the SOP and SIG corpora, to balance semantic recall with exact-term precision and avoid topically-close-but-wrong matches.
---

# Hybrid Retrieval

## Overview

Grounding comes from two corpora: SOP policy units (ground truth) and historical
SIG Q/A pairs (candidate answers). A purely semantic search drifts to topically
similar but wrong controls; a purely keyword search misses rephrasings. The skill
blends both, reranks, and applies a relevance gate.

**Core principle:** A weak match is worse than no match — it survives casual
review. Treat sub-threshold results as "no match found".

## When to Use

- Any SIG question that needs grounding before interpretation.
- Control IDs / acronyms are present (keyword arm matters).
- The question is paraphrased relative to historical SIGs (semantic arm matters).

## Steps

1. Embed the question with the SAME model used at ingestion.
2. Run semantic search (Chroma) and BM25 keyword search over each corpus.
3. Fuse the scores (weighted) and rerank the top candidates with a cross-encoder
   for true relevance.
4. Retrieve the top-B from EACH corpus (default 5) so conflicts and scope
   differences remain visible to the reasoning core.
5. Apply the relevance threshold. If nothing clears it, return NO MATCH.

## Red Flags

- Returning a single global "best" passage and discarding the rest — you lose the
  ability to detect conflicts.
- Mixing embedding models between ingestion and query time.
- Paraphrasing retrieved text — pass exact passages so they can be cited.

## Quick Reference

| Signal | Arm that catches it |
|--------|---------------------|
| Rephrased question | Semantic similarity |
| Exact control ID / acronym | BM25 keyword |
| Topically close, wrong control | Cross-encoder rerank + threshold |
