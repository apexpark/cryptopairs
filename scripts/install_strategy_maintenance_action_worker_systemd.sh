#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_strategy_maintenance_action_worker_systemd.sh [options]

Options:
  --repo-root <path>            Repo root on host (default: /opt/cryptopairs)
  --python-bin <path>           Python binary (default: /usr/bin/python3)
  --queue-root <path>           Queue root path (default: artifacts/strategy_tuning/manual_action_queue)
  --interval-seconds <n>        Timer frequency in seconds (default: 60)
  --install                     Install/update and enable timer (default)
  --remove                      Disable and remove service/timer
  --show                        Show current service/timer status
  -h, --help                    Show this help
EOF
}

REPO_ROOT="/opt/cryptopairs"
PYTHON_BIN="/usr/bin/python3"
QUEUE_ROOT="artifacts/strategy_tuning/manual_action_queue"
INTERVAL_SECONDS=60
MODE="install"
SERVICE_NAME="cryptopairs-strategy-action-worker"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --queue-root)
      QUEUE_ROOT="${2:-}"
      shift 2
      ;;
    --interval-seconds)
      INTERVAL_SECONDS="${2:-}"
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

if [[ "${MODE}" == "show" ]]; then
  systemctl status "${SERVICE_NAME}.service" --no-pager || true
  systemctl status "${SERVICE_NAME}.timer" --no-pager || true
  exit 0
fi

if [[ "${MODE}" == "remove" ]]; then
  systemctl disable --now "${SERVICE_NAME}.timer" || true
  rm -f "${SERVICE_FILE}" "${TIMER_FILE}"
  systemctl daemon-reload
  echo "Removed ${SERVICE_NAME} systemd service/timer."
  exit 0
fi

cat >"${SERVICE_FILE}" <<EOF
[Unit]
Description=CryptoPairs Strategy Maintenance Action Worker
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${REPO_ROOT}
ExecStart=${PYTHON_BIN} ${REPO_ROOT}/tools/scripts/strategy_maintenance_action_worker.py --repo-root ${REPO_ROOT} --queue-root ${QUEUE_ROOT} --once
StandardOutput=append:${REPO_ROOT}/artifacts/strategy_tuning/maintenance_action_worker.log
StandardError=append:${REPO_ROOT}/artifacts/strategy_tuning/maintenance_action_worker.log
User=root
Group=root
EOF

cat >"${TIMER_FILE}" <<EOF
[Unit]
Description=Run CryptoPairs Strategy Maintenance Action Worker every ${INTERVAL_SECONDS}s

[Timer]
OnBootSec=30s
OnUnitActiveSec=${INTERVAL_SECONDS}s
AccuracySec=1s
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.timer"
echo "Installed and started ${SERVICE_NAME}.timer"
systemctl status "${SERVICE_NAME}.timer" --no-pager || true
