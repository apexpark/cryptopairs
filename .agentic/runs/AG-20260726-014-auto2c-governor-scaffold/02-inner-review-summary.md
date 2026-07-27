# AUTO-2C C-b Inner Review Summary

Date: 2026-07-27
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after two C-b repairs; fresh independent Claude exact-SHA
review required**

## Context and scope

- Hydrated `AGENTS.md`, `docs/AGENT_STATE.md`, and
  `docs/playbooks/remote-agent-bootstrap.md`.
- Fetched only `origin/main` without tags and proved local `main`, fetched
  `origin/main`, and the authorized base all equalled
  `b29118e0373c7f8149051f687c91eef9f5281119` before branching.
- Inspected the merged AUTO-2C proposal, C-a work order/inner review, unchanged
  C-a contract/example/tests, B2-c snapshot contract/example, compatibility,
  versioning, testing, integrity, risk, observability, and governance records.
- Changed paths are limited to the authorized inert CLI, synthetic vectors,
  independent test-only auditor, C-a completion/C-b governance records,
  compatibility, and changelog.
- No C-a contract/example/test, C-c governor/output, runbook, B2-c/paper
  surface, dependency, CI, host/artifact, selector capture, eligibility,
  service, deployment, secret, trading, AUTO-2D/AUTO-3, OBS-1/OBS-3, or CI-1
  surface changed.

## Production-boundary review

- `autopilot_dynamic_allowlist.py` contains only argument parsing and two
  bounded diagnostics. Its imports are limited to standard argument/JSON/stdout
  support; its only functions are `parse_args` and `main`.
- Default invocation emits deterministic disabled JSON and returns zero.
- `--enabled` emits only `GOVERNOR_NOT_IMPLEMENTED` to stderr and returns 2
  before inspecting any supplied path value.
- Tests patch built-in and `Path` reads/writes, pass deliberately inaccessible
  paths, run two enabled subprocesses concurrently, and require no output
  artifact.
- Source-boundary inspection finds no file/path, network, subprocess, hashing,
  decision-ID, evaluation, ranking, or test-oracle import in production code.
- The scaffold provides no paper/live eligibility, execution, configuration,
  service, deployment, or Operator-approval authority.

## Synthetic-specification review

- The bundle materializes schema-valid full B2-c snapshot documents from the
  canonical example: distinct current/previous schema-v2 inputs plus a
  schema-v1 predecessor with selector-only v2 blocks removed.
- The independent test-only auditor binds exact raw bytes, selector config,
  producer metadata, current/previous cutoffs, paper config, governor config,
  exact-key identity/order, and the canonical decision-ID envelope.
- The comparable-v2 vector passes exactly at 86,400-second separation,
  1,800-second freshness, two directions per pair/variant, two entries per
  full instrument, one changed key, 25% baseline-denominator churn, and
  24-hour validity.
- The production-shaped v1-predecessor vector is blocked with an empty proposed
  set. `NONE` and null remain separately counted and non-actionable; unknown
  selector or realized directions fail closed.
- Realized-paper and selector-view data remain separate. Candidate membership
  uses only exact-key set intersections; no numeric evidence is merged.
- Mutations cover raw hash drift, config drift, malformed/non-finite JSON,
  stale/short windows, identity reuse, unknown/non-actionable directions,
  incomplete/duplicate evidence, stream mixing, nondeterministic/duplicate
  keys, blocked-nonempty claims, selection/concentration overflow, and
  one-change/churn overflow.
- Both materialized synthetic decisions validate against the unchanged C-a
  schema and retain advisory-only, exact-hash Operator-approval boundaries.

## Inner-review findings and repairs

### IR-1 — production-shaped snapshot identity

The first draft hashed compact snapshot metadata stubs. Although adequate for
arithmetic tests, those stubs were not valid B2-c snapshot inputs and weakened
the claimed production-shaped replay boundary.

Repair: materialize exact raw snapshot bytes from the canonical B2-c example,
validate current/previous v2 and the transformed v1 predecessor against the
merged snapshot schema, and bind the governed-decision references to those
full-document SHA-256 hashes.

### IR-2 — selector provenance and independent policy lock

The first draft used a placeholder selector-configuration hash and compared the
governor raw JSON only with values from the same fixture. A coordinated fixture
mutation could therefore evade the independent oracle.

Repair: bind the selector config to its actual canonical SHA-256 and hard-code
the Operator-adopted selector/governor values in the independent test auditor
before comparing raw and structured fixture data.

## Governance and versioning review

- The decisions-register change is append-only: two inserted rows and zero
  deletions.
- PR #258's CLEAN head and landing SHA, C-a completion, the adopted C-b
  identity choices, C-b authorization, and later-slice stop are consistent
  across work orders, decisions, agent-runs, living state, compatibility, and
  changelog.
- C-b is additive operator tooling/test specification around the existing
  schema-version-1 contract. No contract, package version, dependency, release,
  or tag changes.
- C-c/C-d, a second selector window, AUTO-2D/AUTO-3, OBS-1/OBS-3, and CI-1
  remain separately gated.

## Verification evidence

- Focused C-b suite: **28 passed** with no skip/xfail/expected-failure cases.
- Full canonical `tools/scripts` suite from `tools/scripts/`:
  **250 passed, 70 subtests passed, 1 pre-existing third-party deprecation
  warning** under `/opt/anaconda3/bin/python3` with external pytest plugin
  autoload disabled.
- The real CLI default and explicit-enable probes return the exact bounded
  diagnostics; explicit enable returns 2 without accessing nonexistent inputs
  or creating outputs.
- Ruff on both new Python files: pass.
- All 113 existing contract/example JSON files plus the new vector bundle
  parse.
- Three materialized synthetic snapshot inputs and both materialized governed
  decisions validate against their unchanged merged schemas.
- C-a contract, example, and focused C-a tests: byte-identical to the exact
  base.
- `git diff --check`: pass.
- Authorized changed-path allowlist: pass.
- Production scaffold AST/source boundary: pass.
- Authorized base remains an ancestor of the branch.

E2 is achieved. The bounded E4 proof applies only to the explicit-enable
refusal/no-input/no-output scaffold boundary; it is not a governor mutation
checkpoint and does not claim C-c behavior or production evidence.

## Next gate

Commit, push, and open a Tier 3 draft PR. Claude must independently review the
exact PR head SHA read-only. Any repair push voids that verdict. Merge remains
Operator-only after a CLEAN exact-SHA verdict, passing required checks, zero
unresolved review threads, and mergeability.
