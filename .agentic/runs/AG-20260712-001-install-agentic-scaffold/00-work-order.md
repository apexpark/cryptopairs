---
id: AG-20260712-001
title: Install agentic scaffold v0 (build on loop-harness adapter)
repo: cryptopairs
base_branch: main
working_branch: claude/agentic-scaffold-v0
worker_tier: T1
required_evidence_level: E1
status: dispatched
---

# Work Order

## Objective

Install the full `.agentic/` dual-agent scaffold (v0), building on the
existing `codex/agentic-loop-harness-adapter` branch, with registers seeded
with the Operator's adoption decisions of 2026-07-12 (OP-1).

## Scope

In: `.agentic/**` (policies, registers, templates, playbooks, project.yaml,
README, this run folder), `CHANGELOG.md`, `docs/AGENT_STATE.md` in-flight row.
Out: `docs/ops/dual_agent_workflow.md` (Slice 2), `CLAUDE.md` doctrine
(Slice 3), CODEOWNERS/PR-template expansion (Slice 4), any code.

## Allowed paths

- `.agentic/**`
- `CHANGELOG.md`
- `docs/AGENT_STATE.md`

## Forbidden paths

- Everything else. No service code, contracts, workflows, or deploy paths.

## Acceptance criteria

1. Harness files exist and are internally consistent (precedence, tier, and
   protected-path statements agree with the decisions register).
2. Decisions register seeded with the five OP-1 decisions.
3. JSON templates parse.
4. Multi-angle inner review clean before PR.
5. PR opened as Tier 3 (`.agentic/**` is protected), pending Codex exact-SHA
   review + Operator authorization.

## Verification commands

| Command | Expected |
|---|---|
| `python3 -m json.tool .agentic/templates/loop-spec.json` (and loop-state) | parses |
| `git diff --stat main...HEAD -- . ':!/.agentic' ':!CHANGELOG.md' ':!docs/AGENT_STATE.md'` | empty (scope respected) |

## Budget caps

Wall-clock: one session · Installs allowed: no

## Stop conditions

Any conflict between harness text and `AGENTS.md`/guardrails → stop and
escalate; do not weaken repo governance to fit the scaffold.

## Required report

Worker result + evidence in `06-worker-result.md`; inner-review verdicts in
`02-inner-review-*.md`.
