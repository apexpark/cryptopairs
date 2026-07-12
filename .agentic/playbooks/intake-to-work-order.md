# Playbook: Intake → Work Order

From an Operator request (or an accepted follow-up) to a dispatchable work
order.

1. Clarify the goal in one sentence; if it cannot be stated in one sentence,
   split it.
2. Identify the lane: docs/chore (Tier 1), unprotected code (Tier 2),
   protected path (Tier 3), or Operator-only (Tier 4 → stop, brief the
   Operator instead).
3. Read the policy files that touch the surface (`AGENTS.md` sections,
   guardrails, the relevant `docs/1x` policy, contracts).
4. Decide worker tier (`policies/permissions.md`) and required evidence level
   (`policies/evidence.md`).
5. Enumerate allowed and forbidden paths explicitly.
6. Run the Slice Loop Check (`docs/ops/ai_workflow.md`) — new input, state
   transition, concrete value, non-repetition, stop boundary.
7. Write `00-work-order.md` in `.agentic/runs/AG-YYYYMMDD-NNN-<slug>/` from
   the template.
8. Write `01-context-pack.md`.
9. If authority is unclear at any step: stop, record the question, escalate
   with a step card. Do not dispatch.
