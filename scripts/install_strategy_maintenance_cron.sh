#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_strategy_maintenance_cron.sh [options]

Options:
  --schedule "<cron expr>"      Cron schedule (default: 15 6 * * *)
  --timezone <IANA tz>          Cron timezone via CRON_TZ (default: system cron timezone)
  --repo-root <path>            Repo root on host (default: /opt/cryptopairs)
  --python-bin <path>           Python binary (default: /usr/bin/python3)
  --env-file <path>             Hosted env file (default: /opt/cryptopairs/.env.hosted)
  --timeout-seconds <seconds>   Per-step timeout (default: 420)
  --deploy-health-retries <n>   Deploy health retries (default: 90)
  --deploy-health-sleep-secs <n>
                               Seconds between deploy health retries (default: 2)
  --install                     Install or update cron entry (default)
  --remove                      Remove cron entry
  --show                        Show current cron entry
  -h, --help                    Show this help
EOF
}

MARKER="# cryptopairs-strategy-maintenance"
SCHEDULE="15 6 * * *"
TIMEZONE=""
REPO_ROOT="/opt/cryptopairs"
PYTHON_BIN="/usr/bin/python3"
ENV_FILE="/opt/cryptopairs/.env.hosted"
TIMEOUT_SECONDS="420"
DEPLOY_HEALTH_RETRIES="90"
DEPLOY_HEALTH_SLEEP_SECS="2"
MODE="install"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --schedule)
      SCHEDULE="${2:-}"
      shift 2
      ;;
    --timezone)
      TIMEZONE="${2:-}"
      shift 2
      ;;
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --deploy-health-retries)
      DEPLOY_HEALTH_RETRIES="${2:-}"
      shift 2
      ;;
    --deploy-health-sleep-secs)
      DEPLOY_HEALTH_SLEEP_SECS="${2:-}"
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

entry_command="cd ${REPO_ROOT} && ${PYTHON_BIN} tools/scripts/strategy_maintenance_cycle.py --env-file ${ENV_FILE} --output-root artifacts/strategy_tuning/runs --latest-report artifacts/strategy_tuning/latest_maintenance_report.json --timeout-seconds ${TIMEOUT_SECONDS} --deploy-health-retries ${DEPLOY_HEALTH_RETRIES} --deploy-health-sleep-secs ${DEPLOY_HEALTH_SLEEP_SECS} >> artifacts/strategy_tuning/maintenance_cron.log 2>&1"
entry_line="${SCHEDULE} ${entry_command} ${MARKER}"
timezone_line=""
if [[ -n "${TIMEZONE}" ]]; then
  timezone_line="CRON_TZ=${TIMEZONE} ${MARKER}"
fi

current_cron="$(crontab -l 2>/dev/null || true)"
filtered_cron="$(printf '%s\n' "${current_cron}" | grep -v "${MARKER}" || true)"

case "${MODE}" in
  show)
    if printf '%s\n' "${current_cron}" | grep -q "${MARKER}"; then
      printf '%s\n' "${current_cron}" | grep "${MARKER}"
    else
      echo "No strategy maintenance cron entry installed."
    fi
    ;;
  remove)
    printf '%s\n' "${filtered_cron}" | crontab -
    echo "Removed strategy maintenance cron entry (if present)."
    ;;
  install)
    {
      printf '%s\n' "${filtered_cron}"
      if [[ -n "${timezone_line}" ]]; then
        printf '%s\n' "${timezone_line}"
      fi
      printf '%s\n' "${entry_line}"
    } | sed '/^[[:space:]]*$/d' | crontab -
    echo "Installed strategy maintenance cron entry:"
    if [[ -n "${timezone_line}" ]]; then
      echo "${timezone_line}"
    fi
    echo "${entry_line}"
    ;;
  *)
    echo "Unexpected mode: ${MODE}" >&2
    exit 1
    ;;
esac
