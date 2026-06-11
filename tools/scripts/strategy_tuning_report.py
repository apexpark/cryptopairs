#!/usr/bin/env python3
"""Deterministic strategy tuning reporter with promote/hold/revert recommendations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SUPPORTED_TIMEFRAMES = ("1m", "15m", "1h")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timeframes(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    parsed = [value for value in values if value in SUPPORTED_TIMEFRAMES]
    if not parsed:
        return list(SUPPORTED_TIMEFRAMES)
    # preserve order and remove duplicates
    unique: list[str] = []
    for value in parsed:
        if value not in unique:
            unique.append(value)
    return unique


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def http_json(
    url: str,
    timeout_seconds: int,
    method: str = "GET",
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_guardrail_blocks(
    cues: list[dict[str, Any]],
    guardrail_codes: set[str],
) -> tuple[int, dict[str, int]]:
    blocked_pairs = 0
    counts: dict[str, int] = {code: 0 for code in sorted(guardrail_codes)}
    for row in cues:
        cue = row.get("cue", {})
        cue_codes = cue.get("rationale_codes", [])
        cost_gate_codes = cue.get("cost_gate", {}).get("rationale_codes", [])
        combined_codes = set([*cue_codes, *cost_gate_codes])
        blocked = False
        for code in combined_codes:
            if code in guardrail_codes:
                counts[code] = counts.get(code, 0) + 1
                blocked = True
        if blocked:
            blocked_pairs += 1
    return blocked_pairs, counts


def summarize_timeframe(
    timeframe: str,
    response: dict[str, Any],
    guardrail_codes: set[str],
) -> dict[str, Any]:
    candidate_set = response.get("candidate_set", {})
    cues = response.get("cues", [])
    evaluated_pairs = int(candidate_set.get("evaluated_pairs", len(cues)))
    actionable_pairs = int(candidate_set.get("actionable_pairs", 0))
    cost_gate_pass_pairs = int(candidate_set.get("cost_gate_pass_pairs", 0))
    shadow_disagreement_pairs = int(candidate_set.get("shadow_disagreement_pairs", 0))

    guardrail_blocked_pairs, guardrail_code_counts = count_guardrail_blocks(cues, guardrail_codes)

    return {
        "timeframe": timeframe,
        "total_pairs": int(candidate_set.get("total_pairs", len(cues))),
        "evaluated_pairs": evaluated_pairs,
        "actionable_pairs": actionable_pairs,
        "actionable_ratio": safe_div(actionable_pairs, evaluated_pairs),
        "cost_gate_pass_pairs": cost_gate_pass_pairs,
        "cost_gate_pass_ratio": safe_div(cost_gate_pass_pairs, evaluated_pairs),
        "shadow_disagreement_pairs": shadow_disagreement_pairs,
        "shadow_disagreement_ratio": safe_div(shadow_disagreement_pairs, evaluated_pairs),
        "guardrail_blocked_pairs": guardrail_blocked_pairs,
        "guardrail_block_ratio": safe_div(guardrail_blocked_pairs, evaluated_pairs),
        "guardrail_code_counts": guardrail_code_counts,
    }


def compute_drawdown_pct(equity_points: list[float]) -> float:
    if not equity_points:
        return 0.0
    peak = equity_points[0]
    worst_drawdown = 0.0
    for equity in equity_points:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        drawdown = (equity / peak) - 1.0
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown
    return worst_drawdown * 100.0


def compute_backtest_insight(pair_id: str, timeframe: str, bars: int, backtest: dict[str, Any]) -> dict[str, Any]:
    points = backtest.get("points", [])
    equities = [float(point.get("equity", 0.0)) for point in points if "equity" in point]
    start = equities[0] if equities else 0.0
    end = equities[-1] if equities else 0.0
    equity_return_pct = 0.0
    if start > 0:
        equity_return_pct = ((end / start) - 1.0) * 100.0

    markers = backtest.get("markers", [])
    entries = sum(1 for marker in markers if marker.get("kind") == "entry")
    exits = sum(1 for marker in markers if marker.get("kind") == "exit")
    stops = sum(1 for marker in markers if marker.get("kind") == "stop")

    return {
        "timeframe": timeframe,
        "pair_id": pair_id,
        "bars": bars,
        "equity_return_pct": equity_return_pct,
        "max_drawdown_pct": compute_drawdown_pct(equities),
        "entries": entries,
        "exits": exits,
        "stops": stops,
    }


def average_metric(timeframe_rows: list[dict[str, Any]], key: str) -> float:
    if not timeframe_rows:
        return 0.0
    return sum(float(row.get(key, 0.0)) for row in timeframe_rows) / float(len(timeframe_rows))


def execution_alert_counts(alerts: list[dict[str, Any]]) -> tuple[int, int]:
    p1 = 0
    p2 = 0
    for alert in alerts:
        if not alert.get("triggered"):
            continue
        severity = str(alert.get("severity", "")).upper()
        if severity == "P1":
            p1 += 1
        elif severity == "P2":
            p2 += 1
    return p1, p2


def build_comparison(
    current_aggregate: dict[str, Any],
    baseline_report: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, float]]:
    if not baseline_report:
        deltas = {
            "actionable_ratio_mean": 0.0,
            "cost_gate_pass_ratio_mean": 0.0,
            "shadow_disagreement_ratio_mean": 0.0,
            "guardrail_block_ratio_mean": 0.0,
        }
        return (
            {
                "baseline_report": None,
                "deltas": deltas,
                "checks": [],
            },
            deltas,
        )

    baseline_aggregate = baseline_report.get("metrics", {}).get("aggregate", {})
    deltas = {
        "actionable_ratio_mean": float(current_aggregate.get("actionable_ratio_mean", 0.0))
        - float(baseline_aggregate.get("actionable_ratio_mean", 0.0)),
        "cost_gate_pass_ratio_mean": float(current_aggregate.get("cost_gate_pass_ratio_mean", 0.0))
        - float(baseline_aggregate.get("cost_gate_pass_ratio_mean", 0.0)),
        "shadow_disagreement_ratio_mean": float(
            current_aggregate.get("shadow_disagreement_ratio_mean", 0.0)
        )
        - float(baseline_aggregate.get("shadow_disagreement_ratio_mean", 0.0)),
        "guardrail_block_ratio_mean": float(current_aggregate.get("guardrail_block_ratio_mean", 0.0))
        - float(baseline_aggregate.get("guardrail_block_ratio_mean", 0.0)),
    }
    return (
        {
            "baseline_report": baseline_report.get("artifacts", {}).get("report_path"),
            "deltas": deltas,
            "checks": [],
        },
        deltas,
    )


def evaluate_checks(
    thresholds: dict[str, Any],
    deltas: dict[str, float],
    reopt_error_count: int,
    p1_triggered: int,
    p2_triggered: int,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "pass": passed, "detail": detail})

    actionable_threshold = float(thresholds.get("min_actionable_ratio_delta", 0.0))
    actionable_delta = float(deltas.get("actionable_ratio_mean", 0.0))
    add_check(
        "actionable_ratio_delta",
        actionable_delta >= actionable_threshold,
        f"delta={actionable_delta:.6f} threshold>={actionable_threshold:.6f}",
    )

    cost_threshold = float(thresholds.get("min_cost_gate_pass_ratio_delta", 0.0))
    cost_delta = float(deltas.get("cost_gate_pass_ratio_mean", 0.0))
    add_check(
        "cost_gate_pass_ratio_delta",
        cost_delta >= cost_threshold,
        f"delta={cost_delta:.6f} threshold>={cost_threshold:.6f}",
    )

    guardrail_threshold = float(thresholds.get("max_guardrail_block_ratio_delta", 0.0))
    guardrail_delta = float(deltas.get("guardrail_block_ratio_mean", 0.0))
    add_check(
        "guardrail_block_ratio_delta",
        guardrail_delta <= guardrail_threshold,
        f"delta={guardrail_delta:.6f} threshold<={guardrail_threshold:.6f}",
    )

    shadow_threshold = float(thresholds.get("max_shadow_disagreement_ratio_delta", 0.0))
    shadow_delta = float(deltas.get("shadow_disagreement_ratio_mean", 0.0))
    add_check(
        "shadow_disagreement_ratio_delta",
        shadow_delta <= shadow_threshold,
        f"delta={shadow_delta:.6f} threshold<={shadow_threshold:.6f}",
    )

    max_reopt_errors = int(thresholds.get("max_reopt_error_count", 0))
    add_check(
        "reopt_errors",
        reopt_error_count <= max_reopt_errors,
        f"errors={reopt_error_count} threshold<={max_reopt_errors}",
    )

    allow_p1_alerts = bool(thresholds.get("allow_p1_alerts", False))
    add_check(
        "execution_p1_alerts",
        allow_p1_alerts or p1_triggered == 0,
        f"p1={p1_triggered} policy_allow={str(allow_p1_alerts).lower()}",
    )

    allow_p2_alerts = bool(thresholds.get("allow_p2_alerts", True))
    add_check(
        "execution_p2_alerts",
        allow_p2_alerts or p2_triggered == 0,
        f"p2={p2_triggered} policy_allow={str(allow_p2_alerts).lower()}",
    )

    return checks


def decide(
    profile: str,
    baseline_report_present: bool,
    checks: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    if not baseline_report_present:
        return (
            "HOLD",
            [
                "Baseline comparison report not supplied.",
                "Fail-closed mode keeps decision at HOLD until comparison evidence exists.",
            ],
        )

    failed = [check for check in checks if not check["pass"]]
    if failed:
        reasons = [f"check_failed:{check['name']} ({check['detail']})" for check in failed]
        if profile == "candidate":
            return "REVERT", reasons
        return "HOLD", reasons

    if profile == "candidate":
        return (
            "PROMOTE",
            [
                "All threshold checks passed for candidate profile.",
                "No fail-closed guardrail check breached.",
            ],
        )

    return (
        "HOLD",
        [
            "Profile is baseline; promotion decision is only valid for candidate runs.",
        ],
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    policy_path = Path(args.policy_json)
    policy = load_json(policy_path)
    thresholds = policy.get("decision_thresholds", {})
    guardrail_codes = set(policy.get("guardrail_codes", []))
    analytics_cfg = policy.get("analytics", {})
    bars_by_timeframe = analytics_cfg.get("bars_by_timeframe", {})
    top_pairs_per_timeframe = int(analytics_cfg.get("top_pairs_per_timeframe", 5))

    timeframes = parse_timeframes(args.timeframes)

    reopt_summary: dict[str, Any]
    if args.skip_reoptimize:
        reopt_summary = {
            "pairs_processed": 0,
            "cues_generated": 0,
            "cost_gate_pass": 0,
            "cost_gate_fail": 0,
            "errors": [],
        }
    else:
        reopt_payload = {"timeframes": timeframes}
        reopt_response = http_json(
            f"{args.strategy_service_url}/v1/strategy/pairs/reoptimize",
            args.timeout_seconds,
            method="POST",
            payload=reopt_payload,
        )
        reopt_summary = {
            "pairs_processed": int(reopt_response.get("pairs_processed", 0)),
            "cues_generated": int(reopt_response.get("cues_generated", 0)),
            "cost_gate_pass": int(reopt_response.get("cost_gate_pass", 0)),
            "cost_gate_fail": int(reopt_response.get("cost_gate_fail", 0)),
            "errors": reopt_response.get("errors", []),
        }

    execution_summary = http_json(
        f"{args.execution_service_url}/v1/execution/observability/summary",
        args.timeout_seconds,
        query={
            "exchange": args.exchange,
            "account_id": args.account_id,
            "window_minutes": args.window_minutes,
        },
    )
    execution_alerts = execution_summary.get("alerts", [])
    p1_triggered, p2_triggered = execution_alert_counts(execution_alerts)

    timeframe_summaries: list[dict[str, Any]] = []
    backtest_insights: list[dict[str, Any]] = []

    for timeframe in timeframes:
        cues_response = http_json(
            f"{args.strategy_service_url}/v1/strategy/pairs/cues",
            args.timeout_seconds,
            query={"timeframe": timeframe, "limit": max(1, min(args.limit, 100))},
        )
        timeframe_summary = summarize_timeframe(timeframe, cues_response, guardrail_codes)
        timeframe_summaries.append(timeframe_summary)

        cues = cues_response.get("cues", [])
        cues_sorted = sorted(
            cues,
            key=lambda row: float(row.get("cue", {}).get("opportunity_score", 0.0)),
            reverse=True,
        )
        top_rows = cues_sorted[: max(1, top_pairs_per_timeframe)]
        bars = int(bars_by_timeframe.get(timeframe, 300))
        bars = max(120, min(bars, 2000))

        for row in top_rows:
            pair_id = str(row.get("cue", {}).get("pair_id", "")).strip()
            if not pair_id:
                continue
            backtest = http_json(
                f"{args.strategy_service_url}/v1/strategy/pairs/backtest",
                args.timeout_seconds,
                query={
                    "timeframe": timeframe,
                    "pair_id": pair_id,
                    "bars": bars,
                },
            )
            backtest_insights.append(compute_backtest_insight(pair_id, timeframe, bars, backtest))

    aggregate = {
        "timeframes": [summary["timeframe"] for summary in timeframe_summaries],
        "actionable_ratio_mean": average_metric(timeframe_summaries, "actionable_ratio"),
        "cost_gate_pass_ratio_mean": average_metric(timeframe_summaries, "cost_gate_pass_ratio"),
        "shadow_disagreement_ratio_mean": average_metric(
            timeframe_summaries,
            "shadow_disagreement_ratio",
        ),
        "guardrail_block_ratio_mean": average_metric(timeframe_summaries, "guardrail_block_ratio"),
    }

    baseline_report: dict[str, Any] | None = None
    baseline_report_path: str | None = None
    if args.compare_report:
        baseline_path = Path(args.compare_report)
        if baseline_path.exists():
            baseline_report = load_json(baseline_path)
            baseline_report_path = str(baseline_path)

    comparison, deltas = build_comparison(aggregate, baseline_report)
    checks = evaluate_checks(
        thresholds,
        deltas,
        len(reopt_summary.get("errors", [])),
        p1_triggered,
        p2_triggered,
    )
    comparison["checks"] = checks

    decision, decision_reasons = decide(
        args.profile,
        baseline_report is not None,
        checks,
    )

    return {
        "generated_at": utc_now_iso(),
        "profile": args.profile,
        "decision": decision,
        "decision_reasons": decision_reasons,
        "policy": {
            "path": str(policy_path),
            "version": int(policy.get("version", 1)),
            "guardrail_codes": sorted(list(guardrail_codes)),
        },
        "metrics": {
            "by_timeframe": timeframe_summaries,
            "aggregate": aggregate,
        },
        "comparison": comparison,
        "execution_observability": {
            "window_minutes": int(args.window_minutes),
            "p1_triggered": p1_triggered,
            "p2_triggered": p2_triggered,
            "alerts": execution_alerts,
        },
        "reoptimize_summary": reopt_summary,
        "backtest_insights": backtest_insights,
        "artifacts": {
            "report_path": str(args.output_json),
            "baseline_report_path": baseline_report_path,
        },
    }


def build_failure_report(args: argparse.Namespace, error: Exception) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "profile": args.profile,
        "decision": "HOLD",
        "decision_reasons": [
            "Reporter execution failed.",
            f"error:{error}",
            "Fail-closed default set to HOLD.",
        ],
        "policy": {
            "path": str(args.policy_json),
            "version": 1,
            "guardrail_codes": [],
        },
        "metrics": {
            "by_timeframe": [],
            "aggregate": {
                "timeframes": [],
                "actionable_ratio_mean": 0.0,
                "cost_gate_pass_ratio_mean": 0.0,
                "shadow_disagreement_ratio_mean": 0.0,
                "guardrail_block_ratio_mean": 0.0,
            },
        },
        "comparison": {
            "baseline_report": args.compare_report,
            "deltas": {
                "actionable_ratio_mean": 0.0,
                "cost_gate_pass_ratio_mean": 0.0,
                "shadow_disagreement_ratio_mean": 0.0,
                "guardrail_block_ratio_mean": 0.0,
            },
            "checks": [
                {
                    "name": "reporter_execution",
                    "pass": False,
                    "detail": str(error),
                }
            ],
        },
        "execution_observability": {
            "window_minutes": int(args.window_minutes),
            "p1_triggered": 0,
            "p2_triggered": 0,
            "alerts": [],
        },
        "reoptimize_summary": {
            "pairs_processed": 0,
            "cues_generated": 0,
            "cost_gate_pass": 0,
            "cost_gate_fail": 0,
            "errors": [{"pair_id": "*", "timeframe": "1m", "error": str(error)}],
        },
        "backtest_insights": [],
        "artifacts": {
            "report_path": str(args.output_json),
            "baseline_report_path": args.compare_report,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:8083")
    parser.add_argument("--execution-service-url", default="http://127.0.0.1:8082")
    parser.add_argument("--exchange", default="kraken_futures")
    parser.add_argument("--account-id", default="primary")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--policy-json",
        default="infra/config/strategy_tuning_policy.json",
    )
    parser.add_argument("--profile", choices=["baseline", "candidate"], default="candidate")
    parser.add_argument("--compare-report", help="Baseline report JSON path for delta checks")
    parser.add_argument("--timeframes", default="1m,15m,1h")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--skip-reoptimize", action="store_true")
    parser.add_argument(
        "--output-json",
        default="artifacts/strategy_tuning/report.json",
    )
    args = parser.parse_args()

    args.window_minutes = max(1, min(args.window_minutes, 24 * 60))
    args.timeout_seconds = max(3, args.timeout_seconds)
    args.limit = max(1, min(args.limit, 100))

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = build_report(args)
        rc = 0
    except Exception as error:  # noqa: BLE001
        report = build_failure_report(args, error)
        rc = 1

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    # decision exit semantics:
    # 0 = promote-ready / hold
    # 2 = revert suggested
    if report.get("decision") == "REVERT":
        return 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
