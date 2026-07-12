# CryptoPairs Agentic Harness

Project-local governance harness: the bounded-loop adapter plus the
dual-agent scaffold (v0) adopted by Operator decision 2026-07-12
(`registers/decisions.md`).

Local policy has highest priority. This harness cannot grant permissions
beyond `AGENTS.md`, `docs/AGENT_STATE.md`,
`docs/playbooks/remote-agent-bootstrap.md`, and the current operator
instruction. If this harness and repo governance disagree, repo governance
wins.

## Layout

- `project.yaml` — harness metadata, default-deny authorities, merge-authority
  pointers, protected-path mirror.
- `policies/` — constitution, worker tiers (`permissions.md`), evidence ladder
  (`evidence.md`), branch/merge rules (`git-github.md`), context policy, and
  the loop policy (`project-loop-policy.md`).
- `registers/` — decisions (machine-of-record for Operator decisions), risks,
  assumptions, capabilities, agent-runs, loop-runs.
- `templates/` — work order, context pack, worker result, evidence report,
  code/spec review, handoff, exception, PR-description mapping, loop
  spec/state.
- `playbooks/` — intake→work-order, dispatch-worker, review-and-integrate,
  blocked-or-escalated, repository-development-loop.
- `runs/` — one folder per work order: `AG-YYYYMMDD-NNN-<slug>/`.

## Quick start (any fresh session)

1. Hydrate per `AGENTS.md` §8.4: `AGENTS.md`, then `docs/AGENT_STATE.md`,
   then `docs/playbooks/remote-agent-bootstrap.md`; then read
   `registers/decisions.md`.
2. For a new task: `playbooks/intake-to-work-order.md`.
3. For merging anything: `policies/git-github.md` (tiers 1–4).
4. Blocked? `playbooks/blocked-or-escalated.md` — `BLOCKED` is a valid
   outcome.

This harness does not authorize schedulers, deployment, secrets, external
connectors, host access, production jobs, live trading, or background loops.
It grants no merge authority: until `docs/ops/ai_workflow.md` is amended to
reference the merge tiers (see the transition note in
`policies/git-github.md`), every merge requires per-PR Operator
authorization.
