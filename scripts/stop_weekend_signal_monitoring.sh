#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/stop_weekend_signal_monitoring.sh [--repo-root PATH]
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
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

cd "$REPO_ROOT"
RUNTIME_DIR="$REPO_ROOT/artifacts/runtime"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[skip] $label pid file not found: $pid_file"
    return
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    echo "[skip] $label pid file empty: $pid_file"
    rm -f "$pid_file"
    return
  fi
  if is_running "$pid"; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    if is_running "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "[ok] stopped $label pid=$pid"
  else
    echo "[skip] $label not running (stale pid=$pid)"
  fi
  rm -f "$pid_file"
}

stop_pid_file "signal-learning" "$RUNTIME_DIR/signal-learning-weekend.pid"
stop_pid_file "compare-snapshots" "$RUNTIME_DIR/compare-snapshots-weekend.pid"
stop_pid_file "benchmark" "$RUNTIME_DIR/benchmark-weekend.pid"

orphan_pids="$(
  ps ax -o pid=,command= \
    | awk '
        ($0 ~ /scripts\/run_signal_learning_overnight\.sh/ ||
         $0 ~ /scripts\/compare_signal_snapshots\.sh/ ||
         $0 ~ /scripts\/benchmark_signal_engines\.sh/) {
          print $1
        }
      '
)"
if [[ -n "$orphan_pids" ]]; then
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$orphan_pids"
  sleep 1
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if is_running "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done <<< "$orphan_pids"
  echo "[ok] cleaned orphan monitor workers:"
  echo "$orphan_pids" | sed 's/^/  - pid /'
fi
