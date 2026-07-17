# Agent State (Living)

> **This file is the second mandatory read for every agent, after `AGENTS.md`.**
> See `AGENTS.md` §8 for the topology, work-allocation rules, and hydration sequence.

---

## Pin

| Field | Value |
|---|---|
| Last updated (UTC) | 2026-07-17 |
| Updated by | codex |
| Repo HEAD pin (committed) | `354f8acb5b2cc46ee39daa52b23e6cea3a2a804b` |
| Pin branch | `main` |
| Sprint base branch | `main` |
| Pin notes | Pin is `origin/main` after PR #254 completed the standalone OP-44 / OBS-2 bookkeeping. Codex holds Lead Coder + Operator Interface and Claude holds Independent Reviewer. AUTO-2 remains constrained to the paper-autopilot sequence; OP-45 assigns B2-c as the current coding slice under AG-20260717-010. |
| Origin | `https://github.com/apexpark/cryptopairs.git` |
| Working-tree state | **B2-c in progress under AG-20260717-010.** PR #254 landed the OP-44 / OBS-2 bookkeeping as `354f8acb5b2cc46ee39daa52b23e6cea3a2a804b`; Codex now authors B2-c and Claude independently reviews its exact PR head. Scope is the advisory shadow scorer's selector-view input, universe metrics, and per-stream churn only. OBS-1, OBS-3, and CI-1 remain open. No service code, order intents, dispatches, dynamic allowlist control, live `ENTRY` / `EXIT` enablement, host action, deploy, capture, secret access, or unattended loop is included. |

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
| AUTO-2B.2 - B2-b selector-view capture | **Done — PR #252 merged** | claude (author) / codex (reviewer) | PR #252 was Codex-reviewed CLEAN at final head `256e80031216773102dcddcccf88f76a8975d75b` and personally squash-merged by the Operator as `04826d1d708fa3e40812301d368ec43cf388c300` on `main`. `autopilot_observe.py` gains disabled-by-default `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW` (all three cue buckets → v2 selector-view rows, no outcome/eligibility path), a `MAX_RUNTIME_SECONDS` bound, a per-tick row count, and a runbook section requiring a read-only disk estimate before capture. Disabled-default behaviour is unchanged on well-formed input (tested), and round 7 restored the narrow paper-feeding run's pre-slice stop behaviour (no signal handler, default SIGTERM disposition, one plain sleep per interval). It is **not** byte-identical on malformed input: the slice's fail-closed hardening also lands on the narrow path (malformed values now record `null`; a float in `QUALITY_WINDOWS_JSON` now fails at startup), which the Operator ratified under OBS-2 Option 1 as fail-closed validation; normal-operation behaviour remains unchanged and the hardening must not be reverted. Capture is all-or-nothing: any degraded/stale source, missing/non-list bucket, or untranscribable candidate refuses the whole tick (no partial universe reaches B2-c); a selector-view loop refuses to start without a positive `MAX_RUNTIME_SECONDS`; the runbook carries an exact selector-view stop procedure. Each captured tick is led by a `selector_view_tick` manifest (`recorded_rows` + per-bucket counts) so an empty-but-captured universe is distinguishable from a missed tick and a truncated tail from a smaller universe; refused ticks emit no manifest. The tick manifest's contract pins its own identity (non-empty `run_id` carrying the tick's `observed_at` date-time, `date-time`-formatted required non-nullable timestamps, `timeframe` fixed to `1m`), adversarially tested under a jsonschema `FormatChecker`. A **selector-view loop only** handles SIGTERM/SIGINT and exits at a checkpoint: a signal while polling abandons the unwritten tick at the next fetch boundary, while a signal arriving once the tick is past abandoning (during/after record construction, or during the final fetch, which has no boundary after it) lets the append complete — the guarantee is that no tick is left half-written, not that every in-flight tick finishes nor that every stop while polling abandons one. Cue timestamps are normalized to RFC 3339 on the selector-view path, so a parseable-but-not-RFC-3339 `generated_at` cannot yield a manifest that violates its own contract. The narrow paper-feeding loop keeps its default signal disposition and its plain sleep (pre-slice stop behaviour restored; malformed-input/config divergence is ratified under OBS-2 Option 1; graceful stop is tracked as OBS-1). A read-only `--verify-selector-view-pid` probe confirms a PID is a selector-view run — not the identically-invoked narrow run — before the operator signals it; it establishes the process's *kind*, not its *identity* — and nothing establishes identity today, the PID file included (it records a PID, the recyclable thing), so an early stop needs explicit Operator authorization; binding the probe to one specific run is follow-up OBS-3. **Transitional ownership complete:** grandfathered under OP-44's transition clause / OP-45(a), B2-b completed under the prior Claude-author / Codex-review roles; OP-44 is now operative. This branch merged `origin/main` (`ecc9cbd`, PR #253), resolved the decisions/AGENT_STATE/CHANGELOG conflicts, repaired the four findings from the Codex review at `93efb4d`, repaired the three round-6 findings at `4d14612` (empty-tick representation, exact-argv process *kind* checking + graceful stop — round 6 called this "exact process identity", which overstated it: the check separates a capture from the narrow run but does not identify *which* capture, per OBS-3 — and clean-tree verification totals — the prior "180" was measured in a tree carrying an untracked duplicate test module), and repaired the four round-7 findings from the fresh Codex review at `177cd0e` (manifest identity contract, work-order scope restored, operational wording, audit surfaces). Round 9 repaired three of the four P2s from the Codex review at `f9b3e63`: the selector-view runtime bound now measures the monotonic clock (a wall-clock bound is steerable by an NTP correction — this is the control that keeps a capture from running unattended); `recorded_rows` is documented as a producer invariant that JSON Schema cannot enforce, with the writer's invariant pinned by test instead; and the byte-identity audit was extended to the surfaces round 8 missed — the decisions register (via an appended correction row leaving the ratified decision intact), the agent-runs register, two inner-review-summary claims, and, after round 9's own inner review caught the first sweep excluding code, the same false "disabled probe stays byte-identical" claim surviving in `autopilot_observe.py`'s comments and its test's. The fourth P2 (the stop probe verifies a process's kind, not its identity) was **deferred by the Operator** to follow-up OBS-3 for its own work order. Rounds 10 and 11 then repaired the operator-facing consequences of that deferral, both documentation-only: round 10 stopped the runbook telling the Operator the probe confirmed "this" capture was "safe to signal" before having them kill it; round 11 withdrew round 10's replacement claim that two procedural rules closed the gap — a sequential PID recycle (A exits, B reuses the PID, only B running) satisfies every one of them, so the runbook now treats the checks as screening only and an early stop requires explicit Operator authorization with identity declared unverified; round 12 then withdrew round 11's own "verify-then-signal in one process" constraint (still TOCTOU on a raw PID — OBS-3 now requires a pidfd, opened before verification so a recycle fails `ESRCH`), made the kill block's SIGTERM guarantees conditional on the PID still referring to a capture (authorization does not restore identity), and corrected a verification record that had gone stale under its own round's repairs. Clean-tree `tools/scripts` totals: **169** pre-repair → **181** after round 6 → **185** after round 7 → **187** after round 9 (49 subtests; round 9 adds 2 tests). All counts are measured in a clean detached worktree — the untracked macOS duplicate test module that inflated an earlier round's count by 11 is no longer present in the working tree, but clean-checkout measurement remains the standing rule rather than a workaround for it. Round 7's own multi-angle inner review found and fixed two defects in the repairs themselves (the tightened `date-time` contract was violable by a parseable-but-not-RFC-3339 cue timestamp; "a signal during polling abandons the tick" was itself an over-claim — a stop during the final fetch completes the tick) and recorded follow-ups OBS-1 (narrow-loop graceful stop) and OBS-2 (the slice's fail-closed hardening also changed the narrow run's entry emission — resolved by the Operator's Option 1 ruling; do not revert the hardening). The final exact head `256e80031216773102dcddcccf88f76a8975d75b` was reviewed CLEAN by Codex and the Operator squash-merged it as `04826d1d708fa3e40812301d368ec43cf388c300`; Tier 3 flow complete. |
| AUTO-2B.2 - B2-c shadow scorer selector-view input | **In progress — AG-20260717-010** | codex (author) / claude (reviewer) | Branch `codex/b2c-selector-view-input` is scoped to optional complete-tick selector-view input, the already-contracted v2 selector/universe blocks, per-stream churn, deterministic tests, and the shadow runbook. Output remains advisory and cannot control paper entries. No capture, host action, OBS-1/OBS-3, service, deploy, secret, live-trading, or unattended-loop work is included. |
| GOV-ROLESWAP - Swap Claude/Codex roles (OP-44) | **Merged and operative** | claude | PR #253 merged at `ecc9cbd` on `main`. B2-b PR #252 completed under the prior roles and merged as `04826d1`, making the swap operative per OP-44's transition clause and OP-45(a)/(g). Codex → Lead Coder + Operator Interface; Claude → Independent Reviewer. Added `CODEX.md`; updated ai_workflow/git-github/CLAUDE role sections, codex_prompt_pack note, CODEOWNERS, project.yaml. |
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
| CI-1 | medium | **CI never runs the `tools/scripts` test suite.** `.github/workflows/ci.yml:75` runs `pytest research/strategy-engine/tests -q` only, and the `contracts` job (`ci.yml:84-88`) is `python -m json.tool` — JSON *syntax* only, no schema validation. So every operator-tooling test (`tools/scripts/tests/**`, 185 tests as of AUTO-2B.2 B2-b round 7) runs only when an agent or the Operator runs it locally, and the sole schema-vs-example validation for `autopilot_observe_record.schema.json` lives in `tools/scripts/tests/test_autopilot_observe.py`, which CI does not invoke. Contracts and their examples can therefore drift green. Sharpened by round 7: the tightened `selector_view_tick` `date-time` constraints are `format` assertions, which are inert unless a validator is handed a `FormatChecker` — those tests are the repo's only `FormatChecker` users, and `rfc3339-validator` is an undeclared dependency (no Python requirements file exists; `ci.yml` installs only `ruff pytest`). The tests assert the checker is live so they fail loudly rather than silently passing, but the contract is currently enforced only on machines that happen to have `jsonschema[format]` installed. Surfaced by the round-6 inner review of PR #252 (contract-angle reviewer); pre-existing, not introduced by that slice. Fix candidates: add a `tools/scripts` pytest job, or extend the `contracts` job to validate every `specs/examples/*.json` against its schema. Note the local runner caveat: the suite needs `--import-mode=importlib` (Anaconda ships a `tests` package that shadows the local namespace dir) — CI's cleaner env may not need it, but the job should pin it regardless. | **open — not started** |
| OBS-1 | low-medium | **The narrow paper-feeding observe loop has no graceful stop.** `tools/scripts/autopilot_observe.py` installs its `StopSignal` handler only for selector-view loops, so the narrow loop keeps SIGTERM's default disposition and a stop can land mid-append and truncate its final JSONL record. AUTO-2B.2 B2-b originally installed the handler for *every* loop, which would have fixed this — but that changed the narrow paper-feeding run's operator-visible stop behaviour, which the B2-b work order (AG-20260713-009) put out of scope and required to stay byte-identical. Reverted to selector-view-only in the round-7 repairs of PR #252 and recorded here rather than carried, since widening a live paper-feeding run's stop semantics needs Operator authorization it did not have. Fix candidate: extend the same `StopSignal` install + stop-aware sleep to the narrow loop under its own work order, with the byte-identical constraint explicitly lifted. The machinery already exists and is tested; this is a scope/authorization decision, not an engineering one. Surfaced by the fresh Codex exact-SHA review of PR #252 at `177cd0e`. | **open — not started; needs Operator scope decision** |
| OBS-2 | medium | **B2-b's fail-closed hardening also changed the narrow paper-feeding run's emission; the Operator ratified that hardening under Option 1.** AG-20260713-009 required narrow-run behaviour to be byte-identical with the capture flag false, and named "any change to the entry-candidate emission when the flag is false" as a stop condition. Surfaced by the round-7 multi-angle inner review (scope-boundary reviewer) and independently reproduced by executing `origin/main`'s module against the branch's, flag false: (a) `source_generated_at` with a non-ISO `generated_at` records `null`, was the raw string; (b) `spread_z` from a NaN input records `null`, was `nan`; (c) `learning_overlay_age_seconds` of `-5` records `null`, was `-5`; (d) `dispatch_mode` of `"WEIRD_MODE"` records `null`, was `"WEIRD_MODE"`; (e) `_optional_int(5.0)` now raises `ValueError` where it returned `5` — reachable at startup because the narrow run is launched with `AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON` (runbook §narrow), so a `"rows": 5.0` in that file now kills the run before its first tick instead of loading; (f) `AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=-1` now raises at config load. All six are only observable on malformed upstream data or a malformed quality-windows file, so normal operation is unaffected. **Widened in round 8 (verified):** (e)/(f) are config-load failures, and `load_config` runs *before* the disabled-default early return — so they also reach the **disabled probe**, which this PR elsewhere claimed stays byte-identical. Reproduced: with a `"rows": 5.0` quality-windows row and `AUTOPILOT_OBSERVE_ENABLED=false`, `origin/main` exits 0 printing the disabled payload while this branch raises `ValueError`. So the divergence is not confined to enabled narrow runs; any invocation that loads a malformed quality-windows file now fails at startup, disabled probe included. The round-8 audit-surface repair corrected the claim; the behaviour itself remained untouched and awaited the Operator ruling recorded below. **Deliberately not repaired in round 7:** every one is a fail-closed hardening that makes records schema-valid instead of admitting NaN/negative/out-of-enum values, so "restoring byte-identical" here would mean *weakening* a safety property — a call reserved for the Operator and now resolved below. Options presented before the ruling: (1) ratify the hardening and amend the work order's byte-identical clause to except fail-closed input validation; (2) scope the hardening to the selector-view path and let entry rows keep passing malformed values through; (3) split it into its own work order against the narrow run. Pre-ruling recommendation: (1) — the hardening is aligned with the standing fail-closed invariant, and (2) would knowingly keep emitting contract-violating entry rows. Note (e)/(f) are the sharpest: they turn a previously-loading config into a hard startup failure. **Operator ruling (2026-07-17): Option 1 adopted.** The already-merged hardening is ratified; AG-20260713-009's byte-identical requirement is superseded only for fail-closed validation of malformed inputs and configuration; normal-operation behaviour remains unchanged; do not revert the hardening. OBS-1, OBS-3, B2-c scope expansion, capture, host action, deploy, secret access, live trading, and unattended loops remain unauthorized. | **resolved — Operator adopted Option 1; fail-closed hardening ratified** |
| OBS-3 | medium | **The selector-view stop probe verifies a process's *kind*, not its *identity*.** `verify_selector_view_pid` / `selector_view_argv_matches` (`tools/scripts/autopilot_observe.py`) read exact argv from `/proc` and prove the PID is *a* selector-view capture — which is what round 6 set out to do, and it correctly refuses the narrow run, lookalike flag values, and inexact `ps` output. It does **not** prove the PID is *the* run the Operator meant to stop: two concurrent selector-view captures both match, and a stale PID file whose PID has been recycled by a *different* selector-view capture passes the probe and gets signalled. **Nothing establishes identity today** — not the PID file (it records a PID, which is the recyclable thing) and not any procedural rule, since a *sequential* recycle (capture A exits, capture B is later handed A's PID) defeats every "one capture at a time" rule because the two never coexist. Until OBS-3 lands, every early stop therefore costs an explicit Operator authorization with identity declared unverified. Fix candidates (all Linux/`/proc`, all **untested** — this session's host is macOS with no `/proc`, so they must be validated on the capture host inside the OBS-3 slice rather than trusted from here): (a) compare the process's start time against the PID file's mtime — the original writer started at or before its own PID file was written, whereas a recycled PID's process must have started strictly after, since it could not exist until the first exited; note second-granularity and NTP-step caveats, the latter being the same class as the round-9 wall-clock bug; (b) `readlink /proc/<pid>/fd/1` and require it to resolve to *this* run root's log — the `nohup` redirect ties a capture's stdout to the run root it was started with, so a recycled PID belonging to another capture points at a different log; (c) carry the run id / output dir in argv and match it against the PID file. **Binding constraint on all three:** an identity check performed as an Operator eyeball *between* the probe and the `kill` is still TOCTOU-exposed and is therefore not a fix — it reproduces exactly the round-10 error of trusting a procedural step to close a race. Whichever candidate wins must run **inside the signalling tool** — but note that "verify-then-signal in one process" is **not sufficient and not atomic**, a correction raised by the round-12 review against this row's own earlier wording: reading `/proc` and calling `kill(pid)` are separate syscalls, and the target can exit and have its PID recycled between them, so a single process racing on a raw PID reproduces the very TOCTOU it was meant to close. **The requirement is a stable kernel handle, not a PID:** acquire a pidfd (`os.pidfd_open`, Linux 5.3+/Python 3.9+) and signal through it (`signal.pidfd_send_signal`, Linux 5.1+/Python 3.9+); a pidfd refers to one specific process and is never recycled, which is exactly the property `pidfd_send_signal(2)` exists to provide. **Order is load-bearing:** open the pidfd *first*, then verify identity, then signal through the pidfd — that way a recycle between steps leaves the pidfd pointing at the original (now dead) process and the signal fails `ESRCH`, i.e. fails closed, instead of landing on a stranger. Verify-then-open is *wrong* and must not be built: a recycle in that window is exactly what gets signalled. Fail closed if the pidfd APIs are unavailable (non-Linux, or kernel too old), consistent with the tool's existing `IDENTITY_NOT_VERIFIABLE` posture. Both APIs are **untested here** — confirmed absent on this session's macOS host — so validate on the capture host inside the slice. Known holes to design against: (b) passes for the wrong run if a capture is restarted into an existing `$SV_ROOT` without regenerating `SV_ID`, since both runs' stdout resolves to the same log; and a rotated or removed log makes `readlink` yield a `… (deleted)` path, which must fail closed rather than mismatch-and-guess. All are design choices about how a stop command binds to one run — hence a work order of its own rather than an improvisation at the end of this PR. Raised by the Codex exact-SHA review of PR #252 at `f9b3e63`; **Operator deferred it out of round 9** (2026-07-17) so the redesign gets its own slice and review. **Round 10 addition:** the round-10 review found the disclosure had not reached the operator-facing surfaces — the runbook told the Operator the probe confirmed "this" capture was "safe to signal" and then had them kill it. The runbook, the matcher docstring, and the state/PR wording were corrected to state kind-not-identity. (Round 10 also added two procedural rules and a both-conditions kill gate; **round 11 withdrew both** — see the round-11 addition below — so do not read that part as current.) **Two overstatements deliberately left in the tool's own output, for this work order to resolve rather than a wording round:** the probe emits a field literally named `safe_to_signal: true`, and its `--help` says "exit 0 only if it is safe to signal" — both assert a safety the check does not establish. They were not renamed because that changes the tool's output contract (a behaviour change, out of scope for an audit-wording repair) and any consumer of that JSON would need updating in step. Fold both into the OBS-3 redesign: if the probe is bound to a specific run, `safe_to_signal` becomes true as named; if not, rename it to something like `is_selector_view_capture`. **Round 11 addition — the round-10 stopgap was itself unsound and is withdrawn.** Round 10 named the recycled-PID case and then claimed two procedural rules "closed the gap"; they do not. The round-11 review supplied the counterexample: capture A writes its PID and exits, capture B later reuses that PID, and at kill time only B runs — so "one capture at a time" holds, the PID file is the one the Operator created, and the probe exits 0 because B genuinely is a capture. Every condition passes and the wrong run is killed; the two captures never coexist, so no "one at a time" rule can exclude it. The runbook no longer claims sufficiency: the checks are stated as **screening** (they can prove you must not signal, never that you may), the false "identity comes from the PID file" claim is gone (a PID file records a PID — the recyclable thing), and an early stop now requires explicit Operator authorization with identity declared unverified. **This raises OBS-3's practical priority:** until it lands there is no procedural substitute, so every early stop costs an Operator decision. Blast radius, for weighing that decision — and note it is a likelihood, not a bound: *at the moment it runs* the probe does reliably exclude the narrow paper-feeding run, so if that still holds at signal time the worst case is a graceful SIGTERM to a different selector-view capture (observation-only, no trading or eligibility path, no half-written record — B installs its `StopSignal` before its first tick — losing at most that run's in-flight tick). **But the probe and the `kill` are separate commands and nothing holds the PID between them**, so a recycle inside that window can land the signal on a process the probe never saw, including the narrow paper-feeding run (which has no handler — see OBS-1 — so a truncated final record) or anything else on the host. Unlikely, not excluded. Any OBS-3 design that budgets against a bounded observation-only blast radius is budgeting against the wrong risk. | **open — deferred by Operator; needs its own work order** |
| R3-impl | low-medium | Implement the merged R3 proposal: replace the `SKIP_RUST_CHECKS=1` early return in `.githooks/pre-push`, extend `scripts/test-pre-push.sh`, update remote-agent bootstrap docs, and record the operator-tooling changelog entry. | **resolved by PR #172 (`f874f7c`)** — hard rejects `SKIP_RUST_CHECKS=1`; accepts reason-bearing `RUST_PREFLIGHT_OVERRIDE=<reason>`; rejects exact boolean-ish override values `1`, `true`, `TRUE`, `yes`, `YES`; prints supplied reasons exactly with docs warning not to include secrets; keeps sentinel-file override future-only. |
| X1 | low | Audit script in `docs/27` §"Live Cue Mismatch Audit" still reads `cue.selected_variant` and `cue.selected_signal_config.source`. Update to use `cue.selection_state` once Slice A is on the host. | **resolved by PR #171 (`0d28534`)** — audit command now reads `cue.selection_state.best_variant`, `cue.selection_state.stored_champion_variant`, `cue.selection_state.source`, and `cue.selection_state.validation_state`, with `missing_selection_state_count` surfacing hosts not yet serving the Slice A cue contract. |
| X2 | low | Operator-facing reads of `cue.selected_variant` in any other surface (Trade and Analytics now updated, but check everywhere) should migrate to `selection_state.best_variant` / `stored_champion_variant` per the spec. | **audited in post-PR #171/#172/#173 curation (`94c109e` base)** — no migrate-now operator-facing surfaces found: Trade and Analytics use `cueDisplayedVariant` / `cueBestVariant`; legacy `selected_variant` remains in contracts, examples, service internals, tests, and historical docs for compatibility. Keep legacy contract compatibility for now; post-Slice-C reporting alignment is tracked by X3. |
| X3 | low | After Slice C lands and legacy-row behavior is observed, align reporting/diagnostic surfaces that still expose only legacy `selected_variant` (backtest, live-z, paper-trades, opportunity-history) so operators can distinguish evaluated-best vs stored-champion presentation without breaking existing contracts. | **design landed by PR #175 (`2d66495`); implementation still deferred** — later work should add optional/additive `selection_diagnostics` to backtest, live-z, paper-trades, and opportunity-history only after Slice C host/runtime behavior is implemented and operator-captured observation evidence exists. Do not remove or redefine legacy `selected_variant`. |

---

## Next Recommended Move

Operator-approved queue per **OP-45** (dependency order). Do not reorder or skip; each step is gated on the prior one:

Completed prerequisite: PR #252 (AUTO-2B.2 B2-b) was Codex-reviewed CLEAN at `256e80031216773102dcddcccf88f76a8975d75b` and Operator squash-merged as `04826d1d708fa3e40812301d368ec43cf388c300`, completing OP-45(a)/(g).

1. **Codex: AUTO-2B.2 B2-c (shadow scorer selector-view input)** — the first post-swap Codex-authored slice (OP-45(b)); Claude is Independent Reviewer. Preserve the boundary that shadow/selector output cannot control paper entries.
2. **Operator-only: AUTO-2B.2 B2-d evidence pass** — the operator capture window (OP-45(c)). Artifact-only; must not start unattended loops or alter runtime config.
3. **Codex: AUTO-2C design proposal** — governed dynamic allowlist governor: sample, dwell-time, churn, concentration, direction, quarantine, and stale-selector gates between champion/challenger output and paper eligibility (OP-45(d)). Design-only.
4. **Stop after the AUTO-2C proposal** and rebuild the implementation queue from captured evidence (OP-45(e)) — do not auto-continue into AUTO-2C implementation, AUTO-2D, or AUTO-3.

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
