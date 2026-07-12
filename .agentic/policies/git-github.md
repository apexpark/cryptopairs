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
  local Claude session (`AGENTS.md` §8.1 "Local agent"). Authors slices,
  runs inner review, opens PRs.
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

**Transition note (binding until superseded):** the delegated merge authority
in Tiers 1–2 was adopted by Operator decision 2026-07-12 but is **not yet
operative**, because the higher-precedence `docs/ops/ai_workflow.md` ("Only
the Operator can authorize merge"; "Never merge on Coder judgment alone") and
the PR-template Operator-authorization checkbox still require per-PR Operator
authorization for every merge. Tiers 1–2 become operative only when the
workflow-manual slice amends `docs/ops/ai_workflow.md` and the PR template to
reference these tiers. Until then, all merges — every tier — require Operator
authorization. Tiers 3–4 add requirements; they never relax under any
reading.

Protected paths: single source of truth is `.github/CODEOWNERS`. Until the
CODEOWNERS expansion slice merges, the binding list is the Operator decision
of 2026-07-12 in `.agentic/registers/decisions.md`.

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
