#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/status_weekend_signal_monitoring.sh [--repo-root PATH] [--tail-lines N]
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

is_running() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

REPO_ROOT="$(pwd)"
TAIL_LINES="20"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --tail-lines)
      TAIL_LINES="${2:-}"
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

[[ "$TAIL_LINES" =~ ^[0-9]+$ ]] || die "--tail-lines must be an integer"

cd "$REPO_ROOT"
RUNTIME_DIR="$REPO_ROOT/artifacts/runtime"

report_pid() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "$label: not started (missing pid file)"
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    echo "$label: pid file empty"
    return
  fi
  if is_running "$pid"; then
    echo "$label: running pid=$pid"
    ps -p "$pid" -o pid=,etime=,command=
  else
    echo "$label: not running (stale pid=$pid)"
  fi
}

echo "=== Weekend Monitoring Status ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
report_pid "signal-learning" "$RUNTIME_DIR/signal-learning-weekend.pid"
report_pid "compare-snapshots" "$RUNTIME_DIR/compare-snapshots-weekend.pid"
report_pid "benchmark" "$RUNTIME_DIR/benchmark-weekend.pid"

echo ""
echo "=== Health ==="
for url in \
  "http://127.0.0.1:18080/health" \
  "http://127.0.0.1:18081/health" \
  "http://127.0.0.1:18082/health" \
  "http://127.0.0.1:18083/health"
do
  printf "%s -> " "$url"
  curl -fsS "$url" || echo "DOWN"
  echo ""
done

latest_log() {
  local pattern="$1"
  ls -1t $pattern 2>/dev/null | head -n1 || true
}

SL_LOG="$(latest_log "$RUNTIME_DIR/signal-learning-weekend-*.log")"
CP_LOG="$(latest_log "$RUNTIME_DIR/compare-snapshots-weekend-*.log")"
BM_LOG="$(latest_log "$RUNTIME_DIR/benchmark-weekend-*.log")"

echo ""
echo "=== Log tails ==="
for pair in \
  "signal-learning:$SL_LOG" \
  "compare-snapshots:$CP_LOG" \
  "benchmark:$BM_LOG"
do
  label="${pair%%:*}"
  file="${pair#*:}"
  if [[ -n "$file" && -f "$file" ]]; then
    echo "--- $label ($file)"
    tail -n "$TAIL_LINES" "$file"
  else
    echo "--- $label (no log found)"
  fi
done

echo ""
latest_cycle="$(ls -1t "$REPO_ROOT"/artifacts/signal_learning/runs/*signal-learning-cycle.json 2>/dev/null | head -n1 || true)"
if [[ -n "$latest_cycle" ]]; then
  echo "=== Latest cycle summary ==="
  jq '{
    cycle_index,
    generated_at,
    summary,
    selection: {
      selected_with_paper_low_sample_count: .selection.selected_with_paper_low_sample_count,
      selection_turnover_rate: .selection.selection_turnover_rate,
      top_1: .selection.top_1
    }
  }' "$latest_cycle"
else
  echo "No cycle artifacts found."
fi
