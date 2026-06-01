# Apex Harness AI Workflow

This document installs a lightweight Apex harness methodology for CryptoPairs.
It adapts the workflow to this repository's existing `AGENTS.md`, docs-governed
process, GitHub PRs, Rust services, React UI, Python research/tooling, and
machine-readable contracts.

## Precedence

1. `AGENTS.md` is highest precedence for all agents.
2. Safety and product policies in `docs/00-guardrails.md` and
   `docs/01-product-scope.md` come next.
3. Governance docs in `docs/02-05`, `docs/07`, `docs/17`, and this file define
   workflow.
4. Domain policies in `docs/10-16` define technical safety requirements.

If this document conflicts with a higher-precedence file, stop and follow the
higher-precedence file.

## Roles

### Operator

The Operator is the human owner. Only the Operator can:

- accept Reviewer signoff;
- authorize merge;
- waive branch protection;
- approve governance exceptions;
- authorize live services, production jobs, trading/order paths, sync loops, or
  background loops.

### Coder

The Coder is an implementation agent. The Coder may edit source, tests, scripts,
CI, and narrow technical docs when the task allows it. The Coder must keep work
scoped to the slice, preserve unrelated user changes, and provide a Reviewer
prompt after every commit or push.

### Reviewer

The Reviewer is an independent review actor. The Reviewer may be a fresh Codex
chat, a separate agent thread, or a same-chat read-only sub-agent. The Reviewer
must not edit files, commit, push, change branches, merge, approve its own work,
or run destructive commands.

## Path Ownership Lanes

| Lane | Paths | Coder may edit when in scope | Reviewer posture |
|---|---|---:|---|
| Agent governance | `AGENTS.md`, `docs/AGENT_STATE.md`, `docs/ops/**`, `docs/research/packets/**`, `.github/**` | Yes, only for governance slices | Strict process review |
| Contracts and examples | `specs/contracts/**`, `specs/examples/**` | Yes, with schema/example validation and versioning review | Compatibility and fail-closed review |
| Rust services | `services/**`, `crates/**`, `Cargo.toml`, `Cargo.lock` | Yes, with Rust checks and relevant integration tests | Safety, persistence, and execution review |
| Web app | `apps/web/**` | Yes, with TypeScript/build/test coverage | Operator UX and contract-consumption review |
| Research and tools | `research/**`, `tools/**`, `plans/**` | Yes, with deterministic tests where applicable | Reproducibility and scope review |
| Infra and environment | `infra/**`, `docker-compose*.yml`, `.env.example`, `scripts/**` | Yes, but no production actions without Operator approval | Deployment, secrets, and rollback review |
| Runtime artifacts | `artifacts/**`, local caches, generated reports | No, unless explicitly requested and ignored | Verify not committed accidentally |

## Branch Naming

- Coder branches use `codex/<short-slug>` by default.
- Claude or other remote-agent branches use `<agent-id>/<short-slug>`, for
  example `claude/<short-slug>`.
- Long-lived branches such as `main`, `rc/*`, and active integration branches
  are protected by process. Do not force-push them.
- The PR base is the Operator-designated base for the slice. If
  `docs/AGENT_STATE.md` is current, use its sprint base. If local state has
  moved beyond `docs/AGENT_STATE.md`, stop and ask the Operator to confirm the
  base branch before merging.

## Coder Discipline

Coders must:

- work in small, reviewable slices;
- prefer TDD for behavior changes: write a failing test, verify it fails,
  implement, then verify green;
- keep edits scoped to the claimed files and domain;
- never revert unrelated user changes;
- never run destructive commands unless the Operator explicitly requests them;
- never start live services, production jobs, trading/order paths, sync loops,
  or background loops unless the Operator explicitly requests them;
- use exact file paths and verified facts;
- provide a Reviewer prompt after every commit or push.

For behavior changes, the minimum slice shape is:

1. failing test or fixture;
2. minimal implementation;
3. verification evidence;
4. commit;
5. Reviewer prompt for the exact head SHA.

Docs-only governance changes may skip TDD, but still need scoped diffs and
verification evidence.

## Reviewer Discipline

Reviewers must review exact base and head SHAs. A valid review includes:

- base SHA;
- head SHA;
- PR URL or branch;
- verification performed;
- P1/P2/P3 findings with file:line references;
- residual risks;
- explicit acceptability for Operator review.

Review approval is valid only for the exact head SHA reviewed. Any later push
invalidates the signoff and requires fresh review.

## Same-Chat Read-Only Reviewer Sub-Agent

A same-chat Reviewer sub-agent is acceptable only when the Operator or Coder
explicitly asks for sub-agents or read-only review. The Coder must instruct the
sub-agent:

- read only;
- do not edit files;
- do not commit, push, change branches, or merge;
- review only the stated base/head SHA range;
- return P1/P2/P3 findings with file:line references, verification performed,
  residual risks, and acceptability.

The Coder must not treat sub-agent silence, partial output, or failure to
hydrate as approval.

## Review And Merge Protocol

1. Coder opens a PR or prepares a branch.
2. Coder supplies a Reviewer prompt with exact base/head SHAs.
3. Reviewer returns findings and acceptability for that exact head SHA.
4. Coder resolves P1 and P2 issues or explains why a finding is not applicable.
5. If the branch changes, repeat review for the new head SHA.
6. Operator explicitly accepts Reviewer signoff for the reviewed head SHA.
7. Operator explicitly authorizes merge.
8. Before merge, verify the PR head SHA still matches the Operator-accepted SHA
   and checks are passing.
9. After merge, sync the local base branch and move to the next small slice.

Never merge on Coder judgment alone.

## Exception Process

Governance exceptions require an explicit Operator decision. The request must
include:

- the rule being excepted;
- why the normal process is insufficient;
- affected files and branches;
- risk and rollback path;
- exact duration or scope of the exception;
- whether fresh review is still required afterward.

Exceptions do not create precedent. Record accepted exceptions in the PR body or
the relevant governance packet.

## Enforcement Proposal

PROPOSAL only: a later slice may add a checker script and CI job for protected
paths. Do not implement enforcement until the Operator approves the protected
path set.

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
