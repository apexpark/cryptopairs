# Git and GitHub Policy

Branch lanes, merge authority, and PR rules for harness-driven work. The
branch-naming source of truth is `AGENTS.md` §8.5 and
`docs/ops/ai_workflow.md`; this file adds the merge-authority tiers adopted by
Operator decision 2026-07-12 (see `.agentic/registers/decisions.md`).

## Branch lanes

- `main` and `rc/*` are protected: no direct pushes, no force-push.
- Feature branches: `<agent-id>/<short-slug>` — e.g. `codex/<slug>`,
  `claude/<slug>`.
- One branch per change; clean tree at every handoff.

## Roles

- **Lead Coder** — the "Coder" role of `docs/ops/ai_workflow.md`, held by the
  local Claude session (`AGENTS.md` §8.1 "Local agent") when the Operator
  assigns it a slice. Authors that slice, runs inner review, opens PRs. This
  is a per-slice Operator assignment; the `AGENTS.md` §8 default work
  allocation (remote agents for heavy implementation, local agent for
  review and curation) is unchanged as the default.
- **Independent Reviewer** — the ai_workflow.md "Independent Reviewer" role,
  held by Codex. On protected paths the reviewing model must differ from the
  authoring model.
- **Operator** — the human authority (T3). Same role in both vocabularies.

## Merge authority tiers (Operator decision 2026-07-12)

| Tier | Surface | Who may merge, and when |
|---|---|---|
| 1 | Docs / chore | Lead Coder merges after green CI; reports after the fact. |
| 2 | Code outside protected paths | Lead Coder merges after clean multi-angle inner review + green CI; reports after the fact. |
| 3 | Protected paths | Independent Reviewer (different model than the author) reviews the exact head SHA and reports CLEAN + green CI + Operator authorization on a plain-English brief. A verdict against a stale SHA does not count. Every repair push requires a fresh review at the new head SHA. |
| 4 | Live capital, risk limits, paper→live toggle, Hetzner production runtime | Operator only. No delegation, ever. |

**Operative status:** Tiers 1–2 delegated merge becomes operative upon merge
of the workflow-manual amendment slice (GOV-SCAFFOLD-2), which amends
`docs/ops/ai_workflow.md` §Merge Authority Tiers and adds a merge-tier
declaration to the PR template. The standing delegation, its conditions
(green-checks verification before merge, per-merge record comment and
same-session report, no merging over failing/pending/bypassed checks), and
its forbidden-even-when-delegated list are recorded in
`.agentic/registers/decisions.md` (2026-07-12, OP-7 hardened per OP-8).
Delegated merges are mechanical execution of that recorded decision and
revocable at any time. Ambiguous tier → treat as the higher tier. Tiers 3–4
add requirements; they never relax under any reading.

Protected paths: single source of truth is `.github/CODEOWNERS` (expanded
to the full OP-8 list plus retained legacy protections by the
GOV-SCAFFOLD-4 slice). Its global `*` line is default review-routing only,
not a Tier 3 designation: Tier 3 = the specifically enumerated entries;
paths matched only by `*` take their tier from the register's Tier 2
enumeration. On disagreement between lists, the BROADER protection applies
until the lists are reconciled — a narrower CODEOWNERS pattern is a defect
to fix, never a relaxation to exploit. The decisions register keeps the
adoption trail. Note: `CHANGELOG.md` and `docs/AGENT_STATE.md` are
protected, so Tier 1–2 delegated PRs touch neither — both catch up in
Tier 3 governance PRs.

## Rules

1. No direct edits or pushes to `main` or `rc/*`.
2. No self-merge above Tier 2. Tier 3 requires recorded Operator
   authorization (PR body or decisions register, with head SHA).
3. Every PR uses `.github/pull_request_template.md`, including Base SHA /
   Head SHA fields and the Slice Loop Check.
4. PRs reference their work-order ID when one exists.
5. Model-diversity rule: on protected paths the reviewing model must differ
   from the authoring model; no model sole-reviews its own work there.
6. Fresh review after every repair push; stale-SHA verdicts are void.
7. No merge over failed CI or missing evidence without a recorded exception
   (`.agentic/templates/exception.md`) approved by the Operator.
8. Merge commits/squashes record the PR number; protected-path merges also
   record head SHA and merge SHA in the decisions register.
9. Force-push only on your own unshared lane branch.
