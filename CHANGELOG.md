# Changelog
All notable changes to this project will be documented in this file.

This project follows SemVer as defined in `docs/02-versioning-and-releases.md`.

## Unreleased
### Fixed
- AUTO-2A paper ledger now accepts real observe-only records whose observe key
  is minute-bucketed and whose strategy `source_generated_at` includes
  fractional seconds in the same serialized second as `observed_at`, while
  preserving stale/future candidate blocking.
- Data-service `/health` now performs a repository-backed Postgres health
  check and returns 503 on repository errors instead of reporting static OK.
- Trade z-score charts now anchor the initial 16x zoom window on the newest live
  data after a hard refresh, instead of opening on the oldest loaded history.
- Hosted web builds now treat blank Vercel service URL environment variables as
  invalid and fall back to the public `api.apexpark.io` service bases, while
  preserving local service defaults for localhost development.

### Operator Tooling
- Canonicalized `.github/CODEOWNERS` as the single source of truth for
  merge Tier 3 protected paths: expanded to the full 2026-07-12 list (all
  services, scripts, playbooks, git hooks, compose files, dependency and
  toolchain manifests, governance and ops docs, agent state, autopilot
  tooling) while retaining all legacy protections. Tier 1–2 delegated PRs
  now touch neither `CHANGELOG.md` nor `docs/AGENT_STATE.md`; both catch
  up in Tier 3 governance PRs.
- Added `CLAUDE.md`: the Claude session entry point and Autonomy Doctrine.
  Current phase is operator-invoked and evidence-gated (no unattended
  loops); autonomy graduates per component on the AUTO-2 §3 non-negotiable
  sequence (AUTO-2A → 2B → 2C → 2D → AUTO-3 design gate, with AUTO-1 as
  the deployed observe-only predecessor) only by Operator sign-off merged
  via the Tier 3 flow; AUTO-3 is never grantable by the doctrine; the
  2026-07-12 safety invariants and the docs/23 always-on rules are
  restated with capital protection never restricted. `AGENTS.md` remains
  highest precedence.
- Made the 2026-07-12 merge-authority tiers operative (upon merge of this
  slice): `docs/ops/ai_workflow.md` now defines the four tiers with a
  tier-scoped review/merge protocol, the PR template requires a merge-tier
  declaration, the Codex prompt pack gains a Tier 3 exact-SHA reviewer
  prompt, and the decisions register records the PR #245 merge
  authorization plus the standing Tier 1–2 delegated-merge decision
  (green-checks-verified merges only, per-merge record comment, revocable,
  with a forbidden-even-when-delegated list). The Tier 3 protected-path
  list was expanded after adversarial inner review and Operator
  ratification: all `services/**`, `scripts/**`, `docs/playbooks/**`,
  `.githooks/**`, `docker-compose*.yml`, dependency/toolchain manifests,
  and `.env.example` now require cross-model review plus Operator
  authorization. Tier 3–4 requirements are unchanged or strengthened.
- Installed the dual-agent governance scaffold (v0) under `.agentic/**`,
  building on the loop-harness adapter: constitution, worker-tier,
  evidence-ladder, context, and git/merge policies, seeded
  decisions/risks/assumptions/capabilities/agent-runs registers, nine
  work-order/review/handoff templates, and intake/dispatch/review/blocked
  playbooks. Records the 2026-07-12 merge-authority tiers as adopted but
  non-operative until `docs/ops/ai_workflow.md` is amended; grants no new
  authority and repo governance wins.
- Added a project-local `.agentic/**` adapter for bounded agentic loops,
  including default-deny local policy, machine-checkable loop spec/state
  templates, a repository-development loop playbook, and a loop-run register
  while preserving existing Apex/AGENTS authority boundaries.
- AUTO-2A paper-only tooling now supports direction-gated static allowlists
  using `pair_id:selected_variant:direction` entries while preserving legacy
  `pair_id:selected_variant` behavior. Paper reports record the static
  allowlist mode so 72h direction-gated trials can distinguish pair-level,
  direction-level, and mixed eligibility evidence.
- Added AUTO-2A paper-only report tooling and hosted runbook commands for
  static `1m` paper trial evidence capture: `autopilot_paper_report.py`
  summarizes append-only paper decisions/positions, records run configuration
  and blocked-decision breakdowns, emits JSON/Markdown, and preserves the
  no-execution-service/no-live-automation boundary.
- Added AUTO-2A paper-only ledger contracts and a disabled-by-default static
  `1m` `autopilot_paper.py` tool that consumes observe-like candidates and
  paper marks, writes append-only paper decisions/positions, suppresses
  duplicate/open-position/cooldown re-entry, and uses fixed holding-window
  exits without any execution-service order-intent or dispatch path.
- Added the AUTO-2A focused static paper-autopilot design proposal, defining
  the disabled-by-default static `1m` paper trial, duplicate/cooldown/open
  paper-position controls, fixed holding-window exits, and no-execution POST
  boundaries before implementation.
- Added a Slice Loop Check to the Apex harness workflow, prompt pack,
  remote-agent bootstrap, and PR template so coding slices must show new input,
  state transition, concrete value, non-repetition, and stop/defer boundaries
  before implementation.
- Added the AUTO-2 1m paper-autopilot governance roadmap and Superpowers plan,
  locking the next automation sequence to focused static paper trial, shadow
  champion/challenger allowlist, governed dynamic allowlist, dynamic paper
  trial, and a separate live-design gate before any live automation work.
- Added AUTO-1C/AUTO-1D observe-only attribution tooling and hosted evidence
  capture docs: an offline `autopilot_observe_report` JSON/Markdown report
  compares 1m observe-only candidates with later ready windows and simulated
  paper-trade outcomes, with aggregate paper-trade deduplication and explicit
  non-execution caveats.
- Added a disabled-by-default `1m` autopilot observe-only sidecar that polls
  read-only health, Trade Now, kill-switch, dispatch-mode, and open-trade
  surfaces, then writes append-only JSONL "would consider" records without any
  execution order-intent or dispatch path. Mixed or non-`1m` timeframe config,
  execution `FAIL_CLOSED` dispatch mode, malformed safety payloads, and repeated
  observe keys fail closed into block records.
- Added a hosted systemd timer installer for read-only signal-learning overlay
  refreshes, keeping Trade Now's approved-universe artifact fresh without a
  long-running shell loop, with artifact/log paths constrained under
  `artifacts/signal_learning/`.
- Rotated the pre-push Rust preflight bypass from legacy `SKIP_RUST_CHECKS=1` to reason-bearing `RUST_PREFLIGHT_OVERRIDE=<reason>`, with boolean-ish override values rejected fail-closed.
- Pinned the Rust toolchain to channel `1.95` for local rustup-aware cargo invocations and CI, with CI logging the active toolchain before cargo checks.
- `.githooks/pre-push` now autostashes unstaged and untracked work before running the Rust preflight so pushes check the staged tree, with `scripts/test-pre-push.sh` covering the restore paths.
- `docs/27` live cue mismatch audit now reads `cue.selection_state` fields for stored champion, evaluated best, source, and validation state instead of legacy cue-selected fields.

### Added
- Added `autopilot_observe_record` artifact schema and example for validating
  observe-only 1m candidate/block records.
- Strategy service now exposes Prometheus-style `/metrics` counters for champion-selection observability:
  - `pairs_cue_projection_total{outcome}`
    - records `PROJECTED_BLOCKED` separately when champion projection succeeds but drift blocking keeps the cue non-actionable
  - `strategy_selection_transition_total{decision,timeframe}`
  - `strategy_selection_rows_updated_without_transition_total{timeframe}`
- Multi-agent operating model:
  - `AGENTS.md` §8 defines Local vs Remote agent roles, the canonical-source rule, work allocation defaults, branch/PR conventions, and a mandatory hydration sequence (`AGENTS.md` → `docs/AGENT_STATE.md` → `docs/playbooks/remote-agent-bootstrap.md` → task brief → code).
  - `docs/AGENT_STATE.md` is a living state file: sprint pin, in-flight work, blocked items, open follow-ups (S4/S6-S8 from Slice A review, B1-B6 from Slice B review including the new B6 Postgres-backed test harness item, X1-X2 cross-cutting), and update protocol. Curated by the local agent; deltas proposed by remote agents in their PRs.
  - New `docs/playbooks/remote-agent-bootstrap.md` is the operational procedure for §8.4: bootstrap prompt, self-preflight (pin match / clean tree / fresh feature branch / base up to date), claim protocol via the open-follow-ups table, verification sequence (calls `scripts/check-rust-ci.sh` so it stays in sync with the pre-push hook, plus tsc and JSON-schema validation), branch/commit/PR templates, design-proposal-first PR variant, blocking protocol, local review checklist.
- Experimental signal-learning cycle tooling (recommendation-only):
  - New policy file for confidence-gated recursive signal logic updates:
    - `infra/config/signal_learning_policy.json`
  - New script:
    - `tools/scripts/signal_learning_cycle.py`
    - Periodically samples cues/expectancy/paper-trades by pair/timeframe.
    - Persists immutable cycle reports + rolling state artifacts.
    - Recursively updates `artifacts/signal_learning/signal_logic.json` with confidence-gated `PROMOTE|DEMOTE|HOLD` recommendations.
    - Ranks `trade_eligible` rows into deterministic universe-selection outputs (`selection.top_1` and `selection.top_k`) using configurable utility weights and per-base-asset concentration caps.
    - Supports configurable reason-aware utility penalties (for example `PAPER_LOW_SAMPLE`) when ranking selected candidates.
    - Emits selection observability diagnostics:
      - `selected_with_paper_low_sample_count`
      - `top1_dwell_cycles_by_pair_tf`
      - `selection_turnover_rate`
    - Enforces non-invasive behavior (no runtime config mutation/deploy writes).
  - New runbook:
    - `docs/playbooks/signal-learning-runbook.md`
  - New artifact contract/example:
    - `specs/contracts/signal_learning_cycle_report.schema.json`
    - `specs/examples/signal_learning_cycle_report.example.json`
  - New unit coverage:
    - `tools/scripts/tests/test_signal_learning_cycle.py`
- Strategy live selected-signal config scaffolding:
  - `strategy_selected_signal` now persists additive `config_json` metadata for the active live signal configuration.
  - Strategy cues now expose `selected_signal_config` so operators can inspect the live bands/lookback/holding parameters driving evaluation.
  - Live evaluation now hydrates its bands/lookback/hold settings from persisted selected-signal config with legacy fallback to settings defaults.
- Strategy reoptimize control-plane hardening (Slice C):
  - `POST /v1/strategy/pairs/reoptimize` now returns explicit run status fields:
    - `status` (`OK|DEGRADED|FAILED`)
    - `critical_error_count`
    - `non_critical_error_count`
    - `timeframe_statuses[]`
    - `flatline_summary`
  - Reoptimize errors are now tagged with additive `code` and `severity` (`CRITICAL|NON_CRITICAL`).
  - Reoptimize mutation path now aborts remaining writes for a timeframe after first critical optimizer failure (fail-closed continuation guard).
  - Canonical selected-variant flatline diagnostics are computed during evaluation and aggregated in reoptimize observability.
- Strategy backtest leakage hardening (Slice D):
  - `compute_backtest_series` now uses causal prior-window z-score normalization instead of full-sample mean/stddev normalization.
  - Added regression coverage proving backtest points before the final bar are invariant to future-only tail spikes.
  - Updated deterministic backtest scenarios to include warm-up history under prior-window normalization.
- Strategy champion selection stability and full-config lock semantics (Slice E):
  - Champion transition now applies configurable hysteresis during post-switch cooldown:
    - `STRATEGY_CHAMPION_SWITCH_HYSTERESIS_DELTA`
    - `STRATEGY_CHAMPION_SWITCH_COOLDOWN_SECS`
  - On `KEEP_CHAMPION`, persisted champion config (bands/windows) is retained instead of inheriting challenger config fields.
  - Added unit coverage for cooldown hysteresis behavior and champion-config retention on lock.
- Strategy signal-math refinement and unit consistency (Slice F):
  - `FUNDING_ADJUSTED` now converts funding drag from bps into a dimensionless z-penalty using spread volatility, then shrinks score magnitude symmetrically (`long`/`short`) instead of applying a raw bps subtraction.
  - Variant edge estimation now runs in executable leg-return space (`left_return - hedge_ratio * right_return`) and reports outcome in bps, removing prior log-spread/spot-price unit mismatch.
  - Vol-normalized scores now use robust volatility pressure from absolute spread-diff robust z-scores, reducing outlier sensitivity.
  - Added unit coverage for funding penalty scaling/symmetry, return-domain edge estimation, and robust vol-normalized suppression behavior.
- Execution open-trades API and Trade tab live position view for SIM/manual operations:
  - New endpoint: `GET /v1/execution/portfolio/open-trades` (pair-level spread + per-leg live unrealized PnL using data-service marks).
  - New contracts/examples:
    - `specs/contracts/execution_open_trades_response.schema.json`
    - `specs/examples/execution_open_trades_response.example.json`
  - Trade UI now shows an `Open Trades` panel (replacing historical intent timeline) with:
    - selected-pair spread summary (direction, size, entry/current/target z, live spread uPnL),
    - per-leg live table (side, qty, entry ref, mark, leg uPnL),
    - live current-z tick chip.
  - Opportunities status model simplified to two states only: `READY` and `WAIT` (removed `<TWO` display state).
- Mixed-lot-step spread sizing guardrails for execution intents:
  - Order intent contract now supports optional `sizing` payload metadata (target notional, target hedge ratio, reference prices, planned leg qty, achieved drift, tolerance overrides).
  - Dispatch mode response now includes runtime sizing tolerance configuration:
    - `sizing_tolerance_notional_drift_pct`
    - `sizing_tolerance_hedge_ratio_drift_pct`
  - Execution service validates submitted sizing payload against pair/instrument, planned leg qty, and drift tolerances; rejects out-of-tolerance or inconsistent sizing fail-closed.
  - Trade UI now sizes entries/exits from target USD notional using live bid/ask, per-leg lot-step quantization, and pre-submit drift/tolerance preview.
- Analytics chart provenance visibility:
  - Analytics now shows the active chart pair, selected variant, exit mode, and effective fee basis above the equity curve.
  - Persisted pair selections that are no longer present in the live cue set now surface an explicit warning instead of silently rewriting local storage to the first live cue.
- Slice A `Trade Now` proposal scaffolding:
  - Added proposal doc `docs/24-trade-now-opportunity-proposal.md` with locked bucket semantics, overlay TTL, governance precedence, and baseline cadence numbers.
  - Added machine-readable contract/example for the proposed read model:
    - `specs/contracts/strategy_pairs_trade_now_response.schema.json`
    - `specs/examples/strategy_pairs_trade_now_response.example.json`
  - Tightened the draft `trade-now` contract to version `0.2.1` with stable reason-code enums, explicit overlay freshness invariants, a stale-overlay guard that forbids learning-selected rows in `tradable_now`, and per-row `requires_fresh_overlay` semantics.
- Slice B1 `Trade Now` learning overlay loader:
  - `strategy-service` now includes an internal latest-artifact loader for signal-learning cycle reports, selecting the newest report by logical `generated_at` (with filesystem time only as tiebreak), plus pure overlay-policy resolution for stale TTL, governance precedence, operator-promoted champion survival, and legacy-fallback suppression.
  - Selected-signal provenance policy now uses shared source constants so legacy-fallback and operator-promotion handling cannot drift silently from their producers.
  - Added unit coverage for selected-vs-eligible splitting, stale downgrade, operator-promoted-vs-learning-HOLD precedence, pending-challenger suppression, and legacy fallback behavior.
- Slice B2 `Trade Now` strategy endpoint:
  - Added `GET /v1/strategy/pairs/trade-now`, which builds grouped `tradable_now`, `watchlist`, and `excluded` rows by combining live cue gates with the Slice B1 learning overlay policy.
  - The endpoint carries learning-overlay freshness metadata, selected-config provenance, and stable decision/watch/block reason codes that match the Slice A schema.
  - Trade Now rows now include additive `selected_score_z` and `entry_distance_z` diagnostics (`abs(selected_score_z) - entry_band`) so setup-blocked watchlist rows can show how far the selected signal remains from the live entry threshold.
  - Added Rust-side contract drift protection: grouped-response orchestration tests plus a schema roundtrip validation against `specs/contracts/strategy_pairs_trade_now_response.schema.json`.
  - Current B2 scope remains strategy-service-local: `open_live_trade` is reported as `false` until a bounded execution-service position source is wired in a later slice.
- Slice C `Trade Now` UI split:
  - Trade page now consumes `GET /v1/strategy/pairs/trade-now` separately from live cues and presents four distinct operator buckets:
    - `Trade Now`
    - `Watchlist`
    - `Excluded`
    - `Research Bench`
  - Research/analytics routing is now labeled `Research Bench`, while cue-backed charts and pair analytics remain on the existing research page.
  - Empty approved-universe timeframes now surface an explicit explanation instead of silently showing a blank operator surface.
- Slice D approved-universe cadence reporting:
  - Trade page now computes a bounded cadence snapshot from the current `trade-now` approved set plus `GET /v1/strategy/pairs/opportunity-history` over the last `168h`.
  - Cadence snapshot shows approved-ready rows/day, median ready duration, stored history coverage, top wait/block reasons, and top recurring approved setups for the current timeframe.
  - Cadence remains fail-closed: if no approved universe exists or history fetch fails, the UI shows an explicit unavailable explanation instead of implying frequency confidence.
- Slice E `Trade Now` hardening and observability:
  - `strategy-service` now resolves `open_live_trade` from `execution-service` open-trade state and fails the `trade-now` endpoint closed if that upstream execution state is unavailable.
  - Active candidate probation lookups for `trade-now` now batch by timeframe and pair set instead of issuing one repository query per cue.
  - Added `GET /v1/strategy/observability/trade-now` plus contract/example for `learning_challenger_bypass_suppressed_total` and pair/timeframe suppression breakdowns.
  - Added strategy env controls for the execution-state lookup:
    - `STRATEGY_EXECUTION_SERVICE_URL`
    - `STRATEGY_EXECUTION_EXCHANGE`
    - `STRATEGY_EXECUTION_ACCOUNT_ID`
- Data horizon and retention controls for `data-service` candles:
  - Configurable backfill windows by timeframe (`1m/15m/1h`) with defaults aligned to long-horizon research (`120d/540d/1095d`).
  - Configurable candle retention pruning by timeframe plus periodic prune interval.
  - Structured prune logs and operator runbook updates for horizon/retention settings.
- Hosted storage-growth controls for self-hosted Timescale:
  - Added `TRADES_RETENTION_DAYS` prune support in `data-service` for high-volume `trades`.
  - Added explicit `BACKFILL_*` and `CANDLES_RETENTION_DAYS_*` env wiring in `docker-compose.yml` so hosted operators can tune horizon/retention without code edits.
  - Added `STRATEGY_OPPORTUNITY_HISTORY_RETENTION_DAYS`, `STRATEGY_PAPER_TRADES_HISTORY_RETENTION_DAYS`, and `STRATEGY_HISTORY_PRUNE_INTERVAL_SECONDS` in `strategy-service`.
  - Added bounded-retention wiring in `docker-compose.yml` and hosted env/runbook documentation.
- Strategy research IS/OOS window contracts (Slice B):
  - Added explicit `train_bars` and `validation_bars` metadata to expectancy/replay/sweep configs and schemas.
  - Added bounded query/request support for optional train/validation windows and timeframe-based defaults.
  - Expectancy/replay/sweep now score on out-of-sample trades (validation segment) with `IS_OOS_WINDOW_APPLIED` rationale tagging.
  - Added strategy env defaults for optimizer windows:
    - `STRATEGY_OPT_TRAIN_DAYS_1M/15M/1H`
    - `STRATEGY_OPT_VALIDATE_DAYS_1M/15M/1H`
- Strategy research walk-forward scoring (Slice C):
  - Research sweep candidate ranking now uses validation-window walk-forward fold scoring.
  - Added fail-closed fold sufficiency gate with rationale code `WALK_FORWARD_INSUFFICIENT_TRADES`.
  - Added candidate `walk_forward` diagnostics in sweep response contracts/examples.
  - Added runtime controls:
    - `STRATEGY_WF_FOLDS`
    - `STRATEGY_WF_MIN_TRADES_PER_FOLD`
- Autonomous optimizer candidate lifecycle (Slices D/E/F):
  - Added candidate lifecycle persistence tables:
    - `strategy_candidate_runs`
    - `strategy_candidate_probation`
    - `strategy_candidate_actions`
  - Research sweep execution now persists top candidates and activates one challenger probation record per pair/timeframe.
  - Reoptimize cycles now advance challenger probation to `PROMOTION_READY` or `HOLD` with structured transition audit logs.
  - Added operator candidate APIs:
    - `GET /v1/strategy/pairs/candidate-inbox`
    - `POST /v1/strategy/pairs/candidate-action` (`PROMOTE|HOLD|REJECT`, confirm required)
  - Added contracts/examples:
    - `specs/contracts/strategy_pairs_candidate_inbox_response.schema.json`
    - `specs/contracts/strategy_pairs_candidate_action_request.schema.json`
    - `specs/contracts/strategy_pairs_candidate_action_response.schema.json`
    - `specs/examples/strategy_pairs_candidate_inbox_response.example.json`
    - `specs/examples/strategy_pairs_candidate_action_request.example.json`
    - `specs/examples/strategy_pairs_candidate_action_response.example.json`
  - Added Analytics candidate inbox panel with promote/hold/reject controls.
  - Added candidate probation and inbox env controls:
    - `STRATEGY_CANDIDATE_PROBATION_DAYS_1M/15M/1H`
    - `STRATEGY_CANDIDATE_PROBATION_MIN_SAMPLES`
    - `STRATEGY_CANDIDATE_PROBATION_MAX_SAMPLES`
    - `STRATEGY_CANDIDATE_PROMOTION_MIN_OBJECTIVE_DELTA`
    - `STRATEGY_CANDIDATE_INBOX_DEFAULT_LIMIT`
  - Expanded observability and runbooks for optimizer candidate lifecycle metrics and operator actions.
- Autonomous optimizer implementation roadmap and slice checklist:
  - `docs/23-autonomous-optimizer-roadmap.md`
- Strategy tuning governance and interruption recovery package:
  - `docs/22-strategy-tuning-control.md`
  - `plans/strategy_tuning_plan.json`
  - `infra/config/strategy_tuning_policy.json`
  - `docs/playbooks/strategy-tuning-runbook.md`
- Strategy tuning machine-readable reporting contract/example:
  - `specs/contracts/strategy_tuning_report.schema.json`
  - `specs/examples/strategy_tuning_report.example.json`
- Strategy tuning automation scripts:
  - `tools/scripts/strategy_tuning_report.py` (deterministic snapshot/compare/decision report)
  - `tools/scripts/strategy_tuning_apply.py` (guarded promote/revert apply with env backup and rollback on deploy failure)
- Strategy tuning script unit tests:
  - `tools/scripts/tests/test_strategy_tuning_scripts.py`
- Automated daily strategy maintenance evaluation workflow:
  - `tools/scripts/strategy_maintenance_cycle.py` (health checks, baseline/candidate evaluation, restore-original, latest report publish)
  - `scripts/install_strategy_maintenance_cron.sh` (cron install/update/remove helper)
  - `docs/playbooks/strategy-maintenance-automation-runbook.md`
- Strategy maintenance report API + UI integration:
  - `GET /v1/strategy/maintenance/latest`
  - `GET /v1/strategy/maintenance/artifact?path=...`
  - `POST /v1/strategy/maintenance/action` (manual operator-triggered `PROMOTE` / `REVERT`)
  - Analytics tab panel with downloadable maintenance artifacts
  - `specs/contracts/strategy_maintenance_latest_response.schema.json`
  - `specs/examples/strategy_maintenance_latest_response.example.json`
- Strategy maintenance one-click operator controls:
  - Analytics panel buttons for `One-Click Promote` and `One-Click Revert`
  - Human-readable action result surfaced in-panel
  - `specs/contracts/strategy_maintenance_action_response.schema.json`
  - `specs/examples/strategy_maintenance_action_response.example.json`
- One-click strategy maintenance action runtime support for hosted deployments:
  - `scripts/deploy.sh` now supports `docker compose` and `docker-compose` command variants.
  - `scripts/deploy.sh` now supports configurable health-check retries for slow-start service restarts.
  - `strategy-service` runtime in `docker-compose.yml` now provisions Docker CLI and mounts the host Docker socket for promote/revert apply actions initiated from the Analytics UI.
  - Hosted deployment runbook documents validation and security constraints for privileged maintenance actions.
- Host-side queued maintenance action execution:
  - `POST /v1/strategy/maintenance/action` now enqueues promote/revert requests instead of executing deploy inline in strategy-service.
  - Added host worker `tools/scripts/strategy_maintenance_action_worker.py` to process queued actions and execute `strategy_tuning_apply.py`.
  - Added cron/systemd installer scripts:
    - `scripts/install_strategy_maintenance_action_worker_cron.sh`
    - `scripts/install_strategy_maintenance_action_worker_systemd.sh`
  - Updated maintenance runbook and script README with queue/worker operations.
- Opportunity history persistence and downloadable reporting:
  - Added persistence table `strategy_opportunity_history` and per-tick writes from strategy reoptimize loops.
  - Added APIs:
    - `GET /v1/strategy/pairs/opportunity-history`
    - `GET /v1/strategy/pairs/opportunity-history/download`
    - `GET /v1/strategy/pairs/opportunity-history/stats`
  - Added history contract/example:
    - `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`
    - `specs/examples/strategy_pairs_opportunity_history_response.example.json`
    - `specs/contracts/strategy_pairs_opportunity_history_stats_response.schema.json`
    - `specs/examples/strategy_pairs_opportunity_history_stats_response.example.json`
- Paper-trade ledger persistence and reporting:
  - Added persistence table `strategy_paper_trades` populated from backtest marker replay (paper-only, no broker dependency).
  - Added APIs:
    - `GET /v1/strategy/pairs/paper-trades`
    - `GET /v1/strategy/pairs/paper-trades/download`
  - Added paper-trades contract/example:
    - `specs/contracts/strategy_pairs_paper_trades_response.schema.json`
    - `specs/examples/strategy_pairs_paper_trades_response.example.json`
  - Paper-trade persistence now replaces rows per `(pair_id, timeframe, exit_mode)` scope on each recompute to prevent stale historical trades from surviving across model-window changes.
  - `GET /v1/strategy/pairs/paper-trades` now returns `model_bars` so UI can disclose the active simulation window used for persisted trade generation.
  - Paper-trade realized accounting now uses a canonical trade outcome path:
    - `net_bps` is aligned to equity path delta per trade (`equity_trade_bps`) to prevent contradictory profit signals.
    - Leg contributions are hedge-ratio weighted and normalized to sum to `gross_bps`.
- Strategy research groundwork contracts and endpoints (slice A):
  - Added APIs (contract-only, fail-closed placeholders):
    - `GET /v1/strategy/pairs/expectancy`
    - `GET /v1/strategy/pairs/replay-trades`
    - `POST /v1/strategy/pairs/research-sweep`
  - Added contracts/examples:
    - `specs/contracts/strategy_pairs_expectancy_response.schema.json`
    - `specs/examples/strategy_pairs_expectancy_response.example.json`
    - `specs/contracts/strategy_pairs_replay_trades_response.schema.json`
    - `specs/examples/strategy_pairs_replay_trades_response.example.json`
    - `specs/contracts/strategy_pairs_research_sweep_response.schema.json`
    - `specs/examples/strategy_pairs_research_sweep_response.example.json`
- Strategy research endpoints (slice C) now compute deterministic outputs:
  - `GET /v1/strategy/pairs/replay-trades` returns computed replay rows (entry/exit, net bps, MAE/MFE, underwater bars, hold bars) from current backtest logic.
  - `GET /v1/strategy/pairs/expectancy` returns computed expectancy metrics (win rate, p25/p50/p75 net bps, hold/path stats, min-lot net projection).
  - Both endpoints fail closed for unsupported z-methods (`ROBUST_Z` only in this slice) and insufficient aligned candle history.
  - `POST /v1/strategy/pairs/research-sweep` now performs deterministic dry-run validation and returns `AVAILABLE`/`UNAVAILABLE` based on combination limits and z-method support.
- Strategy research sweep execution (slice E):
  - `POST /v1/strategy/pairs/research-sweep` now executes full parameter sweeps when `dry_run=false` and guardrails pass.
  - Sweep execution is fail-closed with explicit rationale codes for unsupported methods, max-combination breaches, and execution-cap breaches.
  - Response now includes execution counters (`executed_combinations`, `successful_combinations`, `failed_combinations`) and ranked optimization outputs (`best_candidate`, `top_candidates`).
  - Added bounded runtime settings:
    - `STRATEGY_RESEARCH_SWEEP_EXECUTION_CAP` (default `20000`)
    - `STRATEGY_RESEARCH_SWEEP_TOP_K` (default `10`)
- UI now provides 24h/72h/7d opportunity-history downloads (PASS/all) plus retention meter (days covered).
- Automated Daily Maintenance panel moved to dedicated `Maintenance` page in side navigation (under `Data Quality`).
- Maintenance cron installer scripts now support explicit `CRON_TZ` timezone configuration (`--timezone`).
- UI timestamp displays are now explicitly local-time formatted with timezone suffix.
- UI password gate for hosted access:
  - Added strategy-service endpoints:
    - `GET /v1/strategy/ui-auth/status`
    - `POST /v1/strategy/ui-auth/verify`
  - Web app now presents a full-screen black password screen before loading dashboard content when `STRATEGY_UI_ACCESS_PASSWORD` is configured.
  - Added `STRATEGY_UI_ACCESS_PASSWORD` to `.env.example` and hosted runbook instructions for server-side setup/rotation.
- Header metric and chart scaling refinements:
  - Added `GET /v1/strategy/market/metrics?instrument=<symbol>` as a strategy-service proxy to data-service market metrics for hosted deployments where `/data/v1/market/metrics` is not exposed by the public API gateway.
  - Web app market metric fetches now use strategy-service market metrics endpoint.
  - Header market metrics now update per instrument independently (partial failures no longer blank both legs).
  - Z-score charts now use dynamic domain scaling based on observed series values so the plotted line uses more panel space.
  - Dashboard viewport-fit improvements:
    - Content shell now scrolls internally instead of clipping lower content on shorter laptop viewports.
    - Trade/Analytics chart heights now adapt to viewport height with bounded min/max values for consistent laptop-to-4K rendering.
- Trade and Analytics UI readability pass:
  - Added y-axis labels and threshold-value labels on z-score charts.
  - Added live current z-score label on the Trade chart right-hand side (updates each data refresh) and positioned it to the right of the latest dot for readability.
  - Decluttered Analytics and Settings with progressive disclosure:
    - Diagnostics and persisted paper-trade tables now live under optional “Advanced Analytics” accordions.
    - Research controls remain fully available but are collapsed by default under “Advanced Research (Optional)”.
    - Removed redundant static “Safety Defaults” settings card; guardrails remain enforced in Trade execution controls.
  - Entry suppression at stop extremes:
    - Strategy cue generation now blocks new entries when the selected score is at or beyond the configured stop band (`AT_OR_BEYOND_STOP_BAND`).
    - Backtest/live-z marker generation now suppresses entry markers at/through stop levels so invalid stop-zone entries are not rendered.
  - Increased chart axis text size and z-score marker dot size.
  - Added persistent execution-marker overlay on the Trade z-score chart so trader action anchors remain visible across live signal recalculations.
  - Added active trade anchor summary (entry z, current z, delta z, entry timestamp) in Open spread summary.
  - Applied a larger Inter-first typography scale across topbar metrics, tables, cards, controls, and chart labels to better match Kraken Pro text hierarchy.
  - Added a compact typography mode pass reducing selected metric/table/meta text classes by 40% for tighter Kraken-like density.
  - Added USD-formatted y-axis labels for equity charts and tightened equity chart scaling for better vertical space usage.
  - Removed numeric prefixes from spread execution section titles.
  - Added `Definitions` and `Reoptimise` tabs in `How This Works`.
  - Set dark mode as the default first-load theme.
  - Reworked top-header metrics layout to remove horizontal scrolling.
  - Added PF/PI instrument-prefix fallback when fetching mark/index metrics to reduce `--` header values.
- Strategy fee override from UI settings:
  - Added `Taker Commission` input in Settings (percent format, e.g. `0.10%`).
  - Web app now threads optional `taker_fee_bps` to strategy endpoints (`cues`, `cost-gate`, `portfolio-plan`, `backtest`, `live-z`).
  - Strategy-service now applies optional `taker_fee_bps` overrides in cost-gate and cost-estimate calculations while validating bounds fail-closed.
- Configurable backtest exit behavior for analytics:
  - Added optional `exit_mode` query parameter (`mean_revert` or `opposite_extreme`) to:
    - `GET /v1/strategy/pairs/backtest`
    - `GET /v1/strategy/pairs/live-z`
  - Responses now echo `exit_mode` for auditability.
  - Settings tab now includes `Backtest Exit Mode` selector to drive analytics chart computation mode.
- Live sampled slippage gating and execution-aware quote handling:
  - `data-service` market metrics now include `bid` and `ask`.
  - Added `GET /v1/market/metrics/batch?instruments=...` for efficient quote polling.
  - Added contract/example:
    - `specs/contracts/data_market_metrics_batch_response.schema.json`
    - `specs/examples/data_market_metrics_batch_response.example.json`
  - `strategy-service` now maintains a 1s sampled slippage feed (EWMA) and blocks entry advisory gates when sampled data is warming/stale/unavailable (no heuristic fallback for entry gating).
  - Added warm-start sampled slippage persistence:
    - Persisted sampled state checkpoints (`EWMA`, funding sample, sample count, `last_sample_at`) to `STRATEGY_SAMPLED_SLIPPAGE_STATE_PATH` on a configurable interval.
    - Strategy-service now hydrates fresh checkpoints on startup (`< 2 * STRATEGY_SAMPLED_SLIPPAGE_STALE_SECS`) and marks them as bootstrapped.
    - First live-sample deviation checks can force fail-closed re-warming when checkpoint values diverge beyond `STRATEGY_SAMPLED_SLIPPAGE_BOOTSTRAP_MAX_DEVIATION_BPS`.
    - Added `SLIPPAGE_SOURCE_BOOTSTRAPPED` rationale code for checkpoint-backed advisory windows.
  - Cost-gate diagnostics now include rationale codes for sampled slippage source and feed health (`SLIPPAGE_SOURCE_SAMPLED`, `SLIPPAGE_DATA_WARMING`, `SLIPPAGE_DATA_STALE`, `SLIPPAGE_DATA_UNAVAILABLE`).
  - Header spread display in web app now uses direction-aware executable quote pricing (bid/ask/index based) instead of mark-only spread.
- Dynamic funding impact modeling for cost-gate decisions:
  - `strategy-service` now computes spread funding as directional per-event bps from live leg funding rates and hedge-ratio/index notional weights.
  - Funding impact now uses continuous hold-hours accrual across all strategy timeframes:
    - `funding_bps` = directional sampled `funding_bps_per_event` normalized by funding interval and scaled by expected hold duration in hours.
    - `funding_events` remains informational settlement-boundary metadata (`STRATEGY_FUNDING_INTERVAL_SECS`, `STRATEGY_FUNDING_PHASE_OFFSET_SECS`) and is no longer used as the primary multiplier for expected funding drag.
  - Entry advisory fails closed with `FUNDING_DATA_UNAVAILABLE` when dynamic funding samples are unavailable.
  - Added dynamic rationale codes `FUNDING_CONTINUOUS_ACCRUAL` and `FUNDING_WINDOW_NO_SETTLEMENT` for auditability on short hold windows.
  - Static funding drag remains available only when dynamic funding is disabled (`STRATEGY_DYNAMIC_FUNDING_ENABLED=false`).
  - Cost-gate diagnostics now expose `funding_model`, `funding_events`, and `funding_bps_per_event` in cues and cost-gate APIs.
  - Added configurable funding-rate input normalization mode (`STRATEGY_FUNDING_RATE_INPUT_MODE=fraction|percent|auto`, default `percent`) so strategy math and header market-metrics proxy can normalize exchange funding-rate units consistently.
  - Top-header net spread funding is now rendered as normalized `bps/hr` using explicit funding interval conversion (`funding_interval_secs`) instead of raw `% / hr` formatting.
- Kraken private-auth hardening for execution order-status lookups:
  - `execution-service` now signs the exact URL-encoded URI component (`path?query`) used on wire for private status requests.
  - Reduces risk of auth mismatch under Kraken’s encoded-URI signing enforcement updates.
- Gate signaling clarity improvements for operator UX:
  - `cost_gate.pass` is now preserved as economics-only pass/fail (expected edge minus modeled trade costs).
  - Added explicit cue diagnostics: `setup_gate` and `trade_gate` (with `blocked_by`) to separate setup constraints from economics constraints.
  - Trade/Analytics UI now reports setup, cost economics, and final trade readiness independently, reducing false “cost blocked” messaging when setup is the actual blocker.
  - Cost-gate API now includes `setup_pass`, `trade_ready`, and `trade_blocked_by` for downstream consumers.
- Entry-gate simplification and messaging cleanup:
  - Funding is now informational and no longer part of automated cost-gate pass/fail math (`net_edge_bps` now uses expected edge minus fee/slippage).
  - Missing funding samples no longer fail-close advisory gates; funding diagnostics remain visible as informational rationale codes.
  - Half-life and hedge-ratio stability are now advisory warnings rather than hard setup-entry blocks.
  - Cost gate now uses selected-variant expected edge (reliability-adjusted) rather than raw opportunity ranking score.
  - Analytics “Why blocked” copy now removes repetitive generic gate reasons and fixes hedge-ratio wording (`above preferred stability tolerance`).
- Exchange minimum-lot/tick-size alignment hardening:
  - Added shared Kraken perp trading constraints (`min_lot`, `tick_size`) and symbol normalization in `common-types`.
  - `execution-service` now validates `ENTRY`/`EXIT` quantities against exchange lot-step and minimum lot constraints fail-closed before order-intent acceptance.
  - `strategy-service` analytics/backtest/replay paths now quantize leg prices to exchange tick sizes and use exchange min-lot sizing for expectancy minimum-notional projections.
  - Added tests covering constraint lookup/normalization, execution lot-step enforcement, and min-lot-based expectancy projections.
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
- Market metrics API endpoint (`GET /v1/market/metrics?instrument=<symbol>`) backed by Kraken tickers.
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
  - Top header metrics (Mark/Index/24h/Funding/OI) now sourced from `data-service` live market metrics.
  - Trade and Analytics charts now include timestamp x-axis labels.
  - Data Quality integrity table now explicitly indicates latest-row windowing.
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
- Server-truth spread portfolio ledger slice:
  - New endpoint: `GET /v1/execution/portfolio/positions`
  - Execution intents now accept optional spread context fields:
    - `pair_id`
    - `spread_direction`
    - `spread_z`
  - Web portfolio/trade position state now reads backend ledger output instead of browser-local position storage.
  - New contract/example:
    - `specs/contracts/execution_portfolio_positions_response.schema.json`
    - `specs/examples/execution_portfolio_positions_response.example.json`
- Kraken normalization hardening for open-orders/order-status:
  - Added normalization matrix fixture:
    - `services/execution-service/tests/fixtures/kraken/normalization_matrix.json`
  - Added normalization contract/example:
    - `specs/contracts/execution_kraken_normalization_matrix.schema.json`
    - `specs/examples/execution_kraken_normalization_matrix.example.json`
  - Expanded transition handling for exchange statuses:
    - open-orders: cancel/reject/expire status mapping
    - order-status: `ENTERED_BOOK` full-fill mapping and explicit `EXPIRED` mapping
  - Added replay test coverage against normalization matrix fixture.
- End-to-end manual trade validation harness:
  - Added script: `tools/scripts/manual_trade_e2e_check.py`
  - Validates preflight + manual entry/dispatch/lifecycle/position/reconcile path.
  - Supports optional emergency stop-close validation with flat-position enforcement.
- Frontend manual flow integration coverage:
  - Added `apps/web/src/__tests__/manualTradeFlow.integration.test.tsx`
  - Verifies spread metadata submit, dispatch sequencing, and acknowledged-flow UI state.
- Observability summary package with operator alert thresholds:
  - New execution endpoint:
    - `GET /v1/execution/observability/summary`
  - New account endpoint:
    - `GET /v1/account/observability/summary`
  - New contracts/examples:
    - `specs/contracts/execution_observability_summary_response.schema.json`
    - `specs/examples/execution_observability_summary_response.example.json`
    - `specs/contracts/account_observability_summary_response.schema.json`
    - `specs/examples/account_observability_summary_response.example.json`
  - New observability SLO runbook:
    - `docs/playbooks/observability-slo-runbook.md`
- Hosted secrets lifecycle package:
  - `execution-service` live credential loading now supports file sources:
    - `KRAKEN_FUTURES_API_KEY_FILE`
    - `KRAKEN_FUTURES_API_SECRET_FILE`
  - Added hosted-mode env template:
    - `infra/env/hosted-mode.env.example`
  - Added secrets rotation policy config:
    - `infra/config/hosted_secrets_rotation_policy.json`
  - Added secrets lifecycle audit script:
    - `tools/scripts/secrets_lifecycle_audit.py`
  - Added runbook:
    - `docs/playbooks/secrets-lifecycle-runbook.md`
  - Added contract/example:
    - `specs/contracts/hosted_secrets_rotation_policy.schema.json`
    - `specs/examples/hosted_secrets_rotation_policy.example.json`
- Fail-closed operator recovery package:
  - Added readiness checker:
    - `tools/scripts/fail_closed_readiness_check.py`
  - Added fail-closed recovery runbook:
    - `docs/playbooks/fail-closed-recovery-runbook.md`
  - Expanded incident and execution runbooks with deterministic recovery command gates.

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
- Web operator console simplified for operator-first flow:
  - Side navigation now focuses on `Trade`, `Analytics`, and `Settings` only.
  - Removed inactive runtime surfaces from the main app flow (`How This Works`, `Markets`, `Portfolio`, `Data Quality`, `Maintenance`).
  - Removed session-only API credential inputs from Settings (keys are backend-managed).
  - Trade entry arming now depends on operator confirmation + execution gate health only (no fake local stop prerequisite).
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
- Strategy cost gate now prioritizes realized recent paper-trade profitability:
  - Pass/block is derived from recent persisted `strategy_paper_trades` outcomes (median/sum net bps),
    instead of modeled expected-edge arithmetic.
  - Funding rationale codes were removed from gate blocking reasons (funding remains reference data only).
  - Non-ready gate state now surfaces as `WAIT` (replacing `UNAVAILABLE` in setup/cost/trade gate flow).
- Execution-service now exposes dispatch-mode status via
  `GET /v1/execution/dispatch-mode` to let UI distinguish `FAIL_CLOSED`,
  `SIMULATE_ACK`, and `LIVE_KRAKEN` runtime behavior.
- Manual controls now require explicit operator confirmation only when execution
  dispatch mode is `LIVE_KRAKEN`; `SIMULATE_ACK` allows unarmed entry/exit intents
  (operator ID still required for auditability).
- Trade page Spread Execution panel enhancements:
  - Added global kill-switch on/off slide toggle (wired to `POST /v1/execution/kill-switch`).
  - SIM mode now enables entry/add/reduce actions without live arming when backend mode is `SIMULATE_ACK`.
  - Strategy conditions now surface as warnings in the panel instead of disabling action buttons.
  - Action hierarchy now uses green long-entry and red short-entry controls.
- SIM demo mode now bypasses execution safety gate blocking end-to-end when
  `EXECUTION_DISPATCH_MODE=simulate_ack`:
  - `GET /v1/execution/decision` returns `ALLOWED` for UI leg checks.
  - order-intent evaluation ignores kill-switch, integrity, reconcile, and risk gates in SIM mode.
  - live modes (`FAIL_CLOSED`, `LIVE_KRAKEN`) retain existing fail-closed gate behavior.
- Trade panel now enforces executable lot-step sizing before submit:
  - spread size is quantized down to a pair-valid executable step for ENTRY/EXIT in UI,
    preventing server-side lot-step rejects (for example `PF_XRPUSD` with integer lots).
  - preview quantities now reflect actual executable submit size.

### Fixed
- Trade-now historical quality now casts win/stop-rate aggregates to `DOUBLE PRECISION`,
  preventing Postgres numeric deserialization panics when building the endpoint response.
- Trade and Analytics now render champion projection failures as `BLOCKED`
  instead of displaying an untrustworthy stored champion variant.
- Hosted compose wiring for execution dispatch mode:
  - `docker-compose.yml` now passes `EXECUTION_DISPATCH_MODE` into `execution-service`
    so SIM/LIVE mode selection is applied at runtime (instead of always defaulting to `FAIL_CLOSED`).
- Removed accidental duplicate spec/example files with `* 2.json` suffix.
- Strategy marker generation no longer emits same-bar `entry` + `stop` overlaps in live z-score/backtest series,
  preventing visual stop markers without a preceding visible entry.
- Execution lifecycle transition matrix now permits watchdog-driven expiration from
  `ACKNOWLEDGED` and `PARTIALLY_FILLED` (`-> EXPIRED`).
- Integrity false-negative gap detection when request bounds were unaligned to timeframe steps
  (could report `INCOMPLETE` with non-empty candle windows).
- Kraken funding ingestion now normalizes ticker `fundingRate` as a **relative rate**
  (`relativeFundingRate` when available, otherwise `fundingRate/indexPrice`) to prevent
  instrument-price-scaled funding distortions in strategy cost-gate calculations.
- Strategy cues now force cost-gate `pass=false` when `actionable=false`, preventing
  Gate/Edge PASS presentation on non-actionable rows (including champion-drift blocked cues).
- Strategy reoptimize transition accounting diagnostics:
  - `POST /v1/strategy/pairs/reoptimize` now returns additive `initialize_decisions` and `unchanged_decisions` counters alongside existing champion promotion/lock totals.
  - Strategy reoptimize observability now logs all four champion decision outcomes and warns if selected rows are written without any accounted transition result.
- Strategy cue selection-state diagnostics and champion-consistent drift projection:
  - `GET /v1/strategy/pairs/cues` now includes optional `cue.selection_state` metadata so consumers can compare the evaluated-best variant against the stored champion explicitly.
  - Drift-state cue responses no longer rewrite only `selected_variant` and `opportunity_score`; they now project a champion-consistent cue or fail closed with explicit rationale.
  - Trade and Analytics UI surfaces now read selection-state diagnostics instead of treating `cue.selected_variant` as sole ground truth.
- Strategy selected-signal persistence now preserves non-legacy provenance against same-variant
  legacy-source regression without freezing retuned parameters, preventing `trade-now` rows from
  regressing into `LEGACY_ROW_FALLBACK` during normal evaluation cycles.
- Trade-now now attaches an internal 168h paper-trade quality snapshot per pair/timeframe for
  later frequency-gating slices without changing the public response contract.
- Trade-now can now surface a bounded `LEARNING_ELIGIBLE_OVERRIDE` approval path for fresh
  learning-positive, non-selected rows when recent 168h paper-trade quality clears timeframe-aware
  thresholds.
- Trade-now now lets fresh `LEARNING_SELECTION` rows bypass a short rolling cost-gate false
  negative when the same 168h completed-trade quality checks remain strong, marks that path via
  explicit rationale provenance, and preserves the raw live `net_edge_bps` display.
- Trade-now observability now tracks surfaced `LEARNING_ELIGIBLE_OVERRIDE` rows and applied
  `LEARNING_SELECTION_COST_OVERRIDE_APPLIED` rows alongside challenger-bypass suppressions.
