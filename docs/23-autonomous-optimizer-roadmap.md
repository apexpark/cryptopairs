# Autonomous Optimizer Roadmap (Operator-Approved Promotion)

## Objective

Build an autonomous propose / human promote optimization workflow that:
- grows multi-timeframe history in the local repository,
- evaluates candidates on strict in-sample/out-of-sample splits,
- runs walk-forward validation,
- surfaces only material candidate changes to the operator,
- preserves fail-closed behavior and deterministic auditability.

## Target Data Horizons

- 1m: 120 days retained, optimize on rolling 30-60d train + 14-30d validation
- 15m: 540 days retained, optimize on rolling 180-360d train + 60-90d validation
- 1h: 1095 days retained, optimize on rolling 730d train + 180d validation

## Slice Checklist

### Slice A: Data Horizons + Retention (foundational)

Status: In progress

Files:
- `services/data-service/src/config.rs`
- `services/data-service/src/worker.rs`
- `services/data-service/src/repository.rs`
- `services/data-service/src/main.rs`
- `.env.example`
- `docs/playbooks/backfill-runbook.md`

Env keys:
- `BACKFILL_WINDOW_DAYS_1M` (default `120`)
- `BACKFILL_WINDOW_DAYS_15M` (default `540`)
- `BACKFILL_WINDOW_DAYS_1H` (default `1095`)
- `CANDLES_RETENTION_DAYS_1M` (default `120`)
- `CANDLES_RETENTION_DAYS_15M` (default `540`)
- `CANDLES_RETENTION_DAYS_1H` (default `1095`)
- `CANDLES_PRUNE_INTERVAL_SECONDS` (default `3600`)

Acceptance:
- Backfill worker uses configured windows per timeframe.
- Retention prune runs periodically and logs deleted rows.
- Unit tests cover timeframe-window math and prune cadence.

### Slice B: Explicit IS/OOS Window Contracts

Status: Completed (v1 contract + parser + API metadata)

Contracts:
- `specs/contracts/strategy_pairs_research_sweep_response.schema.json` (add window metadata)
- `specs/contracts/strategy_pairs_expectancy_response.schema.json` (add train/validation window metadata)
- New (proposal): `specs/contracts/strategy_pairs_optimizer_cycle_response.schema.json`

Files:
- `services/strategy-service/src/main.rs` (query parsing + response population)
- `apps/web/src/types.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/App.tsx` (Research Controls)

Env keys (proposal):
- `STRATEGY_OPT_TRAIN_DAYS_1M`, `STRATEGY_OPT_VALIDATE_DAYS_1M`
- `STRATEGY_OPT_TRAIN_DAYS_15M`, `STRATEGY_OPT_VALIDATE_DAYS_15M`
- `STRATEGY_OPT_TRAIN_DAYS_1H`, `STRATEGY_OPT_VALIDATE_DAYS_1H`

Acceptance:
- Every optimization result explicitly declares IS/OOS windows used.
- Selection and score never use same bars.

### Slice C: Walk-Forward Execution Engine

Status: Planned

Files:
- `services/strategy-service/src/main.rs` (sweep execution path)
- new internal module (proposal): `services/strategy-service/src/walk_forward.rs`

Behavior:
- Run k walk-forward folds per pair/timeframe.
- Rank by OOS objective first; include robustness and min-trade gates.

Env keys (proposal):
- `STRATEGY_WF_FOLDS`
- `STRATEGY_WF_MIN_TRADES_PER_FOLD`
- `STRATEGY_WF_ROBUSTNESS_PERTURBATION_PCT`

Acceptance:
- Deterministic fold outputs from fixed fixtures.
- Candidate marked unavailable if fold sufficiency fails.

### Slice D: Candidate Lifecycle + Probation

Status: Planned

DB schema (proposal):
- `strategy_candidate_runs`
- `strategy_candidate_probation`
- `strategy_candidate_actions`

Files:
- `infra/sql/init_timescale.sql` (additive tables/indexes)
- `services/strategy-service/src/main.rs` (state transitions, API wiring)

Lifecycle:
- `CANDIDATE` -> `CHALLENGER` (paper-forward probation) -> `PROMOTION_READY` -> `CHAMPION`
- Promotions remain operator-triggered only.

Acceptance:
- One active challenger per pair/timeframe.
- Full transition audit trail with timestamps and operator_id on actions.

### Slice E: Operator Candidate Inbox

Status: Planned

Contracts (proposal):
- `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json`
- `specs/contracts/strategy_pairs_candidate_action_request.schema.json`
- `specs/contracts/strategy_pairs_candidate_action_response.schema.json`

Endpoints (proposal):
- `GET /v1/strategy/pairs/candidate-inbox`
- `POST /v1/strategy/pairs/candidate-action` (`PROMOTE|HOLD|REJECT`)

Files:
- `services/strategy-service/src/main.rs`
- `apps/web/src/types.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/App.tsx` (Maintenance/Analytics candidate panel)

Acceptance:
- Show top material candidates only (default top 3).
- Show delta vs champion: expectancy, drawdown, confidence, failure modes.
- One-click promote/reject with confirmation + audit note.

### Slice F: Observability + Runbook Hardening

Status: Planned

Docs:
- `docs/15-observability-and-alerting.md`
- `docs/playbooks/strategy-maintenance-automation-runbook.md`
- `docs/playbooks/hosted-deployment-runbook.md`

Metrics (proposal):
- `optimizer_cycle_total{timeframe,status}`
- `optimizer_candidate_generated_total{timeframe}`
- `optimizer_candidate_promotable_total{timeframe}`
- `optimizer_candidate_rejected_total{timeframe,reason}`
- `candidate_probation_pass_total{timeframe}`
- `candidate_probation_fail_total{timeframe,reason}`
- `data_retention_prune_rows_total{timeframe}`

Acceptance:
- Alerts for repeated optimizer failures and persistent no-candidate conditions.
- Incident reconstruction from structured logs + artifacts.

## Safety Rules (Always On)

- Missing or stale data -> `WAIT`/non-actionable.
- Unknown optimizer state -> `HOLD` recommendation.
- No autonomous trade execution changes.
- Promotion requires explicit operator action.

## Rollout Order

1. Slice A
2. Slice B
3. Slice C
4. Slice D
5. Slice E
6. Slice F

Each slice must pass tests and publish artifacts before next slice starts.
