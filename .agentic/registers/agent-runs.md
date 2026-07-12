# Agent Runs Register

One row per dispatched work order. Run folders live under
`.agentic/runs/AG-YYYYMMDD-NNN-<slug>/`.

| Work order | Title | Branch | Worker | Status | Evidence | Outcome |
|---|---|---|---|---|---|---|
| AG-20260712-001 | Install agentic scaffold v0 (build on loop-harness adapter) | `claude/agentic-scaffold-v0` | Claude (Lead Coder) | done | E1 achieved: JSON/YAML parse, scope check clean, 2× inner review + 3× Codex exact-SHA cycles, full CI green | PR #245 squash-merged at `2516fc5` |
| AG-20260712-002 | Make merge-authority tiers operative (workflow manual amendment) | `claude/workflow-tiers-operative` | Claude (Lead Coder) | done | E1 achieved: YAML/scope checks, 2-angle inner review (1 P1 + 7 P2 repaired, OP-8 ratifications), 3 Codex exact-SHA cycles, full CI green | PR #246 squash-merged at `7041b41` |
| AG-20260712-003 | CLAUDE.md Autonomy Doctrine on the AUTO ladder | `claude/claude-md-autonomy-doctrine` | Claude (Lead Coder) | in-progress | E1 target: doctrine consistent with AGENTS.md/guardrails/docs-12/docs-23/AUTO-2 and the registers; inner review clean | — |
