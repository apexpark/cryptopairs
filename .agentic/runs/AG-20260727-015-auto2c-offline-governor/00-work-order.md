---
id: AG-20260727-015
title: AUTO-2C C-c deterministic offline governor
repo: cryptopairs
base_branch: main
base_sha: 40e0513531f3b44bc2dcbd234747c9e46142360d
working_branch: codex/auto2c-offline-governor
worker_tier: T1
required_evidence_level: E3
status: done
---

# Work Order

## Objective

Implement only AUTO-2C C-c: the deterministic, one-shot, offline governed
dynamic-allowlist reducer behind the existing explicit `--enabled` gate. The
output remains advisory pending exact-hash Operator approval and has no paper,
live, service, configuration, execution, or deployment authority.

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/00-work-order.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/02-inner-review-summary.md`
- `.agentic/runs/AG-20260726-014-auto2c-governor-scaffold/00-work-order.md`
- `.agentic/runs/AG-20260726-014-auto2c-governor-scaffold/02-inner-review-summary.md`
- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`
- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/fixtures/autopilot_dynamic_allowlist_cases.json`
- `tools/scripts/autopilot_shadow_allowlist.py`
- `tools/scripts/autopilot_paper_report.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `.agentic/policies/evidence.md`

## New Evidence and Operator Decisions

- PR #259 landed C-b on `main` as exact SHA
  `40e0513531f3b44bc2dcbd234747c9e46142360d`.
- The Operator adopted explicit raw-hash and producer-Git-SHA bindings,
  direction-level paper baselines only, a fresh common output directory with
  no repair/reuse, comparison-only previous decisions, standard-library-only
  production validation, and an E3 pause when no exact-hash read-only copies
  are supplied.
- The C-a contract/example/focused tests and all B2-c/paper code and contracts
  remain immutable in this slice.

## Slice Loop Check

- New input: the merged C-a contract, C-b independent specification vectors,
  and the Operator-ratified C-c input/output and failure taxonomy.
- New state transition: explicit trusted inputs can be reduced to one
  schema-valid advisory review decision or a blocked empty decision.
- New value: deterministic offline governance evaluation without eligibility
  actuation.
- Non-repetition: C-b only refused `--enabled`; C-c implements the reducer but
  still cannot feed paper or runtime configuration.
- Stop/defer: missing E3 copies, any contract/paper/B2-c/dependency change,
  runbook, host, selector capture, eligibility, CI-1/OBS-1/OBS-3, C-d,
  AUTO-2D/AUTO-3, service, deployment, secret, or trading work stops the
  slice.

## Plan

1. Extend the inert CLI with explicit path, expected-hash, producer-SHA,
   evaluation-time, optional comparison, and exclusive output bindings.
2. Add strict raw-file, JSON, snapshot, paper-config, governor-config, and
   optional previous-decision validation without new dependencies.
3. Add deterministic qualification, policy gating, decision construction,
   Markdown rendering, and exclusive output creation.
4. Add focused schema/replay/determinism/mutation/concurrency/read-only tests.
5. Reconcile PR #259 landing and C-c state in compatibility, changelog, and
   governance.
6. Run E2 plus bounded E4. Pause while Operator-supplied E3 files are absent;
   after exact bindings and separate execution authorization arrive, run
   exactly one local offline E3 and continue only if it passes.

## Interfaces / Contracts

- Preserve
  `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`,
  its canonical example, and its focused C-a tests byte-identically.
- Preserve the exact C-b key sort and `decision_id` formula.
- Default CLI output remains byte-identical and performs no I/O.
- Enabled output is one schema-version-1 decision JSON plus deterministic
  Markdown under one newly and exclusively created directory.
- `NONE` and null remain distinct selector evidence but non-actionable.
  Unknown selector directions and every non-long/short realized direction
  produce no artifact.

## Risk & Failure Modes

- Untrusted bytes or provenance: reject before output.
- Snapshot/config ambiguity or internal inconsistency: reject before output.
- Valid policy insufficiency: produce `GOVERNOR_BLOCKED` with an empty set.
- Candidate overflow: block all; never rank or truncate.
- Output collision/concurrency: atomic parent-directory creation lets one
  invocation win; every other invocation refuses without mutation.
- Crash-partial root: retain it; never overwrite, repair, clean, or reuse it.
- Input mutation: bind one stable read and recheck before output creation.
- Authority leakage: source and tests prohibit HTTP, subprocess, paper,
  execution, environment/configuration writes, and service integration.

## Test Plan

- Focused C-a schema validation over every generated decision.
- Comparable-v2 eligible replay and valid blocked predecessor replay.
- Raw hash, producer SHA, timestamp, config, direction, completeness,
  duplication, segregation, cutoff, freshness, selection, concentration,
  change, and churn mutations.
- Byte-identical JSON/Markdown and canonical decision identity.
- Default no-I/O behavior, exclusive output, concurrent invocation, input
  preservation, output collision, and partial-root refusal.
- Full canonical `tools/scripts` suite with no skips or expected failures.
- Genuine E3 only from Operator-supplied read-only exact-hash copies.

## Observability

The CLI emits one bounded JSON diagnostic on success or one bounded error
diagnostic on failure. It adds no metric, alert, log service, daemon, process,
scheduler, transcript, or unattended loop.

## Versioning

C-c is an additive MINOR-level operator-tooling behavior behind explicit
enablement. Schema version `1`, every existing contract, package version,
dependency, release, and tag remain unchanged. Compatibility and CHANGELOG
must record the enabled offline behavior and unchanged advisory authority.

## Allowed Paths

- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/fixtures/autopilot_dynamic_allowlist_cases.json`
- `docs/03-contracts-and-compatibility.md`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`
- `.agentic/registers/decisions.md`
- `.agentic/registers/agent-runs.md`
- `.agentic/runs/AG-20260726-014-auto2c-governor-scaffold/00-work-order.md`
- `.agentic/runs/AG-20260727-015-auto2c-offline-governor/**`

## Stop Conditions

Stop if `origin/main` differs from the exact base, the C-a contract/example/
focused tests or any B2-c/paper code or contract must change, a dependency is
needed, E2/E4 fail after bounded repair, E3 copies are absent after E2/E4, or
any forbidden scope becomes necessary.

## E2 / E4 Verification Evidence

- Focused C-c suite: 39 passed, with no skip, xfail, or expected-failure
  cases.
- Bounded E4 subset: 17 passed. It covers byte-identical disabled behavior,
  schema-valid eligible and blocked replays, selector unknown and
  realized-paper non-actionable direction refusal, numeric internal-consistency
  mutation refusal, exact-hash mismatch, mutation before output, symlink and
  non-regular input rejection, existing output collision, two concurrent
  invocations with one exclusive winner, retained partial output on injected
  write failure, comparison-only previous decision behavior, and no
  test/runtime-actuation dependency.
- Full canonical `tools/scripts` suite: 261 passed plus 70 subtests; one
  pre-existing Anaconda `dateutil` deprecation warning.
- Ruff: pass for the implementation and focused test module.
- `git diff --check`: pass.
- Default diagnostic matches the exact `origin/main` C-b bytes:
  `{"artifact_created":false,"mode":"auto2c_governor_scaffold","status":"DISABLED"}`.
- C-a contract, canonical example, focused C-a tests, B2-c code/contracts, and
  paper code/contracts remain unchanged.

## E3 Production-Evidence Verification

The Operator supplied four local, mode-`0400`, regular non-symlink copies and
authorized exactly one offline invocation:

- current snapshot SHA-256
  `97275666f9f07af9ea5ce2942838dda3bf53dcf20cced063af83d01e576a547b`,
  producer Git SHA `29de6028b564869298bc0be7e581ed28df78bbf2`;
- previous snapshot SHA-256
  `d26267fefa68ee5dc9929fa7c2b0e8964d76face655377382c5550b1c579b853`,
  producer Git SHA `632ba80d31885a6427de68d93e2e003f95543b85`;
- paper-run config SHA-256
  `588d29b3a75ba1637132b3b9e2c78bf8a145e7b394ff86bf4ffe1ecb68197f8f`,
  producer Git SHA `632ba80d31885a6427de68d93e2e003f95543b85`;
- governor-config SHA-256
  `41c8bcefe13ae55407a9c9eef7e4e727a1e4d2fa17f0f0d8fa0a1a96f921266c`;
- evaluation time `2026-07-23T00:32:25Z`; and
- fresh local output root
  `/Users/kevinsaunders/Documents/cryptopairs-e3/AG-20260727-015-output`.

Preflight re-proved the exact base/branch and every file property, hash, and
provenance binding. The output root was absent. The single invocation returned
`GOVERNOR_BLOCKED`, as required for the accepted schema-v1 predecessor route,
with decision ID
`26a9caeef8820115e5b62e73bfeca849cbf710b15c93c5b3cec87e94badac3ce`.
It exclusively created the authorized JSON and Markdown:

- decision JSON SHA-256
  `7f519e209b271530cdd01eb592d5ad03844b4d688367a079df4993db19e7d9c9`;
- decision Markdown SHA-256
  `a3baa49d30dae9541b9ef9c5a36f78983135850a2346a5d3a8662580165e8845`.

Post-run validation used the unchanged C-a schema with active format checking
and independently recomputed the decision ID. It proved an empty proposed set,
`PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2` and `SELECTOR_CHURN_UNAVAILABLE` reasons,
all authority boundaries false, exact input/provenance/config/time bindings,
24-hour validity, and preserved input bytes and file modes. E3 is achieved.

## Inner Review

Codex completed a multi-angle scope, implementation, failure-mode, contract,
test, governance, and production-evidence review. The result is CLEAN with no
post-E3 source repair. The exact review and verification evidence is recorded
in `02-inner-review-summary.md`. A fresh independent Claude review remains
required at the exact Tier 3 draft-PR head.

## Boundary Record

No host was accessed by Codex, no input was modified, E3 was not retried, no
dependency was added, and no eligibility, paper/live, service, deployment,
secret, C-d, AUTO-2D/AUTO-3, CI-1/OBS-1/OBS-3, or unattended-loop action
occurred.

## Completion

Claude independently reviewed exact PR head
`b9132de68791bdba5754ba6cd8195e900053d903` CLEAN. After the Operator's
exact-head, required-check, unresolved-thread, and mergeability gates passed,
PR #260 squash-merged on `main` as
`c1b65389ebf0ead41146df12ca49a07f3889cfc9`. This completed C-c only and
granted no C-d, v2-governor, AUTO-2D, host, evidence, configuration,
eligibility, paper/live trading, service, deployment, secret, CI-1, OBS-1,
OBS-3, AUTO-3, or unattended-loop authority.
