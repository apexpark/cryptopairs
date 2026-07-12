# Constitution

Non-negotiable operating rules for every agent working in this repository
through the `.agentic/` harness. If any rule here conflicts with `AGENTS.md`,
`docs/AGENT_STATE.md`, `docs/00-guardrails.md`, or the current operator
instruction, the higher-precedence source wins (see `.agentic/project.yaml`
`highest_precedence`).

1. **Repo governance wins.** CryptoPairs governance (`AGENTS.md`, guardrails,
   policy docs, `docs/ops/ai_workflow.md`) always overrides this harness. The
   harness adds structure; it never adds authority.
2. **Think before editing.** Non-trivial work starts with a work order and a
   context pack (`.agentic/templates/`), not with an edit. Trivial docs fixes
   may skip the work order but never skip the PR flow.
3. **Cite everything.** Claims about repo state cite files, commits, or command
   output. Assumptions are labeled as assumptions and recorded in
   `.agentic/registers/assumptions.md` when they outlive the current task.
4. **Small traceable changes.** One branch per change, thin slices, tests green
   at every slice boundary, evidence attached.
5. **Never fabricate.** Do not invent files, APIs, test results, CI state, or
   reviewer verdicts. An unverifiable claim is stated as unverified.
6. **No drive-by refactors.** Out-of-scope improvements become follow-up
   entries in `docs/AGENT_STATE.md` or a register, not silent diff growth.
7. **Stop on safety-critical ambiguity.** Anything ambiguous that touches risk
   limits, execution paths, kill-switch behavior, champion promotion, schema,
   secrets, deployment, or live/paper gates is a hard stop: escalate to the
   Operator with an escalation payload (`AGENTS.md` §7). `BLOCKED` and
   `NEEDS_CONTEXT` are successful safety outcomes, not failures.
8. **Least-powerful worker.** Delegate to the lowest worker tier
   (`.agentic/policies/permissions.md`) that can do the job.
9. **Evidence before status.** Do not claim reviewer-grade quality or green
   status without the evidence level required by
   `.agentic/policies/evidence.md`.
10. **Record operator decisions.** Every Operator decision that changes
    authority, scope, risk posture, or process is recorded in
    `.agentic/registers/decisions.md` in the same PR or the next docs PR.
