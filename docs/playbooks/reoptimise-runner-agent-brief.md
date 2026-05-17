# Reoptimise Runner Agent Brief

> Reusable project-specific brief for agents working on the bounded async
> reoptimization runner.
>
> `AGENTS.md` remains highest precedence. `docs/AGENT_STATE.md` remains the
> canonical project state. This file is reusable operating context only.

---

## Required Hydration

Every reoptimise runner agent must read, in order:

1. `AGENTS.md`
2. `docs/AGENT_STATE.md`
3. `docs/playbooks/remote-agent-bootstrap.md`
4. `docs/playbooks/reoptimise-runner-agent-brief.md` (this file)
5. `docs/proposals/reoptimise-background-runner-redesign.md`
6. `specs/contracts/strategy_reoptimize_run_*`
7. `specs/examples/strategy_reoptimize_run_*`
8. `docs/proposals/reoptimise-observability-runbook-plan.md`
9. `docs/proposals/reoptimise-api-script-migration-plan.md`
10. `docs/14-testing-standards.md`
11. `docs/03-contracts-and-compatibility.md`

Then run `docs/playbooks/remote-agent-bootstrap.md` §1 self-preflight. If it
fails, stop and report.

---

## Project Objective

Build a bounded asynchronous reoptimization system that is:

- durable and auditable;
- single-flight for mutation-producing work;
- budgeted and cancelable;
- observable through bounded metrics and structured logs;
- fail-closed by default;
- compatible with existing synchronous callers until an explicit versioned
  migration is approved.

The target is not "turn the old worker back on." The target is a safe async
runner whose scheduler/API/script enablement is introduced in approved slices.

---

## Hard Invariants

These apply to every slice and every PR:

- Default disabled; no production scheduler enablement without explicit
  operator approval.
- Existing `POST /v1/strategy/pairs/reoptimize` remains synchronous and
  compatible until a separately approved versioned migration.
- Unknown, stale, invalid, expired, canceled, degraded, failed, or
  contradictory run state maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
- Lease loss, lease expiry, budget exhaustion, artifact failure, and missing
  telemetry fail closed.
- No automatic `PROMOTE`.
- No automatic `REVERT`.
- No live `ENTRY` or `EXIT` enablement.
- No automatic graduation of repair-only provenance such as
  `RECANONICALIZED_LEGACY_ROW`.
- Host verification remains operator-only. Agents must not SSH into
  `cryptopairs` or claim host runtime evidence unless the operator provides it.
- Heavy workers stay fail-closed by default until leases, budgets,
  single-flight, observability, and canary evidence are implemented and
  approved.
- Metrics must use bounded labels. Never use `run_id`, `pair_id`,
  `operator_id`, `lease_owner`, hostnames, artifact paths, URLs, or free-form
  error text as labels.

---

## Slice Order

| Slice | Gate |
|---|---|
| Slice A — async contracts and examples | Done before implementation work. |
| Slice B — durable run state and lease state machine | Must land before Slice C. |
| Slice C — bounded runner loop | Must land before async endpoints or script migration. |
| Slice D — async API and script migration | Endpoints before scripts; defaults stay compatible. |
| Slice E — observability and runbooks | May be docs-only in parallel; Rust metrics must coordinate with Slice C/D edits. |
| Slice F — production canary | Operator-only after C-E and explicit approval. |

`docs/AGENT_STATE.md` is the current source of truth for exact slice status,
branch names, PRs, and next recommended move.

---

## Safe Parallelism Rules

- Safe in parallel:
  - local acceptance/review of a PR;
  - docs-only runbook work;
  - read-only audits;
  - independent review of an already-open implementation PR.
- Coordinate before editing:
  - `services/strategy-service/src/main.rs`;
  - shared Python maintenance scripts;
  - `docs/AGENT_STATE.md`;
  - `CHANGELOG.md`.
- Do not run two implementation agents with overlapping write ownership in
  `services/strategy-service/src/main.rs`.
- If a task needs files outside its assigned slice or owned file list, stop and
  escalate per `AGENTS.md` §7.

---

## Standard Verification

Run checks appropriate to changed files and report exact pass/fail:

- Rust changes:
  - `cargo fmt --all -- --check`
  - `cargo clippy --workspace --all-targets -- -D warnings`
  - `cargo test --workspace`
- Strategy repository persistence tests:
  - if `STRATEGY_TEST_DATABASE_URL` is available, run the relevant
    `strategy-service` Postgres-backed integration tests;
  - if unavailable locally, state that clearly and rely on CI/backstop.
- Contract/example changes:
  - JSON syntax for `specs/contracts/*.json` and `specs/examples/*.json`
  - schema validation for changed examples.
- Docs-only changes:
  - `git diff --check`

Host runtime verification is never agent-claimed unless operator-provided.

---

## PR Requirements

Every implementation PR should state:

- slice addressed;
- files touched and why;
- verification commands and results;
- in-scope items deliberately left for follow-up;
- operator-only steps, if any;
- `docs/AGENT_STATE.md` proposed delta or reason no state change is required.

Do not imply a host check, scheduler enablement, or live execution path passed
unless operator evidence is provided.
