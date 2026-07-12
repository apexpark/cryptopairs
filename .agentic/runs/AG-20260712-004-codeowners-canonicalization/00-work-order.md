---
id: AG-20260712-004
title: CODEOWNERS canonicalization (Tier 3 single source of truth)
repo: cryptopairs
base_branch: main
working_branch: claude/codeowners-expansion
worker_tier: T1
required_evidence_level: E1
status: dispatched
---

# Work Order

## Objective

Expand `.github/CODEOWNERS` to the full OP-8 protected-path list plus
retained legacy protections and declare it the single source of truth for
merge Tier 3, closing the final apex-forge audit gap. Record the PR #247
merge authorization and Slice 3 close-out.

## Scope

In: `.github/CODEOWNERS`, `.agentic/**` (registers, git-github.md,
project.yaml mirror), this run folder, `docs/AGENT_STATE.md`,
`CHANGELOG.md`.
Out: branch-protection settings (GitHub UI, Operator-only), any code, any
relaxation of an existing protection.

## Allowed paths

- `.github/CODEOWNERS`
- `.agentic/**`
- `docs/AGENT_STATE.md`, `CHANGELOG.md`

## Forbidden paths

- Everything else.

## Acceptance criteria

1. CODEOWNERS covers every path in the OP-8 register row plus all
   protections present in the pre-existing file (no relaxation).
2. project.yaml mirror and git-github.md agree with CODEOWNERS.
3. The CHANGELOG.md/AGENT_STATE delegated-PR consequence is recorded in the
   decisions register.
4. PR #247 authorization row recorded (review SHA + merge SHA, OP-16
   verdict confirmation).
5. Multi-angle inner review clean before PR; Tier 3 flow on the PR.

## Verification commands

| Command | Expected |
|---|---|
| `python3 -c "import yaml; yaml.safe_load(open('.agentic/project.yaml'))"` | parses |
| `git diff --stat main...HEAD` | only allowed paths |

## Budget caps

Wall-clock: one session · Installs allowed: no

## Stop conditions

Any change that would remove or narrow an existing CODEOWNERS entry →
stop and escalate (protections are never silently relaxed).

## Required report

Worker result + inner-review summary in this folder.
