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

5. Async reoptimization Slice F readiness
- `strategy_reoptimize_active_runs{status}` (P2): any unexpected nonzero
  active status before operator approval blocks canary review.
- `strategy_reoptimize_run_total{trigger,status}` (P2): terminal `FAILED` or
  `DEGRADED` counts during a canary keep recommendations at `HOLD`.
- `strategy_reoptimize_budget_exhausted_total{budget}` (P2): any increase is
  fail-closed and requires budget/load review.
- `strategy_reoptimize_telemetry_missing_total{reason}` (P2): any increase
  blocks canary trust until telemetry is restored.
- `strategy_reoptimize_status_unknown_total{reason}` (P2): any increase
  blocks canary trust until status persistence/contract evidence is known.
- `strategy_reoptimize_fail_closed_total{reason="UNSAFE_PROMOTION_ATTEMPT"}`
  (P1): any increase requires preserving audit logs and confirming no
  automatic promote path executed.
- `strategy_reoptimize_fail_closed_total{reason="REPAIR_PROVENANCE_ACTIVE"}`
  (P2): evidence must show repair-only provenance stayed blocked; this signal
  is not promotion evidence.

Missing async reoptimization alert rules, missing routes, or dashboards that
render absent data as healthy are Slice F stop conditions. Capture alert rules
and active alert state in
`specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json`
format before any canary review.

Repo-side Slice F alert templates:

- `infra/alerts/slice_f_reoptimization_alert_rules.example.json`
- `infra/alerts/slice_f_reoptimization_prometheus_rules.example.yml`

These templates are not deployed alert evidence. Validate template coverage
with `python3 tools/scripts/validate_slice_f_alert_rules.py
infra/alerts/slice_f_reoptimization_alert_rules.example.json`, then capture the
host's deployed/routed alert state separately.

| Slice F alert id | Severity | Source signal | Fail-closed action |
| --- | --- | --- | --- |
| `stuck_lease` | P2 | `strategy_reoptimize_active_runs{status}` plus lease/status evidence | Keep runner disabled; inspect lease owner, generation, heartbeat, and status rows. |
| `failed_degraded_runs` | P2 | `strategy_reoptimize_run_total{trigger,status}` terminal non-success | Keep recommendations at `HOLD` or `OPERATOR_REVIEW_REQUIRED`. |
| `schedule_missed` | P2 | scheduler enqueue/fail-closed counters while explicitly enabled | Keep scheduler disabled until health, integrity, lease, and status evidence agree. |
| `budget_exhaustion` | P2 | `strategy_reoptimize_budget_exhausted_total{budget}` | Keep canary blocked and review operator-approved budgets/load. |
| `cancellation_failure` | P2 | `strategy_reoptimize_cancel_total{result="FAILED"|"TIMED_OUT"}` | Preserve audit evidence; cancellation never becomes `SUCCEEDED`. |
| `missing_telemetry` | P2 | `strategy_reoptimize_telemetry_missing_total{reason}` | Restore telemetry before any canary trust. |
| `unknown_status` | P2 | `strategy_reoptimize_status_unknown_total{reason}` | Treat status as blocked; do not accept the run as success. |
| `unsafe_promotion` | P1 | `strategy_reoptimize_fail_closed_total{reason="UNSAFE_PROMOTION_ATTEMPT"}` | Confirm no automatic `PROMOTE` path executed and keep promotion manual. |
| `repair_provenance_active` | P2 | `strategy_reoptimize_fail_closed_total{reason="REPAIR_PROVENANCE_ACTIVE"}` plus Trade Now evidence | Prove `RECANONICALIZED_LEGACY_ROW` remains excluded and non-trade-eligible. |

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
- For async reoptimization Slice F, do not enable the runner or scheduler and
  keep maintenance/report recommendations at `HOLD` until the evidence
  manifest passes `tools/scripts/slice_f_evidence_check.py`.

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
