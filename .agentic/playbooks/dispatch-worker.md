# Playbook: Dispatch Worker

1. Confirm the work order is complete (tier, evidence level, paths, budgets,
   stop conditions) and the run folder exists.
2. Hand the worker ONLY the work order + context pack; do not rely on
   inherited conversation state.
3. Record dispatch in `.agentic/registers/agent-runs.md` (status:
   in-progress).
4. On `done`: verify the worker result against acceptance criteria and the
   claimed evidence; spot-check, never rubber-stamp.
5. On `NEEDS_CONTEXT`: extend the context pack, re-dispatch. This is a normal
   outcome.
6. On `BLOCKED`: run `playbooks/blocked-or-escalated.md`.
7. Update the agent-runs row (status, evidence, outcome) before starting the
   next order.
