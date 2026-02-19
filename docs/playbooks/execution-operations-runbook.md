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

## Normal Lifecycle Expectations

1. Manual intent accepted: `NEW -> APPROVED`
2. Dispatch submit: `APPROVED -> PENDING_SUBMIT`
3. Exchange ack: `PENDING_SUBMIT -> ACKNOWLEDGED`
4. Fill flow: `ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED` (or terminal cancel/reject/expire)
5. Terminal states trigger account reconcile hook.

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

## Validation Checklist Before Live

1. Kill switch behavior verified.
2. Manual ENTRY/EXIT controls verified (`operator_confirmed`, `operator_id`).
3. Dispatch path tested with small order size.
4. Order lifecycle history endpoint checked for deterministic transitions.
5. Reconcile trigger confirmed after terminal transition.
