#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/morning_signal_check.sh [options]

Options:
  --data-url URL         Data service health URL (default: http://127.0.0.1:18080/health)
  --account-url URL      Account service health URL (default: http://127.0.0.1:18081/health)
  --execution-url URL    Execution service health URL (default: http://127.0.0.1:18082/health)
  --strategy-url URL     Strategy service base URL (default: http://127.0.0.1:18083)
  --web-url URL          Local web URL (default: http://127.0.0.1:5174)
  --repo-root PATH       Repository root (default: current working directory)
  -h, --help             Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

DATA_HEALTH_URL="http://127.0.0.1:18080/health"
ACCOUNT_HEALTH_URL="http://127.0.0.1:18081/health"
EXECUTION_HEALTH_URL="http://127.0.0.1:18082/health"
STRATEGY_BASE_URL="http://127.0.0.1:18083"
WEB_URL="http://127.0.0.1:5174"
REPO_ROOT="$(pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-url)
      DATA_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --account-url)
      ACCOUNT_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --execution-url)
      EXECUTION_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --strategy-url)
      STRATEGY_BASE_URL="${2:-}"
      shift 2
      ;;
    --web-url)
      WEB_URL="${2:-}"
      shift 2
      ;;
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

require_cmd curl
require_cmd jq
require_cmd pgrep
require_cmd tail
require_cmd ls

cd "$REPO_ROOT"
[[ -d "artifacts" ]] || die "Run from repo root (missing artifacts/)"

BENCHMARK_LOG="artifacts/runtime/benchmark-24h.log"
COMPARE_LOG="artifacts/runtime/compare-snapshots-24h.log"
LEARNING_LOG="artifacts/runtime/signal-learning-24h.log"
RUNS_DIR="artifacts/signal_learning/runs"

echo "=== SIGNAL LAB MORNING CHECK ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

echo ""
echo "[1] Health"
echo "- ${DATA_HEALTH_URL} -> $(curl -fsS "${DATA_HEALTH_URL}" || echo DOWN)"
echo "- ${ACCOUNT_HEALTH_URL} -> $(curl -fsS "${ACCOUNT_HEALTH_URL}" || echo DOWN)"
echo "- ${EXECUTION_HEALTH_URL} -> $(curl -fsS "${EXECUTION_HEALTH_URL}" || echo DOWN)"
echo "- ${STRATEGY_BASE_URL}/health -> $(curl -fsS "${STRATEGY_BASE_URL%/}/health" || echo DOWN)"
echo "- ${WEB_URL} -> $(curl -fsS "${WEB_URL}" >/dev/null && echo ok || echo DOWN)"

echo ""
echo "[2] Core Processes"
pgrep -fl "target/debug/data-service|target/debug/strategy-service|target/debug/execution-service|vite --host 127.0.0.1 --port 5174|signal_learning_cycle.py|compare_signal_snapshots.sh|benchmark_signal_engines.sh" || true

echo ""
echo "[3] Latest Learning Cycle"
latest="$(ls -1t "${RUNS_DIR}"/*signal-learning-cycle.json 2>/dev/null | head -n1 || true)"
if [[ -z "${latest}" ]]; then
  echo "- No cycle artifacts found"
else
  echo "- file: ${latest}"
  jq -r '"  cycle=\(.cycle_index) generated_at=\(.generated_at) finished_at=\(.finished_at)"' "${latest}"
  jq -r '"  pairs=\(.summary.pairs_evaluated) promote=\(.summary.promote_recommendations) demote=\(.summary.demote_recommendations) hold=\(.summary.hold_recommendations) eligible=\(.summary.trade_eligible_timeframes) consensus=\(.summary.pairs_with_consensus) veto=\(.summary.pairs_with_veto) degraded=\(.summary.degraded_timeframes) mutated=\(.summary.mutated_pairs)"' "${latest}"
fi

echo ""
echo "[4] Benchmark Last Verdict"
if [[ -f "${BENCHMARK_LOG}" ]]; then
  grep -E "^\[|^Score:|^VERDICT:" "${BENCHMARK_LOG}" | tail -n 8 || true
else
  echo "- benchmark log missing: ${BENCHMARK_LOG}"
fi

echo ""
echo "[5] Compare Snapshot Last Cycle (tail)"
if [[ -f "${COMPARE_LOG}" ]]; then
  tail -n 40 "${COMPARE_LOG}" || true
else
  echo "- compare log missing: ${COMPARE_LOG}"
fi

echo ""
echo "[6] Learning Log Tail"
if [[ -f "${LEARNING_LOG}" ]]; then
  tail -n 20 "${LEARNING_LOG}" || true
else
  echo "- learning log missing: ${LEARNING_LOG}"
fi

echo ""
echo "[7] Newest Cycle Artifacts"
if [[ -d "${RUNS_DIR}" ]]; then
  ls -lt "${RUNS_DIR}" | head -n 10 || true
else
  echo "- runs dir missing: ${RUNS_DIR}"
fi
