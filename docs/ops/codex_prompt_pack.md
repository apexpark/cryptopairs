# Codex Prompt Pack

Reusable prompts for the CryptoPairs Apex harness. Replace placeholders before
use. `AGENTS.md` remains highest precedence.

## Coder Startup

```text
You are the Coder for CryptoPairs.

Before doing work, read:
1. AGENTS.md
2. docs/AGENT_STATE.md
3. docs/playbooks/remote-agent-bootstrap.md

Then run the self-preflight in docs/playbooks/remote-agent-bootstrap.md. If
preflight fails, stop and report before making changes.

After preflight passes, read:
4. docs/ops/ai_workflow.md
5. docs/05-agent-build-workflow.md
6. docs/17-verification-protocol.md
7. task-specific docs and contracts

Task:
<slice goal>

Constraints:
- Work in small scoped slices.
- Do not revert unrelated user changes.
- Do not run destructive commands.
- Do not start live services, production jobs, trading/order paths, sync loops,
  or background loops unless the Operator explicitly requests them.
- Prefer TDD for behavior changes.
- After every commit or push, provide a Reviewer prompt for the exact head SHA.
```

## Coder Slice Plan

```text
Create a small-slice plan for this task before editing.

Include:
- Slice Loop Check:
  - new input consumed;
  - new state transition;
  - new artifact/runtime/user value;
  - why this is not repeating the prior slice;
  - stop/defer condition;
- context and sources consulted;
- exact files expected to change;
- affected contracts or public behavior;
- risk and fail-closed behavior;
- tests and verification commands;
- observability impact;
- versioning/changelog impact;
- Reviewer handoff plan.

If the Slice Loop Check cannot be answered concretely, stop and propose the
smallest safe next step instead of coding.
```

## Slice Loop Check

```text
Run this before starting a coding slice.

Loop Check:
- new input consumed:
- new state transition:
- new artifact/runtime/user value:
- why this is not repeating the prior slice:
- stop/defer condition:

Decision:
- Proceed only if the first four bullets are concrete and the stop/defer
  condition is not triggered.
- Stop, split, or ask the Operator if the slice would become micro-hardening,
  repeat prior work, broaden scope, touch execution/order paths unexpectedly, or
  require host/runtime action not already approved.
```

## Reviewer Prompt

```text
Review this CryptoPairs PR.

Base SHA: <base>
Head SHA: <head>
PR: <url>

Read-only review only. Do not edit files, commit, push, change branches, merge,
or run destructive commands.

Review for:
- role separation clarity if governance is touched;
- Slice Loop Check presence and concrete forward motion if implementation,
  tests, tooling, contracts, runbooks, or governance workflow are touched;
- Operator-only merge/signoff authority if workflow is touched;
- exact-SHA review validity;
- Coder/Reviewer ownership boundaries;
- same-chat read-only sub-agent rules if applicable;
- commit/push Reviewer prompt requirement if workflow is touched;
- branch and merge discipline;
- whether any project-specific rules were imported incorrectly;
- contract compatibility and versioning if specs changed;
- fail-closed behavior if risk, execution, integrity, or trading paths changed;
- whether enforcement proposals match this repo's actual risk surfaces.

Return P1/P2/P3 findings with file:line references, residual risks,
verification performed, and whether the PR is acceptable for Operator review.
```

## Apex Harness Installation Reviewer Prompt

```text
Review this Apex-harness installation PR.

Base SHA: <base>
Head SHA: <head>
PR: <url>

Read-only review only. Do not edit files, commit, push, change branches, or run
destructive commands.

Review for:
- role separation clarity
- Operator-only merge/signoff authority
- exact-SHA review validity
- Coder/Reviewer ownership boundaries
- same-chat read-only sub-agent rules
- commit/push Reviewer prompt requirement
- branch and merge discipline
- whether any project-specific rules were imported incorrectly
- whether enforcement proposals match this repo's actual risk surfaces

Return P1/P2/P3 findings with file:line references, residual risks,
verification performed, and whether the PR is acceptable for Operator review.
```

## Tier 3 Exact-SHA Reviewer Prompt (Operator pastes into Codex)

```text
You are the Independent Reviewer for apexpark/cryptopairs PR #<N>.
<If this follows a repair push, state: "FRESH review after a repair push.
Your verdict at <old-sha> is void." and list what the repair commits claim
to fix.>

Review the PR at exactly head SHA <head-sha>.
Before reviewing, confirm the PR head is still this SHA; if it is not, STOP
and reply "STALE SHA — request a fresh review prompt" and do nothing else.

Conduct: read-only. Do not fix anything, do not merge, do not push.

Review against:
1. AGENTS.md, docs/00-guardrails.md, docs/ops/ai_workflow.md — no agent may
   gain authority these docs withhold.
2. Internal consistency of the diff with .agentic/registers/decisions.md
   and the protected-path list.
3. Correctness; behavior-asserting tests where applicable.
4. Safety invariants: kill switch never bypassed; fail-closed on
   stale/unknown state; live ENTRY/EXIT operator-confirmed (docs/12 rule 8);
   promotions operator-triggered; emergency stop-close automated (docs/12
   rule 9).

Report each finding as file:line, severity (P1 blocking / P2 should-fix /
P3 nit), and confidence. Coverage over precision.

End your reply with exactly one verdict line:
VERDICT: CLEAN at <head-sha>
or
VERDICT: FINDINGS at <head-sha>
```

A verdict that omits the SHA, names a different SHA, or follows a later push
does not count. Every repair push requires a fresh prompt with the new SHA.

## Operator Acceptance

```text
I accept Reviewer signoff for head SHA <head-sha> on PR <url> and authorize
merge, assuming the PR head still equals that SHA and required checks are
passing.
```

## Merge Preflight

```text
Before merge:
1. Confirm current PR head SHA equals Operator-accepted SHA <head-sha>.
2. Confirm required checks are passing.
3. Confirm no new pushes occurred after review.
4. Confirm no P1/P2 findings remain unresolved.
5. Merge only after Operator authorization.
```

## Governance Exception Request

```text
Requesting a governance exception.

Rule:
<rule>

Why normal process is insufficient:
<reason>

Affected files/branches:
<paths and branches>

Risk:
<risk>

Rollback:
<rollback>

Duration/scope:
<one-time, branch-only, PR-only, etc.>

Fresh review required afterward:
<yes/no and why>
```
