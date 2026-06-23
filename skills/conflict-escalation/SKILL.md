---
name: conflict-escalation
description: Use when reasoning branches reach conflicting or unsupported conclusions and the system must route to a human early rather than guessing — the human-in-the-loop gate.
---

# Conflict Escalation

## Overview

Some items cannot be answered safely by the agent. Escalation is a first-class
outcome, not a failure. It triggers when there is no confident grounding, or when
two reasoning branches cite SOPs that the precedence rules cannot reconcile. The
escalation can fire mid-search — as soon as the conflict appears — not only at the end.

**Core principle:** When in doubt, escalate with evidence. A flagged item a human
reviews is far cheaper than a wrong answer an auditor catches.

## When to Use

- No retrieved passage clears the relevance threshold (NO MATCH).
- Two surviving branches cite conflicting SOPs and `precedence-resolution` returns
  ESCALATE.
- Confidence is below the team's review bar.
- A historical SIG answer conflicts with current SOPs and cannot be reconciled.

## Steps

1. Stop the reasoning for this item immediately — do not pick a higher-scored
   branch to "break" a real conflict.
2. Assemble the conflicting passages (or the empty-result note) with full
   provenance (document_id, section, version, effective_date, scope).
3. Set status `escalated` and `needs_human_review = true`; emit no answer text.
4. Present the passages to the reviewer side by side, with the reason for escalation.
5. Record the escalation in the session log for the audit trail.

## Red Flags

- "Resolving" a genuine conflict by averaging, summarizing, or trusting the score.
- Deferring every check to final synthesis, so conflicts surface too late.
- Escalating without attaching the evidence the human needs to decide.

## Quick Reference

| Trigger | Outcome |
|---------|---------|
| No match above threshold | Escalate → write-new with human flag |
| Unresolvable SOP conflict | Escalate → side-by-side human review |
| Low confidence | Escalate → human confirmation |
| Resolvable by precedence | Do NOT escalate — apply the rule |
