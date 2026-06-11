#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_signal_learning_cadence_systemd.sh [options]

Options:
  --repo-root <path>            Repo root on host (default: /opt/cryptopairs)
  --strategy-url <url>          Strategy service URL (default: http://127.0.0.1:8083)
  --timeframes <csv>            Timeframes to sample (default: 1m,15m,1h)
  --interval-seconds <n>        Timer frequency in seconds (default: 900)
  --policy-json <path>          Policy path relative to repo root
                                (default: infra/config/signal_learning_policy.json)
  --state-json <path>           State path relative to repo root
                                under artifacts/signal_learning/
                                (default: artifacts/signal_learning/state.json)
  --logic-json <path>           Logic path relative to repo root
                                under artifacts/signal_learning/
                                (default: artifacts/signal_learning/signal_logic.json)
  --output-root <path>          Output root relative to repo root
                                under artifacts/signal_learning/
                                (default: artifacts/signal_learning/runs)
  --log-path <path>             Log path relative to repo root
                                under artifacts/signal_learning/
                                (default: artifacts/signal_learning/cadence.log)
  --install                     Install/update and enable timer (default)
  --remove                      Disable and remove service/timer
  --show                        Show current service/timer status
  -h, --help                    Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_relative_path() {
  local label="$1"
  local value="$2"
  local component
  local -a components
  [[ -n "${value}" ]] || die "${label} is required"
  [[ "${value}" != /* ]] || die "${label} must be relative to repo root: ${value}"
  [[ "${value}" != */ ]] || die "${label} must not end with slash: ${value}"
  [[ "${value}" =~ ^[-A-Za-z0-9._/]+$ ]] \
    || die "${label} may only contain letters, numbers, slash, dot, underscore, or dash: ${value}"
  IFS='/' read -r -a components <<<"${value}"
  for component in "${components[@]}"; do
    [[ -n "${component}" ]] || die "${label} must not contain empty path components: ${value}"
    [[ "${component}" != "." && "${component}" != ".." ]] \
      || die "${label} must not contain . or .. path components: ${value}"
  done
}

require_signal_learning_artifact_path() {
  local label="$1"
  local value="$2"
  [[ "${value}" == artifacts/signal_learning/* ]] \
    || die "${label} must stay under artifacts/signal_learning/: ${value}"
}

REPO_ROOT="/opt/cryptopairs"
STRATEGY_URL="http://127.0.0.1:8083"
TIMEFRAMES="1m,15m,1h"
INTERVAL_SECONDS=900
POLICY_JSON="infra/config/signal_learning_policy.json"
STATE_JSON="artifacts/signal_learning/state.json"
LOGIC_JSON="artifacts/signal_learning/signal_logic.json"
OUTPUT_ROOT="artifacts/signal_learning/runs"
LOG_PATH="artifacts/signal_learning/cadence.log"
MODE="install"
SERVICE_NAME="cryptopairs-signal-learning-cadence"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"

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
    --timeframes)
      TIMEFRAMES="${2:-}"
      shift 2
      ;;
    --interval-seconds)
      INTERVAL_SECONDS="${2:-}"
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
    --log-path)
      LOG_PATH="${2:-}"
      shift 2
      ;;
    --install)
      MODE="install"
      shift
      ;;
    --remove)
      MODE="remove"
      shift
      ;;
    --show)
      MODE="show"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

[[ "${INTERVAL_SECONDS}" =~ ^[0-9]+$ ]] || die "--interval-seconds must be an integer"
[[ "${INTERVAL_SECONDS}" -ge 60 ]] || die "--interval-seconds must be at least 60"
require_relative_path "--policy-json" "${POLICY_JSON}"
require_relative_path "--state-json" "${STATE_JSON}"
require_relative_path "--logic-json" "${LOGIC_JSON}"
require_relative_path "--output-root" "${OUTPUT_ROOT}"
require_relative_path "--log-path" "${LOG_PATH}"
require_signal_learning_artifact_path "--state-json" "${STATE_JSON}"
require_signal_learning_artifact_path "--logic-json" "${LOGIC_JSON}"
require_signal_learning_artifact_path "--output-root" "${OUTPUT_ROOT}"
require_signal_learning_artifact_path "--log-path" "${LOG_PATH}"

if [[ "${MODE}" == "show" ]]; then
  systemctl status "${SERVICE_NAME}.service" --no-pager || true
  systemctl status "${SERVICE_NAME}.timer" --no-pager || true
  exit 0
fi

if [[ "${MODE}" == "remove" ]]; then
  systemctl disable --now "${SERVICE_NAME}.timer" || true
  systemctl stop "${SERVICE_NAME}.service" || true
  rm -f "${SERVICE_FILE}" "${TIMER_FILE}"
  systemctl daemon-reload
  systemctl reset-failed "${SERVICE_NAME}.service" "${SERVICE_NAME}.timer" || true
  echo "Removed ${SERVICE_NAME} systemd service/timer."
  exit 0
fi

[[ -d "${REPO_ROOT}" ]] || die "Repo root not found: ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/scripts/run_signal_learning_overnight.sh" ]] \
  || die "Signal learning runner not found under ${REPO_ROOT}"

mkdir -p "${REPO_ROOT}/$(dirname "${LOG_PATH}")" "${REPO_ROOT}/${OUTPUT_ROOT}"

cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=CryptoPairs read-only signal-learning overlay refresh
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${REPO_ROOT}
ExecStart=/usr/bin/bash ${REPO_ROOT}/scripts/run_signal_learning_overnight.sh --strategy-url ${STRATEGY_URL} --cycles 1 --sleep-seconds 0 --timeframes ${TIMEFRAMES} --policy-json ${POLICY_JSON} --state-json ${STATE_JSON} --logic-json ${LOGIC_JSON} --output-root ${OUTPUT_ROOT}
StandardOutput=append:${REPO_ROOT}/${LOG_PATH}
StandardError=append:${REPO_ROOT}/${LOG_PATH}
User=root
Group=root
EOF

cat >"${TIMER_FILE}" <<EOF
[Unit]
Description=Refresh CryptoPairs signal-learning overlay every ${INTERVAL_SECONDS}s

[Timer]
OnBootSec=2min
OnUnitActiveSec=${INTERVAL_SECONDS}s
AccuracySec=30s
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.timer"
echo "Installed and started ${SERVICE_NAME}.timer"
systemctl status "${SERVICE_NAME}.timer" --no-pager || true
