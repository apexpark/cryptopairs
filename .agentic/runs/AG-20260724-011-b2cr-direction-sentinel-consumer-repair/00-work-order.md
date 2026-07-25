---
id: AG-20260724-011
title: B2-cR direction-sentinel consumer repair
repo: cryptopairs
base_branch: main
base_sha: 88f12eab5ec29c19b91a27497c1658c6cf109002
working_branch: codex/b2cr-direction-sentinel-repair
worker_tier: T1
required_evidence_level: E3
status: dispatched
---

# Work Order

## Objective

Repair the narrow AUTO-2B.2 B2-c consumer incompatibility proven by the
Operator-run B2-d evidence pass: accept the strategy service's explicit
non-actionable `direction_hint="NONE"` sentinel as a distinct selector key
without normalizing it to JSON null, while continuing to reject every unknown
direction string before any snapshot artifact is written.

## New Evidence

The completed B2-d run `20260720T000558Z` ended naturally and retained four
unchanged JSONL shards containing 849 complete manifests and 13,584 selector
rows. The read-only diagnostic found 11,418 B2-a-schema-valid `NONE` rows, all
in `WATCHLIST` or `EXCLUDED`; all 224 `TRADE_NOW` rows used `LONG_SPREAD` or
`SHORT_SPREAD`. Merged B2-c rejected every `NONE` row because its exact
consumer set omitted the third value emitted by strategy-service
`DirectionHint::None`.

## Slice Loop Check

- New input consumed: the completed B2-d operational evidence and its exact
  direction diagnostic.
- New state transition: existing schema-valid selector evidence becomes
  consumable by the advisory B2-c scorer; it does not become eligible to trade.
- New artifact/runtime/user value: the preserved B2-d window can be validated
  and summarized without recapture or hand-editing.
- Why this is not repeating B2-c: B2-c implemented strict complete-tick
  ingestion; B2-cR repairs one production-evidenced value-set mismatch.
- Stop/defer condition: any producer, contract-shape, eligibility,
  scoring-policy, host, capture, OBS-1/OBS-3, or AUTO-2C change stops the slice.

## Scope

In:

- `tools/scripts/autopilot_shadow_allowlist.py`: add only the established
  literal `NONE` sentinel to a selector-only exact direction set. The realized
  paper-event direction set remains `LONG_SPREAD` / `SHORT_SPREAD`.
- `tools/scripts/tests/test_autopilot_shadow_allowlist.py`: producer-shaped
  replay, key identity, marginal/prominent, paper/static-overlap,
  deterministic serialization, schema, and fail-closed regression coverage.
- `docs/playbooks/autopilot-shadow-allowlist-runbook.md`: explain `NONE`
  versus null and its advisory/non-eligibility meaning.
- `CHANGELOG.md`, `docs/AGENT_STATE.md`,
  `.agentic/registers/agent-runs.md`, and this run folder: required versioning
  and audit state.

Out:

- `autopilot_observe.py`, services, contracts/examples, selector thresholds,
  paper/live allowlists, eligibility, capture, host actions, deployment,
  secrets, trading, schedulers, unattended loops, OBS-1, OBS-3, and AUTO-2C+.

## Binding Rules

1. Supported non-null selector directions are exactly `LONG_SPREAD`, `NONE`,
   and `SHORT_SPREAD`. The paper-event parser must continue to reject `NONE`.
2. `NONE` remains the literal string in selector keys and serialized output.
   It must not be converted to null because null retains existing unspecified
   direction matching behavior.
3. `NONE` must not match directional paper evidence or direction-specific
   static entries. Existing pair/variant-only static overlap is unchanged.
4. Prominent/marginal classification remains bucket-based. The
   production-shaped `WATCHLIST`/`EXCLUDED` `NONE` rows are marginal.
5. Any other direction string remains malformed and aborts before output.
6. Selector evidence remains segregated from realized outcomes and cannot
   control paper or live eligibility.

## Acceptance Criteria

1. A complete manifest containing producer-generated `NONE` rows passes the
   binding B2-a schema and the B2-c reader with exact identity preserved.
2. A snapshot over `NONE` rows is schema-valid, marginal for the captured
   non-`TRADE_NOW` buckets, and does not claim directional paper overlap.
3. Reversing tick and row order across mixed `NONE`/long/short evidence yields
   byte-identical deterministic output.
4. The existing unknown-direction and malformed-input tests still fail closed
   without output artifacts, and a regression proves `NONE` is not accepted as
   a realized paper-event direction.
5. The new test-only checkpoint fails against the merged pre-fix consumer and
   passes after the one-value repair.
6. Focused and full Python tooling suites, ruff, schema/example validation,
   scope checks, and `git diff --check` pass in a clean tree.
7. Codex inner review is clean, then Claude performs a fresh exact-SHA
   independent review before any Operator merge decision.

## Versioning

No contract or schema version changes. This is a backward-compatible PATCH
consumer bug fix recorded under `CHANGELOG.md` Unreleased.
