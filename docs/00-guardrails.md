# Engineering Guardrails

## Purpose

Define non-negotiable rules for building and operating the trading platform.

## Hard Rules

1. `MUST` treat market data integrity as a first-class safety control.
2. `MUST` serve data from local storage first, then backfill only missing ranges.
3. `MUST NOT` run live trading when data integrity or risk checks fail.
4. `MUST` keep exchange-facing code deterministic and auditable.
5. `MUST` separate strategy logic from execution and account state transitions.
6. `MUST` use idempotency keys for order placement and stateful retries.
7. `MUST` secure API credentials outside source control and encrypted at rest.
8. `MUST` make every service observable (logs, metrics, health, alerts).
9. `MUST` prefer additive schema changes with versioned contracts.
10. `MUST` document material design/architecture decisions as ADRs.

## Build Principles

1. Local-first development, cloud-ready deployment.
2. Rust for low-latency and safety-critical services.
3. Python for rapid quantitative research and early strategy iteration.
4. Keep interfaces explicit so strategy components can be swapped safely.

## Required Gates Before Merge

1. Unit tests for new logic.
2. Integration tests for boundary interfaces.
3. Replay test for execution/accounting if order lifecycle changed.
4. Data quality checks if ingestion/backfill changed.
5. Security check if credentials/auth paths changed.

## Failure Handling

1. Fail closed for execution and risk controls.
2. Fail visible for data integrity (return status + warnings, not silent success).
3. Trigger runbook and incident logging for unresolved integrity gaps.

## Out Of Scope

1. Fully autonomous online retraining without human approval.
2. Manual ad hoc production changes that bypass documented controls.
