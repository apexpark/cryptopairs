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
