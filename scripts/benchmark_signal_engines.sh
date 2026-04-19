#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  benchmark_signal_engines.sh --main-base URL [options]

Options:
  --exp-base URL         Experimental strategy base URL (default: http://127.0.0.1:18083)
  --main-base URL        Main strategy base URL (required)
  --timeframes CSV       Comma list: 1m,15m,1h (default: 1m,15m,1h)
  --timeout SEC          Per-request timeout seconds (default: 30)
  --rounds N             Cue stability rounds (default: 6)
  --sleep SEC            Seconds between stability rounds (default: 5)
  --help                 Show this message

Metrics (lower is better):
  - cue_live_mean_abs
  - freshness_mean_age_s
  - cadence_mean_step_error_s
  - cue_stability_mean_abs
EOF
}

require_bin() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $name" >&2
    exit 1
  fi
}

expected_step_seconds() {
  case "$1" in
    1m) echo 60 ;;
    15m) echo 900 ;;
    1h) echo 3600 ;;
    *)
      echo "ERROR: unsupported timeframe: $1" >&2
      exit 1
      ;;
  esac
}

fetch_snapshot_tsv() {
  local base="$1"
  local tf="$2"
  local timeout_s="$3"
  local out_tsv="$4"
  local expected_step
  expected_step="$(expected_step_seconds "$tf")"

  local cues_json
  cues_json="$(curl -fsS --max-time "$timeout_s" "${base%/}/v1/strategy/pairs/cues?timeframe=${tf}&limit=50")"
  local pair_count
  pair_count="$(echo "$cues_json" | jq -er '.cues | length')"
  if [[ "$pair_count" -le 0 ]]; then
    echo "ERROR: no cues for base=$base timeframe=$tf" >&2
    exit 1
  fi

  : > "$out_tsv"
  while IFS= read -r pair_id; do
    [[ -z "$pair_id" ]] && continue
    local cue_z
    cue_z="$(echo "$cues_json" | jq -er --arg p "$pair_id" '.cues[] | select(.cue.pair_id==$p) | .cue.spread_z')"
    local live_json
    live_json="$(curl -fsS --max-time "$timeout_s" "${base%/}/v1/strategy/pairs/live-z?pair_id=${pair_id}&timeframe=${tf}")"
    local live_z age_s step_s cue_live_abs step_error_abs
    live_z="$(echo "$live_json" | jq -er '.points[-1].z')"
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
    step_s="$(
      echo "$live_json" | jq -er '
        if (.points | length) < 2 then
          -1
        else
          (
            .points[-1].ts
            | sub("\\.[0-9]+Z$";"Z")
            | fromdateiso8601
          ) - (
            .points[-2].ts
            | sub("\\.[0-9]+Z$";"Z")
            | fromdateiso8601
          )
        end
      '
    )"
    cue_live_abs="$(awk -v a="$cue_z" -v b="$live_z" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.8f", d}')"
    step_error_abs="$(awk -v s="$step_s" -v e="$expected_step" 'BEGIN{d=s-e; if(d<0)d=-d; printf "%.8f", d}')"
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
      "$pair_id" "$cue_z" "$live_z" "$cue_live_abs" "$age_s" "$step_s" "$step_error_abs" >> "$out_tsv"
  done < <(echo "$cues_json" | jq -er '.cues[].cue.pair_id')

  sort -o "$out_tsv" "$out_tsv"
}

summarize_snapshot_tsv() {
  local in_tsv="$1"
  awk -F '\t' '
    {
      n+=1
      coh=$4+0.0
      age=$5+0.0
      serr=$7+0.0
      coh_sum+=coh
      age_sum+=age
      serr_sum+=serr
      if (coh > coh_max) coh_max=coh
      if (age > age_max) age_max=age
      if (serr > serr_max) serr_max=serr
    }
    END {
      if (n == 0) {
        printf "0\t0\t0\t0\t0\t0\t0\n"
      } else {
        printf "%d\t%.8f\t%.8f\t%.8f\t%.8f\t%.8f\t%.8f\n", \
          n, coh_sum/n, coh_max, age_sum/n, age_max, serr_sum/n, serr_max
      }
    }
  ' "$in_tsv"
}

filter_snapshot_to_pairs() {
  local in_tsv="$1"
  local pairs_file="$2"
  local out_tsv="$3"
  awk -F '\t' 'NR==FNR{keep[$1]=1; next} ($1 in keep){print}' "$pairs_file" "$in_tsv" > "$out_tsv"
  sort -o "$out_tsv" "$out_tsv"
}

measure_cue_stability() {
  local base="$1"
  local tf="$2"
  local timeout_s="$3"
  local rounds="$4"
  local sleep_s="$5"
  local pair_filter_file="${6:-}"
  local tmp_dir prev_file i
  tmp_dir="$(mktemp -d)"
  prev_file=""
  i=1
  : > "$tmp_dir/drift.tsv"

  while [[ "$i" -le "$rounds" ]]; do
    local snap_raw="$tmp_dir/snap_raw_${i}.tsv"
    local snap="$tmp_dir/snap_${i}.tsv"
    curl -fsS --max-time "$timeout_s" "${base%/}/v1/strategy/pairs/cues?timeframe=${tf}&limit=50" \
      | jq -er '.cues[] | [.cue.pair_id, .cue.spread_z] | @tsv' \
      | sort > "$snap_raw"
    if [[ -n "$pair_filter_file" && -s "$pair_filter_file" ]]; then
      awk -F '\t' 'NR==FNR{keep[$1]=1; next} ($1 in keep){print}' "$pair_filter_file" "$snap_raw" > "$snap"
      sort -o "$snap" "$snap"
    else
      mv "$snap_raw" "$snap"
    fi
    if [[ -n "$prev_file" ]]; then
      join -t $'\t' "$prev_file" "$snap" \
        | awk -F '\t' '{d=$2-$3; if(d<0)d=-d; printf "%s\t%.8f\n", $1, d}' >> "$tmp_dir/drift.tsv"
    fi
    prev_file="$snap"
    i=$((i+1))
    if [[ "$i" -le "$rounds" ]]; then
      sleep "$sleep_s"
    fi
  done

  awk -F '\t' '
    {
      n+=1
      d=$2+0.0
      sum+=d
      if (d > max) max=d
    }
    END {
      if (n == 0) {
        printf "0\t0\t0\n"
      } else {
        printf "%d\t%.8f\t%.8f\n", n, sum/n, max
      }
    }
  ' "$tmp_dir/drift.tsv"

  rm -rf "$tmp_dir"
}

compare_lt() {
  local a="$1"
  local b="$2"
  local eps="${3:-0.000001}"
  awk -v x="$a" -v y="$b" -v e="$eps" 'BEGIN{if (x + e < y) print "A"; else if (y + e < x) print "B"; else print "T"}'
}

exp_base="http://127.0.0.1:18083"
main_base=""
timeframes_csv="1m,15m,1h"
timeout_s=30
rounds=6
sleep_s=5

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exp-base)
      exp_base="${2:-}"
      shift 2
      ;;
    --main-base)
      main_base="${2:-}"
      shift 2
      ;;
    --timeframes)
      timeframes_csv="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout_s="${2:-}"
      shift 2
      ;;
    --rounds)
      rounds="${2:-}"
      shift 2
      ;;
    --sleep)
      sleep_s="${2:-}"
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

if [[ -z "$main_base" ]]; then
  echo "ERROR: --main-base is required" >&2
  usage >&2
  exit 1
fi

if ! [[ "$timeout_s" =~ ^[0-9]+$ ]] || [[ "$timeout_s" -le 0 ]]; then
  echo "ERROR: timeout must be a positive integer" >&2
  exit 1
fi
if ! [[ "$rounds" =~ ^[0-9]+$ ]] || [[ "$rounds" -lt 2 ]]; then
  echo "ERROR: rounds must be integer >= 2" >&2
  exit 1
fi
if ! [[ "$sleep_s" =~ ^[0-9]+$ ]] || [[ "$sleep_s" -lt 1 ]]; then
  echo "ERROR: sleep must be integer >= 1" >&2
  exit 1
fi

require_bin curl
require_bin jq
require_bin awk
require_bin join
require_bin sort

IFS=',' read -r -a timeframes <<< "$timeframes_csv"
for tf in "${timeframes[@]}"; do
  case "$tf" in
    1m|15m|1h) ;;
    *)
      echo "ERROR: invalid timeframe in --timeframes: $tf" >&2
      exit 1
      ;;
  esac
done

echo "Benchmark: EXP=$exp_base MAIN=$main_base timeframes=$timeframes_csv timeout=${timeout_s}s rounds=$rounds sleep=${sleep_s}s"

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

exp_wins=0
main_wins=0
ties=0

printf "\n%-6s  %-8s %-8s  %-8s %-8s  %-8s %-8s  %-8s %-8s\n" \
  "TF" \
  "cohE" "cohM" \
  "ageE" "ageM" \
  "stepE" "stepM" \
  "stabE" "stabM"
printf "%-6s  %-8s %-8s  %-8s %-8s  %-8s %-8s  %-8s %-8s\n" \
  "------" \
  "--------" "--------" \
  "--------" "--------" \
  "--------" "--------" \
  "--------" "--------"

for tf in "${timeframes[@]}"; do
  exp_tsv="$tmp_root/exp_${tf}.tsv"
  main_tsv="$tmp_root/main_${tf}.tsv"
  fetch_snapshot_tsv "$exp_base" "$tf" "$timeout_s" "$exp_tsv"
  fetch_snapshot_tsv "$main_base" "$tf" "$timeout_s" "$main_tsv"

  raw_exp_n="$(wc -l < "$exp_tsv" | tr -d ' ')"
  raw_main_n="$(wc -l < "$main_tsv" | tr -d ' ')"
  exp_eval_tsv="$exp_tsv"
  main_eval_tsv="$main_tsv"
  pair_filter_file=""

  if [[ "$raw_exp_n" -ne "$raw_main_n" ]]; then
    pair_filter_file="$tmp_root/common_pairs_${tf}.txt"
    comm -12 <(cut -f1 "$exp_tsv") <(cut -f1 "$main_tsv") > "$pair_filter_file"
    common_n="$(wc -l < "$pair_filter_file" | tr -d ' ')"
    if [[ "$common_n" -le 0 ]]; then
      echo "ERROR: pair count mismatch for timeframe=$tf and no common pair intersection (exp=$raw_exp_n main=$raw_main_n)" >&2
      exit 1
    fi
    echo "WARN: pair count mismatch for timeframe=$tf exp=$raw_exp_n main=$raw_main_n; benchmarking on common_pairs=$common_n" >&2
    exp_eval_tsv="$tmp_root/exp_${tf}_aligned.tsv"
    main_eval_tsv="$tmp_root/main_${tf}_aligned.tsv"
    filter_snapshot_to_pairs "$exp_tsv" "$pair_filter_file" "$exp_eval_tsv"
    filter_snapshot_to_pairs "$main_tsv" "$pair_filter_file" "$main_eval_tsv"
  fi

  IFS=$'\t' read -r exp_n exp_coh_mean _ exp_age_mean _ exp_steperr_mean _ < <(summarize_snapshot_tsv "$exp_eval_tsv")
  IFS=$'\t' read -r main_n main_coh_mean _ main_age_mean _ main_steperr_mean _ < <(summarize_snapshot_tsv "$main_eval_tsv")
  if [[ "$exp_n" -ne "$main_n" ]]; then
    echo "ERROR: aligned pair count mismatch for timeframe=$tf exp=$exp_n main=$main_n" >&2
    exit 1
  fi

  IFS=$'\t' read -r _ exp_stab_mean _ < <(measure_cue_stability "$exp_base" "$tf" "$timeout_s" "$rounds" "$sleep_s" "$pair_filter_file")
  IFS=$'\t' read -r _ main_stab_mean _ < <(measure_cue_stability "$main_base" "$tf" "$timeout_s" "$rounds" "$sleep_s" "$pair_filter_file")

  printf "%-6s  %-8.4f %-8.4f  %-8.3f %-8.3f  %-8.2f %-8.2f  %-8.4f %-8.4f\n" \
    "$tf" \
    "$exp_coh_mean" "$main_coh_mean" \
    "$exp_age_mean" "$main_age_mean" \
    "$exp_steperr_mean" "$main_steperr_mean" \
    "$exp_stab_mean" "$main_stab_mean"

  for metric_pair in \
    "$exp_coh_mean:$main_coh_mean" \
    "$exp_age_mean:$main_age_mean" \
    "$exp_steperr_mean:$main_steperr_mean" \
    "$exp_stab_mean:$main_stab_mean"; do
    IFS=':' read -r a b <<< "$metric_pair"
    result="$(compare_lt "$a" "$b")"
    case "$result" in
      A) exp_wins=$((exp_wins + 1)) ;;
      B) main_wins=$((main_wins + 1)) ;;
      T) ties=$((ties + 1)) ;;
    esac
  done
done

total=$((exp_wins + main_wins + ties))
printf "\nScore: EXP wins=%d MAIN wins=%d ties=%d total=%d\n" "$exp_wins" "$main_wins" "$ties" "$total"
if [[ "$exp_wins" -gt "$main_wins" ]]; then
  echo "VERDICT: EXPERIMENTAL currently outperforms MAIN on benchmark metrics."
  exit 0
fi
if [[ "$exp_wins" -lt "$main_wins" ]]; then
  echo "VERDICT: MAIN currently outperforms EXPERIMENTAL on benchmark metrics."
  exit 2
fi
echo "VERDICT: TIE (no clear outperformance)."
exit 3
