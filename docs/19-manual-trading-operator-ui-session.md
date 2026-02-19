# Manual Trading UI Session (Focused)

## Goal
Lock a manual-first operator workflow that converts strategy cues into explicit entry/exit actions while preserving fail-closed behavior.

## Operator Workflow
1. Select timeframe (`1m`, `15m`, `1h`) and pair.
2. Review cue panel: z-score, half-life, cost gate status, portfolio hint.
3. Review execution readiness panel:
- Kill switch state
- Integrity gate status
- Reconcile gate status (`exchange`, `account_id`)
4. Choose action (`ENTRY`, `EXIT`, `EMERGENCY_STOP_CLOSE`) and side (`BUY`, `SELL`).
5. Confirm trade with explicit operator confirmation.
6. Submit order intent and read deterministic result (`ACCEPTED`/`BLOCKED`) with reason.
7. Track lifecycle timeline from state events (`NEW`, `APPROVED`, `REJECTED`, etc.).

## Required Visual Cues
- Green: all gates pass and action can be submitted.
- Amber: warning state (for example stale account snapshot).
- Red: blocked state with explicit reason string.
- Sticky emergency control: one-click emergency stop close per active instrument.

## Layout (Desktop-first)
1. Left column: strategy opportunities table (pair, timeframe, z-score, edge, cost gate, regime).
2. Center column: selected opportunity detail + entry/exit controls.
3. Right column: risk and safety rail cards (kill switch, integrity, reconcile, recent lifecycle events).

## API Surface Used
- `GET /v1/strategy/pairs/cues?timeframe=...`
- `GET /v1/execution/kill-switch`
- `GET /v1/execution/decision?instrument=...&timeframe=...`
- `POST /v1/execution/order-intent`
- `GET /v1/account/reconcile?exchange=...&account_id=...`

## Initial Interaction Rules
1. `ENTRY` and `EXIT` buttons are disabled unless operator confirmation toggle is enabled and operator ID is present.
2. `ENTRY` and `EXIT` are disabled when kill switch is active.
3. `ENTRY` and `EXIT` show blocked state if integrity/reconcile gates fail.
4. `EMERGENCY_STOP_CLOSE` is always available and bypasses integrity/reconcile gate.

## Notes
- This is a design lock for MVP manual operations.
- Automated execution remains out of scope for this UI slice.
