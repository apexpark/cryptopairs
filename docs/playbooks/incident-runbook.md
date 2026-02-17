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

## Investigation Checklist

1. Data integrity status and unresolved ranges.
2. Exchange adapter connectivity/auth state.
3. Execution queue and order lifecycle anomalies.
4. Account drift and reconciliation mismatches.
5. Recent configuration or deployment changes.

## Containment

1. Keep unsafe paths disabled.
2. Isolate failing module if possible.
3. Preserve logs/events for replay and root-cause analysis.

## Recovery

1. Repair root issue (connectivity, data repair, config rollback, service restart).
2. Verify health checks and critical metrics normalization.
3. Reconcile account and position state against exchange.
4. Resume paper/live mode only after explicit checks pass.

## Post-Incident

1. Write incident summary with timeline, impact, root cause, and remediation.
2. Create follow-up tasks and owner assignments.
3. Update relevant docs and tests to prevent recurrence.
