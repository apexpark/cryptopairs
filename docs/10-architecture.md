# System Architecture

## Purpose

Define module boundaries, responsibilities, and key interfaces.

## Module Overview

1. `exchange-adapter-kraken` (Rust)
- REST/WebSocket connectivity, auth signing, retries, reconnects, rate limits.
- Emits normalized events and supports order/account APIs.

2. `data-service` (Rust)
- Local-first query service for historical and near-real-time data.
- Gap detection and targeted backfill orchestration.

3. `strategy-engine` (Python first, Rust later for live-critical paths)
- Backtesting and forward testing.
- First strategy: pairs/stat-arb module.
- Live cue scaffold: `strategy-service` (Rust) for adaptive signal ranking and manual action prompts.
- Shadow ML diagnostics run in decision-support mode only (no autonomous order execution changes).

4. `execution-service` (Rust)
- Signal-to-order translation.
- Manual-first control path in MVP: strategy cues -> operator action -> order intent.
- Pre-trade risk checks, idempotent order submission, order state machine.

5. `account-service` (Rust)
- Positions, PnL, balance, margin, and reconciliation.

6. `settings-secrets` (Rust or backend utility service)
- Profile/config management and secure credential access.

7. `web-app` (React)
- Dashboard for integrity, strategy performance, positions, risk, and controls.

## Data Plane

1. Live ingestion via WebSocket to local store.
2. Historical backfill via REST.
3. Hot-window cache (optional Redis) + historical store (TimescaleDB).

## Control Plane

1. Job scheduler for backfill tasks.
2. Strategy run orchestration.
3. Health and incident signaling.

## Contract Rules

1. Every cross-module message includes `schema_version`.
2. Every data response includes `integrity_status`.
3. Every order command includes `idempotency_key`.
4. Every state transition is logged with a stable correlation ID.

## Acceptance Checks

1. Module can fail independently without cascading data corruption.
2. Execution remains disabled when risk or data integrity checks fail.
3. Replay of events reproduces account/execution state transitions.
