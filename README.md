# Crypto Pairs Trader

This repo is **docs-governed and implementation-active**: policies/contracts define guardrails, and code is added in thin slices.

## Start Here
- `AGENTS.md` (highest precedence; mandatory for agents)
- `docs/README.md` (documentation map + precedence)
- `docs/00-guardrails.md` and `docs/01-product-scope.md`
- `docs/05-agent-build-workflow.md` and `docs/17-verification-protocol.md`
- `docs/20-alpha-delivery-control.md` and `plans/alpha_plan.json` (delivery tracking)

## Alpha Progress Tracking

Use the tracker to keep one active focus and recover quickly after interruptions:

```bash
python3 tools/scripts/alpha_tracker.py summary
```

## Precedence

If instructions conflict, use this order:

1. `AGENTS.md`
2. `docs/00-guardrails.md`
3. `docs/01-product-scope.md`
4. Governance docs in `docs/` (`02-05`, `07`, and `17`)
5. Module policy docs in `docs/` (`10-16` series)
6. Playbooks in `docs/playbooks/`
7. ADRs in `docs/adr/`
8. Temporary notes and ad hoc plans

## Onboarding Flow

1. Read scope and guardrails (`docs/00-guardrails.md`, `docs/01-product-scope.md`).
2. Read governance workflow/policies (`docs/02-05`, `docs/07`, `docs/17`).
3. Review architecture and domain policies (`docs/10-architecture.md` plus relevant `11-16` docs).
4. Use runbooks and ADRs for operations and design decisions.

## Contracts
Machine-readable contracts should live in:
- `specs/contracts/`
with examples in:
- `specs/examples/`

## Local Stack (Docker)
Prerequisites:
- Rust toolchain (`cargo`, `rustc`)
- Docker Desktop (`docker`, `docker compose`)
- Python 3.9+ for research tests

Start local storage dependencies:

```bash
docker compose up -d
```

Start Rust application services in Docker:

```bash
docker compose --profile app up -d data-service account-service execution-service strategy-service
```

Services:
- TimescaleDB (PostgreSQL) on `localhost:5432`
- Redis on `localhost:6379`
- Data service on `localhost:8080` (app profile)
- Account service on `localhost:8081` (app profile)
- Execution service on `localhost:8082` (app profile)
- Strategy service on `localhost:8083` (app profile)

## Web Operator Console

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

Run frontend checks:

```bash
cd apps/web
npm run test -- --run
npm run build
```

## Run Checks

```bash
cargo test --workspace
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

```bash
python -m pip install ruff pytest
PYTHONPATH=research/strategy-engine/src pytest research/strategy-engine/tests -q
ruff check research
```

## Run Data Service

```bash
cargo run -p data-service
```

Current behavior:
- Reads requested candles from local Timescale first.
- Detects missing ranges for `1m`, `15m`, `1h`.
- Performs targeted Kraken backfill only for missing ranges.
- Re-queries local store and returns data + integrity report.
- Enforces Kraken historical start bounds + page-depth limits per symbol/timeframe
  using `KRAKEN_HISTORY_BOUNDS_PATH` (default: `infra/config/kraken_history_bounds.json`).
- Background worker continuously backfills configured symbols (`KRAKEN_SYMBOLS`).
- WebSocket worker subscribes to Kraken Futures trade feed and persists live trades.
- Symbol conventions: `PI_*` = inverse perpetual contracts, `PF_*` = linear perpetual contracts.

## Integrity History Endpoint

```bash
GET /v1/integrity/history?instrument=PF_XBTUSD&timeframe=1m&limit=100
```

Returns recent integrity audit rows from `data_quality_intervals`.

## Execution Decision Endpoint

```bash
GET /v1/execution/decision?instrument=PF_XBTUSD&timeframe=1m
```

Returns a fail-closed decision (`ALLOWED` or `BLOCKED`) using persisted integrity history.

## Execution Kill Switch Endpoints

```bash
GET /v1/execution/kill-switch
POST /v1/execution/kill-switch
```

The kill switch is fail-closed; when state is unknown, order intents are blocked.

## Execution Order Intent Endpoint

```bash
POST /v1/execution/order-intent
```

Evaluates idempotent order intents against kill switch + integrity gate and persists the decision.
`ENTRY` and `EXIT` are now also gated by latest account reconciliation status (fail-closed).

Manual-first behavior:
- `ENTRY` and `EXIT` require `operator_confirmed=true` plus `operator_id`.
- `ENTRY` and `EXIT` require `exchange` and `account_id` for reconciliation gate checks.
- Optional spread metadata (`pair_id`, `spread_direction`, `spread_z`) can be supplied for
  server-truth spread ledger reconstruction.
- `EMERGENCY_STOP_CLOSE` is the only action allowed without operator confirmation.
- Lifecycle events are persisted in `execution_order_state_events` (`NEW`, `APPROVED`, `REJECTED`, etc.).

## Execution Lifecycle History Endpoint

```bash
GET /v1/execution/order-intent/history?idempotency_key=<key>
```

Returns the persisted intent record, lifecycle state events, and dispatch attempt audit rows.

## Execution Portfolio Positions Endpoint

```bash
GET /v1/execution/portfolio/positions?exchange=kraken_futures&account_id=primary
```

Returns server-truth spread positions folded from accepted + acknowledged/fill lifecycle events.

## Execution Dispatch Endpoint

```bash
POST /v1/execution/order-intent/dispatch
```

Dispatches an `ACCEPTED` + `APPROVED` intent into the submit lifecycle:
- `APPROVED` -> `PENDING_SUBMIT` -> `ACKNOWLEDGED` (simulate mode)
- `APPROVED` -> `PENDING_SUBMIT` -> `REJECTED` (default fail-closed mode)

Operator Settings (friendly name -> technical key):
- Trading Mode (`EXECUTION_DISPATCH_MODE`): `fail_closed` (default), `simulate_ack`, `live_kraken`.
- Kraken API Key (`KRAKEN_FUTURES_API_KEY`): required for `live_kraken`.
- Kraken API Secret (Base64) (`KRAKEN_FUTURES_API_SECRET`): required for `live_kraken`.
- Kraken API Key Mounted File (`KRAKEN_FUTURES_API_KEY_FILE`): optional file source, preferred for hosted mode.
- Kraken API Secret Mounted File (`KRAKEN_FUTURES_API_SECRET_FILE`): optional file source, preferred for hosted mode.
- Kraken API Key Secret Reference (`KRAKEN_FUTURES_API_KEY_REF`): operator metadata for vault/KMS source.
- Kraken API Secret Reference (`KRAKEN_FUTURES_API_SECRET_REF`): operator metadata for vault/KMS source.
- Kraken API Base URL (`KRAKEN_FUTURES_API_BASE_URL`): default `https://futures.kraken.com`.
- Send Order Endpoint (`KRAKEN_FUTURES_SENDORDER_PATH`): default `/derivatives/api/v3/sendorder`.
- Open Orders Endpoint (`KRAKEN_FUTURES_OPENORDERS_PATH`): default `/derivatives/api/v3/openorders`.
- Open Orders Poller Enabled (`EXECUTION_OPENORDERS_POLLER_ENABLED`): default `true`.
- Open Orders Poll Interval Seconds (`EXECUTION_OPENORDERS_POLL_SECONDS`): default `5`.
- Open Orders Poll Batch Limit (`EXECUTION_OPENORDERS_POLL_BATCH_LIMIT`): default `200`.
- Order Status Lookup Enabled (`EXECUTION_ORDER_STATUS_LOOKUP_ENABLED`): default `false`.
- Order Status Endpoint (`KRAKEN_FUTURES_ORDER_STATUS_PATH`): default `/derivatives/api/v3/orders/status`.
- Order Status Query Key (`KRAKEN_FUTURES_ORDER_STATUS_QUERY_KEY`): default `orderId`.
- Ack Timeout Poll Seconds (`EXECUTION_ACK_WATCHDOG_POLL_SECONDS`): default `15`.
- Ack Expiry Threshold Seconds (`EXECUTION_ACK_EXPIRE_AFTER_SECONDS`): default `90`.
- Ack Timeout Batch Limit (`EXECUTION_ACK_WATCHDOG_BATCH_LIMIT`): default `200`.
- Account Service URL (`ACCOUNT_SERVICE_URL`): default `http://127.0.0.1:8081`.
- Reconcile On Terminal State (`EXECUTION_TRIGGER_RECONCILE_ON_TERMINAL`): default `true`.
- Per-Pair Qty Cap (`EXECUTION_RISK_PER_PAIR_MAX_QTY`): default `12`.
- Gross Qty Cap (`EXECUTION_RISK_GROSS_MAX_QTY`): default `40`.
- Max Leverage (`EXECUTION_RISK_MAX_LEVERAGE`): default `3.0`.
- Daily Loss Cap USD (`EXECUTION_RISK_DAILY_LOSS_LIMIT_USD`): default `500`.
- Entry Cooldown Seconds (`EXECUTION_RISK_ENTRY_COOLDOWN_SECONDS`): default `30`.
- Max Account Snapshot Age Seconds (`EXECUTION_RISK_MAX_SNAPSHOT_AGE_SECONDS`): default `120`.
- Execution Risk-Block Ratio Alert Threshold (`EXECUTION_ALERT_RISK_BLOCK_RATIO_P2`): default `0.25`.
- Execution Dispatch-Reject Ratio Alert Threshold (`EXECUTION_ALERT_DISPATCH_REJECT_RATIO_P2`): default `0.15`.
- Execution Stale-ACK Count Alert Threshold (`EXECUTION_ALERT_STALE_ACK_COUNT_P1`): default `1`.
- Execution Reconcile-Block Count Alert Threshold (`EXECUTION_ALERT_RECONCILE_BLOCK_COUNT_P1`): default `1`.
- Account Snapshot Age Alert Threshold (`ACCOUNT_ALERT_MAX_SNAPSHOT_AGE_SECONDS_P1`): default `120`.
- Account Reconcile Non-OK Count Alert Threshold (`ACCOUNT_ALERT_RECONCILE_NON_OK_COUNT_P2`): default `1`.

Operator playbook: `docs/playbooks/execution-operations-runbook.md`
Preset examples:
- `infra/env/paper-mode.env.example`
- `infra/env/live-mode.env.example`
- `infra/env/hosted-mode.env.example`

Hosted secrets lifecycle policy:
- `infra/config/hosted_secrets_rotation_policy.json`

The execution service includes an automatic stale-ack watchdog:
- any order stuck in `ACKNOWLEDGED` beyond the configured threshold is deterministically
  transitioned to `EXPIRED` with an audit event.

Terminal lifecycle transitions (`FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`) now trigger
`POST /v1/account/reconcile/run` as a best-effort synchronization hook.

New `ENTRY` intents are also pre-gated by fail-closed risk caps (per-pair qty, gross qty,
leverage, daily loss, cooldown) using account-service snapshots and active intent exposure.
`ENTRY` is blocked when account snapshot freshness exceeds
`EXECUTION_RISK_MAX_SNAPSHOT_AGE_SECONDS`.

When `EXECUTION_DISPATCH_MODE=live_kraken`, an open-orders poller now reads
`GET /derivatives/api/v3/openorders` and applies deterministic `ACKNOWLEDGED -> PARTIALLY_FILLED`
or `-> FILLED` transitions when supported by open-order fields.

If an order disappears from `openorders`, an optional order-status lookup can resolve terminal
states (`FULLY_EXECUTED`, `CANCELLED`, `REJECTED`) when enabled.

Replay fixtures for hardening live parser behavior:
- `services/execution-service/tests/fixtures/kraken/openorders.success.json`
- `services/execution-service/tests/fixtures/kraken/order_status.success.json`
- `services/execution-service/tests/fixtures/kraken/normalization_matrix.json`

## Execution Order Event Ingest Endpoint

```bash
POST /v1/execution/order-event
```

Applies post-dispatch exchange lifecycle truth (`ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`)
to existing order intents using strict deterministic transition checks.
Identity can be supplied by `idempotency_key` or `exchange_order_id`.
Invalid transitions are fail-closed as `NOOP` (no state mutation).

## Account Reconcile Run Endpoint

```bash
POST /v1/account/reconcile/run
```

Runs a reconciliation pass for all accounts with recent snapshots and persists results.

## Account Snapshot Read Endpoints

```bash
GET /v1/account/snapshot?exchange=kraken_futures&account_id=primary
GET /v1/account/snapshot/day-start?exchange=kraken_futures&account_id=primary&day_start_utc=2026-02-20T00:00:00Z
```

Execution risk checks consume these account-service endpoints as server-truth inputs.

## Observability Summary Endpoints

```bash
GET /v1/execution/observability/summary?exchange=kraken_futures&account_id=primary&window_minutes=60
GET /v1/account/observability/summary?exchange=kraken_futures&account_id=primary&window_minutes=60
```

These endpoints provide operator-facing alert evaluations and SLO threshold context for
execution risk/dispatch health and account snapshot/reconcile health.

## Strategy Pairs Cues Endpoint

```bash
GET /v1/strategy/pairs/cues?timeframe=1m&limit=20
```

Returns adaptive pairs cue candidates with champion/challenger variant diagnostics for manual action.
Each cue now includes `shadow_ml` diagnostics (availability, model quality, recommended variant)
and per-variant `shadow_success_probability`/`shadow_rank_score` fields for decision support.
Each cue also includes a fail-closed `cost_gate` block and a `portfolio_hint` advisory block.
Response-level `candidate_set` and `portfolio_plan` objects summarize scan quality and suggested sizing.

## Strategy Backtest Endpoint

```bash
GET /v1/strategy/pairs/backtest?timeframe=1m&pair_id=PF_XBTUSD__PF_ETHUSD&bars=300
```

Returns deterministic, backend-generated analytics series for the selected pair:
- `points[]` with `ts`, `z`, and simulated `equity`
- `markers[]` for `entry`, `exit`, and `stop`
- selected variant + active trading bands used for the simulation

## Strategy Live Z Endpoint

```bash
GET /v1/strategy/pairs/live-z?timeframe=1m&pair_id=PF_XBTUSD__PF_ETHUSD&points=300
```

Returns near-real-time z-score series + entry/exit/stop markers for Trade-page operator timing cues.

## Strategy Cost Gate Endpoint

```bash
GET /v1/strategy/pairs/cost-gate?timeframe=1m
```

Returns edge-versus-cost diagnostics (`expected_edge_bps`, fee/funding/slippage, pass/fail) for each pair.

## Strategy Portfolio Plan Endpoint

```bash
GET /v1/strategy/pairs/portfolio-plan?timeframe=1m
```

Returns advisory pair weights with dollar-neutrality and exposure cap constraints for manual execution support.

## Strategy Reoptimize Endpoint

```bash
POST /v1/strategy/pairs/reoptimize
```

Runs rolling recent-performance evaluation and persists selected signal variants by pair/timeframe.
Response includes shadow model counters, cost-gate pass/fail counters, and portfolio advisory availability counters.
Champion/challenger handling is hardened with:
- `STRATEGY_CHAMPION_SWITCH_MIN_DELTA` (minimum score delta required before champion promotion)
- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT` (fail-closed cue gating when live challenger drifts from stored champion)

## Bootstrap Historical Backfill

```bash
cargo run -p data-service --bin bootstrap_backfill
```

This command:
- Pulls real Kraken candles in chunked windows from `BOOTSTRAP_START_TS`.
- Upserts candles to local Timescale.
- Writes integrity audit rows into `data_quality_intervals` for each chunk.

## Data Pipeline E2E Validation

```bash
python3 tools/scripts/data_pipeline_e2e_check.py \
  --data-service-url http://127.0.0.1:8080 \
  --instrument PF_XBTUSD \
  --timeframe 1m \
  --output-json artifacts/data_pipeline_e2e_report.json
```

The script checks live service health, queries local-first candles, validates integrity metadata,
reads integrity history, and emits a machine-readable pass/fail report.

## Manual Trade E2E Validation

```bash
python3 tools/scripts/manual_trade_e2e_check.py \
  --timeframe 1m \
  --include-close \
  --require-flat-after-close \
  --output-json artifacts/manual_trade_e2e_report.json
```

The script validates a full manual-first trading slice:
- strategy cue selection
- integrity warm-up for pair legs
- account snapshot + reconcile gate seeding
- kill-switch preflight
- order intent + dispatch + lifecycle history
- portfolio spread position update
- optional emergency-stop-close and flat-position check
- reconcile run and final status check

## Secrets Lifecycle Audit

```bash
python3 tools/scripts/secrets_lifecycle_audit.py \
  --policy-json infra/config/hosted_secrets_rotation_policy.json \
  --env-file infra/env/hosted-mode.env.example \
  --output-json artifacts/secrets_lifecycle_audit_report.json
```

Use this audit before hosted/live operation to verify secret references, mounted-file wiring,
and optional rotation-age checks.

## Fail-Closed Readiness Check

```bash
python3 tools/scripts/fail_closed_readiness_check.py \
  --exchange kraken_futures \
  --account-id primary \
  --window-minutes 60 \
  --output-json artifacts/fail_closed_readiness_report.json
```

Use this pre-session gate before enabling manual entries. If report recommends
`KEEP_FAIL_CLOSED`, keep entry actions blocked and follow:
- `docs/playbooks/fail-closed-recovery-runbook.md`

## Kraken History Depth Probe (Live Data)

Run:

```bash
python3 tools/scripts/kraken_history_depth_probe.py \
  --symbol PF_XBTUSD \
  --timeframes 1m 15m 1h \
  --output-json specs/examples/kraken_history_depth_probe_PF_XBTUSD.json
```

The generated report captures earliest returned candles, page continuity checks, and pagination flags for each timeframe.

Configured historical bounds file:

- `infra/config/kraken_history_bounds.json`
- Loaded by data-service/bootstrap via:
  - `Historical Bounds File (KRAKEN_HISTORY_BOUNDS_PATH)`

## Monorepo Layout
- `services/` Rust services (`kraken-adapter`, `data-service`, `strategy-service`, `execution-service`, `account-service`)
- `crates/` shared Rust types and contracts
- `research/` Python strategy research scaffolding
- `apps/` UI applications
- `infra/` local infra and SQL bootstrap
- `specs/` schema contracts and examples

## Versioning
See `docs/02-versioning-and-releases.md` and `CHANGELOG.md`.
