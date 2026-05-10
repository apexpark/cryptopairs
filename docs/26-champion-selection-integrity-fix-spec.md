# Champion Selection Integrity Fix Spec

## Purpose

Define a safe, verifiable fix for the current champion-selection integrity issue in the strategy service.

This document separates:

1. facts verified in the local repo
2. facts verified on the Hetzner runtime on May 2, 2026
3. proposals for a safe implementation path

## Problem Summary

The current runtime produces live cues and rewrites `strategy_selected_signal`, but that does not prove healthy challenger competition.

The core concern is that the system appears to be preserving or reapplying incumbent champions without giving operators or downstream diagnostics a clear, auditable separation between:

1. the best variant in the current evaluation window
2. the stored incumbent champion
3. the final transition decision that kept or replaced the incumbent

That ambiguity weakens three things at once:

1. selection correctness
2. operator trust in `Trade` / `Research Bench`
3. safe promotion of signals toward tradability

## Verified Facts

### Local Repo Facts

Verified in this workspace:

- `services/strategy-service/src/lib.rs:931-940` selects the highest `opportunity_score` variant during evaluation.
- `services/strategy-service/src/lib.rs:994-1023` emits that value as `cue.selected_variant` and `cue.opportunity_score`.
- `services/strategy-service/src/main.rs:900-933` persists the selected row through `decide_champion_transition(...)` and `upsert_selected_signal(...)`.
- `services/strategy-service/src/main.rs:2010-2068` compares the stored champion with `evaluation.cue.selected_variant`.
- `services/strategy-service/src/main.rs:4645-4674` rewrites the public cue back to the stored preferred signal when they differ, and can block action with `CHAMPION_DRIFT_BLOCKED`.
- in that rewrite path, only `cue.selected_variant` and `cue.opportunity_score` are overwritten; dependent cue fields such as `direction_hint`, `confidence_band`, `expected_hold_bars`, `setup_gate`, and the selected-score-derived directional slice remain challenger-derived from `services/strategy-service/src/lib.rs:941-1023`.
- `services/strategy-service/src/main.rs:920-933` records drift rows only for `KEEP_CHAMPION` and `PROMOTE_CHALLENGER`, not `INITIALIZE` or `UNCHANGED`.

Implication:

- the local repo already mixes two meanings into one surface
- worse, the current drift rewrite can present a champion label and score beside challenger-derived directional and gate metadata

### Hetzner Runtime Facts

Verified on host `cryptopairs` and public API reads on May 2, 2026:

- `strategy_selected_signal` has `48` rows total.
- `12` of those rows are `LEGACY_ROW_FALLBACK` on `1m`.
- live cue mismatch counts, comparing displayed/stored selected variant with the highest `opportunity_score` variant in the same response:
  - `1m`: `11 / 16`
  - `15m`: `13 / 16`
  - `1h`: `11 / 16`
  - overall: `35 / 48`
- mismatch breakdown by source:
  - `AUTO_CHAMPION`: `26 / 36`
  - `LEGACY_ROW_FALLBACK`: `9 / 12`
- `strategy_champion_drift_events` has historical rows, but `0` rows after the current `rc/live-trial` cutover at `2026-04-19 03:26:54 UTC`.
- `strategy_candidate_runs = 0`
- `strategy_candidate_probation = 0`
- `strategy_candidate_actions = 0`

Implication:

- the current runtime is alive and rewriting selected rows
- but post-cutover it is not producing observable challenger-vs-champion decision evidence

### Host-Only Runtime Difference

The Hetzner runtime contains newer config/provenance plumbing that is not present in this local workspace:

- host `/opt/cryptopairs/services/strategy-service/src/main.rs:1565-1587` loads the existing selected config before evaluation
- host `/opt/cryptopairs/services/strategy-service/src/lib.rs:977-1005` prefers that configured variant when present and valid
- host `/opt/cryptopairs/services/strategy-service/src/main.rs:2746-2848` then uses `evaluation.cue.selected_variant` as the challenger in champion transition

Implication:

- the local repo shows the public-surface ambiguity clearly
- the live host appears to have an additional deeper issue: incumbent bias can enter before transition logic even runs

## Root Cause Model

This is the current likely failure shape:

1. the service stores a champion row for a pair/timeframe
2. evaluation computes or inherits a candidate variant
3. the transition step compares champion and challenger
4. the public cue surface may then be partially rewritten to match the stored champion
5. operators can read a hybrid cue made from champion identity plus challenger-derived telemetry

On the host runtime, there is a stronger form of the same problem:

1. the incumbent config is loaded before evaluation
2. evaluation may prefer the incumbent directly
3. the transition step receives an incumbent-shaped challenger
4. the steady-state result becomes repeated `UNCHANGED` behavior
5. no drift rows are recorded because `UNCHANGED` is not persisted to `strategy_champion_drift_events`

## Desired End State

The system must make three states explicit and auditable:

1. `evaluated_best_variant`
   - the highest-scoring variant from the current neutral evaluation
2. `stored_champion_variant`
   - the incumbent variant already persisted for this pair/timeframe
3. `transition_decision`
   - one of `INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, `PROMOTE_CHALLENGER`

The safe trading end-state is:

1. evaluation is neutral and deterministic
2. champion retention preserves the existing score-delta hysteresis threshold in this repo and does not add time-based cooldown logic unless that behavior is first reproduced and reviewed from the host branch
3. any operator-facing champion cue is internally consistent across all dependent fields
4. the UI and API expose champion state and challenger state separately
5. legacy fallback provenance is a temporary repair state, not a steady-state operator concept
6. ambiguous selection state remains fail-closed for tradability

## Non-Goals

This fix is not intended to:

1. make previously blocked rows automatically tradable
2. redesign optimizer candidate generation in the same change
3. remove operator approval, reconcile, integrity, or kill-switch gates
4. redefine trade-now policy rules unrelated to selection integrity

## Invariants

Any implementation must satisfy these invariants:

1. the challenger candidate is derived from the current evaluation window, not from the persisted champion label alone
2. if the persisted champion is projected into the public cue, all dependent cue fields must be recomputed against the champion on the same evaluation snapshot
3. all transition outcomes are observable
4. if transition state is ambiguous or missing, trade eligibility remains blocked
5. replaying the same candle history yields the same best variant, champion decision, and persisted outcome

## Immediate Safety Action

Until Slice A and Slice B are complete:

1. keep `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`
2. do not enable live `ENTRY` or `EXIT` dispatch for this strategy runtime
3. treat current cues as research-visible but not execution-trustworthy

This is the explicit bridging safeguard required by `docs/12-risk-and-execution-policy.md`:

- fail closed when selection integrity is not proven
- do not rely on operator interpretation of ambiguous cue state

## Proposed Fix

### Slice A: Separate Evaluation From Champion Presentation

Scope:

- local repo first
- no liberalization of trade eligibility

Changes:

1. Keep neutral evaluation authoritative inside `evaluate_pair(...)`.
2. Preserve the evaluated best variant separately from the stored champion throughout the request path.
3. Introduce an explicit selection diagnostics object in the cue response.
4. Keep the current operator-facing cue contract stable in the first rollout by making any champion-projected cue internally consistent.

Default design choice for Slice A:

1. when drift exists, do not leave the response as a hybrid cue
2. either recompute the operator-facing cue against the stored champion using the same evaluation snapshot, or fail closed for champion projection
3. expose the evaluated-best track side by side so consumers can compare both states explicitly

Preferred first implementation:

1. `cue` remains the operator-facing presented track
2. if champion projection is applied, all variant-dependent fields are recomputed for the champion before response emission
3. `selection_state` carries the evaluated-best track, stored champion track, and transition metadata
4. if champion-consistent recomputation cannot be performed safely, the service should leave the cue blocked and annotate the failure rather than return a hybrid

Recommended additive response shape:

- `cue.selection_state.best_variant`
- `cue.selection_state.best_opportunity_score`
- `cue.selection_state.best_direction_hint`
- `cue.selection_state.best_confidence_band`
- `cue.selection_state.stored_champion_variant`
- `cue.selection_state.stored_champion_score`
- `cue.selection_state.stored_champion_direction_hint`
- `cue.selection_state.stored_champion_confidence_band`
- `cue.selection_state.transition_decision`
- `cue.selection_state.score_delta_to_champion`
- `cue.selection_state.drift_active`
- `cue.selection_state.source`
- `cue.selection_state.validation_state`

Compatibility rule:

- do not change the meaning of existing required fields in the first slice
- add new optional fields first
- keep `cue` internally consistent if it remains the operator-facing champion projection
- deprecate ambiguous use of `selected_variant` only after clients have migrated

### Slice B: Make Transition Accounting Complete

Scope:

- internal behavior
- additive observability

Changes:

1. Record `INITIALIZE` and `UNCHANGED` transition outcomes as first-class metrics.
2. Distinguish:
   - `INITIALIZE`: no incumbent champion existed for the row
   - `UNCHANGED`: challenger equals champion
   - `KEEP_CHAMPION`: challenger differs but loses by the existing score-delta threshold in this repo
   - `PROMOTE_CHALLENGER`: challenger wins
3. Add an anomaly alert when:
   - `selected_rows_written > 0`
   - but `INITIALIZE + UNCHANGED + KEEP_CHAMPION + PROMOTE_CHALLENGER = 0`
   - over a meaningful runtime window

This closes the current blind spot where rows can update indefinitely without proving decision-path health.

Default accounting choice:

1. keep `strategy_champion_drift_events` for true drift decisions only:
   - `KEEP_CHAMPION`
   - `PROMOTE_CHALLENGER`
2. emit `strategy_selection_transition_total{decision}` for all four decisions:
   - `INITIALIZE`
   - `UNCHANGED`
   - `KEEP_CHAMPION`
   - `PROMOTE_CHALLENGER`
3. only add a persisted all-decisions table later if metric-only auditability proves insufficient

### Slice C: Remove Incumbent Bias In Host Runtime

Scope:

- applies to the host/runtime branch that carries selected-config provenance
- blocked until that host lineage is reproduced in a reviewable local branch

Changes:

0. Before coding Slice C:
   - capture host `git rev-parse HEAD`
   - capture host branch name and dirty status
   - diff or import the host runtime lineage into a local reviewable branch
   - confirm the host-only incumbent-bias code path against version-controlled code
1. Ensure evaluation computes the best variant neutrally from the current candle snapshot.
2. Use persisted champion config as comparison input, not as preselection input.
3. Keep per-variant parameterization explicit:
   - if a variant requires stored parameters, those parameters must be loaded per variant and compared fairly
   - if that cannot be done safely, the row must fail closed into a repair state instead of inheriting the incumbent silently

This is the highest-risk engineering slice and should follow Slice A instrumentation, not precede it.

### Slice D: Recanonicalize Legacy Rows

Scope:

- maintenance action
- fail-closed repair path

Changes:

1. Treat `LEGACY_ROW_FALLBACK` as a migration-only internal state.
2. Add a maintenance/report path that scans affected rows and attempts recanonicalization.
3. Recanonicalize only when:
   - the pair/timeframe evaluates successfully
   - the winning variant is explicit
   - the persisted config can be serialized canonically
   - the resulting row is attributable to a trusted current source
4. Leave unresolved rows blocked.

Important:

- recanonicalized does not mean tradable
- it only means the row is no longer relying on legacy provenance
- recanonicalized rows must surface a distinct validation state until a current non-legacy approval path confirms them

## Contract Changes

### Required If Slice A Is Implemented

Affected contracts:

- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/examples/strategy_pairs_cues_response.example.json`

Recommended change:

- add an optional `selection_state` object under `cue`
- update the cue example to show both champion-projected and evaluated-best diagnostics
- keep all new fields explicitly declared because nested objects in the current schema use `additionalProperties: false`

Reason:

- current response shape makes it too easy for consumers to confuse the best live evaluation with the stored champion
- `Trade` and `Research Bench` surfaces must consume `selection_state` and must not treat `cue.selected_variant` as sole ground truth once Slice A ships

### Recommended For Operational Reporting

Affected contracts:

- `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
- `specs/examples/strategy_pairs_reoptimize_response.example.json`
- `specs/contracts/strategy_maintenance_action_response.schema.json`
- `specs/contracts/strategy_maintenance_latest_response.schema.json`

Recommended additive fields:

- `initialize_decisions`
- `unchanged_decisions`
- `selection_drift_pairs`
- `selection_mismatch_pairs`
- `legacy_rows_seen`
- `legacy_rows_recanonicalized`
- `legacy_rows_blocked`

## Safe Contract Strategy

Preferred approach:

1. add new fields
2. keep old fields stable for one minor cycle
3. migrate UI and downstream tooling
4. only then consider semantic cleanup of `selected_variant`

Avoid:

- redefining `selected_variant` in-place in the first rollout

That would be a contract meaning change and would require `MAJOR` handling per `docs/02-versioning-and-releases.md` and `docs/03-contracts-and-compatibility.md`.

## Implementation Plan

### Phase 1: Instrument And Clarify

Files likely touched:

- `services/strategy-service/src/main.rs`
- `services/strategy-service/src/lib.rs`
- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/examples/strategy_pairs_cues_response.example.json`
- `apps/web/src/lib/api.ts`
- `apps/web/src/App.tsx`

Goals:

1. expose explicit champion vs challenger diagnostics
2. eliminate hybrid cue payloads in drift state
3. preserve current fail-closed behavior
4. prove selection-path activity in tests and telemetry

### Phase 2: Repair Runtime Decisioning

Files likely touched:

- host/runtime branch equivalent of `services/strategy-service/src/main.rs`
- host/runtime branch equivalent of `services/strategy-service/src/lib.rs`
- maintenance report paths and schemas

Goals:

1. remove incumbent bias before or during evaluation
2. ensure the decision table actually runs in steady state
3. recanonicalize legacy rows safely
4. only begin after the host runtime lineage is present in a reviewable local branch

## Test Plan

### Unit Tests

1. neutral evaluation picks highest-score variant without champion influence
2. champion-projected cue recomputation produces a fully champion-consistent payload, or fails closed without hybrid output
3. `INITIALIZE` occurs only when no incumbent champion existed
4. `UNCHANGED` occurs only when best variant equals stored champion
5. `KEEP_CHAMPION` occurs only when best variant differs but the score-delta threshold blocks promotion
6. `PROMOTE_CHALLENGER` occurs when delta exceeds required threshold
7. legacy recanonicalization upgrades source only when canonical serialization succeeds

### Integration Tests

1. cue endpoint returns both evaluated-best and stored-champion diagnostics
2. cue endpoint never returns a hybrid champion/challenger payload during drift
3. transition metrics appear during steady-state reevaluation across `INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, and `PROMOTE_CHALLENGER`
4. reoptimize response includes accurate transition totals
5. maintenance recanonicalization reports counts, validation state, and blocked reasons

### Replay / Regression Tests

1. fixed candle fixtures yield stable best variant and transition outcomes
2. replay with an incumbent champion present produces the same decision sequence every run
3. a replay window containing challenger reversals proves promotions and keeps are both observable
4. replay after cold start proves `INITIALIZE` metrics do not trigger the anomaly alert spuriously

### Schema Validation

1. updated cue schema validates new `selection_state`
2. updated examples validate
3. any maintenance/reoptimize additive fields validate
4. implementation includes a `MINOR` contract/version bump and `CHANGELOG.md` entry when the additive fields ship

## Observability Requirements

Add or clarify:

1. `strategy_selection_best_vs_champion_mismatch_total{timeframe}`
2. `strategy_selection_transition_total{timeframe,decision}`
3. `strategy_selection_legacy_rows_total{timeframe}`
4. `strategy_selection_recanonicalized_total{timeframe}`
5. `strategy_selection_rows_updated_without_transition_total{timeframe}`

Required logs:

1. `pair_id`
2. `timeframe`
3. `best_variant`
4. `best_score`
5. `stored_champion_variant`
6. `stored_champion_score`
7. `decision`
8. `score_delta`
9. `selection_source`
10. `validation_state`

## Risk And Failure Modes

1. If evaluation remains incumbent-biased, all later reporting will be cosmetically improved but still wrong.
2. If champion projection remains partial, the UI can show a hybrid cue made from champion and challenger fields.
3. If legacy rows are recanonicalized without current evaluation proof, defaults could be mistaken for approved champions.
4. If the system exposes challenger data but still allows live dispatch on ambiguous state, operators may overtrust the UI.

Fail-closed rule:

- if selection integrity cannot be established for a row, that row remains research-visible but not trade-eligible

## Versioning Impact

Current document:

- docs-only planning
- no version bump
- no `CHANGELOG.md` update required

Future implementation:

- Slice A additive cue/report fields: `MINOR`
- required file updates for Slice A:
  - `specs/contracts/strategy_pairs_cues_response.schema.json`
  - `specs/examples/strategy_pairs_cues_response.example.json`
  - `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
  - `specs/examples/strategy_pairs_reoptimize_response.example.json`
  - `CHANGELOG.md`
- redefining existing field meaning: `MAJOR`
- behavior changes affecting operator interpretation or maintenance procedures: document in `CHANGELOG.md` and update runbooks

## Open Questions

1. On the host branch, are variant-specific parameters fully comparable across variants, or do some variants still rely on champion-specific persisted config in a way that requires a deeper model change?

## Recommendation

Implement Slice A first in the repo, with the immediate safeguard already active:

1. keep `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`
2. keep live `ENTRY` and `EXIT` disabled for this strategy runtime
3. eliminate hybrid cue payloads before changing any selection policy

That ordering gives Codex a safe coding path:

1. clarify selection truth and cue consistency
2. instrument transition health including `INITIALIZE` and `UNCHANGED`
3. reproduce the host runtime lineage in a reviewable branch
4. repair deeper incumbent bias
5. recanonicalize legacy rows only after the runtime can prove current selection correctness
