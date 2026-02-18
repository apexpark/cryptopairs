# Product Scope

## Purpose

Define what this system is intended to do in the first production-capable milestone.

## In Scope (MVP)

1. Kraken Futures market data ingestion (REST backfill + WebSocket live).
2. Local market data repository with multi-timeframe support.
3. Data integrity status and gap reporting for every data request.
4. Pairs trading strategy module (research + backtest + forward/paper).
5. Manual-first execution module with order lifecycle tracking, risk checks, and operator-confirmed entry/exit controls.
6. Account management (balances, positions, realized/unrealized PnL).
7. Browser UI for data health, strategy runs, positions, and controls.
8. Secure settings management for API credentials.

## Out Of Scope (MVP)

1. Multi-exchange execution routing.
2. Portfolio optimization across many strategy families.
3. Fully autonomous parameter retraining and live rollout without approval.
4. Complex HFT microstructure models.

## Success Criteria

1. Data coverage target: `>= 99.5%` for required strategy windows.
2. Backfill completion SLA: configured per timeframe and window.
3. Strategy runs blocked when integrity policy fails.
4. End-to-end paper trading flow from signal to fill reconciliation.
5. Full observability and incident traceability.
6. Live entry/exit requires explicit operator confirmation; only emergency stop-close may run automatically.

## Non-Functional Requirements

1. Deterministic replay for strategy/execution paths.
2. Clear degradation behavior under exchange/API failures.
3. Secure key handling and action audit trail.
