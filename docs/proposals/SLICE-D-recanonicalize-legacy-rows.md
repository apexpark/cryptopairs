# Proposal: Slice D recanonicalize legacy selected rows

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: codex (remote agent), 2026-05-08.
>
> **Branch**: `codex/slice-d-recanonicalization-design`. Sprint base:
> `codex/fix-clippy-run-24549051096`.
>
> **Item addressed**: Slice D planning in `docs/AGENT_STATE.md`
> section "Currently In Flight".

---

## 1. Problem

Slice D is the cleanup step after Slice C proves neutral champion selection in
the host runtime. It must repair `LEGACY_ROW_FALLBACK` selected rows without
turning legacy provenance into trusted trading provenance.

Current verified repo context:

- `docs/26-champion-selection-integrity-fix-spec.md` defines Slice D as a
  maintenance/fail-closed repair path. It says `LEGACY_ROW_FALLBACK` is a
  migration-only internal state, recanonicalized does not mean tradable, and
  unresolved rows stay blocked.
- `docs/proposals/SLICE-C-host-lineage-and-implementation.md` explicitly leaves
  recanonicalization out of Slice C. It says Slice C must not treat
  recanonicalization as a prerequisite for neutral evaluation and must not let
  legacy provenance become trade-eligible by accident.
- `docs/AGENT_STATE.md` records the latest captured host selected-row state:
  `12 / 16` `1m` rows are `LEGACY_ROW_FALLBACK`; the remaining `1m` rows plus
  all captured `15m` and `1h` rows are `AUTO_CHAMPION`.
- The same state document records live cue mismatch counts of `11 / 16` for
  `1m`, `12 / 16` for `15m`, and `7 / 16` for `1h`, plus `0` post-cutover drift
  events and empty candidate pipeline tables.

The last two facts matter together. Legacy rows are real cleanup debt, but they
are not the whole champion-selection bug. Slice D is safe only after Slice C
observation proves the runtime is evaluating neutrally and accounting for
champion decisions.

## 2. Non-goals

This proposal does not:

1. implement recanonicalization;
2. edit services, apps, contracts, examples, or `docs/AGENT_STATE.md`;
3. enable live `ENTRY` / `EXIT`;
4. relax `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`;
5. redefine `cue.selected_variant` or any existing required contract field;
6. remove `LEGACY_ROW_FALLBACK` rows by deletion alone;
7. make a recanonicalized row automatically trade-eligible;
8. replace operator-only host verification with agent inference.

## 3. Preconditions

Slice D implementation must not start until Slice C has produced operator-
captured observation evidence. Minimum required evidence:

1. Host lineage and deployed identity:
- deployed commit and branch;
- whether host dirty state was included, reconstructed, or excluded;
- Slice C neutral-selection rollout flag name and value;
- target timeframes and observation window start/end.

2. Safety posture:
- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`;
- live `ENTRY` / `EXIT` disabled;
- no P1 execution/account alerts during the observation window;
- no claim that cues are execution-trustworthy.

3. Slice A cue contract evidence:
- `cue.selection_state` present for every audited cue;
- `missing_selection_state_count == 0`;
- no `CHAMPION_PROJECTION_FAILED` rows in the target observation window.

4. Slice B accounting evidence:
- `strategy_selection_transition_total{decision,timeframe}` shows accounted
  activity for every evaluated target timeframe;
- `strategy_selection_rows_updated_without_transition_total{timeframe}` does
  not increase;
- when `cue.selection_state.stored_champion_variant` differs from
  `cue.selection_state.best_variant`, `KEEP_CHAMPION` or
  `PROMOTE_CHALLENGER` activity is observed for the affected timeframe after a
  completed evaluation window.

5. Legacy inventory evidence:
- pre-Slice-D selected-row inventory by `pair_id`, `timeframe`,
  `signal_variant`, selected-row provenance source, and `updated_at`;
- count of legacy rows by timeframe;
- cue mismatch audit grouped by source and validation state;
- explicit list of rows that cannot be evaluated neutrally or serialized
  canonically.

PROPOSAL: require at least one completed reoptimization/evaluation window for
each target timeframe before enabling an apply-mode recanonicalization action.
If the target cadence cannot be verified from operator evidence, defer Slice D.

## 4. Options

### Option A - report-only legacy inventory

Add a maintenance report that inventories legacy rows and blocks them, but does
not rewrite selected rows.

**Pros**

- Lowest mutation risk.
- Useful if Slice C observation remains inconclusive.
- Gives operators an exact worklist before any repair action exists.

**Cons**

- Leaves `LEGACY_ROW_FALLBACK` as steady-state debt.
- Does not prove the canonical selected-row write path.
- Requires a second design/implementation step to actually repair eligible
  rows.

**Verdict**: acceptable fallback if Slice C evidence is incomplete; too weak as
the primary Slice D endpoint.

### Option B - dry-run first, then operator-confirmed recanonicalization

Add a maintenance action with two phases:

1. dry-run: evaluate each targeted legacy row, classify eligibility, compute
   the would-write canonical payload, and emit a report without mutation;
2. apply: require operator confirmation that references the dry-run report and
   update only rows whose eligibility still matches the report snapshot.

Recanonicalized rows remain repair-only until a separate current approval path
confirms tradability.

**Pros**

- Preserves fail-closed posture while allowing real cleanup.
- Gives operators a row-level before/after report.
- Makes rollback possible because apply can capture pre-image rows.
- Fits existing maintenance-action/report surfaces named in `docs/26`.

**Cons**

- Requires careful idempotency and snapshot checks.
- Requires contract additions for dry-run/apply reports.
- Still depends on operator-host evidence for the Slice C observation gate.

**Verdict**: recommended.

### Option C - automatic background recanonicalization

Automatically repair legacy rows during normal reoptimization once Slice C is
enabled.

**Pros**

- No separate operator flow.
- Eventually clears legacy rows without manual action.

**Cons**

- Too easy to hide unsafe or partial repairs in normal runtime churn.
- Harder to produce auditable pre/post evidence.
- Raises rollback risk if many rows mutate before an operator notices a bad
  assumption.

**Verdict**: not recommended for first Slice D implementation.

### Option D - delete legacy rows and cold-initialize

Delete `LEGACY_ROW_FALLBACK` selected rows and let normal initialization write
new rows.

**Pros**

- Simple mental model.
- Avoids preserving untrusted legacy payloads.

**Cons**

- Destroys row-level before/after evidence unless carefully exported first.
- Can look like approval by omission if initialized rows are not explicitly
  marked repair-only.
- Does not exercise a controlled recanonicalization report path.

**Verdict**: not recommended except as an emergency operator-only recovery
after a separate rollback plan is approved.

## 5. Recommended design

Use Option B.

The Slice D implementation should add an operator-triggered maintenance action
that defaults to dry-run. Apply mode is allowed only when all Slice C evidence
gates pass and the operator confirms the exact dry-run report being applied.

### Row eligibility

A legacy row is eligible for recanonicalization only when all checks pass:

1. the row is identified as legacy by the selected-row provenance source in the
   imported host code path;
2. the pair/timeframe evaluates successfully through Slice C neutral selection;
3. data integrity for the evaluation window meets the policy threshold in
   `docs/11-data-integrity-policy.md`;
4. the neutral winning variant is explicit and belongs to the supported variant
   set;
5. the final selected-row payload can be serialized canonically and round-trips
   without changing meaning;
6. transition accounting for the row is explainable as `INITIALIZE`,
   `UNCHANGED`, `KEEP_CHAMPION`, or `PROMOTE_CHALLENGER`;
7. the row has no projection failure, selected-row accounting gap, or missing
   `selection_state` in the same observation context;
8. the resulting row can carry a non-legacy repair provenance that is distinct
   from current trade approval.

If any check fails, the row is not partially repaired. It remains blocked and
appears in the report with a reason code.

### Repair-only state

Recanonicalization changes provenance quality, not trading approval.

The implementation should persist enough metadata for operators and downstream
surfaces to distinguish:

1. legacy fallback row;
2. recanonicalized repair-only row;
3. current non-legacy approved row.

PROPOSAL: store the recanonicalized state as a repair-only selected-row
provenance marker in the selected-row config, and surface it in the maintenance
report. If the implementation also needs this state in
`cue.selection_state.validation_state`, that is a contract change and must
update the strict enum in `specs/contracts/strategy_pairs_cues_response.schema.json`
plus the examples and UI handling.

Until a current non-legacy approval path confirms the row, execution-facing
logic must treat recanonicalized repair-only rows as not trade-eligible.

### Dry-run report

Dry-run should report:

1. Slice C evidence bundle identity or reference;
2. target timeframes and row selector;
3. pre-run legacy row counts by timeframe;
4. per-row classification: eligible, blocked, skipped, or already current;
5. per-row reason codes;
6. neutral best variant, stored/legacy variant, transition decision, and score
   delta where available;
7. canonical payload digest or equivalent stable comparison value;
8. counts for rows seen, eligible, would-recanonicalize, blocked, and skipped;
9. rollback artifact path that would be created by apply mode;
10. explicit statement that dry-run made no selected-row mutations.

### Apply behavior

Apply mode should:

1. require operator confirmation tied to a dry-run report identity;
2. re-check the Slice C evidence gate;
3. re-read each target row and refuse rows whose source, variant, updated time,
   or payload digest no longer matches the dry-run snapshot;
4. capture a pre-image artifact for every row that will be mutated;
5. update only eligible rows;
6. mark recanonicalized rows repair-only;
7. emit per-row structured logs and aggregate metrics;
8. return a report whose counts reconcile exactly with attempted rows.

The apply action should be idempotent. Re-running it against the same already
recanonicalized repair-only rows should classify them as already repaired or
skipped, not mutate them again.

## 6. Rollback

Rollback must be designed before apply mode ships.

Minimum rollback behavior:

1. apply mode writes a pre-image artifact before any selected-row mutation;
2. the artifact records target row primary keys, previous `signal_variant`,
   previous config payload, previous updated timestamp, and the apply report
   identity;
3. rollback restores only rows that still match the apply report's post-image
   digest;
4. if a row has changed since apply, rollback refuses that row and reports
   operator action required;
5. rollback never deletes unrelated rows;
6. rollback keeps live trading disabled and does not mark restored legacy rows
   trade-eligible;
7. rollback emits the same aggregate counts and per-row reason codes as apply.

Operationally, rollback should restore the previous row state, then rerun the
Slice A/Slice C cue audit and selected-row inventory. If rollback cannot prove
the row returned to its previous state, the row remains blocked.

## 7. Operator verification

Host verification is operator-only. Remote agents must not SSH into
`cryptopairs` or claim host evidence that was not captured by the operator.

For the implementation PR, the operator should capture:

1. deployed commit, branch, dirty status, and rollout flag state;
2. pre-Slice-D selected-row inventory grouped by source/timeframe;
3. Slice C observation evidence listed in section 3;
4. dry-run report output and report identity;
5. apply report output, if apply mode is approved;
6. post-apply selected-row inventory grouped by source/timeframe;
7. cue mismatch audit after apply using `cue.selection_state`;
8. metric deltas for legacy rows seen, recanonicalized, blocked, and rollback
   events;
9. confirmation that live `ENTRY` / `EXIT` stayed disabled;
10. rollback report output if rollback is exercised.

The implementation PR should include these as PR comments, linked artifacts, or
a proposed `docs/AGENT_STATE.md` delta.

## 8. Acceptance criteria for implementation PR

The follow-up implementation PR is acceptable only if:

1. apply mode refuses to run when Slice C evidence is missing or stale;
2. dry-run is side-effect-free and produces row-level eligibility reasons;
3. apply mode mutates only rows that still match the dry-run snapshot;
4. unresolved rows remain blocked and research-visible only;
5. recanonicalized rows are marked repair-only and are not trade-eligible;
6. pre-image artifacts make rollback deterministic;
7. rollback restores only rows that still match the expected post-image;
8. aggregate counts reconcile exactly:
   `seen = eligible + blocked + skipped + already_current`;
9. contract/example changes are additive, versioned, and schema-validated;
10. pg-backed integration tests cover eligible repair, blocked repair,
    idempotent re-run, and rollback refusal on changed rows;
11. replay/regression tests prove stable neutral best variant and decision
    outcome for a fixed fixture window, or the PR explicitly documents why the
    fixture does not exist yet and keeps pg-backed persistence coverage as the
    minimum gate;
12. observability includes metrics/logs sufficient to reconstruct the repair
    timeline.

## 9. Interfaces and contracts

No contracts are changed by this proposal PR.

Future implementation will likely touch these existing contracts:

- `specs/contracts/strategy_maintenance_action_response.schema.json`;
- `specs/contracts/strategy_maintenance_latest_response.schema.json`;
- possibly `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
  if recanonicalization counts are surfaced in reoptimization reports;
- possibly `specs/contracts/strategy_pairs_cues_response.schema.json` if
  repair-only validation state must be exposed in live cues.

Expected additive fields include:

- `legacy_rows_seen`;
- `legacy_rows_eligible`;
- `legacy_rows_recanonicalized`;
- `legacy_rows_blocked`;
- `legacy_rows_skipped`;
- `rollback_artifact_path`;
- per-row reason codes;
- repair-only validation/provenance state.

Changing the meaning of existing fields, especially `cue.selected_variant` or
existing validation states, is out of scope and would require a separate
compatibility review.

## 10. Observability

Future implementation should emit bounded metrics such as:

- `strategy_selection_legacy_rows_total{timeframe,state}`;
- `strategy_selection_recanonicalized_total{timeframe,result}`;
- `strategy_selection_recanonicalization_blocked_total{timeframe,reason}`;
- `strategy_selection_recanonicalization_rollback_total{timeframe,result}`.

Structured logs should include:

- `request_id` or maintenance report identity;
- `pair_id`;
- `timeframe`;
- previous provenance source;
- new provenance state;
- neutral best variant;
- previous stored variant;
- transition decision;
- score delta;
- reason code;
- dry-run/apply/rollback mode.

Alerting should treat any apply attempt without Slice C evidence, any selected-
row accounting gap, or any projection failure as a fail-closed stop condition.

## 11. Versioning

This proposal PR is docs-only and does not change public behavior, contracts,
or operator workflow. No version bump and no `CHANGELOG.md` entry are required.

Future implementation should:

1. update `CHANGELOG.md` because it changes operator maintenance workflow;
2. bump modified maintenance/cue/reoptimize contracts according to
   `docs/02-versioning-and-releases.md`;
3. treat additive optional report fields as `MINOR`;
4. treat changed field meanings, removed fields, or stricter validation of
   previously valid payloads as `MAJOR`.

## 12. Open questions for operator approval

1. Observation window: approve the proposed minimum of one completed
   evaluation/reoptimization window per target timeframe, or specify a longer
   canary window?
2. Repair state location: should repair-only provenance be surfaced only in
   maintenance reports/config metadata first, or also in live
   `cue.selection_state.validation_state`?
3. Apply scope: should the first implementation target only `1m`
   `LEGACY_ROW_FALLBACK` rows from the captured host state, or all legacy rows
   found at run time?
4. Rollback artifact retention: where should apply/rollback artifacts be stored
   and how long should they be retained?
5. Approval path: what later non-legacy approval step can promote a repair-only
   recanonicalized row to execution-trustworthy status?

## 13. Out of scope

- No code changes in this PR.
- No `CHANGELOG.md` change in this PR.
- No service, app, contract, or example changes in this PR.
- No host SSH or live database query by the agent.
- No automatic execution enablement.
- No broad X3 reporting alignment for backtest, live-z, paper-trades, or
  opportunity-history surfaces.
