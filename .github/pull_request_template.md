## Summary
What does this PR change?

## Slice Loop Check
- New input consumed:
- New state transition:
- New artifact/runtime/user value:
- Why this is not repeating the prior slice:
- Stop/defer condition:

## Apex Harness / Agentic Review
- Role for this PR:
  - [ ] Coder implementation
  - [ ] Reviewer read-only review
  - [ ] Operator-authored change
- Merge tier claimed (see `docs/ops/ai_workflow.md` §Merge Authority Tiers):
  - [ ] Tier 1 — docs/chore
  - [ ] Tier 2 — code outside protected paths
  - [ ] Tier 3 — protected paths (Operator authorization required)
  - [ ] Tier 4 — Operator-only surface
- Base SHA:
- Head SHA:
- Reviewer prompt provided after latest push:
  - [ ] Yes
  - [ ] Not ready for review yet
- Reviewer signoff:
  - [ ] Pending
  - [ ] Accepted for Operator review at exact head SHA:
  - [ ] Not accepted; findings unresolved
- Operator merge authorization:
  - [ ] Pending
  - [ ] Operator accepted Reviewer signoff for exact head SHA and authorized merge
- Notes:

## Context & Policy References
- [ ] Consulted `AGENTS.md`
- [ ] Consulted `docs/ops/ai_workflow.md`
- [ ] Consulted `docs/00-guardrails.md`
- [ ] Consulted `docs/01-product-scope.md`
- Governance docs (check all that apply):
  - [ ] `docs/02-versioning-and-releases.md`
  - [ ] `docs/03-contracts-and-compatibility.md`
  - [ ] `docs/04-repo-structure-and-ownership.md`
  - [ ] `docs/05-agent-build-workflow.md`
  - [ ] `docs/07-dependency-and-supply-chain-policy.md`
  - [ ] `docs/17-verification-protocol.md`
- Relevant domain docs (check all that apply):
  - [ ] `docs/10-architecture.md`
  - [ ] `docs/11-data-integrity-policy.md`
  - [ ] `docs/12-risk-and-execution-policy.md`
  - [ ] `docs/13-secrets-and-security.md`
  - [ ] `docs/14-testing-standards.md`
  - [ ] `docs/15-observability-and-alerting.md`
  - [ ] `docs/16-ui-styling-guide.md`

## Contracts / Compatibility
- [ ] No contract changes
- [ ] Contract changes included (describe):
  - Contract files changed/added:
  - Compatibility impact:
  - Examples updated in `specs/examples/`:

## Safety & Failure Modes
- Fail-closed behavior preserved/added? Explain:

## Test Plan
- [ ] Schema/examples updated
- [ ] Tests added/updated (when applicable):
- How to validate locally:

## Observability
- Metrics/logs added/updated:
- Alerts impacted:

## Versioning & Changelog
- [ ] No external behavior change
- [ ] External behavior/contract change → updated `CHANGELOG.md`
- Proposed version bump (if tagging releases): MAJOR / MINOR / PATCH

## Checklist
- [ ] Small, reviewable change (or split into slices)
- [ ] Documentation updated
- [ ] Runbooks updated (if ops impact)
- [ ] If pushed after review, fresh review was requested for the new head SHA
- [ ] No merge will occur on Coder judgment alone
