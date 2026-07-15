# Capabilities Register

Who/what can act, at which tier, with which constraints.

| Agent / machine | Tier | Known capability | Known constraint |
|---|---|---|---|
| Operator (Kevin) | T3 | Merge authorization, champion promotion, deploys, secrets, Hetzner SSH, live authority | Non-coder: needs plain-English briefs and paste-ready step cards; never needs to read diffs |
| Claude Code (local Mac session) | T1/T2 | Post-OP-44: Independent Reviewer — exact-SHA read-only review of protected-path PRs, plus local cargo/pytest and subagent inner review. (Pre-OP-44: was Lead Coder/PR authoring — see historical agent-runs.) | No SSH to Hetzner host; reviewing model must differ from author; outbound network sometimes sandboxed |
| Codex (cloud) | T0/T1 | Post-OP-44: Lead Coder + Operator Interface — authors/implements slices, inner review, opens PRs, gives Operator briefs/step cards. Remote slices on `codex/*` lanes. | No host access; must fetch the exact current head before reviewing/handing off (stale-checkout risk observed 2026-07-13) |
| GitHub Actions CI | — | Full workspace test gate on every PR (`cargo fmt`/`clippy`/`test --workspace` + Timescale service, pytest, contract validation, docs-structure gate) | Cannot exercise the Hetzner runtime (E5 evidence is operator-run) |
