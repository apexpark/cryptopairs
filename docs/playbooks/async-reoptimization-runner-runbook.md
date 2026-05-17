# Async Reoptimization Runner Runbook

## Purpose

Provide operator-facing guidance for the future bounded async reoptimization
runner without enabling it.

This runbook is docs-only groundwork. It does not prove any host state, does
not implement metrics, does not add endpoints, and does not enable a scheduler.

## Scope And Safety Rules

The async reoptimization runner is safe to operate only when the approved
implementation provides durable run state, leases, budgets, cancellation,
bounded telemetry, and readable artifacts.

Hard rules:

1. Scheduler enablement requires explicit operator approval.
2. Live `ENTRY` and `EXIT` stay disabled unless separately approved under risk
   and execution policy.
3. `PROMOTION_CANDIDATE_AVAILABLE` is evidence only, not a `PROMOTE` action.
4. Automatic `PROMOTE`, automatic `REVERT`, and automatic repair-provenance
   graduation are forbidden.
5. Unknown, missing, stale, invalid, contradictory, canceled, degraded, failed,
   or expired runner state maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
6. Missing telemetry, lease loss, budget exhaustion, artifact failure, and
   cancellation uncertainty fail closed.

## Required Telemetry Before Enablement

Before any production scheduler enablement, confirm the approved implementation
exposes bounded metrics for these surfaces:

1. Runner lifecycle:
   - `strategy_reoptimize_run_total{trigger,status}`
   - `strategy_reoptimize_active_runs{status}`
   - `strategy_reoptimize_duration_seconds{status}`
   - `strategy_reoptimize_status_unknown_total{reason}`
2. Scheduler:
   - `strategy_reoptimize_scheduler_enqueue_total{trigger,result}`
   - `strategy_reoptimize_schedule_missed_total{reason}`
   - `strategy_reoptimize_next_due_timestamp_seconds`
   - `strategy_reoptimize_last_terminal_timestamp_seconds{status}`
3. Lease and single-flight:
   - `strategy_reoptimize_lease_acquire_total{result}`
   - `strategy_reoptimize_lease_lost_total{reason}`
   - `strategy_reoptimize_lease_heartbeat_total{result}`
   - `strategy_reoptimize_lease_heartbeat_age_seconds`
   - `strategy_reoptimize_lease_age_seconds`
4. Budgets and progress:
   - `strategy_reoptimize_budget_exhausted_total{budget}`
   - `strategy_reoptimize_budget_remaining{budget}`
   - `strategy_reoptimize_progress_pairs_total{timeframe,result}`
   - `strategy_reoptimize_timeframe_total{timeframe,status}`
5. Artifacts:
   - `strategy_reoptimize_artifact_write_total{artifact,result}`
   - `strategy_reoptimize_artifact_read_total{artifact,result}`
   - `strategy_reoptimize_artifact_manifest_available`
   - `strategy_reoptimize_artifact_bytes_written_total{artifact}`
6. Cancellation and safety:
   - `strategy_reoptimize_cancel_total{result}`
   - `strategy_reoptimize_cancel_latency_seconds{result}`
   - `strategy_reoptimize_fail_closed_total{reason}`
   - `strategy_reoptimize_recommendation_total{recommendation}`
   - `strategy_reoptimize_unsafe_promotion_attempt_total{attempt_type,result}`
   - `strategy_reoptimize_telemetry_missing_total{reason}`

Metric labels must stay bounded. Never use `run_id`, `pair_id`,
`operator_id`, `lease_owner`, hostnames, container ids, artifact paths, request
URLs, stack traces, or free-form errors as labels. Put those values in
structured logs, status responses, or artifacts.

## Missing Telemetry Fail-Closed Handling

If any required async runner metric, status response, lease field, budget
field, recommendation, fail-closed reason, or artifact manifest is missing,
stale, unreadable, schema-invalid, or contradictory:

1. Keep the scheduler disabled or disable it immediately.
2. Do not enqueue a new mutation-producing run.
3. Treat the latest recommendation as `HOLD` or
   `OPERATOR_REVIEW_REQUIRED`.
4. Do not trust `PROMOTION_CANDIDATE_AVAILABLE`.
5. Record the missing telemetry source in operator notes.
6. Restore telemetry and verify a fresh successful run before re-enable.

## Enable Scheduler Flow

Use this only after the async runner implementation, contracts, metrics, and
runbooks are merged and the operator explicitly approves production canary.

1. Confirm the deployed build contains the approved async runner
   implementation.
2. Confirm live `ENTRY` and `EXIT` remain disabled.
3. Confirm promotion remains manual and requires explicit operator
   confirmation.
4. Confirm conservative run, timeframe, pair, DB batch, artifact, cooldown,
   lease TTL, and heartbeat budgets are configured.
5. Confirm `/metrics` exposes all required async runner metrics with bounded
   labels.
6. Confirm the latest status endpoint returns a known status from the async
   run contract.
7. Confirm artifact root and retention policy are approved.
8. Enable the scheduler flag in host configuration.
9. Deploy or restart only the required services.
10. Capture host identity, branch, commit, dirty status, deployed image or
    service identity, and relevant flags.
11. Watch one approved canary run from enqueue through terminal state.
12. Inspect artifacts before trusting any recommendation.

Stop and keep recommendations fail-closed if any metric, status, lease,
budget, artifact, or host identity evidence is missing or contradictory.

## Disable Scheduler Flow

1. Set the scheduler enabled flag to false.
2. Deploy or restart only the required services.
3. Verify no new scheduled runs are enqueued.
4. If a run is active, choose either allow-to-finish or cancel.
5. Keep latest status and artifacts readable.
6. Keep maintenance recommendations fail-closed until a fresh successful run
   exists after re-enable.

If disable verification is missing or contradictory, treat scheduler state as
unknown and keep recommendations at `HOLD`.

## Cancel Active Run Flow

1. Inspect latest status and confirm the exact target `run_id`.
2. Confirm the run is cancelable and non-terminal.
3. Submit the approved cancel endpoint for that exact `run_id`.
4. Verify status transitions to `CANCEL_REQUESTED`.
5. Verify no new pair or timeframe work starts after cancellation is observed.
6. Wait for terminal `CANCELED`, `FAILED`, or `EXPIRED`.
7. Inspect artifacts for completed, skipped, canceled, and failed units.

`CANCELED` is not success. A canceled or cancel-requested run must keep the
recommendation at `HOLD`.

## Inspect Artifacts Flow

1. Read the run status response.
2. Read `artifact_manifest`.
3. Confirm every artifact path is relative to the configured artifact root.
4. Reject any path with parent traversal or absolute path shape.
5. Read `request.json`, `progress.json`, `summary.json`, `errors.json`, and
   operator summary when present.
6. Compare artifact counts with status counters.
7. Treat any missing, partial, unreadable, or contradictory artifact as
   fail-closed.

Artifact inspection never substitutes for host verification when deployed
identity, runtime flags, or service state are in question.

## Rollback To Disabled Flow

1. Disable the scheduler flag.
2. Cancel the active run when safe, or let it reach terminal status under
   existing budgets.
3. Mark abandoned expired leases as `EXPIRED` through an approved recovery
   path.
4. Preserve run rows, event history, and artifacts.
5. Redeploy the previous known-good service image only if required for service
   health.
6. Verify `/metrics`, the status endpoint, and artifact reads remain
   available.
7. Keep maintenance recommendations at `HOLD` until the operator explicitly
   approves re-enable and observes a fresh successful run.

Rollback must not delete run history or artifact evidence.

## Alert Response

1. Stuck lease:
   - Trigger: active `LEASED` or `RUNNING` heartbeat age exceeds lease TTL plus
     grace.
   - Action: keep scheduler disabled or refuse new runs; inspect latest run;
     recover or mark `EXPIRED` before enablement.
2. Budget exhaustion:
   - Trigger: any increase in `strategy_reoptimize_budget_exhausted_total`.
   - Action: treat run as `DEGRADED` or `FAILED`; keep recommendation
     fail-closed; review budget and host load.
3. Artifact failure:
   - Trigger: artifact write/read result `FAILED`, `PARTIAL`, `NOT_FOUND`, or
     `CONTAINMENT_REJECTED`.
   - Action: do not trust terminal recommendation; inspect artifact root and
     manifest.
4. Cancellation failed or timed out:
   - Trigger: cancel result `FAILED` or `TIMED_OUT`.
   - Action: keep new runs disabled; inspect lease and active run before
     recovery.
5. Unsafe promotion attempt:
   - Trigger: any `strategy_reoptimize_unsafe_promotion_attempt_total`
     increase.
   - Action: block action, preserve audit logs, verify live `ENTRY` and `EXIT`
     remain disabled, and require operator review.
6. Missing telemetry or unknown status:
   - Trigger: any `strategy_reoptimize_telemetry_missing_total` or
     `strategy_reoptimize_status_unknown_total` increase.
   - Action: fail closed; do not enable scheduler until telemetry and status
     are restored.

## Host Verification Boundary

Host verification is operator-only. Agents must not SSH into `cryptopairs` or
claim host runtime evidence unless the operator provides it.

For future canary or enablement, the operator should capture:

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

If any host evidence is missing, stale, or contradictory, keep the scheduler
disabled and keep recommendations at `HOLD`.
