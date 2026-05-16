# Proposal: observability and runbook plan for bounded async reoptimization

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Branch**: `codex/reoptimise-runner-observability`.
>
> **Base design**:
> `docs/proposals/reoptimise-background-runner-redesign.md`.
>
> **Item addressed**: Slice E observability and runbook design for the
> bounded asynchronous reoptimization runner.

---

## 1. Scope

This is a docs-only proposal. It does not:

1. implement the async runner;
2. edit Rust service code;
3. edit JSON schemas or examples;
4. change runtime defaults;
5. add or change environment variables;
6. enable any background worker;
7. enable live `ENTRY` or `EXIT`;
8. make `PROMOTE` automatic;
9. claim host verification.

The exact existing synchronous route found in
`services/strategy-service/src/main.rs` is
`POST /v1/strategy/pairs/reoptimize`. This document uses `reoptimize` for
route and metric names and `reoptimise` only where matching proposal filenames
or operator wording.

## 2. Context And Sources

Verified repository sources consulted before writing:

1. `AGENTS.md`;
2. `docs/AGENT_STATE.md`;
3. `docs/playbooks/remote-agent-bootstrap.md`;
4. `docs/proposals/reoptimise-background-runner-redesign.md`;
5. `docs/15-observability-and-alerting.md`;
6. `docs/playbooks/strategy-maintenance-automation-runbook.md`;
7. `docs/playbooks/daily-strategy-maintenance-guide.md`;
8. `docs/playbooks/hosted-deployment-runbook.md`;
9. `docs/playbooks/observability-slo-runbook.md`;
10. `docs/02-versioning-and-releases.md`;
11. `docs/03-contracts-and-compatibility.md`;
12. `docs/12-risk-and-execution-policy.md`;
13. `docs/14-testing-standards.md`;
14. `services/strategy-service/src/main.rs`;
15. `specs/contracts/strategy_pairs_reoptimize_response.schema.json`;
16. `specs/contracts/strategy_maintenance_latest_response.schema.json`;
17. `specs/contracts/strategy_maintenance_action_response.schema.json`.

Verified repo facts:

1. `services/strategy-service/src/main.rs` registers
   `POST /v1/strategy/pairs/reoptimize`.
2. `services/strategy-service/src/main.rs` contains
   `spawn_reoptimize_worker`.
3. `services/strategy-service/src/main.rs` exposes current strategy metrics
   including `pairs_cue_projection_total{outcome}`,
   `strategy_selection_transition_total{decision,timeframe}`, and
   `strategy_selection_rows_updated_without_transition_total{timeframe}`.
4. `services/strategy-service/src/main.rs` contains maintenance artifact path
   containment logic in `resolve_artifact_path`.
5. `docs/03-contracts-and-compatibility.md` defines metrics names and label
   sets as contracts.
6. `docs/12-risk-and-execution-policy.md` requires explicit operator
   confirmation for live `ENTRY` and `EXIT` intents and fail-closed behavior
   on unknown risk state.
7. `docs/playbooks/strategy-maintenance-automation-runbook.md` states that
   automated maintenance evaluates and reports while final `PROMOTE` /
   `REVERT` actions remain manual.

## 3. Slice E Objective

PROPOSAL: Slice E should define the telemetry and operator workflow that must
exist before any production enablement of the bounded async reoptimization
runner.

The implementation must be considered unsafe to enable if any required
telemetry is missing, stale, contradictory, or unavailable. Missing telemetry
or unknown runner status fails closed:

1. no new scheduled mutation-producing run is enqueued;
2. latest recommendation is `HOLD` or `OPERATOR_REVIEW_REQUIRED`;
3. automatic promotion remains impossible;
4. operator-facing status must show the reason.

## 4. Interfaces And Contracts

No contract files are changed by this proposal.

Existing contracts likely affected by future implementation:

1. `specs/contracts/strategy_pairs_reoptimize_response.schema.json`;
2. `specs/contracts/strategy_maintenance_latest_response.schema.json`;
3. `specs/contracts/strategy_maintenance_action_response.schema.json`.

Future async contracts proposed by the base redesign:

1. `specs/contracts/strategy_reoptimize_run_enqueue_response.schema.json`;
2. `specs/contracts/strategy_reoptimize_run_status_response.schema.json`;
3. `specs/contracts/strategy_reoptimize_run_cancel_response.schema.json`;
4. `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`.

Metrics names and label sets below are also contracts under
`docs/03-contracts-and-compatibility.md`. They must be added only through an
implementation PR with versioning and `CHANGELOG.md` review.

## 5. Bounded Metric Label Policy

PROPOSAL: async reoptimization metrics must never use high-cardinality labels.

Allowed metric labels:

| Label | Allowed values |
|---|---|
| `trigger` | `SCHEDULED`, `MANUAL_API`, `MAINTENANCE_REPORT`, `RECOVERY` |
| `status` | `QUEUED`, `LEASED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELED`, `SUCCEEDED`, `DEGRADED`, `FAILED`, `EXPIRED` |
| `result` | metric-specific bounded enums defined in this document |
| `timeframe` | `1m`, `15m`, `1h` |
| `phase` | `QUEUED`, `PRECHECK`, `TIMEFRAME_PRECHECK`, `PAIR_EVALUATION`, `PERSIST_SELECTED_ROWS`, `PERSIST_SHADOW_MODEL`, `TIMEFRAME_SUMMARY`, `RUN_SUMMARY`, `ARTIFACT_WRITE`, `TERMINAL` |
| `budget` | `RUN_WALL_CLOCK`, `TIMEFRAME_WALL_CLOCK`, `PAIR_EVALUATIONS_RUN`, `PAIR_EVALUATIONS_TIMEFRAME`, `PAIR_CONCURRENCY`, `DB_WRITE_BATCH`, `ARTIFACT_BYTES`, `COOLDOWN`, `LEASE_TTL` |
| `artifact` | `REQUEST`, `PROGRESS`, `SUMMARY`, `ERRORS`, `TIMEFRAME_DETAIL`, `OPERATOR_SUMMARY` |
| `recommendation` | `HOLD`, `OPERATOR_REVIEW_REQUIRED`, `PROMOTION_CANDIDATE_AVAILABLE`, `REVERT_REVIEW_REQUIRED` |
| `reason` | bounded fail-closed and scheduler reasons listed in sections 6 and 9 |
| `attempt_type` | `AUTO_PROMOTE`, `MISSING_CONFIRMATION`, `STALE_RUN`, `NON_SUCCEEDED_RUN`, `ARTIFACT_UNAVAILABLE`, `UNKNOWN_STATUS` |

Disallowed metric labels:

1. `run_id`;
2. `pair_id`;
3. `operator_id`;
4. `lease_owner`;
5. hostnames or container ids;
6. artifact paths;
7. free-form error strings;
8. stack traces;
9. request URLs.

Those values belong in structured logs, status payloads, or artifacts, not
Prometheus-style labels.
Any unenumerated reason or error text must stay in structured logs or
artifacts; metric labels must use only the bounded enums in this document.

Metrics that emit only terminal outcomes still use the `status` label. For
those metrics, allowed emitted values are limited to terminal statuses:
`CANCELED`, `SUCCEEDED`, `DEGRADED`, `FAILED`, and `EXPIRED`.

## 6. Proposed Metrics

All metrics are PROPOSAL and must be implemented behind the disabled-by-default
async runner work.

### Runner lifecycle

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_run_total` | counter | `trigger`, `status` | a run reaches a terminal state; `status` emits only terminal values |
| `strategy_reoptimize_active_runs` | gauge | `status` | current active run count by non-terminal status |
| `strategy_reoptimize_duration_seconds` | histogram | `status` | a run reaches a terminal state; `status` emits only terminal values |
| `strategy_reoptimize_phase_duration_seconds` | histogram | `phase` | a work phase completes or fails |
| `strategy_reoptimize_status_unknown_total` | counter | `reason` | status cannot be read, parsed, or reconciled |

Allowed `reason` values for `strategy_reoptimize_status_unknown_total`:
`STATUS_ROW_MISSING`, `STATUS_ENUM_UNKNOWN`, `STATUS_CONTRADICTORY`,
`STATUS_STALE`, `TELEMETRY_UNAVAILABLE`.

### Scheduler

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_scheduler_enqueue_total` | counter | `trigger`, `result` | scheduler or API tries to enqueue a run |
| `strategy_reoptimize_schedule_missed_total` | counter | `reason` | a scheduled due time passes without enqueueing |
| `strategy_reoptimize_next_due_timestamp_seconds` | gauge | none | scheduler computes next due time |
| `strategy_reoptimize_last_terminal_timestamp_seconds` | gauge | `status` | latest terminal run timestamp; `status` emits only terminal values |

Allowed `result` values for `strategy_reoptimize_scheduler_enqueue_total`:
`ENQUEUED`, `DISABLED`, `ACTIVE_RUN`, `COOLDOWN`, `HEALTH_UNAVAILABLE`,
`INTEGRITY_UNKNOWN`, `BUDGET_INVALID`, `LEASE_UNAVAILABLE`,
`UNKNOWN_STATUS`, `CONFIG_INVALID`.

Allowed `reason` values for `strategy_reoptimize_schedule_missed_total`:
`DISABLED`, `ACTIVE_RUN`, `COOLDOWN`, `HEALTH_UNAVAILABLE`,
`INTEGRITY_UNKNOWN`, `BUDGET_INVALID`, `LEASE_UNAVAILABLE`,
`UNKNOWN_STATUS`, `TELEMETRY_UNAVAILABLE`.

### Lease and single-flight

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_lease_acquire_total` | counter | `result` | a runner attempts lease acquisition |
| `strategy_reoptimize_lease_lost_total` | counter | `reason` | current owner loses or cannot prove ownership |
| `strategy_reoptimize_lease_heartbeat_total` | counter | `result` | heartbeat extension succeeds or fails |
| `strategy_reoptimize_lease_heartbeat_age_seconds` | gauge | none | latest active lease heartbeat age |
| `strategy_reoptimize_lease_age_seconds` | gauge | none | latest active lease age |

Allowed `result` values for `strategy_reoptimize_lease_acquire_total`:
`ACQUIRED`, `BUSY`, `STALE_RECOVERED`, `FAILED`.

Allowed `reason` values for `strategy_reoptimize_lease_lost_total`:
`EXPIRED`, `GENERATION_MISMATCH`, `HEARTBEAT_FAILED`, `OWNER_MISMATCH`,
`UNKNOWN`.

Allowed `result` values for `strategy_reoptimize_lease_heartbeat_total`:
`SUCCEEDED`, `FAILED`, `STALE_OWNER`, `GENERATION_MISMATCH`.

### Budgets and progress

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_budget_exhausted_total` | counter | `budget` | a configured budget stops new work |
| `strategy_reoptimize_budget_remaining` | gauge | `budget` | runner writes a budget checkpoint |
| `strategy_reoptimize_progress_pairs_total` | counter | `timeframe`, `result` | a pair work unit finishes |
| `strategy_reoptimize_timeframe_total` | counter | `timeframe`, `status` | a timeframe reaches terminal status; `status` emits only terminal values |

Allowed `result` values for `strategy_reoptimize_progress_pairs_total`:
`COMPLETED`, `SKIPPED`, `FAILED`, `CANCELED`.

Budget exhaustion is always fail-closed. A run stopped by any budget must end as
`DEGRADED` or `FAILED` and recommend `HOLD` or `OPERATOR_REVIEW_REQUIRED`.

### Artifacts

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_artifact_write_total` | counter | `artifact`, `result` | writing an artifact succeeds or fails |
| `strategy_reoptimize_artifact_read_total` | counter | `artifact`, `result` | operator/API artifact read succeeds or fails |
| `strategy_reoptimize_artifact_manifest_available` | gauge | none | latest terminal run has a readable manifest |
| `strategy_reoptimize_artifact_bytes_written_total` | counter | `artifact` | bytes are written inside the artifact root |

Allowed `result` values for artifact metrics:
`SUCCEEDED`, `FAILED`, `NOT_FOUND`, `CONTAINMENT_REJECTED`,
`BUDGET_EXHAUSTED`, `PARTIAL`.

A missing, partial, unreadable, or path-containment-rejected artifact manifest
must map the run recommendation to `HOLD`.

### Cancellation

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_cancel_total` | counter | `result` | cancellation is requested or completed |
| `strategy_reoptimize_cancel_latency_seconds` | histogram | `result` | time from accepted cancel request to terminal state |

Allowed `result` values:
`REQUESTED`, `ACCEPTED`, `COMPLETED`, `REJECTED_TERMINAL`,
`REJECTED_NOT_FOUND`, `FAILED`, `TIMED_OUT`.

`CANCELED` is a terminal non-success state. It must never produce
`PROMOTION_CANDIDATE_AVAILABLE`.

### Fail-closed decisions and unsafe promotion

| Metric | Type | Labels | Increment or set when |
|---|---|---|---|
| `strategy_reoptimize_fail_closed_total` | counter | `reason` | runner or scheduler blocks recommendation/action |
| `strategy_reoptimize_recommendation_total` | counter | `recommendation` | terminal recommendation is finalized |
| `strategy_reoptimize_unsafe_promotion_attempt_total` | counter | `attempt_type`, `result` | promotion is attempted without a safe, explicit path |
| `strategy_reoptimize_telemetry_missing_total` | counter | `reason` | required telemetry is absent or stale |

Allowed `reason` values for `strategy_reoptimize_fail_closed_total` and
`strategy_reoptimize_telemetry_missing_total`: `MISSING_TELEMETRY`,
`UNKNOWN_STATUS`, `STALE_STATUS`, `LEASE_LOST`, `BUDGET_EXHAUSTED`,
`CANCELED`, `ARTIFACT_FAILED`, `INTEGRITY_UNKNOWN`, `RISK_UNKNOWN`,
`ACCOUNTING_ANOMALY`, `SCHEDULE_MISSED`, `UNSAFE_PROMOTION_ATTEMPT`,
`CONFIG_INVALID`, `REPAIR_PROVENANCE_ACTIVE`.

Allowed `result` values for
`strategy_reoptimize_unsafe_promotion_attempt_total`: `BLOCKED`,
`FAILED_CLOSED`.

## 7. Structured Logs

PROPOSAL: every async reoptimization structured log record must include a
correlation field and enough data to reconstruct the run timeline without
depending on metric labels.

Common fields:

| Field | Requirement |
|---|---|
| `request_id` | required when triggered by an API request or maintenance cycle |
| `run_id` | required for any record after enqueue succeeds |
| `event` | required bounded event name |
| `trigger_source` | one of `SCHEDULED`, `MANUAL_API`, `MAINTENANCE_REPORT`, `RECOVERY` |
| `status_before` | previous bounded status, nullable only at enqueue |
| `status_after` | next bounded status |
| `phase` | bounded phase when applicable |
| `timeframe` | bounded timeframe when applicable |
| `pair_id` | allowed in logs for pair-level events, never in metric labels |
| `lease_owner` | current owner identifier when applicable |
| `lease_generation` | current lease generation when applicable |
| `lease_expires_at` | current lease expiry when applicable |
| `heartbeat_at` | latest heartbeat timestamp when applicable |
| `budget_name` | bounded budget name when applicable |
| `budget_limit` | numeric limit when applicable |
| `budget_used` | numeric usage when applicable |
| `cancel_requested` | boolean |
| `artifact_kind` | bounded artifact kind when applicable |
| `artifact_relative_path` | relative path inside artifact root; never absolute |
| `artifact_manifest_id` | stable manifest id or run id, if present |
| `recommendation` | terminal recommendation when applicable |
| `fail_closed_reason` | bounded fail-closed reason when applicable |
| `operator_id` | optional for manual operator actions; do not include secrets |
| `error_code` | bounded code when applicable |
| `error` | sanitized text for logs only; never a metric label |

Recommended event names:

1. `reoptimize_run_enqueue_attempted`;
2. `reoptimize_run_enqueued`;
3. `reoptimize_run_enqueue_rejected`;
4. `reoptimize_lease_acquire_attempted`;
5. `reoptimize_lease_acquired`;
6. `reoptimize_lease_heartbeat`;
7. `reoptimize_lease_lost`;
8. `reoptimize_phase_started`;
9. `reoptimize_phase_completed`;
10. `reoptimize_budget_exhausted`;
11. `reoptimize_cancel_requested`;
12. `reoptimize_cancel_observed`;
13. `reoptimize_artifact_write_succeeded`;
14. `reoptimize_artifact_write_failed`;
15. `reoptimize_recommendation_finalized`;
16. `reoptimize_fail_closed`;
17. `reoptimize_unsafe_promotion_blocked`.

No log event may mark a run `SUCCEEDED` unless the terminal status, artifacts,
and recommendation are all internally consistent. Unknown consistency must
emit `reoptimize_fail_closed`.

## 8. Alerts

All thresholds below are PROPOSAL defaults. Operator-approved values should be
set during implementation and canary.

| Alert | Severity | Signal | Required action |
|---|---|---|---|
| Stuck lease | P2, P1 if promotion path is open | active `LEASED` or `RUNNING` run heartbeat age exceeds lease TTL plus grace | keep scheduler disabled or refuse new runs; inspect latest run; recover or mark `EXPIRED` before any enablement |
| Repeated failures | P2 | two or more scheduled runs reach `FAILED` or `DEGRADED` in the configured window | keep recommendations `HOLD`; inspect errors and artifacts before re-enabling |
| Missed schedule | P2 after repeated misses, P3 first miss | `strategy_reoptimize_schedule_missed_total` increases for enabled scheduler | inspect scheduler gates; do not force enqueue if reason is unknown |
| Budget exhaustion | P2 | any increase in `strategy_reoptimize_budget_exhausted_total` | treat run as `DEGRADED` or `FAILED`; keep recommendation fail-closed; review budget and load |
| Artifact failure | P2 | artifact write/read result is `FAILED`, `PARTIAL`, `NOT_FOUND`, or `CONTAINMENT_REJECTED` | do not trust terminal recommendation; inspect artifact root and manifest |
| Cancellation failed or timed out | P2 | cancel result `FAILED` or `TIMED_OUT` | keep new runs disabled; inspect lease and active run before recovery |
| Cancellation surge | P3/P2 trend | repeated operator cancellations within a short window | review scheduler budgets and workload size |
| Unsafe promotion attempt | P1 | any `strategy_reoptimize_unsafe_promotion_attempt_total` increase | block action, preserve audit logs, verify live `ENTRY` / `EXIT` remain disabled |
| Missing telemetry | P2 | any `strategy_reoptimize_telemetry_missing_total` increase | fail closed; do not enable scheduler until telemetry is restored |
| Unknown status | P2 | any `strategy_reoptimize_status_unknown_total` increase | fail closed; inspect persistence/status contract before new runs |

Alert payloads must include:

1. alert name;
2. severity;
3. latest `run_id` if known;
4. latest status if known;
5. fail-closed reason;
6. dashboard link or status endpoint path;
7. artifact manifest path if available;
8. operator-only host verification note when runtime state must be checked on
   `cryptopairs`.

## 9. Dashboard Design

PROPOSAL: the operator dashboard should have one async reoptimization panel
with six sections.

1. Latest run state:
   - latest `run_id`;
   - status;
   - trigger source;
   - started and finished timestamps;
   - current phase;
   - progress counts;
   - terminal recommendation.
2. Scheduler health:
   - scheduler enabled flag status;
   - next due time;
   - last terminal run age;
   - missed schedule count by reason.
3. Lease health:
   - active lease status;
   - heartbeat age;
   - lease age;
   - lease lost count by reason.
4. Budgets and load:
   - run duration;
   - phase duration;
   - budget exhaustion count by budget;
   - remaining budget gauges.
5. Artifacts:
   - manifest availability;
   - artifact write/read results;
   - links to request, progress, summary, errors, timeframe details, and
     operator summary artifacts.
6. Safety and recommendations:
   - fail-closed reasons;
   - latest recommendation;
   - unsafe promotion attempts;
   - explicit reminder that `PROMOTION_CANDIDATE_AVAILABLE` is not an action.

Dashboard rules:

1. Unknown latest status renders as blocked, not healthy.
2. Missing metrics render as blocked, not empty green panels.
3. `CANCELED`, `DEGRADED`, `FAILED`, and `EXPIRED` render as non-success.
4. Artifact links are hidden or marked unavailable when the manifest is absent
   or failed containment checks.
5. No dashboard control may submit live `ENTRY`, live `EXIT`, or automatic
   `PROMOTE`.

## 10. Operator Runbook Flows

These flows are design targets for future updates to the hosted deployment and
strategy maintenance runbooks. Host verification remains operator-only.

### Enable scheduler

PROPOSAL:

1. Confirm the implementation PR and contract PR are merged.
2. Confirm live `ENTRY` and `EXIT` remain disabled.
3. Confirm promotion remains manual and requires explicit operator
   confirmation.
4. Confirm async runner config is present with conservative budgets.
5. Confirm `/metrics` exposes all required async runner metrics.
6. Confirm latest status endpoint returns a known status.
7. Enable scheduler flag in host configuration.
8. Deploy or restart only the required services.
9. Capture host identity, branch, commit, and dirty status.
10. Watch one scheduled canary run through terminal status.
11. Inspect artifacts before trusting the recommendation.

Fail-closed stop conditions:

1. missing metric;
2. unknown status;
3. stale status;
4. missing artifact manifest;
5. budget exhaustion;
6. lease anomaly;
7. any unsafe promotion attempt.

### Disable scheduler

PROPOSAL:

1. Set scheduler enabled flag to false.
2. Deploy or restart only the required services.
3. Verify no new scheduled runs are enqueued.
4. If a run is active, choose either allow-to-finish or cancel.
5. Keep latest status and artifacts readable.
6. Keep maintenance recommendations fail-closed until a fresh successful run is
   available after re-enable.

If disable verification is missing or contradictory, treat scheduler state as
unknown and keep recommendations at `HOLD`.

### Cancel active run

PROPOSAL:

1. Inspect latest status and confirm the target `run_id`.
2. Confirm the run is cancelable.
3. Submit the future cancel endpoint for that exact `run_id`.
4. Verify status transitions to `CANCEL_REQUESTED`.
5. Verify no new pair/timeframe work starts after cancellation is observed.
6. Wait for terminal `CANCELED`, `FAILED`, or `EXPIRED`.
7. Inspect artifacts for completed, skipped, canceled, and failed work units.

`CANCELED` is not success. It must keep recommendation at `HOLD`.

### Inspect artifacts

PROPOSAL:

1. Read the run status response.
2. Read `artifact_manifest`.
3. Confirm every artifact path is relative to the configured root.
4. Download `request.json`, `progress.json`, `summary.json`, `errors.json`,
   and operator summary if present.
5. Compare artifact counts with status counters.
6. Treat any missing, partial, or contradictory artifact as fail-closed.

Artifact inspection never substitutes for host verification when runtime
configuration or deployed identity is in question.

### Rollback to disabled

PROPOSAL:

1. Disable scheduler flag.
2. Cancel the active run when safe, or let it reach terminal status under
   existing budgets.
3. Mark abandoned expired leases as `EXPIRED` through an approved recovery path.
4. Preserve run rows, event history, and artifacts.
5. Redeploy the previous known-good service image only if needed for service
   health.
6. Verify `/metrics`, status endpoint, and artifact reads remain available.
7. Keep maintenance recommendations at `HOLD` until the operator explicitly
   approves re-enable and observes a fresh successful run.

Rollback must not delete run history or artifact evidence.

## 11. Host Verification Boundary

Host verification is operator-only. Agents must not SSH into `cryptopairs` or
claim host state.

For any future canary or enablement, the operator should capture:

1. host branch, commit, and dirty status;
2. deployed image or service identity;
3. scheduler, lease, budget, cache, and worker flag values;
4. proof live `ENTRY` and `EXIT` remain disabled;
5. proof promotion remains manual;
6. pre-enable CPU and hot endpoint latency baseline;
7. `/metrics` output for async runner metrics;
8. status endpoint output for the canary run;
9. artifact manifest and artifacts;
10. post-run CPU and hot endpoint latency comparison;
11. active alerts before and after the run.

If any host evidence is missing, stale, or contradictory, the safe outcome is:
scheduler disabled and recommendation `HOLD`.

## 12. Test Plan

This proposal PR:

1. run `git diff --check`;
2. no schema validation required because no JSON schema or example changes are
   made;
3. no Rust checks required because no Rust files are changed.

Future contract PR:

1. schema validation for every new async runner example;
2. compatibility review for existing reoptimize and maintenance contracts;
3. version bump and `CHANGELOG.md` entry if contracts change.

Future implementation PR:

1. unit tests for scheduler gate decisions;
2. unit tests for lease acquire, heartbeat, loss, expiry, and recovery;
3. unit tests for budget exhaustion and fail-closed recommendation mapping;
4. unit tests for cancellation transitions;
5. integration tests for Postgres-backed single-flight and run status
   persistence;
6. integration tests for artifact manifest persistence and path containment;
7. replay tests proving fixed inputs produce deterministic run summaries and
   recommendations;
8. metric rendering tests asserting every label value is bounded.

## 13. Acceptance Criteria

Slice E is ready for implementation only when the approved design defines:

1. bounded metrics and label values;
2. structured log event names and required fields;
3. alerts for stuck leases, repeated failures, missed schedules, budget
   exhaustion, artifact failure, cancellation, and unsafe promotion attempts;
4. dashboard panels for latest run, scheduler health, lease health, budgets,
   artifacts, and recommendations;
5. operator runbook flows for enable, disable, cancel, inspect artifacts, and
   rollback-to-disabled;
6. host verification as operator-only;
7. missing telemetry and unknown status as fail-closed conditions.

## 14. Versioning

This proposal PR is docs-only and changes no runtime behavior, service code,
contracts, config keys, or operator procedure. No version bump and no
`CHANGELOG.md` entry are required.

Future implementation:

1. adding metric names or label sets is a MINOR-class contract addition under
   `docs/02-versioning-and-releases.md` and
   `docs/03-contracts-and-compatibility.md`;
2. adding async run/status/cancel/artifact schemas requires contract versioning,
   examples, schema validation, and `CHANGELOG.md`;
3. changing the behavior of `POST /v1/strategy/pairs/reoptimize` requires
   compatibility review and may require a MAJOR bump;
4. new operator-required procedures or config semantics require runbook updates
   and `CHANGELOG.md`.
