# Fail-Closed Recovery Runbook

## Purpose

Provide deterministic operator recovery steps when any safety gate is degraded.

## Recovery Principle

1. Default to blocked entries.
2. Keep emergency close available.
3. Re-open entries only after objective checks pass.

## Recovery Matrix

1. Integrity degraded (`INCOMPLETE`/`FAILED` or low coverage)
- Action: keep kill switch active for new entries.
- Repair: run data backfill workflow and verify integrity history.
- Verify: `tools/scripts/data_pipeline_e2e_check.py` passes.

2. Reconcile not `OK`
- Action: block new entries.
- Repair: fix snapshot drift or stale snapshot source.
- Verify: `GET /v1/account/reconcile?...` returns `status=OK`.

3. Execution stale acknowledgements
- Action: do not add new risk until stale ACK count returns below threshold.
- Repair: validate exchange connectivity, open-orders poller, and status lookup settings.
- Verify: `GET /v1/execution/observability/summary?...` shows no triggered P1 alerts.

4. Credentials incident or rotation in progress
- Action: keep fail-closed mode.
- Repair: rotate vault/KMS secrets and remount files.
- Verify: `tools/scripts/secrets_lifecycle_audit.py` passes.

## Session Recovery Sequence

1. Run readiness check:

```bash
python3 tools/scripts/fail_closed_readiness_check.py \
  --exchange kraken_futures \
  --account-id primary \
  --window-minutes 60 \
  --output-json artifacts/fail_closed_readiness_report.json
```

2. If report recommends `KEEP_FAIL_CLOSED`, do not enable entries.
3. Resolve triggered checks.
4. Re-run readiness check until report recommends `ENABLE_MANUAL_ENTRY`.
5. Run manual trade flow E2E before resuming normal operations:

```bash
python3 tools/scripts/manual_trade_e2e_check.py \
  --timeframe 1m \
  --include-close \
  --require-flat-after-close \
  --output-json artifacts/manual_trade_e2e_report.json
```
