#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/start_weekend_signal_monitoring.sh [options]

Options:
  --repo-root PATH                  Repo root (default: current directory)
  --strategy-url URL                Experimental strategy base (default: http://127.0.0.1:18083)
  --prod-base URL                   Production strategy base (default: https://api.apexpark.io/strategy)
  --hours N                         Monitoring duration in hours (default: 96)
  --learning-sleep-seconds N        Signal-learning sleep between cycles (default: 900)
  --compare-sleep-seconds N         Compare snapshot interval (default: 900)
  --benchmark-sleep-seconds N       Benchmark interval (default: 7200)
  --benchmark-rounds N              Benchmark rounds per execution (default: 6)
  --timeout-seconds N               HTTP timeout for compare/benchmark scripts (default: 30)
  --compare-timeframe TF            Compare timeframe: 1m|15m|1h (default: 1m)
  --benchmark-timeframes CSV        Benchmark timeframes (default: 1m,15m,1h)
  --dry-run                         Print commands but do not start jobs
  --force                           Stop existing weekend monitor jobs before start
  -h, --help                        Show help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

is_running() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

REPO_ROOT="$(pwd)"
STRATEGY_URL="http://127.0.0.1:18083"
PROD_BASE="https://api.apexpark.io/strategy"
HOURS="96"
LEARNING_SLEEP_SECONDS="900"
COMPARE_SLEEP_SECONDS="900"
BENCHMARK_SLEEP_SECONDS="7200"
BENCHMARK_ROUNDS="6"
TIMEOUT_SECONDS="30"
COMPARE_TIMEFRAME="1m"
BENCHMARK_TIMEFRAMES="1m,15m,1h"
DRY_RUN="false"
FORCE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --strategy-url)
      STRATEGY_URL="${2:-}"
      shift 2
      ;;
    --prod-base)
      PROD_BASE="${2:-}"
      shift 2
      ;;
    --hours)
      HOURS="${2:-}"
      shift 2
      ;;
    --learning-sleep-seconds)
      LEARNING_SLEEP_SECONDS="${2:-}"
      shift 2
      ;;
    --compare-sleep-seconds)
      COMPARE_SLEEP_SECONDS="${2:-}"
      shift 2
      ;;
    --benchmark-sleep-seconds)
      BENCHMARK_SLEEP_SECONDS="${2:-}"
      shift 2
      ;;
    --benchmark-rounds)
      BENCHMARK_ROUNDS="${2:-}"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --compare-timeframe)
      COMPARE_TIMEFRAME="${2:-}"
      shift 2
      ;;
    --benchmark-timeframes)
      BENCHMARK_TIMEFRAMES="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift 1
      ;;
    --force)
      FORCE="true"
      shift 1
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

require_cmd bash
require_cmd date
require_cmd nohup
require_cmd curl
require_cmd jq
require_cmd awk

[[ "$HOURS" =~ ^[0-9]+$ ]] || die "--hours must be an integer"
[[ "$LEARNING_SLEEP_SECONDS" =~ ^[0-9]+$ ]] || die "--learning-sleep-seconds must be an integer"
[[ "$COMPARE_SLEEP_SECONDS" =~ ^[0-9]+$ ]] || die "--compare-sleep-seconds must be an integer"
[[ "$BENCHMARK_SLEEP_SECONDS" =~ ^[0-9]+$ ]] || die "--benchmark-sleep-seconds must be an integer"
[[ "$BENCHMARK_ROUNDS" =~ ^[0-9]+$ ]] || die "--benchmark-rounds must be an integer"
[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "--timeout-seconds must be an integer"
[[ "$HOURS" -gt 0 ]] || die "--hours must be > 0"
[[ "$LEARNING_SLEEP_SECONDS" -gt 0 ]] || die "--learning-sleep-seconds must be > 0"
[[ "$COMPARE_SLEEP_SECONDS" -gt 0 ]] || die "--compare-sleep-seconds must be > 0"
[[ "$BENCHMARK_SLEEP_SECONDS" -gt 0 ]] || die "--benchmark-sleep-seconds must be > 0"
[[ "$BENCHMARK_ROUNDS" -ge 2 ]] || die "--benchmark-rounds must be >= 2"
[[ "$TIMEOUT_SECONDS" -gt 0 ]] || die "--timeout-seconds must be > 0"

case "$COMPARE_TIMEFRAME" in
  1m|15m|1h) ;;
  *)
    die "--compare-timeframe must be one of: 1m, 15m, 1h"
    ;;
esac

cd "$REPO_ROOT"
[[ -d scripts ]] || die "Invalid repo root (missing scripts/): $REPO_ROOT"

RUNTIME_DIR="$REPO_ROOT/artifacts/runtime"
mkdir -p "$RUNTIME_DIR"

LEARNING_PID_FILE="$RUNTIME_DIR/signal-learning-weekend.pid"
COMPARE_PID_FILE="$RUNTIME_DIR/compare-snapshots-weekend.pid"
BENCH_PID_FILE="$RUNTIME_DIR/benchmark-weekend.pid"
META_FILE="$RUNTIME_DIR/weekend-monitoring-latest.json"
RUNNER_DIR="$RUNTIME_DIR/monitor-runners"
mkdir -p "$RUNNER_DIR"

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEADLINE_TS=$(( $(date +%s) + HOURS * 3600 ))
DEADLINE_UTC="$(date -u -r "$DEADLINE_TS" +%Y-%m-%dT%H:%M:%SZ)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

LEARNING_LOG="$RUNTIME_DIR/signal-learning-weekend-${STAMP}.log"
COMPARE_LOG="$RUNTIME_DIR/compare-snapshots-weekend-${STAMP}.log"
BENCH_LOG="$RUNTIME_DIR/benchmark-weekend-${STAMP}.log"

LEARNING_INTERVAL=$(( LEARNING_SLEEP_SECONDS + 30 ))
LEARNING_CYCLES=$(( (HOURS * 3600 + LEARNING_INTERVAL - 1) / LEARNING_INTERVAL ))
[[ "$LEARNING_CYCLES" -ge 1 ]] || LEARNING_CYCLES=1

stop_if_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && is_running "$pid"; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
}

stop_orphan_workers() {
  local pids
  pids="$(
    ps ax -o pid=,command= \
      | awk '
          ($0 ~ /scripts\/run_signal_learning_overnight\.sh/ ||
           $0 ~ /scripts\/compare_signal_snapshots\.sh/ ||
           $0 ~ /scripts\/benchmark_signal_engines\.sh/) {
            print $1
          }
        '
  )"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$pids"
  sleep 1
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if is_running "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done <<< "$pids"
}

ensure_not_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && is_running "$pid"; then
      die "Job already running (pid=$pid, pid_file=$pid_file). Use --force or stop script."
    fi
    rm -f "$pid_file"
  fi
}

if [[ "$FORCE" == "true" ]]; then
  stop_if_running "$LEARNING_PID_FILE"
  stop_if_running "$COMPARE_PID_FILE"
  stop_if_running "$BENCH_PID_FILE"
  stop_orphan_workers
else
  ensure_not_running "$LEARNING_PID_FILE"
  ensure_not_running "$COMPARE_PID_FILE"
  ensure_not_running "$BENCH_PID_FILE"
fi

LEARNING_CMD="cd '$REPO_ROOT' && bash '$REPO_ROOT/scripts/run_signal_learning_overnight.sh' \
  --strategy-url '$STRATEGY_URL' \
  --policy-json '$REPO_ROOT/infra/config/signal_learning_policy.json' \
  --cycles '$LEARNING_CYCLES' \
  --sleep-seconds '$LEARNING_SLEEP_SECONDS'"

COMPARE_CMD="cd '$REPO_ROOT' && while [[ \$(date +%s) -lt '$DEADLINE_TS' ]]; do \
  echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] compare cycle\"; \
  '$REPO_ROOT/scripts/compare_signal_snapshots.sh' --exp-base '$STRATEGY_URL' --prod-base '$PROD_BASE' --timeframe '$COMPARE_TIMEFRAME' --timeout '$TIMEOUT_SECONDS' || true; \
  sleep '$COMPARE_SLEEP_SECONDS'; \
done; \
echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] compare loop complete (deadline reached)\""

BENCH_CMD="cd '$REPO_ROOT' && while [[ \$(date +%s) -lt '$DEADLINE_TS' ]]; do \
  echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] benchmark cycle\"; \
  '$REPO_ROOT/scripts/benchmark_signal_engines.sh' --exp-base '$STRATEGY_URL' --main-base '$PROD_BASE' --timeframes '$BENCHMARK_TIMEFRAMES' --timeout '$TIMEOUT_SECONDS' --rounds '$BENCHMARK_ROUNDS' --sleep 5 || true; \
  sleep '$BENCHMARK_SLEEP_SECONDS'; \
done; \
echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] benchmark loop complete (deadline reached)\""

start_job() {
  local name="$1"
  local cmd="$2"
  local log_file="$3"
  local pid_file="$4"
  local runner_file="$RUNNER_DIR/${name}-${STAMP}.sh"
  cat > "$runner_file" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo \$\$ > '$pid_file'
$cmd
EOF
  chmod +x "$runner_file"
  if [[ "$DRY_RUN" == "true" ]]; then
    printf '[dry-run] %s\nrunner=%s\n%s\nlog=%s\npid_file=%s\n\n' "$name" "$runner_file" "$cmd" "$log_file" "$pid_file"
    return 0
  fi
  nohup bash "$runner_file" >> "$log_file" 2>&1 < /dev/null &
  local launch_pid=$!
  sleep 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    pid="$launch_pid"
    echo "$pid" > "$pid_file"
  fi
  if ! is_running "$pid"; then
    tail -n 40 "$log_file" || true
    die "Failed to start $name (pid=$pid, launch_pid=$launch_pid, log=$log_file, runner=$runner_file)"
  fi
  printf '[ok] %s started pid=%s launch_pid=%s log=%s runner=%s\n' "$name" "$pid" "$launch_pid" "$log_file" "$runner_file"
}

echo "Start UTC:    $START_UTC"
echo "Deadline UTC: $DEADLINE_UTC"
echo "Hours:        $HOURS"
echo "Learning cycles (derived): $LEARNING_CYCLES"
echo ""

start_job "signal-learning" "$LEARNING_CMD" "$LEARNING_LOG" "$LEARNING_PID_FILE"
start_job "compare-snapshots" "$COMPARE_CMD" "$COMPARE_LOG" "$COMPARE_PID_FILE"
start_job "benchmark" "$BENCH_CMD" "$BENCH_LOG" "$BENCH_PID_FILE"

if [[ "$DRY_RUN" == "false" ]]; then
  cat > "$META_FILE" <<EOF
{
  "version": 1,
  "created_at_utc": "$START_UTC",
  "start_utc": "$START_UTC",
  "deadline_utc": "$DEADLINE_UTC",
  "deadline_unix": $DEADLINE_TS,
  "hours": $HOURS,
  "strategy_url": "$STRATEGY_URL",
  "prod_base": "$PROD_BASE",
  "compare_timeframe": "$COMPARE_TIMEFRAME",
  "benchmark_timeframes": "$BENCHMARK_TIMEFRAMES",
  "benchmark_rounds": $BENCHMARK_ROUNDS,
  "timeout_seconds": $TIMEOUT_SECONDS,
  "learning_sleep_seconds": $LEARNING_SLEEP_SECONDS,
  "compare_sleep_seconds": $COMPARE_SLEEP_SECONDS,
  "benchmark_sleep_seconds": $BENCHMARK_SLEEP_SECONDS,
  "learning_cycles_derived": $LEARNING_CYCLES,
  "logs": {
    "signal_learning": "$LEARNING_LOG",
    "compare_snapshots": "$COMPARE_LOG",
    "benchmark": "$BENCH_LOG"
  },
  "pid_files": {
    "signal_learning": "$LEARNING_PID_FILE",
    "compare_snapshots": "$COMPARE_PID_FILE",
    "benchmark": "$BENCH_PID_FILE"
  },
  "runner_dir": "$RUNNER_DIR",
  "runner_files": {
    "signal_learning": "$RUNNER_DIR/signal-learning-${STAMP}.sh",
    "compare_snapshots": "$RUNNER_DIR/compare-snapshots-${STAMP}.sh",
    "benchmark": "$RUNNER_DIR/benchmark-${STAMP}.sh"
  }
}
EOF
  cat <<EOF

Weekend monitoring is active.
Use status:
  bash scripts/status_weekend_signal_monitoring.sh --repo-root '$REPO_ROOT'

One-command review:
  bash scripts/report_signal_monitoring_pass_fail.sh --repo-root '$REPO_ROOT'

Stop early if needed:
  bash scripts/stop_weekend_signal_monitoring.sh --repo-root '$REPO_ROOT'
EOF
fi
