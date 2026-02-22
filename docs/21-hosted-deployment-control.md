# Hosted Deployment Control

## Purpose

Keep hosted rollout deterministic, recoverable, and resistant to drift/hallucination.

Primary control artifacts:
- `plans/hosted_deployment_plan.json`
- `tools/scripts/alpha_tracker.py` (used with `--plan plans/hosted_deployment_plan.json`)

## Hard Control Rules

1. Keep one active focus item only (`active_focus_id`).
2. Require dependency readiness before starting an item.
3. Require evidence paths for every `DONE` item.
4. Park side requests in `sidetrack_queue` before context switching.
5. Record a checkpoint after each meaningful deploy action.
6. Treat provider/dashboard state as external truth; never infer completion without verification output.

## Deterministic Resume Protocol

When context is lost or interrupted:

1. Run:
```bash
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json summary
```
2. Read `active_focus_id` and latest checkpoint `next_action`.
3. Verify dependencies are `DONE`.
4. Execute only the checkpointed next action.
5. Record a new checkpoint immediately after action.

## Anti-Hallucination Evidence Rules

For each completed item include one or more evidence paths:

1. Command output artifact in `artifacts/`
2. Config path in repo (`infra/env/...`, `docker-compose...`, etc.)
3. Health check response evidence
4. Hosted URL or deployment ID reference in notes

## User Assistance Boundary

`requires_user=true` items in the plan require user action. Typical user-required tasks:

1. Account billing/plan purchase
2. Domain registrar and DNS ownership actions
3. Provider console actions requiring interactive login/MFA
4. Secret values that should not be visible to automation

All other tasks are automation-owned by default.

## Standard Commands

```bash
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json summary
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json set-focus --id 4
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json set-status --id 4 --status IN_PROGRESS --note "started"
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json checkpoint --delta "created env template" --next-action "prepare immutable images"
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json park --title "investigate optional analytics provider" --return-after-id 10
```

## Failure Recovery Rules

1. If deployment step fails, set item `BLOCKED` with blocker reason.
2. Do not skip failed item dependencies.
3. Add minimal remediation task if required, then re-run blocked step.
4. Keep fail-closed runtime mode enabled during recovery.

## Stop Conditions

Pause and request user input if:

1. Credential/secret access is required.
2. Billing or quota changes are required.
3. DNS ownership validation requires registrar interaction.
4. A production-impacting change lacks rollback path.

## Definition Of Done For Hosted Rollout

Hosted rollout is done only when:

1. Backend services are persistent and auto-restart.
2. Data capture/backfill and strategy reopt run continuously.
3. Public web URL loads and reaches healthy APIs.
4. Fail-closed readiness checks pass.
5. Recovery steps are documented and tested.
