#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  compare_signal_snapshots.sh [--exp-base URL] [--prod-base URL] [--timeframe TF] [--timeout SEC]

Examples:
  compare_signal_snapshots.sh
  compare_signal_snapshots.sh --exp-base http://127.0.0.1:18083 --prod-base http://127.0.0.1:8083
  compare_signal_snapshots.sh --timeframe 15m --timeout 15

Notes:
  - If --prod-base is omitted, only experimental snapshot output is printed.
  - Timeframe must be one of: 1m, 15m, 1h.
EOF
}

require_bin() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $name" >&2
    exit 1
  fi
}

normalize_ts_for_parse() {
  # jq 1.6 fromdateiso8601 can reject fractional seconds; strip them.
  jq -r 'sub("\\.[0-9]+Z$";"Z")'
}

fetch_snapshot() {
  local label="$1"
  local base="$2"
  local timeframe="$3"
  local timeout_sec="$4"
  local output_tsv="$5"

  local cues_url="${base%/}/v1/strategy/pairs/cues?timeframe=${timeframe}"
  local cues_json
  if ! cues_json="$(curl -fsS --max-time "$timeout_sec" "$cues_url")"; then
    echo "ERROR: failed to fetch cues for ${label} from ${cues_url}" >&2
    return 1
  fi

  local pair_count
  pair_count="$(echo "$cues_json" | jq -er '.cues | length')" || {
    echo "ERROR: invalid cues payload for ${label}" >&2
    return 1
  }
  if [[ "$pair_count" -le 0 ]]; then
    echo "ERROR: no cues returned for ${label}" >&2
    return 1
  fi

  echo "[$label] base=$base timeframe=$timeframe pairs=$pair_count"

  : > "$output_tsv"
  while IFS= read -r pair_id; do
    [[ -z "$pair_id" ]] && continue

    local cue_z
    cue_z="$(echo "$cues_json" | jq -er --arg p "$pair_id" '.cues[] | select(.cue.pair_id==$p) | .cue.spread_z')"

    local live_url="${base%/}/v1/strategy/pairs/live-z?pair_id=${pair_id}&timeframe=${timeframe}"
    local live_json
    if ! live_json="$(curl -fsS --max-time "$timeout_sec" "$live_url")"; then
      echo "ERROR: failed to fetch live-z for ${label} pair=${pair_id}" >&2
      return 1
    fi

    local live_z generated_at point_ts age_s
    live_z="$(echo "$live_json" | jq -er '.points[-1].z')"
    generated_at="$(echo "$live_json" | jq -er '.generated_at')"
    point_ts="$(echo "$live_json" | jq -er '.points[-1].ts')"
    age_s="$(
      echo "$live_json" | jq -er '
        (
          .generated_at
          | sub("\\.[0-9]+Z$";"Z")
          | fromdateiso8601
        ) - (
          .points[-1].ts
          | sub("\\.[0-9]+Z$";"Z")
          | fromdateiso8601
        ) | floor
      '
    )"

    printf "%s\t%s\t%s\t%s\t%s\n" "$pair_id" "$cue_z" "$live_z" "$age_s" "$generated_at" >> "$output_tsv"
  done < <(echo "$cues_json" | jq -er '.cues[].cue.pair_id')

  sort -o "$output_tsv" "$output_tsv"
}

print_single_env_table() {
  local label="$1"
  local input_tsv="$2"
  printf "\n%s\n" "=== ${label} Snapshot ==="
  printf "%-24s %10s %10s %10s %9s\n" "PAIR" "CUE_Z" "LIVE_Z" "|DELTA|" "AGE_S"
  printf "%-24s %10s %10s %10s %9s\n" "------------------------" "----------" "----------" "----------" "---------"
  awk -F '\t' '
    {
      cue=$2+0.0
      live=$3+0.0
      d=cue-live
      if (d < 0) d = -d
      printf "%-24s %10.4f %10.4f %10.4f %9s\n", $1, cue, live, d, $4
    }
  ' "$input_tsv"
}

print_joined_table() {
  local exp_tsv="$1"
  local prod_tsv="$2"
  local mismatches
  mismatches="$(comm -3 <(cut -f1 "$exp_tsv") <(cut -f1 "$prod_tsv") || true)"
  if [[ -n "$mismatches" ]]; then
    printf "\nWARNING: pair-set mismatch between environments:\n%s\n" "$mismatches"
  fi

  printf "\n%s\n" "=== Cross-Env Delta (EXP vs PROD) ==="
  printf "%-24s %10s %10s %10s %10s %10s %10s %7s/%s\n" \
    "PAIR" "CUE_EXP" "CUE_PROD" "|CUE_D|" "LIVE_EXP" "LIVE_PROD" "|LIVE_D|" "AGE_E" "AGE_P"
  printf "%-24s %10s %10s %10s %10s %10s %10s %7s/%s\n" \
    "------------------------" "----------" "----------" "----------" "----------" "----------" "----------" "-----" "-----"

  join -t $'\t' "$exp_tsv" "$prod_tsv" | awk -F '\t' '
    {
      cue_e=$2+0.0; live_e=$3+0.0; age_e=$4
      cue_p=$6+0.0; live_p=$7+0.0; age_p=$8
      dc=cue_e-cue_p; if (dc < 0) dc=-dc
      dl=live_e-live_p; if (dl < 0) dl=-dl
      printf "%-24s %10.4f %10.4f %10.4f %10.4f %10.4f %10.4f %7s/%-5s\n", \
        $1, cue_e, cue_p, dc, live_e, live_p, dl, age_e, age_p
    }
  '
}

exp_base="http://127.0.0.1:18083"
prod_base=""
timeframe="1m"
timeout_sec="10"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exp-base)
      exp_base="${2:-}"
      shift 2
      ;;
    --prod-base)
      prod_base="${2:-}"
      shift 2
      ;;
    --timeframe)
      timeframe="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout_sec="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$timeframe" != "1m" && "$timeframe" != "15m" && "$timeframe" != "1h" ]]; then
  echo "ERROR: invalid timeframe '$timeframe' (expected 1m/15m/1h)" >&2
  exit 1
fi

if ! [[ "$timeout_sec" =~ ^[0-9]+$ ]] || [[ "$timeout_sec" -le 0 ]]; then
  echo "ERROR: timeout must be a positive integer" >&2
  exit 1
fi

require_bin curl
require_bin jq
require_bin awk
require_bin join
require_bin sort
require_bin comm

tmp_exp="$(mktemp)"
tmp_prod="$(mktemp)"
trap 'rm -f "$tmp_exp" "$tmp_prod"' EXIT

fetch_snapshot "EXP" "$exp_base" "$timeframe" "$timeout_sec" "$tmp_exp"
print_single_env_table "EXP" "$tmp_exp"

if [[ -n "$prod_base" ]]; then
  fetch_snapshot "PROD" "$prod_base" "$timeframe" "$timeout_sec" "$tmp_prod"
  print_single_env_table "PROD" "$tmp_prod"
  print_joined_table "$tmp_exp" "$tmp_prod"
fi
