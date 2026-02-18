# Risk And Execution Policy

## Purpose

Define mandatory controls for converting strategy signals into safe and auditable orders.

## Hard Rules

1. `MUST` apply pre-trade risk checks before any order is sent.
2. `MUST` enforce max position size, leverage, and daily loss caps.
3. `MUST` reject orders without valid idempotency keys.
4. `MUST` track each order through a deterministic lifecycle.
5. `MUST` reconcile fills and positions against exchange state.
6. `MUST` expose a kill switch that halts new order submissions.
7. `MUST` fail closed on unknown risk state.
8. `MUST` require explicit operator confirmation for live `ENTRY` and `EXIT` intents.
9. `MUST` allow automated execution only for emergency stop-close actions.

## Order Lifecycle States

1. `NEW`
2. `PENDING_SUBMIT`
3. `ACKNOWLEDGED`
4. `PARTIALLY_FILLED`
5. `FILLED`
6. `CANCELED`
7. `REJECTED`
8. `EXPIRED`

## Pre-Trade Checks

1. Strategy enabled and approved mode (backtest/paper/live).
2. Data integrity threshold met.
3. Symbol tradability and account permission valid.
4. Exposure and leverage within configured limits.
5. Kill switch not active.
6. Operator confirmation present for `ENTRY` and `EXIT`.

## Post-Trade Checks

1. Fill reconciliation and residual exposure check.
2. Slippage and fee impact attribution.
3. Position and PnL consistency with account service.

## Acceptance Checks

1. Duplicate order submissions do not create duplicate live orders.
2. Replayed order events produce the same terminal states.
3. Risk threshold violations block order submission with explicit reason.

## Failure Handling

1. If reconciliation fails, freeze strategy-to-execution handoff.
2. If exchange acknowledgments lag beyond threshold, trigger alert.
3. If kill switch is activated, cancel open non-reduce-only orders per policy.
4. Emergency stop-close remains allowed even when new entries are blocked.

## Out Of Scope

1. Cross-exchange smart order routing.
2. Advanced options Greeks-based risk management.
