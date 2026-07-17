---
id: AG-20260717-010
title: B2-c shadow scorer selector-view input
repo: cryptopairs
base_branch: main
working_branch: codex/b2c-selector-view-input
worker_tier: T1
required_evidence_level: E3
status: dispatched
---

# Work Order

## Objective

Implement AUTO-2B.2 slice B2-c per the merged proposal §4.2 and OP-45(b):
extend the artifact-only shadow scorer so it can consume B2-b selector-view
capture JSONL, emit the already-contracted v2 selector-view and universe
blocks, and measure selector-view churn separately from realized-paper churn.
The output remains advisory and cannot control paper or live eligibility.

## Slice Loop Check

- New input consumed: the merged B2-a v2 contracts, B2-b complete-tick
  selector-view records, OP-45(b), and the accepted B2-c design.
- New state transition: selector-view capture becomes consumable advisory
  evidence; it does not become an eligibility input.
- New artifact/runtime/user value: universe-wide bucket metrics,
  prominent/marginal discovery, static/paper overlap, and per-stream churn.
- Why this is not repeating the prior slice: B2-b records complete selector
  ticks; B2-c validates and summarizes those records.
- Stop/defer condition: any eligibility coupling, capture, host action,
  scheduler, live path, OBS-1/OBS-3 work, or contract expansion beyond the
  merged v2 shape stops this slice.

## Scope

In:

- `tools/scripts/autopilot_shadow_allowlist.py`: optional repeatable
  `--selector-view-jsonl` input; complete-tick validation; selector-only
  metrics; universe comparison; per-stream churn; JSON/Markdown rendering.
- `tools/scripts/tests/test_autopilot_shadow_allowlist.py`: deterministic
  replay, malformed/truncated-input, stream-segregation, legacy-compatibility,
  schema-validation, and CLI/reporting coverage.
- `docs/playbooks/autopilot-shadow-allowlist-runbook.md`: bounded B2-d input
  consumption commands and interpretation only; no capture start.
- `CHANGELOG.md`, `docs/AGENT_STATE.md`, `.agentic/registers/agent-runs.md`,
  and this run folder for versioning and audit state.
- Existing contracts/examples are binding validation targets; no schema shape
  change is planned.

Out:

- `autopilot_observe.py`, capture execution, host commands, deployment,
  secrets, services, paper/live entry eligibility, champion promotion,
  schedulers/daemons/unattended loops, OBS-1, OBS-3, and AUTO-2C+.
- Any outcome estimate, realized bps, fill, or PnL claim derived from
  selector-view rows.

## Binding Implementation Rules

1. No selector input preserves the current version-1 output and failure
   behavior.
2. Selector input emits the existing version-2 optional blocks only after all
   input ticks validate as complete against their leading manifests.
3. A candidate is `selector_view_prominent` when observed in `TRADE_NOW` at
   least once; candidates never observed there are `selector_view_marginal`.
   This is deterministic and consistent with the binding example's prominent
   row having a `time_in_tradable_now_ratio` below 0.5.
4. Selector score summaries use the selector-stated `selected_score_z`; edge
   summaries use selector-stated `net_edge_bps`. Neither is an outcome.
5. Gate-failure reasons come only from the dedicated decision/blocked/watch
   reason fields, ranked by frequency then lexical order; general rationale
   codes are not reclassified as failures.
6. Realized-paper aggregates and selector-view aggregates are built by
   separate code paths. Only set-membership comparisons appear in `universe`.

## Acceptance Criteria

1. Complete manifests, including an empty-universe tick, produce schema-valid
   v2 snapshots with deterministic selector-view metrics and universe counts.
2. Truncated ticks, count mismatches, unmanifested rows, duplicate ticks or
   duplicate candidates within a tick, invalid identities, non-finite values,
   and selector rows carrying outcome/PnL/fill fields fail closed without an
   output artifact.
3. `churn.selector_view` compares prominent sets only when both snapshots
   contain selector-view evidence; realized churn remains unchanged.
4. A targeted E4 regression test proves selector-view aggregates cannot
   consume or emit realized-outcome evidence, and every new regression test is
   mutation-checked against pre-fix code.
5. With no selector-view input, existing v1 tests and generated output remain
   unchanged.
6. Focused and full `tools/scripts` Python suites pass; schemas/examples and
   generated v1/v2 artifacts validate; final counts are re-derived in a clean
   detached worktree after the last edit.
7. Multi-angle inner review is clean, then the Tier 3 PR receives a fresh
   Claude exact-SHA review before any Operator merge decision.

## Stop Conditions

- The merged v2 contract cannot express a required B2-c quantity without a
  shape change.
- Selector-view data would need to control or mutate paper/live eligibility.
- Correctness would require capture, host access, a scheduler, deployment,
  secrets, or an unattended loop.
- Work would enter OBS-1, OBS-3, AUTO-2C, or any file outside the scope above.

