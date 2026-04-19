# Trade-Now Opportunity Filtering Proposal

## Status

- Proposal only.
- No code or runtime behavior is changed by this document.
- Intended review target: experimental branch `codex/slice-a-live-signal-config`.
- Code and line references in this document were verified against experimental commit `81864faef8433fb1cd913f6f4609c3a489658f71`.

## Primary Question

The product should answer two operator questions clearly:

1. What can I trade now?
2. Can I trade good opportunities often?

The current system answers those questions only partially. It has strong building blocks for live cue generation, research, paper-trade review, and candidate promotion, but it does not yet bind the `168h` signal-learning output into a single operator-facing decision surface.

This proposal explains:

- what the codebase currently does
- what the `168h` trial actually did
- what the `168h` trial proved and did not prove
- why the current UI can still show weak pair replays after a successful trial
- how to convert the existing learning and runtime infrastructure into a useful `Trade Now` workflow

## Context & Sources Consulted

### Governing Docs

- `AGENTS.md`
- `docs/01-product-scope.md`
- `docs/10-architecture.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `docs/16-ui-styling-guide.md`
- `docs/19-manual-trading-operator-ui-session.md`
- `docs/playbooks/signal-learning-runbook.md`

### Key Contracts And Examples

- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json`
- `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`
- `specs/contracts/strategy_pairs_opportunity_history_stats_response.schema.json`
- `specs/contracts/signal_learning_cycle_report.schema.json`
- `specs/examples/strategy_pairs_cues_response.example.json`
- `specs/examples/strategy_pairs_candidate_inbox_response.example.json`
- `specs/examples/signal_learning_cycle_report.example.json`

### Key Runtime Code

- `services/strategy-service/src/main.rs`
- `services/strategy-service/src/lib.rs`
- `apps/web/src/App.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types.ts`

### Trial Artifact

- `artifacts/signal_learning/runs/2026-04-17T02-06-50Z-signal-learning-cycle.json`

## Executive Summary

The `168h` experimental work was useful, but the value is currently trapped in a recommendation artifact instead of driving the operator workflow.

The most important finding is this:

- the `168h` trial did **not** conclude that all visible pairs are good to trade
- it concluded that only a narrower subset of pair/timeframe combinations should be treated as strong, trade-eligible candidates
- the current operator UI still behaves primarily as a flat scanner of all live cues

That mismatch is why the experimental work can be genuinely better while the operator can still click into a weak pair and see a poor short-window equity curve.

The proposal is to:

1. add a server-side `Trade Now` read model that intersects:
   - live cue gates
   - fail-closed execution safety
   - the latest fresh learning-approved universe
2. split the UI into:
   - `Trade Now`
   - `Watchlist`
   - `Excluded`
   - `Research Bench`
3. add cadence metrics so the system can answer:
   - how often approved opportunities appear
   - how often they remain actionable long enough to trade

## What The Codebase Does Today

### Product Scope

The intended MVP scope is already clear in `docs/01-product-scope.md:7-17`:

- Kraken Futures market data ingestion
- local historical and near-real-time market repository
- data integrity and gap visibility
- pairs strategy research and paper/live cueing
- adaptive strategy cue ranking
- manual-first execution with operator-confirmed entry/exit
- account reconciliation and browser UI

This matters because the current system is not a black-box autonomous trader. It is a fail-closed, manual-first operator platform with decision-support layers.

### Service Boundaries

The high-level module split is defined in `docs/10-architecture.md:7-37`:

- `data-service`: historical and near-real-time data access
- `strategy-service`: adaptive signal ranking, research, and manual action prompts
- `execution-service`: signal-to-order translation with deterministic lifecycle
- `account-service`: balances, positions, reconciliation
- `apps/web`: operator UI

This architecture is good for the requested goal because the missing `Trade Now` logic belongs in `strategy-service` and `apps/web`, not inside `execution-service`.

### Strategy-Service API Surface

The relevant routes are defined in `services/strategy-service/src/main.rs:3902-3934`:

- `GET /v1/strategy/pairs/cues`
- `GET /v1/strategy/pairs/live-z`
- `GET /v1/strategy/pairs/expectancy`
- `GET /v1/strategy/pairs/candidate-inbox`
- `POST /v1/strategy/pairs/candidate-action`
- `GET /v1/strategy/pairs/paper-trades`
- `GET /v1/strategy/pairs/opportunity-history`
- `GET /v1/strategy/pairs/opportunity-history/stats`

The frontend consumes those routes in `apps/web/src/lib/api.ts:55-236`.

That means the system already has:

- live cue generation
- per-pair replay and backtest views
- expectancy analysis
- paper-trade review over `168h`
- candidate promotion governance
- opportunity history and frequency statistics

The gap is not lack of raw data. The gap is lack of a unified operator decision layer.

### Live Cue Generation

The live cue structure is defined in `specs/contracts/strategy_pairs_cues_response.schema.json:17-348` and typed in `apps/web/src/types.ts:54-130`.

Important fields already exist:

- `cue.actionable`
- `cue.setup_gate`
- `cue.cost_gate`
- `cue.trade_gate`
- `cue.portfolio_hint`
- `cue.selected_signal_config`
- `candidate_set`
- `portfolio_plan`

This is already close to a usable operator answer. The problem is that the current UI mostly renders it as a flat list rather than a filtered decision result.

### Current Operator UI

The current Opportunities surface is in `apps/web/src/App.tsx:3297-3335`.

It currently shows only:

- pair
- live z-score
- edge
- a derived status

The status derivation is in `apps/web/src/App.tsx:793-809`:

- `LIVE` if there is an open trade
- `DATA` if data is degraded
- `READY` if `trade_gate.pass` or `cue.actionable`
- `WAIT` otherwise

This is useful, but it is still scanner behavior.

It does **not** answer:

- whether the pair is inside the learning-approved universe
- whether the currently displayed champion was promoted from research or is still a legacy fallback
- whether the pair should be watched or ignored
- how often similar approved setups appear

### Current Research And Candidate Governance

The research bench is in `apps/web/src/App.tsx:3864-4195`.

It includes:

- expectancy
- replay trades
- research sweep
- candidate inbox

The candidate inbox is already strong infrastructure:

- contract: `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json:110-185`
- example: `specs/examples/strategy_pairs_candidate_inbox_response.example.json:1-70`
- promotion behavior: `services/strategy-service/src/main.rs:7077-7145`

This means the system already knows how to:

- evaluate challenger configs
- compare them to the champion
- require operator review before promotion

Again, the missing layer is not governance. It is runtime/operator filtering.

## What The 168h Trial Did

### Trial Method

The signal-learning runbook is explicit in `docs/playbooks/signal-learning-runbook.md:5-20`.

The overnight loop:

1. sampled live strategy outputs by pair/timeframe
2. accumulated rolling evidence of expectancy and paper-trade quality
3. wrote a **recommendation-only** artifact

The runbook also states:

- it does **not** auto-apply strategy changes
- it performs **no writes to runtime selected-signal config or deploy settings**

This is the single most important point for reviewers.

The `168h` trial was a learning and recommendation layer, not a direct runtime mutation.

### Trial Artifact

The concrete artifact used in this analysis is:

- `artifacts/signal_learning/runs/2026-04-17T02-06-50Z-signal-learning-cycle.json`

The contract for that artifact is `specs/contracts/signal_learning_cycle_report.schema.json:46-194`.

The relevant fields are:

- summary counts
- `selection.top_1`
- `selection.top_k`
- per-timeframe `pairs[]`
- `recommendation`
- `trade_eligible`
- `selection_selected`
- `combined_avg_net_bps`
- `combined_robust_net_bps`
- `reason_codes`
- `arbitration_reason_codes`

### Trial Summary Results

From the `2026-04-17T02-06-50Z` artifact:

- `pairs_evaluated = 48`
- `promote_recommendations = 17`
- `hold_recommendations = 31`
- `trade_eligible_timeframes = 10`
- `selection_selected_count = 3`
- `mutated_pairs = 3`

The selected top-3 were:

1. `PF_SOLUSD__PF_AVAXUSD 15m`
   - `combined_robust_net_bps = 20.652191`
   - `combined_trades = 424`
   - `selection_utility = 0.973799`
2. `PF_XBTUSD__PF_AVAXUSD 15m`
   - `combined_robust_net_bps = 17.959368`
   - `combined_trades = 397`
   - `selection_utility = 0.939192`
3. `PF_DOGEUSD__PF_PEPEUSD 15m`
   - `combined_robust_net_bps = 20.036`
   - `combined_trades = 406`
   - `selection_utility = 0.775046`

The headline conclusion is that the trial concentrated confidence into a smaller, stronger set of pair/timeframe combinations, with a strong bias toward `15m`.

### What The Trial Said About The Pairs That Caused Confusion Later

#### `PF_XBTUSD__PF_ETHUSD`

From the same artifact:

- `1m`
  - `recommendation = HOLD`
  - `trade_eligible = false`
  - `selection_selected = false`
  - `combined_avg_net_bps = 0.24859`
  - `combined_robust_net_bps = 2.061304`
  - `reason_codes = ["MIXED_SIGNAL", "NO_MUTATION_FOR_HOLD"]`
  - `arbitration_reason_codes = ["PAIR_CROSS_TF_CONSENSUS_NOT_MET"]`
- `15m`
  - `recommendation = HOLD`
  - `trade_eligible = false`
  - `selection_selected = false`
  - `combined_avg_net_bps = -0.385555`
  - `combined_robust_net_bps = 8.309794`
  - same cross-timeframe-consensus failure
- `1h`
  - `recommendation = PROMOTE`
  - `trade_eligible = false`
  - `selection_selected = false`
  - `combined_avg_net_bps = 5.504416`
  - `combined_robust_net_bps = 20.705099`
  - but still not selected because consensus and sample rules were not yet satisfied

This means the trial did **not** endorse `XBTUSD/ETHUSD 1m` as a strong operator-facing trading opportunity.

#### `PF_ETHUSD__PF_XRPUSD`

From the same artifact:

- `1m`
  - `recommendation = HOLD`
  - `trade_eligible = false`
  - `selection_selected = false`
  - `combined_avg_net_bps = -1.068961`
  - `combined_robust_net_bps = 2.517642`
- `15m`
  - `recommendation = HOLD`
  - `trade_eligible = false`
  - `selection_selected = false`
- `1h`
  - `recommendation = HOLD`
  - `trade_eligible = false`
  - `selection_selected = false`

This pair also was **not** one of the approved winners.

### What The Trial Was Actually Trying To Achieve

The `168h` trial was trying to answer:

- which pair/timeframe combinations deserve promotion
- which ones should be held back
- which parameter mutations are justified by recent evidence
- which opportunities remain robust after accounting for net-performance quality and stability

It was **not** trying to guarantee that:

- every visible pair in the scanner will show a strong replay
- every `1m` pair remains attractive
- the runtime UI automatically narrows itself to only the approved universe

## Follow-Up Analysis

### Why The Current UI Can Still Show Weak Replays

The current equity chart is a short-window replay from live candles and current strategy bands. The relevant code path is:

- frontend fetch: `apps/web/src/lib/api.ts:68-85`
- backend replay: `services/strategy-service/src/lib.rs:1206-1234`
- analytics display: `apps/web/src/App.tsx:3792-3821`

That chart is useful, but it is not the same thing as the `168h` learning score.

So a pair can show:

- a weak short replay now
- while still being part of a codebase that is better overall because it learned to prefer other pairs/timeframes

### Runtime Selection Still Has A Legacy Escape Hatch

`services/strategy-service/src/main.rs:516-547` resolves selected signal config.

If stored `config_json` is missing or invalid, the service falls back to:

- `default_selected_signal_config(..., "LEGACY_ROW_FALLBACK", ...)`

This is operationally useful as a fail-safe, but it weakens the alignment between:

- the recommendation artifact
- the promoted champion configuration
- the operator’s visible decision surface

If the system is allowed to look tradable while still depending on legacy fallback defaults, the reviewer should treat that as a real gap.

### The UI Still Prioritizes Scanner Behavior Over Decision Behavior

The current Opportunities table in `apps/web/src/App.tsx:3297-3335` shows all cue rows for a timeframe and lets the operator inspect each one as if they are all comparably meaningful.

That behavior discards the main benefit of the learning work:

- narrowing the universe
- preferring stronger pair/timeframe combinations
- de-emphasizing noisy or mixed-signal setups

### The Candidate Inbox Exists But Is Buried

The candidate inbox in `apps/web/src/App.tsx:4116-4191` is an advanced research/governance surface, not the main operator workflow.

That is correct for promotion governance.

However, the product currently has no equally strong top-level surface for:

- `tradable now`
- `watch but not ready`
- `excluded with reason`
- `research bench`

### The Codebase Already Has The Building Blocks For Opportunity Cadence

The repo already stores opportunity history and exposes summary stats:

- contract: `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`
- stats contract: `specs/contracts/strategy_pairs_opportunity_history_stats_response.schema.json`
- route registration: `services/strategy-service/src/main.rs:3926-3934`

That means the system is already capable of supporting a reviewer-quality answer to:

- how often tradeable setups appear
- how frequently those setups pass cost gates
- which timeframes produce repeatable opportunities

## Proposed Product Direction

## Goal

Turn the current strategy platform into a manual-first decision system that answers:

- `What can I trade now?`
- `Can I trade good opportunities often?`

without weakening fail-closed execution behavior.

## Proposal Summary

### 1. Add A Server-Side `Trade Now` Read Model

Do not make the frontend infer this from raw cue rows.

Add a dedicated endpoint, for example:

- **PROPOSAL:** `GET /v1/strategy/pairs/trade-now`

This endpoint should return only opportunities that satisfy all required operator-facing conditions.

### 2. Define A Learning-Approved Universe

Use the latest learning artifact as a read-only overlay.

Do **not** treat every positive learning signal as equivalent.

Recommended confidence split:

- `Trade Now` universe:
  - `selection_selected = true` in the latest **fresh** learning cycle, with the currently active runtime champion/config still in force
  - or a currently active champion/config that was explicitly operator-promoted and has not been superseded
- `Watchlist` universe:
  - `trade_eligible = true` but `selection_selected = false`
  - learning-positive rows waiting on live trigger conditions
  - learning-positive rows downgraded because the overlay is stale
- `Excluded` universe:
  - `HOLD`
  - `trade_eligible = false`
  - vetoed rows
  - rows blocked by provenance policy such as legacy fallback

This is intentionally stricter than a simple OR-union. In the cited `2026-04-17T02-06-50Z` artifact, `trade_eligible_timeframes = 10` while `selection_selected_count = 3`. A loose union would re-expand the decision surface and undo the main value of the learning work.

It should exclude combinations that are clearly outside the learned universe, including `HOLD` / `trade_eligible = false` cases such as `PF_XBTUSD__PF_ETHUSD 1m` in the `2026-04-17T02-06-50Z` artifact.

For this proposal, "currently active runtime champion/config still in force" means:

- the pair/timeframe has a persisted selected-signal row
- `resolve_selected_signal_config()` does not fall back to `LEGACY_ROW_FALLBACK`
- the current live cue is using that persisted champion variant/config
- no later challenger has been promoted over that persisted champion

Important constraint: the learning artifact is pair/timeframe-level and does not carry a full serialized selected-signal config. So B1 should key on pair/timeframe membership plus current persisted non-legacy champion provenance, not on exact config equality with the artifact.

### 3. Define A Freshness TTL For The Learning Overlay

Use an explicit max age for the latest completed learning artifact:

- **PROPOSAL:** `24h` hard TTL for `Trade Now` eligibility

Behavior:

- if the latest learning artifact is newer than `24h`, it may drive `Trade Now`
- if it is older than `24h`, rows that depend on learning approval are downgraded from `Trade Now` to `Watchlist`
- stale learning artifacts must never silently continue to authorize the `Trade Now` surface
- rows with `approval_source = OPERATOR_PROMOTED_ACTIVE_CHAMPION` bypass TTL downgrade and set `requires_fresh_overlay = false`
- rows with `approval_source = LEARNING_SELECTION` set `requires_fresh_overlay = true`
- when `learning_overlay_fresh = false`, `tradable_now[]` must contain only `OPERATOR_PROMOTED_ACTIVE_CHAMPION` rows

This should be represented explicitly in response fields and rationale codes, not inferred in the UI.

### 4. Define Precedence Between Learning And Candidate Inbox Governance

Learning output must not bypass operator promotion governance.

Precedence rule:

- the learning artifact may decide **which pair/timeframe combinations deserve top-level attention**
- the candidate inbox remains authoritative for promoting a new challenger configuration over the active champion
- a pending challenger from the candidate inbox must never enter `Trade Now` as if it were already live-approved solely because learning says `PROMOTE`

Practical meaning:

- `selection_selected = true` may qualify the current active champion row for `Trade Now`
- it does **not** auto-promote a challenger variant/config that is still awaiting operator action
- an explicitly operator-promoted active champion remains eligible for `Trade Now` even if the latest learning artifact says `HOLD`, until it is superseded by later operator governance or an explicit policy that demotes it

### 5. Intersect The Approved Universe With Live Safety And Trade Gates

For a row to appear in `Trade Now`, it should satisfy:

- inside the `Trade Now` universe
- `cue.setup_gate.pass = true`
- `cue.cost_gate.pass = true`
- `cue.trade_gate.pass = true`
- no open live position conflict
- account/integrity/reconcile safe to proceed in the current execution mode
- selected config source is not legacy fallback-only

This keeps the decision layer aligned with `docs/12-risk-and-execution-policy.md:30-58`.

### 6. Split The UI Into Four Buckets

#### A. `Trade Now`

The only surface intended to answer immediate entry decisions.

Each row should show:

- pair and timeframe
- direction hint
- selected variant
- net edge bps
- expected hold bars
- confidence band
- gating summary
- portfolio hint target weight
- explicit blocked reason if it falls out of readiness

#### B. `Watchlist`

Pairs that are learning-positive but not currently tradable because they are waiting on:

- z-entry trigger
- cost gate
- trade gate
- open position conflict
- data freshness

This surface answers:

- what should I watch next?

#### C. `Excluded`

Rows that are intentionally not part of the operator decision set because they are:

- outside the fresh selected universe
- learning `HOLD`
- `trade_eligible = false`
- vetoed
- provenance-blocked, for example because legacy fallback is active

This surface answers:

- why is this not being offered as a trade?

#### D. `Research Bench`

Keep the current replay/expectancy/sweep tooling here.

This is where the operator can inspect:

- non-approved pairs
- challenger variants
- manual what-if analysis

This is separate from `Excluded`. `Excluded` is an operator explanation surface. `Research Bench` is an analysis workspace.

#### E. Timeframe-Empty Behavior

Under the current `2026-04-17T02-06-50Z` learning artifact, the strict selected-universe gate produces:

- `15m`: non-empty selected universe
- `1m`: empty selected universe
- `1h`: empty selected universe

This is a product decision, not an implementation accident.

For this proposal, empty `Trade Now` on a timeframe is acceptable UX **if and only if** the frontend renders an explicit timeframe-level empty-state explanation rather than synthesizing a fake row inside `Excluded`.

Example operator-facing copy:

- `No learning-selected opportunities are currently approved for 1m in the latest fresh overlay. Use Watchlist or Research Bench for lower-confidence scanning.`

So B2 should keep the endpoint row-oriented, while C should render a visible empty-state banner when `timeframe_filter` is set and all three row buckets are empty because the selected universe itself is empty.

### 7. Add Opportunity Cadence Reporting

The second operator question is not answered by a single equity curve.

Add a cadence view based on opportunity-history and learning-approved rows:

- ready events per 24h / 168h
- median ready duration
- per-timeframe approved-ready frequency
- top recurring approved opportunities
- percentage of approved opportunities blocked by cost gate, setup gate, or safety gate

This directly answers:

- can I trade good opportunities often?

## Detailed Design

### A. Backend: `Trade Now` Read Model

#### Inputs

- current cue snapshot from `pairs/cues`
- latest learning artifact
- promoted champion state
- open trade state
- account/integrity/reconcile state where applicable

#### Output

**PROPOSAL:** new response contract with rows grouped by:

- `tradable_now`
- `watchlist`
- `excluded`

Each row should include:

- live cue fields already present in `strategy_pairs_cues_response`
- learning overlay fields:
  - `learning_recommendation`
  - `learning_trade_eligible`
  - `learning_selection_selected`
  - `learning_reason_codes`
  - `learning_cycle_generated_at`
- config provenance fields:
  - `selected_config_source`
  - `legacy_fallback_active`
- operator decision fields:
  - `requires_fresh_overlay`
  - `decision_bucket`
  - `decision_reason_code`
  - `blocked_reason_code`
  - `watch_reason_code`
  - `rationale_codes`

Top-level response should also include:

- `learning_overlay_generated_at`
- `learning_overlay_age_seconds`
- `learning_overlay_fresh`
- `learning_overlay_ttl_seconds`

Reason-code model:

- use one headline `decision_reason_code` per row
- use `blocked_reason_code` and `watch_reason_code` only when their bucket needs a single direct explanation
- use `rationale_codes[]` for supporting atomic tags
- these codes should be schema-enumerated, not free-form UI strings
- `WATCHLIST` rows must force `blocked_reason_code = null`
- `EXCLUDED` rows must force `watch_reason_code = null`

#### Why A New Endpoint Is Better Than Mutating `pairs/cues`

- `pairs/cues` is already a generic scanner/research contract
- it is consumed in multiple UI paths
- overloading it with reviewer/operator semantics will make it harder to reason about
- a new contract keeps backward compatibility cleaner

### B. Backend: Learning Overlay Loader

Use the latest completed signal-learning artifact as read-only input.

This should not auto-promote runtime configs.

It should only:

- narrow the decision surface
- add provenance
- add reviewer/operator explainability

This preserves the runbook’s recommendation-only guarantee while still using the results operationally.

### C. Backend: Suppress Legacy-Fallback Rows From `Trade Now`

Rows produced from `LEGACY_ROW_FALLBACK` should not be shown as fully tradable unless there is explicit policy approval for that.

Reason:

- they are still useful for scanner visibility and research
- they are not ideal as first-class operator recommendations

This also requires an explicit test for:

- `selection_selected = true`
- `legacy_fallback_active = true`
- result is **not** `tradable_now`

### D. Frontend: Replace The Flat Opportunities Table

Current implementation:

- `apps/web/src/App.tsx:3297-3335`

Target behavior:

- a top-level `Trade Now` table
- a secondary `Watchlist`
- an `Excluded` explanation view
- a separate `Research Bench`

The existing charting and research panels can remain, but their role should be reframed as analysis of the selected item rather than the primary decision surface.

### E. Frontend: Show Provenance On Every Operator-Relevant Row

Each row should visibly answer:

- why is this here?
- why is it tradable or not?

Minimal provenance fields:

- runtime selected variant
- learning recommendation
- approval source
- cost gate summary
- safety gate summary

## Cadence Baseline Before New Metrics

The reviewer should not approve cadence UX without a baseline source.

The baseline source already exists:

- `GET /v1/strategy/pairs/opportunity-history/stats`
- `GET /v1/strategy/pairs/opportunity-history`

On the hosted experimental runtime checked on April 18, 2026, the existing stats endpoint reported roughly `54` days of stored opportunity history per timeframe:

- `1m`: `22056` rows over `54.01` days
- `15m`: `21556` rows over `54.00` days
- `1h`: `20754` rows over `54.03` days

That is enough data to compute a meaningful pre-implementation cadence baseline in Slice A before adding new metrics or UI.

The Slice A baseline output should not stop at row-count coverage. Reviewers should see, per timeframe:

- approved-ready events per day over the covered history window
- approved-watchlist events per day over the covered history window
- the denominator window used for those rates

Reproducible baseline query for the latest learning-selected universe:

```sql
WITH selected_universe(pair_id, timeframe) AS (
  VALUES
    ('PF_SOLUSD__PF_AVAXUSD', '15m'),
    ('PF_XBTUSD__PF_AVAXUSD', '15m'),
    ('PF_DOGEUSD__PF_PEPEUSD', '15m')
),
filtered AS (
  SELECT h.*
  FROM strategy_opportunity_history h
  JOIN selected_universe u
    ON h.pair_id = u.pair_id
   AND h.timeframe = u.timeframe
),
rollup AS (
  SELECT
    timeframe,
    COUNT(*) AS total_events,
    COUNT(*) FILTER (WHERE actionable AND cost_gate_pass) AS approved_ready_events,
    COUNT(*) FILTER (WHERE NOT (actionable AND cost_gate_pass)) AS approved_watchlist_events,
    MIN(evaluated_at) AS first_evaluated_at,
    MAX(evaluated_at) AS last_evaluated_at
  FROM filtered
  GROUP BY timeframe
)
SELECT
  timeframe,
  total_events,
  approved_ready_events,
  approved_watchlist_events,
  EXTRACT(EPOCH FROM (last_evaluated_at - first_evaluated_at)) / 86400.0 AS days_covered,
  approved_ready_events
    / NULLIF(EXTRACT(EPOCH FROM (last_evaluated_at - first_evaluated_at)) / 86400.0, 0)
      AS approved_ready_events_per_day,
  approved_watchlist_events
    / NULLIF(EXTRACT(EPOCH FROM (last_evaluated_at - first_evaluated_at)) / 86400.0, 0)
      AS approved_watchlist_events_per_day
FROM rollup;
```

Using the latest fresh learning-selected universe from `2026-04-17T02-06-50Z` (`PF_SOLUSD__PF_AVAXUSD 15m`, `PF_XBTUSD__PF_AVAXUSD 15m`, `PF_DOGEUSD__PF_PEPEUSD 15m`) and the hosted `strategy_opportunity_history` table on April 18, 2026:

- `15m` selected-universe baseline:
  - `4047` total selected-universe events over `53.9981` days
  - `461` approved-ready events
  - `3586` approved-watchlist events
  - `8.5373` approved-ready events/day
  - `66.4097` approved-watchlist events/day
- `1m` selected-universe baseline:
  - `0` selected rows in the latest learning-selected universe
  - `0` approved-ready events/day under current Slice A semantics
- `1h` selected-universe baseline:
  - `0` selected rows in the latest learning-selected universe
  - `0` approved-ready events/day under current Slice A semantics

The `1m` and `1h` zeroes are not missing-data artifacts. They follow directly from the current selected-universe decision policy and the latest fresh artifact, which selected only `15m` rows.

## Implementation Plan

### Slice A: Contracts And Reviewer Scaffolding

1. Add new contract:
   - **PROPOSAL:** `specs/contracts/strategy_pairs_trade_now_response.schema.json`
2. Add example:
   - **PROPOSAL:** `specs/examples/strategy_pairs_trade_now_response.example.json`
3. Lock these contract-level semantics before implementation:
   - `Trade Now` uses `selection_selected` or explicitly operator-promoted active champion rows
   - bare `trade_eligible` goes to `Watchlist`, not `Trade Now`
   - learning TTL is `24h`
   - candidate inbox promotion remains authoritative for challenger activation
4. Compute and document the current cadence baseline from opportunity-history tables, including per-timeframe approved-ready events/day over the covered window.
5. Add this proposal document to the docs index.

Acceptance target:

- no behavior change yet
- contract and example are reviewable
- reviewers can judge cadence output against explicit per-timeframe baseline numbers, not just a baseline source
- reviewers can re-derive the baseline from a pinned query snippet

### Slice B1: Strategy-Service Learning Overlay Loader

1. Add loader for latest signal-learning artifact.
2. Normalize its per-pair/per-timeframe decisions into an in-memory overlay.
3. Apply TTL and provenance policies in memory.
4. Unit-test:
   - selected vs trade-eligible splitting
   - stale artifact downgrade
   - stale overlay plus operator-promoted active champion -> remains eligible for `tradable_now`
   - candidate governance precedence
   - pending challenger plus learning `PROMOTE` -> remains `excluded` with `PENDING_CHALLENGER_REQUIRES_PROMOTION`
   - `selection_selected = true` plus `legacy_fallback_active = true`

Acceptance target:

- no endpoint yet
- overlay policy is deterministic and testable in isolation

### Slice B2: Strategy-Service `Trade Now` Endpoint

1. Build `trade-now` rows from:
   - cue snapshot
   - learning overlay
   - selected config provenance
   - open-trade state
2. Return grouped response:
   - `tradable_now`
   - `watchlist`
   - `excluded`

Acceptance target:

- backend can explain why `XBTUSD/ETHUSD 1m` is not surfaced as tradable
- backend can surface `15m` winners from the approved universe when they are actually live-actionable

### Slice C: Web Operator Surface

1. Replace the flat Opportunities scanner as the default trading view.
2. Add `Excluded` as a separate explanation view.
3. Keep the research panels, but relabel them `Research Bench`.
4. Add watchlist states and reasons.
5. Preserve pair analytics, but tie them to the selected decision bucket row.

Acceptance target:

- operator lands on a prioritized decision surface, not a flat scanner
- a reviewer can inspect the app and immediately see which rows are:
  - tradable
  - watch-only
  - excluded

### Slice D: Cadence And Frequency Reporting

1. Add approved-universe cadence stats on top of the Slice A baseline.
2. Show:
   - approved-ready events per timeframe
   - median ready duration
   - block rates by reason
   - top recurring approved setups
3. Use opportunity history stats plus the learning overlay as the base.

Acceptance target:

- the system can answer whether good opportunities appear often enough to justify the operating model

### Slice E: Hardening And Rollout

1. Add observability and alerting for decision-bucket composition.
2. Validate that no live execution behavior is loosened.
3. Review `legacy_fallback_active` handling before surfacing any row as tradable.

## Interfaces / Contracts

### Existing Contracts Reused

- `specs/contracts/strategy_pairs_cues_response.schema.json`
- `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json`
- `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`
- `specs/contracts/strategy_pairs_opportunity_history_stats_response.schema.json`
- `specs/contracts/signal_learning_cycle_report.schema.json`

### Proposed New Contract

- **PROPOSAL:** `specs/contracts/strategy_pairs_trade_now_response.schema.json`

This is the cleanest contract boundary for implementation.

## Risk & Failure Modes

### 1. False Confidence From Learning Overlay

Risk:

- treating recommendation artifacts as if they were already runtime-approved champions

Mitigation:

- keep promotion and learning approval separate
- expose provenance fields
- do not hide candidate-inbox governance

### 2. Safety Drift

Risk:

- `Trade Now` could accidentally bypass real execution safety gates

Mitigation:

- no direct coupling to order submission
- keep execution-service gating authoritative
- make `Trade Now` purely advisory unless all safety gates pass

### 3. Stale Or Missing Learning Artifacts

Risk:

- decision surface becomes confusing if the latest learning file is stale or absent

Mitigation:

- fail closed to `Watchlist` / `Excluded`
- never claim `tradable_now` from missing learning evidence
- surface artifact timestamp in response

### 4. Over-Filtration

Risk:

- too few opportunities shown

Mitigation:

- keep `Watchlist`, `Excluded`, and `Research Bench`
- cadence reporting will reveal whether the approved universe is too narrow

## Test Plan

Per `docs/14-testing-standards.md:14-45`, implementation should include:

### Schema Validation

- validate the new `trade-now` response schema and example

### Integration Tests

- learning-approved pair + live trade gate pass -> `tradable_now`
- learning `HOLD` pair + live-ready cue -> `excluded` or `watchlist`, not `tradable_now`
- missing learning artifact -> safe degraded behavior
- legacy fallback config -> not surfaced as fully tradable
- `selection_selected = true` plus `legacy_fallback_active = true` -> not `tradable_now`
- pending challenger in candidate inbox plus learning `PROMOTE` -> challenger does not bypass promotion governance
- operator-promoted active champion plus learning `HOLD` for the same pair/timeframe -> remains eligible for `tradable_now` if live gates still pass

### Replay / Regression Tests

- regression fixture using the `2026-04-17T02-06-50Z` learning artifact
- assertion that `PF_XBTUSD__PF_ETHUSD 1m` is not promoted to `tradable_now`
- assertion that selected `15m` winners can surface if live conditions align

### UI Tests

- `Trade Now` renders only approved and safe rows
- `Watchlist` renders waiting reasons
- `Excluded` renders explicit why-not-tradable reasons
- `Research Bench` still allows manual inspection without confusing it for a trading recommendation

## Observability

Per `docs/15-observability-and-alerting.md:29-70`, add:

- `trade_now_rows_total`
- `trade_watchlist_rows_total`
- `trade_excluded_rows_total`
- `trade_now_blocked_reason_total{reason=...}`
- `learning_overlay_artifact_age_seconds`
- `learning_overlay_missing_total`
- `legacy_fallback_tradable_suppressed_total`
- `learning_challenger_bypass_suppressed_total{pair_id,timeframe}`
- `approved_ready_events_total{timeframe=...}`
- `approved_ready_duration_seconds`

Useful logs:

- decision bucket assignment with `pair_id`, `timeframe`, `request_id`
- learning provenance fields
- blocked reason and gating reason codes

## Versioning

- Adding a new endpoint is backward compatible.
- Mutating `pairs/cues` in-place is riskier and should be avoided unless there is a strong reason.
- This proposal does not require a public behavior version bump yet, but implementation should update:
  - `CHANGELOG.md`
  - contract docs
  - example payloads

## Reviewer Notes

The key review question is not:

- why does a specific short-window replay still look weak?

The key review question is:

- should the product continue to expose all cue rows as if they were equally actionable, or should it capitalize on the `168h` learning work by narrowing and explaining the operator decision set?

This proposal recommends the second path.

## Code Reference Index

### System Intent

- `docs/01-product-scope.md:7-17`
- `docs/10-architecture.md:7-37`
- `docs/12-risk-and-execution-policy.md:30-58`
- `docs/19-manual-trading-operator-ui-session.md:6-45`

### Strategy Routes

- `services/strategy-service/src/main.rs:3902-3934`

### Selected-Signal Fallback

- `services/strategy-service/src/main.rs:516-547`

### Candidate Promotion

- `services/strategy-service/src/main.rs:7077-7145`

### Cue Actionability Logic

- `services/strategy-service/src/lib.rs:1017-1075`

### Backtest / Equity Replay Path

- `services/strategy-service/src/lib.rs:1206-1234`
- `apps/web/src/lib/api.ts:68-85`
- `apps/web/src/App.tsx:3792-3821`

### Opportunities UI

- `apps/web/src/App.tsx:793-809`
- `apps/web/src/App.tsx:3297-3335`

### Candidate Inbox UI

- `apps/web/src/App.tsx:4116-4191`

### Frontend API Bindings

- `apps/web/src/lib/api.ts:55-236`

### Core Contracts

- `specs/contracts/strategy_pairs_cues_response.schema.json:17-348`
- `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json:110-185`
- `specs/contracts/strategy_pairs_opportunity_history_response.schema.json:7-76`
- `specs/contracts/strategy_pairs_opportunity_history_stats_response.schema.json:7-48`
- `specs/contracts/signal_learning_cycle_report.schema.json:46-194`

### Trial Artifact

- `artifacts/signal_learning/runs/2026-04-17T02-06-50Z-signal-learning-cycle.json`
