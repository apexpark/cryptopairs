# Slice F Alert Deployment Checklist

This checklist is deployable guidance only. It is not applied by the
repository, not routed host alerting, and not active alert state evidence.

Use it when the operator is ready to deploy or verify Slice F async
reoptimization alerts. The resulting host captures must still be recorded in a
Slice F evidence bundle and validated with:

```bash
python3 tools/scripts/slice_f_evidence_check.py path/to/slice_f_manifest.json
```

## Inputs

1. Alert queries based on
   `infra/alerts/slice_f_reoptimization_prometheus_rules.example.yml` or an
   equivalent host alerting system.
2. Required alert coverage from
   `infra/alerts/slice_f_reoptimization_alert_rules.example.json`.
3. Operator-approved threshold artifact matching
   `specs/contracts/slice_f_threshold_approval.schema.json`.
4. Pre-canary active alert state capture.
5. Routing destination and dashboard or alert inspection path.

## Deployment Checks

Complete every check before treating alert evidence as ready:

1. Deploy the alert definitions to the host alerting system.
2. Confirm every required rule id is present:
   `stuck_lease`, `failed_degraded_runs`, `schedule_missed`,
   `budget_exhaustion`, `cancellation_failure`, `missing_telemetry`,
   `unknown_status`, `unsafe_promotion`, and `repair_provenance_active`.
3. Confirm every rule is routed to the operator-approved destination.
4. Confirm the alert inspection path or dashboard query path is available.
5. Confirm missing series, missing status, stale status, and unknown status
   render blocked or firing, not green.
6. Confirm alert labels stay bounded and do not include `run_id`, `pair_id`,
   `operator_id`, `lease_owner`, hostnames, container ids, artifact paths,
   URLs, or free-form error text.
7. Capture active alert state before any canary. For readiness-only bundles,
   this is the `alerts_before` artifact.
8. If a canary is explicitly authorized later, capture `alerts_after` before
   considering the bundle complete.

## Evidence Mapping

| Evidence | Manifest field or artifact |
|---|---|
| Deployed alert definitions or equivalent queries | `alerting.rules[].configured=true` and `alerts_config` |
| Routing destination | `alerting.routed=true`, `alerting.routing_destination`, and `alerts_config` |
| Dashboard or query path | `alerting.dashboard_or_query_path` |
| Missing-data behavior | `alerting.missing_data_blocks=true` |
| Pre-canary active alert state | `alerting.rules[].before_state_captured=true` and `alerts_before` |
| Post-canary active alert state | `alerting.rules[].after_state_captured=true` and `alerts_after` |
| CPU and hot endpoint threshold approval | `thresholds.approved_before_canary=true` and `threshold_approval` |

If any evidence is missing or contradictory, keep
`STRATEGY_REOPT_WORKER_ENABLED=false`, keep scheduler enablement disabled, and
keep downstream recommendations at `HOLD`.
