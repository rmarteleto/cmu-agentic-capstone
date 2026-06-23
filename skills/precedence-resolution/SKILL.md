---
name: precedence-resolution
description: Use when two or more SOP passages give conflicting guidance for the same SIG control and you must decide which governs, deterministically and auditably.
---

# Precedence Resolution

## Overview

When retrieved SOP passages conflict, the answer must be decided by a fixed,
reproducible rule — never by the LLM's preference — because an auditor must be
able to replay the decision. Resolution is implemented in code
(`sig_agent.reasoning.precedence.resolve_precedence`) and surfaced as a tool.

**Core principle:** Resolve by rule, in order. If the rules cannot break the tie,
do NOT answer — escalate to a human with the passages side by side.

## When to Use

- Two SOP passages answer the same control differently.
- The compliance-critic finds two surviving candidates with conflicting citations.
- A historical SIG answer disagrees with current SOP text.

## Steps

Apply the rules in strict order; stop at the first that yields a single winner.

1. **Newest effective date wins.** Compare `effective_date` metadata; the most
   recent governing passage supersedes older ones.
2. **Narrowest applicable scope wins.** If dates tie, prefer the more specific
   scope (`control` > `system` > `business_unit` > `division` > `global`).
3. **Highest document authority wins.** If scope ties, prefer the higher
   `authority_rank`.
4. **Otherwise escalate.** If still tied, return ESCALATE — present the conflicting
   passages to a human for side-by-side review. Do not generate an answer.

## Red Flags — stop and escalate

- Breaking a tie by LLM judgment, averaging, or picking the higher relevance score.
- Comparing passages that are missing `effective_date` or `scope` metadata —
  treat missing metadata as a reason to escalate, not to guess.
- Resolving silently at synthesis time. Run this check at each beam depth so a
  conflict surfaces as early as it appears.

## Quick Reference

| Situation | Decision |
|-----------|----------|
| Different effective dates | Newest wins |
| Same date, different scope | Narrowest scope wins |
| Same date + scope, different authority | Highest authority wins |
| All tie | Escalate to human |
