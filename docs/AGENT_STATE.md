# Agent State (Living)

> **This file is the second mandatory read for every agent, after `AGENTS.md`.**
> See `AGENTS.md` §8 for the topology, work-allocation rules, and hydration sequence.

---

## Pin

| Field | Value |
|---|---|
| Last updated (UTC) | 2026-07-16 |
| Updated by | claude |
| Repo HEAD pin (committed) | `ecc9cbde3d95d04a2ae53de9e87e01174a5c5cbe` |
| Pin branch | `main` |
| Sprint base branch | `main` |
| Pin notes | Pin is `origin/main` (PR #253, OP-44 role swap) as merged into the B2-b feature branch during this conflict repair; it is a parent of the merge commit and therefore reachable from `HEAD`. PRs #251 (B2-a) and #253 (OP-44 swap) are both on `main`. AUTO-2 remains constrained to the paper-autopilot sequence: static paper trial, shadow dynamic champion/challenger allowlist, governed dynamic allowlist, dynamic paper trial, then live-design gate only. OP-45 sets the approved queue (see §"Next Recommended Move"). Future coding slices must pass the Slice Loop Check before implementation. |
| Origin | `https://github.com/apexpark/cryptopairs.git` |
| Working-tree state | **B2-b (PR #252) conflict-repaired against `main`** — merged `origin/main` (`ecc9cbd`, PR #253/OP-44) into `claude/b2b-selector-view-capture`, resolving the append-only decisions register, `AGENT_STATE.md`, and `CHANGELOG.md` conflicts (both sides preserved), and appended OP-45. B2-b remains Claude-authored / Codex-reviewed under OP-44's transition clause; the repair push voids prior review verdicts and requires a fresh exact-SHA Codex review before merge. No service code, order intents, dispatches, dynamic allowlist control, or live `ENTRY` / `EXIT` enablement is in flight. No host action, deploy, or capture was performed by this session. |

If the pin above is not reachable from `HEAD` via fast-forward, this file is stale; if `HEAD` is ahead of the pin, see §"Pin Convention".

---

## Currently In Flight

### Active Sequence: Main Baseline And 1m Paper-Autopilot Governance

| Slice | Status | Owner | Notes |
|---|---|---|---|
| BASE-1 - Promote Hetzner runtime baseline to `main` | **Merged** | local | PR #229 merged at f22c26f. `origin/main` tree matched `origin/cherry-picked-from-rc-live-trial` after merge, preserving the data-service Postgres-backed health check and the current production runtime tree. |
| STATE-1 - Curate agent state for `main` baseline | **Merged** | local | PR #230 flipped the sprint base to `main`, recorded PR #229 as the production baseline reconciliation, and cleared stale guidance that pointed new work at `cherry-picked-from-rc-live-trial`. |
| AUTO-1 - 1m autopilot observe-only design proposal | **Merged** | codex | PR #230 landed `docs/proposals/AUTO-1-1m-autopilot-observe-only.md`. Scope remains observation, decision logging, and safety/readiness design. It must not create order intents, dispatch orders, alter live `ENTRY` / `EXIT`, or weaken execution-service gating. |
| AUTO-1A/B - Observe-only contract and sidecar | **Merged** | codex | PR #231 merged at `c1e031d`. It added the `autopilot_observe_record` schema/example, a disabled-by-default Python sidecar under `tools/scripts/autopilot_observe.py`, and focused tests for replay/persisted dedupe, fail-closed health/kill-switch/dispatch/open-trades/malformed-source behavior, quality-gate blocking, 1m-only enforcement, generated-record schema validation, and no execution order-intent URL use. |
| AUTO-1C/D - Attribution report and observe-only evidence runbook | **Merged** | codex | PR #233 landed at `94b15b2`. It added the offline attribution report, observe-only runbook, report schema/example, and tests. No runtime service behavior or execution path changes were included. |
| HOST-1 - Hetzner repo checkout alignment | **Operator reported complete** | operator | Operator-provided Hetzner output showed `/opt/cryptopairs` fast-forwarded to `94b15b2`, data/strategy/execution health probes passed, dispatch mode remained `SIMULATE_ACK`, kill switch was inactive, and `AUTOPILOT_OBSERVE_ENABLED=false python3 tools/scripts/autopilot_observe.py --once` reported disabled-by-default behavior. |
| AUTO-2 - 1m paper-autopilot governance sequence | **Merged** | codex | PR #234 merged at `d5b7ebe`. It records the required progression: focused static paper trial, shadow dynamic champion/challenger allowlist, governed dynamic allowlist, dynamic paper trial, then live-automation design gate only. Champion/challenger output remains advisory until the governed dynamic allowlist slice is complete. |
| GOV-LOOP - Slice Loop Check governance | **Merged** | codex | PR #235 merged at `b5baca4`. It added the pre-slice anti-loop check to the Apex harness workflow, prompt pack, remote-agent bootstrap, local review checklist, and PR template so future coding slices must prove new input, state transition, concrete value, non-repetition, and stop/defer boundaries before implementation. Test-only slices are explicitly covered. |
| AUTO-2A - Focused static paper trial design | **Merged** | codex | PR #237 merged at `98dd6f3`. Design proposal defines disabled-by-default static `1m` paper-only lifecycle, duplicate/open-position/cooldown controls, fixed holding-window exit on the next available paper outcome/mark, future paper contracts, and explicit no-execution-service-POST boundaries. |
| AUTO-2A - Contracts and static paper ledger | **Merged** | codex | PR #238 landed at `daca062`. First implementation slice added paper decision/position contracts, examples, disabled-by-default `tools/scripts/autopilot_paper.py`, and focused tests for static allowlist, non-`1m`, stale/malformed/future input, invalid hold-window config, open-position conflict, cooldown, fixed hold-window exit, mark-unavailable deferral, persisted duplicate suppression, generated schema validation, and no execution-service order-intent/dispatch path. No host runbook/report, hosted loop, service behavior, dynamic allowlist control, or live execution change was included. |
| AUTO-2A - Paper report and hosted runbook | **Merged** | codex | PR #240 landed at `7e7e38d`. It added the paper report contract/example/tooling plus hosted run, monitor, stop, and evidence-capture commands. Static allowlist only; no service behavior, dynamic allowlist control, or live execution change was included. |
| AUTO-2A - Paper observe-record compatibility fix | **Merged** | codex | PR #241 landed at `5f21375`. It fixed the paper ledger so real observe-only records with minute-bucketed observe keys and nanosecond `source_generated_at` values can open paper positions while preserving stale/future candidate blocking. |
| AUTO-2A - Direction-level static paper gating | **Merged** | codex | PR #242 landed at `a47f52e`. It added direction-aware static allowlist support for AUTO-2A paper-only trials using `pair_id:selected_variant:direction` entries while preserving legacy pair/variant allowlists. It updates paper reports/runbook evidence for allowlist mode and prepares operator-only 72h direction-gated trial commands. No service behavior, dynamic allowlist control, execution-service POST path, or live execution change is included. |
| AUTO-2A - Operator paper evidence | **Operator reported complete** | operator | Operator-provided Hetzner evidence for run `20260628T061640Z` showed 83/83 closed paper positions, 57 profitable, +288.9911 realized net bps, and no open positions. `PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z` both directions and `PF_XBTUSD__PF_BNBUSD:COINTEGRATION_Z:LONG_SPREAD` were positive; `PF_TAOUSD__PF_HYPEUSD:COINTEGRATION_Z:SHORT_SPREAD` was negative due to a -118.0464 bps tail loss. Exit-lag analysis showed the edge survived outside long-lag exits but requires caveating. |
| AUTO-2B - Shadow dynamic allowlist | **Merged** | codex+claude | This branch adds the `autopilot_shadow_allowlist_snapshot` contract/example, advisory `tools/scripts/autopilot_shadow_allowlist.py`, focused tests, proposal, Superpowers plan, and runbook. Output is shadow-only and must not control `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`, paper entries, live entries, execution order intents, dispatch, or exchange calls. |
| AUTO-2A - Second 72h direction-gated paper window | **Operator running on host** | operator | Run `20260713T060641Z` started 2026-07-13T06:17Z after host reboot + fresh observe capture (`20260713T060526Z`); same 4-leg allowlist for churn comparability; loop-resilience deviation authorized (stale tick skips, logged). Ends ~2026-07-16T06:07Z; then second shadow snapshot with `--previous-snapshot-json` starts the churn series. |
| AUTO-2B.2 - Full-universe selector-view design | **Merged** | claude | PR #249 at `c1eaf79` (Operator-approved per AUTO-2 §6). OP-35 gave the implementation go with §8 answers: all three buckets, 300s cadence, disk estimate before capture. |
| AUTO-2B.2 - B2-a selector-view contracts | **Merged** | claude | PR #251 at `2147635` (Codex CLEAN at `c49ad67`, 4 cycles). observe_record v2 (entry|selector-view oneOf) and snapshot v2 (optional selector_view/universe/per-stream-churn, version-gated) are binding. |
| AUTO-2B.2 - B2-b selector-view capture | **In flight (conflict-repaired; prior-role transition)** | claude (author) / codex (reviewer) | PR #252 on branch `claude/b2b-selector-view-capture`. `autopilot_observe.py` gains disabled-by-default `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW` (all three cue buckets → v2 selector-view rows, no outcome/eligibility path), a `MAX_RUNTIME_SECONDS` bound, a per-tick row count, and a runbook section requiring a read-only disk estimate before capture. Disabled-default behaviour is byte-identical (tested). Capture is all-or-nothing: any degraded/stale source, missing/non-list bucket, or untranscribable candidate refuses the whole tick (no partial universe reaches B2-c); a selector-view loop refuses to start without a positive `MAX_RUNTIME_SECONDS`; the runbook carries an exact selector-view stop procedure. Each captured tick is led by a `selector_view_tick` manifest (`recorded_rows` + per-bucket counts) so an empty-but-captured universe is distinguishable from a missed tick and a truncated tail from a smaller universe; refused ticks emit no manifest. SIGTERM/SIGINT finish the in-flight tick before exit, and a read-only `--verify-selector-view-pid` probe confirms a PID is the selector-view run — not the identically-invoked narrow run — before the operator signals it. **Transitional ownership:** grandfathered under OP-44's transition clause / OP-45(a) — completes under the prior Claude-author / Codex-review roles even though OP-44 has merged. This branch merged `origin/main` (`ecc9cbd`, PR #253), resolved the decisions/AGENT_STATE/CHANGELOG conflicts, repaired the four findings from the Codex review at `93efb4d`, and repaired the three round-6 findings at `4d14612` (empty-tick representation, exact process identity + graceful stop, and clean-tree verification totals — the prior "180" was measured in a tree carrying an untracked duplicate test module; the clean-tree total is 169 pre-repair, 177 after). Each repair push voids every earlier review verdict, so a fresh exact-SHA Codex review is required before merge. Tier 3 flow. |
| GOV-ROLESWAP - Swap Claude/Codex roles (OP-44) | **Merged** | claude | PR #253 merged at `ecc9cbd` on `main`. Codex → Lead Coder + Operator Interface; Claude → Independent Reviewer, operative for the first slice started after the merge; B2-b PR #252 completes under the prior roles per the transition clause (OP-45(a)). Added `CODEX.md`; updated ai_workflow/git-github/CLAUDE role sections, codex_prompt_pack note, CODEOWNERS, project.yaml. |
| GOV-SCAFFOLD-1 - Install dual-agent governance scaffold v0 (`.agentic/**`) | **Merged** | claude | PR #245 squash-merged at `2516fc5` (Codex CLEAN at `7c0efe2` after three exact-SHA review cycles; Operator-executed merge, recorded in `.agentic/registers/decisions.md`). Branch `claude/agentic-scaffold-v0` builds on `codex/agentic-loop-harness-adapter` (build-on, not supersede; Operator decision 2026-07-12). Adds constitution/permissions/evidence/git/context policies, seeded decisions/risks/assumptions/capabilities/agent-runs registers, nine work-order/review/handoff templates, and intake/dispatch/review/blocked playbooks. Docs-only; grants no new authority — the 2026-07-12 merge tiers are recorded as adopted but non-operative until `docs/ops/ai_workflow.md` is amended (Slice 2); protected-path list recorded in `.agentic/registers/decisions.md`. Tier 3 flow: Codex exact-SHA review + Operator authorization required. Follow-on slices: dual-agent workflow manual (Slice 2), `CLAUDE.md` Autonomy Doctrine mapped to the AUTO ladder (Slice 3), CODEOWNERS/PR-template expansion (Slice 4). |
| GOV-SCAFFOLD-2 - Make merge-authority tiers operative | **Merged** | claude | PR #246 squash-merged at `7041b41` (Codex CLEAN at `053da11` after three exact-SHA cycles; Operator-executed merge; authorization recorded in the decisions register). Tiers 1–2 delegated merge operative from that merge under the hardened standing-delegation conditions. |
| GOV-SCAFFOLD-3 - CLAUDE.md Autonomy Doctrine | **Merged** | claude | PR #247 squash-merged at `b409849` (Codex CLEAN at `a5132ae` after four exact-SHA cycles; Operator-executed merge; authorization recorded in the decisions register). CLAUDE.md is the Claude session entry point: operator-invoked/evidence-gated phase, graduation on the full AUTO-2 §3 sequence with AUTO-2D unskippable, AUTO-3 never grantable, graduation rows valid only when Tier 3-merged citing an Operator instruction. |
| GOV-SCAFFOLD-4 - CODEOWNERS canonicalization | **Merged** | claude | PR #248 squash-merged at `4bce8e5` (Codex CLEAN at `51baba1` after three exact-SHA cycles; Operator-executed merge; authorization recorded in the decisions register). Scaffold complete — apex-forge audit gaps closed. |

### Sprint: Champion-Selection Integrity (docs/26 + docs/27)

Status snapshot of the four slices defined in `docs/26-champion-selection-integrity-fix-spec.md`:

| Slice | Status | Owner | Notes |
|---|---|---|---|
| Slice A — Separate evaluation from champion presentation | **Committed on sprint base** | local | Verified: schema validation passed; full `cargo test --workspace` passed in pre-push hook (covers `cue_for_pairs_response_*` × 5 + `evaluate_pair_honors_preferred_variant_override`); tsc passed. |
| Slice B — Make transition accounting complete | **Committed on sprint base** | local | Verified: full `cargo test --workspace` passed in pre-push hook (covers `selection_transition_counts_*` × 3 + `reoptimize_response_serializes_transition_counts_at_top_level` + `update_persist_summary_for_transition_records_all_summary_counts`); clippy clean; reoptimize schema validation passed (0.2.0). |
| Slice C — Remove incumbent bias in host runtime | **Planning historical; implementation requires operator re-scope** | operator/local | Design proposal PR #166 (`3a44100`) was written before PR #229 promoted the committed Hetzner runtime tree to `main`. The old host-lineage import gate is no longer the active branch blocker, but Slice C implementation must not start until the operator confirms it still applies under the current `main` baseline and records updated rollout decisions. |
| Slice D — Recanonicalize legacy rows | **Design proposal merged; implementation blocked on Slice C observation/operator approval** | unassigned | PR #174 (`38ccc01`) recommends dry-run-first, operator-confirmed recanonicalization with rollback/pre-image artifacts. Implementation must wait for Slice C neutral-selection observation evidence and operator approval of the proposal's open questions; recanonicalized rows remain repair-only, not trade-eligible. |

### Immediate Safety Action (still active)

Per `docs/26` §"Immediate Safety Action":
- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` MUST stay set.
- Live `ENTRY` / `EXIT` for this strategy runtime MUST stay disabled.
- Cues are research-visible but NOT execution-trustworthy.

Do not relax these until Slice C is verified.

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
- **Committed (`da7fea9`)**: Apex harness governance scaffold (PR #217) — installs `docs/ops/README.md`, `docs/ops/ai_workflow.md`, `docs/ops/codex_prompt_pack.md`, `docs/research/packets/template.md`, `docs/research/packets/01-agentic-harness.md`, `.github/pull_request_template.md`, and docs index updates. The workflow preserves `AGENTS.md` as highest precedence, keeps required independent review cross-agent under current rules, treats same-chat sub-agent review as advisory unless the Operator records an explicit exception, and leaves protected-path enforcement as a proposal only.
- **Committed (`f22c26f`)**: Hetzner runtime baseline promoted to `main` (PR #229) — squash-merged the committed production runtime tree from `origin/cherry-picked-from-rc-live-trial` so `main` became the canonical branch for the running server baseline. Verification recorded in the PR: `git diff --quiet HEAD origin/cherry-picked-from-rc-live-trial`, `git diff --check`, and focused `cargo test -p data-service health_returns_503_when_repository_check_fails`.
- **Committed (`c1e031d`)**: AUTO-1A/B observe-only sidecar (PR #231) — added the `autopilot_observe_record` artifact schema/example plus a disabled-by-default `1m` observer sidecar under `tools/scripts/autopilot_observe.py`. The sidecar only performs read-only GETs, writes append-only JSONL records, blocks empty allowlists, mixed/non-`1m` timeframes, `FAIL_CLOSED` dispatch mode, malformed safety payloads, stale/malformed source data, failed live/quality gates, and duplicate observe keys, and has focused tests proving no execution order-intent URL use.
- **Committed (`94b15b2`)**: AUTO-1C/D attribution report and observe-only runbook (PR #233) — added `tools/scripts/autopilot_observe_report.py`, the `autopilot_observe_report` schema/example, focused report tests, and `docs/playbooks/autopilot-observe-only-runbook.md`. The report compares observed 1m candidates against later ready-window and simulated paper-trade outcomes, including direction-aware attribution. The runbook gives hosted one-shot, loop, monitor, stop, and evidence-capture commands. No execution path or runtime service behavior changed.
- **Committed (`d5b7ebe`)**: AUTO-2 paper-autopilot governance roadmap (PR #234) — added `docs/proposals/AUTO-2-1m-paper-autopilot-governance.md` plus `docs/superpowers/plans/2026-06-22-auto2-paper-autopilot-sequence.md`, locking the sequence to focused static paper trial, shadow dynamic champion/challenger allowlist, governed dynamic allowlist, dynamic paper trial, and a separate live-design gate before any live automation work.
- **Committed (`b5baca4`)**: Slice Loop Check governance (PR #235) — added the pre-slice anti-loop check to the Apex harness workflow, Codex prompt pack, remote-agent bootstrap, local review checklist, and GitHub PR template. Future coding slices, including test-only slices, must show new input, state transition, concrete value, non-repetition, and stop/defer boundaries before implementation.
- **Committed (`daca062`)**: AUTO-2A paper ledger/contracts (PR #238) — added the `autopilot_paper_decision_record` and `autopilot_paper_position` contracts/examples plus disabled-by-default static `1m` paper ledger tooling in `tools/scripts/autopilot_paper.py`. The slice is artifact-only and paper-only: no execution-service POST path, live `ENTRY` / `EXIT`, host loop, dynamic allowlist control, runtime service behavior, or Hetzner deployment.
- **Committed (`7e7e38d`)**: AUTO-2A paper report and hosted runbook (PR #240) — added `tools/scripts/autopilot_paper_report.py`, the `autopilot_paper_report` contract/example, focused tests, and `docs/playbooks/autopilot-paper-only-runbook.md` for paper-only hosted run, monitor, stop, evidence, and report commands.
- **Committed (`5f21375`)**: AUTO-2A paper observe-record compatibility fix (PR #241) — accepted real observe-only records whose observe key is minute-bucketed and whose strategy `source_generated_at` includes fractional seconds in the same serialized second as `observed_at`, while preserving stale/future candidate blocking.
- **Committed (`a47f52e`)**: AUTO-2A direction-level static paper gating (PR #242) — added `pair_id:selected_variant:direction` allowlist support for paper-only trials while preserving pair-level entries, report evidence for `pair_variant` / `pair_variant_direction` / `mixed` allowlist mode, and 72h direction-gated runbook commands. No service runtime, dynamic allowlist control, execution-service POST path, or live execution change was included.
- **Merged**: AUTO-2B shadow dynamic allowlist (PR #244 at `632ba80`) — advisory selector artifacts over closed `1m` paper evidence with churn measurability; first snapshot run 2026-07-13. AUTO-2B.2 selector-view design merged (PR #249 at `c1eaf79`); implementation awaits operator go. Output cannot control paper entries; AUTO-2C remains the governor slice.

---

## Blocked / Waiting On

### B-Host-Lineage (historical; cleared by production baseline promotion)

Operator captured the `docs/27` read-only host verification outputs on **2026-05-05 02:29:31Z**. Those outputs remain historical context for Slice C planning. The prior branch-lineage blocker was cleared for new work by PR #229, which promoted the committed Hetzner runtime tree to `main`. This does not green-light Slice C implementation; that work now requires a fresh operator applicability and rollout decision against the current `main` baseline.

Hetzner repo checkout alignment was later operator-reported complete after the
host fast-forwarded to `94b15b2` on `main` and health/disabled-default probes
passed. This section remains only as historical Slice C context.

Neither the local nor any remote agent has SSH access to `cryptopairs`. This is operator-only.

Repository identity raw output:

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
| Slice-C-impl | **HIGH** | Re-scope Slice C against the current `main` baseline before any implementation, then implement neutral champion selection only if the operator confirms the bug model still applies. | **blocked on operator re-scope/decisions** — design proposal PR #166 (`3a44100`) remains historical context, but its host-lineage import premise was superseded by PR #229's production-baseline promotion. Operator must choose whether Slice C still applies, the rollout path, observation window/success thresholds, and host verification owner before implementation PR review. |

### Cross-cutting

| ID | Severity | Description | Status |
|---|---|---|---|
| R1 | medium | Pin rustfmt + clippy version via `rust-toolchain.toml` so operator Mac, CI, and remote-agent environments converge on one Rust toolchain. The operator's Mac currently runs a clippy older than 1.95.0 (CI's stable); GitHub Actions enforces lints the operator's pre-push hook misses. Surfaced when local Codex's clean-worktree review of rebased PR #161 caught a `clippy::unnecessary_sort_by` failure local clippy didn't emit. Recommended Design-proposal-first PR — the channel choice (specific patch vs minor floating vs `stable`) is a small architectural decision. | **resolved by PR #167 (`4ac38b5`) and PR #169 (`74ef7c6`)** — design selected Rust channel `1.95`; implementation added `rust-toolchain.toml`, `Cargo.toml` `rust-version = "1.95"`, CI `toolchain: "1.95"` plus active-toolchain logging, and bootstrap/testing docs plus `CHANGELOG.md` updates. |
| R2 | **HIGH** | Pre-push hook (`.githooks/pre-push` → `scripts/check-rust-ci.sh`) tests operator's working tree, not the staged/committed state. Caught masking three CI failures on origin in 24h: missing `retention_cutoff_ts` import (resolved at `05bca71`), `clippy::unnecessary_sort_by` in `execution-service` and `strategy-service` (resolved at `a82e8f0`). Each time pre-push reported green while origin was broken. **Promote to HIGH** — recurrence rate makes it the bug-of-the-week. Fix candidates: (a) modify `.githooks/pre-push` to `git stash --keep-index --include-untracked` before invoking `scripts/check-rust-ci.sh` and restore on EXIT trap, (b) add a separate `scripts/check-rust-ci-staged.sh` invoked by the hook that operates on a stashed checkout, (c) document as known limitation and rely on CI as canonical. (a) is the smallest diff. Recommended Design-proposal-first PR from a remote agent **as the next claimable item after this commit lands** — block all other work on this slipping further. | **resolved by PR #162 (design proposal merged at `f87e291`)** — Option A recommended (stash-then-pop in `.githooks/pre-push`). Implementation resolved by the R2-impl follow-up row below. |
| R2-impl | **HIGH** | Implement Option A from the merged R2 design proposal (`f87e291`, `docs/proposals/R2-pre-push-staged-only.md`). Modify `.githooks/pre-push` to `git stash --keep-index --include-untracked --quiet --message "pre-push autostash"` before invoking `scripts/check-rust-ci.sh`, restore on EXIT/INT/TERM trap, guard with a clean-tree check (no-op if working tree matches index), preserve `SKIP_RUST_CHECKS=1` early-return. Operator decisions binding for this PR (per R2 §10): (1) Option A as Slice A (do NOT pre-build Option B). (2) Test plan ships as runnable `scripts/test-pre-push.sh` covering the six §9 scenarios plus an "untracked file present" expansion of scenario 3 (gap noted in §7 review). (3) Scope to `.githooks/pre-push` only — no other hooks need this pattern (`ls .githooks/` shows pre-push as the only hook). (4) `SKIP_RUST_CHECKS` rotation deferred to R3 below. Implementation effort per R2 §6: ~75-135 LOC. Operator-side verification only (CI does not run pre-push hooks). | **resolved by PR #164 (`d17103`)** — `.githooks/pre-push` autostashes dirty worktree-only state before invoking `scripts/check-rust-ci.sh`; `scripts/test-pre-push.sh` passed all seven required scenarios. |
| R3 | low-medium | Rotate the pre-push escape hatch from `SKIP_RUST_CHECKS=1` to a less-permissive interface (e.g. `RUST_PREFLIGHT_OVERRIDE=<reason-string>` requiring an explicit reason argument), so casual bypass is less attractive once R2-impl removes the most common reason to bypass (slow-on-dirty-tree pre-push). Out of scope for R2-impl per the binding decisions. | **resolved at design layer by PR #168 (`a1c536d`)** — proposal recommends Option A (`RUST_PREFLIGHT_OVERRIDE=<reason-string>`) with hard reject for legacy `SKIP_RUST_CHECKS=1`; implementation tracked by R3-impl below. |
| CI-1 | medium | **CI never runs the `tools/scripts` test suite.** `.github/workflows/ci.yml:75` runs `pytest research/strategy-engine/tests -q` only, and the `contracts` job (`ci.yml:84-88`) is `python -m json.tool` — JSON *syntax* only, no schema validation. So every operator-tooling test (`tools/scripts/tests/**`, 181 tests as of AUTO-2B.2 B2-b) runs only when an agent or the Operator runs it locally, and the sole schema-vs-example validation for `autopilot_observe_record.schema.json` lives in `tools/scripts/tests/test_autopilot_observe.py`, which CI does not invoke. Contracts and their examples can therefore drift green. Surfaced by the round-6 inner review of PR #252 (contract-angle reviewer); pre-existing, not introduced by that slice. Fix candidates: add a `tools/scripts` pytest job, or extend the `contracts` job to validate every `specs/examples/*.json` against its schema. Note the local runner caveat: the suite needs `--import-mode=importlib` (Anaconda ships a `tests` package that shadows the local namespace dir) — CI's cleaner env may not need it, but the job should pin it regardless. | **open — not started** |
| R3-impl | low-medium | Implement the merged R3 proposal: replace the `SKIP_RUST_CHECKS=1` early return in `.githooks/pre-push`, extend `scripts/test-pre-push.sh`, update remote-agent bootstrap docs, and record the operator-tooling changelog entry. | **resolved by PR #172 (`f874f7c`)** — hard rejects `SKIP_RUST_CHECKS=1`; accepts reason-bearing `RUST_PREFLIGHT_OVERRIDE=<reason>`; rejects exact boolean-ish override values `1`, `true`, `TRUE`, `yes`, `YES`; prints supplied reasons exactly with docs warning not to include secrets; keeps sentinel-file override future-only. |
| X1 | low | Audit script in `docs/27` §"Live Cue Mismatch Audit" still reads `cue.selected_variant` and `cue.selected_signal_config.source`. Update to use `cue.selection_state` once Slice A is on the host. | **resolved by PR #171 (`0d28534`)** — audit command now reads `cue.selection_state.best_variant`, `cue.selection_state.stored_champion_variant`, `cue.selection_state.source`, and `cue.selection_state.validation_state`, with `missing_selection_state_count` surfacing hosts not yet serving the Slice A cue contract. |
| X2 | low | Operator-facing reads of `cue.selected_variant` in any other surface (Trade and Analytics now updated, but check everywhere) should migrate to `selection_state.best_variant` / `stored_champion_variant` per the spec. | **audited in post-PR #171/#172/#173 curation (`94c109e` base)** — no migrate-now operator-facing surfaces found: Trade and Analytics use `cueDisplayedVariant` / `cueBestVariant`; legacy `selected_variant` remains in contracts, examples, service internals, tests, and historical docs for compatibility. Keep legacy contract compatibility for now; post-Slice-C reporting alignment is tracked by X3. |
| X3 | low | After Slice C lands and legacy-row behavior is observed, align reporting/diagnostic surfaces that still expose only legacy `selected_variant` (backtest, live-z, paper-trades, opportunity-history) so operators can distinguish evaluated-best vs stored-champion presentation without breaking existing contracts. | **design landed by PR #175 (`2d66495`); implementation still deferred** — later work should add optional/additive `selection_diagnostics` to backtest, live-z, paper-trades, and opportunity-history only after Slice C host/runtime behavior is implemented and operator-captured observation evidence exists. Do not remove or redefine legacy `selected_variant`. |

---

## Next Recommended Move

Operator-approved queue per **OP-45** (dependency order). Do not reorder or skip; each step is gated on the prior one:

1. **Complete PR #252 (AUTO-2B.2 B2-b)** — under the prior Claude-author / Codex-review roles (OP-44 transition clause / OP-45(a)). Gate before merge: conflict-free against `main`, fresh exact-SHA Codex review at the repaired head, Operator authorization, then merge (Tier 3). OP-45(g): B2-c must not start until this is done.
2. **Codex: AUTO-2B.2 B2-c (shadow scorer selector-view input)** — the first post-swap Codex-authored slice (OP-45(b)); Claude is Independent Reviewer. Preserve the boundary that shadow/selector output cannot control paper entries.
3. **Operator-only: AUTO-2B.2 B2-d evidence pass** — the operator capture window (OP-45(c)). Artifact-only; must not start unattended loops or alter runtime config.
4. **Codex: AUTO-2C design proposal** — governed dynamic allowlist governor: sample, dwell-time, churn, concentration, direction, quarantine, and stale-selector gates between champion/challenger output and paper eligibility (OP-45(d)). Design-only.
5. **Stop after the AUTO-2C proposal** and rebuild the implementation queue from captured evidence (OP-45(e)) — do not auto-continue into AUTO-2C implementation, AUTO-2D, or AUTO-3.

Parked / conditional (not part of the OP-45 active queue):

- **Legacy PRs #216, #187, #186, #165, #159 remain parked** pending separate per-PR relevance reviews (OP-45(f)). Do not fork new work from them.
- **AUTO-2D dynamic paper trial** — only after the AUTO-2C governor lands and the queue is rebuilt; the governed dynamic allowlist (not raw champion/challenger output) controls paper-only eligibility. Live execution stays out of scope.
- **AUTO-3 live automation design proposal** — design-only, after AUTO-2D evidence and explicit Operator approval; never grantable by `CLAUDE.md`.
- **Slice C / Slice C observation / Slice D / X3** — unchanged, still gated on Operator re-scope against the `main` baseline and the respective proposals (PR #166 / #174 / #175). Preserve Slice A/B semantics and legacy `selected_variant` compatibility.

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
