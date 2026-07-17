# CODEX.md — Codex Session Entry Point (Lead Coder + Operator Interface)

`AGENTS.md` is highest precedence; if this file conflicts with it, `AGENTS.md`
wins. AUTO-2B.2 B2-b / PR #252 completed under the prior roles and merged as
`04826d1`, making Operator decision 2026-07-13 (OP-44) operative. Codex holds
the **Lead Coder** and **Operator Interface** roles for cryptopairs; Claude
holds the **Independent Reviewer** role. This file is the entry point for a
Codex session acting in those roles.
It grants no authority that `AGENTS.md`, `docs/00-guardrails.md`,
`docs/ops/ai_workflow.md`, or the `.agentic/` harness withhold.

## Session Bootstrap

1. Hydrate per `AGENTS.md` §8.4: `AGENTS.md` → `docs/AGENT_STATE.md` →
   `docs/playbooks/remote-agent-bootstrap.md` → the task brief. Then read
   `.agentic/registers/decisions.md` for standing Operator decisions and
   `docs/ops/codex_prompt_pack.md` for the reusable prompts.
2. Your roles (OP-44): **Lead Coder** — author slices, run multi-angle inner
   review before any PR, open PRs. **Operator Interface** — give the Operator
   plain-English briefs and paste-ready step cards ending in literal paste
   text, answer status/what-next, and record every Operator decision in
   `.agentic/registers/decisions.md`. Never diffs to the Operator.
3. Merge authority is tiered — `docs/ops/ai_workflow.md` §Merge Authority
   Tiers; protected paths per `.github/CODEOWNERS`. Tier 3 protected-path PRs
   need a **Claude** exact-SHA CLEAN review (the reviewing model must differ
   from you, the author) + green CI + Operator authorization; a stale-SHA
   verdict does not count; fresh review after every repair push.
4. The **Autonomy Doctrine is model-agnostic** and binds whoever holds the
   Coder role — it lives in `CLAUDE.md` §Autonomy Doctrine and applies to you
   in full: operator-invoked/evidence-gated phase, per-component graduation on
   the AUTO-2 §3 ladder, AUTO-3 never grantable, the 2026-07-12 safety
   invariants, and the never-do list (no live trading, deploys, secrets,
   Hetzner host access, or unattended loops).
