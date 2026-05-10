# Testing Standards

## Purpose

Define required test levels and quality gates across Rust and Python services.

## Test Pyramid

1. Unit tests (fast, deterministic).
2. Integration tests (service and storage boundaries).
3. Replay/regression tests (event-driven determinism).
4. End-to-end smoke tests (critical user paths).

## Hard Rules

1. `MUST` add or update tests for any behavior change.
2. `MUST` include fixture coverage for edge cases in time-series gaps.
3. `MUST` validate strategy metrics against known baseline datasets.
4. `MUST` test execution idempotency and order-state transitions.
5. `MUST` test account reconciliation under partial fill and delayed ack scenarios.
6. `MUST` keep tests reproducible with seed control where randomness exists.

## Language-Specific Requirements

1. Rust:
- The workspace pins its Rust channel in repo-root `rust-toolchain.toml`;
  local development should use rustup-aware `cargo` invocations so rustfmt,
  clippy, and tests honor the repository pin.
- Unit tests alongside modules.
- Integration tests for adapters and persistence boundaries.
- Property tests for parsing/state transitions where helpful.
- `strategy-service` repository integration tests live in
  `services/strategy-service/tests/repository_integration.rs` and exercise
  `StrategyRepository` against real Postgres/TimescaleDB SQL.
- Set `STRATEGY_TEST_DATABASE_URL` to run those tests locally. Typical local
  flow:
  `docker compose up timescaledb`, then
  `STRATEGY_TEST_DATABASE_URL=postgres://cryptopairs:cryptopairs@localhost:5432/cryptopairs cargo test -p strategy-service --test repository_integration`.
- When `STRATEGY_TEST_DATABASE_URL` is unset and `CI` is not `true`, the
  Postgres-backed tests print a `SKIPPED` line and pass without touching a
  database. When `CI=true`, the same missing env var is a hard test failure so
  CI cannot silently stop running persistence-boundary coverage.

2. Python:
- Unit tests for signal generation and statistical calculations.
- Backtest regression tests with fixed datasets and expected metrics bounds.

## Minimum Merge Gates

1. Passing unit and integration tests for affected modules.
2. Passing replay tests when execution/accounting behavior changes.
3. No drop in core coverage for touched files without documented reason.

## Acceptance Checks

1. Synthetic missing-interval datasets trigger expected integrity states.
2. Strategy outputs remain stable across deterministic replay.
3. Order lifecycle remains deterministic under retry/reconnect simulation.

## Out Of Scope

1. Full market scenario simulation across every regime in MVP.
2. Performance benchmarking as a required gate for all PRs (separate benchmark track).
