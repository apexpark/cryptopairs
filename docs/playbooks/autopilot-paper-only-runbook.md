# 1m Autopilot Paper-Only Runbook

## Purpose

Run the AUTO-2A static `1m` paper ledger on Hetzner after the observe-only
candidate capture is already available, then build a bounded offline paper
report from append-only paper artifacts.

This runbook is paper-only. It must not create execution order intents,
dispatch orders, restart services, change live `ENTRY` / `EXIT`, or enable a
dynamic allowlist.

## Safety Invariants

1. Keep the paper ledger disabled unless the command explicitly sets
   `AUTOPILOT_PAPER_ENABLED=true`.
2. Use only static allowlists. Entries may be legacy
   `pair_id:selected_variant` or direction-gated
   `pair_id:selected_variant:direction`.
3. Use only `1m` observe candidates and paper mark/outcome rows.
4. Keep all output under ignored `artifacts/autopilot_paper/`.
5. Treat realized net bps as paper simulation, not live PnL or fill evidence.
6. Do not start the hosted loop until this runbook is reviewed and the
   operator explicitly chooses the run window and allowlist.

## Host Preflight

Run on Hetzner from `/opt/cryptopairs`.

```bash
cd /opt/cryptopairs

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="artifacts/autopilot_paper/runs/$RUN_ID"
mkdir -p "$RUN_ROOT"/records

git status --short --branch | tee "$RUN_ROOT/git_status.txt"
git rev-parse HEAD | tee "$RUN_ROOT/git_head.txt"
python3 --version | tee "$RUN_ROOT/python_version.txt"

curl -fsS http://127.0.0.1:8080/health | tee "$RUN_ROOT/data_health.json"
curl -fsS http://127.0.0.1:8083/health | tee "$RUN_ROOT/strategy_health.json"
curl -fsS http://127.0.0.1:8082/v1/execution/dispatch-mode | tee "$RUN_ROOT/dispatch_mode.json"
curl -fsS http://127.0.0.1:8082/v1/execution/kill-switch | tee "$RUN_ROOT/kill_switch.json"

AUTOPILOT_PAPER_ENABLED=false \
python3 tools/scripts/autopilot_paper.py --once | tee "$RUN_ROOT/disabled_probe.json"
```

Expected disabled probe:

```json
{
  "enabled": false,
  "recommended_action": "SET_AUTOPILOT_PAPER_ENABLED_TRUE_TO_RUN"
}
```

## Configure Static Inputs

Point `OBSERVE_RUN_ROOT` at the reviewed observe-only run that produced
`autopilot_observe_*.jsonl` records. The observe source must still be running
or otherwise producing fresh records; a completed/stale observe run is not a
valid input for the 24-72 hour paper loop. Keep the allowlist static for
AUTO-2A. Use `pair_id:selected_variant` for pair-level gating or
`pair_id:selected_variant:direction` for direction-level gating. Mixed
allowlists are valid; a pair-level entry remains broad and permits both
directions for that pair/variant.

```bash
OBSERVE_RUN_ROOT="artifacts/autopilot_observe/runs/<observe-run-id>"
ALLOWLIST="PF_TAOUSD__PF_HYPEUSD:COINTEGRATION_Z:SHORT_SPREAD,PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z:LONG_SPREAD,PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z:SHORT_SPREAD"
HOLD_WINDOW_BARS=5
MAX_RUNTIME_SECONDS=259200
MAX_OBSERVE_CANDIDATE_AGE_SECONDS=120

test -d "$OBSERVE_RUN_ROOT/records"
find "$OBSERVE_RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print -exec wc -l {} \;

RUN_ID="$RUN_ID" \
ALLOWLIST="$ALLOWLIST" \
HOLD_WINDOW_BARS="$HOLD_WINDOW_BARS" \
MAX_RUNTIME_SECONDS="$MAX_RUNTIME_SECONDS" \
MAX_OBSERVE_CANDIDATE_AGE_SECONDS="$MAX_OBSERVE_CANDIDATE_AGE_SECONDS" \
python3 - <<'PY' > "$RUN_ROOT/run_config.json"
import json
import os

allowlist = []
direction_entries = 0
for item in os.environ["ALLOWLIST"].split(","):
    parts = item.split(":")
    if len(parts) not in {2, 3}:
        raise SystemExit(
            "ALLOWLIST entries must be pair_id:selected_variant or "
            "pair_id:selected_variant:direction"
        )
    entry = {
        "pair_id": parts[0],
        "selected_variant": parts[1],
    }
    if len(parts) == 3:
        entry["direction"] = parts[2]
        direction_entries += 1
    allowlist.append(entry)

if direction_entries == 0:
    static_allowlist_mode = "pair_variant"
elif direction_entries == len(allowlist):
    static_allowlist_mode = "pair_variant_direction"
else:
    static_allowlist_mode = "mixed"

print(
    json.dumps(
        {
            "run_id": os.environ["RUN_ID"],
            "timeframe": "1m",
            "static_allowlist_mode": static_allowlist_mode,
            "static_allowlist": allowlist,
            "hold_window_bars": int(os.environ["HOLD_WINDOW_BARS"]),
            "max_runtime_seconds": int(os.environ["MAX_RUNTIME_SECONDS"]),
            "max_observe_candidate_age_seconds": int(
                os.environ["MAX_OBSERVE_CANDIDATE_AGE_SECONDS"]
            ),
        },
        indent=2,
        sort_keys=True,
    )
)
PY

python3 -m json.tool "$RUN_ROOT/run_config.json" >/dev/null
cat "$RUN_ROOT/run_config.json"
```

## Require Fresh Observe Candidates

Create the freshness checker once and use it before the one-shot and each loop
tick. It fails closed if no `1m` observe candidate has a recent
`source_generated_at`.

```bash
cat > "$RUN_ROOT/check_observe_fresh.py" <<'PY'
import datetime as dt
import json
import pathlib
import re
import sys

LONG_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{6})\d+((?:[+-]\d{2}:\d{2})?)$")


def parse_observed_at(value):
    normalized = value.replace("Z", "+00:00")
    normalized = LONG_FRACTIONAL_SECONDS_RE.sub(r"\1\2", normalized)
    return dt.datetime.fromisoformat(normalized).astimezone(dt.timezone.utc)


path = pathlib.Path(sys.argv[1])
max_age_seconds = int(sys.argv[2])
latest = None

for line in path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get("timeframe") != "1m":
        continue
    source_generated_at = row.get("source_generated_at")
    if not source_generated_at:
        continue
    observed = parse_observed_at(source_generated_at)
    latest = observed if latest is None or observed > latest else latest

if latest is None:
    raise SystemExit("no fresh-checkable 1m observe candidates found")

age_seconds = int((dt.datetime.now(dt.timezone.utc) - latest).total_seconds())
if age_seconds > max_age_seconds:
    raise SystemExit(
        f"latest 1m observe candidate is stale: age_seconds={age_seconds}, "
        f"max_age_seconds={max_age_seconds}, latest={latest.isoformat()}"
    )

print(
    json.dumps(
        {
            "latest_source_generated_at": latest.isoformat().replace("+00:00", "Z"),
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        },
        sort_keys=True,
    )
)
PY

find "$OBSERVE_RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print0 \
  | sort -z \
  | xargs -0 -r cat \
  | tail -n 500 > "$RUN_ROOT/latest_observe_candidates.jsonl"

python3 "$RUN_ROOT/check_observe_fresh.py" \
  "$RUN_ROOT/latest_observe_candidates.jsonl" \
  "$MAX_OBSERVE_CANDIDATE_AGE_SECONDS" \
  | tee "$RUN_ROOT/observe_freshness_preflight.json"
```

## Capture Paper Marks

The paper ledger consumes mark rows with `mark_at` and `net_bps`. Capture the
strategy paper-trades endpoint and transform exited paper trades into mark rows.

```bash
PAPER_MARK_HOURS=24

curl -fsS \
  "http://127.0.0.1:8083/v1/strategy/pairs/paper-trades?timeframe=1m&hours=$PAPER_MARK_HOURS&limit=20000" \
  -o "$RUN_ROOT/paper_trades_1m.json"

jq '[.rows[]?
  | select(.exit_ts != null and .net_bps != null)
  | {
      pair_id,
      timeframe,
      selected_variant,
      direction,
      mark_at: .exit_ts,
      source_type: "paper_trade_outcome",
      net_bps
    }
]' "$RUN_ROOT/paper_trades_1m.json" > "$RUN_ROOT/paper_marks_1m.json"

python3 -m json.tool "$RUN_ROOT/paper_trades_1m.json" >/dev/null
python3 -m json.tool "$RUN_ROOT/paper_marks_1m.json" >/dev/null
```

## One-Shot Paper Tick

Run one enabled paper tick before starting a loop. This reads observe-only
candidate artifacts and writes append-only paper decisions/positions under
`$RUN_ROOT/records`.

```bash
candidate_args=()
candidate_args+=(--candidates-jsonl "$RUN_ROOT/latest_observe_candidates.jsonl")

AUTOPILOT_PAPER_ENABLED=true \
AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
AUTOPILOT_PAPER_HOLD_WINDOW_BARS="$HOLD_WINDOW_BARS" \
AUTOPILOT_PAPER_OUTPUT_DIR="$RUN_ROOT/records" \
python3 tools/scripts/autopilot_paper.py \
  --once \
  "${candidate_args[@]}" \
  --marks-json "$RUN_ROOT/paper_marks_1m.json" \
  --output-dir "$RUN_ROOT/records" | tee "$RUN_ROOT/one_shot_stdout.json"
```

Review the stdout and generated JSONL before starting a longer run:

```bash
find "$RUN_ROOT/records" -type f -name 'autopilot_paper_*.jsonl' -print -exec wc -l {} \;
tail -n 20 "$RUN_ROOT"/records/*/autopilot_paper_decisions_*.jsonl
tail -n 20 "$RUN_ROOT"/records/*/autopilot_paper_positions_*.jsonl
```

## 24-72 Hour Paper Loop

Start only after the one-shot output is reviewed. This shell loop refreshes
paper marks, snapshots recent observe candidates, and runs one paper ledger
tick every minute. It exits automatically at `MAX_RUNTIME_SECONDS`, which must
be between 1 and 259200 seconds (72 hours). It does not call execution-service
POST endpoints.

```bash
cat > "$RUN_ROOT/run_paper_loop.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

: "${OBSERVE_RUN_ROOT:?OBSERVE_RUN_ROOT is required}"
: "${ALLOWLIST:?ALLOWLIST is required}"
: "${HOLD_WINDOW_BARS:?HOLD_WINDOW_BARS is required}"
: "${RUN_ROOT:?RUN_ROOT is required}"
: "${MAX_OBSERVE_CANDIDATE_AGE_SECONDS:?MAX_OBSERVE_CANDIDATE_AGE_SECONDS is required}"

: "${MAX_RUNTIME_SECONDS:=86400}"
if ! [[ "$MAX_RUNTIME_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "MAX_RUNTIME_SECONDS must be an integer number of seconds" >&2
  exit 2
fi
if [ "$MAX_RUNTIME_SECONDS" -lt 1 ] || [ "$MAX_RUNTIME_SECONDS" -gt 259200 ]; then
  echo "MAX_RUNTIME_SECONDS must be between 1 and 259200 seconds" >&2
  exit 2
fi

started_epoch="$(date -u +%s)"
deadline_epoch="$((started_epoch + MAX_RUNTIME_SECONDS))"

while [ "$(date -u +%s)" -lt "$deadline_epoch" ]; do
  observed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  curl -fsS \
    "http://127.0.0.1:8083/v1/strategy/pairs/paper-trades?timeframe=1m&hours=24&limit=20000" \
    -o "$RUN_ROOT/paper_trades_1m.json"
  jq '[.rows[]?
    | select(.exit_ts != null and .net_bps != null)
    | {
        pair_id,
        timeframe,
        selected_variant,
        direction,
        mark_at: .exit_ts,
        source_type: "paper_trade_outcome",
        net_bps
      }
  ]' "$RUN_ROOT/paper_trades_1m.json" > "$RUN_ROOT/paper_marks_1m.json"

  find "$OBSERVE_RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print0 \
    | sort -z \
    | xargs -0 -r cat \
    | tail -n 500 > "$RUN_ROOT/latest_observe_candidates.jsonl"

  python3 "$RUN_ROOT/check_observe_fresh.py" \
    "$RUN_ROOT/latest_observe_candidates.jsonl" \
    "$MAX_OBSERVE_CANDIDATE_AGE_SECONDS" \
    | tee "$RUN_ROOT/observe_freshness_latest.json"

  AUTOPILOT_PAPER_ENABLED=true \
  AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
  AUTOPILOT_PAPER_HOLD_WINDOW_BARS="$HOLD_WINDOW_BARS" \
  AUTOPILOT_PAPER_OUTPUT_DIR="$RUN_ROOT/records" \
  python3 tools/scripts/autopilot_paper.py \
    --once \
    --candidates-jsonl "$RUN_ROOT/latest_observe_candidates.jsonl" \
    --marks-json "$RUN_ROOT/paper_marks_1m.json" \
    --output-dir "$RUN_ROOT/records"

  echo "{\"observed_at\":\"$observed_at\",\"status\":\"tick_complete\"}"
  sleep 60
done

echo "{\"observed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"max_runtime_reached\"}"
SH
chmod +x "$RUN_ROOT/run_paper_loop.sh"

nohup env \
  OBSERVE_RUN_ROOT="$OBSERVE_RUN_ROOT" \
  ALLOWLIST="$ALLOWLIST" \
  HOLD_WINDOW_BARS="$HOLD_WINDOW_BARS" \
  RUN_ROOT="$RUN_ROOT" \
  MAX_RUNTIME_SECONDS="$MAX_RUNTIME_SECONDS" \
  MAX_OBSERVE_CANDIDATE_AGE_SECONDS="$MAX_OBSERVE_CANDIDATE_AGE_SECONDS" \
  "$RUN_ROOT/run_paper_loop.sh" \
  > "$RUN_ROOT/autopilot_paper.log" 2>&1 &
echo "$!" | tee "$RUN_ROOT/autopilot_paper.pid"
```

## Monitor

```bash
cat "$RUN_ROOT/autopilot_paper.pid"
ps -p "$(cat "$RUN_ROOT/autopilot_paper.pid")" -o pid,etime,command
tail -n 100 "$RUN_ROOT/autopilot_paper.log"
find "$RUN_ROOT/records" -type f -name 'autopilot_paper_*.jsonl' -print -exec wc -l {} \;
jq -R 'fromjson? | select(.) | .decision_type' "$RUN_ROOT"/records/*/autopilot_paper_decisions_*.jsonl \
  | sort | uniq -c
```

## Stop

```bash
pid="$(cat "$RUN_ROOT/autopilot_paper.pid")"
command="$(ps -p "$pid" -o command= || true)"
case "$command" in
  *"$RUN_ROOT/run_paper_loop.sh"*)
    kill "$pid"
    ;;
  *)
    echo "Refusing to kill pid $pid; command does not match $RUN_ROOT/run_paper_loop.sh" >&2
    echo "$command" >&2
    exit 2
    ;;
esac
sleep 2
ps -p "$pid" -o pid,etime,command || true
tail -n 100 "$RUN_ROOT/autopilot_paper.log"
```

## Build The AUTO-2A Paper Report

```bash
python3 tools/scripts/autopilot_paper_report.py \
  --paper-dir "$RUN_ROOT/records" \
  --run-config-json "$RUN_ROOT/run_config.json" \
  --output-json "$RUN_ROOT/autopilot_paper_report.json" \
  --output-markdown "$RUN_ROOT/autopilot_paper_report.md"

jq '.summary' "$RUN_ROOT/autopilot_paper_report.json"
sed -n '1,160p' "$RUN_ROOT/autopilot_paper_report.md"
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
- `$RUN_ROOT/run_config.json`
- `$RUN_ROOT/check_observe_fresh.py`
- `$RUN_ROOT/latest_observe_candidates.jsonl`
- `$RUN_ROOT/observe_freshness_preflight.json`
- `$RUN_ROOT/observe_freshness_latest.json`
- `$RUN_ROOT/one_shot_stdout.json`
- `$RUN_ROOT/autopilot_paper.log`
- `$RUN_ROOT/run_paper_loop.sh`
- `$RUN_ROOT/paper_trades_1m.json`
- `$RUN_ROOT/paper_marks_1m.json`
- `$RUN_ROOT/records/**/autopilot_paper_decisions_*.jsonl`
- `$RUN_ROOT/records/**/autopilot_paper_positions_*.jsonl`
- `$RUN_ROOT/autopilot_paper_report.json`
- `$RUN_ROOT/autopilot_paper_report.md`

Do not merge this evidence into the repository. It is host/runtime evidence and
should stay under ignored `artifacts/`.

## Failure Handling

1. If the disabled probe is not disabled, stop and inspect environment leakage.
2. If data-service or strategy-service health fails, stop and investigate
   service health before starting a paper run.
3. If no observe candidate records exist, stop and run/review the AUTO-1
   observe-only capture first.
4. If mark capture is empty, one-shot entries may open but exits will defer
   until valid paper outcomes appear.
5. If report generation fails on non-`1m` input, discard that evidence set for
   AUTO-2A and recapture with 1m-only paper artifacts.
