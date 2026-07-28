# Work Order — AG-20260728-017 AUTO-2C v2 Governor + C-d

Status: `in-review`

## 1. Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- `docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`
- C-a/C-b/C-c work orders and inner-review records under `.agentic/runs/`
- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`
- `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`
- the canonical v1/v2 examples under `specs/examples/`
- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist_v2_contract.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `.agentic/policies/evidence.md`
- `CHANGELOG.md`

Verified starting fact: live `origin/main` equalled exact authorized SHA
`670bba2e5c31374f5d09018ec86355ec352bd15f` before branch creation. PR #261
landed the v2 contracts/examples/tests at that SHA. Host, process, and artifact
state is not inspected and is treated as stale.

## 2. Plan

1. Add a separate disabled-by-default v2 CLI; do not alter the v1 governor.
2. Bind exact local input paths, raw-byte SHA-256 values, producer Git
   attestations, the exact v2 policy config, and an explicit evaluation time.
3. Reuse the merged production file/snapshot validators, then independently
   apply v2 qualification, lane ranking, reserved exploration, concentration
   skip-and-continue, deterministic truncation, transition, freshness, and
   expiry rules.
4. Support only first-transition static-baseline reconstruction. Refuse the
   future previous-accepted-v2-universe route until AUTO-2D supplies its
   independently accepted provenance.
5. Exclusively create deterministic JSON and Markdown in one fresh output
   directory. Add a strictly read-only reconstruction mode.
6. Add deterministic synthetic fixtures plus focused schema, replay, mutation,
   concurrency, preservation, and command-safety tests.
7. Add an Operator runbook and reconcile compatibility, CHANGELOG, and
   governance.
8. Run full E2 and bounded E4 verification. Record genuine E3 as
   `NOT RUN — separately gated`.
9. Perform Codex inner review, commit, push, and open a Tier 3 draft PR.

## 3. Interfaces / Contracts

- The unchanged output contract is
  `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`.
- The unchanged future AUTO-2D companion is
  `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`.
- New implementation surface:
  `tools/scripts/autopilot_dynamic_allowlist_v2.py`.
- New operational surface:
  `docs/playbooks/autopilot-dynamic-allowlist-v2-runbook.md`.
- The v1 governor, B2-c snapshots, paper contracts/code, and all v2
  contracts/examples remain byte-identical.
- Output remains advisory and non-actuating. `--verify-only` is an operational
  self-check, not the independent AUTO-2D verifier.

## 4. Risk & Failure Modes

- Missing, stale, malformed, non-finite, duplicate-key, hash-mismatched,
  symlinked, non-regular, concurrently changed, schema-v1, partial, or
  internally inconsistent evidence: reject without an artifact.
- Selector `NONE` and null: retain distinct counts, never form candidates.
- Unknown selector direction or any realized non-actionable direction: reject
  without an artifact.
- Too many candidates: rank deterministically, truncate, and record; never
  block solely on overflow.
- Concentration conflict: skip the candidate and continue; never weaken caps.
- Trusted freshness, separation, qualification, or transition failure: emit a
  schema-valid blocked-empty decision, with candidate evidence retained only
  when qualification completed before a global transition failure.
- Existing or concurrent output: refuse. A partial output root remains for
  diagnosis and cannot be repaired, reused, or removed by the tool.
- Future prior-universe route: fail closed with
  `PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE_NOT_IMPLEMENTED`.
- No fallback, self-approval, eligibility, configuration write, trial start,
  order, service, deployment, or live authority exists.

## 5. Test Plan

- Focused Draft 2020-12 schema validation with RFC 3339 format checking.
- Deterministic eligible and blocked replays.
- Exact policy hash, prior-set hash, and decision-ID recomputation.
- Ranking, tie-break, reserved exploration, skip-and-continue, truncation,
  addition/removal, concentration, churn, freshness, separation, and expiry.
- `NONE`/null distinction, unknown-direction refusal, and evidence-stream
  segregation.
- Hash, provenance, duplicate-key, non-finite, malformed, symlink,
  non-regular, mutation, collision, concurrency, and partial-root checkpoints.
- Read-only input preservation and `--verify-only` no-write reconstruction.
- Byte-identical protection for the v1 governor and merged contract/example
  surfaces.
- Full canonical `tools/scripts` regression plus Ruff, JSON parsing, compile,
  scope, and protected-hash checks.
- Bounded E4 subprocess proof for disabled no-I/O and unsupported-prior
  refusal/no-output behavior.
- E3: `NOT RUN — separately gated`; synthetic evidence is not E3.

## 6. Observability

The JSON decision records exact input and policy identities, source timing,
candidate evidence and ranks, every selection/skip/truncation, transition and
concentration calculations, gates, reasons, methodology, and all-false
authority boundaries. The Markdown report mirrors the decision for Operator
review. The runbook requires retained input/output hashes and an Operator
transcript, but this BUILD creates no runtime metric, service log, scheduler,
alert, or production artifact.

## 7. Versioning

This is additive implementation of the already merged v2 MINOR contract
family. No schema, example, package, dependency, release tag, B2-c, paper, or
v1 behavior changes. `CHANGELOG.md` and
`docs/03-contracts-and-compatibility.md` record the new separate CLI and
runbook. No version bump is required.

## 8. Authorization and Stop Conditions

Authorized: branch `codex/auto2c-v2-governor-runbook`, run
`AG-20260728-017`, implementation/tests/runbook/governance, E2/E4, inner
review, commit, push, and Tier 3 draft PR.

Stop rather than expand if the base moves or work requires a contract/example,
v1, B2-c, paper, dependency, host, real-artifact, evidence-capture,
configuration, eligibility, AUTO-2D, trading, service, deployment, secret,
CI-1, OBS-1, OBS-3, AUTO-3, merge, or unattended-loop change.

## 9. Gates

`PLAN → BUILD → INNER → Tier 3 draft PR → Claude exact-SHA REVIEW → Operator MERGE authorization`

This run ends at the draft PR. A CLEAN review does not authorize merge.
