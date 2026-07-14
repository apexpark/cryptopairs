---
id: AG-20260713-009
title: B2-b selector-view capture (observe tool)
repo: cryptopairs
base_branch: main
working_branch: claude/b2b-selector-view-capture
worker_tier: T1
required_evidence_level: E3
status: dispatched
---

# Work Order

## Objective

Implement AUTO-2B.2 slice B2-b per the merged proposal §4.1: teach
`autopilot_observe.py` to capture the cue endpoint's full selector view
(all three buckets) as observation-only v2 selector-view rows, behind a
fail-closed default env, bounded, with a runbook that requires a read-only
disk estimate before any capture starts.

## Design decisions (for inner review to challenge)

- **Pure observational mode**: when `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW`
  is true, `run_once` emits selector-view rows for all buckets and does NOT
  invoke the entry-candidate path. Rationale: a dedicated wide run produces
  a clean single-purpose artifact and avoids doubling disk with
  uniformly-blocked entry rows. The entry code path is unchanged (untouched),
  just not invoked in this mode. The narrow paper-feeding run keeps the
  default (false) and is byte-identical.
- Source-unavailable / malformed-response system records still fire before
  the mode branch — fail-closed preserved.
- Bounded loop via `AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS` (default None =
  unbounded = current behaviour; only the wide run sets it).

## Scope

In: `tools/scripts/autopilot_observe.py`,
`tools/scripts/tests/test_autopilot_observe.py`,
`docs/playbooks/autopilot-observe-only-runbook.md`, registers, state,
CHANGELOG, this run folder.
Out: `autopilot_shadow_allowlist.py` (B2-c), any capture start (B2-d, operator).

## Acceptance criteria

1. Generated selector-view records validate against the merged v2 schema
   for all three buckets; malformed buckets/rows skip fail-closed.
2. Disabled default ⇒ behaviour byte-identical to pre-slice (tested).
3. No outcome fields on any emitted row; capture drives no eligibility or
   execution path.
4. 143 tools/scripts tests green (importlib mode); inner review clean;
   Tier 3 flow on the PR.

## Stop conditions

Any coupling of selector-view capture to eligibility/execution, or any
change to the entry-candidate emission when the flag is false → stop.
