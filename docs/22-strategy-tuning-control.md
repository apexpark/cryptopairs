# Strategy Tuning Control

## Purpose

Define a deterministic, interruption-safe workflow for strategy lookback tuning and daily promote/hold/revert decisions.

Primary control artifacts:
- `plans/strategy_tuning_plan.json`
- `infra/config/strategy_tuning_policy.json`
- `artifacts/strategy_tuning/*.json`
- `tools/scripts/strategy_tuning_report.py`
- `tools/scripts/strategy_tuning_apply.py`

## Hard Control Rules

1. One active focus item only (`active_focus_id` in `plans/strategy_tuning_plan.json`).
2. Work-in-progress limit is one implementation slice at a time.
3. Every decision claim must point to a report artifact path.
4. Any side request must be parked in `sidetrack_queue` before context switch.
5. Unknown or missing safety inputs force `HOLD` (fail-closed).
6. Any candidate failure against hard thresholds forces `REVERT` recommendation.

## Resume Protocol (After Interruption)

1. Run:
   - `python3 tools/scripts/alpha_tracker.py --plan plans/strategy_tuning_plan.json summary`
2. Read latest checkpoint (`delta`, `next_action`, `blockers`).
3. Continue only the recorded `next_action`.
4. If scope changed, park new work first and append a checkpoint.

## Evidence Protocol

A slice is complete only when it has:
- code/doc paths changed,
- test evidence (command and pass/fail),
- report artifact path where relevant.

This follows `docs/17-verification-protocol.md` and `AGENTS.md`.

## Decision Lifecycle

1. Capture baseline report (current production tuning profile).
2. Apply candidate lookback profile.
3. Capture candidate report with comparison against baseline.
4. Decision from policy thresholds:
   - `PROMOTE` if all gates pass.
   - `HOLD` if evidence is inconclusive.
   - `REVERT` if degradation or safety alerts breach thresholds.
5. Archive both report artifacts for traceability.

## Fail-Closed Behavior

- Reporter exceptions produce `HOLD` recommendation.
- Apply script supports dry-run and always creates env backups before mutation.
- Promote/revert actions are constrained to strategy lookback keys and strategy-service rollout.

## Operational Cadence

- Morning: capture candidate report, compare to baseline, evaluate decision.
- If `PROMOTE`, promote and refresh baseline snapshot.
- If `REVERT`, revert profile and redeploy strategy-service.
- If `HOLD`, keep current profile and collect another cycle.
