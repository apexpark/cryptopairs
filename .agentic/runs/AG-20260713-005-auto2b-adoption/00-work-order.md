---
id: AG-20260713-005
title: Adopt and refresh AUTO-2B shadow allowlist (PR #244) under Tier 3
repo: cryptopairs
base_branch: main
working_branch: codex/auto2b-shadow-dynamic-allowlist
worker_tier: T1
required_evidence_level: E2
status: dispatched
---

# Work Order

## Objective

Adopt the pre-migration AUTO-2B slice (PR #244, authored by Codex before
the governance scaffold existed) and refresh it under the Tier 3 flow:
merge current `main` in, verify the two open P2 review findings are fixed,
bring records current, and route it through cross-model dual review.

## Scope

In: merge of `main` (conflict resolution in `docs/AGENT_STATE.md`,
`CHANGELOG.md` keeping both histories), `.github/CODEOWNERS` add-a-line for
`autopilot_shadow_allowlist.py`, register rows (PR #248 authorization,
OP-21 adoption decision, AG-005), AGENT_STATE curation (pin, GOV-SCAFFOLD-4
→ Merged), this run folder. The Codex-authored slice content (proposal,
contract, tool, tests, runbook) is reviewed, not rewritten.
Out: any behavior change to the shadow tool beyond review findings; any
control coupling from shadow output to paper or live eligibility.

## Review plan (model diversity)

Original content author = Codex → Claude performs the multi-angle inner
review of that content (cross-model). Curation commits author = Claude →
Codex performs the exact-SHA Tier 3 review of the refreshed head
(cross-model). Neither model sole-reviews its own work.

## Acceptance criteria

1. Shadow output remains advisory-only: no path from snapshot artifacts to
   `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`, paper entries, execution
   intents, dispatch, or exchange calls.
2. The two pre-migration P2s verified fixed (trade-row dedupe;
   finite-float thresholds) — confirmed, threads resolved.
3. `pytest tools/scripts/tests/test_autopilot_shadow_allowlist.py` green
   locally (13 passed) and full CI green.
4. Records current; conflicts resolved without losing either history.

## Stop conditions

Any coupling of shadow output to eligibility or execution → stop and
escalate; that is AUTO-2C+ territory requiring its own slice and gates.
