#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/report_signal_monitoring_pass_fail.sh [options]

Options:
  --repo-root PATH                 Repo root (default: current directory)
  --meta-file PATH                 Monitoring metadata file
                                   (default: artifacts/runtime/weekend-monitoring-latest.json)
  --baseline-start-utc TS          Baseline start (ISO8601 UTC, default: 2026-03-23T22:02:05Z)
  --baseline-end-utc TS            Baseline end   (ISO8601 UTC, default: 2026-03-24T22:06:00Z)
  --no-baseline                    Skip baseline/pre-C3 comparison block
  --selector-topk-overlap-min X    Acceptance min for adjacent top-k overlap mean (default: 0.60)
  --selector-dwell-mean-min X      Acceptance min for top-k member dwell mean (default: 2.0)
  --turnover-local-max X           Deprecated alias for --selector-topk-overlap-min
  --turnover-p95-max X             Deprecated alias for --selector-topk-overlap-min
  --max-compare-errors N           Acceptance threshold for compare transient errors (default: 1)
  --max-pairset-mismatch N         Acceptance threshold for compare pair-set mismatch warnings (default: 0)
  --coverage-min X                 Acceptance threshold (default: 0.98)
  --output-json PATH               Write full report JSON to file
  -h, --help                       Show help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

REPO_ROOT="$(pwd)"
META_FILE=""
BASELINE_START_UTC="2026-03-23T22:02:05Z"
BASELINE_END_UTC="2026-03-24T22:06:00Z"
INCLUDE_BASELINE="true"
SELECTOR_TOPK_OVERLAP_MIN="0.60"
SELECTOR_DWELL_MEAN_MIN="2.0"
MAX_COMPARE_ERRORS="1"
MAX_PAIRSET_MISMATCH="0"
COVERAGE_MIN="0.98"
OUTPUT_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --meta-file)
      META_FILE="${2:-}"
      shift 2
      ;;
    --baseline-start-utc)
      BASELINE_START_UTC="${2:-}"
      shift 2
      ;;
    --baseline-end-utc)
      BASELINE_END_UTC="${2:-}"
      shift 2
      ;;
    --no-baseline)
      INCLUDE_BASELINE="false"
      shift 1
      ;;
    --selector-topk-overlap-min|--turnover-local-max|--turnover-p95-max)
      SELECTOR_TOPK_OVERLAP_MIN="${2:-}"
      shift 2
      ;;
    --selector-dwell-mean-min)
      SELECTOR_DWELL_MEAN_MIN="${2:-}"
      shift 2
      ;;
    --max-compare-errors)
      MAX_COMPARE_ERRORS="${2:-}"
      shift 2
      ;;
    --max-pairset-mismatch)
      MAX_PAIRSET_MISMATCH="${2:-}"
      shift 2
      ;;
    --coverage-min)
      COVERAGE_MIN="${2:-}"
      shift 2
      ;;
    --output-json)
      OUTPUT_JSON="${2:-}"
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

require_cmd python3
require_cmd jq

cd "$REPO_ROOT"

if [[ -z "$META_FILE" ]]; then
  META_FILE="$REPO_ROOT/artifacts/runtime/weekend-monitoring-latest.json"
fi

[[ -f "$META_FILE" ]] || die "Metadata file not found: $META_FILE (start monitoring first)"

REPORT_JSON="$(
python3 - "$REPO_ROOT" "$META_FILE" "$BASELINE_START_UTC" "$BASELINE_END_UTC" "$INCLUDE_BASELINE" "$SELECTOR_TOPK_OVERLAP_MIN" "$SELECTOR_DWELL_MEAN_MIN" "$COVERAGE_MIN" "$MAX_COMPARE_ERRORS" "$MAX_PAIRSET_MISMATCH" <<'PY'
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(sys.argv[1])
meta_file = Path(sys.argv[2])
baseline_start_utc = sys.argv[3]
baseline_end_utc = sys.argv[4]
include_baseline = sys.argv[5].lower() == "true"
selector_topk_overlap_min = float(sys.argv[6])
selector_dwell_mean_min = float(sys.argv[7])
coverage_min = float(sys.argv[8])
max_compare_errors = int(sys.argv[9])
max_pairset_mismatch = int(sys.argv[10])

runs_dir = repo_root / "artifacts" / "signal_learning" / "runs"
meta = json.loads(meta_file.read_text())

def parse_iso_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"invalid timestamp value: {value!r}")
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.fromisoformat(value).astimezone(timezone.utc)

def parse_cycle_filename_ts(name: str):
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})Z-signal-learning-cycle\.json$", name)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)

def load_cycles(start_utc: datetime, end_utc: datetime):
    rows = []
    for path in runs_dir.glob("*-signal-learning-cycle.json"):
        ts = parse_cycle_filename_ts(path.name)
        if ts is None or ts < start_utc or ts > end_utc:
            continue
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        rows.append((ts, payload, path.name))
    rows.sort(key=lambda x: x[0])
    return rows

def parse_benchmark(path: Path):
    if not path.exists():
        return {
            "exists": False,
            "verdict_exp": 0,
            "verdict_main": 0,
            "verdict_tie": 0,
            "exp_win_rate": 0.0,
            "main_win_rate": 0.0,
            "total_verdicts": 0,
            "pair_mismatch_warn_count": 0,
            "curl_error_count": 0,
        }
    text = path.read_text(errors="ignore")
    verdict_exp = text.count("VERDICT: EXPERIMENTAL currently outperforms MAIN")
    verdict_main = text.count("VERDICT: MAIN currently outperforms EXPERIMENTAL")
    verdict_tie = text.count("VERDICT: TIE")
    total = verdict_exp + verdict_main + verdict_tie
    return {
        "exists": True,
        "verdict_exp": verdict_exp,
        "verdict_main": verdict_main,
        "verdict_tie": verdict_tie,
        "exp_win_rate": (verdict_exp / total) if total else 0.0,
        "main_win_rate": (verdict_main / total) if total else 0.0,
        "total_verdicts": total,
        "pair_mismatch_warn_count": text.count("pair count mismatch"),
        "curl_error_count": len(re.findall(r"curl:\s*\(\d+\)", text)),
    }

def parse_compare(path: Path):
    if not path.exists():
        return {
            "exists": False,
            "pair_set_mismatch_warnings": 0,
            "error_count": 0,
            "exp_cycle_count": 0,
            "prod_cycle_count": 0,
        }
    text = path.read_text(errors="ignore")
    return {
        "exists": True,
        "pair_set_mismatch_warnings": text.count("WARNING: pair-set mismatch"),
        "error_count": sum(1 for line in text.splitlines() if "ERROR:" in line),
        "exp_cycle_count": text.count("[EXP] base="),
        "prod_cycle_count": text.count("[PROD] base="),
    }

def summarize(rows):
    summary = {"cycles": len(rows)}
    if not rows:
        return summary

    summary["start_utc"] = rows[0][0].isoformat().replace("+00:00", "Z")
    summary["end_utc"] = rows[-1][0].isoformat().replace("+00:00", "Z")

    def pull(path, default=0.0):
        out = []
        for _, payload, _ in rows:
            value = payload
            for key in path:
                if isinstance(value, dict):
                    value = value.get(key, {})
                else:
                    value = {}
            out.append(float(value if isinstance(value, (int, float)) else default))
        return out

    keys = {
        "pairs_evaluated": ("summary", "pairs_evaluated"),
        "promote_recommendations": ("summary", "promote_recommendations"),
        "demote_recommendations": ("summary", "demote_recommendations"),
        "hold_recommendations": ("summary", "hold_recommendations"),
        "pairs_with_consensus": ("summary", "pairs_with_consensus"),
        "pairs_with_veto": ("summary", "pairs_with_veto"),
        "trade_eligible_timeframes": ("summary", "trade_eligible_timeframes"),
        "degraded_timeframes": ("summary", "degraded_timeframes"),
        "mutated_pairs": ("summary", "mutated_pairs"),
        "selection_selected_count": ("summary", "selection_selected_count"),
        "selected_with_paper_low_sample_count": ("selection", "selected_with_paper_low_sample_count"),
        "selection_turnover_rate": ("selection", "selection_turnover_rate"),
    }

    series = {key: pull(path) for key, path in keys.items()}

    for key, values in series.items():
        summary[key] = {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "sum": sum(values),
            "p95": (statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values)),
        }

    summary["count_degraded_nonzero"] = sum(
        1 for value in series["degraded_timeframes"] if value > 0.0
    )
    summary["count_low_sample_nonzero"] = sum(
        1 for value in series["selected_with_paper_low_sample_count"] if value > 0.0
    )
    summary["count_pairs_eval_48"] = sum(
        1 for value in series["pairs_evaluated"] if value == 48.0
    )
    summary["pairs_eval_48_ratio"] = summary["count_pairs_eval_48"] / len(rows)

    # Window-local turnover: recompute from top-1 sequence inside this report window only.
    top1_keys = []
    for _, payload, _ in rows:
        selection = payload.get("selection", {})
        top_1 = selection.get("top_1", {})
        if not isinstance(top_1, dict):
            continue
        pair_id = top_1.get("pair_id")
        timeframe = top_1.get("timeframe")
        if isinstance(pair_id, str) and pair_id and isinstance(timeframe, str) and timeframe:
            top1_keys.append(f"{pair_id}|{timeframe}")

    switches = 0
    for idx in range(1, len(top1_keys)):
        if top1_keys[idx] != top1_keys[idx - 1]:
            switches += 1
    observed = len(top1_keys)
    local_turnover = (switches / max(1, observed - 1)) if observed else 0.0
    summary["selection_turnover_rate_window_local"] = {
        "observed": observed,
        "switches": switches,
        "rate": local_turnover,
    }

    # Selector stability from top-k membership:
    # - adjacent overlap (order-insensitive)
    # - dwell runs of members remaining in top-k across consecutive cycles
    topk_sets = []
    for _, payload, _ in rows:
        selection = payload.get("selection", {})
        top_k = selection.get("top_k", [])
        keys = []
        if isinstance(top_k, list):
            for row in top_k:
                if not isinstance(row, dict):
                    continue
                pair_id = row.get("pair_id")
                timeframe = row.get("timeframe")
                if isinstance(pair_id, str) and pair_id and isinstance(timeframe, str) and timeframe:
                    keys.append(f"{pair_id}|{timeframe}")
        topk_sets.append(set(keys))

    overlaps = []
    overlap_losses = []
    for idx in range(1, len(topk_sets)):
        prev_set = topk_sets[idx - 1]
        curr_set = topk_sets[idx]
        denom = max(1, min(len(prev_set), len(curr_set)))
        overlap = len(prev_set & curr_set) / denom
        overlaps.append(overlap)
        overlap_losses.append(1.0 - overlap)

    active_members = {}
    member_runs = []
    for member_set in topk_sets:
        for key in list(active_members.keys()):
            if key in member_set:
                active_members[key] += 1
            else:
                member_runs.append(active_members[key])
                del active_members[key]
        for key in member_set:
            if key not in active_members:
                active_members[key] = 1
    member_runs.extend(active_members.values())

    summary["selector_stability"] = {
        "topk_overlap_mean": (sum(overlaps) / len(overlaps)) if overlaps else 0.0,
        "topk_overlap_p95_loss": (
            statistics.quantiles(overlap_losses, n=20)[18]
            if len(overlap_losses) >= 20
            else (max(overlap_losses) if overlap_losses else 0.0)
        ),
        "topk_member_dwell_mean": (sum(member_runs) / len(member_runs)) if member_runs else 0.0,
        "topk_member_dwell_p50": statistics.median(member_runs) if member_runs else 0.0,
        "topk_member_dwell_runs": len(member_runs),
        "adjacent_pairs": len(overlaps),
    }

    return summary

def acceptance(snapshot_summary, benchmark_summary, compare_summary):
    if not snapshot_summary or snapshot_summary.get("cycles", 0) == 0:
        return {
            "A_low_sample_zero": False,
            "B_degraded_zero": False,
            "C_pairset_stable": False,
            "D_benchmark_not_worse": False,
            "E_selector_stability_guard": False,
            "F_coverage_guard": False,
            "all_pass": False,
        }
    checks = {
        "A_low_sample_zero": snapshot_summary["count_low_sample_nonzero"] == 0,
        "B_degraded_zero": snapshot_summary["count_degraded_nonzero"] == 0,
        "C_pairset_stable": compare_summary.get("pair_set_mismatch_warnings", 1) <= max_pairset_mismatch
        and compare_summary.get("error_count", 1) <= max_compare_errors,
        "D_benchmark_not_worse": benchmark_summary.get("exp_win_rate", 0.0)
        >= benchmark_summary.get("main_win_rate", 1.0),
        "E_selector_stability_guard": snapshot_summary["selector_stability"]["topk_overlap_mean"] >= selector_topk_overlap_min
        and snapshot_summary["selector_stability"]["topk_member_dwell_mean"] >= selector_dwell_mean_min,
        "F_coverage_guard": snapshot_summary["pairs_eval_48_ratio"] >= coverage_min,
    }
    checks["all_pass"] = all(checks.values())
    return checks

candidate_start = parse_iso_utc(meta["start_utc"])
candidate_end_target = parse_iso_utc(meta["deadline_utc"])
now_utc = datetime.now(timezone.utc)
candidate_end_effective = min(candidate_end_target, now_utc)
candidate_rows = load_cycles(candidate_start, candidate_end_effective)

logs = meta.get("logs", {})
benchmark_path = Path(logs.get("benchmark", ""))
compare_path = Path(logs.get("compare_snapshots", ""))

candidate_summary = summarize(candidate_rows)
candidate_benchmark = parse_benchmark(benchmark_path)
candidate_compare = parse_compare(compare_path)
candidate_acceptance = acceptance(candidate_summary, candidate_benchmark, candidate_compare)

report = {
    "generated_at_utc": now_utc.isoformat().replace("+00:00", "Z"),
    "meta_file": str(meta_file),
    "thresholds": {
        "selector_topk_overlap_min": selector_topk_overlap_min,
        "selector_dwell_mean_min": selector_dwell_mean_min,
        "max_compare_errors": max_compare_errors,
        "max_pairset_mismatch_warnings": max_pairset_mismatch,
        "coverage_min": coverage_min,
    },
    "candidate_window": {
        "start_utc": candidate_start.isoformat().replace("+00:00", "Z"),
        "end_utc_effective": candidate_end_effective.isoformat().replace("+00:00", "Z"),
        "end_utc_target": candidate_end_target.isoformat().replace("+00:00", "Z"),
        "is_complete": candidate_end_effective >= candidate_end_target,
    },
    "candidate": {
        "summary": candidate_summary,
        "benchmark": candidate_benchmark,
        "compare": candidate_compare,
        "acceptance": candidate_acceptance,
    },
}

if include_baseline:
    baseline_start = parse_iso_utc(baseline_start_utc)
    baseline_end = parse_iso_utc(baseline_end_utc)
    baseline_rows = load_cycles(baseline_start, baseline_end)
    baseline_summary = summarize(baseline_rows)
    report["baseline_window"] = {
        "start_utc": baseline_start.isoformat().replace("+00:00", "Z"),
        "end_utc": baseline_end.isoformat().replace("+00:00", "Z"),
    }
    report["baseline"] = {
        "summary": baseline_summary,
    }

    if baseline_summary.get("cycles", 0) > 0 and candidate_summary.get("cycles", 0) > 0:
        report["delta_post_minus_baseline"] = {
            "promote_recommendations_mean": candidate_summary["promote_recommendations"]["mean"]
            - baseline_summary["promote_recommendations"]["mean"],
            "trade_eligible_timeframes_mean": candidate_summary["trade_eligible_timeframes"]["mean"]
            - baseline_summary["trade_eligible_timeframes"]["mean"],
            "pairs_with_consensus_mean": candidate_summary["pairs_with_consensus"]["mean"]
            - baseline_summary["pairs_with_consensus"]["mean"],
            "selection_turnover_rate_mean": candidate_summary["selection_turnover_rate"]["mean"]
            - baseline_summary["selection_turnover_rate"]["mean"],
            "selection_turnover_rate_window_local": candidate_summary["selection_turnover_rate_window_local"]["rate"],
            "selector_topk_overlap_mean": candidate_summary["selector_stability"]["topk_overlap_mean"],
            "selector_topk_member_dwell_mean": candidate_summary["selector_stability"]["topk_member_dwell_mean"],
            "selected_with_paper_low_sample_count_mean": candidate_summary[
                "selected_with_paper_low_sample_count"
            ]["mean"]
            - baseline_summary["selected_with_paper_low_sample_count"]["mean"],
            "pairs_eval_48_ratio": candidate_summary["pairs_eval_48_ratio"]
            - baseline_summary["pairs_eval_48_ratio"],
        }

print(json.dumps(report))
PY
)"

if [[ -n "$OUTPUT_JSON" ]]; then
  printf '%s\n' "$REPORT_JSON" > "$OUTPUT_JSON"
fi

echo "=== Signal Monitoring Pass/Fail Report ==="
echo "$REPORT_JSON" | jq '{
  generated_at_utc,
  candidate_window,
  thresholds,
  acceptance: .candidate.acceptance,
  candidate_key_metrics: {
    cycles: .candidate.summary.cycles,
    pairs_eval_48_ratio: .candidate.summary.pairs_eval_48_ratio,
    selected_with_paper_low_sample_count_mean: .candidate.summary.selected_with_paper_low_sample_count.mean,
    selection_turnover_rate_window_local: .candidate.summary.selection_turnover_rate_window_local.rate,
    selection_turnover_rate_window_local_switches: .candidate.summary.selection_turnover_rate_window_local.switches,
    selection_turnover_rate_window_local_observed: .candidate.summary.selection_turnover_rate_window_local.observed,
    selection_turnover_rate_cumulative_mean: .candidate.summary.selection_turnover_rate.mean,
    selection_turnover_rate_cumulative_p95: .candidate.summary.selection_turnover_rate.p95,
    selector_topk_overlap_mean: .candidate.summary.selector_stability.topk_overlap_mean,
    selector_topk_overlap_p95_loss: .candidate.summary.selector_stability.topk_overlap_p95_loss,
    selector_topk_member_dwell_mean: .candidate.summary.selector_stability.topk_member_dwell_mean,
    selector_topk_member_dwell_p50: .candidate.summary.selector_stability.topk_member_dwell_p50,
    selector_topk_member_dwell_runs: .candidate.summary.selector_stability.topk_member_dwell_runs,
    promote_recommendations_mean: .candidate.summary.promote_recommendations.mean,
    trade_eligible_timeframes_mean: .candidate.summary.trade_eligible_timeframes.mean,
    pairs_with_consensus_mean: .candidate.summary.pairs_with_consensus.mean
  },
  benchmark: .candidate.benchmark,
  compare: .candidate.compare
}'

if [[ "$INCLUDE_BASELINE" == "true" ]]; then
  echo ""
  echo "=== Baseline Delta (candidate - baseline) ==="
  echo "$REPORT_JSON" | jq '.delta_post_minus_baseline // {"info":"baseline unavailable"}'
fi

ALL_PASS="$(echo "$REPORT_JSON" | jq -r '.candidate.acceptance.all_pass')"
if [[ "$ALL_PASS" == "true" ]]; then
  echo ""
  echo "RESULT: PASS (all acceptance checks met)."
  exit 0
fi

echo ""
echo "RESULT: FAIL (one or more acceptance checks failed)."
exit 2
