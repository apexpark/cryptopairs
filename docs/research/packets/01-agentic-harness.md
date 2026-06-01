# Packet: Agentic Harness

Status: PROPOSED

Owner: Operator

Date: 2026-06-01

## Purpose

Install a lightweight Apex harness methodology for CryptoPairs without changing
product behavior. The harness defines role separation, path ownership lanes,
exact-SHA review validity, and merge discipline for agentic development.

## Sources Consulted

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/04-repo-structure-and-ownership.md`
- `docs/05-agent-build-workflow.md`
- `docs/14-testing-standards.md`
- `docs/17-verification-protocol.md`
- `.github/pull_request_template.md`
- `.github/CODEOWNERS`
- `.github/workflows/ci.yml`
- `.github/workflows/docs-ci.yml`

## Role Separation

The harness uses three roles.

Operator:

- owns final acceptance;
- accepts or rejects Reviewer signoff;
- authorizes merges;
- approves governance exceptions;
- authorizes live services, production jobs, trading/order paths, sync loops, or
  background loops.

Coder:

- implements scoped slices;
- owns source, tests, scripts, CI, and narrow technical docs only when the slice
  allows it;
- preserves unrelated user changes;
- provides a Reviewer prompt after every commit or push.

Reviewer:

- reviews exact base/head SHA ranges;
- returns P1/P2/P3 findings with file:line references;
- may be a fresh Codex chat or a same-chat read-only sub-agent;
- must not edit, commit, push, change branches, merge, or approve its own work.

## File And Path Ownership Lanes

| Lane | Paths | Required review emphasis |
|---|---|---|
| Governance | `AGENTS.md`, `docs/AGENT_STATE.md`, `.github/**`, `docs/ops/**`, `docs/research/packets/**` | Role clarity, branch discipline, Operator authority |
| Contracts | `specs/contracts/**`, `specs/examples/**` | Schema validation, compatibility, versioning |
| Safety policy | `docs/00-guardrails.md`, `docs/01-product-scope.md`, `docs/10-architecture.md` through `docs/17-verification-protocol.md` | Fail-closed behavior and operational safety |
| Rust services | `services/**`, `crates/**`, `Cargo.toml`, `Cargo.lock` | Tests, persistence, risk/execution/integrity behavior |
| Web app | `apps/web/**` | Type-check, build/test, operator UX, contract consumption |
| Research/tools | `research/**`, `tools/**`, `plans/**` | Reproducibility, deterministic outputs, artifact hygiene |
| Infra/scripts | `infra/**`, `scripts/**`, `docker-compose*.yml`, `.env.example` | Secrets, deployment safety, rollback |

## Branch Naming

- Coder branches default to `codex/<short-slug>`.
- Other agent branches use `<agent-id>/<short-slug>`, for example
  `claude/<short-slug>`.
- Long-lived branches such as `main`, `rc/*`, and active integration branches
  must not be force-pushed by agents.
- The PR base is the Operator-designated base. If `docs/AGENT_STATE.md` is
  current, use its sprint base. If local state has moved beyond it, ask the
  Operator to confirm the base before merge.

## Review Protocol

1. Coder creates a small scoped branch and implements the slice.
2. Coder verifies the slice with commands appropriate to the changed files.
3. Coder commits and pushes.
4. Coder provides a Reviewer prompt with exact base/head SHAs and PR URL.
5. Reviewer performs read-only review and returns P1/P2/P3 findings,
   verification performed, residual risks, and acceptability.
6. Coder resolves findings or records a technical disagreement.
7. Any later push requires fresh review for the new head SHA.

Review approval is valid only for the exact head SHA reviewed.

## Same-Chat Read-Only Reviewer Sub-Agent Protocol

Same-chat review is allowed when explicitly requested. The Coder must instruct
the sub-agent:

- read-only review only;
- no edits;
- no commits;
- no pushes;
- no branch changes;
- no destructive commands;
- review exact base/head SHAs;
- return P1/P2/P3 findings with file:line references, residual risks,
  verification performed, and acceptability.

A failed or incomplete sub-agent review is not signoff.

## Merge Protocol

Merge requires all of the following:

1. Reviewer says the exact head SHA is acceptable for Operator review.
2. Operator explicitly accepts that Reviewer signoff.
3. Operator explicitly authorizes merge.
4. PR head SHA still equals the Operator-accepted SHA.
5. Required checks are passing or an Operator-approved exception is recorded.

Never merge on Coder judgment alone.

## Commit And Push Reviewer Prompt Requirement

After every Coder commit or push, the Coder must provide either:

- a complete Reviewer prompt for the exact head SHA; or
- a statement that the branch is not ready for review and why.

If the branch is pushed after review, previous review signoff is invalid.

## Exception And Signoff Process

Only the Operator can approve exceptions. Exception requests must include:

- rule being excepted;
- affected paths and branch;
- reason normal process is insufficient;
- risk;
- rollback path;
- duration/scope;
- whether fresh review is still required afterward.

Approved exceptions must be recorded in the PR body or a follow-up governance
packet.

## Enforcement Proposal

PROPOSAL: add a future script and CI job that detects protected-path changes and
requires PR-body evidence of Reviewer exact-SHA signoff and Operator acceptance.
Do not implement this enforcement in the initial harness slice.

Candidate protected paths:

- `AGENTS.md`
- `.github/**`
- `docs/ops/**`
- `docs/research/packets/**`
- `docs/00-guardrails.md`
- `docs/01-product-scope.md`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/04-repo-structure-and-ownership.md`
- `docs/05-agent-build-workflow.md`
- `docs/07-dependency-and-supply-chain-policy.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/13-secrets-and-security.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `docs/16-ui-styling-guide.md`
- `docs/17-verification-protocol.md`
- `docs/playbooks/**`
- `specs/contracts/**`
- `specs/examples/**`
- `services/execution-service/**`
- `services/strategy-service/**`
- `infra/env/**`
- `.env.example`

## Verification For This Packet

This packet is docs-only. Verification should confirm:

- the requested harness documents exist;
- the PR template includes exact-SHA review and Operator merge authority fields;
- no product code changed;
- `git diff --check` passes;
- docs index links remain valid.
