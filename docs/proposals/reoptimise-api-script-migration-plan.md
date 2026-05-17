# Proposal: reoptimize async API and script migration plan

> **Status**: design plan. No service or script implementation in this PR.
>
> **Item addressed**: Slice D from
> `docs/proposals/reoptimise-background-runner-redesign.md` - async API and
> script migration for the bounded reoptimization runner.
>
> **Compatibility rule**: `POST /v1/strategy/pairs/reoptimize` remains the
> synchronous compatibility route until a separate versioned migration is
> approved.

---

## 1. Scope

This plan defines the migration path for:

1. additive async reoptimization APIs;
2. `tools/scripts/strategy_tuning_report.py`;
3. `tools/scripts/strategy_maintenance_cycle.py`;
4. host/operator verification for rollout.

It does not:

1. implement async endpoints;
2. edit service or script code;
3. add or change contracts;
4. change runtime defaults;
5. enable live `ENTRY` or `EXIT`;
6. make `PROMOTE` automatic;
7. deprecate the existing synchronous route.

PR #192 proposes the Slice A async contracts that this plan expects later
script work to consume. Until those contracts are merged, validated, and
operator-approved, script migration remains design-only.

## 2. Verified Current Repo Facts

Verified before writing this plan:

- `services/strategy-service/src/main.rs` registers
  `POST /v1/strategy/pairs/reoptimize` at the router.
- `services/strategy-service/src/main.rs` registers
  `GET /v1/strategy/maintenance/latest`,
  `GET /v1/strategy/maintenance/artifact`, and
  `POST /v1/strategy/maintenance/action`.
- `services/strategy-service/src/main.rs` defines `ReoptimizeRequest` with
  `timeframes: Option<Vec<String>>`.
- `services/strategy-service/src/main.rs` defines `ReoptimizeResponse` as a
  synchronous aggregate response with run status, counts, per-timeframe
  status, flatline summary, transition counts, and errors.
- `tools/scripts/strategy_tuning_report.py` posts to
  `/v1/strategy/pairs/reoptimize` unless `--skip-reoptimize` is supplied.
- `tools/scripts/strategy_tuning_report.py` writes `decision: "HOLD"` when
  reporter execution fails.
- `tools/scripts/strategy_maintenance_cycle.py` currently runs the baseline
  report with `skip_reoptimize=True` and the candidate report with
  `skip_reoptimize=False`.
- `tools/scripts/strategy_maintenance_action_worker.py` processes queued
  manual maintenance actions and invokes `strategy_tuning_apply.py`; it does
  not run reoptimization.
- Current contracts exist for synchronous reoptimization and maintenance:
  - `specs/contracts/strategy_pairs_reoptimize_response.schema.json`;
  - `specs/contracts/strategy_maintenance_latest_response.schema.json`;
  - `specs/contracts/strategy_maintenance_action_response.schema.json`.
- PR #192 proposes draft Slice A async run contracts under `specs/contracts/`:
  - `strategy_reoptimize_run_enqueue_response.schema.json`;
  - `strategy_reoptimize_run_status_response.schema.json`;
  - `strategy_reoptimize_run_cancel_response.schema.json`;
  - `strategy_reoptimize_run_artifact_manifest.schema.json`.

The PR #192 contract files are draft contracts, not merged baseline contracts
for this PR. This plan references their names and semantics without changing
schemas, examples, service code, or script code.

## 3. Draft Slice A Contract Alignment

PR #192's draft async contracts define the first concrete contract surface for
the script migration plan:

1. `strategy_reoptimize_run_enqueue_response.schema.json` defines accepted
   enqueue responses, `run_id`, `status_route`, `cancel_route`, active-run
   attachment, progress, budgets, recommendation, fail-closed reasons,
   artifact manifest, and errors.
2. `strategy_reoptimize_run_status_response.schema.json` defines durable run
   status, lease fields, progress, budgets, recommendation, fail-closed
   reasons, artifact manifest, and errors.
3. `strategy_reoptimize_run_cancel_response.schema.json` defines cancellation
   as a state transition with `cancel_result`, `previous_status`,
   `cancel_requested_at`, `cancelable`, and the same fail-closed evidence
   fields.
4. `strategy_reoptimize_run_artifact_manifest.schema.json` defines artifact
   evidence with path containment, required artifact metadata, total bytes,
   fail-closed reasons, and errors.

The draft contracts also define bounded shared enums that scripts should treat
as the allowed contract vocabulary once merged:

1. run statuses: `QUEUED`, `LEASED`, `RUNNING`, `CANCEL_REQUESTED`,
   `CANCELED`, `SUCCEEDED`, `DEGRADED`, `FAILED`, `EXPIRED`;
2. trigger sources: `SCHEDULED`, `MANUAL_API`, `MAINTENANCE_REPORT`,
   `RECOVERY`;
3. recommendations: `HOLD`, `OPERATOR_REVIEW_REQUIRED`,
   `PROMOTION_CANDIDATE_AVAILABLE`, `REVERT_REVIEW_REQUIRED`;
4. fail-closed reasons including `UNKNOWN_STATUS`, `STALE_STATUS`,
   `LEASE_LOST`, `BUDGET_EXHAUSTED`, `CANCELED`, `ARTIFACT_FAILED`,
   `INTEGRITY_UNKNOWN`, `RISK_UNKNOWN`, `ACCOUNTING_ANOMALY`,
   `UNSAFE_PROMOTION_ATTEMPT`, `CONFIG_INVALID`, and
   `REPAIR_PROVENANCE_ACTIVE`;
5. cancellation results: `REQUESTED`, `ACCEPTED`, `COMPLETED`,
   `REJECTED_TERMINAL`, `REJECTED_NOT_FOUND`, `FAILED`, `TIMED_OUT`.

Script implementation must validate against the merged versions of these
contracts, not against this proposal text. If PR #192 changes before merge,
the implementation plan must follow the merged contract files.

## 4. Migration Principles

1. Add async APIs beside the synchronous route. Do not change the meaning of
   the synchronous route in place.
2. Make async behavior opt-in for scripts until the PR #192 Slice A contracts
   and examples are merged, validated, and approved.
3. Treat async reoptimization output as evidence, not as an action.
4. Unknown, stale, timed out, failed, degraded, expired, canceled, or
   contradictory runner state maps to `HOLD`.
5. Scripts must use bounded polling. There must be no infinite wait loop and
   no tight retry loop.
6. A fresh run must be request-compatible with the report that consumes it:
   timeframes, strategy profile/config fingerprint, service version, and
   trigger metadata must match the consumer's expectation.
7. Cancellation is best-effort and state-based. A canceled or cancel-requested
   run must never be treated as successful.
8. Promotion remains a separate manual operator decision through existing or
   future confirmed controls.
9. Repair-only provenance such as `RECANONICALIZED_LEGACY_ROW` remains
   fail-closed unless an explicit operator-approved transition exists.

## 5. API Compatibility Plan

### Existing route

`POST /v1/strategy/pairs/reoptimize` stays synchronous during migration.

Required compatibility behavior:

1. request body keeps accepting `{"timeframes": [...]}`;
2. response continues validating against
   `specs/contracts/strategy_pairs_reoptimize_response.schema.json`;
3. `status` continues to mean the synchronous run result
   (`OK`, `DEGRADED`, or `FAILED`);
4. callers that have not opted into async behavior do not receive enqueue-only
   payloads from this route.

Any future change that turns this route into an async wrapper, admin-only
route, or deprecated route requires a separate versioned migration proposal.

### Proposed async routes

**PROPOSAL**: after the PR #192 Slice A contracts are merged and approved, add
these routes:

1. `POST /v1/strategy/reoptimize/runs`;
2. `GET /v1/strategy/reoptimize/runs/latest`;
3. `GET /v1/strategy/reoptimize/runs/{run_id}`;
4. `POST /v1/strategy/reoptimize/runs/{run_id}/cancel`;
5. `GET /v1/strategy/reoptimize/runs/{run_id}/artifacts` or a versioned
   artifact manifest/download route.

The enqueue route should return a payload compatible with the merged
`strategy_reoptimize_run_enqueue_response.schema.json`: durable `run_id`,
accepted/queued status, status/cancel routes, the effective request, and
whether the service created a new run or attached the caller to an
already-compatible active run.

The status route should return a payload compatible with the merged
`strategy_reoptimize_run_status_response.schema.json`, including:

1. `schema_version`;
2. `run_id`;
3. `status`;
4. `trigger_source`;
5. `requested_timeframes`;
6. `request_fingerprint`;
7. `service_version` or commit/build identity when available;
8. `created_at`, `started_at`, `finished_at`;
9. progress counts;
10. budgets;
11. `recommendation`;
12. `fail_closed_reasons`;
13. `artifact_manifest`;
14. errors;
15. `cancel_requested_at`.

Terminal status handling for scripts:

| Status | Script consumption |
|---|---|
| `SUCCEEDED` | May consume only if request-compatible, fresh, and artifacts/status validate. |
| `DEGRADED` | `HOLD`; may include diagnostics but not promotion evidence. |
| `FAILED` | `HOLD`. |
| `EXPIRED` | `HOLD`. |
| `CANCELED` | `HOLD`. |
| `CANCEL_REQUESTED` | Keep polling until terminal or deadline; deadline maps to `HOLD`. |
| `QUEUED` / `LEASED` / `RUNNING` | Continue bounded polling until terminal or deadline. |
| unknown status or schema-invalid payload | `HOLD`. |

The artifact route should use the merged
`strategy_reoptimize_run_artifact_manifest.schema.json` semantics: artifact
paths must be relative to the configured artifact root, must not contain parent
traversal, and must be evidence-only. Artifact evidence must not authorize
promotion or repair-provenance graduation.

## 6. `strategy_tuning_report.py` Migration

### CLI mode

**PROPOSAL**: add an explicit mode flag only after the PR #192 Slice A async
contracts are merged:

```text
--reoptimize-mode sync|async|latest-successful|skip
```

Initial migration default should remain `sync` to preserve existing behavior.
`skip` maps to the current `--skip-reoptimize` behavior. A later versioned
operator approval can change the default to `async` or `latest-successful`.

Supporting **PROPOSAL** flags:

```text
--reoptimize-max-wait-seconds <int>
--reoptimize-poll-initial-seconds <float>
--reoptimize-poll-max-seconds <float>
--reoptimize-max-age-seconds <int>
--reoptimize-cancel-on-timeout / --no-reoptimize-cancel-on-timeout
```

All values must be clamped to safe minimums and maximums in the script.

### Async enqueue flow

**PROPOSAL** for `--reoptimize-mode async`:

1. Build an enqueue request from the report timeframes and trigger metadata:
   `trigger_source=MAINTENANCE_REPORT` for maintenance use or
   `trigger_source=MANUAL_API` for direct operator report runs.
2. Include a report-side request fingerprint covering timeframes, profile,
   relevant strategy tuning policy version/path, and any config values that
   affect evaluation.
3. `POST /v1/strategy/reoptimize/runs`.
4. If the service returns an existing compatible active run, record that in
   `reoptimize_summary` and poll it.
5. If enqueue fails, returns an incompatible active run, fails schema
   validation, or returns an unknown payload shape, write a report with
   `decision: "HOLD"`.

### Polling and backoff

**PROPOSAL** polling policy:

1. Use one total deadline for enqueue plus all polls.
2. Start at 2 seconds.
3. Multiply each interval by 1.5.
4. Cap each interval at 30 seconds.
5. Stop when the run reaches a terminal state or the deadline expires.
6. Add deterministic jitter only if multiple callers are expected; derive it
   from `run_id` so logs remain auditable.
7. Clamp sleep so the final sleep cannot exceed the remaining deadline.

The script must record:

1. poll count;
2. first and last status;
3. elapsed milliseconds;
4. timeout deadline;
5. terminal status or timeout reason;
6. run id;
7. whether cancellation was requested.

No script path may poll forever.

### Timeout and cancellation

On timeout:

1. set report `decision` to `HOLD`;
2. add `ASYNC_REOPTIMIZE_TIMEOUT` to `reoptimize_summary.errors`;
3. skip promotion-positive decision checks that depend on fresh reoptimization
   evidence;
4. if and only if this script enqueued the run, request cancellation when the
   cancel endpoint is available and `--reoptimize-cancel-on-timeout` is true;
5. do not cancel a scheduled run or a shared latest run that this process did
   not create;
6. record cancel request success/failure as diagnostic evidence only.

If cancellation fails, the report remains `HOLD`; the failure is not retried
unboundedly.

### Fail-closed report mapping

`strategy_tuning_report.py` should treat these as fail-closed `HOLD` reasons:

1. enqueue HTTP error;
2. status HTTP error after retry budget is exhausted;
3. timeout;
4. unknown status;
5. missing `run_id`;
6. missing or stale `finished_at`;
7. request fingerprint mismatch;
8. missing required artifact manifest;
9. non-empty critical errors;
10. `fail_closed_reasons` present;
11. terminal state other than `SUCCEEDED`;
12. recommendation decision outside the merged contract enum;
13. `REPAIR_PROVENANCE_ACTIVE` or equivalent repair-provenance fail-closed
    reason.

The script may still collect non-decisional diagnostics after a failed async
run, but it must mark them as non-decisional in the report and keep the final
decision at `HOLD`.

## 7. `strategy_maintenance_cycle.py` Migration

### Decision rule: latest successful versus fresh run

**PROPOSAL**: maintenance should prefer the latest successful run only when
all compatibility checks pass. Otherwise, it should request a fresh run in
`auto` mode or fail closed in `latest-only` mode.

Compatibility checks for consuming latest successful run:

1. status is `SUCCEEDED`;
2. `finished_at` is present and within `--reoptimize-max-age-seconds`;
3. requested timeframes exactly match or safely cover the maintenance
   timeframes;
4. request fingerprint matches the active profile/config being evaluated;
5. service version/build identity is acceptable for the current deploy;
6. artifact manifest is present and path-contained;
7. no fail-closed reasons are present;
8. progress counts show the expected timeframes reached terminal summary.
9. recommendation and status values validate against the merged Slice A
   contracts.

If any check is unknown or false, the latest run is not eligible.

### Baseline step

The current script runs baseline with `skip_reoptimize=True`.

**PROPOSAL** migration:

1. keep baseline skip behavior as the initial compatibility default;
2. allow opt-in baseline evidence refresh with
   `--baseline-reoptimize-mode latest-successful|fresh|skip`;
3. consume latest successful baseline run only if it matches the baseline
   profile/config fingerprint;
4. request a fresh baseline run only when explicitly configured;
5. if baseline reoptimization is required but unavailable, set cycle
   `decision` to `HOLD` and `status` to `FAIL`.

### Candidate step

After candidate settings are applied, latest successful evidence is acceptable
only if it finished after the candidate deployment and matches the candidate
profile/config fingerprint.

Default **PROPOSAL** for candidate mode:

1. request a fresh async run after candidate apply completes;
2. poll with bounded backoff;
3. on `SUCCEEDED`, run the candidate report against the fresh evidence;
4. on timeout, cancellation, failure, stale evidence, or fingerprint mismatch,
   restore original settings as today where applicable and keep decision
   `HOLD`;
5. do not translate async runner `PROMOTION_CANDIDATE_AVAILABLE` into an
   automatic `PROMOTE` action;
6. do not translate async runner success into repair-provenance graduation.

### Active run collision behavior

When a maintenance cycle starts and a run is already active:

1. if the active run is compatible with the needed profile and timeframes,
   attach to it and poll within the same total deadline;
2. if it is incompatible, wait only up to a bounded active-run wait budget;
3. after the wait budget expires, fail closed to `HOLD`;
4. do not cancel a run owned by another trigger unless an explicit operator
   cancel action is supplied through the approved API boundary.

### Maintenance reports

The cycle report should include an async reoptimization section:

1. mode used;
2. run id;
3. whether latest or fresh evidence was consumed;
4. request fingerprint;
5. status timeline summary;
6. poll count and elapsed time;
7. timeout/cancel diagnostics;
8. artifact manifest references;
9. fail-closed reasons.

The existing `GET /v1/strategy/maintenance/latest` contract can continue to
return the latest report payload as an opaque object until a future contract
slice makes this structure explicit.

## 8. Manual Actions and Promotion Safety

`tools/scripts/strategy_maintenance_action_worker.py` should remain scoped to
manual maintenance actions.

Required invariants:

1. async reoptimization cannot enqueue `PROMOTE` or `REVERT`;
2. maintenance cycle automation can recommend, but cannot execute, final
   promotion;
3. `POST /v1/strategy/maintenance/action` continues to require
   `operator_id` and `confirm=true`;
4. candidate actions remain manual and auditable;
5. live `ENTRY` / `EXIT` remain disabled unless separately approved by risk
   and execution policy;
6. repair-only provenance cannot be converted to non-repair provenance by an
   async run or script decision.

No migration step may weaken `docs/12-risk-and-execution-policy.md`.

## 9. Timeout and Cancellation Contract Requirements

PR #192's draft cancellation contract defines the starting point for this
surface. Before scripts can migrate to async mode, the merged contracts must
define:

1. which states are terminal;
2. whether cancellation is allowed for each non-terminal state;
3. how cancel request acceptance differs from completed cancellation;
4. whether cancel is authorized by trigger owner, operator role, or both;
5. how expired leases surface to callers;
6. how partial artifacts are represented;
7. how request fingerprints are built and compared.

Script-side safe defaults:

1. cancel only caller-owned runs;
2. never cancel latest successful evidence;
3. never treat cancel acceptance as a terminal result;
4. map cancellation uncertainty to `HOLD`;
5. map `CANCEL_REQUESTED`, `CANCELED`, `FAILED`, `TIMED_OUT`, or schema-invalid
   cancel responses to `HOLD`.

## 10. Rollout Slices

### Slice D1 - contract approval gate

Merge and approve the PR #192 async run contracts and examples before script
code changes.

Acceptance:

1. schema validation passes for enqueue, status, cancel, and artifact
   manifest examples;
2. old synchronous reoptimize example still validates;
3. compatibility notes state that `/v1/strategy/pairs/reoptimize` remains
   synchronous.

### Slice D2 - script library helpers

Add small shared Python helpers for enqueue, status polling, deadline/backoff,
and fail-closed mapping.

Acceptance:

1. no script default behavior changes;
2. helper unit tests cover timeout, unknown status, HTTP failures, and
   terminal state mapping;
3. helpers validate response payloads against the merged Slice A contracts.

### Slice D3 - `strategy_tuning_report.py` opt-in async mode

Add async mode behind an explicit CLI flag.

Acceptance:

1. default remains synchronous;
2. `--reoptimize-mode async` uses bounded polling;
3. timeout returns report decision `HOLD`;
4. generated report includes run id, poll summary, and fail-closed reasons.

### Slice D4 - `strategy_maintenance_cycle.py` migration

Add baseline/candidate reoptimization modes and latest-successful validation.

Acceptance:

1. candidate fresh-run mode is opt-in at first;
2. latest successful run is consumed only when request-compatible and fresh;
3. active incompatible run collision fails closed;
4. restore-original behavior remains intact;
5. no automatic promotion.

### Slice D5 - versioned default migration

After operator approval and host evidence, change script defaults if desired.

Acceptance:

1. `CHANGELOG.md` documents the workflow change;
2. runbooks document sync fallback and async disable path;
3. old synchronous route remains supported or is deprecated through a
   separate approved process.

## 11. Testing Plan Notes

Docs-only PR verification:

1. `git diff --check`.

PR #192 / future contract PR:

1. validate each new async example against its schema;
2. validate existing synchronous examples still pass;
3. confirm `additionalProperties: false` coverage for nested objects;
4. update `CHANGELOG.md` and version metadata.

Future script PR:

1. unit-test poll sequence caps and total-deadline behavior;
2. unit-test status mapping to `HOLD`;
3. unit-test latest-successful compatibility checks;
4. schema-validate mocked async responses against the merged Slice A
   contracts;
5. integration-test script behavior against a mocked HTTP server:
   - enqueue succeeds then `SUCCEEDED`;
   - enqueue succeeds then `FAILED`;
   - run stays `RUNNING` until timeout;
   - cancel accepted after timeout;
   - latest run stale;
   - latest run fingerprint mismatch;
6. replay/regression-test that deterministic fixtures still produce stable
   report decisions when async run evidence is successful.

Future service PR:

1. Postgres-backed run queue and lease tests;
2. cancel endpoint tests;
3. artifact manifest path containment tests;
4. single-flight collision tests.

## 12. Observability Plan

This docs-only plan adds no metrics or logs.

Future implementation should follow the merged/patched #190 observability plan
for metric names, help text, label names, alert details, dashboards, and
runbook procedures. This migration plan keeps only the script-facing
requirements that must align with the async contracts.

1. `strategy_reoptimize_run_total{trigger,status}`;
2. `strategy_reoptimize_active_runs`;
3. `strategy_reoptimize_lease_acquire_total{result}`;
4. `strategy_reoptimize_lease_lost_total`;
5. `strategy_reoptimize_duration_seconds{status}`;
6. `strategy_reoptimize_budget_exhausted_total{budget}`;
7. `strategy_reoptimize_cancel_total{result}`;
8. `strategy_reoptimize_progress_pairs_total{timeframe,result}`;
9. `strategy_reoptimize_artifact_write_total{result}`;
10. `strategy_reoptimize_fail_closed_total{reason}`;
11. `strategy_reoptimize_recommendation_total{recommendation}`.

Metric labels must keep `status` as the status label. Terminal-only metrics use
the same `status` label, but emit only terminal values: `CANCELED`,
`SUCCEEDED`, `DEGRADED`, `FAILED`, and `EXPIRED`.

Scripts should validate `status`, `recommendation`, `fail_closed_reason` /
`fail_closed_reasons`, and `cancel_result` values against the merged PR #192
schemas rather than accepting free-form strings.

Script logs and reports should include:

1. `run_id`;
2. `trigger_source`;
3. `request_fingerprint`;
4. poll count;
5. elapsed milliseconds;
6. terminal status;
7. timeout reason;
8. cancellation request result;
9. fail-closed reasons.

Alerts should cover stuck runs, repeated timeouts, repeated budget exhaustion,
artifact write failures, and repeated fail-closed recommendations.

## 13. Host and Operator-Only Verification

Remote and local agents must not claim host runtime verification without
operator-provided evidence.

Operator-only checks before enabling async script mode on host:

1. capture deployed branch, commit, and dirty status;
2. capture strategy-service worker flags and async runner flags;
3. capture runtime budgets and polling defaults;
4. prove live `ENTRY` / `EXIT` remain disabled;
5. prove `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` remains set when applicable;
6. capture pre-run CPU and hot endpoint latency baseline;
7. enqueue one canary run with a narrow approved timeframe;
8. capture status progression from queued to terminal state;
9. capture run artifacts and artifact manifest;
10. capture metrics for lease, progress, cancellation, budget, and
    recommendation;
11. run `strategy_tuning_report.py` in async mode and verify timeout/failure
    maps to `HOLD` when forced;
12. run `strategy_maintenance_cycle.py` in the approved mode and verify no
    automatic `PROMOTE` / `REVERT` action occurs;
13. confirm sync route still responds to old callers;
14. confirm repair-only provenance remains fail-closed unless explicitly
    operator-approved through a separate transition;
15. document rollback to sync mode and disabled async scheduler.

If any host check is missing or contradictory, keep async script mode disabled
and keep recommendations at `HOLD`.

## 14. Rollback and Disable Path

Safe rollback must be available before production enablement:

1. set scripts back to `--reoptimize-mode sync` or `skip`;
2. disable async scheduler/enqueue flags if present;
3. allow active caller-owned runs to finish or request cancellation;
4. keep status/artifacts readable;
5. preserve the synchronous route;
6. keep maintenance latest report available;
7. keep decisions fail-closed until a fresh successful run exists;
8. keep repair-provenance decisions fail-closed until explicit operator
   approval exists.

Rollback must not delete run history or artifacts.

## 15. Versioning

This plan is docs-only. It changes no public behavior, contracts, config, or
runtime defaults. No version bump and no `CHANGELOG.md` entry are required.

Future work:

1. the additive async contracts and examples proposed by PR #192 require a
   `MINOR` version update when merged;
2. new script flags and operator workflow defaults require `CHANGELOG.md`;
3. changing the meaning or default response shape of
   `POST /v1/strategy/pairs/reoptimize` requires a separate versioned
   migration and may require `MAJOR` handling;
4. metrics and label sets are contracts under
   `docs/03-contracts-and-compatibility.md` and must stay bounded.

## 16. Open Approval Questions

1. Should first async script rollout default to `sync` with an opt-in async
   flag, or should host-only automation opt into async immediately after
   canary?
2. What maximum age makes latest successful run evidence acceptable for daily
   maintenance?
3. Which fields define the canonical request/config fingerprint?
4. Should report-triggered runs be cancelable by the script that enqueued
   them, or only by an operator-authenticated cancellation request?
5. Should baseline reoptimization remain skipped by default, or should it
   consume latest successful evidence when available?
6. What is the first host canary timeframe?
