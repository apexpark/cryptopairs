---
id: AG-YYYYMMDD-NNN
title:
repo: cryptopairs
base_branch: main
working_branch:
worker_tier: # T0 | T1 | T2 (T3 actions are Operator-only, never a work order)
required_evidence_level: # E1–E5, per .agentic/policies/evidence.md
status: draft # draft | dispatched | blocked | done
---

# Work Order

## Objective

One paragraph: what done looks like.

## Scope

In scope / out of scope, explicitly.

## Allowed paths

-

## Forbidden paths

- Everything not listed above; protected paths (see decisions register
  2026-07-12 / `.github/CODEOWNERS`) unless this order explicitly runs the
  Tier 3 flow.

## Acceptance criteria

1.

## Verification commands

| Command | Expected |
|---|---|
| | |

## Budget caps

Wall-clock: · Iterations: · Installs allowed: no

## Stop conditions

Return `BLOCKED` or `NEEDS_CONTEXT` if: safety-critical ambiguity
(constitution rule 7); acceptance criteria unreachable within budget;
required context missing.

## Required report

Worker result per `.agentic/templates/worker-result.md`, evidence level
stated.
