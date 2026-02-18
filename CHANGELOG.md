# Changelog
All notable changes to this project will be documented in this file.

This project follows SemVer as defined in `docs/02-versioning-and-releases.md`.

## Unreleased
### Added
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

### Changed
- Product/risk/architecture docs now explicitly define manual-first live trading for MVP.

### Fixed
- Removed accidental duplicate spec/example files with `* 2.json` suffix.
