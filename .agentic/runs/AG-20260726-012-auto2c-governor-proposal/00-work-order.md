---
id: AG-20260726-012
title: AUTO-2C governed dynamic-allowlist proposal
repo: cryptopairs
base_branch: main
base_sha: 29de6028b564869298bc0be7e581ed28df78bbf2
working_branch: codex/auto2c-governor-proposal
worker_tier: T1
required_evidence_level: E1
status: dispatched
---

# Work Order

## Objective

Author only the AUTO-2C governed dynamic-allowlist design proposal after the
Operator accepted the corrected B2-cR preserved-evidence replay. Reconcile the
living governance state, stop after the proposal, and leave every
implementation, contract, host, eligibility, AUTO-2D, and AUTO-3 action
unauthorized.

## New Evidence

- PR #256 landed B2-cR on `main` as
  `29de6028b564869298bc0be7e581ed28df78bbf2`.
- The corrected offline B2-c replay validated 46 closed paper events, excluded
  two open positions, represented 849 manifests and 13,584 selector rows, and
  preserved 11,418 `NONE` rows distinctly from null.
- The replay selected one realized-paper identity, rejected three,
  quarantined none, and found zero unknown directions.
- `churn.selector_view=null`, so the accepted evidence has no comparable v2
  selector history and cannot authorize dynamic eligibility.

## Slice Loop Check

- New input consumed: accepted B2-d/B2-cR production-shaped evidence.
- New state transition: the project gains a reviewed governor design; no
  candidate gains eligibility.
- New artifact/runtime/user value: explicit offline, deterministic,
  fail-closed, exact-hash-governed design and future acceptance criteria.
- Why this is not repeating B2-c/B2-cR: those slices validate evidence; this
  proposal defines the future governance boundary before paper eligibility.
- Stop/defer condition: any implementation, contract, test, runbook, CI,
  eligibility, host, capture, service, deploy, secret, OBS-1, OBS-3, AUTO-2D,
  AUTO-3, paper-trading, live-trading, or unattended-loop work stops the
  slice.

## Scope

In:

- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`.
- Append-only `.agentic/registers/decisions.md`.
- `.agentic/registers/agent-runs.md`.
- This run folder.
- `docs/AGENT_STATE.md`.
- `CHANGELOG.md` Governance section.

Out:

- Contracts, examples, Python/Rust code, tests, runbooks, CI, dependencies,
  services, runtime configuration, artifacts, eligibility inputs, host
  access, capture, replay, deployment, secrets, OBS-1, OBS-3, CI-1, AUTO-2D,
  AUTO-3, paper trading, live trading, and unattended loops.

## Binding Rules

1. Every unratified policy value is labeled `PROPOSAL`.
2. The accepted replay is valid design evidence but cannot yield actionable
   eligibility while `churn.selector_view=null`.
3. `NONE` stays distinct from null; both are non-actionable. Unknown direction
   strings fail closed.
4. Realized-paper and selector-view evidence remain segregated.
5. A future governed artifact requires exact-hash Operator approval before
   AUTO-2D consumption.
6. The future implementation queue is recommended but not started.
7. OP-45(e) stops the queue after this proposal for Operator-led rebuilding.

## Acceptance Criteria

1. The proposal contains the mandatory AGENTS.md planning sections.
2. It defines offline, deterministic, fail-closed inputs, outputs, identity,
   freshness, history, churn, concentration, quarantine, expiry, idempotency,
   concurrency, rollback, approval, testing, observability, and versioning
   boundaries.
3. Policy defaults are visibly proposals rather than recorded Operator
   decisions.
4. Governance records accurately reflect PR #256, the corrected replay,
   B2-d completion, this proposal, and the implementation stop.
5. Scope contains only the authorized docs/governance surfaces.
6. Docs/governance checks and Codex multi-angle inner review are clean.
7. The Tier 3 draft PR receives a fresh Claude exact-SHA review before any
   Operator merge decision.

## Versioning

Proposal-only and governance-only: no contract or runtime version bump. The
proposal records that a future new governed-decision contract would be an
additive MINOR-level feature with its own schema version `1`.
