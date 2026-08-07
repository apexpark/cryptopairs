# AG-20260807-019 — AUTO-2D first bounded paper experiment policy route

## Context & Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-v2-automatic-paper-policy.md`
- `.agentic/runs/AG-20260728-016-auto2c-v2-automatic-paper-contract/`
- `.agentic/runs/AG-20260728-017-auto2c-v2-governor-runbook/`
- `.agentic/runs/AG-20260729-018-auto2d-bounded-paper-controller/`
- `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json`
- `tools/scripts/autopilot_dynamic_allowlist_v2.py`
- `tools/scripts/autopilot_dynamic_paper_controller_v2.py`
- `docs/playbooks/autopilot-dynamic-allowlist-v2-runbook.md`
- `docs/playbooks/autopilot-dynamic-paper-v2-runbook.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `docs/02-versioning-and-releases.md`

Verified start: branch `codex/auto2d-bounded-paper-controller`, exact head
`26d3bfcd7579cb7b9266e6e3698c4f0e87099b14`, exact `origin/main`
`c5a5c1a370112567073eaf00088ff4c121a0170d`, clean worktree, and draft PR
#263 at that exact head. Claude's earlier CLEAN applies only to that starting
head and becomes stale when this amendment changes the PR.

## Plan

1. Extend the v2 decision contract with one explicit policy version while
   preserving the historical policy and examples.
2. Add the exact policy envelope and production-shaped canonical examples.
3. Make the governor apply static removal/churn only for the historical route;
   keep static overlap fully reported for the isolated experiment route.
4. Independently implement the same route in AUTO-2D without importing the
   governor or test auditor.
5. Record the root-local immutable-universe and no-later-promotion boundaries.
6. Add schema, replay, mutation, ranking, concentration, compatibility,
   determinism and no-actuation coverage.
7. Update both runbooks, compatibility, CHANGELOG and governance.
8. Run full E2, bounded E4 and exact-head Codex inner review, then commit, push
   and update draft PR #263. Do not run E3 or merge.

## Interfaces / Contracts

- Extend
  `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json` to
  recognize exact policy version
  `auto2c-v2-first-bounded-paper-experiment-1`.
- Preserve `auto2c-v2-paper-automatic-acceptance-1` as the historical route,
  including its removal/churn enforcement and existing canonical examples.
- Add canonical experiment governor-config and eligible-decision examples.
- Do not change B2-c snapshots, paper contracts/engine, provenance schema,
  services, runtime configuration or eligibility inputs.

## Risk & Failure Modes

- Policy-version ambiguity could silently weaken the historical route. Fail
  closed by exact complete-config matching and route-specific schema clauses.
- Skipping static transition checks could accidentally mutate shared paper
  configuration. The route grants no write authority and the controller may
  materialize the universe only within one exclusive trial root.
- Excess exploration or concentration could broaden the trial. Retain the
  two-exploration, two-addition, four-total, pair, variant/direction and
  instrument limits.
- Trial evidence could be misread as promotion evidence. Record false later
  promotion authority in the decision and binding; require a separate policy
  decision for any later paper/live promotion.
- Any malformed input, unknown direction, provenance/freshness mismatch,
  output collision, partial root or independent-recompute mismatch remains
  fail closed with no retry, cleanup, fallback or restart.

## Test Plan

- Validate historical eligible/blocked examples and the new experiment
  examples against Draft 2020-12 with RFC 3339 checking.
- Reproduce four qualified candidates, deterministic selection of three and
  one addition-instrument concentration skip.
- Prove the same evidence blocks under the historical static transition route
  but is experiment-eligible with reported removal count 3 and churn 1.25.
- Prove exact policy hash and decision identity, deterministic output,
  independent AUTO-2D recomputation, immutable root-local universe and false
  later-promotion authority.
- Mutate route version, config, static posture, authority, directions,
  evidence and decisions and require fail-closed rejection.
- Run focused suites, full canonical E2 and bounded E4 no-I/O/no-actuation
  proofs. Genuine E3 remains `NOT RUN — separately gated`.

## Observability

- JSON and Markdown identify the exact policy version, report static overlap,
  removals and churn, and state that those two values are not experiment
  eligibility gates.
- The controller binding records the immutable root-local universe, unchanged
  static configuration and false subsequent-promotion authority.
- Existing append-only provenance, event, paper-record and bounded CLI
  diagnostics remain unchanged.

## Versioning

- Add one exact policy version inside the existing decision schema-version-2
  family; no existing policy version is reinterpreted.
- This is additive but changes a protected contract and optional governor /
  controller behavior, so compatibility, CHANGELOG and governance records are
  required.
- No service/API version, dependency or paper contract change is included.

## Stop Conditions

Stop rather than expand scope if the base/head moves, historical policy
compatibility cannot be preserved, B2-c/paper/service changes become
necessary, genuine host evidence is required, or any configuration,
eligibility, trial-start, trading, deployment, secret, AUTO-3,
CI-1/OBS-1/OBS-3 or merge action becomes necessary.
