# Capabilities Register

Who/what can act, at which tier, with which constraints.

| Agent / machine | Tier | Known capability | Known constraint |
|---|---|---|---|
| Operator (Kevin) | T3 | Merge authorization, champion promotion, deploys, secrets, Hetzner SSH, live authority | Non-coder: needs plain-English briefs and paste-ready step cards; never needs to read diffs |
| Claude Code (local Mac session) | T1/T2 | Read/write on lane branches within work-order allowed paths, local cargo/pytest, subagent inner review, PR authoring | No SSH to Hetzner host; protected paths only via the Tier 3 flow; outbound network sometimes sandboxed (git push may need Operator paste) |
| Codex (cloud) | T0/T1 | Independent exact-SHA review, remote slices on `codex/*` lanes | No host access; review verdicts must state the SHA reviewed |
| GitHub Actions CI | — | Full workspace test gate on every PR (`cargo fmt`/`clippy`/`test --workspace` + Timescale service, pytest, contract validation, docs-structure gate) | Cannot exercise the Hetzner runtime (E5 evidence is operator-run) |
