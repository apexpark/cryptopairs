# Strategy Tuning Operations Runbook

## Purpose

Run daily strategy tuning in a deterministic, fail-closed workflow that can resume cleanly after interruptions.

Control artifacts:
- `docs/22-strategy-tuning-control.md`
- `plans/strategy_tuning_plan.json`
- `infra/config/strategy_tuning_policy.json`
- `artifacts/strategy_tuning/*.json`

## Preconditions

1. Strategy and execution services are healthy.
2. `infra/config/strategy_tuning_policy.json` is present and reviewed.
3. Operator can run deploy workflow (`scripts/deploy.sh`) on target host.

## Daily Cycle

### 1) Resume context (interruption-safe)

```bash
python3 tools/scripts/alpha_tracker.py --plan plans/strategy_tuning_plan.json summary
```

Use the latest checkpoint `next_action` as the only starting action.

### 2) Capture baseline report

```bash
python3 tools/scripts/strategy_tuning_report.py \
  --profile baseline \
  --skip-reoptimize \
  --output-json artifacts/strategy_tuning/$(date -u +%Y-%m-%dT%H-%M-%SZ)-baseline.json
```

### 3) Apply candidate profile (dry-run first, then live)

Dry-run:

```bash
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --dry-run \
  --deploy-health-retries 90 \
  --deploy-health-sleep-secs 2 \
  --output-json artifacts/strategy_tuning/$(date -u +%Y-%m-%dT%H-%M-%SZ)-apply-promote-dryrun.json
```

Live apply:

```bash
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --deploy-health-retries 90 \
  --deploy-health-sleep-secs 2 \
  --output-json artifacts/strategy_tuning/$(date -u +%Y-%m-%dT%H-%M-%SZ)-apply-promote.json
```

### 4) Capture candidate report with baseline comparison

```bash
BASELINE=artifacts/strategy_tuning/<baseline-report>.json
python3 tools/scripts/strategy_tuning_report.py \
  --profile candidate \
  --compare-report "$BASELINE" \
  --output-json artifacts/strategy_tuning/$(date -u +%Y-%m-%dT%H-%M-%SZ)-candidate.json
```

Decision semantics:
- `PROMOTE`: candidate can remain active.
- `HOLD`: insufficient or mixed evidence; keep current config and gather more data.
- `REVERT`: fail-closed recommendation to restore baseline.

### 5) Revert if decision is REVERT

```bash
python3 tools/scripts/strategy_tuning_apply.py \
  --mode revert \
  --deploy-health-retries 90 \
  --deploy-health-sleep-secs 2 \
  --output-json artifacts/strategy_tuning/$(date -u +%Y-%m-%dT%H-%M-%SZ)-apply-revert.json
```

## Threshold Logic (Policy-driven)

Threshold source: `infra/config/strategy_tuning_policy.json`

Current gate families:
1. Actionable ratio delta.
2. Cost-gate pass ratio delta.
3. Guardrail blocked ratio delta.
4. Shadow disagreement ratio delta.
5. Reoptimize error cap.
6. Execution alert policy (`P1` and `P2`).

Missing baseline or runtime errors force `HOLD`.

## Git Cadence (Anti-scope-drift)

1. One slice at a time.
2. Commit immediately after each slice with evidence-ready changes.
3. Push after each commit.
4. Record checkpoint in plan file between slices.

## Rollback and Failure Handling

- Apply script always writes env backup before live mutation.
- On deploy failure, apply script restores backup automatically.
- If reporter fails, it emits a fail-closed `HOLD` report with error details.

## Evidence Checklist

For each daily run, retain:
1. Baseline report artifact path.
2. Candidate report artifact path.
3. Apply promote/revert artifact path.
4. Final decision and reasons.

This evidence is required before changing policy thresholds.
