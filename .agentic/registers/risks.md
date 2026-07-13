# Risks Register

Live risks to the process or the system that are accepted, mitigated, or
being watched. Point-in-time trading risk policy lives in
`docs/12-risk-and-execution-policy.md`; this register tracks residual and
process risks.

| Risk | Impact | Mitigation | Status |
|---|---|---|---|
| Harness conflicts with existing repo governance | Process ambiguity, wrong authority assumed | `AGENTS.md` and local governance explicitly win; harness is lowest precedence (`.agentic/project.yaml`) | active |
| CODEOWNERS does not yet cover the full protected-path list | Protected-path merge could slip through as Tier 2 | Decisions-register row of 2026-07-12 is binding in the interim; CODEOWNERS expansion slice closes the gap | active |
| Single human Operator | Authorization bottleneck; bus factor | Registers + `docs/AGENT_STATE.md` let any fresh session resume; step cards keep Operator actions paste-ready | active |
| Local checkout divergence (multiple stale worktrees on this machine) | Agents act on stale code or push from the wrong tree | Canonical local checkout is `Documents/CryptoPairs/cryptopairs`; every session verifies `git fetch` + pin reachability before work | active |
| Trial automation runs on the production Hetzner host | A bad merge reaches the live runtime via `scripts/deploy.sh` | Deploy paths are Tier 3/4; host access and deploys are Operator-only; fail-closed defaults in services | active |
