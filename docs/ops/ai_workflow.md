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
- authorize merge on protected paths and Operator-only surfaces (Tiers 3–4 in
  §Merge Authority Tiers; Tier 1–2 mechanical merges are delegated there
  under a standing Operator decision);
- waive branch protection;
- approve governance exceptions;
- authorize live services, production jobs, trading/order paths, sync loops, or
  background loops.

### Coder

The Coder is an implementation agent. The Coder may edit source, tests, scripts,
CI, and narrow technical docs when the task allows it. The Coder must keep work
scoped to the slice, preserve unrelated user changes, and provide a Reviewer
prompt after every commit or push.

When the Operator directs the local Claude session to act as Coder for a
slice, it also carries the "Lead Coder" and "Operator Interface" duties
defined in `.agentic/policies/git-github.md`: authoring that slice, running
multi-angle inner review before any PR, and giving the Operator
plain-English briefs and paste-ready step cards. This is a per-slice
Operator assignment; the `AGENTS.md` §8 default work allocation (remote
agents for heavy implementation, local agent for review and curation) is
unchanged as the default.

### Independent Reviewer

The Reviewer is an independent review actor. Under the current `AGENTS.md`
topology, required independent code/spec review is cross-agent review by a
different remote agent than the implementer. The Reviewer may be a fresh Codex
chat or a separate remote-agent thread. The Reviewer must not edit files, commit,
push, change branches, merge, approve its own work, or run destructive commands.

A same-chat read-only sub-agent can provide advisory review, but it does not
satisfy required independent Reviewer signoff unless the Operator records an
explicit governance exception for that PR.

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
- complete the Slice Loop Check before coding unless the task is a trivial
  answer-only or read-only review;
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

## Slice Loop Check

Before starting a coding slice, the Coder must show that the slice creates
meaningful forward motion instead of another micro-hardening or refinement loop.
The check is required for implementation, tests, contracts, runbooks, tooling,
and governance changes unless the task is a trivial answer-only response or a
read-only review.

The Slice Loop Check has five fields:

1. **New input consumed** - name the new evidence, operator decision, incident,
   review finding, accepted design, or runtime observation this slice consumes.
2. **New state transition** - state what project state changes when the slice
   lands, for example design to contract, observe-only to paper-only, static
   allowlist to shadow dynamic allowlist, or disabled tool to operator-run
   command.
3. **New artifact/runtime/user value** - identify the concrete new value: a
   schema, test, report, command, runbook, ledger, dashboard, operator decision
   point, or safer runtime behavior.
4. **Why this is not repeating the prior slice** - compare against the exact
   existing capability and explain the material difference.
5. **Stop/defer condition** - list the boundaries that force the Coder to stop,
   defer, split the work, or request Operator approval instead of expanding
   scope.

If the first four fields cannot be answered concretely, do not code the slice.
If the stop/defer condition is triggered, stop and either split the slice or ask
the Operator for an explicit decision. The check is not a substitute for
`AGENTS.md` §2; it is an additional guard before spending implementation time.

Reviewer posture:

- For implementation PRs, Reviewers should treat a missing or vague Slice Loop
  Check as a process finding.
- For docs-only governance PRs, the check may be embedded in the PR body or the
  changed governance doc.
- A slice that only adds hardening must still identify the new failure mode,
  user value, and non-repetition boundary.

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

## Same-Chat Read-Only Advisory Sub-Agent

A same-chat read-only sub-agent is acceptable only when the Operator or Coder
explicitly asks for sub-agents or advisory read-only review. The Coder must
instruct the sub-agent:

- read only;
- do not edit files;
- do not commit, push, change branches, or merge;
- review only the stated base/head SHA range;
- return P1/P2/P3 findings with file:line references, verification performed,
  residual risks, and acceptability.

The Coder must not treat sub-agent silence, partial output, or failure to
hydrate as approval. Same-chat advisory review does not satisfy required
independent Reviewer signoff unless the Operator records an explicit governance
exception.

## Merge Authority Tiers

Adopted by Operator decision 2026-07-12; operative upon merge of the slice
that added this section (see `.agentic/registers/decisions.md`, which also
records the standing delegation for Tiers 1–2 and its hardened conditions). The tier table and rules live in
`.agentic/policies/git-github.md`; summary:

| Tier | Surface | Merge requirement |
|---|---|---|
| 1 | Docs / chore | Green CI. Lead Coder executes the mechanical squash merge under the standing delegation and reports after the fact. |
| 2 | Code outside protected paths | Clean multi-angle inner review + green CI. Same delegated execution and after-the-fact report. |
| 3 | Protected paths | Independent Reviewer CLEAN verdict at the exact head SHA + green CI + explicit Operator authorization on a plain-English brief. |
| 4 | Live capital, risk limits, paper→live toggle, Hetzner production runtime | Operator only. Never delegated. |

Rules that apply at every tier:

- Protected paths: source of truth is `.github/CODEOWNERS` once the
  expansion slice merges; until then the Operator decision of 2026-07-12 in
  `.agentic/registers/decisions.md` is binding.
- A review verdict is valid only for the exact head SHA it names; any push
  voids it and requires fresh review.
- Every PR states the merge tier it claims in the PR template. If tier
  classification is ambiguous, treat the PR as the higher tier.
- Delegated Tier 1–2 merges are mechanical execution of a standing Operator
  decision, not Coder judgment: the delegation is recorded in the decisions
  register, is revocable at any time, and never extends to Tier 3–4
  surfaces.
- Delegated merge mechanics: exactly `gh pr merge <N> --squash
  --delete-branch` on a qualifying PR, after verifying via `gh pr checks`
  that every required check passes and via `gh pr view` that the head SHA
  equals the inner-reviewed SHA. `--admin` may be used solely to satisfy the
  approval formality GitHub cannot path-scope — never to merge over
  failing, pending, or bypassed checks or unresolved review threads.
- Per-merge record: at merge time the Lead Coder posts a merge-record
  comment on the PR (tier claimed, head SHA verified, checks state,
  inner-review evidence) and reports to the Operator in the same session or
  at the next Operator interaction. Batching or deferring reports is
  forbidden.
- For Tier 2, the required review is the multi-angle inner review (two or
  more distinct read-only reviewer perspectives from the same session;
  Operator decision of 2026-07-12 confirms this standard for unprotected
  code). Cross-model Independent Reviewer signoff remains required for
  Tier 3; the same-chat advisory limitation in §Same-Chat Read-Only
  Advisory Sub-Agent continues to apply there.

## Review And Merge Protocol

Tier 1–2 PRs follow steps 1, 8 (verifying against the inner-review SHA for
Tier 2), and 9, under the standing delegation above. Tier 3 PRs follow all
steps. Tier 4 actions are Operator-only and follow the runbooks.

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

Never merge on Coder judgment alone: Tier 1–2 merges execute a recorded
standing Operator decision under its stated conditions; Tier 3–4 merges
require fresh per-PR Operator action. A merge outside those conditions is a
governance violation regardless of CI state.

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
- `services/account-service/**`
- `services/data-service/**`
- `services/execution-service/**`
- `services/strategy-service/**`
- `Cargo.toml`
- `Cargo.lock`
- `rust-toolchain.toml`
- `.githooks/**`
- `scripts/**`
- `docker-compose*.yml`
- `infra/env/**`
- `.env.example`
