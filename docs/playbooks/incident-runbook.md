# Incident Runbook

## Purpose

Provide a standard response for production-impacting failures in data, execution, risk, or account reconciliation.

## Severity Levels

1. `SEV-1`: potential financial loss or unsafe live behavior.
2. `SEV-2`: major degradation with no immediate unsafe execution.
3. `SEV-3`: limited degradation or recoverable subsystem failure.

## Immediate Actions

1. For `SEV-1`, activate kill switch and halt new live orders.
2. Capture incident timestamp and primary symptom.
3. Identify impacted modules and symbols.
4. Assign incident owner.
5. Keep `EMERGENCY_STOP_CLOSE` available for open spread risk reduction.

## Investigation Checklist

1. Data integrity status and unresolved ranges.
2. Exchange adapter connectivity/auth state.
3. Execution queue and order lifecycle anomalies.
4. Account drift and reconciliation mismatches.
5. Recent configuration or deployment changes.
6. Strategy cost gate behavior (`pass/fail` spikes, negative net-edge drift).
7. Portfolio advisory status (`AVAILABLE`/`UNAVAILABLE`) and rationale codes.

## Containment

1. Keep unsafe paths disabled.
2. Isolate failing module if possible.
3. Preserve logs/events for replay and root-cause analysis.

## Recovery

1. Repair root issue (connectivity, data repair, config rollback, service restart).
2. Verify health checks and critical metrics normalization.
3. Reconcile account and position state against exchange.
4. Resume paper/live mode only after explicit checks pass.
5. Confirm strategy cues are fail-closed when advisory or cost model inputs are degraded.
6. Run objective readiness gate:

```bash
python3 tools/scripts/fail_closed_readiness_check.py \
  --exchange kraken_futures \
  --account-id primary \
  --window-minutes 60 \
  --output-json artifacts/fail_closed_readiness_report.json
```

7. If credentials were involved, run:

```bash
python3 tools/scripts/secrets_lifecycle_audit.py \
  --policy-json infra/config/hosted_secrets_rotation_policy.json \
  --env-file infra/env/hosted-mode.env.example \
  --output-json artifacts/secrets_lifecycle_audit_report.json
```

8. Confirm manual trade vertical slice is healthy:

```bash
python3 tools/scripts/manual_trade_e2e_check.py \
  --timeframe 1m \
  --include-close \
  --require-flat-after-close \
  --output-json artifacts/manual_trade_e2e_report.json
```

## Post-Incident

1. Write incident summary with timeline, impact, root cause, and remediation.
2. Create follow-up tasks and owner assignments.
3. Update relevant docs and tests to prevent recurrence.
