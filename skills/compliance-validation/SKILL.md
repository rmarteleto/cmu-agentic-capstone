---
name: compliance-validation
description: Use when scoring a candidate SIG answer against its cited SOPs to decide whether it is accurate, in-scope, and authoritative enough to keep — the independent critic step.
---

# Compliance Validation

## Overview

Every candidate answer must pass an independent check before it can be shown to
an auditor. The validator is a different actor from the interpreter, so the system
never grades its own draft. Scoring combines an LLM rubric with deterministic
attribute checks.

**Core principle:** Be most suspicious of well-sourced answers that quietly govern
the wrong control. Alignment to the *exact* control beats surface similarity.

## When to Use

- After interpretation, before synthesis.
- Whenever a historical SIG answer is proposed for reuse (confirm still compliant).
- Before reusing any answer that an auditor will rely on.

## Steps

1. Score the candidate 1-5 on three axes:
   - **semantic_alignment** — does it answer the control actually asked?
   - **scope_completeness** — does the cited policy fully cover the question scope?
   - **authority** — is the citation current and from an authoritative document?
2. Run deterministic checks (no tokens): citation present, effective date present,
   scope applicable. Apply penalties for missing metadata.
3. Prune any candidate below the scope-completeness threshold.
4. On conflicting survivors, invoke `precedence-resolution`; if unresolved, escalate.

## Red Flags

- Citation governs a different control than the question asks.
- No effective date / unknown authority on the cited passage.
- Passing an answer because it "sounds right" without checking the citation text.

## Quick Reference

| Score pattern | Action |
|---------------|--------|
| High alignment + scope + authority | Keep; eligible for the answer |
| High alignment, low scope | Prune or narrow the claim |
| Strong wording, wrong control | Reject regardless of fluency |
| Missing date/authority | Penalize; likely escalate |
