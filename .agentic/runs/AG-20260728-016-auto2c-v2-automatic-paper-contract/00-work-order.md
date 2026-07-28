---
id: AG-20260728-016
title: AUTO-2C v2 automatic paper contract family
repo: cryptopairs
base_branch: main
base_sha: c1b65389ebf0ead41146df12ca49a07f3889cfc9
working_branch: codex/auto2c-v2-automatic-paper-contract
worker_tier: T1
required_evidence_level: E2
status: in-review
---

# Work Order

## Objective

Build only the first accelerated OP-45(e) slice: a separately versioned,
non-actuating AUTO-2C v2 contract family, canonical synthetic examples, and
focused independent E2 tests for bounded additions, deterministic ranking and
truncation, and later independent AUTO-2D automatic acceptance. Do not
implement the v2 governor or controller.

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- the C-a, C-b, and C-c work orders and inner-review records
- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/contracts/autopilot_paper_decision_record.schema.json`
- `specs/contracts/autopilot_paper_position.schema.json`
- `tools/scripts/autopilot_paper.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `.agentic/policies/evidence.md`

## New Evidence and Operator Decisions

- PR #260 landed C-c on `main` as exact SHA
  `c1b65389ebf0ead41146df12ca49a07f3889cfc9`.
- The Operator reset the queue toward one bounded paper-only trial, adopted
  addition-capable deterministic ranking/truncation and independent AUTO-2D
  automatic acceptance, then authorized only this v2 contract/example/test
  slice at that exact base.
- The exact ratified policy is recorded in
  `docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`.

## Slice Loop Check

- New input: ratified addition, ranking, concentration, churn, exploration,
  paper-exposure, lifecycle, and independent-verification rules.
- New transition: v1 demotion-only prose becomes a distinct v2
  machine-readable contract capable of representing bounded additions.
- New value: later governor/controller slices have one deterministic target
  and cannot invent automatic-acceptance semantics.
- Non-repetition: v1 remains byte-identical; v2 deliberately versions the
  policies that cannot reach the paper-trial goal.
- Stop/defer: any governor/controller/runbook implementation, host/evidence
  action, configuration mutation, paper start, trading, services, deployment,
  secrets, CI-1/OBS-1/OBS-3, or AUTO-3 work stops the slice.

## Plan

1. Add a schema-version-2 AUTO-2C decision contract.
2. Add an additive v2 paper-provenance companion for later independent
   AUTO-2D verification and audit.
3. Add canonical synthetic eligible, blocked, trial, decision-binding, and
   position-binding examples.
4. Add independent schema, semantic, identity, ranking, mutation,
   concentration, transition, and compatibility tests.
5. Record the ratified v2 policy, compatibility, changelog, and governance.
6. Run focused and full E2 verification plus multi-angle Codex inner review.
7. Commit, push, and open a Tier 3 draft PR for fresh Claude exact-SHA review.

## Interfaces / Contracts

- Add
  `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`.
- Add
  `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`.
- Preserve the v1 decision contract/example/tests and existing B2-c/paper
  contracts and code byte-identically.
- Actionable identity remains exact pair/timeframe/variant/direction with
  long/short only. `NONE` and null remain distinct but non-actionable; unknown
  directions fail closed.
- A v2 decision remains non-actuating. A later AUTO-2D controller must
  independently recompute it before any separately authorized paper action.

## Risk & Failure Modes

- Ambiguous ranking or tie: record canonical rank components, lane ranks, and
  exact-key final tie-breaks.
- Silent overflow: record each skip/truncation and never drop a candidate.
- Unsafe addition/churn/concentration: fixed policy limits and semantic tests
  fail closed.
- Self-approval: governor authority remains false; independent AUTO-2D
  recomputation is mandatory.
- Direction leakage: `NONE` and null cannot enter actionable keys; unknown
  values cannot form a valid output.
- Compatibility drift: exact SHA-256 regression guards preserve v1, B2-c, and
  paper surfaces.

## Test Plan

- Draft 2020-12 schema and canonical-example validation with active date-time
  checking.
- Independent canonical policy/prior-set/decision-ID recomputation.
- Comparable-v2, selector-configuration, cutoff, freshness, validity, evidence
  segregation, direction, ranking, allocation, concentration, transition,
  churn, blocked-empty, no-fallback, and authority tests.
- Synthetic overflow/truncation and skip-and-continue concentration proof.
- Companion provenance binding, lifecycle arithmetic, and v1 rejection.
- Mutation checkpoints and full canonical `tools/scripts` regression.

## Observability

Contracts record inputs, hashes, provenance, rank components, selection steps,
truncations, skips, transitions, concentration, churn, reasons, expiry,
independent-verification requirements, and all authority boundaries. This
slice creates no artifact, metric, alert, log process, service, scheduler, or
runtime loop.

## Versioning

This is an additive MINOR-level contract family with explicit schema version
2. Version 1 and every existing runtime contract remain unchanged. No package
version, dependency, release, or tag changes.

## Allowed Paths

- `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`
- `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision_v2.eligible.example.json`
- `specs/examples/autopilot_dynamic_allowlist_decision_v2.blocked.example.json`
- `specs/examples/autopilot_dynamic_paper_trial_manifest_v2.example.json`
- `specs/examples/autopilot_dynamic_paper_decision_binding_v2.example.json`
- `specs/examples/autopilot_dynamic_paper_position_binding_v2.example.json`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist_v2_contract.py`
- `docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`
- `docs/03-contracts-and-compatibility.md`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`
- `.agentic/registers/decisions.md`
- `.agentic/registers/agent-runs.md`
- `.agentic/runs/AG-20260727-015-auto2c-offline-governor/00-work-order.md`
- `.agentic/runs/AG-20260728-016-auto2c-v2-automatic-paper-contract/**`

## Acceptance Criteria

1. Both v2 schemas and all five examples validate.
2. Independent tests prove the ratified identity, ranking, truncation,
   concentration, transition, lifecycle, and authority boundaries.
3. Blocked decisions have no selection or transition outcome state; an early
   stale/input-policy block has no candidates, while candidate evidence may
   remain if qualification completed before a later global gate blocked.
4. V1, B2-c, and paper code/contracts remain byte-identical.
5. Governance records PR #260 landing and this accelerated queue without
   claiming implementation, host state, evidence, eligibility, or paper start.
6. E2 and Codex inner review pass before the Tier 3 draft PR.

## Verification Commands

| Command | Expected |
|---|---|
| `python3 -m json.tool` on new schemas/examples | pass |
| focused v2 contract pytest | pass |
| full canonical `tools/scripts` pytest | pass |
| Ruff and Python compile | pass |
| changed-path and protected-surface hash audits | pass |
| `git diff --check` | pass |

## Stop Conditions

Stop if live `origin/main` moves from the exact base; any v1, B2-c, or paper
contract/code must change; tests require governor/controller behavior; or any
host, real artifact, paper configuration, eligibility, trading, service,
deployment, secret, CI-1/OBS-1/OBS-3, AUTO-3, merge, or unattended-loop action
becomes necessary.

## Verification and Inner Review

- Focused v2 contract suite: 36 passed.
- Full canonical `tools/scripts` suite: 297 passed plus 70 subtests.
- Both schemas and all five examples validate with active RFC 3339 checking.
- All 120 contract/example JSON files parse.
- Ruff, Python compilation, diff whitespace, exact-base, scope, append-only,
  and protected-surface hash audits pass.
- The system-Python diagnostic reproduces only the known separately scoped
  CI-1 environment gap: 295 pass and two pre-existing observe format guards
  fail because that environment lacks the RFC 3339 checker.
- Multi-angle Codex inner review is CLEAN after the four repairs recorded in
  `02-inner-review-summary.md`.

E2 is achieved. The next gate is one exact Tier 3 draft-PR head and fresh
Claude read-only review. No merge or later slice is authorized.
