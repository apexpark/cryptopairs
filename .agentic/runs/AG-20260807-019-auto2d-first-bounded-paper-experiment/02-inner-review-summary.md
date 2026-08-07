# Inner Review Summary — AG-20260807-019

Verdict: `CLEAN`

## Scope reviewed

Reviewed the complete local PR #263 diff from exact merged-main base
`c5a5c1a370112567073eaf00088ff4c121a0170d`, with AG-20260807-019 isolated
from its exact starting head
`26d3bfcd7579cb7b9266e6e3698c4f0e87099b14`, for:

- the separately versioned first-bounded-paper-experiment decision route;
- the backward-compatible schema and canonical examples;
- deterministic governor qualification, ranking, concentration skip and
  selection;
- independent AUTO-2D recomputation and root-local immutable-universe record;
- both Operator runbooks, compatibility and CHANGELOG;
- production-shaped synthetic, mutation, schema and command-safety tests; and
- append-only governance under AG-20260807-019.

No host, real artifact, capture, replay, E3, configuration, eligibility,
controller start, trial root/process, paper/live trading, service, deployment,
secret, CI-1, OBS-1, OBS-3, AUTO-3, merge or unattended-loop action occurred.

## Contract and policy angle

- The historical exact policy remains the default and its existing eligible
  and blocked examples remain byte-identical.
- The new exact policy version differs from the historical envelope only in
  null removal/churn limits and four explicit route metadata fields. Complete
  governor-config equality is required; partial, unknown or mutated configs
  fail before output.
- Both routes still require two complete comparable schema-v2 snapshots,
  identical selector configuration, exact raw hashes and provenance,
  86,400-second cutoff separation, 1,800-second freshness, complete selector
  churn, positive per-key edge, and the existing per-key count/ratio gates.
- `NONE` and null remain distinct and non-actionable. Unknown selector
  directions and non-actionable realized-paper directions still reject before
  output. Realized-paper and selector-view evidence remain separate
  set-membership streams with no numeric merge.
- For the experiment route only, removals and churn are recomputed and reported
  but do not block eligibility. At most four entries, two additions, two
  selector-exploration entries and every pair, pair/variant/direction,
  full-instrument and new-addition concentration limit remain active.
- The schema requires route-specific methodology and explicitly false later
  paper/live promotion authority. Historical decisions cannot smuggle those
  fields or reinterpret the new route.

## Governor and independent-controller angle

- Production-shaped synthetic evidence produces four qualified candidates,
  selects exactly three in deterministic order, and skips the fourth for the
  new-addition instrument concentration. Removal count 3 and reported churn
  1.25 do not gate the isolated route.
- The identical evidence under the historical route remains
  `GOVERNOR_BLOCKED` with `TRANSITION_LIMITS_UNSATISFIABLE`.
- The AUTO-2D controller does not import the v2 governor or any test oracle.
  Its independently duplicated complete policy objects, route resolution,
  policy hash, qualification, ranking, allocation, calculations, decision ID,
  methodology and authority fields reproduce the governor output exactly.
- Controller verification accepts only exact
  `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` output. The controller binding
  records report-only static overlap, unchanged shared paper configuration,
  controller-owned immutable trial-root scope, false later-promotion authority
  and the requirement for a separate promotion policy decision.
- Existing maximum-two-open, one-exploration-position, holding, cooldown,
  candidate-age, automatic-start-age, entry-window, exit-only and hard-runtime
  controls are unchanged. No fallback, restart, shared configuration write,
  eligibility promotion, self-approval, exchange route or live route was
  added.

## Compatibility witness

- The current historical route and the pre-amendment implementation at exact
  head `26d3bfcd7579cb7b9266e6e3698c4f0e87099b14` were run in memory against the
  same production-shaped historical inputs. Their JSON outputs were
  byte-identical at SHA-256
  `e2bc4e42d4ab1d8a9506bf6946b22485a08a6471c524960acee02d8a3e54975d`;
  their Markdown outputs were byte-identical at SHA-256
  `8f0025328aac3ed7cc22956ec5d586c4cf8a39c3df84d79797ba674b1acd4a94`.
- Existing v2 eligible/blocked examples, the v1 governor, B2-c scorer, paper
  engine/contracts, provenance contract/examples, dependencies, CI, services
  and runtime configuration are unchanged.
- The decisions register has one appended row and zero deletions.

## Findings repaired during inner review

1. The initial focused set proved experiment eligibility and historical
   compatibility but did not separately pin the new route's stale-evidence
   blocked-empty result or an exact-config mutation's no-artifact refusal.
   Added both non-vacuous tests; no production behavior changed.

No unresolved P1, P2 or P3 finding remains.

## Verification evidence

- Focused governor/controller/contract suite: **124 passed**.
- Full canonical `tools/scripts` suite under the configured Python with active
  RFC 3339 format validation: **385 passed plus 70 subtests**, with one
  pre-existing third-party `dateutil` deprecation warning.
- Bounded E4: **25 passed**, covering disabled/no-I/O defaults, two-gate start
  refusal, experiment and historical route outcomes, deterministic output,
  verify-only preservation, malformed/hash/symlink/mutation rejection,
  concurrency, exclusive output, retained partial roots and no automatic
  repair or retry.
- Draft 2020-12 schema meta-validation and all v2 decision examples pass with
  active RFC 3339 format checking; every JSON under `specs/` parses.
- Ruff check/format, Python 3.9 source compilation, `git diff --check`, exact
  base ancestry, policy parity, exact route delta, independent-import audit,
  protected hashes and scope checks pass.
- `/usr/bin/python3` lacks the repository's already documented optional
  `rfc3339-validator`, so its full-suite attempt deliberately failed the two
  pre-existing non-vacuity guards. The configured Anaconda Python includes the
  validator and passed the complete suite. CI-1 remains separately scoped and
  was not changed.
- Genuine E3: **NOT RUN — separately gated**.

## Governance position and next gate

The amended PR head may now be committed, pushed and kept as Tier 3 draft.
The prior Claude CLEAN verdict is bound only to obsolete head
`26d3bfcd7579cb7b9266e6e3698c4f0e87099b14`; Claude must independently review
the new exact head. A clean review and green CI are not merge or operational
authority. Genuine E3, merge, host alignment/preflight and one bounded paper
trial each remain separately gated.
