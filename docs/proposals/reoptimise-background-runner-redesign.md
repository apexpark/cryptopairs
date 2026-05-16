# Proposal: bounded asynchronous reoptimization runner

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: codex, 2026-05-16.
>
> **Branch**: `codex/reoptimise-runner-redesign`. Stacked on
> `origin/codex/trade-now-live-z-score` so this proposal can reference the
> current hot-path safety work without carrying unrelated edits in this PR.
>
> **Item addressed**: operator-requested redesign of `/reoptimise` into a
> bounded asynchronous background reoptimization system.

---

## 1. Scope

This is a docs-only proposal. It does not:

1. implement a runner;
2. change service code;
3. change contracts or examples;
4. change runtime defaults;
5. update `CHANGELOG.md`;
6. enable live `ENTRY` or `EXIT`;
7. make promotion automatic.

The exact repository route found in `services/strategy-service/src/main.rs` is
`POST /v1/strategy/pairs/reoptimize`. This proposal uses `reoptimize` for the
exact API route and `reoptimise` only when referring to the operator-facing
feature request.

## 2. Context

### Verified repo facts

Current working-tree facts verified before writing this proposal:

- `services/strategy-service/src/main.rs` defines `ReoptimizeRequest` with only
  `timeframes: Option<Vec<String>>`.
- `services/strategy-service/src/main.rs` defines `ReoptimizeResponse` with
  aggregate run counts, transition counts, per-timeframe status, flatline
  summary, and errors.
- `services/strategy-service/src/main.rs` registers
  `POST /v1/strategy/pairs/reoptimize`.
- `services/strategy-service/src/main.rs` contains `spawn_reoptimize_worker`,
  which loops on a Tokio interval and runs the same heavy evaluation and
  persistence path for each configured timeframe.
- `services/strategy-service/src/main.rs` contains the synchronous
  `reoptimize` handler, which evaluates requested timeframes and performs
  mutation writes before returning the response.
- `services/strategy-service/src/main.rs` contains configurable startup gates
  for the reoptimize, sampled-slippage, and strategy-history-retention workers:
  `STRATEGY_REOPT_WORKER_ENABLED`,
  `STRATEGY_SAMPLED_SLIPPAGE_WORKER_ENABLED`, and
  `STRATEGY_HISTORY_RETENTION_WORKER_ENABLED`.
- `services/strategy-service/src/main.rs` contains `StrategyResponseCache`,
  `STRATEGY_RESPONSE_CACHE_TTL_MS`, and
  `STRATEGY_LIVE_Z_TICKER_MAX_WINDOW_BARS` handling for hot strategy response
  paths.
- `.env.example` and `docker-compose.yml` expose the reoptimize worker,
  sampled-slippage worker, history-retention worker, response-cache, and
  live-z ticker window configuration keys.
- `tools/scripts/strategy_tuning_report.py` posts to
  `/v1/strategy/pairs/reoptimize` unless `--skip-reoptimize` is supplied.
- `docs/22-strategy-tuning-control.md` requires unknown or missing safety
  inputs to force `HOLD`.
- `docs/playbooks/strategy-maintenance-automation-runbook.md` says automated
  maintenance evaluates and reports, while final `PROMOTE` / `REVERT` actions
  remain manual.
- `docs/12-risk-and-execution-policy.md` requires explicit operator
  confirmation for live `ENTRY` and `EXIT` intents and fail-closed behavior on
  unknown risk state.
- `docs/15-observability-and-alerting.md` already names optimizer lifecycle
  and candidate lifecycle metrics as alertable strategy telemetry.

### Operator-provided production context

The following runtime facts were provided by the operator in the task prompt
and were not independently verified by this agent on the host:

- production safety config currently has these heavy workers disabled:
  - `STRATEGY_REOPT_WORKER_ENABLED=false`;
  - `STRATEGY_HISTORY_RETENTION_WORKER_ENABLED=false`;
  - `STRATEGY_SAMPLED_SLIPPAGE_WORKER_ENABLED=false`;
- response cache is enabled:
  - `STRATEGY_RESPONSE_CACHE_TTL_MS=10000`;
  - `STRATEGY_LIVE_Z_TICKER_MAX_WINDOW_BARS=240`;
- the CPU spike was resolved only after bounding hot strategy response paths
  and disabling heavy background workers.

This proposal treats those runtime facts as design inputs, not as repo-derived
facts.

## 3. Problem

The current reoptimization shape has two unsafe extremes:

1. when the worker is enabled, a periodic background loop can run heavy
   evaluation and persistence work without an explicit runtime budget,
   persisted lease, progress contract, or cancellation protocol;
2. when the worker is disabled, reoptimization stops being autonomous and
   operator/reporting flows fall back to direct synchronous calls or skipped
   reoptimization.

The target state is not "turn the worker back on." The target state is a
bounded asynchronous runner whose work is schedulable, observable, cancelable,
auditable, and unable to liberalize trading behavior.

## 4. Goals

The redesigned system should:

1. run autonomous reoptimization again under explicit schedules and budgets;
2. guarantee single-flight execution for mutation-producing runs;
3. enforce CPU/runtime/concurrency limits before any production enablement;
4. expose durable run status and progress;
5. support cancellation at safe checkpoints;
6. write run artifacts that make the decision timeline auditable;
7. return fail-closed recommendations when any required input is missing,
   stale, timed out, or ambiguous;
8. keep promotion operator-controlled.

## 5. Non-goals

This redesign must not:

1. enable live entries or exits;
2. make `PROMOTE` automatic;
3. bypass champion drift, integrity, cost, risk, or operator gates;
4. weaken `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`;
5. rely on the response cache as a correctness boundary;
6. hide failed or partial optimization behind an `OK` status;
7. require host SSH access from remote agents.

## 6. Invariants

Any implementation that follows this proposal must preserve these invariants:

1. unknown runner state produces a `HOLD` or blocked recommendation;
2. stale runner state produces a `HOLD` or blocked recommendation;
3. failed lease acquisition produces no mutation writes;
4. budget exhaustion stops new work and returns a terminal degraded or failed
   status;
5. cancellation is honored between safe work units and never leaves a run
   marked successful;
6. only one mutation-producing reoptimization run can be active at a time;
7. promotion remains a separate operator action with explicit confirmation;
8. live trading behavior is not liberalized by this redesign.

## 7. Options Considered

### Option A - keep workers disabled and rely on manual synchronous calls

Leave `STRATEGY_REOPT_WORKER_ENABLED=false` in production and keep using
manual/report-triggered `POST /v1/strategy/pairs/reoptimize` calls when needed.

**Pros**

- Lowest immediate CPU risk.
- No new storage or contract surface.

**Cons**

- Reoptimization is not autonomous.
- Synchronous callers still own the heavy request path.
- No durable progress, lease, cancellation, or artifact protocol.
- Report flows can time out or skip reoptimization, which weakens operational
  evidence.

**Verdict**: acceptable as the current safety posture, not acceptable as the
target design.

### Option B - re-enable the existing worker with larger intervals

Turn the existing worker back on with a long interval and rely on logs.

**Pros**

- Small implementation change.
- Restores autonomy quickly.

**Cons**

- Does not provide leases, single-flight guarantees, progress, cancellation,
  runtime budgets, or artifacts.
- CPU spikes can recur if a cycle overlaps with hot paths or takes longer than
  expected.
- Failure is mostly log-based and not contract-visible.

**Verdict**: not recommended.

### Option C - bounded asynchronous in-service runner

Add a durable run queue/state machine inside `strategy-service`. API calls
enqueue or inspect runs. A background runner claims one lease, processes bounded
work units, persists progress and artifacts, and returns fail-closed
recommendations.

**Pros**

- Keeps strategy evaluation close to existing repository and metrics code.
- Supports single-flight, leases, budgets, progress, cancellation, and
  artifacts.
- Enables autonomous scheduling without putting heavy work on hot request
  threads.
- Can be rolled out behind disabled-by-default flags.

**Cons**

- Requires new persistence and contract surfaces.
- Requires careful migration of current synchronous callers.
- Needs host canary evidence before production enablement.

**Verdict**: recommended.

### Option D - external cron-only runner

Move scheduling and execution into a host-side script or systemd timer, using
existing service endpoints.

**Pros**

- Separates scheduling from the service process.
- Familiar host operations model.

**Cons**

- Still depends on service endpoints for heavy work unless paired with new
  async contracts.
- Harder to enforce process-local single-flight with API-triggered runs.
- Splits lifecycle state between host scripts and service internals.

**Verdict**: useful for host orchestration later, but insufficient as the core
contract.

## 8. Recommended Design

Adopt Option C in slices, with the first implementation disabled by default.

### Runner state machine

PROPOSAL: model each run with a durable `run_id` and one of these bounded
states:

1. `QUEUED`;
2. `LEASED`;
3. `RUNNING`;
4. `CANCEL_REQUESTED`;
5. `CANCELED`;
6. `SUCCEEDED`;
7. `DEGRADED`;
8. `FAILED`;
9. `EXPIRED`.

Only terminal states may produce final recommendation artifacts. Any terminal
state other than `SUCCEEDED` must recommend `HOLD` or `OPERATOR_REVIEW_REQUIRED`
instead of promotion.

### Triggers

PROPOSAL: support explicit trigger sources:

- `SCHEDULED`;
- `MANUAL_API`;
- `MAINTENANCE_REPORT`;
- `RECOVERY`.

The trigger source is metadata. It must not change risk or promotion gates.

### Scheduling

PROPOSAL: replace the current interval-only worker behavior with a scheduler
that creates queued runs only when all scheduling gates pass:

1. scheduler feature flag enabled;
2. no active leased/running run exists;
3. last terminal run is older than the configured interval;
4. service health is acceptable;
5. data/integrity prechecks are not already known-failed;
6. CPU/runtime budget config is valid.

If any gate is unknown, the scheduler does not enqueue a mutation-producing
run and emits a fail-closed reason.

### Leases and single-flight

PROPOSAL: use a persisted lease on the run row:

- `lease_owner`;
- `lease_acquired_at`;
- `lease_expires_at`;
- `heartbeat_at`;
- `lease_generation`.

The runner must acquire the lease atomically before mutation writes. A lease
must be heartbeat-extended only by the current owner and generation. If the
lease expires, the run becomes `EXPIRED` unless a recovery pass can prove the
same owner is still healthy. The first implementation should enforce global
single-flight for all mutation-producing reoptimization work.

### Budgets

PROPOSAL: add explicit budgets before production enablement:

- max wall-clock runtime per run;
- max runtime per timeframe;
- max pair evaluations per run;
- max pair evaluations per timeframe;
- max in-flight pair evaluations;
- max DB write batch size;
- max artifact bytes per run;
- minimum cooldown between runs;
- lease TTL and heartbeat interval.

Recommended first production posture:

1. global run concurrency: `1`;
2. per-pair evaluation concurrency: `1` or very small;
3. mutation writes serialized per pair/timeframe;
4. stop new work when any budget is exhausted;
5. return `DEGRADED` or `FAILED` with recommendation `HOLD`.

### Work units

PROPOSAL: process work in checkpointable units:

1. run precheck;
2. timeframe precheck;
3. pair evaluation;
4. selected-row/performance persistence;
5. shadow model/opportunity/paper-trade/candidate lifecycle persistence;
6. timeframe summary;
7. run summary and artifacts.

Cancellation and budget checks happen between work units. A partially processed
run must show exact counts for completed, skipped, canceled, and failed units.

### Progress reporting

PROPOSAL: expose progress as durable counts:

- requested timeframes;
- active timeframe;
- total pairs planned;
- pairs completed;
- pairs skipped;
- pairs failed;
- selected rows written;
- drift rows written;
- transition counts;
- critical and non-critical errors;
- current phase;
- current recommendation;
- artifact manifest.

Progress must be monotonic except for explicitly documented retry/recovery
fields.

### Cancellation

PROPOSAL: cancellation is a state transition, not a process kill.

1. `POST cancel` sets `CANCEL_REQUESTED` when the run is cancelable.
2. The runner checks cancellation between safe work units.
3. New pair/timeframe work stops after cancellation is observed.
4. The run ends as `CANCELED`, not `SUCCEEDED`.
5. The recommendation is `HOLD`.
6. Artifacts record which units completed before cancellation.

### Artifacts

PROPOSAL: every run writes an artifact bundle under a configured artifact root:

- `request.json`;
- `progress.json`;
- `summary.json`;
- `errors.json`;
- optional per-timeframe detail files;
- optional operator summary markdown.

Artifacts must be referenced by status responses rather than embedded
unboundedly in API payloads. Artifact paths must stay within the configured
artifact root, following the existing maintenance artifact safety pattern.

### Recommendations

PROPOSAL: run output can recommend only:

- `HOLD`;
- `OPERATOR_REVIEW_REQUIRED`;
- `PROMOTION_CANDIDATE_AVAILABLE`;
- `REVERT_REVIEW_REQUIRED`.

`PROMOTION_CANDIDATE_AVAILABLE` is not an action. It means the operator can
review the candidate through existing or future manual controls. It must never
enqueue a promote action by itself.

Fail-closed mappings:

- missing integrity input -> `HOLD`;
- stale candles -> `HOLD`;
- risk/execution state unknown -> `HOLD`;
- lease lost -> `HOLD`;
- budget exhausted -> `HOLD` or `OPERATOR_REVIEW_REQUIRED`;
- cancellation -> `HOLD`;
- partial artifact write -> `HOLD`;
- projection/accounting anomaly -> `HOLD`.

## 9. Interfaces and Contracts

No contract changes are made in this proposal PR.

### Existing affected contracts

Future implementation will likely touch:

- `specs/contracts/strategy_pairs_reoptimize_response.schema.json`;
- `specs/examples/strategy_pairs_reoptimize_response.example.json`;
- `specs/contracts/strategy_maintenance_latest_response.schema.json`;
- `specs/contracts/strategy_maintenance_action_response.schema.json`.

Reason:

- the existing reoptimize contract describes synchronous aggregate output;
- maintenance reports currently embed opaque report payloads;
- maintenance actions currently cover only `PROMOTE` and `REVERT`.

### Proposed new contracts

PROPOSAL: add new contracts before implementation:

- `specs/contracts/strategy_reoptimize_run_enqueue_response.schema.json`;
- `specs/contracts/strategy_reoptimize_run_status_response.schema.json`;
- `specs/contracts/strategy_reoptimize_run_cancel_response.schema.json`;
- `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`.

PROPOSAL: add examples under `specs/examples/` for each new contract.

### Endpoint shape

PROPOSAL: prefer new async endpoints over changing the existing synchronous
route in place:

- `POST /v1/strategy/reoptimize/runs` to enqueue a run;
- `GET /v1/strategy/reoptimize/runs/latest` to fetch latest run status;
- `GET /v1/strategy/reoptimize/runs/{run_id}` to fetch one run status;
- `POST /v1/strategy/reoptimize/runs/{run_id}/cancel` to request
  cancellation;
- `GET /v1/strategy/reoptimize/artifact?path=...` to download run artifacts.

Compatibility choice for the existing route:

1. keep `POST /v1/strategy/pairs/reoptimize` as synchronous during Slice A/B;
2. add explicit async endpoints first;
3. migrate scripts/UI to async endpoints;
4. only then decide whether the old route becomes a compatibility wrapper,
   admin-only endpoint, or deprecated route.

Changing `POST /v1/strategy/pairs/reoptimize` from synchronous results to
enqueue-only semantics in place would be a contract meaning change and needs a
separate compatibility review.

### Proposed status response fields

PROPOSAL: status responses include:

- `schema_version`;
- `generated_at`;
- `run_id`;
- `status`;
- `trigger_source`;
- `requested_timeframes`;
- `started_at`;
- `finished_at`;
- `lease_owner`;
- `lease_expires_at`;
- `progress`;
- `budgets`;
- `recommendation`;
- `fail_closed_reasons`;
- `artifact_manifest`;
- `errors`;
- `operator_action_required`.

Nested objects should use `additionalProperties: false`, matching current
strict contract style.

## 10. Persistence

PROPOSAL: add durable tables in a later implementation slice:

- `strategy_reoptimize_runs`;
- `strategy_reoptimize_run_events`;
- possibly `strategy_reoptimize_run_artifacts`.

Minimum run fields:

- `run_id`;
- `status`;
- `trigger_source`;
- `requested_timeframes`;
- `lease_owner`;
- `lease_generation`;
- `lease_acquired_at`;
- `lease_expires_at`;
- `heartbeat_at`;
- `created_at`;
- `started_at`;
- `finished_at`;
- `cancel_requested_at`;
- `progress_json`;
- `summary_json`;
- `recommendation`;
- `fail_closed_reasons_json`;
- `artifact_manifest_json`.

The implementation should prefer append-only events for audit history and a
current run row for efficient status reads.

## 11. Interaction With Hot Paths

The runner must not depend on hot response paths being called to make progress.
It should call internal evaluation functions directly under its own budgets.

The response cache remains a hot-path protection, not a correctness guarantee.
The runner must not:

1. invalidate hot caches on every pair;
2. hold hot-path locks while doing DB writes;
3. make user-facing cue/live-z responses wait for a background run;
4. increase polling frequency to compensate for missing progress APIs.

UI and maintenance scripts should poll the durable status endpoint at a bounded
interval and back off after terminal states.

## 12. Observability

Future implementation should add bounded metrics:

- `strategy_reoptimize_run_total{trigger,status}`;
- `strategy_reoptimize_active_runs`;
- `strategy_reoptimize_lease_acquire_total{result}`;
- `strategy_reoptimize_lease_lost_total`;
- `strategy_reoptimize_duration_seconds{status}`;
- `strategy_reoptimize_budget_exhausted_total{budget}`;
- `strategy_reoptimize_cancel_total{result}`;
- `strategy_reoptimize_progress_pairs_total{timeframe,result}`;
- `strategy_reoptimize_artifact_write_total{result}`;
- `strategy_reoptimize_fail_closed_total{reason}`;
- `strategy_reoptimize_recommendation_total{recommendation}`.

Structured logs should include:

- `run_id`;
- `trigger_source`;
- `lease_owner`;
- `lease_generation`;
- `timeframe`;
- `pair_id`;
- `phase`;
- `budget_name`;
- `cancel_requested`;
- `artifact_path`;
- `recommendation`;
- `fail_closed_reason`;
- `status_before`;
- `status_after`.

Alerting should cover:

1. repeated failed scheduled runs;
2. stuck `RUNNING` or `LEASED` state beyond TTL;
3. repeated lease acquisition failures;
4. repeated budget exhaustion;
5. artifact write failure;
6. recommendation unavailable;
7. promotion attempted without operator confirmation.

## 13. Testing Strategy

### Proposal PR

This docs-only PR should run:

1. `git diff --check`;
2. JSON syntax validation for existing `specs/contracts/*.json` and
   `specs/examples/*.json`.

### Future contract PR

Required:

1. schema validation for every new example;
2. compatibility review for existing reoptimize and maintenance contracts;
3. version bump according to `docs/02-versioning-and-releases.md`;
4. `CHANGELOG.md` entry.

### Future implementation PR

Required unit coverage:

1. scheduler gate decision table;
2. lease acquire, heartbeat, loss, expiry, and recovery transitions;
3. single-flight refusal;
4. budget math and exhaustion;
5. cancellation state transitions;
6. fail-closed recommendation mapping;
7. artifact path containment.

Required integration coverage:

1. Postgres-backed run queue and lease tests;
2. enqueue and status endpoint tests;
3. cancellation endpoint tests;
4. artifact manifest persistence tests;
5. existing synchronous route compatibility tests if retained.

Required replay/regression coverage:

1. fixed candle fixtures produce deterministic per-timeframe run summaries;
2. repeated run with the same inputs yields the same recommendation and counts;
3. stale or incomplete data fixture yields `HOLD`.

## 14. Implementation Slice Plan

### Slice A - contracts and examples

Add the new async run/status/cancel/artifact contracts and examples. Do not
change service behavior yet.

Acceptance:

- schema validation passes;
- compatibility notes are explicit;
- `CHANGELOG.md` records additive contracts;
- no runtime behavior changes.

### Slice B - persistence and state machine behind disabled flag

Add run tables, state transition helpers, and artifact path validation behind
disabled-by-default config.

Acceptance:

- unit tests cover transition invariants;
- Postgres-backed tests cover lease/single-flight behavior;
- no scheduler is enabled in production by default.

### Slice C - bounded runner

Add the async runner loop with budgets, checkpointed work units, heartbeats,
progress writes, and cancellation checks.

Acceptance:

- default disabled;
- budgets required before enablement;
- budget exhaustion produces terminal degraded/failed status and `HOLD`;
- no automatic promotion.

### Slice D - async API and script migration

Add enqueue/status/cancel endpoints and migrate `strategy_tuning_report.py` /
`strategy_maintenance_cycle.py` to request a run, poll status, and fail closed
on timeout.

Acceptance:

- bounded polling;
- timeout yields `HOLD`;
- old synchronous route behavior remains documented and compatible, or is
  deprecated through a versioned path.

### Slice E - observability and runbooks

Add metrics, logs, alerts, dashboard/runbook notes, and operator-only host
verification steps.

Acceptance:

- metrics have bounded labels;
- logs include `run_id`;
- runbooks describe enable, disable, cancel, and rollback-to-disabled steps.

### Slice F - production canary

Enable scheduler on host only after operator approval and capture evidence.

Acceptance:

- host identity captured;
- worker flags and budgets captured;
- one completed run per target timeframe, or an approved narrower canary;
- CPU and hot endpoint latency stay within operator-approved thresholds;
- live `ENTRY` / `EXIT` remain disabled;
- promotion remains manual.

## 15. Host and Operator Verification

Host verification is operator-only. Remote agents must not SSH into
`cryptopairs` or claim host evidence.

For a future implementation/canary, the operator should capture:

1. deployed branch, commit, and dirty status;
2. runtime values for all reoptimize scheduler, lease, budget, cache, and
   worker flags;
3. proof that live `ENTRY` / `EXIT` remain disabled;
4. proof that `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` remains set;
5. pre-enable CPU and hot endpoint latency baseline;
6. scheduler enqueue log and run id;
7. run status progression from queued to terminal state;
8. run artifacts;
9. metrics for lease, progress, budget, cancellation, and recommendation;
10. post-run CPU and hot endpoint latency comparison;
11. maintenance report behavior after async migration;
12. explicit operator decision if any candidate is promoted later.

If any host check is missing, stale, or contradictory, the safe next step is to
keep the scheduler disabled and keep recommendations at `HOLD`.

## 16. Rollback and Disable Path

The first implementation must include a clear disable path:

1. set scheduler enabled flag to false;
2. refuse new scheduled runs;
3. allow active run to finish or cancel it;
4. mark expired leases as `EXPIRED`;
5. keep latest status readable;
6. preserve artifacts;
7. keep maintenance recommendations fail-closed until a fresh successful run.

Emergency rollback must not delete run history.

## 17. Versioning

This proposal PR is docs-only and changes no public behavior, contracts, or
operator workflow. No version bump and no `CHANGELOG.md` entry are required.

Future work:

1. additive new contracts and optional fields require `MINOR`;
2. changed meaning for existing `/v1/strategy/pairs/reoptimize` response fields
   requires `MAJOR` unless introduced through a backward-compatible endpoint or
   transition period;
3. new config keys and operator workflow changes require `CHANGELOG.md`;
4. new metrics and labels are contracts under
   `docs/03-contracts-and-compatibility.md` and must use bounded labels.

## 18. Open Questions for Approval

1. Base endpoint strategy: approve new async endpoints first, or require the
   existing `/v1/strategy/pairs/reoptimize` route to become an async wrapper?
2. Initial canary scope: all timeframes, or start with one low-frequency
   timeframe?
3. Initial runtime budgets: what CPU/runtime thresholds should block
   production enablement?
4. Lease backend: approve Postgres-backed leases in strategy-service, or prefer
   an external scheduler/lock service later?
5. Artifact retention: how long should reoptimization artifacts be retained?
6. Maintenance scripts: should `strategy_tuning_report.py` wait for async run
   completion, or consume latest successful run unless explicitly requested?
7. Cancellation authority: which operator/API auth boundary is required before
   cancellation endpoints are exposed?
