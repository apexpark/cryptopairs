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
- Async reoptimization lifecycle counts by trigger/status (`strategy_reoptimize_run_total{trigger,status}` with bounded triggers `SCHEDULED`, `MANUAL_API`, `MAINTENANCE_REPORT`, `RECOVERY` and terminal statuses `CANCELED`, `SUCCEEDED`, `DEGRADED`, `FAILED`, `EXPIRED`)
- Async reoptimization active run gauges by status (`strategy_reoptimize_active_runs{status}` with bounded active statuses `QUEUED`, `LEASED`, `RUNNING`, `CANCEL_REQUESTED`)
- Async reoptimization enqueue, lease, heartbeat, budget, progress, cancellation, fail-closed, missing-telemetry, unknown-status, and terminal-recommendation counters:
  - `strategy_reoptimize_scheduler_enqueue_total{trigger,result}` where `result` is one of `ENQUEUED`, `DISABLED`, `ACTIVE_RUN`, `COOLDOWN`, `HEALTH_UNAVAILABLE`, `INTEGRITY_UNKNOWN`, `BUDGET_INVALID`, `LEASE_UNAVAILABLE`, `UNKNOWN_STATUS`, `CONFIG_INVALID`
  - `strategy_reoptimize_lease_acquire_total{result}` where `result` is one of `ACQUIRED`, `BUSY`, `STALE_RECOVERED`, `FAILED`
  - `strategy_reoptimize_lease_lost_total{reason}` where `reason` is one of `EXPIRED`, `GENERATION_MISMATCH`, `HEARTBEAT_FAILED`, `OWNER_MISMATCH`, `UNKNOWN`
  - `strategy_reoptimize_lease_heartbeat_total{result}` where `result` is one of `SUCCEEDED`, `FAILED`, `STALE_OWNER`, `GENERATION_MISMATCH`
  - `strategy_reoptimize_budget_exhausted_total{budget}` where `budget` is one of `RUN_WALL_CLOCK`, `TIMEFRAME_WALL_CLOCK`, `PAIR_EVALUATIONS_RUN`, `PAIR_EVALUATIONS_TIMEFRAME`, `PAIR_CONCURRENCY`, `DB_WRITE_BATCH`, `ARTIFACT_BYTES`, `COOLDOWN`, `LEASE_TTL`
  - `strategy_reoptimize_progress_pairs_total{timeframe,result}` and `strategy_reoptimize_timeframe_total{timeframe,status}` with bounded timeframes `1m`, `15m`, `1h`
  - `strategy_reoptimize_cancel_total{result}` where `result` is one of `REQUESTED`, `ACCEPTED`, `COMPLETED`, `REJECTED_TERMINAL`, `REJECTED_NOT_FOUND`, `FAILED`, `TIMED_OUT`
  - `strategy_reoptimize_fail_closed_total{reason}` and `strategy_reoptimize_telemetry_missing_total{reason}` using bounded fail-closed reasons `MISSING_TELEMETRY`, `UNKNOWN_STATUS`, `STALE_STATUS`, `LEASE_LOST`, `BUDGET_EXHAUSTED`, `CANCELED`, `ARTIFACT_FAILED`, `INTEGRITY_UNKNOWN`, `RISK_UNKNOWN`, `ACCOUNTING_ANOMALY`, `SCHEDULE_MISSED`, `UNSAFE_PROMOTION_ATTEMPT`, `CONFIG_INVALID`, `REPAIR_PROVENANCE_ACTIVE`
  - `strategy_reoptimize_status_unknown_total{reason}` where `reason` is one of `STATUS_ROW_MISSING`, `STATUS_ENUM_UNKNOWN`, `STATUS_CONTRADICTORY`, `STATUS_STALE`, `TELEMETRY_UNAVAILABLE`
  - `strategy_reoptimize_recommendation_total{recommendation}` where `recommendation` is one of `HOLD`, `OPERATOR_REVIEW_REQUIRED`, `PROMOTION_CANDIDATE_AVAILABLE`, `REVERT_REVIEW_REQUIRED`

Async reoptimization metric labels must not include `run_id`, `pair_id`,
`operator_id`, `lease_owner`, hostnames, artifact paths, URLs, free-form
errors, or stack traces. Those values are allowed only in structured logs,
status payloads, or artifacts. Reoptimization artifact read/write metrics are
not emitted until artifact writing and artifact read/download surfaces exist.

4. Execution and risk:
- Order ack latency
- Reject/cancel rates
- Risk check fail counts
- Kill switch activation count
- Reconcile gate fail counts on order intents
- Order lifecycle transition counts by state

5. Account:
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

## Out Of Scope

1. Enterprise SIEM integration in initial local-first phase.
2. Multi-region failover monitoring at MVP stage.
