# Agent State (Living)

> **This file is the second mandatory read for every agent, after `AGENTS.md`.**
> See `AGENTS.md` §8 for the topology, work-allocation rules, and hydration sequence.

---

## Pin

| Field | Value |
|---|---|
| Last updated (UTC) | 2026-05-03 |
| Updated by | local agent |
| Repo HEAD pin (committed) | `2148693` |
| Pin branch | `codex/fix-clippy-run-24549051096` |
| Pin notes | Pin convention + cargo-blocked remote-agent workaround landed on top of a87b8ae. Pin lags HEAD by 1 after the cargo-workaround commit (per the new convention). The pin row above is the canonical machine-readable pin — no other backticked SHA appears in the §Pin table so the playbook §1 regex extracts unambiguously. |
| Origin | `https://github.com/apexpark/cryptopairs.git` |
| Working-tree state | **DIRTY** — Slice A and Slice B code (cue + selection_state + transition accounting + reoptimize 0.2.0) is in the operator’s working tree but **not yet committed**. The retention/data-horizon sprint and a 4k z-chart UI sprint are also dirty in the same worktree. See §"Currently In Flight" and §"Next Recommended Move". |

If `git rev-parse HEAD` does not match the pin above, this file is stale; stop and request operator refresh per `AGENTS.md` §7.

---

## Currently In Flight

### Sprint: Champion-Selection Integrity (docs/26 + docs/27)

Status snapshot of the four slices defined in `docs/26-champion-selection-integrity-fix-spec.md`:

| Slice | Status | Owner | Notes |
|---|---|---|---|
| Slice A — Separate evaluation from champion presentation | **Implemented in working tree, awaiting commit + push** | local | Verified: schema validation passed; full `cargo test --workspace` passed in pre-push hook (covers `cue_for_pairs_response_*` × 5 + `evaluate_pair_honors_preferred_variant_override`); tsc passed. |
| Slice B — Make transition accounting complete | **Implemented in working tree, awaiting commit + push** | local | Verified: full `cargo test --workspace` passed in pre-push hook (covers `selection_transition_counts_*` × 3 + `reoptimize_response_serializes_transition_counts_at_top_level` + `update_persist_summary_for_transition_records_all_summary_counts`); clippy clean; reoptimize schema validation passed (0.2.0). |
| Slice C — Remove incumbent bias in host runtime | **Blocked** | unassigned | Blocked on pulling the host `rc/live-trial` lineage into a reviewable local branch (see §"Blocked / Waiting On"). |
| Slice D — Recanonicalize legacy rows | Not started | unassigned | Should follow Slice C. |

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
- **Working-tree only (this commit)**: Cargo-blocked remote-agent workaround. Remote agents (Codex, Claude) cannot install `cargo` in their environments. Two-tier Rust verification both running `scripts/check-rust-ci.sh`: primary = local agent on demand against the remote agent's branch (sub-second with incremental cache), backstop = GitHub Actions on every push to `codex/**` or `claude/**` (`ci.yml` extended to include `claude/**`). Playbook §3 split into 3a (agent-runnable: tsc, jsonschema, json syntax) and 3b (cargo-dependent: delegated). Playbook §4 PR template adds explicit "Rust check status" field. Playbook §7 review checklist requires both local-agent and CI green for any Rust-touching PR. The multi-agent operating model is **fully active** as of this commit — Codex and Claude can hydrate, claim follow-ups, and ship Rust-touching PRs without local cargo.
- **Working-tree only (not yet committed)** — Slice A: `cue.selection_state` contract added with strict enums for `source` and `validation_state`; cue endpoint now projects champion-consistent cues or fails closed; UI surfaces consume `selection_state`. `specs/contracts/strategy_pairs_cues_response.schema.json`, `specs/examples/strategy_pairs_cues_response.example.json`, `apps/web/src/types.ts`, `apps/web/src/App.tsx`, `services/strategy-service/src/lib.rs`, `services/strategy-service/src/main.rs`. Tests: `cue_for_pairs_response_*` + `evaluate_pair_honors_preferred_variant_override`.
- **Working-tree only (not yet committed)** — Slice B: `SelectionTransitionCounts` struct now records all four `ChampionDecision` outcomes; reoptimize observability emits all four counts and warns on `selected_rows_written > 0` with zero accounted decisions; reoptimize response schema bumped to 0.2.0 with additive `initialize_decisions` / `unchanged_decisions`. Drift table remains scoped to `KEEP_CHAMPION` / `PROMOTE_CHALLENGER` only. Tests: `selection_transition_counts_*` (×3 incl. accumulate), `reoptimize_response_serializes_transition_counts_at_top_level`, `update_persist_summary_for_transition_records_all_summary_counts`.

---

## Blocked / Waiting On

### B-Host-Lineage (blocks Slice C)

The Hetzner host `cryptopairs` is running a divergent branch (`rc/live-trial`) with selection-config / provenance code that is **not** in this repo. Slice C cannot be designed against unaudited code.

Required to unblock:
1. Operator runs `ssh cryptopairs 'cd /opt/cryptopairs && git rev-parse HEAD && git branch --show-current && git status --short'` and posts the result.
2. Operator imports the host runtime lineage into a local reviewable branch (or merges it back to `origin`).
3. The brief (`docs/27` §"Host Verification Steps") provides the read-only verification commands; results should be posted into this file before Slice C work begins.

Neither the local nor any remote agent has SSH access to `cryptopairs`. This is operator-only.

---

## Open Follow-ups

Follow-ups carried forward from prior reviews. Ordered by source review then severity. Pickable by any remote agent unless marked `local-only`.

### From Slice A independent review

| ID | Severity | Description | Status |
|---|---|---|---|
| S4 | medium | Add `pairs_cue_projection_total{outcome}` counter; double evaluation cost on drift pairs needs a metric and a runbook note. | open |
| S6 | low | UI’s `cueDisplayedVariant` shows champion name in `CHAMPION_PROJECTION_FAILED` state. Consider rendering `--` or `BLOCKED` instead. (`apps/web/src/App.tsx:206-211`) | open |
| S7 | low | Reoptimize / write path does not yet emit `cue.selection_state`. Bridge in Slice B+ work or accept as deferred. | partially addressed by Slice B (counts now emitted in response, but `selection_state` shape itself still cue-only) |
| S8 | low | Unreachable fifth match arm at `services/strategy-service/src/main.rs:4676-4681`. Replace with `unreachable!` or document. | open |

### From Slice B independent review

| ID | Severity | Description | Status |
|---|---|---|---|
| B1 | low | Add `accumulate(other)` unit test on `SelectionTransitionCounts`. | **resolved in working tree** — `selection_transition_counts_accumulate_sums_each_field` at `services/strategy-service/src/main.rs:8472` (passes in pre-push `cargo test --workspace`). Lands when Slice B commits. |
| B2 | low | Add serde round-trip test asserting `initialize_decisions` / `unchanged_decisions` / `champion_promotions` / `champion_locks` appear at the top level of `ReoptimizeResponse` (locks the `serde(flatten)` wire shape). | **resolved in working tree** — `reoptimize_response_serializes_transition_counts_at_top_level` at `services/strategy-service/src/main.rs:8529` (passes). Lands when Slice B commits. |
| B3 | low | One-line schema comment explaining `initialize_decisions` / `unchanged_decisions` are kept optional in `required` for backward compatibility but always populated by the server. | open |
| B4 | medium-low | Integration-shaped test that drives `record_evaluation` and asserts `summary.transition_counts` matches an expected `ChampionDecision` distribution. Was the highest-value Slice B follow-up. | **partially resolved in working tree** — `update_persist_summary_for_transition` was extracted as a free helper (`services/strategy-service/src/main.rs:2042`, called at `:967` / `:976`) and unit-tested by `update_persist_summary_for_transition_records_all_summary_counts` at `:8501`. That covers the accounting math but **does not exercise the `record_evaluation` persistence boundary** — the helper call could be removed from `record_evaluation` and the test would still pass. True end-to-end coverage requires a Postgres-backed test harness in `strategy-service`, which does not exist (see B6). |
| B5 | low | Materialize the per-decision counts as actual Prometheus-style metrics (`strategy_selection_transition_total{decision,timeframe}` and `strategy_selection_rows_updated_without_transition_total{timeframe}`) rather than relying on log lines for alerting. Spec named these in `docs/26` §Observability. | **still deferred** — slice currently emits structured `info!` / `warn!` logs only; no scrapeable metric on the `/metrics` endpoint. Alert rules cannot key off these without a metric. |
| B6 | medium | Stand up a Postgres-backed repository integration harness for `strategy-service` (e.g. `testcontainers`-style ephemeral Timescale, or an explicit `StrategyRepository` trait seam with an in-memory implementation for tests). Required to make B4 a true persistence-boundary test, and a precondition for any future test that needs to assert real `upsert_selected_signal` / `record_champion_drift_event` behavior. Affects `services/strategy-service/src/main.rs` (struct `StrategyRepository`) and likely `Cargo.toml`. | open — no harness exists today. |

### Cross-cutting

| ID | Severity | Description | Status |
|---|---|---|---|
| X1 | low | Audit script in `docs/27` §"Live Cue Mismatch Audit" still reads `cue.selected_variant` and `cue.selected_signal_config.source`. Update to use `cue.selection_state` once Slice A is on the host. | open |
| X2 | low | Operator-facing reads of `cue.selected_variant` in any other surface (Trade and Analytics now updated, but check everywhere) should migrate to `selection_state.best_variant` / `stored_champion_variant` per the spec. | open |

---

## Next Recommended Move

Pickable items, in priority order:

1. **Operator action: commit Slice A + B and push.** Until committed, no remote agent can see this work and Slice C planning cannot proceed against the actual implemented code. Slice A and B coexist with the retention sprint and the 4k z-chart sprint on the same dirty worktree, so the commit needs hand-resolved patch staging on `services/strategy-service/src/main.rs` (41 hunks total) and `CHANGELOG.md` (entries for slice A, slice B, and retention interleaved). When this lands, B1/B2/B4 land with it.
2. **Operator action: produce the host verification output** (B-Host-Lineage above). Once captured, post into this file under §"Blocked / Waiting On".
3. **Remote agent: B3 + S8** — quick defensive adds (one schema comment, one `unreachable!` macro). Can be batched into one PR.
4. **Remote agent: B6** — stand up the Postgres-backed test harness. Higher-priority than the smaller items below because it unblocks a true B4 boundary test, unblocks future Slice C/D persistence assertions, and is a precondition for any honest "drives the real write path" assertion in this codebase. Needs an architectural decision (testcontainers vs. trait seam vs. sqlx-mock) — a remote agent should open this with a short design proposal first, not a code PR.
5. **Remote agent: B4 (real)** — once B6 lands, replace the helper-only test with one that constructs a real `StrategyRepository`, drives `record_evaluation` for each `ChampionDecision`, and asserts both the in-memory `summary.transition_counts` and the actual rows in `strategy_selected_signal` / `strategy_champion_drift_events`.
6. **Remote agent: S4 + B5** — observability hardening. Best to do together since both add metrics: the projection-cost counter (S4) and the per-decision Prometheus metrics on `/metrics` (B5). Currently both are log-only; alert rules cannot key off them.
7. **Remote agent: S6** — UI nit, render `--`/`BLOCKED` instead of champion name in `CHAMPION_PROJECTION_FAILED` state. Trade tab + Analytics tab.
8. **Remote agent: X1** — update the host audit script in `docs/27` to read `cue.selection_state` once Slice A is on the host.
9. **After commit + host data: Slice C planning** — must start with reproducing host lineage in a reviewable local branch per `docs/26` §Slice C step 0.

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
