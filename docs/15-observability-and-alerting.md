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
- Optimizer candidate generation count by timeframe (`optimizer_candidate_generated_total`)
- Optimizer promotable-candidate count by timeframe (`optimizer_candidate_promotable_total`)
- Optimizer rejected-candidate count by timeframe/reason (`optimizer_candidate_rejected_total`)
- Candidate probation pass/fail counts by timeframe/reason (`candidate_probation_pass_total`, `candidate_probation_fail_total`)

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
