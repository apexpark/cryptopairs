#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/stop-signal-lab.sh [options]

Options:
  -e, --env-file <path>   Env file to use (default: .env.signal-lab)
      --volumes           Remove signal-lab volumes as well
  -h, --help              Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ENV_FILE=".env.signal-lab"
REMOVE_VOLUMES="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --volumes)
      REMOVE_VOLUMES="true"
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

if has_cmd docker && docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif has_cmd docker-compose; then
  COMPOSE=(docker-compose)
else
  die "Missing compose command"
fi

[[ -f "$ENV_FILE" ]] || die "Env file not found: $ENV_FILE"
[[ -f "docker-compose.signal-lab.yml" ]] || die "Run from repo root (missing docker-compose.signal-lab.yml)"

COMPOSE_ARGS=(-f docker-compose.signal-lab.yml --env-file "$ENV_FILE" down --remove-orphans)
if [[ "$REMOVE_VOLUMES" == "true" ]]; then
  COMPOSE_ARGS+=(--volumes)
fi

"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}"
