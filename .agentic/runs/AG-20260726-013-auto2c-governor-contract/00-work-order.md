---
id: AG-20260726-013
title: AUTO-2C C-a governed dynamic-allowlist decision contract
repo: cryptopairs
base_branch: main
base_sha: f1da80f11e5a8d2244ebc9715d026f30068c0fb3
working_branch: codex/auto2c-governor-contract
worker_tier: T1
required_evidence_level: E2
status: dispatched
---

# Work Order

## Objective

Implement only AUTO-2C slice C-a: a schema-version-1 advisory governed-decision
contract, canonical blocked example, focused contract validation, compatibility
record, and governance reconciliation after the Operator rebuilt the queue under
OP-45(e). Do not implement or scaffold the governor.

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `.agentic/runs/AG-20260726-012-auto2c-governor-proposal/00-work-order.md`
- `.agentic/runs/AG-20260726-012-auto2c-governor-proposal/02-inner-review-summary.md`
- `.agentic/registers/decisions.md`
- `.agentic/policies/evidence.md`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `tools/scripts/autopilot_shadow_allowlist.py`
- `tools/scripts/autopilot_paper.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`

## New Evidence and Operator Decisions

- PR #257 landed the design proposal on `main` as exact SHA
  `f1da80f11e5a8d2244ebc9715d026f30068c0fb3`.
- The Operator ratified demotion-only, two comparable schema-v2 snapshots,
  86,400-second cutoff separation, 1,800-second current-source freshness, four
  entries, two directions per pair/variant, two entries per full instrument,
  one changed key, 25% baseline-denominator churn, 24-hour validity, no
  fallback, Operator-supplied read-only E3 copies, and separately scoped CI-1.

## Slice Loop Check

- New input: the Operator-ratified policy values and merged AUTO-2C proposal.
- New state transition: unratified prose becomes a versioned, machine-readable
  advisory decision boundary.
- New artifact value: future C-b/C-c work can validate and target one exact
  contract without inventing eligibility semantics.
- Non-repetition: B2-c summarizes advisory evidence; C-a defines only the
  future governor's output, not another scorer or capture.
- Stop/defer: any governor implementation/scaffold, runbook, paper integration,
  host/artifact action, CI-1/OBS-1/OBS-3, AUTO-2D/AUTO-3, service, deployment,
  secret, eligibility, or trading work stops the slice.

## Plan

1. Add the governed-decision schema and canonical blocked example.
2. Add focused schema/example tests for the adopted policy and authority
   boundaries.
3. Record additive compatibility/versioning impact.
4. Reconcile PR #257's landing and the OP-45(e) queue rebuild in living
   governance.
5. Run E2 checks and multi-angle Codex inner review.
6. Commit, push, and open a Tier 3 draft PR for fresh Claude exact-SHA review.

## Interfaces / Contracts

- Add `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`.
- Add `specs/examples/autopilot_dynamic_allowlist_decision.example.json`.
- Existing snapshot, observe, paper-decision, paper-position, and report
  contracts remain unchanged.
- Proposed entries are exact `pair_id + 1m + selected_variant + direction`
  long/short keys only. `NONE` and null remain distinct evidence counts but are
  non-actionable. Unknown directions cannot form a decision artifact.

## Risk & Failure Modes

- A schema-v1 predecessor is valid historical evidence but insufficient
  comparable selector history: represent it only as a blocked empty decision.
- Malformed, unknown-direction, provenance-conflicting, or internally
  inconsistent inputs are outside the valid output contract and must later
  produce no artifact.
- An eligible decision cannot exceed any adopted limit, use fallback, contain
  additions, or carry authority beyond exact-hash Operator review.
- Schema conditions enforce the highest-value invariants; C-b/C-c must add
  cross-field semantic and mutation proofs that JSON Schema cannot express.

## Test Plan

- Validate the schema itself and the canonical blocked example with a
  `FormatChecker`.
- Validate a synthetic, non-production eligible shape.
- Mutate timestamps, directions, policy constants, blocked output contents,
  authority flags, history, freshness, change, and churn fields and require
  rejection.
- Run the focused test plus the complete canonical `tools/scripts` suite.

## Observability

The contract records input paths/hashes/producer SHAs, cutoffs, evaluation and
expiry times, gate verdicts/reasons, transition sets, concentration, churn,
direction counts, and explicit advisory/no-authority flags. It adds no service
metric, alert, process, daemon, scheduler, or hosted loop.

## Versioning

This is a new additive contract type: MINOR-level compatibility impact, with
its own `schema_version: 1`, a canonical example, focused E2 validation,
compatibility note, and `CHANGELOG.md` entry. Existing contracts and package
versions remain unchanged; no release or tag is part of this slice.

## Allowed Paths

- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist_contract.py`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `docs/03-contracts-and-compatibility.md`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`
- `.agentic/registers/decisions.md`
- `.agentic/registers/agent-runs.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/**`

## Acceptance Criteria

1. Contract and example validate at E2.
2. Ratified policy constants and direction/authority boundaries are explicit.
3. `GOVERNOR_BLOCKED` requires an empty proposed set and a bounded reason.
4. `ELIGIBLE_FOR_OPERATOR_REVIEW` requires comparable schema-v2 selector
   history and every adopted cap.
5. Governance records PR #257's landing, the policy ratification, C-a, and the
   continued C-b/C-c/C-d/AUTO-2D stop.
6. No forbidden implementation or operational surface changes.
7. Codex inner review is clean before the Tier 3 draft PR is opened.

## Verification Commands

| Command | Expected |
|---|---|
| `python3 -m json.tool` on the new schema and example | pass |
| focused C-a pytest | pass |
| full canonical `tools/scripts` pytest | pass |
| schema/example and mutation assertions | pass |
| changed-path allowlist and source-boundary scans | pass |
| `git diff --check` | pass |

## Stop Conditions

Stop if the exact base moves, any existing contract must change, C-a cannot
express the adopted boundary without governor implementation, E2 cannot be
reached, or any forbidden host, artifact, eligibility, service, trading,
AUTO-2D/AUTO-3, OBS-1/OBS-3, or CI-1 action becomes necessary.
