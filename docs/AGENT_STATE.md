# Agent State (Living)

> **This file is the second mandatory read for every agent, after `AGENTS.md`.**
> See `AGENTS.md` §8 for the topology, work-allocation rules, and hydration sequence.

---

## Pin

| Field | Value |
|---|---|
| Last updated (UTC) | 2026-05-03 |
| Updated by | local agent |
| Repo HEAD pin (committed) | `cf78cad` on branch `codex/fix-clippy-run-24549051096` |
| Origin | `https://github.com/apexpark/cryptopairs.git` |
| Working-tree state | **DIRTY** — Slice A and Slice B for champion-selection integrity are present in the operator’s working tree but **not yet committed**. See §"Currently In Flight". |

If `git rev-parse HEAD` does not match the pin above, this file is stale; stop and request operator refresh per `AGENTS.md` §7.

---

## Currently In Flight

### Sprint: Champion-Selection Integrity (docs/26 + docs/27)

Status snapshot of the four slices defined in `docs/26-champion-selection-integrity-fix-spec.md`:

| Slice | Status | Owner | Notes |
|---|---|---|---|
| Slice A — Separate evaluation from champion presentation | **Implemented in working tree, awaiting commit + push** | local | Verified: schema validation passed; lib test `evaluate_pair_honors_preferred_variant_override` passed; tsc passed. Bin-test compile not run end-to-end. |
| Slice B — Make transition accounting complete | **Implemented in working tree, awaiting commit + push** | local | Verified: `cargo check --tests --bin strategy-service` passed; `cargo test selection_transition_counts` passed; clippy passed; reoptimize schema validation passed (bumped to 0.2.0). |
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

- Slice A: `cue.selection_state` contract added with strict enums for `source` and `validation_state`; cue endpoint now projects champion-consistent cues or fails closed; UI surfaces consume `selection_state`. `specs/contracts/strategy_pairs_cues_response.schema.json`, `specs/examples/strategy_pairs_cues_response.example.json`, `apps/web/src/types.ts`, `apps/web/src/App.tsx`, `services/strategy-service/src/lib.rs`, `services/strategy-service/src/main.rs`. Tests: `cue_for_pairs_response_*` + `evaluate_pair_honors_preferred_variant_override`.
- Slice B: `SelectionTransitionCounts` struct now records all four `ChampionDecision` outcomes; reoptimize observability emits all four counts and warns on `selected_rows_written > 0` with zero accounted decisions; reoptimize response schema bumped to 0.2.0 with additive `initialize_decisions` / `unchanged_decisions`. Drift table remains scoped to `KEEP_CHAMPION` / `PROMOTE_CHALLENGER` only.

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
| B1 | low | Add `accumulate(other)` unit test on `SelectionTransitionCounts`. | open |
| B2 | low | Add serde round-trip test asserting `initialize_decisions` / `unchanged_decisions` / `champion_promotions` / `champion_locks` appear at the top level of `ReoptimizeResponse` (locks the `serde(flatten)` wire shape). | open |
| B3 | low | One-line schema comment explaining `initialize_decisions` / `unchanged_decisions` are kept optional in `required` for backward compatibility but always populated by the server. | open |
| B4 | medium-low | Integration-shaped test that drives `record_evaluation` and asserts `summary.transition_counts` matches an expected `ChampionDecision` distribution. Highest-value follow-up. | open |
| B5 | low | Materialize the per-decision counts as actual Prometheus-style metrics (`strategy_selection_transition_total{decision,timeframe}` and `strategy_selection_rows_updated_without_transition_total{timeframe}`) rather than relying on log lines for alerting. Spec named these in `docs/26` §Observability. | open |

### Cross-cutting

| ID | Severity | Description | Status |
|---|---|---|---|
| X1 | low | Audit script in `docs/27` §"Live Cue Mismatch Audit" still reads `cue.selected_variant` and `cue.selected_signal_config.source`. Update to use `cue.selection_state` once Slice A is on the host. | open |
| X2 | low | Operator-facing reads of `cue.selected_variant` in any other surface (Trade and Analytics now updated, but check everywhere) should migrate to `selection_state.best_variant` / `stored_champion_variant` per the spec. | open |

---

## Next Recommended Move

Pickable items, in priority order:

1. **Operator action: commit Slice A + B and push.** Until committed, no remote agent can see this work and Slice C planning cannot proceed against the actual implemented code. Recommended commit boundaries: one commit for Slice A (cue selection_state + champion-consistent projection), one for Slice B (transition accounting + reoptimize 0.2.0).
2. **Operator action: produce the host verification output** (B-Host-Lineage above). Once captured, post into this file under §"Blocked / Waiting On".
3. **Remote agent: B4** — write the integration-shaped `record_evaluation` test. Closes the central guarantee of Slice B.
4. **Remote agent: B1, B2, B3, S8** — quick defensive adds. Can be batched into one PR.
5. **Remote agent: S4, B5** — observability hardening. Best to do together since both add metrics.
6. **After commit + host data: Slice C planning** — must start with reproducing host lineage in a reviewable local branch per `docs/26` §Slice C step 0.

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
