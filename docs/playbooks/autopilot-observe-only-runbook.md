# 1m Autopilot Observe-Only Runbook

## Purpose

Run the AUTO-1 observe-only sidecar on Hetzner, capture evidence for 24-72
hours, and build an offline AUTO-1C attribution report.

This runbook is observe-only. It must not create execution order intents,
dispatch orders, restart services, or change runtime trading mode.

## Safety Invariants

1. Keep the observer disabled unless the command explicitly sets
   `AUTOPILOT_OBSERVE_ENABLED=true`.
2. Use only `AUTOPILOT_OBSERVE_TIMEFRAMES=1m` or omit the timeframe variable.
3. Provide an explicit `pair_id:selected_variant` allowlist.
4. Keep `EXECUTION_DISPATCH_MODE` unchanged. The observer reads dispatch mode
   and blocks candidates when execution-service reports `FAIL_CLOSED`.
5. Keep the evidence directory under `artifacts/autopilot_observe/`.
6. Treat report paper-trade outcomes as simulated attribution, not live PnL.

## Host Preflight

Run on Hetzner from `/opt/cryptopairs`.

```bash
cd /opt/cryptopairs

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="artifacts/autopilot_observe/runs/$RUN_ID"
mkdir -p "$RUN_ROOT"

git status --short --branch | tee "$RUN_ROOT/git_status.txt"
git rev-parse HEAD | tee "$RUN_ROOT/git_head.txt"
python3 --version | tee "$RUN_ROOT/python_version.txt"

curl -fsS http://127.0.0.1:8080/health | tee "$RUN_ROOT/data_health.json"
curl -fsS http://127.0.0.1:8083/health | tee "$RUN_ROOT/strategy_health.json"
curl -fsS http://127.0.0.1:8082/v1/execution/dispatch-mode | tee "$RUN_ROOT/dispatch_mode.json"
curl -fsS http://127.0.0.1:8082/v1/execution/kill-switch | tee "$RUN_ROOT/kill_switch.json"

AUTOPILOT_OBSERVE_ENABLED=false \
python3 tools/scripts/autopilot_observe.py --once | tee "$RUN_ROOT/disabled_probe.json"
```

Expected disabled probe:

```json
{
  "enabled": false,
  "recommended_action": "SET_AUTOPILOT_OBSERVE_ENABLED_TRUE_TO_RUN"
}
```

## Configure Allowlist And Quality Window

Replace the pair/variant and quality numbers with the operator-approved trial
set. Keep the allowlist small for the first 24-hour capture.

```bash
cat > "$RUN_ROOT/quality_windows.json" <<'JSON'
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
JSON

ALLOWLIST="PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z"
```

## One-Shot Trial Tick

Run one enabled tick before starting a long capture.

```bash
AUTOPILOT_OBSERVE_ENABLED=true \
AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON="$RUN_ROOT/quality_windows.json" \
AUTOPILOT_OBSERVE_OUTPUT_DIR="$RUN_ROOT/records" \
AUTOPILOT_OBSERVE_INTERVAL_SECONDS=60 \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=20 \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS=0 \
python3 tools/scripts/autopilot_observe.py --once | tee "$RUN_ROOT/one_shot_stdout.json"
```

Review the stdout and generated JSONL before starting the loop:

```bash
find "$RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print
tail -n 20 "$RUN_ROOT"/records/*/autopilot_observe_*.jsonl
```

## 24-72 Hour Capture Loop

Start the observer as a background process. The observer appends JSONL records
under `$RUN_ROOT/records`.

```bash
nohup env \
  AUTOPILOT_OBSERVE_ENABLED=true \
  AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
  AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON="$RUN_ROOT/quality_windows.json" \
  AUTOPILOT_OBSERVE_OUTPUT_DIR="$RUN_ROOT/records" \
  AUTOPILOT_OBSERVE_LOOP=true \
  AUTOPILOT_OBSERVE_INTERVAL_SECONDS=60 \
  AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=20 \
  AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS=0 \
  python3 tools/scripts/autopilot_observe.py \
  > "$RUN_ROOT/autopilot_observe.log" 2>&1 &
echo "$!" | tee "$RUN_ROOT/autopilot_observe.pid"
```

Monitor without changing runtime state:

```bash
cat "$RUN_ROOT/autopilot_observe.pid"
tail -n 100 "$RUN_ROOT/autopilot_observe.log"
find "$RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print -exec wc -l {} \;
tail -n 5 "$RUN_ROOT"/records/*/autopilot_observe_*.jsonl
```

Stop after the chosen observation window:

```bash
kill "$(cat "$RUN_ROOT/autopilot_observe.pid")"
sleep 2
tail -n 100 "$RUN_ROOT/autopilot_observe.log"
```

## Capture Attribution Inputs

Capture strategy-service history after the observation window. The service caps
each response at 20,000 rows; for exact multi-day attribution, prefer shorter
report windows or repeat this capture/report step daily.

`only_pass=false` is important for ready-window boundaries because the report
uses non-ready rows to split contiguous ready windows.

```bash
ATTRIBUTION_HOURS=24

curl -fsS \
  "http://127.0.0.1:8083/v1/strategy/pairs/opportunity-history?timeframe=1m&hours=$ATTRIBUTION_HOURS&only_pass=false&limit=20000" \
  -o "$RUN_ROOT/opportunity_history_1m.json"

curl -fsS \
  "http://127.0.0.1:8083/v1/strategy/pairs/paper-trades?timeframe=1m&hours=$ATTRIBUTION_HOURS&limit=20000" \
  -o "$RUN_ROOT/paper_trades_1m.json"

python3 -m json.tool "$RUN_ROOT/opportunity_history_1m.json" >/dev/null
python3 -m json.tool "$RUN_ROOT/paper_trades_1m.json" >/dev/null
```

## Build The AUTO-1C Report

Use a lookahead window that matches the attribution question. For the first
trial, `240` minutes is a useful bounded default for "did this observation lead
to a near-term simulated paper entry?"

```bash
python3 tools/scripts/autopilot_observe_report.py \
  --observe-dir "$RUN_ROOT/records" \
  --opportunity-history-json "$RUN_ROOT/opportunity_history_1m.json" \
  --paper-trades-json "$RUN_ROOT/paper_trades_1m.json" \
  --lookahead-minutes 240 \
  --output-json "$RUN_ROOT/autopilot_observe_report.json" \
  --output-markdown "$RUN_ROOT/autopilot_observe_report.md"

jq '.summary' "$RUN_ROOT/autopilot_observe_report.json"
sed -n '1,120p' "$RUN_ROOT/autopilot_observe_report.md"
```

## Evidence Bundle Checklist

Keep these files together for review:

- `$RUN_ROOT/git_status.txt`
- `$RUN_ROOT/git_head.txt`
- `$RUN_ROOT/data_health.json`
- `$RUN_ROOT/strategy_health.json`
- `$RUN_ROOT/dispatch_mode.json`
- `$RUN_ROOT/kill_switch.json`
- `$RUN_ROOT/disabled_probe.json`
- `$RUN_ROOT/quality_windows.json`
- `$RUN_ROOT/autopilot_observe.log`
- `$RUN_ROOT/records/**/autopilot_observe_*.jsonl`
- `$RUN_ROOT/opportunity_history_1m.json`
- `$RUN_ROOT/paper_trades_1m.json`
- `$RUN_ROOT/autopilot_observe_report.json`
- `$RUN_ROOT/autopilot_observe_report.md`

Do not merge this evidence into the repository. It is host/runtime evidence and
should stay under ignored `artifacts/`.

## Failure Handling

1. If the disabled probe is not disabled, stop and inspect environment leakage.
2. If data-service or strategy-service health fails, stop the observe run and
   investigate service health before collecting candidate evidence.
3. If execution-service reports malformed dispatch mode, active kill switch
   payload shape errors, or open-trades source errors, the observer should emit
   blocked records. Treat this as valid safety evidence, not as a reason to
   bypass guards.
4. If report generation fails on non-`1m` input, discard that evidence set for
   AUTO-1 and recapture with 1m-only inputs.
5. If endpoint row caps truncate the attribution input, lower
   `ATTRIBUTION_HOURS` or split analysis into daily evidence bundles.
