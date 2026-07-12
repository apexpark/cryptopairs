# Playbook: Blocked or Escalated

1. Record what was attempted (commands, files, output) in the run folder.
2. Name the blocker in one sentence.
3. Classify: missing context · missing permission/authority · environment ·
   conflicting requirement · repo-governance conflict · verification failure.
4. Decide: extend context and retry (once), or escalate.
5. Escalate with the `AGENTS.md` §7 escalation payload, as a step card: what
   happened, what is needed, exact paste text for the Operator.
6. Update the agent-runs register row (status: blocked) and, if the blocker
   is a standing risk, add/update a row in `registers/risks.md`.

`BLOCKED` is a successful safety outcome. Never push through ambiguity on
risk, execution, promotion, schema, secrets, deployment, or live/paper
boundaries.
