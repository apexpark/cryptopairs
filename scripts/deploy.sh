#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/deploy.sh [options]

Options:
  -e, --env-file <path>     Env file to source (default: /opt/cryptopairs/.env.hosted)
  -s, --services <csv>      Comma-separated app services to deploy
                            (default: data-service,strategy-service,execution-service,account-service)
      --skip-pull           Skip git pull --ff-only
      --skip-public-health  Skip HTTPS public health check
      --public-health-url   Public health URL (default: https://api.apexpark.io/health)
      --dry-run             Print commands without executing
  -h, --help                Show this help
EOF
}

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

assert_no_duplicate_keys() {
  local env_file="$1"
  local duplicates
  duplicates="$(
    grep -E '^(KRAKEN_SYMBOLS|STRATEGY_PAIRS)=' "$env_file" \
      | cut -d'=' -f1 \
      | sort \
      | uniq -d
  )"
  if [[ -n "$duplicates" ]]; then
    die "Duplicate env key(s) found in $env_file: $duplicates"
  fi
}

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    printf '+ %q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

ENV_FILE="/opt/cryptopairs/.env.hosted"
SERVICES_CSV="data-service,strategy-service,execution-service,account-service"
SKIP_PULL="false"
SKIP_PUBLIC_HEALTH="false"
PUBLIC_HEALTH_URL="https://api.apexpark.io/health"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    -s|--services)
      SERVICES_CSV="${2:-}"
      shift 2
      ;;
    --skip-pull)
      SKIP_PULL="true"
      shift
      ;;
    --skip-public-health)
      SKIP_PUBLIC_HEALTH="true"
      shift
      ;;
    --public-health-url)
      PUBLIC_HEALTH_URL="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
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

require_cmd git
require_cmd curl

COMPOSE_CMD=()
if has_cmd docker && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif has_cmd docker-compose; then
  COMPOSE_CMD=(docker-compose)
else
  die "Missing compose command: install Docker with 'docker compose' or 'docker-compose'"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  die "Env file not found: $ENV_FILE"
fi

if [[ ! -f "docker-compose.yml" ]]; then
  die "Run from repo root (missing docker-compose.yml)"
fi

assert_no_duplicate_keys "$ENV_FILE"
log "Validated env file keys in $ENV_FILE"

IFS=',' read -r -a SERVICES <<<"$SERVICES_CSV"
if [[ "${#SERVICES[@]}" -eq 0 ]]; then
  die "No services provided"
fi

log "Deploy target services: ${SERVICES[*]}"

if [[ "$SKIP_PULL" == "false" ]]; then
  log "Pulling latest git changes"
  run git pull --ff-only
fi

log "Loading env: $ENV_FILE"
if [[ "$DRY_RUN" == "false" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

log "Deploying services via docker compose"
run "${COMPOSE_CMD[@]}" --profile app up -d --build --no-deps "${SERVICES[@]}"

log "Container status"
if has_cmd docker; then
  run docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
else
  run "${COMPOSE_CMD[@]}" ps
fi

local_health_check() {
  local url="$1"
  local label="$2"
  if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN health check: $label -> $url"
    return 0
  fi
  if curl -fsS "$url" >/dev/null; then
    log "Health OK: $label"
  else
    die "Health FAILED: $label ($url)"
  fi
}

local_health_check "http://127.0.0.1:8080/health" "data-service"
local_health_check "http://127.0.0.1:8081/health" "account-service"
local_health_check "http://127.0.0.1:8082/health" "execution-service"
local_health_check "http://127.0.0.1:8083/health" "strategy-service"

if [[ "$SKIP_PUBLIC_HEALTH" == "false" ]]; then
  local_health_check "$PUBLIC_HEALTH_URL" "public-api"
fi

log "Deploy completed successfully"
