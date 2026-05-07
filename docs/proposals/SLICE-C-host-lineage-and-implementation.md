# Proposal: Slice C host lineage import and neutral champion selection

> **Status**: design proposal, awaiting operator approval. No code in this PR.
>
> **Author**: codex (remote agent), 2026-05-07.
>
> **Branch**: `codex/slice-c-planning-design`. Sprint base: `codex/fix-clippy-run-24549051096`.
>
> **Item addressed**: Slice C planning in `docs/AGENT_STATE.md` §"Currently In Flight".

---

## 1. Problem

Slice C is about a host-only runtime bug. The relevant facts are not in the
local service code on this branch; they are the captured host verification
outputs in `docs/AGENT_STATE.md` §"Blocked / Waiting On" ->
`B-Host-Lineage`, plus the host line ranges named in
`docs/27-champion-selection-independent-review-brief.md`.

The captured host identity is:

- host commit: `4dd118242414d38ad33ae50bb433d4988d5276da`
- host branch: `rc/live-trial`
- host dirty status: modified `CHANGELOG.md` and
  `services/strategy-service/src/main.rs`

The captured database/API state shows the runtime is active but not producing
post-cutover challenger-vs-champion drift evidence:

- `strategy_selected_signal` has `48` rows: `16` each for `1m`, `15m`, and `1h`.
- `1m` has `12 / 16` `LEGACY_ROW_FALLBACK` rows, but all three timeframes also
  have `AUTO_CHAMPION` rows.
- historical `strategy_champion_drift_events` include both `KEEP_CHAMPION` and
  `PROMOTE_CHALLENGER` counts by timeframe:
  - `1m`: `KEEP_CHAMPION=12524`, `PROMOTE_CHALLENGER=1852`
  - `15m`: `KEEP_CHAMPION=11322`, `PROMOTE_CHALLENGER=727`
  - `1h`: `KEEP_CHAMPION=8622`, `PROMOTE_CHALLENGER=592`
- post-cutover drift events are `0`.
- candidate pipeline tables are empty: `strategy_candidate_runs=0`,
  `strategy_candidate_probation=0`, `strategy_candidate_actions=0`.
- live cue mismatch audit found displayed `selected_variant` differs from the
  highest-score response variant in:
  - `1m`: `11 / 16`
  - `15m`: `12 / 16`
  - `1h`: `7 / 16`

The host code path called out by `docs/27` is:

- `/opt/cryptopairs/services/strategy-service/src/main.rs:1565-1587` loads the
  existing selected config before evaluation.
- `/opt/cryptopairs/services/strategy-service/src/lib.rs:977-1088` prefers the
  configured variant when present and valid.
- `/opt/cryptopairs/services/strategy-service/src/main.rs:2746-2848` uses
  `evaluation.cue.selected_variant` as the challenger for champion transition.
- `/opt/cryptopairs/services/strategy-service/src/main.rs:6328-6366` is another
  host-only region the implementation PR must inspect before coding.

The Slice C bug model from `docs/26` is therefore:

1. the host loads the incumbent selected config before evaluation;
2. evaluation may prefer that configured incumbent variant;
3. champion transition receives an incumbent-shaped `evaluation.cue.selected_variant`
   as the challenger;
4. the steady state collapses toward `UNCHANGED`;
5. `UNCHANGED` does not create `strategy_champion_drift_events` rows, so the
   system can keep selected rows fresh while producing zero post-cutover drift
   evidence.

This is stronger than a presentation-only mismatch. The mismatches prove the
public response often contains a stored/displayed variant that is not the
highest-score response variant, while the zero post-cutover drift events prove
the current runtime is not exposing the expected `KEEP_CHAMPION` /
`PROMOTE_CHALLENGER` competition that was historically present.

## 2. Preconditions

This proposal **cannot** lead directly to an implementation PR until the
operator imports the host `rc/live-trial` lineage into a reviewable local
branch.

This PR can plan from:

- captured host verification outputs in `docs/AGENT_STATE.md`;
- host path and line ranges listed in `docs/27`;
- local Slice A, Slice B, and B6 behavior already committed on the sprint base.

This PR cannot provide exact implementation diffs because the actual host code
at `4dd118242414d38ad33ae50bb433d4988d5276da`, including dirty host changes, is
not present in this repository checkout. The implementation PR must first
verify the host-only code path against imported, version-controlled code.

## 3. Import strategy options

### Option A - merge `rc/live-trial` directly to `main`

Merge the host branch into `main` and accept whatever divergence lands.

**Review cost**: high. The diff will mix host lineage recovery, unrelated host
drift, dirty-file reconciliation, and any conflicts with the current sprint
base.

**Blame preservation**: good if the host branch has meaningful commits. Poor if
the host dirty state is reconstructed in one manual merge commit.

**Conflict risk with sprint base**: high. The sprint base has already landed
Slice A, Slice B, B6, and tooling changes. Direct merge raises the chance that
reviewers must reason about host divergence and current sprint behavior in one
large review.

**Ease of subsequent Slice C implementation commits**: poor to medium. Once the
lineage is on `main`, Slice C can target a normal branch, but any accidental
host-only divergence becomes part of the long-lived branch before review.

**Verdict**: not recommended. This path maximizes pollution risk on the
canonical branch.

### Option B - cherry-pick host-only commits onto a review branch

Create a new branch, proposed name `cherry-picked-from-rc-live-trial`, from the
current sprint base and cherry-pick the host-only commits needed to reproduce
the selected-config/provenance runtime.

**Review cost**: medium. Reviewers see host-only behavior as atomic commits
against the current sprint base. Any omitted host commit is visible as an
operator decision rather than hidden in a broad merge.

**Blame preservation**: best if the host branch has meaningful commits. Each
imported commit keeps its original author/time/message lineage, subject to
normal cherry-pick metadata.

**Conflict risk with sprint base**: medium. Conflicts still happen in
`services/strategy-service/src/main.rs` and `src/lib.rs`, but they are resolved
one commit at a time. This makes interactions with Slice A cue projection,
Slice B transition accounting, and B6 tests easier to inspect.

**Ease of subsequent Slice C implementation commits**: best. Once the host
lineage branch is reviewed, the Slice C implementation can build on a clean
branch that already contains the host code path, with no main pollution.

**Verdict**: recommended.

### Option C - squash `rc/live-trial` into one review commit

Import the net host diff as a single commit on a planning/import branch.

**Review cost**: medium to high. The review has one diff, which is convenient,
but the reviewer loses the historical grouping that explains why each host
change exists.

**Blame preservation**: poor. A squash collapses host lineage into one author
and one timestamp unless the operator manually preserves detail in the commit
message.

**Conflict risk with sprint base**: medium. Conflicts are resolved once, but the
resulting single commit can hide which host behavior caused each conflict.

**Ease of subsequent Slice C implementation commits**: medium. It is better
than direct merge because `main` stays clean, but worse than cherry-pick because
future debugging cannot follow the original host commit boundaries.

**Verdict**: acceptable fallback if the host history is messy or not
recoverable as commits, but not the first choice.

### Recommended import path

Use **Option B**: cherry-pick the required `rc/live-trial` host-only commits
onto `cherry-picked-from-rc-live-trial` from the current sprint base. Include
the host dirty `services/strategy-service/src/main.rs` state as an explicit
operator-reviewed commit if it is part of live behavior. Do not merge directly
to `main` before review.

## 4. Slice C implementation strategy options

These options apply only **after** the host lineage is imported and reviewed.

### Option A - replace incumbent-biased evaluation with neutral evaluation

Change the host path so evaluation computes the neutral best variant from the
current candle snapshot. Persisted champion config is still loaded, but only as
comparison input for champion-vs-challenger decisioning. It must not determine
which variant is evaluated as the challenger.

**Pros**

- Smallest steady-state model: one selection path, one source of truth for
  `best_variant`.
- Directly addresses the captured symptom: transition receives the neutral best
  challenger, so `UNCHANGED`, `KEEP_CHAMPION`, and `PROMOTE_CHALLENGER` become
  reachable based on real competition.
- Avoids preserving a known-bad path longer than necessary.

**Cons**

- Higher rollout risk because the runtime changes behavior immediately once
  deployed.
- If imported host code contains hidden parameter dependencies, direct removal
  can fail rows that previously evaluated through incumbent config.

### Option B - add a feature flag for neutral champion selection canary

Implement neutral evaluation as the new path, but guard rollout with a feature
flag. Keep the current incumbent-biased path only as a temporary canary/rollback
path, retire it after one approved observation window.

The flag must not relax trading safeguards. During canary:

- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` stays set.
- live `ENTRY` / `EXIT` stays disabled.
- cues remain research-visible until operator verification confirms selection
  integrity.

**Pros**

- Aligns with `AGENTS.md` patch slicing guidance that Slice C implementation
  should land behind a feature flag.
- Lets the operator compare current vs neutral behavior during one observation
  window without enabling live trading.
- Provides a rollback if neutral evaluation exposes incomplete per-variant
  parameterization in the imported host code.

**Cons**

- Temporarily carries two paths, increasing review surface.
- If the flag defaults to the incumbent-biased path for too long, the system can
  keep producing the same zero-post-cutover-drift symptom.
- Requires explicit retirement criteria so the bad path does not become
  permanent compatibility debt.

### Option C - shadow neutral evaluation before changing persistence

Compute the neutral best variant in parallel, emit mismatch/transition
diagnostics, but leave persistence and champion transition on the incumbent
biased path for a preliminary observation window.

**Pros**

- Lowest behavior risk.
- Gives the operator a before/after diagnostic dataset.

**Cons**

- Does not fix the bug during the first implementation window.
- The captured host data already shows mismatch and zero post-cutover drift, so
  a diagnostics-only phase mostly repeats known evidence.
- Prolongs the period in which selected rows update without trustworthy
  challenger competition.

### Recommended implementation path

Use **Option B**, but make the flagged neutral path implement Option A's
semantics. In other words: neutral evaluation is the fix; the feature flag is
the rollout guard, not a second design.

The implementation should make the transition path receive:

- neutral `best_variant` from the current evaluation window;
- stored champion variant/config loaded separately as incumbent comparison
  input;
- the existing score-delta/hysteresis decision function;
- Slice A `selection_state` projection that keeps presented cue and best-state
  diagnostics separate;
- Slice B transition counts for all four decisions.

This turns the captured `0` post-cutover drift-event state into observable
competition as follows:

- if neutral best equals stored champion, the transition records `UNCHANGED`
  in Slice B counts;
- if neutral best differs but does not beat the existing promotion threshold,
  the transition records `KEEP_CHAMPION` and writes a drift event;
- if neutral best differs and beats the threshold, the transition records
  `PROMOTE_CHALLENGER`, writes a drift event, and updates the selected row;
- if no champion exists, the transition records `INITIALIZE`.

The expected healthy observation window is therefore not "all promotions"; it
is a steady stream of accounted `UNCHANGED`, `KEEP_CHAMPION`, and
`PROMOTE_CHALLENGER` outcomes, with `KEEP_CHAMPION` and `PROMOTE_CHALLENGER`
non-zero whenever neutral best differs from the stored champion.

## 5. Recanonicalization preview for Slice D

Slice C does not recanonicalize `LEGACY_ROW_FALLBACK` rows. It does, however,
make legacy provenance more visible.

The captured host data shows `12 / 16` `1m` selected rows are
`LEGACY_ROW_FALLBACK`, while `15m`, `1h`, and `4 / 16` `1m` rows are
`AUTO_CHAMPION`. That means legacy rows are not the whole bug, but they will
become higher-priority cleanup once neutral evaluation is active:

- neutral evaluation may produce legitimate drift decisions for legacy rows;
- legacy rows may lack canonical serialized config or trusted provenance;
- if per-variant parameters cannot be compared safely, those rows must fail
  closed into a repair state rather than silently inherit the incumbent.

Slice D should clean this up by recanonicalizing only rows that can be
re-evaluated, serialized canonically, and attributed to a trusted current
source. Slice C should not treat recanonicalization as a prerequisite for
neutral evaluation, but it must not allow legacy provenance to become
trade-eligible by accident.

## 6. Acceptance criteria for follow-up implementation PRs

### Import PR acceptance

- Host lineage is present in a reviewable branch based on the current sprint
  base.
- The imported code contains or reconstructs the documented host regions:
  - `services/strategy-service/src/main.rs` equivalent of host
    `:1565-1587`;
  - `services/strategy-service/src/main.rs` equivalent of host
    `:2746-2848`;
  - `services/strategy-service/src/main.rs` equivalent of host
    `:6328-6366`;
  - `services/strategy-service/src/lib.rs` equivalent of host `:977-1088`.
- The import PR states whether the live dirty host changes were included,
  omitted, or reconstructed, with rationale.
- No direct merge to `main` occurs until local review accepts the import.

### Behavior assertions

- Evaluation computes neutral best variant without using the stored champion as
  preselection input.
- Stored champion config may be loaded only as incumbent comparison input.
- When stored champion differs from neutral best, the cue/reoptimize path must
  surface drift state and the persistence path must write the appropriate
  `strategy_champion_drift_events` row for `KEEP_CHAMPION` or
  `PROMOTE_CHALLENGER`.
- The cue endpoint must expose the neutral best and stored champion separately
  through Slice A `selection_state`; it must not reintroduce hybrid
  champion/challenger cue fields.
- Transition counts must include accounted `UNCHANGED`, `KEEP_CHAMPION`, and
  `PROMOTE_CHALLENGER` decisions during the next operator-approved observation
  window. `KEEP_CHAMPION` and `PROMOTE_CHALLENGER` must be non-zero when
  neutral best differs from stored champion during that window.
- `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true` remains enabled and live `ENTRY` /
  `EXIT` remains disabled until operator host verification passes.

### Required tests

Use the pg-backed integration harness from B6
(`services/strategy-service/tests/repository_integration.rs`) or an extension
of it.

The implementation PR must add tests that prove:

- `record_evaluation` writes selected rows and drift-event rows when neutral
  best differs from stored champion and the decision is `KEEP_CHAMPION`;
- `record_evaluation` writes selected rows and drift-event rows when neutral
  best differs from stored champion and the decision is `PROMOTE_CHALLENGER`;
- `record_evaluation` records `UNCHANGED` counts without drift rows when
  neutral best equals stored champion;
- cue construction keeps `selection_state.best_variant` and
  `selection_state.stored_champion_variant` distinct when drift is active;
- cue projection remains internally consistent and fails closed if champion
  projection cannot be recomputed;
- legacy fallback rows either evaluate neutrally with explicit safe comparison
  inputs or enter a blocked/repair state.

If deterministic fixture candles are available in the imported host lineage,
add a replay/regression test that replays a fixed window and asserts stable
best variant, champion decision, and persisted outcome. If they are not
available, the implementation PR must state that gap explicitly and keep the
pg-backed integration tests as the minimum acceptance bar.

### Required docs

The implementation PR must update:

- `docs/AGENT_STATE.md` with the Slice C status and any remaining operator-only
  host verification steps;
- `docs/26-champion-selection-integrity-fix-spec.md` if accepted behavior
  differs from this proposal;
- `docs/27-champion-selection-independent-review-brief.md` if host audit
  commands need to use `cue.selection_state` instead of `cue.selected_variant`;
- the relevant hosted runbook if operators must set a new feature flag or run a
  new verification command;
- `CHANGELOG.md` if runtime behavior, operator workflow, or public contracts
  change.

## 7. Effort estimate

### Import phase

- Best case: `0.5-1 day` if `rc/live-trial` history is clean and cherry-picks
  apply with small conflicts.
- Expected case: `1-2 days` to cherry-pick, reconcile dirty host
  `main.rs` state, resolve conflicts with Slice A/B code, and open a reviewable
  import PR.
- Worst case: `2-4 days` if host dirty state must be reconstructed manually or
  host history does not contain clean commits.

### Implementation phase

- Best case: `1.5-2 days` for neutral path behind a flag plus focused
  pg-backed integration tests.
- Expected case: `3-5 days` including import review feedback, per-variant
  parameter comparison fixes, docs/runbook updates, and operator verification
  prep.
- Worst case: `1-2 weeks` if imported host code proves that some variants rely
  on incumbent-specific serialized config that cannot be compared fairly
  without a deeper model change.

## 8. Preconditions and risks

- Operator SSH access remains required for post-implementation host
  verification. Remote agents must not re-query the host.
- The implementation PR must not start until the host lineage is in a
  reviewable local branch.
- If Option B is approved, the canary period still has live-trading exposure as
  a risk category. Mitigation: keep `STRATEGY_BLOCK_ON_CHAMPION_DRIFT=true`,
  keep live `ENTRY` / `EXIT` disabled, and treat cues as research-visible only.
- Slice C must preserve Slice A cue projection semantics. It must not collapse
  `selection_state.best_variant` and `selection_state.stored_champion_variant`
  back into one ambiguous `selected_variant`.
- Slice C must preserve Slice B transition accounting. It must not make
  `KEEP_CHAMPION` / `PROMOTE_CHALLENGER` drift rows disappear behind
  `UNCHANGED`.
- Legacy fallback provenance can make neutral comparison unsafe for some rows.
  Those rows must fail closed into repair/blocked state, not inherit the
  incumbent silently.
- Direct merge of host lineage to `main` risks importing dirty or unrelated
  host changes before local review.

## 9. Open questions for operator approval

1. Import path: approve the recommended
   `cherry-picked-from-rc-live-trial` branch, or choose direct merge/squash
   instead?
2. Dirty host state: should the modified host `CHANGELOG.md` and
   `services/strategy-service/src/main.rs` be imported exactly as live,
   reconstructed as review commits, or excluded if they are local-only notes?
3. Rollout path: approve feature-flagged neutral selection canary (recommended)
   or require direct replacement with no incumbent-biased fallback?
4. Observation window: what timeframe and success thresholds define "healthy"
   after canary? Proposed minimum: all three timeframes show accounted
   `UNCHANGED` decisions and non-zero `KEEP_CHAMPION` / `PROMOTE_CHALLENGER`
   when neutral best differs from stored champion.
5. Host verification timing: who will run the post-implementation SSH/database
   checks, and should they be captured back into `docs/AGENT_STATE.md` before
   Slice D begins?

## 10. Out of scope

- No code changes in this PR.
- No `Cargo.toml`, lockfile, schema, API, UI, or runbook changes in this PR.
- No host SSH or live database re-query by remote agents.
- No Slice D recanonicalization design beyond the preview in §5.
- No enabling live `ENTRY` / `EXIT`.
- No redesign of candidate generation, probation, or action tables.
- No removal of Slice A `selection_state` or Slice B transition accounting.
- No semantic redefinition of existing required fields such as
  `cue.selected_variant` in this proposal PR.
