# Contracts and Compatibility

## Definition Of A Contract
A contract is any interface that another component depends on, including:
- event/message schemas (market data, orders, risk decisions)
- API endpoints (when they exist)
- database schemas/migrations (when they exist)
- config keys, env vars, and config file schema
- metrics names + label sets (alerts depend on them)

Contracts must be explicit and versioned.

## Contract Location And Canonical Source
All machine-readable contracts must live in:
- `specs/contracts/` (JSON Schema recommended)

Human-readable policy belongs in:
- `docs/` (guardrails + module policies)

Examples/samples live in:
- `specs/examples/`

## Compatibility Policy

### Default: Additive Changes Only
Allowed without a breaking bump:
- add optional fields
- add new message types
- widen enums only if consumers treat unknown values safely (must be documented)

### Breaking Changes (Require MAJOR Bump)
- remove fields
- rename fields
- change field meaning
- tighten validation in a way that rejects previously valid data
- change default values that affect behavior

### Deprecation Process
For breaking changes:
1) Mark old field/type as deprecated (document it)
2) Provide migration guidance
3) Keep support through at least one MINOR release (unless emergency/security)

## Validation Requirements

Every contract change must include at least one:
- schema validation test (when code exists)
- example payloads updated in `specs/examples/`
- compatibility notes in `CHANGELOG.md`

## Integrity And Risk Contracts Are Special
Any changes touching:
- integrity states (`COMPLETE`, `INCOMPLETE`, etc.)
- order lifecycle states
- risk decisions / kill switch behavior

…must be reviewed against:
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
and must fail closed by default.

## AUTO-2C Governed Dynamic-Allowlist Decision

`specs/contracts/autopilot_dynamic_allowlist_decision.schema.json` is an
additive schema-version-1 contract. It defines an offline advisory decision
artifact for later exact-hash Operator review; it is not an eligibility,
paper, live, execution, deployment, service, or runtime-configuration
interface. Its canonical example is synthetic and blocked; its paths, hashes,
counts, and identities are not production evidence or an approval.

Compatibility rules:

- existing AUTO-2B/B2-c snapshot and AUTO-2A paper contracts are unchanged;
- proposed entries are exact `pair_id + 1m + selected_variant + direction`
  keys with `LONG_SPREAD` or `SHORT_SPREAD` direction only;
- selector `NONE` and JSON null remain distinct evidence counts but cannot
  appear in baseline, proposed, addition, removal, or retained entry sets;
- unknown selector directions cannot form a valid decision artifact;
- `GOVERNOR_BLOCKED` has an empty proposed set and cannot fall back to an
  older decision or static baseline; and
- `ELIGIBLE_FOR_OPERATOR_REVIEW` is still advisory and requires a later,
  append-only exact-hash Operator approval before any separately designed
  AUTO-2D consumer could use it.

The initial policy values are encoded as constants because changing them
changes the governed decision meaning. A future relaxation or addition-capable
posture requires a separately reviewed contract/versioning decision.

### AUTO-2C C-b inert scaffold compatibility

`tools/scripts/autopilot_dynamic_allowlist.py` is an additive command scaffold,
not a governed-decision producer. Its default invocation emits only:

```json
{"artifact_created":false,"mode":"auto2c_governor_scaffold","status":"DISABLED"}
```

The reserved `--enabled` gate exits nonzero with
`GOVERNOR_NOT_IMPLEMENTED` before any input or output path access. The
scaffold does not read evidence, evaluate or rank candidates, construct the
schema-version-1 decision, create artifacts, import the test-only auditor, or
expose paper/live eligibility authority. Later C-c implementation must be a
separately authorized compatibility change.

C-b's synthetic specification fixes these later implementation identities:

- exact keys sort lexicographically by
  `(pair_id, timeframe, selected_variant, direction)`;
- each supplied input hash is SHA-256 over its exact raw file bytes, without
  parse/reserialize normalization; and
- `decision_id` is lowercase SHA-256 over minified, key-sorted UTF-8 JSON
  containing exactly `current_snapshot_sha256`,
  `previous_snapshot_sha256`, `paper_run_config_sha256`,
  `governor_config_sha256`, and canonical UTC `evaluated_at`, with no trailing
  newline.

These vectors and the independent test-only auditor are a C-c conformance
target, not production governor behavior or an eligibility decision. `NONE`
and null remain separately counted but non-actionable, unknown directions fail
closed, realized-paper and selector-view evidence remain segregated, and every
materialized synthetic decision remains advisory pending exact-hash Operator
approval.

### AUTO-2C C-c offline governor compatibility

Explicit `--enabled` now performs one deterministic offline evaluation against
four caller-named, exact-raw-byte SHA-256-bound files: current and previous
B2-c snapshots, the paper-run configuration, and the ratified governor
configuration. The three evidence producers are also bound by caller-supplied
Git SHAs, and the caller must supply an RFC 3339 evaluation time. The default
disabled invocation and diagnostic above remain byte-identical.

The enabled path is fail-closed:

- inputs must be regular, non-symlink files whose bytes, hashes, structure,
  counts, identity sets, directions, selector configuration, chronology,
  static comparison, and churn are internally consistent and unchanged
  through the final pre-output recheck;
- the paper baseline must use exact direction-level
  `pair_variant_direction` entries;
- selector `NONE` and null remain distinct evidence identities but cannot
  qualify, while unknown selector directions and any realized-paper
  non-`LONG_SPREAD`/`SHORT_SPREAD` direction create no artifact;
- trusted but policy-insufficient inputs produce only a schema-valid
  `GOVERNOR_BLOCKED` decision with an empty proposed set; and
- a review-eligible proposed set is a deterministic demotion-only subset of
  the static baseline and remains advisory pending a separate exact-hash
  Operator approval.

One invocation exclusively creates one previously absent common output
directory containing exactly the canonical JSON decision and Markdown report.
It never overwrites, repairs, cleans, or reuses an existing or partial output
root. An optional previous-decision file is separately hash-bound and affects
only a labelled, non-authoritative Markdown comparison; it cannot affect
decision identity, status, qualification, fallback, or eligibility.

This additive operator-tooling behavior does not change the schema-version-1
contract, B2-c or paper contracts, eligibility configuration, services,
orders, execution, deployment, or any runtime interface. C-d runbook and
hardening work, E3 production evidence, and every AUTO-2D consumer remain
separately gated.

### AUTO-2C v2 automatic-paper contract compatibility

`specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json` is a
separate schema-version-2 contract. It does not relax or replace the
schema-version-1 decision in place. Version 1 remains the historical
demotion-only advisory interface; a future v2 AUTO-2D controller must reject
version 1 and raw B2-c snapshots as automatic-paper decisions.

`tools/scripts/autopilot_dynamic_allowlist_v2.py` is the separate offline
producer for this v2 contract. It preserves the v1 CLI byte-for-byte and
supports only the first transition from an exact direction-level static paper
allowlist. Candidate overflow is ranked and truncated, concentration failures
are skipped and recorded, and output remains non-actuating. Its
`--verify-only` mode is a same-implementation byte reconstruction for
Operator evidence; it is not the independent AUTO-2D verifier.

The future prior-set source `PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE` fails closed
until AUTO-2D provides an independently accepted and hash-bound predecessor.
AUTO-2D, paper configuration writes, eligibility, trial start, and live/order
authority remain outside the v2 governor interface.

The v2 decision may represent at most two evidence-qualified additions,
deterministically rank and truncate excess candidates, and use
`POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` to indicate only that a later
controller may independently verify it. It grants no paper configuration,
eligibility, trial-start, live, order, execution, deployment, service, or
self-approval authority. Per-output Operator approval is not part of the
ratified v2 envelope, but the governor implementation, controller
implementation, production evidence, and first bounded paper trial remain
separate protected gates.

Compatibility rules:

- actionable identity is exact
  `(pair_id, timeframe=1m, selected_variant, direction)`;
- actionable directions remain exactly `LONG_SPREAD` and `SHORT_SPREAD`;
- selector `NONE` and JSON null remain distinct but non-actionable, and every
  unknown selector or non-long/short realized direction remains fail-closed;
- realized-paper and selector-view evidence remain separate streams joined
  only by exact-key membership;
- identity binds exact raw input hashes, producer attestations, the canonical
  policy envelope, the prior active set, and explicit evaluation time;
- candidate overflow is deterministically truncated and recorded;
  concentration overflow skips the candidate and continues;
- blocked decisions contain no selected, selection-step, truncation, skip, or
  transition outcome state and permit no fallback; already-qualified
  candidate evidence may remain for audit when a later global gate blocks; and
- every existing AUTO-2B/B2-c snapshot, AUTO-2A paper, schema-version-1
  decision, and governor surface is unchanged.

`specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json` is an
additive append-only provenance companion for a later AUTO-2D controller. It
binds a synthetic immutable trial manifest and paper decision/position records
to an independently verified v2 decision. It does not replace the existing
paper contracts or implement a controller. Its authority is paper-only, with
live-order, exchange-routing, execution-service, deployment, and
service-configuration authority fixed false.

The complete ratified policy, ranking, transition, exposure, lifecycle, and
no-authority boundary is recorded in
`docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`. Implementing the v2
governor or AUTO-2D remains separately gated.
