# AG-20260729-018 — AUTO-2D bounded paper controller

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`
- `.agentic/runs/AG-20260726-013-auto2c-governor-contract/`
- `.agentic/runs/AG-20260726-014-auto2c-governor-scaffold/`
- `.agentic/runs/AG-20260727-015-auto2c-offline-governor/`
- `.agentic/runs/AG-20260728-016-auto2c-v2-automatic-paper-contract/`
- `.agentic/runs/AG-20260728-017-auto2c-v2-governor-runbook/`
- `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`
- `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision_v2.*.example.json`
- `specs/examples/autopilot_dynamic_paper_*_v2.example.json`
- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/autopilot_dynamic_allowlist_v2.py`
- `tools/scripts/autopilot_paper.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist_v2*.py`
- `tools/scripts/tests/test_autopilot_paper.py`
- `docs/03-api-contracts-and-versioning.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/13-secrets-and-security.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `CHANGELOG.md`

Verified starting point: PR #262 landed on `main` as exact SHA
`c5a5c1a370112567073eaf00088ff4c121a0170d`. The approved AUTO-2C v2
decision and AUTO-2D provenance contracts are present. Genuine E3 remains
`NOT RUN — separately gated`; no second comparable production schema-v2
selector window is available to this BUILD.

## Plan

1. Add one separate, disabled-by-default AUTO-2D controller.
2. Independently reconstruct the exact AUTO-2C v2 decision from raw,
   hash-bound inputs without importing the v2 governor or test auditor.
3. Add a strictly read-only verification mode and an explicit
   `--enabled --start` gate. Do not invoke the operational start gate.
4. Reuse the existing paper ledger in-process while enforcing controller-owned
   global exposure, lifecycle, idempotency, concurrency, expiry and no-fallback
   limits.
5. Emit the existing schema-v2 provenance records into one deterministic,
   exclusively created trial root; retain partial roots on failure.
6. Add focused synthetic replay, schema, mutation, determinism, concurrency,
   crash, preservation, command-safety, paper-lifecycle and no-actuation tests.
7. Add an Operator runbook and reconcile compatibility, versioning and
   governance records.
8. Run full E2 and bounded E4 verification, then perform Codex inner review.
   Record genuine E3 as separately gated and unrun.

## Interfaces / Contracts

- `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`:
  consumed unchanged.
- `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`:
  emitted unchanged.
- Existing v1/v2 examples and contracts: unchanged.
- Existing paper decision and position contracts: unchanged.
- New CLI (proposed path
  `tools/scripts/autopilot_dynamic_paper_controller_v2.py`):
  - no mode: bounded no-I/O disabled diagnostic;
  - `--verify-only`: read-only independent verification, no output;
  - `--enabled --start`: one foreground bounded paper-only controller.
- The controller imports the existing paper ledger only for paper mechanics.
  It does not import the AUTO-2C v2 governor or any test auditor.

## Risk & Failure Modes

- Any path, raw hash, provenance, policy, decision identity, freshness,
  qualification, ranking, transition or configuration mismatch refuses before
  start.
- `NONE` and null stay distinct and non-actionable. Unknown selector
  directions and realized-paper `NONE`, null or unknown directions refuse.
- Blocked, expired, schema-v1, malformed or internally inconsistent decisions
  cannot start.
- A pre-existing deterministic root, another controller owning the parent, an
  unresolved earlier root for the decision, or changed bound input refuses.
- Root creation is exclusive. Failures after creation retain the partial root;
  there is no overwrite, cleanup, repair, fallback or automatic restart.
- The loop uses monotonic elapsed time, a 60-second cadence, entry and exit-only
  deadlines, and the 90,000-second hard runtime bound.
- The explicit start timestamp must not be in the future or more than one
  cadence behind the actual wall clock, and the actual decision age must
  remain within the ratified 300-second automatic-start limit.
- The marks adapter is GET-only and loopback-only. No exchange, execution,
  deployment, service-configuration or live-trading surface is introduced.
- If open-position state cannot be reconstructed safely, the controller enters
  fail-closed exit-only/no-go handling and does not open another position.

## Test Plan

- Focused schema validation of every emitted provenance record.
- Production-shaped synthetic eligible replay proving independent
  recomputation and immutable-universe construction.
- Mutation checkpoints for every bound input and material decision/policy
  field, including direction-domain, ranking, truncation, concentration,
  transition, churn and decision-ID mutations.
- Deterministic verification/trial identity and ordering tests.
- Exclusive-root and concurrent-owner tests.
- Crash/partial-root retention, no-restart and no-fallback tests.
- Input byte/mode preservation and default no-I/O command-safety tests.
- Paper lifecycle tests for caps, entry/exit-only transition, hard runtime,
  candidate age, hold window and cooldown.
- No-actuation import/network/method tests.
- Full canonical `tools/scripts` suite (E2) and bounded adversarial subprocess
  checks (E4).
- Genuine E3: `NOT RUN — separately gated`.

## Observability

- Append-only provenance records bind the independently verified decision,
  immutable universe, controller lifecycle and every paper decision/position.
- A retained controller binding records exact input paths/hashes, Operator
  evaluation/start timestamps, observe source and loopback marks URL.
- The CLI emits bounded machine-readable disabled, verified, started,
  completed or refused summaries. It emits no secrets.
- Partial roots remain as audit evidence and cannot be reused.

## Versioning

- No existing contract version changes.
- This adds an opt-in paper-only controller and Operator runbook, so
  `CHANGELOG.md`, compatibility records and governance registers receive
  additive entries.
- The controller remains disabled by default and does not change existing
  paper behavior unless a future Operator supplies exact E3 inputs and
  separately authorizes one start.

## Gates and Stop Conditions

- Workflow:
  `PLAN → BUILD → INNER → Tier 3 draft PR → Claude exact-SHA REVIEW →`
  `genuine E3 → Operator MERGE authorization → separately authorized trial`.
- Stop if the live base moved, an existing contract/example or paper engine
  must change, a dependency is required, independent recomputation cannot
  remain independent, global paper exposure cannot be reconstructed safely, or
  any host/evidence/configuration/eligibility/trading/deployment scope is
  required.
