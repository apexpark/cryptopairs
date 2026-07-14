---
id: AG-20260713-008
title: B2-a selector-view contracts
repo: cryptopairs
base_branch: main
working_branch: claude/b2a-selector-view-contracts
worker_tier: T1
required_evidence_level: E2
status: dispatched
---

# Work Order

## Objective

Implement AUTO-2B.2 slice B2-a per the merged proposal §6: versioned
contract updates and examples only. Shape decision recorded in the
decisions register (OP-35 row): observe_record v2 as a oneOf split.

## Scope

In: `specs/contracts/autopilot_observe_record.schema.json`,
`specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`,
`specs/examples/**` (updated snapshot example, new selector-view example),
one example-validation test, registers/state/CHANGELOG, this run folder.
Out: any tool code (B2-b/c), any capture start (B2-d), runbooks.

## Acceptance criteria

1. v1 entry example validates unchanged against the v2 observe schema; the
   new selector-view example validates; the updated snapshot example
   validates; a snapshot WITHOUT the new optional blocks stays valid.
2. Selector-view row shape contains no realized/outcome fields (tested).
3. All existing tests stay green (34 total incl. the new one).
4. Multi-angle inner review clean; Tier 3 flow on the PR.

## Stop conditions

Any field implying an outcome claim for selector-view rows → stop.
