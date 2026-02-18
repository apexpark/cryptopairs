# Crypto Pairs Trader

This repo is **docs-governed and implementation-active**: policies/contracts define guardrails, and code is added in thin slices.

## Start Here
- `AGENTS.md` (highest precedence; mandatory for agents)
- `docs/README.md` (documentation map + precedence)
- `docs/00-guardrails.md` and `docs/01-product-scope.md`
- `docs/05-agent-build-workflow.md` and `docs/17-verification-protocol.md`

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
- Background worker continuously backfills configured symbols (`KRAKEN_SYMBOLS`).
- WebSocket worker subscribes to Kraken Futures trade feed and persists live trades.

## Integrity History Endpoint

```bash
GET /v1/integrity/history?instrument=PI_XBTUSD&timeframe=1m&limit=100
```

Returns recent integrity audit rows from `data_quality_intervals`.

## Execution Decision Endpoint

```bash
GET /v1/execution/decision?instrument=PI_XBTUSD&timeframe=1m
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

Manual-first behavior:
- `ENTRY` and `EXIT` require `operator_confirmed=true` plus `operator_id`.
- `EMERGENCY_STOP_CLOSE` is the only action allowed without operator confirmation.

## Account Reconcile Run Endpoint

```bash
POST /v1/account/reconcile/run
```

Runs a reconciliation pass for all accounts with recent snapshots and persists results.

## Strategy Pairs Cues Endpoint

```bash
GET /v1/strategy/pairs/cues?timeframe=1m&limit=20
```

Returns adaptive pairs cue candidates with champion/challenger variant diagnostics for manual action.

## Strategy Reoptimize Endpoint

```bash
POST /v1/strategy/pairs/reoptimize
```

Runs rolling recent-performance evaluation and persists selected signal variants by pair/timeframe.

## Bootstrap Historical Backfill

```bash
cargo run -p data-service --bin bootstrap_backfill
```

This command:
- Pulls real Kraken candles in chunked windows from `BOOTSTRAP_START_TS`.
- Upserts candles to local Timescale.
- Writes integrity audit rows into `data_quality_intervals` for each chunk.

## Kraken History Depth Probe (Live Data)

Run:

```bash
python3 tools/scripts/kraken_history_depth_probe.py \
  --symbol PI_XBTUSD \
  --timeframes 1m 15m 1h \
  --output-json specs/examples/kraken_history_depth_probe_PI_XBTUSD.json
```

The generated report captures earliest returned candles, page continuity checks, and pagination flags for each timeframe.

## Monorepo Layout
- `services/` Rust services (`kraken-adapter`, `data-service`, `strategy-service`, `execution-service`, `account-service`)
- `crates/` shared Rust types and contracts
- `research/` Python strategy research scaffolding
- `apps/` UI applications
- `infra/` local infra and SQL bootstrap
- `specs/` schema contracts and examples

## Versioning
See `docs/02-versioning-and-releases.md` and `CHANGELOG.md`.
