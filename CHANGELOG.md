# Changelog
All notable changes to this project will be documented in this file.

This project follows SemVer as defined in `docs/02-versioning-and-releases.md`.

## Unreleased
### Added
- Strategy module implementation spec derived from SSRN 151 Trading Strategies review: `docs/18-strategy-module-implementation-spec.md`.
- Initial documentation suite and agent governance scaffolding.
- Rust workspace foundation with:
  - `crates/common-types`
  - `services/kraken-adapter`
  - `services/data-service`
  - `services/execution-service`
- Data integrity contract schemas and example payloads in `specs/contracts/` and `specs/examples/`.
- Local Docker stack (`docker-compose.yml`) for TimescaleDB and Redis.
- SQL bootstrap for candles and data quality interval tables (`infra/sql/init_timescale.sql`).
- Python strategy research scaffold with integrity gate tests (`research/strategy-engine`).
- Strict CI workflow (`.github/workflows/ci.yml`) for Rust, Python, and contract JSON validation.
- Real Kraken REST candle adapter implementation (`services/kraken-adapter/src/lib.rs`) for `1m`, `15m`, `1h`.
- Timescale-backed repository implementation (`services/data-service/src/repository.rs`) for local-first reads and upserts.
- Targeted backfill flow in data query API (`services/data-service/src/lib.rs`): local read -> gap detection -> missing-range backfill -> local re-read.
- Periodic backfill worker (`services/data-service/src/worker.rs`) for configured symbols and windows.
- Integrity audit persistence to `data_quality_intervals` from API queries and worker backfills.
- Bootstrap historical backfill CLI (`services/data-service/src/bin/bootstrap_backfill.rs`) for chunked full-history ingestion.
- Integrity history API endpoint (`GET /v1/integrity/history`) backed by persisted quality intervals.
- Kraken WebSocket trade ingest worker (`services/data-service/src/ws_worker.rs`) with reconnect + live trade persistence.
- Trade storage table initialization (`trades`) and repository insert path.
- `account-service` reconciliation scheduler with persisted drift checks and a manual run endpoint (`POST /v1/account/reconcile/run`).
- `execution-service` HTTP API endpoint (`GET /v1/execution/decision`) for fail-closed integrity gate decisions from stored integrity history.
- Docker Compose app profile wiring for `data-service`, `account-service`, and `execution-service`.
- New contracts and examples:
  - `specs/contracts/execution_decision_response.schema.json`
  - `specs/contracts/reconcile_run_response.schema.json`
  - `specs/examples/execution_decision_response_blocked.example.json`
  - `specs/examples/reconcile_run_response.example.json`
- Execution control persistence (`execution_control`, `execution_control_events`) and order intent audit table (`execution_order_intents`) in SQL bootstrap.
- Execution kill switch API endpoints:
  - `GET /v1/execution/kill-switch`
  - `POST /v1/execution/kill-switch`
- Execution order intent API endpoint:
  - `POST /v1/execution/order-intent` (idempotent, fail-closed)
- Additional execution contracts/examples:
  - `specs/contracts/execution_kill_switch_state.schema.json`
  - `specs/contracts/execution_order_intent_request.schema.json`
  - `specs/contracts/execution_order_intent_response.schema.json`
  - `specs/examples/execution_kill_switch_state_active.example.json`
  - `specs/examples/execution_order_intent_request.example.json`
  - `specs/examples/execution_order_intent_response_blocked.example.json`
- Manual-first execution guardrails:
  - `ENTRY` and `EXIT` intents require operator confirmation and operator ID.
  - `EMERGENCY_STOP_CLOSE` is the only automated action path.
  - Order intent records now persist `action`, `operator_confirmed`, and `operator_id`.
- New example for automated safety close:
  - `specs/examples/execution_order_intent_response_emergency_stop_accepted.example.json`
- `strategy-service` (Rust) added for adaptive pairs cue generation and rolling signal reoptimization:
  - `GET /v1/strategy/pairs/cues`
  - `POST /v1/strategy/pairs/reoptimize`
- Strategy evaluation persistence tables:
  - `strategy_signal_performance`
  - `strategy_selected_signal`
- Strategy cue contracts/examples:
  - `specs/contracts/strategy_pairs_cues_response.schema.json`
  - `specs/contracts/strategy_pairs_reoptimize_response.schema.json`
  - `specs/examples/strategy_pairs_cues_response.example.json`
  - `specs/examples/strategy_pairs_reoptimize_response.example.json`
- Shadow decision-support model in `strategy-service`:
  - Deterministic logistic scorer trained from recent `strategy_signal_performance` rows.
  - Cue-level `shadow_ml` diagnostics plus per-variant shadow probability/rank fields.
  - New audit table `strategy_shadow_model_runs`.
  - Reoptimize response counters for model availability and persisted shadow runs.
- Strategy module slices A-D implemented for advisory controls:
  - New strategy endpoints:
    - `GET /v1/strategy/pairs/cost-gate`
    - `GET /v1/strategy/pairs/portfolio-plan`
  - Extended cues response with:
    - `cost_gate` and `portfolio_hint` on each cue
    - `candidate_set` and `portfolio_plan` response-level diagnostics
  - Reoptimize counters expanded:
    - `cost_gate_pass`, `cost_gate_fail`
    - `portfolio_advice_available`, `portfolio_advice_unavailable`
  - New contracts/examples:
    - `specs/contracts/strategy_pairs_cost_gate_response.schema.json`
    - `specs/contracts/strategy_pairs_portfolio_plan_response.schema.json`
    - `specs/examples/strategy_pairs_cost_gate_response.example.json`
    - `specs/examples/strategy_pairs_portfolio_plan_response.example.json`
  - New strategy advisory configuration keys for fee/slippage/net-edge/exposure caps.
- Execution manual-trading hardening:
  - `execution_order_intents` now records `exchange` and `account_id`.
  - `ENTRY` and `EXIT` intents are additionally gated by latest reconciliation status (`reconciliation_events`), fail-closed on missing/non-OK status.
  - New deterministic lifecycle event table `execution_order_state_events` with initial transitions (`NEW` -> `APPROVED`/`REJECTED`).
  - New lifecycle contract/example:
    - `specs/contracts/execution_order_lifecycle_state_machine.schema.json`
    - `specs/examples/execution_order_lifecycle_state_machine.example.json`
- Focused manual-operator UI workflow session doc:
  - `docs/19-manual-trading-operator-ui-session.md`
- Browser-based operator console (`apps/web`) built with React/Vite for manual-first spread trading:
  - Trade cockpit with stop-prerequisite entry controls, add/reduce exposure, and close-spread action.
  - Live wiring to strategy, data, execution, and account services (no mock trading data path).
  - Analytics page with hypothetical equity curve and historical z-score entry/exit/stop markers.
  - Data Quality page backed by integrity history diagnostics and fail-closed execution gate context.
  - Theme-aware PAIRS logos (dark/light) and global timeframe selector.
- Execution handoff lifecycle slice (fail-closed by default):
  - New endpoint `GET /v1/execution/order-intent/history` for intent + lifecycle + dispatch audit retrieval.
  - New endpoint `POST /v1/execution/order-intent/dispatch` to progress `APPROVED` intents into submit states.
  - New persistence table `execution_dispatch_attempts` for dispatch attempt audit history.
  - New dispatch mode config:
    - `EXECUTION_DISPATCH_MODE=fail_closed` (default)
    - `EXECUTION_DISPATCH_MODE=simulate_ack` (local testing)
  - Lifecycle transition set extended to allow `PENDING_SUBMIT -> REJECTED` for submit failures.
  - New contracts/examples:
    - `specs/contracts/execution_order_state_history_response.schema.json`
    - `specs/contracts/execution_dispatch_response.schema.json`
    - `specs/examples/execution_order_state_history_response.example.json`
    - `specs/examples/execution_dispatch_response_fail_closed.example.json`
    - `specs/examples/execution_dispatch_response_acknowledged.example.json`
- `execution-service` live Kraken dispatch adapter mode (`EXECUTION_DISPATCH_MODE=live_kraken`) behind explicit env configuration:
  - Signed private submit requests to Kraken Futures send-order endpoint.
  - Fail-closed rejection when credentials/config are missing, invalid, or exchange submit fails.
  - Dispatch audit trail retains deterministic lifecycle transitions and exchange order IDs on ack.
- Post-dispatch lifecycle truth sync endpoint in `execution-service`:
  - New endpoint `POST /v1/execution/order-event` for ingesting exchange lifecycle updates by `idempotency_key` or `exchange_order_id`.
  - Deterministic transition enforcement for `ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED`, and `EXPIRED`.
  - New contracts/examples:
    - `specs/contracts/execution_order_event_ingest_request.schema.json`
    - `specs/contracts/execution_order_event_ingest_response.schema.json`
    - `specs/examples/execution_order_event_ingest_request.example.json`
    - `specs/examples/execution_order_event_ingest_response_applied.example.json`
    - `specs/examples/execution_order_event_ingest_response_noop.example.json`
- Automatic execution stale-ack watchdog in `execution-service`:
  - Periodic scan for orders whose latest state is `ACKNOWLEDGED` beyond threshold.
  - Deterministic `ACKNOWLEDGED -> EXPIRED` transition with audited state event (`actor=ack-watchdog`).
  - New config:
    - `EXECUTION_ACK_WATCHDOG_POLL_SECONDS` (default `15`)
    - `EXECUTION_ACK_EXPIRE_AFTER_SECONDS` (default `90`)
    - `EXECUTION_ACK_WATCHDOG_BATCH_LIMIT` (default `200`)
- Terminal-state reconcile hook in `execution-service`:
  - Best-effort trigger to `POST /v1/account/reconcile/run` after terminal transitions:
    `FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`.
  - Applied for dispatch terminal outcomes, explicit order-event ingest terminal updates,
    and ack-watchdog expiries.
  - New config:
    - `ACCOUNT_SERVICE_URL` (default `http://127.0.0.1:8081`)
    - `EXECUTION_TRIGGER_RECONCILE_ON_TERMINAL` (default `true`)
- Live open-orders reconciliation poller in `execution-service` (Kraken futures):
  - Background poller calls `GET /derivatives/api/v3/openorders` and reconciles tracked
    `ACKNOWLEDGED` / `PARTIALLY_FILLED` orders by `exchange_order_id`.
  - Applies deterministic `ACKNOWLEDGED -> PARTIALLY_FILLED` and fill inference transitions
    from open-order payload fields (`filledSize`, `unfilledSize`, `status`).
  - Optional `GET /derivatives/api/v3/orders/status` lookup for orders absent from open orders,
    mapping exchange status values (`FULLY_EXECUTED`, `CANCELLED`, `REJECTED`, etc.) to
    deterministic lifecycle transitions.
  - New config:
    - `EXECUTION_OPENORDERS_POLLER_ENABLED` (default `true`)
    - `EXECUTION_OPENORDERS_POLL_SECONDS` (default `5`)
    - `EXECUTION_OPENORDERS_POLL_BATCH_LIMIT` (default `200`)
    - `KRAKEN_FUTURES_OPENORDERS_PATH` (default `/derivatives/api/v3/openorders`)
    - `EXECUTION_ORDER_STATUS_LOOKUP_ENABLED` (default `false`)
    - `KRAKEN_FUTURES_ORDER_STATUS_PATH` (default `/derivatives/api/v3/orders/status`)
    - `KRAKEN_FUTURES_ORDER_STATUS_QUERY_KEY` (default `orderId`)
- Strategy live z-score feed endpoint:
  - `GET /v1/strategy/pairs/live-z` for near-real-time z-score series + entry/exit/stop markers.
  - New contract/example:
    - `specs/contracts/strategy_pairs_live_z_response.schema.json`
    - `specs/examples/strategy_pairs_live_z_response.example.json`
- Data pipeline reproducible E2E verifier:
  - `tools/scripts/data_pipeline_e2e_check.py` validates health, local-first query integrity,
    and integrity history persistence with machine-readable report output.
- Kraken historical bounds policy and enforcement for market-data backfill:
  - New policy file: `infra/config/kraken_history_bounds.json` (symbol + timeframe bounds).
  - `kraken-adapter` now enforces:
    - earliest allowed start timestamp per symbol/timeframe
    - max candles per request (exchange page depth)
  - `data-service` and `bootstrap_backfill` now load operator-configurable bounds via
    `KRAKEN_HISTORY_BOUNDS_PATH` (with safe fallback to built-in defaults).
- Champion/challenger persistence hardening in `strategy-service`:
  - New drift audit table: `strategy_champion_drift_events`.
  - Champion transition policy now enforces `STRATEGY_CHAMPION_SWITCH_MIN_DELTA` before promotion.
  - Reoptimize response now includes:
    - `drift_rows_written`
    - `champion_promotions`
    - `champion_locks`
- Execution risk-cap package for manual `ENTRY` gating:
  - Added pre-trade caps in `execution-service` for:
    - per-pair qty (`EXECUTION_RISK_PER_PAIR_MAX_QTY`)
    - gross qty (`EXECUTION_RISK_GROSS_MAX_QTY`)
    - leverage (`EXECUTION_RISK_MAX_LEVERAGE`)
    - daily loss (`EXECUTION_RISK_DAILY_LOSS_LIMIT_USD`)
    - entry cooldown (`EXECUTION_RISK_ENTRY_COOLDOWN_SECONDS`)
  - Risk checks are fail-closed when account snapshot state is unavailable.
- Live account snapshot ingestion path for execution risk/reconcile decisions:
  - `execution-service` now reads account/reconcile state from `account-service` HTTP endpoints
    (server-truth boundary) instead of direct SQL table reads.
  - Added account-service day-start snapshot endpoint:
    - `GET /v1/account/snapshot/day-start?exchange=<...>&account_id=<...>&day_start_utc=<RFC3339>`
  - Added snapshot freshness fail-closed gate for `ENTRY`:
    - `EXECUTION_RISK_MAX_SNAPSHOT_AGE_SECONDS` (default `120`)
  - Added account-service response contracts/examples:
    - `specs/contracts/account_snapshot_response.schema.json`
    - `specs/contracts/account_reconcile_response.schema.json`
    - `specs/examples/account_snapshot_response.example.json`
    - `specs/examples/account_reconcile_response.example.json`

### Changed
- Product/risk/architecture docs now explicitly define manual-first live trading for MVP.
- Operator-facing execution settings docs now use friendly labels with technical key mapping,
  with a dedicated runbook: `docs/playbooks/execution-operations-runbook.md`.
- Added operator preset templates for execution mode bring-up:
  - `infra/env/paper-mode.env.example`
  - `infra/env/live-mode.env.example`
- Added replay fixtures for Kraken execution parser hardening:
  - `services/execution-service/tests/fixtures/kraken/openorders.success.json`
  - `services/execution-service/tests/fixtures/kraken/order_status.success.json`
- Web operator console layout and controls:
  - Analytics page now stacks Diagnostics under Strategy Metrics and splits remaining space between Equity and Historical Z-Score charts.
  - Trade analysis chart now renders entry, mean (`z=0`), and stop thresholds with live polling refresh.
  - Settings page now includes session-only Kraken API key/secret/passphrase fields (masked by default).
- Web trade execution flow now consumes execution lifecycle endpoints:
  - after intent acceptance, UI dispatches each leg through `POST /v1/execution/order-intent/dispatch`
  - UI stores and displays lifecycle snapshots from `GET /v1/execution/order-intent/history`
  - local spread position ledger updates only when accepted legs are acknowledged by dispatch
- Trade and Analytics z-score rendering now use strategy-service backend outputs:
  - Trade page z-series uses `/v1/strategy/pairs/live-z`
  - Analytics equity curve remains from `/v1/strategy/pairs/backtest`
- Data query windows are normalized to timeframe boundaries before integrity evaluation and persistence,
  with explicit `REQUEST_WINDOW_NORMALIZED` warning codes for auditability.
- Backfill worker now chunks missing ranges into exchange-safe request pages
  (`<= 2000` candles per request) before adapter calls.
- Added frontend integration coverage for global timeframe switching:
  - verifies refetch across strategy cues/gates/portfolio, execution gates, integrity history,
    and analytics feeds (`live-z` + `backtest`) with timeframe-specific bar depth.
- Cue generation now fail-closes on champion/challenger drift when
  `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` by marking drifted cues non-actionable
  and setting `direction_hint=NONE` until reoptimize policy promotes the challenger.
- `evaluate_order_intent` now includes explicit risk-gate decision routing in addition
  to kill-switch, integrity, and reconcile gates.

### Fixed
- Removed accidental duplicate spec/example files with `* 2.json` suffix.
- Execution lifecycle transition matrix now permits watchdog-driven expiration from
  `ACKNOWLEDGED` and `PARTIALLY_FILLED` (`-> EXPIRED`).
- Integrity false-negative gap detection when request bounds were unaligned to timeframe steps
  (could report `INCOMPLETE` with non-empty candle windows).
