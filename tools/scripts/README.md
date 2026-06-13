# Scripts

Place exchange discovery, migration, and operational helper scripts here.

## Alpha Tracking

Use the alpha tracker utility to keep delivery focused:

```bash
python3 tools/scripts/alpha_tracker.py summary
python3 tools/scripts/alpha_tracker.py set-focus --id 1
python3 tools/scripts/alpha_tracker.py set-status --id 1 --status IN_PROGRESS --note "started"
python3 tools/scripts/alpha_tracker.py checkpoint --delta "implemented API skeleton" --next-action "add integration test"
python3 tools/scripts/alpha_tracker.py park --title "investigate optional chart library" --return-after-id 2
```

## Data Pipeline E2E Check

Run a reproducible live check for capture/backfill/storage integrity:

```bash
python3 tools/scripts/data_pipeline_e2e_check.py \
  --data-service-url http://127.0.0.1:8080 \
  --instrument PI_XBTUSD \
  --timeframe 1m \
  --output-json artifacts/data_pipeline_e2e_report.json
```

## Manual Trade Flow E2E Check

Run a deterministic manual trade vertical-slice check:
- strategy cue selection
- account/reconcile seed
- kill-switch preflight
- intent submit + dispatch
- lifecycle history verification
- portfolio position verification
- optional emergency close legs

```bash
python3 tools/scripts/manual_trade_e2e_check.py \
  --timeframe 1m \
  --include-close \
  --require-flat-after-close \
  --output-json artifacts/manual_trade_e2e_report.json
```

## Kraken History Depth Probe

Run live Kraken depth checks to update the historical bounds policy:

```bash
python3 tools/scripts/kraken_history_depth_probe.py \
  --symbol PI_XBTUSD \
  --timeframes 1m 15m 1h \
  --output-json artifacts/kraken_history_depth_probe_PI_XBTUSD.json
```

## Secrets Lifecycle Audit

Audit hosted credential references, mounted-file wiring, and optional file-age checks:

```bash
python3 tools/scripts/secrets_lifecycle_audit.py \
  --policy-json infra/config/hosted_secrets_rotation_policy.json \
  --env-file infra/env/hosted-mode.env.example \
  --output-json artifacts/secrets_lifecycle_audit_report.json
```

## Fail-Closed Readiness Check

Run a pre-session go/no-go check for manual entries:

```bash
python3 tools/scripts/fail_closed_readiness_check.py \
  --exchange kraken_futures \
  --account-id primary \
  --window-minutes 60 \
  --output-json artifacts/fail_closed_readiness_report.json
```

## 1m Autopilot Observe-Only Sidecar

Run one observe-only tick that records what a `1m` autopilot would have
considered. This script never submits execution order intents or dispatches
orders.

By default it is disabled and an empty allowlist blocks all candidates. Enable
it explicitly and provide pair/variant allowlist entries as
`pair_id:selected_variant`.

```bash
AUTOPILOT_OBSERVE_ENABLED=true \
AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z" \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=20 \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS=0 \
python3 tools/scripts/autopilot_observe.py --once
```

Optional pair-level ready-window quality input:

```json
[
  {
    "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
    "timeframe": "1m",
    "selected_variant": "ROBUST_Z",
    "rows": 64,
    "profitable_rate": 0.73,
    "avg_net_bps": 7.4
  }
]
```

Pass it with:

```bash
AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON=artifacts/autopilot_observe/quality_windows.json \
AUTOPILOT_OBSERVE_ENABLED=true \
AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z" \
python3 tools/scripts/autopilot_observe.py --once
```

Outputs append-only JSONL records under `artifacts/autopilot_observe/YYYYMMDD/`.
Each record validates against
`specs/contracts/autopilot_observe_record.schema.json`.

## Signal vs Gate PnL Audit

Audit chart signal markers against gate state at entry time, with leg-level spread PnL attribution:

```bash
python3 tools/scripts/signal_gate_pnl_audit.py \
  --timeframe 1m \
  --hours 24 \
  --bars 600 \
  --output-json artifacts/analysis/signal_gate_pnl_audit_1m.json
```

Optional: scope to explicit pairs.

```bash
python3 tools/scripts/signal_gate_pnl_audit.py \
  --timeframe 1m \
  --pairs "PF_TAOUSD__PF_HYPEUSD,PF_XRPUSD__PF_ADAUSD" \
  --output-json artifacts/analysis/signal_gate_pnl_audit_pairs.json
```

## Strategy Tuning Reporter

Generate a deterministic tuning report with policy checks and a decision:

```bash
python3 tools/scripts/strategy_tuning_report.py \
  --profile candidate \
  --compare-report artifacts/strategy_tuning/<baseline-report>.json \
  --output-json artifacts/strategy_tuning/<candidate-report>.json
```

## Strategy Tuning Apply

Apply lookback profile updates with env backup, deploy integration, and rollback on deploy failure:

```bash
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --output-json artifacts/strategy_tuning/<apply-report>.json
```

Dry-run:

```bash
python3 tools/scripts/strategy_tuning_apply.py \
  --mode promote \
  --dry-run \
  --output-json artifacts/strategy_tuning/<apply-dryrun-report>.json
```

## Automated Strategy Maintenance Cycle

Run the full daily evaluation cycle (health checks, baseline, candidate apply dry/live, candidate report, and restore-original):

```bash
python3 tools/scripts/strategy_maintenance_cycle.py \
  --env-file /opt/cryptopairs/.env.hosted \
  --output-root artifacts/strategy_tuning/runs \
  --latest-report artifacts/strategy_tuning/latest_maintenance_report.json
```

Install/update cron automation on hosted server:

```bash
bash scripts/install_strategy_maintenance_cron.sh \
  --schedule "15 6 * * *" \
  --repo-root /opt/cryptopairs \
  --env-file /opt/cryptopairs/.env.hosted
```

## Strategy Maintenance Action Worker (Host-Side)

Process queued one-click promote/revert requests generated by strategy-service:

```bash
python3 tools/scripts/strategy_maintenance_action_worker.py \
  --repo-root /opt/cryptopairs \
  --queue-root artifacts/strategy_tuning/manual_action_queue \
  --once
```

Install cron worker:

```bash
bash scripts/install_strategy_maintenance_action_worker_cron.sh \
  --schedule "* * * * *" \
  --repo-root /opt/cryptopairs
```

Install systemd timer worker:

```bash
bash scripts/install_strategy_maintenance_action_worker_systemd.sh \
  --repo-root /opt/cryptopairs \
  --interval-seconds 60
```

## Signal Learning Cycle (Experimental, Recommendation-Only)

Run periodic monitoring of cues/expectancy/paper-trades and recursively update a confidence-gated signal-logic artifact:

```bash
python3 tools/scripts/signal_learning_cycle.py \
  --strategy-service-url http://127.0.0.1:18083 \
  --policy-json infra/config/signal_learning_policy.json \
  --cycles 48 \
  --sleep-seconds 900 \
  --output-root artifacts/signal_learning/runs \
  --state-json artifacts/signal_learning/state.json \
  --logic-json artifacts/signal_learning/signal_logic.json
```

Outputs:
- per-cycle reports under `artifacts/signal_learning/runs/`
- rolling state in `artifacts/signal_learning/state.json`
- recursive logic recommendations in `artifacts/signal_learning/signal_logic.json`
- deterministic universe selection output (`selection.top_1` and `selection.top_k`) in each cycle report
- selector observability diagnostics (`selected_with_paper_low_sample_count`, `top1_dwell_cycles_by_pair_tf`, `selection_turnover_rate`)
- optional selector concentration controls via policy (`selection.dwell_penalty_start_cycles`, `selection.dwell_penalty_per_cycle`, `selection.dwell_penalty_cap`)

This script does not apply runtime config changes automatically.

## Hosted Deployment Tracking

Use the same tracker utility with the hosted deployment plan:

```bash
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json summary
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json set-focus --id 1
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json checkpoint --delta "initialized provider accounts" --next-action "provision DNS records"
```
