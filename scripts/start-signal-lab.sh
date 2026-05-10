#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/start-signal-lab.sh [options]

Options:
  -e, --env-file <path>   Env file to use (default: .env.signal-lab)
      --skip-health       Skip local health checks
      --no-build          Do not pass --build to docker compose
  -h, --help              Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

health_check() {
  local url="$1"
  local label="$2"
  local attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -fsS "$url" >/dev/null; then
      printf 'Health OK: %s (%s)\n' "$label" "$url"
      return 0
    fi
    sleep 2
  done
  die "Health FAILED: $label ($url)"
}

ENV_FILE=".env.signal-lab"
SKIP_HEALTH="false"
NO_BUILD="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --skip-health)
      SKIP_HEALTH="true"
      shift
      ;;
    --no-build)
      NO_BUILD="true"
      shift
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
if has_cmd docker && docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif has_cmd docker-compose; then
  COMPOSE=(docker-compose)
else
  die "Missing compose command"
fi

[[ -f "$ENV_FILE" ]] || die "Env file not found: $ENV_FILE"
[[ -f "docker-compose.signal-lab.yml" ]] || die "Run from repo root (missing docker-compose.signal-lab.yml)"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

COMPOSE_ARGS=(-f docker-compose.signal-lab.yml --env-file "$ENV_FILE" --profile app up -d)
if [[ "$NO_BUILD" == "false" ]]; then
  COMPOSE_ARGS+=(--build)
fi

# Start infra dependencies first.
"${COMPOSE[@]}" -f docker-compose.signal-lab.yml --env-file "$ENV_FILE" up -d timescaledb redis

# Start application services sequentially to avoid concurrent heavy cargo compiles.
for svc in data-service account-service execution-service strategy-service; do
  if [[ "$NO_BUILD" == "false" ]]; then
    "${COMPOSE[@]}" -f docker-compose.signal-lab.yml --env-file "$ENV_FILE" --profile app up -d --build "$svc"
  else
    "${COMPOSE[@]}" -f docker-compose.signal-lab.yml --env-file "$ENV_FILE" --profile app up -d "$svc"
  fi
done

if [[ "$SKIP_HEALTH" == "false" ]]; then
  health_check "http://127.0.0.1:${SIGNAL_LAB_DATA_PORT:-18080}/health" "signal-lab data-service"
  health_check "http://127.0.0.1:${SIGNAL_LAB_ACCOUNT_PORT:-18081}/health" "signal-lab account-service"
  health_check "http://127.0.0.1:${SIGNAL_LAB_EXECUTION_PORT:-18082}/health" "signal-lab execution-service"
  health_check "http://127.0.0.1:${SIGNAL_LAB_STRATEGY_PORT:-18083}/health" "signal-lab strategy-service"
fi

cat <<EOF
Signal lab started.
Local API ports:
  data-service:      http://127.0.0.1:${SIGNAL_LAB_DATA_PORT:-18080}
  account-service:   http://127.0.0.1:${SIGNAL_LAB_ACCOUNT_PORT:-18081}
  execution-service: http://127.0.0.1:${SIGNAL_LAB_EXECUTION_PORT:-18082}
  strategy-service:  http://127.0.0.1:${SIGNAL_LAB_STRATEGY_PORT:-18083}
EOF
