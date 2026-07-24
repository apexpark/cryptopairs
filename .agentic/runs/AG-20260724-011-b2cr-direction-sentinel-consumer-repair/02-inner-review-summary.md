# B2-cR Inner Review Summary

Date: 2026-07-24
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after one scope repair; fresh independent Claude review required**

## Context and sources

- Completed Operator-run B2-d evidence for run `20260720T000558Z`: 849
  complete manifests, 13,584 selector rows, and 11,418 B2-a-schema-valid
  `direction_hint="NONE"` rows, all in `WATCHLIST` or `EXCLUDED`.
- Producer sentinel: `services/strategy-service/src/lib.rs`
  (`DirectionHint::None` serializes as `NONE`).
- Binding selector record shape:
  `specs/contracts/autopilot_observe_record.schema.json`.
- Consumer and tests: `tools/scripts/autopilot_shadow_allowlist.py` and
  `tools/scripts/tests/test_autopilot_shadow_allowlist.py`.
- Operator interpretation:
  `docs/playbooks/autopilot-shadow-allowlist-runbook.md`.

## Scope and authority angle

- The implementation changes only the artifact-only B2-c selector-view
  consumer. It accepts `NONE` only for selector-view `direction_hint`.
- `NONE` remains a literal selector identity and is not normalized to null.
- The realized paper-event direction set remains exactly `LONG_SPREAD` and
  `SHORT_SPREAD`; `NONE` still fails closed there.
- No producer, contract/schema/example, service, capture, host, eligibility,
  scoring-policy, order, deployment, secret, OBS-1/OBS-3, AUTO-2C, or
  unattended-loop surface changed.

Finding IR-1: the first implementation expanded the existing global
`SUPPORTED_DIRECTIONS` set. That set is also used by realized paper-event
parsing, so the change would have accepted `NONE` outside the approved
selector-only path.

Repair: restore the paper-event set unchanged and add a dedicated exact
`SUPPORTED_SELECTOR_DIRECTIONS` set for selector rows and previous selector
snapshots. A regression now proves paper-event `NONE` remains rejected.

## Contract, identity, and fail-closed angle

- The production-shaped regression creates rows through B2-b's producer helper,
  validates them against the merged B2-a schema with `FormatChecker`, ingests
  their complete tick manifest, and preserves `NONE` in the selector key and
  producer `observe_key`.
- The test proves `NONE` differs from null and appears only as the literal
  sentinel in the repaired records and artifact.
- Every selector direction outside null, `LONG_SPREAD`, `NONE`, and
  `SHORT_SPREAD` continues to fail before an output artifact is written.
- Existing incomplete-manifest, malformed-value, forbidden-outcome,
  RFC-3339-identity, duplicate-tick, and trailing-partial rejection tests remain
  green.

## Classification, overlap, determinism, and segregation angle

- Production-shaped `WATCHLIST` and `EXCLUDED` `NONE` rows remain marginal;
  prominence remains based only on observation in `TRADE_NOW`.
- A `NONE` selector key does not match directional paper evidence or a
  direction-specific static entry. Existing pair/variant-only static overlap
  behavior remains unchanged.
- Forward and reversed mixed `NONE`/long/short tick and row order produce
  byte-identical serialized snapshots.
- The snapshot remains schema-valid and recursively free of
  realized/outcome/PnL/fill fields in the selector block.
- No selector observation changes paper eligibility or the paper score.

## Evidence

- Test-only mutation checkpoint:
  `1e3a8585ad6d4bc93834f4f5c2c024fdeb586693`. Against merged B2-c, the
  focused suite produced **2 failed, 28 passed**: production-shaped `NONE`
  ingestion and deterministic mixed-direction replay both rejected the
  sentinel.
- Repaired focused suite: **30 passed, 21 subtests passed, 1 warning**.
- Repaired full canonical `tools/scripts` suite:
  **198 passed, 70 subtests passed, 1 warning**, using
  `/opt/anaconda3/bin/python3` with external pytest plugin autoload disabled.
- The warning is the existing third-party `dateutil` UTC deprecation.
- Ruff, Python byte-compilation, binding schema/example validation,
  governance/scope searches, and `git diff --check` pass.

E3 is met by replaying producer-generated, schema-valid `NONE` records through
the consumer into the v2 advisory artifact. E4 is met by the mutation proof,
exact value-set validation, paper-direction non-expansion regression,
deterministic replay, malformed-input rejection, and evidence-segregation
assertions.
