# Assumptions Register

Working assumptions that outlive a single task. Validate or retire them.

| Assumption | Source | Owner | Validation plan | Review trigger |
|---|---|---|---|---|
| `Documents/CryptoPairs/cryptopairs` is the canonical local checkout tracking `origin/main` | Repo survey 2026-07-12 | Lead Coder | `git fetch` + status at session start | Any new clone or worktree appears |
| The Hetzner host at `/opt/cryptopairs` runs the promoted `main` baseline | `docs/AGENT_STATE.md` HOST-1 row; operator-run health probes | Operator | Operator runs runbook validation commands after each deploy | Any deploy or host incident |
| The model not holding the Coder role is available as Independent Reviewer for Tier 3 PRs (post-OP-44: Claude reviews Codex's work) | OP-44 role swap | Operator | Reviewer responds to a Tier 3 review prompt at the exact head SHA | Reviewer unavailable or roles reassigned |
