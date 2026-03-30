#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_signal_learning_overnight.sh [options]

Options:
  --strategy-url URL     Strategy service base URL (default: http://127.0.0.1:18083)
  --cycles N             Number of learning cycles (default: 48)
  --sleep-seconds N      Delay between cycles (default: 900)
  --timeframes CSV       Timeframes (default: 1m,15m,1h)
  --policy-json PATH     Policy path (default: infra/config/signal_learning_policy.json)
  --state-json PATH      State path (default: artifacts/signal_learning/state.json)
  --logic-json PATH      Logic path (default: artifacts/signal_learning/signal_logic.json)
  --output-root PATH     Output root (default: artifacts/signal_learning/runs)
  -h, --help             Show help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

STRATEGY_URL="http://127.0.0.1:18083"
CYCLES="48"
SLEEP_SECONDS="900"
TIMEFRAMES="1m,15m,1h"
POLICY_JSON="infra/config/signal_learning_policy.json"
STATE_JSON="artifacts/signal_learning/state.json"
LOGIC_JSON="artifacts/signal_learning/signal_logic.json"
OUTPUT_ROOT="artifacts/signal_learning/runs"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strategy-url)
      STRATEGY_URL="${2:-}"
      shift 2
      ;;
    --cycles)
      CYCLES="${2:-}"
      shift 2
      ;;
    --sleep-seconds)
      SLEEP_SECONDS="${2:-}"
      shift 2
      ;;
    --timeframes)
      TIMEFRAMES="${2:-}"
      shift 2
      ;;
    --policy-json)
      POLICY_JSON="${2:-}"
      shift 2
      ;;
    --state-json)
      STATE_JSON="${2:-}"
      shift 2
      ;;
    --logic-json)
      LOGIC_JSON="${2:-}"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

[[ "$CYCLES" =~ ^[0-9]+$ ]] || die "--cycles must be an integer"
[[ "$SLEEP_SECONDS" =~ ^[0-9]+$ ]] || die "--sleep-seconds must be an integer"

python3 tools/scripts/signal_learning_cycle.py \
  --strategy-service-url "$STRATEGY_URL" \
  --timeframes "$TIMEFRAMES" \
  --cycles "$CYCLES" \
  --sleep-seconds "$SLEEP_SECONDS" \
  --policy-json "$POLICY_JSON" \
  --state-json "$STATE_JSON" \
  --logic-json "$LOGIC_JSON" \
  --output-root "$OUTPUT_ROOT"
