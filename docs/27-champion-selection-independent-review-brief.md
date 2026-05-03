# Champion Selection Independent Review Brief

## Purpose

Hydrate a second agent on the codebase and runtime problem so it can independently review the current findings without inheriting implementation bias.

This document is for review and verification, not for coding.

## Review Goal

Determine whether the current finding is sound:

- the strategy runtime may be preserving incumbent champions in a way that prevents healthy challenger competition from being observed or trusted

The second agent should specifically test whether:

1. the finding is correct
2. a narrower explanation fits the evidence better
3. the proposed fix space is appropriately scoped and fail-closed

## Required Review Posture

The second agent should:

1. assume nothing not backed by repo or host evidence
2. separate local-repo facts from host-runtime facts
3. prioritize safety and selection correctness over convenience
4. treat live tradability as blocked unless selection integrity is proven

The second agent should not:

1. commit code
2. liberalize execution behavior
3. resolve the issue by removing blocking logic alone

## Fast Hydration Sequence

Read these local docs first:

1. `AGENTS.md`
2. `docs/10-architecture.md`
3. `docs/12-risk-and-execution-policy.md`
4. `docs/14-testing-standards.md`
5. `docs/15-observability-and-alerting.md`
6. `docs/02-versioning-and-releases.md`
7. `docs/03-contracts-and-compatibility.md`
8. `docs/26-champion-selection-integrity-fix-spec.md`

Then inspect these local code paths:

1. `services/strategy-service/src/lib.rs:931-1023`
2. `services/strategy-service/src/main.rs:900-933`
3. `services/strategy-service/src/main.rs:2010-2068`
4. `services/strategy-service/src/main.rs:4645-4674`
5. `specs/contracts/strategy_pairs_cues_response.schema.json`
6. `specs/contracts/strategy_pairs_reoptimize_response.schema.json`

## Local Repo Findings To Confirm

The second agent should validate or refute these statements:

1. local evaluation chooses the highest-score variant during `evaluate_pair(...)`
2. champion transition compares the stored champion against `evaluation.cue.selected_variant`
3. the cue endpoint rewrites the displayed cue back to the stored champion if drift exists
4. that rewrite mutates only `selected_variant` and `opportunity_score`, leaving other cue fields challenger-derived
5. drift rows are only recorded for `KEEP_CHAMPION` and `PROMOTE_CHALLENGER`, not `INITIALIZE` or `UNCHANGED`

If any of those are wrong, the review should say so explicitly with file references.

## Host Runtime Caveat

The Hetzner runtime is not identical to the local repo. It contains newer selection-config and provenance logic that was verified directly on May 2, 2026.

Treat these as host-only findings unless independently reproduced in the local branch:

1. selected config provenance including `LEGACY_ROW_FALLBACK`
2. incumbent-biased evaluation path through `selected_signal_config`
3. current `rc/live-trial` branch divergence from GitHub

## Host Verification Steps

Use read-only verification on host `cryptopairs`.

### Repository Identity

Run:

```bash
ssh cryptopairs 'cd /opt/cryptopairs && git branch --show-current && git rev-parse HEAD && git status --short'
```

Questions:

1. What branch is live?
2. Is it dirty?
3. Is it reproducible from the local repo?
4. What exact host commit should Slice C be designed against?

### Selection Row State

Run:

```bash
ssh cryptopairs "docker exec cryptopairs-timescaledb psql -U cryptopairs -d cryptopairs -At -F '|' -c \"select pair_id, timeframe, signal_variant, (config_json::jsonb->>'source') as source, updated_at from strategy_selected_signal order by timeframe, pair_id;\""
```

Questions:

1. How many rows exist per timeframe?
2. How many rows are `LEGACY_ROW_FALLBACK`?
3. Are rows still updating?

### Drift / Candidate Activity

Run:

```bash
ssh cryptopairs "docker exec cryptopairs-timescaledb psql -U cryptopairs -d cryptopairs -At -F '|' -c \"select timeframe, decision, count(*) from strategy_champion_drift_events group by timeframe, decision order by timeframe, decision; select '---'; select count(*) from strategy_champion_drift_events where event_at >= '2026-04-19 03:26:54+00'; select '---'; select 'candidate_runs', count(*) from strategy_candidate_runs union all select 'candidate_probation', count(*) from strategy_candidate_probation union all select 'candidate_actions', count(*) from strategy_candidate_actions;\""
```

Questions:

1. Are promotions and keeps historically present?
2. Are any drift events recorded after the current cutover?
3. Is the candidate pipeline active?
4. Would an initialize-heavy restart window explain a zero-drift period, or not?

### Live Cue Mismatch Audit

Run:

```bash
for tf in 1m 15m 1h; do
  curl --max-time 30 -s "https://api.apexpark.io/strategy/v1/strategy/pairs/cues?timeframe=$tf&limit=100" |
    jq '{timeframe, total: (.cues | length), mismatch_count: ([.cues[] | select(.cue.selected_variant != (.variants | max_by(.opportunity_score).variant))] | length), mismatches: [.cues[] | {pair_id: .cue.pair_id, source: (.cue.selected_signal_config.source // "UNKNOWN"), selected_variant: .cue.selected_variant, selected_score: .cue.opportunity_score, best_variant: (.variants | max_by(.opportunity_score).variant), best_score: (.variants | max_by(.opportunity_score).opportunity_score)} | select(.selected_variant != .best_variant)]}'
done
```

TODO after Slice A:

- update this audit to compare `cue.selection_state.stored_champion_variant` and `cue.selection_state.best_variant`
- update the source read to the new `selection_state` / validation-state fields once they are present

Questions:

1. How often is the displayed/stored selected variant not the highest-score current variant?
2. Is that concentrated in legacy rows, or broader?
3. Are the score gaps small enough to be explained by hysteresis, or large enough to be suspicious?
4. When drift exists, does the cue become a hybrid of champion and challenger fields?

### Host Code Path

Inspect these host-only ranges:

1. `/opt/cryptopairs/services/strategy-service/src/main.rs:1565-1587`
2. `/opt/cryptopairs/services/strategy-service/src/main.rs:2746-2848`
3. `/opt/cryptopairs/services/strategy-service/src/main.rs:6328-6366`
4. `/opt/cryptopairs/services/strategy-service/src/lib.rs:977-1088`

Questions:

1. Does the host runtime preload the incumbent config before evaluation?
2. Does evaluation prefer the incumbent variant when config is present?
3. Is `cue.selected_variant` later rewritten for presentation?
4. Is the decision path capable of entering `KEEP_CHAMPION` or `PROMOTE_CHALLENGER` in current steady state?
5. Can the host lineage be pulled back into a local reviewable branch before Slice C is approved?

## Claims To Validate Or Refute

The second agent should explicitly assess these claims:

1. `48` selected rows do not prove healthy champion competition.
2. The `12` legacy `1m` rows are not the whole problem.
3. The larger issue is incumbent-preserving rewrite behavior.
4. The current runtime can keep rows fresh while providing zero post-cutover drift evidence.
5. Removing the legacy block alone would be unsafe and insufficient.

Each claim should be marked:

1. confirmed
2. partially confirmed
3. refuted

## Alternative Explanations To Consider

The second agent should actively test these alternatives:

1. the mismatch rate is expected because hysteresis/cooldown is doing exactly what it should
2. the drift-event gap is only an instrumentation bug, not a decision-path bug
3. the cue endpoint is presentation-only, while actual transition logic remains healthy
4. the current cutover window is too narrow or atypical to judge normal behavior
5. the host branch contains a temporary experiment not represented in the local repo

If an alternative explanation survives review, it should be stated clearly.

## Expected Deliverable

Ask the second agent to produce:

1. findings first, ordered by severity
2. exact file and line references for local repo facts
3. exact host paths and command outputs summarized for runtime facts
4. a short section labeled `Where The Current Analysis Is Strong`
5. a short section labeled `Where The Current Analysis Is Weak`
6. a final recommendation on whether the proposed fix direction is:
   - too broad
   - about right
   - too narrow
7. an explicit note on whether immediate operational safeguards should stay in place while Slice A is built

## Review Constraints

The second agent should not:

1. assume the host is identical to GitHub
2. treat public cue data as proof of healthy promotion logic
3. accept `selected_variant` at face value without comparing it to `.variants`
4. recommend enabling live execution before selection integrity is resolved

## Practical Recommendation

Use the second agent to answer:

1. Is the current finding materially correct?
2. Which slice should be implemented first?
3. Which claims still require stronger proof before code changes?

That keeps responsibilities clean:

1. Codex handles implementation
2. the second agent challenges assumptions, verifies evidence, and reviews risk
