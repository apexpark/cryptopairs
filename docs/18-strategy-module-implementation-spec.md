# Strategy Module Implementation Spec (Paper-Informed)

## Purpose

Translate high-value concepts from `ssrn-3247865.pdf` into a concrete, sequenced implementation plan for the existing manual-first crypto perpetuals system.

This document is implementation-focused and aligned with:
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`

## Source Extraction Summary

From `ssrn-3247865.pdf`, the most directly useful sections were:
- Pairs and mean-reversion framing, and regression residualization (pp. 46-50).
- Statistical arbitrage optimization with dollar-neutral constraints (pp. 56-58).
- Strong emphasis on transaction costs/slippage and fast execution constraints (pp. 78-83, 126-127).
- Crypto-specific ML as forecasting support, with overfitting cautions (pp. 117-122).

## Scope Alignment With Current System

Current repo state already includes:
- Manual-first cue generation and reoptimization in `strategy-service`.
- Fail-closed order gating in `execution-service`.
- Data integrity policies and history endpoints in `data-service`.

This spec extends strategy behavior without changing manual-first execution posture.

Hard constraint:
- No autonomous entry/exit order placement.
- Automated path remains restricted to emergency stop-close only.

## Design Principles

1. Fail closed: if integrity, cost, or model confidence is insufficient, output non-actionable cue.
2. Deterministic first: replayable feature generation and ranking before adding adaptive logic.
3. Cost-aware edge: expected edge must exceed explicit fee + funding + slippage budget.
4. Manual-first UX: surface best opportunities and risk context, operator decides entry/exit.
5. Additive interfaces only: avoid breaking existing contracts.
6. Tradable economics first: strategy signal ranking, replay, expectancy, and live-trade monitoring should share one executable spread basis built from lot-rounded leg quantities and marked prices.
7. Entry signals must be computed from a lagged executable-spread reference window (excluding the current bar), and historical trade progress must use the same frozen trade-normalized oscillator as live open trades once a simulated entry is open; scanner `signal_z` remains diagnostic context after entry.

## Strategy Stack (Target)

1. Candidate generation
- Pair-level spread features by timeframe (1m, 15m, 1h).
- Existing variants retained (cointegration z, robust z, vol-normalized, funding-adjusted).

2. Residualized mean-reversion layer
- Add cluster/residualized spread signal path using regression residuals.
- This follows the paper's cluster-neutral residualization idea, adapted to available instrument universe.

3. Cost and viability gate
- Compute expected edge net of:
  - taker/maker fee assumptions,
  - funding impact estimate (directional, event-aware),
  - slippage model from sampled executable quotes (fail-closed if required samples unavailable).
- If net edge <= 0, cue becomes non-actionable.

4. Portfolio construction layer (decision support)
- Build suggested relative sizing for pairs basket under:
  - dollar-neutrality,
  - covariance/risk suppression,
  - max per-pair exposure constraints.
- Output is advisory for operator, not auto-execution.

5. Adaptive ranking layer
- Keep current shadow ML path as non-binding ranker.
- Add champion/challenger tracking by timeframe and regime.

## Sequenced Delivery Plan

### Slice A: Contracts + examples (additive)

Deliverables:
- Add contract for pair portfolio advice response.
- Add contract for cost-gate diagnostics response.
- Add examples for both.

Acceptance criteria:
- JSON contracts validate.
- Existing contracts unchanged and backward compatible.

### Slice B: Scaffolding + deterministic computations

Deliverables:
- Feature structs for residualized signals and cost model inputs.
- Deterministic portfolio optimization module behind strategy-service internals.
- Config keys for fees, slippage multipliers, and exposure caps.
- Config keys for dynamic funding cadence and sign conventions.

Acceptance criteria:
- Unit tests for feature math and optimizer constraints.
- Replay tests produce identical outputs for fixed input windows.

### Slice C: Service integration behind safe defaults

Deliverables:
- Extend `GET /v1/strategy/pairs/cues` with optional advisory blocks:
  - cost gate diagnostics,
  - suggested portfolio sizing,
  - candidate-set diagnostics.
- Extend `POST /v1/strategy/pairs/reoptimize` with counters for new diagnostics.

Acceptance criteria:
- Default behavior remains current if new toggles disabled.
- Non-actionable output when any required input is missing.

### Slice D: Observability + hardening

Deliverables:
- Structured logs and counters for:
  - cost gate pass/fail,
  - residual signal coverage,
  - advisory generation success/failure,
  - champion/challenger drift.
- Playbook updates for strategy degradation or cost-model mismatch.

Acceptance criteria:
- Incident timeline reconstructible from logs.
- Alertable metrics available for unresolved strategy degradation.

## Proposed API/Contract Additions (PROPOSAL)

1. `strategy_pairs_portfolio_plan_response`
- Fields:
  - `timeframe`, `generated_at`
  - `weights[]`: `pair_id`, `target_weight`, `risk_contribution`, `cap_applied`
  - `constraints`: `dollar_neutral`, `gross_cap`, `per_pair_cap`
  - `status`: `AVAILABLE|UNAVAILABLE`
  - `rationale_codes[]`

2. `strategy_pairs_cost_gate_response`
- Fields:
  - `pair_id`, `timeframe`
  - `expected_edge_bps`, `fee_bps`, `funding_bps`, `slippage_bps`, `net_edge_bps`
  - `funding_model`, `funding_events`, `funding_bps_per_event`
  - `pass`
  - `rationale_codes[]`

3. Optional cue embedding
- Add optional fields to existing cues response:
  - `cost_gate`
  - `portfolio_hint`

## Data and Integrity Requirements

1. Strategy reads must enforce local-first data behavior already defined in data-service.
2. If candles/trades required for cost model are incomplete, cue remains non-actionable.
3. Integrity status must be included in strategy diagnostics and propagated to UI.

## Risk and Failure Behavior

1. Missing model inputs -> advisory unavailable, cue non-actionable.
2. Covariance instability or singularity -> fallback to capped equal-risk heuristic.
3. Cost estimate uncertainty beyond threshold -> block actionability and emit rationale code.
4. Any execution/risk uncertainty -> execution-service remains authoritative fail-closed gate.

## Testing Requirements

1. Unit tests
- Residualized signal construction.
- Cost gate arithmetic.
- Portfolio optimizer constraints (dollar-neutral, caps).

2. Integration tests
- Strategy endpoint responses with additive diagnostics.
- Persistence of advisory/audit rows.

3. Replay/regression tests
- Fixed historical windows for deterministic output.
- Champion/challenger drift bounded under replay.

4. Contract tests
- New schemas + examples parse and validate.

## Observability Requirements

Minimum additions:
- `strategy_cost_gate_pass_total{timeframe}`
- `strategy_cost_gate_fail_total{timeframe,reason}`
- `strategy_portfolio_advice_available_total{timeframe}`
- `strategy_portfolio_advice_unavailable_total{timeframe,reason}`
- `strategy_shadow_ml_disagreement_total{timeframe}`

Log fields:
- `pair_id`, `timeframe`, `regime`, `selected_variant`, `net_edge_bps`, `actionable`, `correlation_id`

## UI Integration Notes (Manual-First)

1. Show three panes by timeframe: 1m, 15m, 1h.
2. For each cue show:
- directional cue,
- confidence,
- cost gate net edge,
- advisory size suggestion,
- rationale codes.
3. Entry/exit remains explicit operator button action.
4. Emergency stop control remains always visible and isolated.

## Implementation Order Recommendation

1. Slice A (contracts/examples)
2. Slice B (deterministic modules + tests)
3. Slice C (endpoint integration with safe defaults)
4. Slice D (observability and playbooks)

No slice should bypass fail-closed behavior.

## Out-of-Scope For This Phase

1. Fully autonomous strategy-to-order execution.
2. End-to-end RL/agentic policy optimization in live trading.
3. Cross-exchange routing and smart order execution.

## Definition of Done (for this plan's first execution cycle)

1. Additive contracts merged and validated.
2. Deterministic replay passing for new strategy diagnostics.
3. Cost gate and advisory sizing visible in cues response and UI.
4. Manual-first operator flow preserved with no automation expansion.
5. Observability metrics/logs documented and emitted.
