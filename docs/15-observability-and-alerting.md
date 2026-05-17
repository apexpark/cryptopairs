# Observability And Alerting

## Purpose

Define required telemetry, health signals, and alert policies.

## Hard Rules

1. `MUST` emit structured logs with correlation IDs.
2. `MUST` emit metrics for ingestion, backfill, execution, and account reconciliation.
3. `MUST` expose health endpoints for each service.
4. `MUST` alert on unresolved data gaps affecting active strategies.
5. `MUST` alert on order submission failures and reconciliation mismatches.
6. `MUST` preserve audit trail for user-initiated control actions.

## Minimum Metrics

1. Data ingestion:
- Message throughput
- Ingestion lag
- Duplicate/out-of-order count
- Gap count by symbol/timeframe

2. Backfill:
- Job success/failure rate
- Mean repair latency
- Unresolved interval count

3. Strategy cues:
- Cue generation count by timeframe
- Actionable cue count by pair
- Champion variant selection drift
- Reoptimize success/failure counts
- Shadow model availability/unavailability counts by timeframe
- Cost gate pass/fail counts by timeframe and reason
- Portfolio advisory availability/unavailability by timeframe
- Cue champion-projection outcomes (`pairs_cue_projection_total{outcome}` with bounded outcomes `NOT_REQUIRED`, `PROJECTED`, `PROJECTED_BLOCKED`, `PROJECTION_FAILED`)
- Champion-selection transition counts by decision/timeframe (`strategy_selection_transition_total{decision,timeframe}` with bounded decisions `INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, `PROMOTE_CHALLENGER`)
- Selected-row accounting gaps by timeframe (`strategy_selection_rows_updated_without_transition_total{timeframe}`)
- Optimizer candidate generation count by timeframe (`optimizer_candidate_generated_total`)
- Optimizer promotable-candidate count by timeframe (`optimizer_candidate_promotable_total`)
- Optimizer rejected-candidate count by timeframe/reason (`optimizer_candidate_rejected_total`)
- Candidate probation pass/fail counts by timeframe/reason (`candidate_probation_pass_total`, `candidate_probation_fail_total`)

4. Bounded async reoptimization runner (future gated):
- Required before scheduler enablement: runner lifecycle, scheduler, lease,
  budget, progress, artifact, cancellation, fail-closed, recommendation, unsafe
  promotion, and missing-telemetry metrics.
- Metric labels must be bounded. Allowed label families are `trigger`,
  `status`, `result`, `timeframe`, `phase`, `budget`, `artifact`,
  `recommendation`, `reason`, and `attempt_type`, using only the enums defined
  in `docs/proposals/reoptimise-observability-runbook-plan.md` and the async
  runner contracts.
- Metrics must not label by `run_id`, `pair_id`, `operator_id`,
  `lease_owner`, hostname, container id, artifact path, request URL, stack
  trace, or free-form error text. Those values belong in structured logs,
  status responses, or artifacts.
- Missing, stale, unreadable, schema-invalid, or contradictory async runner
  telemetry fails closed: no new scheduled mutation-producing run, latest
  recommendation `HOLD` or `OPERATOR_REVIEW_REQUIRED`, and no automatic
  `PROMOTE`, `REVERT`, `ENTRY`, or `EXIT`.
- Alert on stuck leases, unknown status, missing telemetry, repeated failed or
  degraded runs, missed schedules, budget exhaustion, artifact failures,
  cancellation failures/timeouts, and unsafe promotion attempts.

5. Execution and risk:
- Order ack latency
- Reject/cancel rates
- Risk check fail counts
- Kill switch activation count
- Reconcile gate fail counts on order intents
- Order lifecycle transition counts by state

6. Account:
- Reconciliation drift
- Margin utilization
- PnL update lag

## Alert Severity

1. `P1`: live trading safety risk (integrity breach, unreconciled positions, repeated order failures).
2. `P2`: degraded operation requiring operator action soon.
3. `P3`: informational trend warnings.

## Acceptance Checks

1. Alerts are routed and actionable with context fields.
2. Dashboards show integrity and execution health at a glance.
3. Incident timeline can be reconstructed from logs and events.
4. Optimizer/candidate lifecycle logs include:
- `request_id`, `timeframe`, `pair_id`
- probation transition state before/after
- rejection reasons and promotable counts per timeframe
5. Async reoptimization logs include:
- `request_id`, `run_id`, `trigger_source`
- bounded `status_before`, `status_after`, and `phase`
- lease generation and heartbeat timestamps where applicable
- bounded budget, artifact, recommendation, and fail-closed reason fields
- sanitized error text only in logs, never in metric labels

## Async Reoptimization Alert Response

Async reoptimization alerts are fail-closed by default:

1. Stuck lease or heartbeat age beyond lease TTL plus grace:
- Keep the scheduler disabled or refuse new runs.
- Inspect latest run status and recover or mark `EXPIRED` through an approved
  path before any enablement.

2. Budget exhaustion:
- Treat the run as `DEGRADED` or `FAILED`.
- Keep recommendation at `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
- Review runtime budget and host load before re-enable.

3. Artifact failure:
- Do not trust terminal recommendations.
- Inspect artifact manifest, root containment, and required artifact files.

4. Cancellation failure or timeout:
- Keep new runs disabled.
- Inspect lease and active run state before recovery.

5. Unsafe promotion attempt:
- Block the action and preserve audit logs.
- Verify live `ENTRY` and `EXIT` remain disabled.
- Require explicit operator review.

6. Missing telemetry or unknown status:
- Keep scheduler disabled.
- Treat latest recommendation as `HOLD`.
- Restore telemetry and verify a fresh successful run before trusting evidence.

Detailed operator flows are in
`docs/playbooks/async-reoptimization-runner-runbook.md`.

## Out Of Scope

1. Enterprise SIEM integration in initial local-first phase.
2. Multi-region failover monitoring at MVP stage.
