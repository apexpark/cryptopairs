# Observability SLO Runbook

## Purpose

Provide operator-facing SLO checks and alert response flow for execution and account health.

## Data Sources

1. Execution summary endpoint:
- `GET /v1/execution/observability/summary?exchange=<...>&account_id=<...>&window_minutes=<n>`

2. Account summary endpoint:
- `GET /v1/account/observability/summary?exchange=<...>&account_id=<...>&window_minutes=<n>`

3. Strategy Prometheus metrics endpoint:
- `GET /metrics` on the strategy service.

## Core SLO Signals

1. Manual execution safety
- `execution_stale_ack_count` (P1): must stay below threshold.
- `execution_reconcile_block_count` (P1): must stay below threshold.

2. Execution quality
- `execution_risk_block_ratio` (P2): should stay below threshold.
- `execution_dispatch_reject_ratio` (P2): should stay below threshold.

3. Account health
- `account_snapshot_age` (P1): latest snapshot age must stay below threshold.
- `account_reconcile_non_ok` (P2): non-OK reconcile count should stay below threshold.

4. Strategy champion-selection integrity
- `strategy_selection_rows_updated_without_transition_total{timeframe}` (P2): any increase means selected rows were written without an accounted transition decision; keep live trading fail-closed until investigated.
- `strategy_selection_transition_total{decision,timeframe}` (P3/P2 trend): should show steady-state `INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, or `PROMOTE_CHALLENGER` activity during reoptimization windows.
- `pairs_cue_projection_total{outcome="PROJECTION_FAILED"}` (P2 trend): increases mean stored champion projection could not be materialized; inspect affected cue logs before trusting operator-facing champion state.

5. Async reoptimization runner (future gated)
- `strategy_reoptimize_lease_heartbeat_age_seconds` (P2/P1 if promotion path is open): active lease heartbeat age must stay below lease TTL plus grace.
- `strategy_reoptimize_budget_exhausted_total{budget}` (P2): any increase means the run must be treated as `DEGRADED` or `FAILED` and recommendation must stay fail-closed.
- `strategy_reoptimize_artifact_write_total{artifact,result}` and `strategy_reoptimize_artifact_read_total{artifact,result}` (P2): `FAILED`, `PARTIAL`, `NOT_FOUND`, or `CONTAINMENT_REJECTED` means terminal recommendations are not trustworthy.
- `strategy_reoptimize_cancel_total{result}` (P2): `FAILED` or `TIMED_OUT` means new runs stay disabled until lease and active run state are inspected.
- `strategy_reoptimize_unsafe_promotion_attempt_total{attempt_type,result}` (P1): any increase requires blocked action, preserved audit logs, and operator review.
- `strategy_reoptimize_telemetry_missing_total{reason}` and `strategy_reoptimize_status_unknown_total{reason}` (P2): any increase means scheduler stays disabled and latest recommendation is `HOLD`.

## Alert Actions

1. If any P1 is triggered:
- Activate or keep kill switch active.
- Pause new ENTRY intents.
- Keep only EMERGENCY_STOP_CLOSE actions available.
- Validate account snapshot freshness and reconcile status before resuming.

2. If only P2 alerts are triggered:
- Continue with reduced manual risk.
- Investigate root cause within the same operator session.
- Re-check alert status after remediation before restoring normal size.

3. If async reoptimization telemetry is missing, stale, or contradictory:
- Keep or set async scheduler disabled.
- Do not enqueue a new mutation-producing run.
- Treat latest recommendation as `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
- Follow `docs/playbooks/async-reoptimization-runner-runbook.md`.

## Operator Loop (every 5-15 minutes in alpha)

1. Read execution summary.
2. Read account summary.
3. Record active alerts and actions in session notes.
4. If P1 persists for 2 consecutive checks, follow incident runbook:
- `docs/playbooks/incident-runbook.md`

## Validation Before Session Close

1. No active P1 alerts.
2. Reconcile latest status is `OK`.
3. Snapshot age below threshold.
4. Any P2 alert has remediation notes and owner.
