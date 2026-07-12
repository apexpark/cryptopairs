---
id: AG-20260712-003
title: CLAUDE.md Autonomy Doctrine on the AUTO ladder
repo: cryptopairs
base_branch: main
working_branch: claude/claude-md-autonomy-doctrine
worker_tier: T1
required_evidence_level: E1
status: dispatched
---

# Work Order

## Objective

Create `CLAUDE.md` (Claude session entry point + Autonomy Doctrine mapped to
the native AUTO ladder), wire it into the harness, and record the PR #246
merge authorization and Slice 2 close-out.

## Scope

In: `CLAUDE.md`, `.agentic/project.yaml` (entry-point wiring),
`.agentic/registers/*.md` (authorization row, agent-runs), this run folder,
`docs/AGENT_STATE.md`, `CHANGELOG.md`.
Out: `AGENTS.md`, CODEOWNERS (Slice 4), any code, any doctrine content that
would grant AUTO-3 or relax an invariant.

## Allowed paths

- `CLAUDE.md`
- `.agentic/**`
- `docs/AGENT_STATE.md`, `CHANGELOG.md`

## Forbidden paths

- Everything else.

## Acceptance criteria

1. Doctrine consistent with `AGENTS.md` §8, `docs/00-guardrails.md`,
   `docs/12` rules 8–9, `docs/23` promotion lifecycle, and the AUTO-2
   proposal's non-negotiable sequence and stop gates.
2. AUTO-3 explicitly ungrantable by the doctrine; promotions
   operator-triggered at every rung.
3. Safety invariants restated without weakening (verbatim intent of the
   decisions-register row).
4. PR #246 authorization row recorded (review SHA + merge SHA).
5. Multi-angle inner review clean before PR; Tier 3 flow on the PR.

## Verification commands

| Command | Expected |
|---|---|
| `python3 -c "import yaml; yaml.safe_load(open('.agentic/project.yaml'))"` | parses |
| `git diff --stat main...HEAD` | only allowed paths |

## Budget caps

Wall-clock: one session · Installs allowed: no

## Stop conditions

Any doctrine wording that could be read as authorizing live automation,
unattended loops, or promotion without Operator action → stop and escalate.

## Required report

Worker result + inner-review summary in this folder.
