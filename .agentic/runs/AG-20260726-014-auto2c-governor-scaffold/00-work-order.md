---
id: AG-20260726-014
title: AUTO-2C C-b governed dynamic-allowlist test vectors and inert scaffold
repo: cryptopairs
base_branch: main
base_sha: b29118e0373c7f8149051f687c91eef9f5281119
working_branch: codex/auto2c-governor-scaffold
worker_tier: T1
required_evidence_level: E2
status: done
---

# Work Order

## Objective

Implement only AUTO-2C slice C-b: deterministic synthetic specification
vectors, an independent test-only cross-field auditor with mutation coverage,
and a disabled-by-default production CLI scaffold that cannot read evidence,
evaluate candidates, build a governed decision, create artifacts, or actuate
eligibility.

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/00-work-order.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/02-inner-review-summary.md`
- `.agentic/registers/decisions.md`
- `.agentic/policies/evidence.md`
- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist_contract.py`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`

## New Evidence and Operator Decisions

- PR #258 landed C-a on `main` as exact SHA
  `b29118e0373c7f8149051f687c91eef9f5281119`.
- The Operator approved the C-b plan and adopted its deterministic
  lexicographic exact-key ordering, raw-file SHA-256 binding, and canonical
  `decision_id` formula.
- The formula hashes minified, key-sorted UTF-8 JSON containing exactly the
  current snapshot SHA-256, previous snapshot SHA-256, paper-run configuration
  SHA-256, governor-configuration SHA-256, and canonical `evaluated_at`, with
  no trailing newline.
- The reserved `--enabled` gate must refuse with
  `GOVERNOR_NOT_IMPLEMENTED` before any input or output access.

## Slice Loop Check

- New input: the merged C-a contract and the Operator-adopted deterministic
  identity choices.
- New state transition: C-a's structural contract gains an independent,
  executable test-only semantic specification and an inert future CLI shape.
- New artifact value: C-c can later implement against stable synthetic vectors
  without inventing cross-field policy or changing the C-a contract.
- Non-repetition: C-b neither re-scores B2-c evidence nor implements the
  governor; it tests declared semantics and the refusal boundary only.
- Stop/defer: any production reducer, evidence read, output creation, runbook,
  host/artifact action, eligibility, CI-1/OBS-1/OBS-3, C-c/C-d,
  AUTO-2D/AUTO-3, service, deployment, secret, or trading work stops the slice.

## Plan

1. Add deterministic, production-shaped synthetic C-b vectors with two
   comparable schema-v2 references and a schema-v1 blocked predecessor case.
2. Add a test-only semantic auditor for provenance, timestamps, direction
   domains, evidence segregation, deterministic identity, transition limits,
   expiry, authority boundaries, and malformed/mutated inputs.
3. Add an inert production CLI scaffold whose disabled and enabled-refusal
   paths perform no file or artifact access.
4. Record additive compatibility, changelog, and governance impact.
5. Run focused E2, bounded E4 refusal proof, the full canonical suite, and
   multi-angle Codex inner review.
6. Commit, push, and open a Tier 3 draft PR for fresh Claude exact-SHA review.

## Interfaces / Contracts

- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`, its
  canonical example, and focused C-a tests remain byte-identical.
- Add `tools/scripts/autopilot_dynamic_allowlist.py` only as an inert CLI
  argument-shape boundary. It emits no governed-decision contract.
- Add a data-only synthetic specification-vector bundle under
  `tools/scripts/tests/fixtures/`.
- Exact keys sort lexicographically by
  `(pair_id, timeframe, selected_variant, direction)`.
- `NONE` and null remain distinct selector evidence but cannot enter an exact
  actionable key. Unknown selector or realized direction strings fail closed.

## Risk & Failure Modes

- Scaffold drift into implementation: source-boundary tests forbid file,
  network, subprocess, hashing, decision-ID, evaluation, and ranking surfaces.
- Accidental input/output access: default and `--enabled` paths receive
  inaccessible input and output paths under patched I/O; concurrent subprocess
  proof requires nonzero refusal and no artifact.
- Oracle self-fulfilment: policy arithmetic lives in an independent test-only
  auditor and is compared with data-only expected vectors plus mutations.
- Semantic normalization weakening provenance: vectors bind SHA-256 to exact
  raw bytes; whitespace-only changes alter identity.
- Unsafe policy values or directions: constants, `NONE`/null distinction,
  unknown rejection, demotion-only subset behavior, caps, freshness,
  separation, validity, and blocked-empty behavior are independently audited.
- C-a expansion: any required schema/example/test modification stops C-b.

## Test Plan

- Validate both synthetic governed decisions against the unchanged C-a schema.
- Prove two distinct comparable v2 snapshots pass at the exact separation,
  freshness, concentration, one-change, and 25% churn boundaries.
- Prove a production-shaped schema-v1 predecessor blocks with an empty set.
- Mutate raw hashes, selector configuration, timestamps, directions,
  completeness, duplicates, stream segregation, keys, claimed output,
  maximum selection, concentration, change, and churn and require refusal.
- Prove exact-key ordering, raw-byte hashing, `decision_id` determinism,
  24-hour expiry, no additions, no fallback, and separate `NONE`/null counts.
- Invoke the real scaffold disabled and explicitly enabled, including two
  concurrent enabled calls, and prove no output is created or input read.
- Run focused and full canonical `tools/scripts` tests without skips or
  expected failures.

## Observability

Default invocation prints one bounded deterministic JSON diagnostic with
`status="DISABLED"` and `artifact_created=false`. Explicit `--enabled` prints
only `GOVERNOR_NOT_IMPLEMENTED` to stderr and exits nonzero. No metrics, logs,
alerts, retained runtime evidence, process, daemon, scheduler, or host loop are
added.

## Versioning

C-b is additive operator tooling and test specification around the existing
schema-version-1 contract. It does not change a contract, public eligibility
behavior, package version, dependency, release, or tag. Record the inert CLI
compatibility boundary and `CHANGELOG.md` Operator Tooling/Governance entries.

## Allowed Paths

- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/fixtures/autopilot_dynamic_allowlist_cases.json`
- `docs/03-contracts-and-compatibility.md`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`
- `.agentic/registers/decisions.md`
- `.agentic/registers/agent-runs.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/00-work-order.md`
- `.agentic/runs/AG-20260726-014-auto2c-governor-scaffold/**`

## Acceptance Criteria

1. Synthetic vectors cover comparable v2 and blocked v1-predecessor cases.
2. The independent test-only auditor exercises all Operator-adopted constants,
   identity rules, evidence boundaries, and requested mutation checkpoints.
3. The production scaffold contains no governor logic or input/output access.
4. Default output is the bounded disabled diagnostic; `--enabled` refuses
   nonzero before I/O with `GOVERNOR_NOT_IMPLEMENTED`.
5. The C-a contract, example, and tests remain unchanged.
6. Governance records PR #258's landing and C-b without authorizing C-c.
7. Focused/full checks and Codex inner review are clean before the draft PR.

## Verification Commands

| Command | Expected |
|---|---|
| focused C-b pytest | pass |
| full canonical `tools/scripts` pytest | pass |
| concurrent enabled-refusal/no-output proof | pass |
| Ruff on new Python | pass |
| fixture JSON parse and hash/identity audit | pass |
| changed-path and forbidden-scope audit | pass |
| `git diff --check` | pass |

## Stop Conditions

Stop if `origin/main` moves from the exact base, any C-a contract/example/test
must change, a passing C-b test requires production governor behavior, E2 or
the bounded refusal proof cannot be reached, or any forbidden C-c/C-d, host,
artifact, eligibility, service, trading, AUTO-2D/AUTO-3, OBS-1/OBS-3, or CI-1
action becomes necessary.

## Merge Completion

Claude returned `VERDICT: CLEAN` at exact PR head
`bc10fb141e49f87b2ccd4c588b9d040fbc67f49d`. After the Operator-authorized
exact-head, required-check, unresolved-thread, and mergeability gates passed,
PR #259 squash-merged to `main` as
`40e0513531f3b44bc2dcbd234747c9e46142360d`. C-b is complete. This record does
not broaden C-c/C-d, host, artifact, eligibility, AUTO-2D/AUTO-3,
CI-1/OBS-1/OBS-3, service, deployment, secret, or trading authority.
