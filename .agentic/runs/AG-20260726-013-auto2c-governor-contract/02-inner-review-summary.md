# AUTO-2C C-a Inner Review Summary

Date: 2026-07-26
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after four C-a repairs; fresh independent Claude exact-SHA
review required**

## Context and scope

- Hydrated `AGENTS.md`, `docs/AGENT_STATE.md`, and
  `docs/playbooks/remote-agent-bootstrap.md`.
- Fetched only `origin/main` without tags and proved both local `main` and the
  fetched ref equalled the authorized base
  `f1da80f11e5a8d2244ebc9715d026f30068c0fb3` before branching.
- Inspected the merged AUTO-2C proposal, AG-20260726-012 work order and inner
  review, current snapshot/paper contracts, B2-c/B2-cR consumer, static paper
  allowlist, evidence ladder, and versioning/testing/observability policies.
- Changed paths are limited to the authorized C-a contract, example, focused
  contract test, compatibility/changelog, proposal ratification notice, and
  governance/audit records.
- No governor implementation or scaffold, runbook, existing contract, B2-c or
  paper code, dependency, CI, host, artifact, eligibility, service, deployment,
  secret, trading, AUTO-2D/AUTO-3, OBS-1, or OBS-3 surface changed.

## Contract and fail-closed review

- `schema_version: 1` defines a new additive decision type; existing
  AUTO-2B/B2-c and AUTO-2A contracts are unchanged.
- Proposed, baseline, retained, addition, and removal entries accept exact
  `pair_id + 1m + selected_variant + direction` keys with long/short directions
  only.
- Selector `NONE` and null are separately required evidence counts and cannot
  enter an actionable key. Unknown selector and realized direction counts are
  fixed at zero.
- The ratified demotion-only policy is machine-readable: additions are always
  empty; eligible outputs contain at most four entries; two comparable v2
  snapshots, cutoff separation, freshness, concentration, one-change, 25%
  baseline-denominator churn, 24-hour validity, block-not-truncate, and no
  fallback values are constants.
- `GOVERNOR_BLOCKED` requires an empty proposed set and at least one bounded
  reason. `ELIGIBLE_FOR_OPERATOR_REVIEW` requires schema-v2 selector history,
  all 19 gates passing, non-empty output, and every adopted cap.
- A structurally valid schema-v1 predecessor can be retained as insufficient
  history in a blocked artifact. A review-eligible artifact requires both
  snapshots to be schema v2 with selector evidence and available selector
  churn.
- The contract cannot prove timestamp arithmetic, list/count/set equality,
  canonical hashes, distinct snapshot bytes, or file properties. Those are
  explicitly deferred to C-b/C-c semantic validation; malformed or internally
  inconsistent input remains outside the valid artifact boundary.

## Inner-review findings and repairs

### IR-1 — governor configuration provenance

The first draft embedded the governor configuration but did not bind the
explicit configuration input by path and SHA-256, weakening later exact-hash
audit and approval.

Repair: add required `governor_config_source` with an exact path and lowercase
SHA-256 plus a focused missing-hash regression.

### IR-2 — snapshot reference consistency

The first draft allowed a schema-v1 snapshot reference to claim selector-view
or selector-churn evidence, which the input contract cannot represent.

Repair: schema-v1 references now require both selector flags false; any
available selector churn requires schema v2 and a present selector block.

### IR-3 — policy calculation references

The adopted symmetric-difference calculation, source-cutoff freshness origin,
and evaluation-time validity origin were initially descriptive rather than
machine-readable.

Repair: add exact `change_measure`, `freshness_reference`, and
`validity_reference` constants and policy mutations.

### IR-4 — idempotency and exact-hash approval boundary

The first draft said the artifact was advisory but did not fully encode
canonical serialization, exclusive output, read-only inputs, or the fields a
later append-only Operator approval must bind.

Repair: add exact methodology constants and an `operator_approval_binding`
object requiring the decision ID, decision JSON SHA-256, governor-config
SHA-256, validity, and bounded paper-run ID in a future Operator decision.

## Governance and versioning review

- The decisions-register change is append-only: two inserted rows and zero
  deletions.
- PR #257's CLEAN head and landing SHA, the OP-45(e) queue rebuild, ratified
  values, C-a authorization, and later-slice stop are consistent across the
  proposal notice, decisions register, agent-runs register, living state, and
  changelog.
- The canonical example is explicitly described as synthetic and blocked, not
  production evidence or approval.
- The new contract is an additive MINOR-level type with its own schema version
  1. No existing contract version, package version, dependency, release, or tag
  changes.
- CI-1 remains open and separately scoped.

## Verification evidence

- New focused contract suite: **24 passed** under system Python, with an active
  self-contained RFC 3339 checker.
- Full canonical `tools/scripts` suite from `tools/scripts/`:
  **222 passed, 70 subtests passed, 1 pre-existing third-party warning** using
  `/opt/anaconda3/bin/python3` with external pytest plugin autoload disabled.
- Standard `jsonschema` `FormatChecker` in that canonical environment rejects
  an invalid date-time and validates the new schema/example.
- System Python full-suite diagnostic: **220 passed, 2 pre-existing RFC 3339
  guard failures** because `rfc3339-validator` is absent. This reproduces the
  recorded CI-1 environment gap and is not represented as passing evidence.
- Ruff: pass.
- All 113 existing contract/example JSON files parse.
- New schema and example parse and validate.
- `git diff --check`: pass.
- Authorized changed-path allowlist: pass.
- Existing runtime scripts and existing contracts: unchanged.
- Authorized base remains an ancestor of the branch.

E2 is achieved. E3 is deliberately not claimed: real artifact copies and
governor behavior belong to later, separately authorized slices.

## Next gate

Open a Tier 3 draft PR. Claude must review the exact PR head SHA read-only.
Every repair push voids the prior verdict. Merge remains Operator-only after a
CLEAN exact-SHA verdict, passing required checks, zero unresolved threads, and
mergeability.
