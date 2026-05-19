# Agent State (Living)

> **This file is the second mandatory read for every agent, after `AGENTS.md`.**
> See `AGENTS.md` §8 for the topology, work-allocation rules, and hydration sequence.

---

## Pin

| Field | Value |
|---|---|
| Last updated (UTC) | 2026-05-19 |
| Updated by | codex/local |
| Repo HEAD pin (committed) | `df1690c8832359b316ce3206d16694b2e4c749fc` |
| Pin branch | `main` |
| Sprint base branch | `main` |
| Pin notes | Post-Slice E curation. The pin is the PR #200 squash merge on main at df1690c8832359b316ce3206d16694b2e4c749fc. This curation records Slices D-E as done and intentionally leaves host verification and production enablement operator-only. |
| Origin | `https://github.com/apexpark/cryptopairs.git` |
| Working-tree state | Reoptimise runner Slices A-E are merged on `main`. Host-runtime verification, scheduler enablement, and production canary evidence remain operator-only and are not claimed by agents. |

If the pin above is not reachable from `HEAD` via fast-forward, this file is stale; if `HEAD` is ahead of the pin, see §"Pin Convention".

---

## Currently In Flight

### Sprint: Champion-Selection Integrity (docs/26 + docs/27)

Status snapshot of the four slices defined in `docs/26-champion-selection-integrity-fix-spec.md`:

| Slice | Status | Owner | Notes |
|---|---|---|---|
| Slice A — Separate evaluation from champion presentation | **Committed on sprint base** | local | Verified: schema validation passed; full `cargo test --workspace` passed in pre-push hook (covers `cue_for_pairs_response_*` × 5 + `evaluate_pair_honors_preferred_variant_override`); tsc passed. |
| Slice B — Make transition accounting complete | **Committed on sprint base** | local | Verified: full `cargo test --workspace` passed in pre-push hook (covers `selection_transition_counts_*` × 3 + `reoptimize_response_serializes_transition_counts_at_top_level` + `update_persist_summary_for_transition_records_all_summary_counts`); clippy clean; reoptimize schema validation passed (0.2.0). |
| Slice C — Remove incumbent bias in host runtime | **Reconciled on main; host deployed; observation active** | operator/local | PR #177 squash-merged the reviewed GitHub lineage onto `main` at `21286c6`, and operator deployed that exact commit to host. `/metrics` now exposes the projection/transition counters. Keep `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` through the observation window. |
| Slice D — Recanonicalize legacy rows | **Runtime guard deployed; observation active** | operator/local | Operator recanonicalized the 12 1m host rows from `LEGACY_ROW_FALLBACK` to `RECANONICALIZED_LEGACY_ROW`. Deployed `main` treats that source as repair-only and fail-closed (`RECANONICALIZED_LEGACY_ROW_ACTIVE`) until an explicit approved non-repair source replaces it. |

### Immediate Safety Action (still active)

Per `docs/26` §"Immediate Safety Action":
- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` MUST stay set.
- Live `ENTRY` / `EXIT` for this strategy runtime MUST stay disabled.
- Cues are research-visible but NOT execution-trustworthy.

Do not relax these during the 72-hour observation window.

### Project: Bounded Async Reoptimization Runner

Canonical design sources:

- `docs/playbooks/reoptimise-runner-agent-brief.md`
- `docs/proposals/reoptimise-background-runner-redesign.md`
- `specs/contracts/strategy_reoptimize_run_*`
- `specs/examples/strategy_reoptimize_run_*`
- `docs/proposals/reoptimise-observability-runbook-plan.md`
- `docs/proposals/reoptimise-api-script-migration-plan.md`

Project objective: replace the unsafe extremes of disabled manual-only
reoptimization and unbounded background work with a durable, bounded,
observable, cancelable, fail-closed async reoptimization system.

Hard invariants for every slice:

- Default disabled; no production scheduler enablement without explicit
  operator approval.
- Existing `POST /v1/strategy/pairs/reoptimize` remains synchronous and
  compatible until a separately approved versioned migration.
- Unknown, stale, invalid, expired, canceled, degraded, or contradictory run
  state maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
- Lease loss, budget exhaustion, artifact failure, and missing telemetry fail
  closed.
- No automatic `PROMOTE`, no automatic `REVERT`, and no live `ENTRY` / `EXIT`
  enablement.
- No automatic graduation of repair-only provenance such as
  `RECANONICALIZED_LEGACY_ROW`.
- Host verification remains operator-only; agents must not claim SSH/runtime
  evidence unless the operator provides it.
- Heavy workers stay fail-closed by default until leases, budgets,
  single-flight, observability, and canary evidence are implemented and
  approved.

Slice tracker:

| Slice | Status | Owner | Notes |
|---|---|---|---|
| Slice A — async contracts and examples | **Committed on main** | remote/local | PR #192 / commit c94740e added enqueue, status, cancel, and artifact-manifest contracts and examples without changing runtime behavior. |
| Slice B — durable run state and lease state machine | **Committed on main** | remote/local | PR #193 squash-merged at 3751ee56f059138e9a11c7238e0e68bc4bea7a71 from head 52fb6f8. Local verification passed: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace`. Explicit local Postgres-backed reoptimize tests were invoked with `--nocapture` and skipped per harness policy because `STRATEGY_TEST_DATABASE_URL` was unset; GitHub CI rust checks were green on the PR head. Scope stayed limited to canonical schema/init path, isolated strategy-service persistence/state-machine helpers, focused unit/Postgres tests, and `CHANGELOG.md`. No routes, scheduler loop, UI, scripts, or synchronous reoptimize behavior changed. |
| Slice C — bounded runner loop | **Committed on main** | remote/local | PR #195 squash-merged at d38229bd7c2b7b8d174e064a9aa9bae4fd48f458 from reviewed head 78a118e. The implementation remains disabled by default and adds the bounded runner loop on top of Slice B state: durable single-flight enqueue/lease, conservative budgets, checkpointed pair/timeframe work, heartbeats, progress/summary writes, cancellation checks, and fail-closed terminal completion. Local verification passed: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`, explicit `cargo test -p strategy-service --test repository_integration -- --nocapture`, and `git diff --check`; local Postgres-backed test bodies skipped per harness because `STRATEGY_TEST_DATABASE_URL` was unset. GitHub CI was green on PR #195. No public API routes, UI, maintenance scripts, existing synchronous `/v1/strategy/pairs/reoptimize` behavior, automatic promotion, repair-provenance graduation, or host verification claims were added. |
| Slice D — async API and script migration | **Committed on main** | remote/local | PR #197 / commit 880da1112a66e4ce58fb24cf354be0c82f2df173 landed the read/enqueue-only async run endpoint subset. PR #198 / commit a115ab785479cf54929cd59aee8f3b787f46a993 landed opt-in script modes (`sync`, `async`, `latest-successful`, `skip`) for report/maintenance scripts while preserving synchronous defaults and baseline skip behavior. Async/latest evidence uses bounded polling and fails closed to `HOLD` on timeout, invalid/unknown status, stale or incompatible latest evidence, missing artifacts, critical errors, fail-closed reasons, or unavailable cancellation. The existing synchronous `/v1/strategy/pairs/reoptimize` route remains unchanged; UI changes, production scheduler defaults, automatic promotion/revert, repair-provenance graduation, artifact download routes, and mutating cancellation remain deferred. |
| Slice E — observability and runbooks | **Committed on main** | remote/local | PR #200 / commit df1690c8832359b316ce3206d16694b2e4c749fc adds bounded async reoptimization metrics, structured runner/API logs, and `docs/playbooks/async-reoptimization-runner-runbook.md` for the merged Slice C/D subset: lifecycle, active runs, enqueue outcomes, lease acquire/heartbeat/loss, budget exhaustion, pair/timeframe progress, cancellation observation/completion, fail-closed reasons, missing/unknown telemetry, terminal recommendations, status inspection, disable/rollback, stuck lease recovery, budget exhaustion response, artifact evidence, and Slice F readiness. Artifact read/write metrics remain deferred because this base still writes empty manifests and has no artifact read/download route. No production scheduler enablement, UI edits, scripts, automatic promotion/revert, repair-provenance graduation, or host verification claims are included. |
| Slice F — production canary | **Not started; operator-only** | operator | Requires explicit operator approval after C-E. Must capture host identity, flags, budgets, metrics, status progression, artifacts, CPU/hot-path baseline comparison, live ENTRY/EXIT disabled evidence, and no automatic promotion. |

Open operator decisions before production enablement:

1. Initial runtime budgets: run wall-clock, timeframe wall-clock, pair counts,
   pair concurrency, DB batch size, artifact bytes, cooldown, lease TTL, and
   heartbeat interval.
2. First canary timeframe and success thresholds.
3. Cancellation authority and auth/audit boundary.
4. Artifact root, retention period, and download/access policy.
5. Canonical request/config fingerprint fields.
6. Script migration defaults: stay sync, async opt-in, latest-successful, or
   skip for each maintenance path.
7. Long-term fate of `POST /v1/strategy/pairs/reoptimize`: compatibility
   route, admin-only route, async wrapper, or deprecated route.

Next safe sequence:

1. Do not start Slice F production canary or scheduler enablement until the
   operator explicitly authorizes host work.
2. Keep the existing synchronous `/v1/strategy/pairs/reoptimize`
   compatibility route unchanged unless a separate versioned migration is
   approved.
3. Treat public mutating cancellation, artifact download/read surfaces,
   request/config fingerprint graduation, and production scheduler enablement
   as separate follow-up decisions unless explicitly assigned.
4. If implementation needs files
   outside the slice boundary, stop and escalate per `AGENTS.md` §7.

---

## Done This Sprint

Source of truth for shipped behavior is `CHANGELOG.md` `## Unreleased` section. Highlights for this sprint:

- **Committed (`039c82c`)**: Multi-agent operating model — `AGENTS.md` §8, `docs/AGENT_STATE.md` (this file), `docs/26-...`, `docs/27-...`, and the corresponding `CHANGELOG.md` entry.
- **Committed (`a87b8ae`)**: Bootstrap playbook — `docs/playbooks/remote-agent-bootstrap.md` (new, 187 lines) is the operational procedure for AGENTS.md §8.4: bootstrap prompt, self-preflight, claim protocol via the open-follow-ups table, verification sequence (calls `scripts/check-rust-ci.sh` so it stays in sync with the pre-push hook), branch/commit/PR templates, design-proposal-first PR variant, blocking protocol, local review checklist. `AGENTS.md` §8.4 updated with a one-line pointer (now five-step hydration sequence).
- **Committed (`2148693`)**: Pin convention — relax §8.4 from strict HEAD equality to fast-forward reachability. Pin records the "as of" anchor; lags HEAD by trivial commits; soft NOTICE on lag with intervening commit list. Resolves a chicken-and-egg in the previous strict rule.
- **Committed (`a2fa027`)**: Cargo-blocked remote-agent workaround. Remote agents (Codex, Claude) cannot install `cargo` in their environments. Two-tier Rust verification both running `scripts/check-rust-ci.sh`: primary = local agent on demand against the remote agent's branch (sub-second with incremental cache), backstop = GitHub Actions on every push to `codex/**` or `claude/**` (`ci.yml` extended to include `claude/**`). Playbook §3 split into 3a (agent-runnable: tsc, jsonschema, json syntax) and 3b (cargo-dependent: delegated). Playbook §4 PR template adds explicit "Rust check status" field. Playbook §7 review checklist requires both local-agent and CI green for any Rust-touching PR. The multi-agent operating model is **fully active** as of this commit — Codex and Claude can hydrate, claim follow-ups, and ship Rust-touching PRs without local cargo.
- **Committed (`b195447`)**: Hosted storage-growth and data-horizon retention sprint — `STRATEGY_OPPORTUNITY_HISTORY_RETENTION_DAYS`, `STRATEGY_PAPER_TRADES_HISTORY_RETENTION_DAYS`, `STRATEGY_HISTORY_PRUNE_INTERVAL_SECONDS`, `TRADES_RETENTION_DAYS`, configurable backfill windows by timeframe, candle retention pruning, structured prune logs, hosted runbook updates. Files: `services/strategy-service/src/main.rs`, `services/data-service/src/config.rs`, `services/data-service/src/main.rs`, `services/data-service/src/repository.rs`, `services/data-service/src/worker.rs`, `docker-compose.yml`, `infra/env/*.env.example`, `.env.example`, `docs/playbooks/hosted-deployment-runbook.md`, `CHANGELOG.md`.
- **Committed (`2771479`)**: Champion-selection Slice A — `cue.selection_state` contract added with strict enums for `source` and `validation_state` (5 enum values incl. `CHAMPION_PROJECTED_BLOCKED` and `CHAMPION_PROJECTION_FAILED`); cue endpoint now projects champion-consistent cues via `evaluate_pair_for_timeframe`’s second-pass champion projection or fails closed with explicit rationale; UI surfaces (Trade tab + Analytics) consume `selection_state` via `cueDisplayedVariant` / `cueBestVariant` instead of `cue.selected_variant`. Files: `services/strategy-service/src/lib.rs`, `services/strategy-service/src/main.rs`, `specs/contracts/strategy_pairs_cues_response.schema.json`, `specs/examples/strategy_pairs_cues_response.example.json`, `apps/web/src/types.ts`, `apps/web/src/App.tsx`, `CHANGELOG.md`. Tests: `evaluate_pair_honors_preferred_variant_override` (lib), `cue_for_pairs_response_*` × 5 (bin).
- **Committed (`e60e634`)**: Champion-selection Slice B — `SelectionTransitionCounts` now records all four `ChampionDecision` outcomes (`INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, `PROMOTE_CHALLENGER`); `record_evaluation` increments via extracted `update_persist_summary_for_transition`; `emit_selection_transition_observability` logs all four counts and warns on `selected_rows_written > 0` with zero accounted decisions. Reoptimize response schema bumped to 0.2.0 with additive `initialize_decisions` / `unchanged_decisions` (kept optional in `required` for backward compatibility but always populated). Drift table writes remain scoped to `KEEP_CHAMPION` / `PROMOTE_CHALLENGER` only — `INITIALIZE` / `UNCHANGED` are metric-only. Files: `services/strategy-service/src/main.rs`, `specs/contracts/strategy_pairs_reoptimize_response.schema.json`, `specs/examples/strategy_pairs_reoptimize_response.example.json`, `CHANGELOG.md`. Tests: `selection_transition_counts_*` × 3, `update_persist_summary_for_transition_records_all_summary_counts`, `reoptimize_response_serializes_transition_counts_at_top_level`.
- **Committed (`ff38663`)**: B6 design proposal — `docs/proposals/B6-pg-test-harness.md` lands the design-proposal-first recommendation for a Postgres-backed `strategy-service` integration harness: env-gated `STRATEGY_TEST_DATABASE_URL`, GitHub Actions `services:` Postgres, schema-per-test isolation via `search_path`, and production-DDL reuse via `StrategyRepository::ensure_schema`. The proposal rejects SQL-string mocks and a `StrategyRepository` trait seam for B6, and defines the acceptance criteria for the later implementation PR.
- **Committed (`79893c6`)**: B3 + S8 defensive clarifications — reoptimize schema now documents that `initialize_decisions` / `unchanged_decisions` stay optional in `required` for backward compatibility while the server always populates them, and the unreachable fifth `build_cue_selection_state(...)` match arm is now `unreachable!`. Files: `specs/contracts/strategy_pairs_reoptimize_response.schema.json`, `services/strategy-service/src/main.rs`, `docs/AGENT_STATE.md`.
- **Committed (`7a572df`)**: Champion-selection B6 implementation (PR #163) — `services/strategy-service/tests/repository_integration.rs` adds schema-per-test Postgres isolation via `STRATEGY_TEST_DATABASE_URL` with `strategy_test_{unix_seconds}_{process_id}_{atomic_counter:03}` naming and no `uuid` dep, production DDL reuse via `StrategyRepository::ensure_schema`, panic-safe schema teardown via hand-rolled Drop, and the asymmetric §10 #2 design (skip locally, fail when `CI=true` and unset). Tests: `record_evaluation_writes_selected_and_drift_rows` (resolves B4 boundary-verified) and `upsert_selected_signal_on_conflict_keeps_latest_row`. `.github/workflows/ci.yml` runs the harness against `timescale/timescaledb:2.16.1-pg16`. Operator-applied cargo-fmt fixup at `d3b7b9b` before merge (rustfmt drift between operator Mac and CI; surfaced because remote Codex cannot install cargo — another instance of the dirty-drag-along class R2-impl will close).
- **Committed (`f87e291`)**: R2 design proposal (PR #162) — `docs/proposals/R2-pre-push-staged-only.md` recommends Option A (stash-then-pop in `.githooks/pre-push` with EXIT/INT/TERM trap) with a Slice B escalation gate. Acceptance criteria for the implementation PR are baked in §5; six MUST-cover test scenarios are listed in §9. Operator decisions on the four §10 questions captured in the new R2-impl follow-up row below.
- **Committed (`d17103`)**: R2 pre-push staged-tree implementation (PR #164) — `.githooks/pre-push` now autostashes unstaged tracked changes and untracked files before invoking `scripts/check-rust-ci.sh`, restores via EXIT/INT/TERM trap, and preserves `SKIP_RUST_CHECKS=1` as the first escape hatch. `scripts/test-pre-push.sh` covers the seven required hook scenarios in temp git repos.
- **Committed (`3a44100`)**: Slice C planning proposal (PR #166) — `docs/proposals/SLICE-C-host-lineage-and-implementation.md` anchors the host-lineage repair plan in the captured `rc/live-trial` evidence, recommends cherry-picking host commits into a reviewable branch, and gates implementation on operator import/rollout decisions.
- **Committed (`4ac38b5`)**: R1 Rust toolchain pin design proposal (PR #167) — `docs/proposals/R1-rust-toolchain-pin.md` recommends pinning the workspace to Rust channel `1.95` via `rust-toolchain.toml`, matching CI's toolchain input, and leaving hooks/scripts unchanged.
- **Committed (`a1c536d`)**: R3 pre-push escape-hatch rotation design proposal (PR #168) — `docs/proposals/R3-skip-checks-rotation.md` recommends replacing `SKIP_RUST_CHECKS=1` with `RUST_PREFLIGHT_OVERRIDE=<reason>` and hard-rejecting the legacy boolean bypass after operator approval.
- **Committed (`74ef7c6`)**: R1 Rust toolchain pin implementation (PR #169) — root `rust-toolchain.toml` pins channel `1.95` with `rustfmt` and `clippy`, `Cargo.toml` records `rust-version = "1.95"`, CI requests the same toolchain and logs active versions, and bootstrap/testing docs describe the pinned local/CI behavior.
- **Committed (`aad7445`)**: S4+B5 selection metrics implementation (PR #170) — strategy-service `/metrics` now exposes `pairs_cue_projection_total{outcome}`, `strategy_selection_transition_total{decision,timeframe}`, and `strategy_selection_rows_updated_without_transition_total{timeframe}` with bounded labels, plus observability docs/runbook updates.
- **Committed (`0d28534`)**: X1 selection-state audit docs (PR #171) — `docs/27` live cue mismatch audit now reads `cue.selection_state.best_variant`, `stored_champion_variant`, `source`, and `validation_state`, while preserving `missing_selection_state_count` for hosts not yet serving the Slice A cue contract. X2 audit context found no migrate-now operator-facing consumers.
- **Committed (`f874f7c`)**: R3 preflight override implementation (PR #172) — `.githooks/pre-push` rejects legacy `SKIP_RUST_CHECKS=1`, accepts reason-bearing `RUST_PREFLIGHT_OVERRIDE=<reason>`, rejects boolean-ish override values, preserves staged-tree/autostash coverage, and updates bootstrap docs plus changelog.
- **Committed (`94c109e`)**: S6 projection-failed UI fix (PR #173) — Trade and Analytics render `CHAMPION_PROJECTION_FAILED` cues as `BLOCKED` instead of displaying an untrustworthy stored champion variant, with focused frontend coverage for failed, projected, projected-blocked, no-stored-champion, and legacy cue paths.
- **Committed (`38ccc01`)**: Slice D recanonicalization design proposal (PR #174) — `docs/proposals/SLICE-D-recanonicalize-legacy-rows.md` recommends a dry-run-first, operator-confirmed maintenance action for legacy selected rows, gated on Slice C neutral-selection observation evidence, with row-level eligibility reasons, repair-only provenance, pre-image rollback artifacts, additive/versioned contracts, bounded metrics/logs, and operator-only host verification.
- **Committed (`2d66495`)**: X3 reporting diagnostics design proposal (PR #175) — `docs/proposals/X3-reporting-alignment-diagnostics.md` recommends optional additive `selection_diagnostics` for backtest, live-z, paper-trades, and opportunity-history surfaces after Slice C observation, while preserving legacy `selected_variant` compatibility and deferring implementation/schema changes to a later PR.
- **Committed (`21286c6`)**: Live-trial lineage reconciliation (PR #177) — `main` now contains the reviewed selection/Trade Now lineage, the host-deployed historical-quality cast hotfix, `/metrics` projection/transition observability, and the fail-closed `RECANONICALIZED_LEGACY_ROW_ACTIVE` Trade Now provenance block. Rust, Python, contracts, docs, and Vercel checks were green before merge; operator deployed the exact commit to host and verified safety gates stayed fail-closed.
- **Committed (`d1a3eb9`)**: Reoptimise runner design/contract stack — PR #188 safety base, PR #189 bounded async runner proposal, PR #192 async reoptimization contracts/examples, PR #190 observability/runbook plan, and PR #191 API/script migration plan landed on `main` before Slice B implementation. Heavy workers remained fail-closed by default and host verification remained operator-only.
- **Committed (`3751ee5`)**: Reoptimise runner Slice B (PR #193) — disabled-by-default durable async reoptimization run-state persistence scaffolding, `strategy_reoptimize_runs` lease/single-flight state, fail-closed expiry/cancellation helpers, artifact-manifest path containment, focused unit coverage, and Postgres-backed repository tests. Local verification passed fmt, clippy, and full workspace tests; local Postgres DB was unavailable, so explicit Postgres-backed tests skipped per harness policy while GitHub CI rust checks were green.
- **Committed (`d38229b`)**: Reoptimise runner Slice C (PR #195) — disabled-by-default bounded async runner loop on Slice B durable state, with lease-gated mutation work, conservative budgets, checkpointed pair/timeframe processing, heartbeats, cancellation checks, fail-closed budget/cancellation terminal behavior, and focused unit/repository coverage. Local verification passed fmt, clippy, full workspace tests, explicit repository integration invocation, and diff check; local Postgres DB was unavailable so fixture bodies skipped per harness policy while GitHub CI was green. No public API routes, scheduler production enablement, UI, maintenance scripts, synchronous reoptimize behavior change, automatic promotion, repair-provenance graduation, or host verification claim landed.
- **Committed (`880da11`)**: Reoptimise runner Slice D endpoint subset (PR #197) — strategy-service exposes read/enqueue-only async run APIs (`POST /v1/strategy/reoptimize/runs`, `GET /v1/strategy/reoptimize/runs/latest`, `GET /v1/strategy/reoptimize/runs/{run_id}`) on top of Slice C durable state. Enqueue fails closed while the disabled-by-default async worker is off, compatible active runs can be attached, and the existing synchronous `/v1/strategy/pairs/reoptimize` route remains unchanged. Cancellation, artifact download routes, script migration, UI changes, scheduler production enablement, automatic promotion/revert, repair-provenance graduation, and host verification were deferred.
- **Committed (`a115ab7`)**: Reoptimise runner Slice D script migration (PR #198) — tuning report and maintenance cycle scripts now support explicit `sync`, `async`, `latest-successful`, and `skip` reoptimization modes while preserving synchronous/default compatibility. Async/latest evidence uses bounded polling and fails closed to `HOLD` on unknown, stale, schema-invalid, timed-out, degraded, canceled, or artifact-missing state. No scheduler production enablement, automatic promotion/revert, repair-provenance graduation, artifact download route, mutating cancellation route, UI change, or host verification claim landed.
- **Committed (`df1690c`)**: Reoptimise runner Slice E observability and runbooks (PR #200) — strategy-service exposes bounded async reoptimization metrics/logs for lifecycle, active runs, enqueue, leases, budgets, progress, cancellation, fail-closed, missing telemetry, unknown status, terminal timeframe status, and terminal recommendations. `docs/playbooks/async-reoptimization-runner-runbook.md` covers status inspection, disable/rollback, cancellation handling, stuck lease recovery, budget exhaustion, missing telemetry, artifact evidence, and Slice F readiness. Artifact read/write metrics remain deferred until artifact write/read/download surfaces exist; production canary remains operator-only.

---

## Blocked / Waiting On

### B-Host-Lineage (deployed; 72-hour observation active)

Operator deployed `origin/main` commit `21286c6b2cf3bce5d951e621ca341ba73d175103` to host on **2026-05-10**. Host tree was clean after deploy, branch was `main`, `/metrics` returned HTTP 200 and exposed `pairs_cue_projection_total`, `strategy_selection_transition_total`, and `strategy_selection_rows_updated_without_transition_total`. Safety remained fail-closed: `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`, `EXECUTION_DISPATCH_MODE=fail_closed`, `OPERATOR_PROMOTION` unset, open trade count zero, and no live ENTRY/EXIT activation evidence.

T0 Trade Now verification showed `trade_now=0`, `watchlist=0`, `excluded=48`; all 12 `RECANONICALIZED_LEGACY_ROW` rows were excluded with `decision_reason_code=PROVENANCE_POLICY_BLOCKED`, `blocked_reason_code=RECANONICALIZED_LEGACY_ROW_ACTIVE`, and `legacy_fallback_active=false`.

T+24 observation on **2026-05-10T22:49Z** showed host still clean at `21286c6b2cf3bce5d951e621ca341ba73d175103`, `/metrics` still healthy, selection accounting gap counters at zero, and Trade Now at `trade_now=0`, `watchlist=8-9`, `excluded=39`. Current blockers are learning/provenance/live-gate conditions, not deployment or metrics. Continue read-only T+48 and T+72 capture; do not enable live ENTRY/EXIT, set `OPERATOR_PROMOTION`, mutate selected rows, or expand the approved universe during the window.

Neither the local nor any remote agent has SSH access to `cryptopairs`. Host verification remains operator-only.

Prior 2026-05-05 repository identity raw output:

```text
4dd118242414d38ad33ae50bb433d4988d5276da
rc/live-trial
 M CHANGELOG.md
 M services/strategy-service/src/main.rs
```

Selection row state raw output:

```text
PF_DOGEUSD__PF_PEPEUSD|15m|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 02:02:43.476+00
PF_ETHUSD__PF_ADAUSD|15m|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 02:02:43.187+00
PF_ETHUSD__PF_SOLUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:43.188+00
PF_ETHUSD__PF_XRPUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:43.185+00
PF_SOLUSD__PF_AVAXUSD|15m|FUNDING_ADJUSTED|AUTO_CHAMPION|2026-05-05 02:02:43.208+00
PF_SUIUSD__PF_ARBUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 00:45:18.683+00
PF_TAOUSD__PF_HYPEUSD|15m|ROBUST_Z|AUTO_CHAMPION|2026-05-05 00:45:18.336+00
PF_XBTUSD__PF_ADAUSD|15m|ROBUST_Z|AUTO_CHAMPION|2026-05-05 02:02:42.896+00
PF_XBTUSD__PF_AVAXUSD|15m|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 02:02:43.206+00
PF_XBTUSD__PF_BNBUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:42.923+00
PF_XBTUSD__PF_DOGEUSD|15m|ROBUST_Z|AUTO_CHAMPION|2026-05-05 02:02:43.316+00
PF_XBTUSD__PF_ETHUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:42.888+00
PF_XBTUSD__PF_LINKUSD|15m|ROBUST_Z|AUTO_CHAMPION|2026-05-05 02:02:42.868+00
PF_XBTUSD__PF_SOLUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:42.917+00
PF_XBTUSD__PF_XRPUSD|15m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 02:02:42.85+00
PF_XRPUSD__PF_ADAUSD|15m|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 02:02:43.452+00
PF_DOGEUSD__PF_PEPEUSD|1h|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:14:40.159+00
PF_ETHUSD__PF_ADAUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.379+00
PF_ETHUSD__PF_SOLUSD|1h|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:14:40.543+00
PF_ETHUSD__PF_XRPUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.562+00
PF_SOLUSD__PF_AVAXUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.376+00
PF_SUIUSD__PF_ARBUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.171+00
PF_TAOUSD__PF_HYPEUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.124+00
PF_XBTUSD__PF_ADAUSD|1h|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 01:14:40.232+00
PF_XBTUSD__PF_AVAXUSD|1h|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:14:40.393+00
PF_XBTUSD__PF_BNBUSD|1h|FUNDING_ADJUSTED|AUTO_CHAMPION|2026-05-05 01:14:40.366+00
PF_XBTUSD__PF_DOGEUSD|1h|VOL_NORMALIZED|AUTO_CHAMPION|2026-05-05 01:14:40.727+00
PF_XBTUSD__PF_ETHUSD|1h|ROBUST_Z|AUTO_CHAMPION|2026-05-05 01:14:40.193+00
PF_XBTUSD__PF_LINKUSD|1h|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:14:40.149+00
PF_XBTUSD__PF_SOLUSD|1h|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:14:40.383+00
PF_XBTUSD__PF_XRPUSD|1h|FUNDING_ADJUSTED|AUTO_CHAMPION|2026-05-05 01:14:40.181+00
PF_XRPUSD__PF_ADAUSD|1h|FUNDING_ADJUSTED|AUTO_CHAMPION|2026-05-05 01:14:40.136+00
PF_DOGEUSD__PF_PEPEUSD|1m|ROBUST_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.84+00
PF_ETHUSD__PF_ADAUSD|1m|VOL_NORMALIZED|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.557+00
PF_ETHUSD__PF_SOLUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.495+00
PF_ETHUSD__PF_XRPUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.067+00
PF_SOLUSD__PF_AVAXUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.903+00
PF_SUIUSD__PF_ARBUSD|1m|ROBUST_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.064+00
PF_TAOUSD__PF_HYPEUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.578+00
PF_XBTUSD__PF_ADAUSD|1m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:31:41.064+00
PF_XBTUSD__PF_AVAXUSD|1m|ROBUST_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.067+00
PF_XBTUSD__PF_BNBUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.066+00
PF_XBTUSD__PF_DOGEUSD|1m|COINTEGRATION_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.057+00
PF_XBTUSD__PF_ETHUSD|1m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:31:41.07+00
PF_XBTUSD__PF_LINKUSD|1m|ROBUST_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.069+00
PF_XBTUSD__PF_SOLUSD|1m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:31:41.06+00
PF_XBTUSD__PF_XRPUSD|1m|COINTEGRATION_Z|AUTO_CHAMPION|2026-05-05 01:31:41.059+00
PF_XRPUSD__PF_ADAUSD|1m|ROBUST_Z|LEGACY_ROW_FALLBACK|2026-05-05 01:31:41.578+00
```

Drift / candidate activity raw output:

```text
15m|KEEP_CHAMPION|11322
15m|PROMOTE_CHALLENGER|727
1h|KEEP_CHAMPION|8622
1h|PROMOTE_CHALLENGER|592
1m|KEEP_CHAMPION|12524
1m|PROMOTE_CHALLENGER|1852
---
0
---
candidate_runs|0
candidate_probation|0
candidate_actions|0
```

Live cue mismatch audit raw output:

```text
{
  "timeframe": "1m",
  "total": 16,
  "mismatch_count": 11,
  "mismatches": [
    {
      "pair_id": "PF_XBTUSD__PF_ETHUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 2.9973810210473424,
      "best_variant": "ROBUST_Z",
      "best_score": 3.945275450280178
    },
    {
      "pair_id": "PF_XBTUSD__PF_DOGEUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 2.8044498223546994,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": 2.8890585784432834
    },
    {
      "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "ROBUST_Z",
      "selected_score": 2.692481070143141,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 5.966961521264695
    },
    {
      "pair_id": "PF_XBTUSD__PF_SOLUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 1.2310755929938346,
      "best_variant": "ROBUST_Z",
      "best_score": 3.0656141198852156
    },
    {
      "pair_id": "PF_XBTUSD__PF_ADAUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 0.7887768695146198,
      "best_variant": "ROBUST_Z",
      "best_score": 1.3544562114973744
    },
    {
      "pair_id": "PF_XBTUSD__PF_BNBUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 0.5841257517511478,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": 0.7938848447734203
    },
    {
      "pair_id": "PF_ETHUSD__PF_ADAUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "VOL_NORMALIZED",
      "selected_score": 0.556415516754834,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": 1.1137833466017824
    },
    {
      "pair_id": "PF_XBTUSD__PF_AVAXUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "ROBUST_Z",
      "selected_score": 0.46425762963464196,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 1.741144257938258
    },
    {
      "pair_id": "PF_ETHUSD__PF_XRPUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 0.3933515619575974,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": 0.6565611025695358
    },
    {
      "pair_id": "PF_XBTUSD__PF_LINKUSD",
      "source": "LEGACY_ROW_FALLBACK",
      "selected_variant": "ROBUST_Z",
      "selected_score": -0.1832169929260295,
      "best_variant": "COINTEGRATION_Z",
      "best_score": -0.049904650337419414
    },
    {
      "pair_id": "PF_XBTUSD__PF_XRPUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": -0.19288838369027989,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": 0.583733013653348
    }
  ]
}
{
  "timeframe": "15m",
  "total": 16,
  "mismatch_count": 12,
  "mismatches": [
    {
      "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "VOL_NORMALIZED",
      "selected_score": 39.240050869755414,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 44.847284820344335
    },
    {
      "pair_id": "PF_SUIUSD__PF_ARBUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 24.72779549240902,
      "best_variant": "ROBUST_Z",
      "best_score": 27.657996560702742
    },
    {
      "pair_id": "PF_TAOUSD__PF_HYPEUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "ROBUST_Z",
      "selected_score": 12.53513925784539,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 27.756779613893663
    },
    {
      "pair_id": "PF_XBTUSD__PF_SOLUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 9.964609946448713,
      "best_variant": "ROBUST_Z",
      "best_score": 11.485567404206074
    },
    {
      "pair_id": "PF_XBTUSD__PF_XRPUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 8.07557132600605,
      "best_variant": "ROBUST_Z",
      "best_score": 9.094231373195827
    },
    {
      "pair_id": "PF_SOLUSD__PF_AVAXUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "FUNDING_ADJUSTED",
      "selected_score": 7.72069353491928,
      "best_variant": "VOL_NORMALIZED",
      "best_score": 10.39955783623868
    },
    {
      "pair_id": "PF_ETHUSD__PF_XRPUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 7.62937133700745,
      "best_variant": "ROBUST_Z",
      "best_score": 12.984572873280346
    },
    {
      "pair_id": "PF_ETHUSD__PF_ADAUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "VOL_NORMALIZED",
      "selected_score": 5.470465574407826,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 11.722435346867863
    },
    {
      "pair_id": "PF_XRPUSD__PF_ADAUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "VOL_NORMALIZED",
      "selected_score": 4.099002823153223,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 4.613011003561543
    },
    {
      "pair_id": "PF_XBTUSD__PF_DOGEUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "ROBUST_Z",
      "selected_score": -4.262370414445777,
      "best_variant": "VOL_NORMALIZED",
      "best_score": -0.8243151780851755
    },
    {
      "pair_id": "PF_XBTUSD__PF_AVAXUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "VOL_NORMALIZED",
      "selected_score": -4.779639410685998,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": -3.2124035849748274
    },
    {
      "pair_id": "PF_XBTUSD__PF_BNBUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": -4.951421730584576,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": -4.867002214919264
    }
  ]
}
{
  "timeframe": "1h",
  "total": 16,
  "mismatch_count": 7,
  "mismatches": [
    {
      "pair_id": "PF_XBTUSD__PF_SOLUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 88.80013716909424,
      "best_variant": "VOL_NORMALIZED",
      "best_score": 98.40145523840727
    },
    {
      "pair_id": "PF_TAOUSD__PF_HYPEUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "ROBUST_Z",
      "selected_score": 59.79615100284696,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 110.76971302291517
    },
    {
      "pair_id": "PF_ETHUSD__PF_SOLUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 40.499901440284894,
      "best_variant": "ROBUST_Z",
      "best_score": 47.14577594706576
    },
    {
      "pair_id": "PF_XBTUSD__PF_XRPUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "FUNDING_ADJUSTED",
      "selected_score": 17.200921773173985,
      "best_variant": "COINTEGRATION_Z",
      "best_score": 20.029628955125986
    },
    {
      "pair_id": "PF_XBTUSD__PF_ETHUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "ROBUST_Z",
      "selected_score": 5.866493372248825,
      "best_variant": "VOL_NORMALIZED",
      "best_score": 14.457189846248943
    },
    {
      "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "COINTEGRATION_Z",
      "selected_score": 3.9180870383898254,
      "best_variant": "ROBUST_Z",
      "best_score": 6.648008101543441
    },
    {
      "pair_id": "PF_ETHUSD__PF_ADAUSD",
      "source": "AUTO_CHAMPION",
      "selected_variant": "ROBUST_Z",
      "selected_score": -29.5248541590155,
      "best_variant": "FUNDING_ADJUSTED",
      "best_score": -22.487867785718784
    }
  ]
}
```

---

## Open Follow-ups

Follow-ups carried forward from prior reviews. Ordered by source review then severity. Pickable by any remote agent unless marked `local-only`.

### From Slice A independent review

| ID | Severity | Description | Status |
|---|---|---|---|
| S4 | medium | Add `pairs_cue_projection_total{outcome}` counter; double evaluation cost on drift pairs needs a metric and a runbook note. | **resolved by PR #170 (`aad7445`)** — strategy-service `/metrics` now renders `pairs_cue_projection_total{outcome}` with bounded outcomes `NOT_REQUIRED`, `PROJECTED`, `PROJECTED_BLOCKED`, and `PROJECTION_FAILED`; operator docs/runbook describe projection-failure handling. |
| S6 | low | UI’s `cueDisplayedVariant` shows champion name in `CHAMPION_PROJECTION_FAILED` state. Consider rendering `--` or `BLOCKED` instead. (`apps/web/src/App.tsx:206-211`) | **resolved by PR #173 (`94c109e`)** — `cueDisplayedVariant` now renders `BLOCKED` for `CHAMPION_PROJECTION_FAILED`, with focused frontend coverage for failed vs projected display paths. |
| S7 | low | Reoptimize / write path does not yet emit `cue.selection_state`. Bridge in Slice B+ work or accept as deferred. | partially addressed by Slice B (counts now emitted in response, but `selection_state` shape itself still cue-only) |
| S8 | low | Unreachable fifth match arm at `services/strategy-service/src/main.rs:4676-4681`. Replace with `unreachable!` or document. | **resolved by PR #160 (`79893c6`)** — the impossible fifth arm in `build_cue_selection_state(...)` is now `unreachable!`, making the invariant explicit and fail-closed. |

### From Slice B independent review

| ID | Severity | Description | Status |
|---|---|---|---|
| B1 | low | Add `accumulate(other)` unit test on `SelectionTransitionCounts`. | **resolved by Slice B (`e60e634`)** — `selection_transition_counts_accumulate_sums_each_field` landed with Slice B and passed in pre-push `cargo test --workspace`. |
| B2 | low | Add serde round-trip test asserting `initialize_decisions` / `unchanged_decisions` / `champion_promotions` / `champion_locks` appear at the top level of `ReoptimizeResponse` (locks the `serde(flatten)` wire shape). | **resolved by Slice B (`e60e634`)** — `reoptimize_response_serializes_transition_counts_at_top_level` landed with Slice B and passed in pre-push `cargo test --workspace`. |
| B3 | low | One-line schema comment explaining `initialize_decisions` / `unchanged_decisions` are kept optional in `required` for backward compatibility but always populated by the server. | **resolved by PR #160 (`79893c6`)** — the response schema now carries the compatibility note as a `$comment`, matching the 0.2.0 wire contract. |
| B4 | medium-low | Integration-shaped test that drives `record_evaluation` and asserts `summary.transition_counts` matches an expected `ChampionDecision` distribution. Was the highest-value Slice B follow-up. | **resolved (boundary-verified) by PR #163 (`7a572df`)** — `record_evaluation_writes_selected_and_drift_rows` drives the real `StrategyRepository::record_evaluation` persistence boundary for `INITIALIZE`, `UNCHANGED`, `PROMOTE_CHALLENGER`, and `KEEP_CHAMPION`, asserting both `summary.transition_counts` and the resulting `strategy_selected_signal` / `strategy_champion_drift_events` rows. |
| B5 | low | Materialize the per-decision counts as actual Prometheus-style metrics (`strategy_selection_transition_total{decision,timeframe}` and `strategy_selection_rows_updated_without_transition_total{timeframe}`) rather than relying on log lines for alerting. Spec named these in `docs/26` §Observability. | **resolved by PR #170 (`aad7445`)** — strategy-service `/metrics` now renders bounded transition counters by `decision,timeframe` and selected-row accounting-gap counters by `timeframe` while preserving existing structured logs. |
| B6 | medium | Stand up a Postgres-backed repository integration harness for `strategy-service`. Design proposal merged at `ff38663` (#161). | **resolved by PR #163 (`7a572df`)** — implementation follows the §10 binding decisions: `STRATEGY_TEST_DATABASE_URL`, skip locally but fail when `CI=true` and unset, schema names formatted as `strategy_test_{unix_seconds}_{process_id}_{atomic_counter:03}` without `uuid`, and both `record_evaluation_writes_selected_and_drift_rows` plus `upsert_selected_signal_on_conflict_keeps_latest_row` ship in `services/strategy-service/tests/repository_integration.rs`. |

### From Slice C planning

| ID | Severity | Description | Status |
|---|---|---|---|
| Slice-C-impl | **HIGH** | Import the host `rc/live-trial` lineage into a reviewable local branch, then implement neutral champion selection so stored champion config is comparison input only, not challenger preselection input. | **blocked on operator import/decisions** — design proposal PR #166 (`3a44100`) recommends a cherry-picked host import branch and feature-flagged neutral selection canary. Operator must choose import path, dirty-host-state handling, rollout path, observation window/success thresholds, and host verification owner before implementation PR review. |

### Cross-cutting

| ID | Severity | Description | Status |
|---|---|---|---|
| R1 | medium | Pin rustfmt + clippy version via `rust-toolchain.toml` so operator Mac, CI, and remote-agent environments converge on one Rust toolchain. The operator's Mac currently runs a clippy older than 1.95.0 (CI's stable); GitHub Actions enforces lints the operator's pre-push hook misses. Surfaced when local Codex's clean-worktree review of rebased PR #161 caught a `clippy::unnecessary_sort_by` failure local clippy didn't emit. Recommended Design-proposal-first PR — the channel choice (specific patch vs minor floating vs `stable`) is a small architectural decision. | **resolved by PR #167 (`4ac38b5`) and PR #169 (`74ef7c6`)** — design selected Rust channel `1.95`; implementation added `rust-toolchain.toml`, `Cargo.toml` `rust-version = "1.95"`, CI `toolchain: "1.95"` plus active-toolchain logging, and bootstrap/testing docs plus `CHANGELOG.md` updates. |
| R2 | **HIGH** | Pre-push hook (`.githooks/pre-push` → `scripts/check-rust-ci.sh`) tests operator's working tree, not the staged/committed state. Caught masking three CI failures on origin in 24h: missing `retention_cutoff_ts` import (resolved at `05bca71`), `clippy::unnecessary_sort_by` in `execution-service` and `strategy-service` (resolved at `a82e8f0`). Each time pre-push reported green while origin was broken. **Promote to HIGH** — recurrence rate makes it the bug-of-the-week. Fix candidates: (a) modify `.githooks/pre-push` to `git stash --keep-index --include-untracked` before invoking `scripts/check-rust-ci.sh` and restore on EXIT trap, (b) add a separate `scripts/check-rust-ci-staged.sh` invoked by the hook that operates on a stashed checkout, (c) document as known limitation and rely on CI as canonical. (a) is the smallest diff. Recommended Design-proposal-first PR from a remote agent **as the next claimable item after this commit lands** — block all other work on this slipping further. | **resolved by PR #162 (design proposal merged at `f87e291`)** — Option A recommended (stash-then-pop in `.githooks/pre-push`). Implementation resolved by the R2-impl follow-up row below. |
| R2-impl | **HIGH** | Implement Option A from the merged R2 design proposal (`f87e291`, `docs/proposals/R2-pre-push-staged-only.md`). Modify `.githooks/pre-push` to `git stash --keep-index --include-untracked --quiet --message "pre-push autostash"` before invoking `scripts/check-rust-ci.sh`, restore on EXIT/INT/TERM trap, guard with a clean-tree check (no-op if working tree matches index), preserve `SKIP_RUST_CHECKS=1` early-return. Operator decisions binding for this PR (per R2 §10): (1) Option A as Slice A (do NOT pre-build Option B). (2) Test plan ships as runnable `scripts/test-pre-push.sh` covering the six §9 scenarios plus an "untracked file present" expansion of scenario 3 (gap noted in §7 review). (3) Scope to `.githooks/pre-push` only — no other hooks need this pattern (`ls .githooks/` shows pre-push as the only hook). (4) `SKIP_RUST_CHECKS` rotation deferred to R3 below. Implementation effort per R2 §6: ~75-135 LOC. Operator-side verification only (CI does not run pre-push hooks). | **resolved by PR #164 (`d17103`)** — `.githooks/pre-push` autostashes dirty worktree-only state before invoking `scripts/check-rust-ci.sh`; `scripts/test-pre-push.sh` passed all seven required scenarios. |
| R3 | low-medium | Rotate the pre-push escape hatch from `SKIP_RUST_CHECKS=1` to a less-permissive interface (e.g. `RUST_PREFLIGHT_OVERRIDE=<reason-string>` requiring an explicit reason argument), so casual bypass is less attractive once R2-impl removes the most common reason to bypass (slow-on-dirty-tree pre-push). Out of scope for R2-impl per the binding decisions. | **resolved at design layer by PR #168 (`a1c536d`)** — proposal recommends Option A (`RUST_PREFLIGHT_OVERRIDE=<reason-string>`) with hard reject for legacy `SKIP_RUST_CHECKS=1`; implementation tracked by R3-impl below. |
| R3-impl | low-medium | Implement the merged R3 proposal: replace the `SKIP_RUST_CHECKS=1` early return in `.githooks/pre-push`, extend `scripts/test-pre-push.sh`, update remote-agent bootstrap docs, and record the operator-tooling changelog entry. | **resolved by PR #172 (`f874f7c`)** — hard rejects `SKIP_RUST_CHECKS=1`; accepts reason-bearing `RUST_PREFLIGHT_OVERRIDE=<reason>`; rejects exact boolean-ish override values `1`, `true`, `TRUE`, `yes`, `YES`; prints supplied reasons exactly with docs warning not to include secrets; keeps sentinel-file override future-only. |
| X1 | low | Audit script in `docs/27` §"Live Cue Mismatch Audit" still reads `cue.selected_variant` and `cue.selected_signal_config.source`. Update to use `cue.selection_state` once Slice A is on the host. | **resolved by PR #171 (`0d28534`)** — audit command now reads `cue.selection_state.best_variant`, `cue.selection_state.stored_champion_variant`, `cue.selection_state.source`, and `cue.selection_state.validation_state`, with `missing_selection_state_count` surfacing hosts not yet serving the Slice A cue contract. |
| X2 | low | Operator-facing reads of `cue.selected_variant` in any other surface (Trade and Analytics now updated, but check everywhere) should migrate to `selection_state.best_variant` / `stored_champion_variant` per the spec. | **audited in post-PR #171/#172/#173 curation (`94c109e` base)** — no migrate-now operator-facing surfaces found: Trade and Analytics use `cueDisplayedVariant` / `cueBestVariant`; legacy `selected_variant` remains in contracts, examples, service internals, tests, and historical docs for compatibility. Keep legacy contract compatibility for now; post-Slice-C reporting alignment is tracked by X3. |
| X3 | low | After Slice C lands and legacy-row behavior is observed, align reporting/diagnostic surfaces that still expose only legacy `selected_variant` (backtest, live-z, paper-trades, opportunity-history) so operators can distinguish evaluated-best vs stored-champion presentation without breaking existing contracts. | **design landed by PR #175 (`2d66495`); implementation still deferred** — later work should add optional/additive `selection_diagnostics` to backtest, live-z, paper-trades, and opportunity-history only after Slice C host/runtime behavior is implemented and operator-captured observation evidence exists. Do not remove or redefine legacy `selected_variant`. |

---

## Next Recommended Move

Pickable items, in priority order:

1. **Operator-only: reoptimise runner Slice F production canary** — only after explicit operator approval; host verification remains operator-only.
2. **Operator/local agent: continue any remaining Champion-Selection observation capture** — preserve fail-closed runtime settings and compare Trade Now buckets, blocked reasons, opportunity history, paper trades, and drift events against prior captures.
3. **Remote/UI agent: Trade Now observation UI** — improve the web UI for the current observation window using existing Trade Now and observability contracts; do not add controls that mutate runtime state.
4. **Remote/local agent: async reoptimization hardening follow-ups** — if approved, handle deferred mutating cancellation auth/audit, artifact write/read/download surfaces, request/config fingerprint graduation, or scheduler/canary refinements as separate slices without making legacy or repair-only provenance trade-eligible.
8. **Remote/local agent: X3 implementation** — only after reconciled deployment is observed; implement PR #175's optional/additive reporting diagnostics while preserving legacy `selected_variant`.
9. **Remote/local agent: blocker-specific strategy follow-up** — only after T+72, target the blocker shown by evidence (learning hold/not eligible, live setup/cost gates, or approved-universe policy) rather than weakening Trade Now safety gates.

---

## Update Protocol

Update this file whenever any of the following happens:

- A slice or follow-up moves between Not Started → In Flight → Done.
- A blocker is introduced or cleared.
- A new follow-up is opened by a review.
- The committed `HEAD` advances meaningfully (re-pin).
- Operating mode for any role changes (e.g. SSH access becomes available).

Curation owner: **local agent** (per `AGENTS.md` §8.3). Remote agents propose deltas in their PRs; the local agent commits the merged state.

When updating, preserve the section order above and bump the “Last updated” date in §Pin.

### Legacy PR Protocol

PRs opened before committed state `039c82c` (when the multi-agent operating model landed) may pass the Rust gate but still fail playbook §7 because they target the wrong base, carry overly broad scope, or omit an `AGENT_STATE.md` delta.

When that happens, the local agent posts a review comment summarizing the §7 violations and waits for operator direction per PR. Acceptable resolutions:

1. Close — legacy work that is stale or superseded.
2. Mark as draft + comment — work to revisit after the current sprint completes. Branch is treated as legacy; new feature branches must not fork from it.
3. Rebase + retarget + scope-split — rescue active legacy work into focused PRs targeting the current sprint base.
4. Explicit grandfather — rare; for time-sensitive ops or security fixes that genuinely cannot wait. Operator approval required.

The local agent does NOT auto-merge a legacy PR even if it passes the Rust gate.

### Pin Convention

The pin SHA in §Pin is the "as of" anchor for the state this file describes. It records the commit at which the operator (or curating agent) last reviewed and updated this file. It is **not** required to equal literal `HEAD`.

Why not literal HEAD: every commit advances HEAD. If the rule were "pin must equal HEAD," then:

1. Every trivial commit (test fix, comment, schema note) would force a re-pin commit.
2. The re-pin commit itself advances HEAD past its own pin → chicken-and-egg.
3. The first remote agent to pull after any commit would fail the strict-equality preflight check.

Instead:

- **When a commit changes state** described in this file (slice flip, follow-up resolved, new blocker, new commit on the active sprint), the operator updates §Pin in the same commit. Conventionally the pin records the commit *immediately preceding* this commit (since you can't reference your own SHA). After the commit lands, the pin lags by exactly 1.
- **When a commit does not change state**, the pin is left alone. Lag grows by 1.
- The pin is intentionally informational + an integrity anchor, not a literal HEAD mirror.

**Hard requirement enforced by playbook §1 preflight**: the pin SHA must be **reachable from HEAD** via fast-forward (`git merge-base --is-ancestor <pin> HEAD`). Anything else (rewritten history, orphan branch, pin from a different lineage) is a hard failure.

**Soft check**: if HEAD has advanced past the pin, the playbook prints a `NOTICE` listing the intervening commits and asks the agent to skim them for unreflected scope changes before proceeding. This is the practical "is AGENT_STATE.md still accurate?" gate.

**Formatting rule (machine-readable)**: the §Pin table's `Repo HEAD pin (committed)` row contains **exactly one** backticked SHA — the canonical pin. Any reference to other SHAs (previous pins, parent commits, etc.) goes in a separate `Pin notes` row in plain text without backticks. The playbook §1 regex extracts the first backticked SHA on the pin row defensively (`head -1`), but keeping the row to a single SHA avoids surprise.
