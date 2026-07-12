---
id: AG-20260712-002
title: Make merge-authority tiers operative (workflow manual amendment)
repo: cryptopairs
base_branch: main
working_branch: claude/workflow-tiers-operative
worker_tier: T1
required_evidence_level: E1
status: dispatched
---

# Work Order

## Objective

Amend the workflow manual so the merge-authority tiers adopted in OP-1
become operative, and complete the Slice 1 record-keeping (PR #245
authorization row, standing OP-7 delegation row, Current State updates).

## Scope

In: `docs/ops/ai_workflow.md`, `docs/ops/codex_prompt_pack.md`,
`.github/pull_request_template.md`, `.agentic/registers/*.md`,
`.agentic/policies/git-github.md` (operative-status note),
`docs/AGENT_STATE.md`, `CHANGELOG.md`, this run folder.
Out: CODEOWNERS (Slice 4), `CLAUDE.md` doctrine (Slice 3), any code.

## Allowed paths

- `docs/ops/ai_workflow.md`, `docs/ops/codex_prompt_pack.md`
- `.github/pull_request_template.md`
- `.agentic/**`
- `docs/AGENT_STATE.md`, `CHANGELOG.md`

## Forbidden paths

- Everything else.

## Acceptance criteria

1. ai_workflow.md defines the tiers, tier-scoped protocol, and role mapping
   without weakening Tier 3–4 requirements.
2. PR template carries a merge-tier declaration.
3. Prompt pack contains the Tier 3 exact-SHA reviewer prompt.
4. Decisions register records the PR #245 authorization (review SHA + merge
   SHA) and the OP-7 standing delegation with its forbidden list.
5. Multi-angle inner review clean before PR; Tier 3 flow on the PR.

## Verification commands

| Command | Expected |
|---|---|
| `git diff --stat main...HEAD` | only allowed paths |
| docs-ci markdown-structure job | pass |

## Budget caps

Wall-clock: one session · Installs allowed: no

## Stop conditions

Any wording that would relax Tier 3–4 or contradict `AGENTS.md`/guardrails →
stop and escalate.

## Required report

Worker result + inner-review summary in this folder.
