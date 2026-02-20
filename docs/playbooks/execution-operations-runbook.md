# Execution Operations Runbook

## Purpose

Operator-facing playbook for running manual-first execution safely in paper and live modes.

This runbook uses friendly setting names first, with technical key names in parentheses.

## Operating Modes

1. `Paper Mode`:
- Orders are acknowledged synthetically for workflow testing.
- No live exchange order placement.

2. `Live Mode`:
- Orders are submitted to Kraken Futures.
- Lifecycle is updated from exchange data and fail-closed guards.

## Operator Settings (Friendly -> Technical Key)

1. Trading Mode (`EXECUTION_DISPATCH_MODE`)
- `fail_closed`: block exchange submit (safe default)
- `simulate_ack`: paper testing mode
- `live_kraken`: real exchange submit mode

2. Kraken API Key (`KRAKEN_FUTURES_API_KEY`)
- Required for live mode.

3. Kraken API Secret (Base64) (`KRAKEN_FUTURES_API_SECRET`)
- Required for live mode.

4. Kraken API Base URL (`KRAKEN_FUTURES_API_BASE_URL`)
- Default: `https://futures.kraken.com`

5. Send Order Endpoint (`KRAKEN_FUTURES_SENDORDER_PATH`)
- Default: `/derivatives/api/v3/sendorder`

6. Open Orders Endpoint (`KRAKEN_FUTURES_OPENORDERS_PATH`)
- Default: `/derivatives/api/v3/openorders`

7. Open Orders Poller Enabled (`EXECUTION_OPENORDERS_POLLER_ENABLED`)
- Default: `true`

8. Open Orders Poll Interval Seconds (`EXECUTION_OPENORDERS_POLL_SECONDS`)
- Default: `5`

9. Open Orders Poll Batch Limit (`EXECUTION_OPENORDERS_POLL_BATCH_LIMIT`)
- Default: `200`

10. Order Status Lookup Enabled (`EXECUTION_ORDER_STATUS_LOOKUP_ENABLED`)
- Default: `false`
- Use only when endpoint query parameter behavior is verified.

11. Order Status Endpoint (`KRAKEN_FUTURES_ORDER_STATUS_PATH`)
- Default: `/derivatives/api/v3/orders/status`

12. Order Status Query Key (`KRAKEN_FUTURES_ORDER_STATUS_QUERY_KEY`)
- Default: `orderId`

13. Ack Timeout Poll Seconds (`EXECUTION_ACK_WATCHDOG_POLL_SECONDS`)
- Default: `15`

14. Ack Expiry Threshold Seconds (`EXECUTION_ACK_EXPIRE_AFTER_SECONDS`)
- Default: `90`

15. Ack Timeout Batch Limit (`EXECUTION_ACK_WATCHDOG_BATCH_LIMIT`)
- Default: `200`

16. Account Service URL (`ACCOUNT_SERVICE_URL`)
- Default: `http://127.0.0.1:8081`

17. Reconcile On Terminal State (`EXECUTION_TRIGGER_RECONCILE_ON_TERMINAL`)
- Default: `true`

18. Per-Pair Qty Cap (`EXECUTION_RISK_PER_PAIR_MAX_QTY`)
- Maximum projected open quantity per instrument/pair leg for new `ENTRY` intents.
- Default: `12`

19. Gross Qty Cap (`EXECUTION_RISK_GROSS_MAX_QTY`)
- Maximum projected gross open quantity across all active instruments.
- Default: `40`

20. Max Leverage (`EXECUTION_RISK_MAX_LEVERAGE`)
- Risk gate blocks `ENTRY` intents above this ratio (`margin_used / equity`).
- Default: `3.0`

21. Daily Loss Cap USD (`EXECUTION_RISK_DAILY_LOSS_LIMIT_USD`)
- Risk gate blocks `ENTRY` intents after this UTC-day drawdown.
- Default: `500`

22. Entry Cooldown Seconds (`EXECUTION_RISK_ENTRY_COOLDOWN_SECONDS`)
- Minimum delay between accepted `ENTRY` intents for the same instrument.
- Default: `30`

23. Max Account Snapshot Age Seconds (`EXECUTION_RISK_MAX_SNAPSHOT_AGE_SECONDS`)
- Blocks `ENTRY` intents when account-service snapshot freshness exceeds this threshold.
- Default: `120`

## Recommended Presets

1. Paper Preset
- Trading Mode: `simulate_ack`
- Open Orders Poller Enabled: `false`
- Order Status Lookup Enabled: `false`
- Reconcile On Terminal State: `true`

2. Live Preset
- Trading Mode: `live_kraken`
- Open Orders Poller Enabled: `true`
- Order Status Lookup Enabled: `true` (only after validation)
- Reconcile On Terminal State: `true`

Preset files in repo:
- `infra/env/paper-mode.env.example`
- `infra/env/live-mode.env.example`

## Normal Lifecycle Expectations

1. Manual intent accepted: `NEW -> APPROVED`
2. Dispatch submit: `APPROVED -> PENDING_SUBMIT`
3. Exchange ack: `PENDING_SUBMIT -> ACKNOWLEDGED`
4. Fill flow: `ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED` (or terminal cancel/reject/expire)
5. Terminal states trigger account reconcile hook.
6. Server-truth portfolio endpoint folds spread positions from accepted + acknowledged/fill intents:
- `GET /v1/execution/portfolio/positions?exchange=<...>&account_id=<...>`

Spread metadata for best portfolio fidelity:
- Include `pair_id`, `spread_direction`, and `spread_z` in `POST /v1/execution/order-intent` payloads.

## Quick Troubleshooting

1. Symptom: Order stuck in `ACKNOWLEDGED`
- Check open-orders poller is enabled in live mode.
- Check Kraken auth settings and endpoint paths.
- Check order status lookup setting if order disappears from open orders.
- Confirm watchdog threshold; stale orders should eventually move to `EXPIRED`.

2. Symptom: Unexpected `REJECTED`
- Review dispatch reason in order history endpoint.
- Validate credentials and exchange availability.
- Confirm order status values in logs.

3. Symptom: Reconcile not triggered
- Confirm `Reconcile On Terminal State` is enabled.
- Confirm account-service URL is reachable.

4. Symptom: `ENTRY` blocked by risk gate
- Confirm latest account snapshot exists (`account_snapshots`).
- Confirm account-service snapshot endpoint is returning recent `ts`.
- Check leverage and daily loss against configured caps.
- Check per-pair and gross quantity caps.
- Check cooldown window for recent accepted `ENTRY` intents.

## Validation Checklist Before Live

1. Kill switch behavior verified.
2. Manual ENTRY/EXIT controls verified (`operator_confirmed`, `operator_id`).
3. Dispatch path tested with small order size.
4. Order lifecycle history endpoint checked for deterministic transitions.
5. Reconcile trigger confirmed after terminal transition.

## Live Canary And Fixture Capture

1. Start with smallest allowed order size and one instrument.
2. Confirm expected path in lifecycle history:
- `APPROVED -> PENDING_SUBMIT -> ACKNOWLEDGED -> PARTIALLY_FILLED/FILLED`
3. Capture and redact raw exchange payloads for:
- open orders endpoint
- order status endpoint
4. Save payloads as fixtures under:
- `services/execution-service/tests/fixtures/kraken/`
5. Re-run tests before keeping live mode enabled:
- `cargo test -p execution-service`
