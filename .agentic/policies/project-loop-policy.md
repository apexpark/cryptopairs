# Project Loop Policy

This policy adapts the global `agentic-loop-harness` skill to CryptoPairs. It is
local scaffolding only. If this file conflicts with `AGENTS.md`, `AGENTS.md`
wins. If it conflicts with `docs/AGENT_STATE.md`,
`docs/playbooks/remote-agent-bootstrap.md`, higher-precedence safety docs, or
the current operator instruction, the higher-precedence source wins.

## Allowed Loop Class

Only manual, bounded repository-development loops are allowed by this adapter.
Each loop must have:

1. A concrete objective and Slice Loop Check.
2. A deterministic gate command that can reject bad output.
3. Durable state under `.agentic/runs/<run_id>/`.
4. A hard exit before it starts.
5. Independent checker review before merge, release, deployment, policy change,
   or any irreversible action.

If a task does not repeat or cannot be gated deterministically, keep it as a
normal one-shot task instead of a loop.

## Default-Deny Authority

Anything not listed in a loop spec is denied.

This adapter does not authorize:

- schedulers;
- production deployment;
- merge, squash merge, branch-protection override, or force-push;
- secret reads, secret writes, key rotation, or credential handling;
- external connectors or authenticated network calls;
- host or SSH access;
- live trading, execution-service POST paths, order dispatch, `ENTRY`, `EXIT`,
  or production trading jobs;
- background loops unless the operator explicitly authorizes the exact loop.

Operator approval for one action does not grant standing authority to future
loops.

## Path Boundaries

Loop specs must name allowed paths. By default, a loop may write only:

- `.agentic/runs/<run_id>/**`
- `.agentic/registers/loop-runs.md`
- files explicitly listed in the loop spec and allowed by local policy

Forbidden by default:

- `.env*` and secret-bearing files;
- runtime artifacts unless explicitly requested;
- deployment or host-runtime files unless explicitly authorized;
- protected long-lived branch refs;
- production configuration or live trading controls.

## Branch And Worktree Rules

Use the repository's existing branch, PR, and worktree rules from `AGENTS.md`
and `docs/ops/ai_workflow.md`.

Remote agents must not force-push long-lived branches. Reviewer work is
read-only unless the operator explicitly assigns an editing role.

## Gate And Checker Rules

Every loop must record:

- gate command;
- gate output path;
- pass/fail result;
- exact head SHA reviewed;
- checker identity or review source;
- unresolved risks.

Same-chat advisory review is not independent reviewer signoff unless the
operator records an explicit governance exception.

## Stop Rules

Stop immediately and ask for operator direction if:

- the AGENT_STATE pin is not reachable from `HEAD`;
- requirements ambiguity affects safety, integrity, risk, execution, or host
  behavior;
- the loop would need authority denied above;
- two consecutive iterations fail for the same reason;
- the iteration, time, token, or spend cap is reached;
- no new state transition or artifact value remains.

## Register Rules

After each accepted or stopped loop, update `.agentic/registers/loop-runs.md`
with the run id, objective, head SHA, gate result, checker outcome, accepted
change status, and reason for stopping.
