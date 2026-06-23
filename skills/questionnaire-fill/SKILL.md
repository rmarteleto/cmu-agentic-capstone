---
name: questionnaire-fill
description: Use when completing a full SIG spreadsheet end-to-end — reading questions from rows, running each through the pipeline, and writing back answers, statuses, citations, and review flags.
---

# Questionnaire Fill

## Overview

The bulk workflow: take a SIG spreadsheet (one question per row) and return a
filled copy with the agent's answer, status, confidence, citations, and a
human-review flag per row. Items run in parallel; escalations are surfaced, not hidden.

**Core principle:** Every row ends in one of three explicit states —
validated_from_history, synthesized_new, or escalated. None are answered silently.

## When to Use

- A customer/auditor sends a SIG spreadsheet to complete.
- A batch of questionnaire items needs answering in one pass.

## Steps

1. Read the question column from the spreadsheet (default header "Question").
2. Run all items through `sig_answer_batch` (parallel fan-out), or per-item via the
   subagent pipeline when a human wants to watch each step.
3. Write back columns: Agent Answer, Status, Needs Review, Confidence, Citations.
4. Summarize: count of answers flagged for human review; list escalated rows first.
5. In interactive mode, walk the reviewer through every `synthesized_new` and
   `escalated` row before delivering the file.

## Red Flags

- Delivering a filled sheet without surfacing how many rows need review.
- Overwriting the original questionnaire — always write a new copy.
- Treating an escalated row as blank — it must carry the reason and evidence.

## Quick Reference

| Column | Meaning |
|--------|---------|
| Status | validated_from_history / synthesized_new / escalated |
| Needs Review | YES for new or escalated answers |
| Citations | SOP/SIG provenance backing the answer |
| Confidence | Engine confidence (0–1) |
