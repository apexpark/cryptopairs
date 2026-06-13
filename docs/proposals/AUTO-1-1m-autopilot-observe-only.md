# Proposal: AUTO-1 1m autopilot observe-only

> **Status**: design proposal. No implementation in this PR.
>
> **Author**: codex, 2026-06-13.
>
> **Branch**: `codex/1m-autopilot-observe-design`. Base: `main` at
> `f22c26f04c40b662bed493528357a009027fd8d1`.
>
> **Item addressed**: `AUTO-1` in `docs/AGENT_STATE.md` section "Currently In
> Flight".

---

## 1. Context and sources consulted

This proposal is a design-only slice for observing `1m` automation behavior
before any automated execution work is considered.

Verified repo artifacts:

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/10-architecture.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/13-secrets-and-security.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `docs/24-trade-now-opportunity-proposal.md`
- `services/strategy-service/src/main.rs`
- `services/execution-service/src/main.rs`
- `services/data-service/src/lib.rs`
- `specs/contracts/strategy_pairs_trade_now_response.schema.json`
- `specs/contracts/strategy_trade_now_observability_response.schema.json`
- `specs/contracts/execution_order_intent_request.schema.json`

Relevant verified facts:

- `GET /v1/strategy/pairs/trade-now` is registered in
  `services/strategy-service/src/main.rs`.
- `GET /v1/strategy/observability/trade-now` is registered in
  `services/strategy-service/src/main.rs`.
- `GET /v1/strategy/pairs/opportunity-history`,
  `GET /v1/strategy/pairs/opportunity-history/stats`,
  `GET /v1/strategy/pairs/paper-trades`, and
  `GET /v1/strategy/pairs/portfolio-plan` are registered in
  `services/strategy-service/src/main.rs`.
- `GET /v1/execution/dispatch-mode`, `GET /v1/execution/kill-switch`,
  `POST /v1/execution/order-intent`, and
  `POST /v1/execution/order-intent/dispatch` are registered in
  `services/execution-service/src/main.rs`.
- `docs/12-risk-and-execution-policy.md` requires explicit operator
  confirmation for live `ENTRY` and `EXIT` intents and allows automated
  execution only for emergency stop-close actions.
- `specs/contracts/execution_order_intent_request.schema.json` requires
  `operator_confirmed: true` and `operator_id` for `ENTRY` and `EXIT`.
- `services/data-service/src/lib.rs` now makes `/health` perform a repository
  health check before returning `200`.

## 2. Problem

The current `1m` Trade Now surface has produced attractive ready-window and
paper-trade evidence, but it is still an advisory surface. Before introducing
any automated order path, the system needs a lower-risk proving step that can
answer:

1. What would an autopilot have selected on each `1m` cycle?
2. Which safety, freshness, and quality gates would have blocked or allowed it?
3. Would repeated polling have produced duplicate actions?
4. How would the operator audit those decisions after 24 to 72 hours?

The proposed first step is therefore observe-only. It records deterministic
"would act" decisions and block reasons, but it must not submit order intents,
dispatch orders, modify exchange state, or relax existing execution controls.

## 3. Scope and non-goals

In scope for later implementation slices:

- a disabled-by-default observer for `1m` Trade Now candidates;
- deterministic decision logging for allowed and blocked candidates;
- readiness checks against data, strategy, and execution surfaces;
- pair-level ready-window attribution inputs for quality gates;
- a summary report that compares observed candidates with later paper-trade or
  attribution outcomes;
- tests proving observe-only behavior cannot call execution submission paths.

Out of scope for AUTO-1:

- live `ENTRY` or `EXIT` automation;
- paper-order creation;
- exchange API calls;
- Kraken credential changes;
- portfolio sizing or live risk-model changes;
- bypassing or synthesizing `operator_confirmed`;
- calling `POST /v1/execution/order-intent`;
- calling `POST /v1/execution/order-intent/dispatch`;
- changing existing execution-service gating;
- enabling any runtime feature by default.

## 4. Design options

### Option A - sidecar observer

Run a small observer process or script that polls existing HTTP surfaces and
writes append-only observation records.

Pros:

- lowest blast radius;
- no strategy-service or execution-service runtime coupling;
- easy to run, stop, and inspect on Hetzner;
- can be disabled by default without changing service behavior.

Cons:

- needs its own deployment/runbook wrapper;
- must be careful to keep HTTP timeouts and retries bounded;
- durable storage starts as a separate artifact unless a later slice adds a
  table.

### Option B - strategy-service background worker

Add an internal strategy-service worker that observes Trade Now decisions.

Pros:

- direct access to strategy state;
- simpler future integration with metrics;
- fewer moving deployment parts.

Cons:

- higher blast radius in a service that already owns signal generation;
- harder to prove that observe-only cannot accidentally become order handoff;
- service restart needed for rollout and rollback.

### Option C - UI-only observer

Record the operator-facing view in the web app only.

Pros:

- fast to inspect visually;
- useful for operator review.

Cons:

- not durable enough for headless 24 to 72 hour evidence;
- browser/session availability would affect observations;
- poor fit for deterministic replay and audit.

### Recommendation

Use **Option A: sidecar observer** for the first implementation slice.

The sidecar must be explicitly observe-only. Its execution client should expose
read-only methods for dispatch mode, kill switch, open positions/trades, and
summary status only. It should have no code path, configuration, or test fixture
that posts order intents or dispatches orders.

## 5. Proposed observation loop

**PROPOSAL:** the observer runs once per minute, aligned as closely as practical
to completed `1m` strategy data, with jitter and request timeouts to avoid
loading services during normal operation.

Per tick:

1. Generate a `run_id` and `observed_at`.
2. Check data-service `/health`.
3. Check strategy-service `/health`.
4. Fetch `GET /v1/strategy/pairs/trade-now?timeframe=1m`.
5. Fetch `GET /v1/strategy/observability/trade-now`.
6. Fetch read-only execution safety state:
   - `GET /v1/execution/dispatch-mode`
   - `GET /v1/execution/kill-switch`
   - read-only open-trade or portfolio status if configured and available
7. Fetch or load pair-level ready-window attribution used by the quality gate.
8. Evaluate each `tradable_now` row against the observe-only policy.
9. Append one decision record per candidate and one tick summary record.
10. Emit metrics and structured logs.

If any required source is unavailable, stale, malformed, or internally
inconsistent, the tick fails closed by writing a blocked observation. It must not
infer missing readiness from older successful ticks.

## 6. Observe-only policy gates

**PROPOSAL:** initial gates should be intentionally stricter than the current
operator-facing Trade Now display.

Candidate eligibility:

- `timeframe == "1m"`;
- candidate is in the `tradable_now` bucket;
- `setup_gate_pass`, `cost_gate_pass`, and `trade_gate_pass` are all `true`;
- learning overlay is fresh when the response exposes freshness fields;
- source is in an explicit allowlist such as `LEARNING_SELECTION` or
  `LEARNING_ELIGIBLE_OVERRIDE`;
- `(pair_id, selected_variant)` is in a configured allowlist;
- no read-only safety surface reports an open live trade that conflicts with
  the candidate;
- kill switch is not active;
- dispatch mode is read successfully and does not indicate a blocked state;
- data-service and strategy-service health checks pass;
- ready-window quality gate passes.

Quality gate:

**PROPOSAL:** the first quality gate should use pair-level ready-window
attribution over a recent window, not all historical paper trades for the pair.
The precise query belongs in the implementation slice, but the gate should be
based on:

- recent ready-window sample count;
- recent ready-window profitable rate;
- recent ready-window average net basis points;
- whether the attribution is specific to the same `pair_id`, timeframe, and
  selected variant when available.

Failure modes should be explicit:

- `BLOCKED_STALE_INPUT`
- `BLOCKED_SOURCE_UNAVAILABLE`
- `BLOCKED_MALFORMED_RESPONSE`
- `BLOCKED_KILL_SWITCH`
- `BLOCKED_DISPATCH_MODE`
- `BLOCKED_OPEN_LIVE_TRADE`
- `BLOCKED_NOT_ALLOWLISTED`
- `BLOCKED_LIVE_GATE`
- `BLOCKED_LEARNING_OVERLAY_STALE`
- `BLOCKED_QUALITY_GATE`
- `BLOCKED_DUPLICATE_OBSERVATION`

Allowed candidates should record:

- `OBSERVED_ENTRY_CANDIDATE`

The word "entry" here means "would have considered an entry". It does not mean
an execution-service `ENTRY` intent was created.

## 7. Observation record shape

**PROPOSAL:** start with append-only JSONL artifacts for the sidecar. A later
slice can promote the record to Postgres after the schema has been observed in
practice.

Recommended record fields:

| Field | Meaning |
|---|---|
| `schema_version` | Observation schema version, initially `1`. |
| `mode` | Constant `observe_only`. |
| `run_id` | Tick-level identifier. |
| `observed_at` | UTC observation timestamp. |
| `source_generated_at` | Trade Now response generation timestamp when available. |
| `timeframe` | Constant `1m` for this slice. |
| `pair_id` | Strategy pair identifier. |
| `selected_variant` | Candidate selected variant from Trade Now. |
| `approval_source` | Trade Now approval source. |
| `decision_reason_code` | Trade Now decision reason code. |
| `setup_gate_pass` | Trade Now setup gate. |
| `cost_gate_pass` | Trade Now cost gate. |
| `trade_gate_pass` | Trade Now trade gate. |
| `spread_z` | Candidate spread z-score when present. |
| `entry_distance_z` | Candidate entry-distance z when present. |
| `selected_score_z` | Candidate selected score when present. |
| `net_edge_bps` | Candidate net edge when present. |
| `opportunity_score` | Candidate opportunity score when present. |
| `learning_overlay_fresh` | Freshness flag when present. |
| `learning_overlay_age_seconds` | Overlay age when present. |
| `dispatch_mode` | Read-only execution dispatch mode snapshot. |
| `kill_switch_active` | Read-only kill switch snapshot. |
| `conflicting_live_trade` | Whether read-only execution state found a conflict. |
| `quality_window` | Ready-window attribution summary used by the gate. |
| `decision` | `OBSERVED_ENTRY_CANDIDATE` or a block code. |
| `reason_codes` | Ordered machine-readable reasons. |
| `observe_key` | Deterministic dedupe key. |
| `evidence` | Source URLs, statuses, and response timestamps. |

The observer must not write exchange credentials, account secrets, or raw
authorization headers into artifacts.

## 8. Dedupe and replay

**PROPOSAL:** use an observation key, not an execution idempotency key:

```text
observe-only:v1:<timeframe>:<pair_id>:<selected_variant>:<direction>:<minute_bucket>
```

The implementation may omit `direction` if the Trade Now row has no explicit
direction field. If direction is absent, the record must say so instead of
inventing it.

The observer should treat repeated records with the same key as duplicate
observations and emit `BLOCKED_DUPLICATE_OBSERVATION` or a tick-level duplicate
counter. This proves polling does not multiply would-act decisions.

## 9. Exit observation boundary

Autopilot execution cannot be considered complete without an exit model. The
observe-only slice may start with entry-candidate observation, but it must
record that limitation plainly.

**PROPOSAL:** before any non-observe automation is designed, a later slice must
define exit observation rules for candidates that would have been entered,
including stale signal, mean reversion, risk stop, time stop, and emergency
stop-close boundaries.

Until that exit proposal exists and is reviewed, the observer output is evidence
for candidate quality only. It is not proof that automated trading is ready.

## 10. Configuration

**PROPOSAL:** later implementation should be disabled by default with explicit
configuration.

Recommended configuration names:

| Setting | Default | Meaning |
|---|---:|---|
| `AUTOPILOT_OBSERVE_ENABLED` | `false` | Master enable for the observer. |
| `AUTOPILOT_OBSERVE_TIMEFRAMES` | `1m` | Allowed timeframe list. |
| `AUTOPILOT_OBSERVE_INTERVAL_SECONDS` | `60` | Polling cadence. |
| `AUTOPILOT_OBSERVE_MAX_SIGNAL_AGE_SECONDS` | `120` | Maximum accepted Trade Now age. |
| `AUTOPILOT_OBSERVE_REQUIRE_FRESH_OVERLAY` | `true` | Block stale learning overlay. |
| `AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS` | empty | Explicit pair/variant allowlist. Empty blocks all. |
| `AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS` | unset | Minimum recent ready-window rows. |
| `AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS` | unset | Minimum average ready-window edge. |
| `AUTOPILOT_OBSERVE_OUTPUT_DIR` | `artifacts/autopilot_observe` | JSONL output root. |

An empty allowlist should fail closed. The operator must explicitly select the
pair and variant set to observe.

## 11. Observability

**PROPOSAL:** later implementation should add bounded logs and metrics.

Structured log fields:

- `run_id`
- `observed_at`
- `timeframe`
- `pair_id`
- `selected_variant`
- `decision`
- `reason_codes`
- `observe_key`

Recommended metrics:

- `autopilot_observe_tick_total{result}`
- `autopilot_observe_decision_total{decision,reason,timeframe}`
- `autopilot_observe_candidate_total{timeframe}`
- `autopilot_observe_blocked_total{reason,timeframe}`
- `autopilot_observe_source_latency_ms{source}`
- `autopilot_observe_source_error_total{source}`

Avoid unbounded metric labels. Pair-level details should live in structured
logs and artifacts unless the implementation uses a bounded allowlist.

## 12. Interfaces and contracts

This design PR changes no runtime contracts.

Contracts that a later implementation must consider:

- `specs/contracts/strategy_pairs_trade_now_response.schema.json`
- `specs/contracts/strategy_trade_now_observability_response.schema.json`
- `specs/contracts/execution_order_intent_request.schema.json`

**PROPOSAL:** a later implementation should add one of these before code lands:

- an artifact schema for observe-only JSONL records under `specs/contracts/`;
  or
- a database migration and response/reporting contract if Postgres persistence
  is chosen first.

The first implementation should prefer an artifact schema and JSONL output.
That keeps the slice small and avoids committing to a database table before the
record shape is proven.

## 13. Test plan for implementation

The implementation PR should use TDD and include focused tests before code:

1. Schema validation: sample observe-only JSONL records validate against the new
   artifact schema.
2. Replay test: replaying the same Trade Now snapshot twice produces one
   allowed observation and one duplicate/block result.
3. Integration-style test with mocked HTTP clients: data-service health failure
   blocks all candidates.
4. Integration-style test with mocked HTTP clients: kill switch active blocks
   all candidates.
5. Integration-style test with mocked HTTP clients: malformed Trade Now response
   fails closed.
6. Negative execution test: observe-only code has no call path to
   `POST /v1/execution/order-intent` or
   `POST /v1/execution/order-intent/dispatch`.
7. Quality-gate test: a candidate that passes live gates but fails pair-level
   ready-window attribution is blocked with `BLOCKED_QUALITY_GATE`.

Host verification remains operator-only.

## 14. Versioning

This proposal changes docs only. No contract version bump is required.

Later implementation versioning depends on scope:

- additive artifact schema: document in `CHANGELOG.md`, no public API bump;
- additive optional HTTP fields: follow `docs/02-versioning-and-releases.md`;
- changed field meaning or required fields: breaking change review required;
- execution behavior change: separate proposal and explicit operator approval
  required.

## 15. Implementation slice recommendation

Recommended future slices:

1. **AUTO-1A - contract and harness**: add observe-only artifact schema,
   fixtures, config parsing, and tests. No polling.
2. **AUTO-1B - sidecar observer**: poll read-only surfaces, write JSONL, and
   prove no execution POST path exists.
3. **AUTO-1C - pair-level attribution report**: summarize observed candidates
   against later ready-window and paper-trade outcomes.
4. **AUTO-1D - operator runbook**: add Hetzner commands for observe-only
   operation and 24 to 72 hour evidence capture.
5. **AUTO-2 - exit observation design**: design hypothetical exit observation
   before any non-observe automation is considered.

No slice in this sequence should enable live automated `ENTRY` or `EXIT`.

## 16. Acceptance criteria for AUTO-1 design

This proposal is acceptable if reviewers agree that it:

- preserves manual-first execution policy;
- keeps automation observe-only and disabled by default;
- makes stale or missing readiness fail closed;
- uses pair-level ready-window attribution rather than broad historical paper
  trades as the first quality gate;
- requires tests proving no execution submission path exists;
- leaves host deployment and runtime operation as operator-only follow-up.
