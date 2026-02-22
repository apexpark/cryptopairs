# Strategy Maintenance Automation Runbook

## Purpose

Automate the daily strategy maintenance evaluation cycle while keeping final `PROMOTE` / `REVERT` actions manual.

Automated cycle scope:
1. Health checks for data/account/execution/strategy services.
2. Baseline report generation.
3. Candidate apply dry-run.
4. Candidate apply live run.
5. Candidate report generation with baseline comparison.
6. Automatic restore back to original profile after evaluation.
7. Publish latest cycle report for UI download links.

## Key Files

- `tools/scripts/strategy_maintenance_cycle.py`
- `scripts/install_strategy_maintenance_cron.sh`
- `artifacts/strategy_tuning/latest_maintenance_report.json`
- `artifacts/strategy_tuning/runs/<run-id>/...`

## One-Time Setup On Server

```bash
cd /opt/cryptopairs
bash scripts/install_strategy_maintenance_cron.sh \
  --schedule "15 6 * * *" \
  --repo-root /opt/cryptopairs \
  --env-file /opt/cryptopairs/.env.hosted
```

Check installed entry:

```bash
bash scripts/install_strategy_maintenance_cron.sh --show
```

## Manual Test Run (Before Cron)

```bash
cd /opt/cryptopairs
python3 tools/scripts/strategy_maintenance_cycle.py \
  --env-file /opt/cryptopairs/.env.hosted \
  --output-root artifacts/strategy_tuning/runs \
  --latest-report artifacts/strategy_tuning/latest_maintenance_report.json
```

## Verify Outputs

```bash
ls -lah artifacts/strategy_tuning/runs | tail -n 5
cat artifacts/strategy_tuning/latest_maintenance_report.json | head -n 60
```

Expected:
1. A new run folder with baseline/candidate/apply reports.
2. `latest_maintenance_report.json` updated.
3. `decision` field present (`PROMOTE`, `HOLD`, or `REVERT`).

## UI Validation

Analytics tab reads:
- `GET /v1/strategy/maintenance/latest`
- artifact downloads via `GET /v1/strategy/maintenance/artifact?path=...`

If available, report downloads appear in the Analytics panel.

## Fail-Closed Behavior

1. Health check failure forces cycle decision to `HOLD`.
2. Any failed cycle step marks cycle status `FAIL`.
3. Candidate apply failure keeps decision `HOLD`.
4. Restore failure is reported and marks cycle status `FAIL`.

## Manual Decision Actions (Operator-Controlled)

Automation only evaluates and reports.
Manual action still required for final configuration intent:
1. `PROMOTE` manually when you approve.
2. `REVERT` manually when you reject.

Use the maintenance guide for operator decision flow:
- `docs/playbooks/daily-strategy-maintenance-guide.md`

## Removing Automation

```bash
cd /opt/cryptopairs
bash scripts/install_strategy_maintenance_cron.sh --remove
```
