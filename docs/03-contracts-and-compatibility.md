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
