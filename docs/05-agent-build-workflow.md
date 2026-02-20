# Agent Build Workflow (Golden Path)

This is the standard workflow for building features safely and quickly.

## Focus Control

- Keep alpha scope status in `plans/alpha_plan.json`.
- Use `tools/scripts/alpha_tracker.py` for summary/checkpoints/sidetrack parking.
- Keep one active `IN_PROGRESS` item unless explicitly re-prioritized.

## Step 1: Read the right policies
- Always start with `docs/00-guardrails.md` and `docs/01-product-scope.md`
- Then consult governance docs as needed (`docs/02-05`, `docs/07`, `docs/17`)
- Then consult the relevant domain policy (`docs/10-16`)

## Step 2: Write or update contracts first
- Define schemas in `specs/contracts/`
- Add example payloads in `specs/examples/`
- Record compatibility notes if applicable

## Step 3: Tests next (even if minimal)
- Add schema validation or fixture-based tests (when code exists)
- Add replay test plan for market/order streams (when code exists)

## Step 4: Implement behind safe defaults
- Feature flags or config gating (once code exists)
- Default to fail-closed behavior for risk/integrity/execution

## Step 5: Observability
- Add metrics/log events for key state transitions
- Define alert conditions and severities in docs if needed

## Step 6: Operational readiness
- Update runbooks if procedures change
- Ensure kill switch pathways are documented and testable

## Step 7: Versioning
- Apply SemVer rules per `docs/02-versioning-and-releases.md`
- Add `CHANGELOG.md` entries for external behavior/contract changes

## Step 8: Small slices
Prefer multiple small PRs over one large PR:
- PR A: contracts + examples + docs
- PR B: scaffolding + tests
- PR C: implementation behind flag
- PR D: hardening + alerts + runbooks
