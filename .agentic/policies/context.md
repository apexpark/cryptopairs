# Context Policy

Context is packaged, not inherited. A worker (subagent, remote agent, fresh
session) must not be assumed to know anything beyond what its context pack
states.

Every dispatched worker receives:

1. The work order (objective, acceptance criteria, allowed/forbidden paths,
   tier, evidence level, budgets).
2. A context pack (`.agentic/templates/context-pack.md`): the minimum set of
   files to read, current state, and known constraints.
3. Stop conditions: what must trigger `NEEDS_CONTEXT` or `BLOCKED`.

Rules:

- Workers return `NEEDS_CONTEXT` rather than guessing; that is a successful
  outcome.
- Hydration order for fresh sessions is fixed by `AGENTS.md` §8.4:
  `AGENTS.md` → `docs/AGENT_STATE.md` →
  `docs/playbooks/remote-agent-bootstrap.md` → the task brief. The context
  pack supplements the task brief; it replaces none of the mandatory reads.
- Operator-provided runtime context (Hetzner output, screenshots) is quoted
  verbatim into the run folder, never paraphrased into fact.
