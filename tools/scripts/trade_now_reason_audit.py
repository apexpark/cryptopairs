#!/usr/bin/env python3
"""Summarize Trade Now WAIT/SETUP/block reasons from captured JSON.

This script is read-only. It accepts a `GET /v1/strategy/pairs/trade-now`
response captured by an operator and prints a deterministic reason summary.
It does not connect to a host and does not infer runtime state from repo files.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BUCKETS = ("tradable_now", "watchlist", "excluded")

SCHEDULER_RELEVANCE = {
    "SETUP_GATE_NOT_PASSING": "market_or_live_gate_not_scheduler",
    "LIVE_TRIGGER_NOT_READY": "market_or_live_gate_not_scheduler",
    "OPEN_POSITION_CONFLICT": "position_state_not_scheduler",
    "COST_GATE_NOT_PASSING": "maybe_reoptimize_but_not_sufficient",
    "TRADE_GATE_NOT_PASSING": "maybe_reoptimize_but_not_sufficient",
    "LEARNING_ELIGIBLE_NOT_SELECTED": "learning_selection_not_scheduler",
    "LEARNING_OVERLAY_STALE": "learning_overlay_refresh_not_scheduler",
    "PROVENANCE_POLICY_BLOCKED": "provenance_block_not_scheduler",
    "RECANONICALIZED_LEGACY_ROW_ACTIVE": "provenance_block_not_scheduler",
    "LEGACY_FALLBACK_ACTIVE": "provenance_block_not_scheduler",
    "GOVERNANCE_POLICY_BLOCKED": "governance_policy_not_scheduler",
    "PENDING_CHALLENGER_REQUIRES_PROMOTION": "governance_policy_not_scheduler",
    "OUTSIDE_APPROVED_UNIVERSE": "learning_policy_not_scheduler",
    "LEARNING_HOLD": "learning_policy_not_scheduler",
    "LEARNING_NOT_TRADE_ELIGIBLE": "learning_policy_not_scheduler",
}


def load_payload(path: str) -> dict[str, Any]:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def iter_rows(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for bucket in BUCKETS:
        value = payload.get(bucket, [])
        if not isinstance(value, list):
            continue
        rows.extend((bucket, row) for row in value if isinstance(row, dict))
    return rows


def first_reason(row: dict[str, Any]) -> str:
    for key in ("watch_reason_code", "blocked_reason_code", "decision_reason_code"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return "UNKNOWN_REASON"


def scheduler_relevance(reason: str) -> str:
    return SCHEDULER_RELEVANCE.get(reason, "unknown_or_mixed")


def summarize_payload(payload: dict[str, Any], source: str) -> dict[str, Any]:
    bucket_counts: Counter[str] = Counter()
    timeframe_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    watch_counts: Counter[str] = Counter()
    blocked_counts: Counter[str] = Counter()
    rationale_counts: Counter[str] = Counter()
    gate_fail_counts: Counter[str] = Counter()
    relevance_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for bucket, row in iter_rows(payload):
        bucket_name = str(row.get("decision_bucket") or bucket).upper()
        timeframe = str(row.get("timeframe") or "unknown")
        reason = first_reason(row)

        bucket_counts[bucket_name] += 1
        timeframe_counts[timeframe] += 1
        reason_counts[reason] += 1
        relevance_counts[scheduler_relevance(reason)] += 1

        for field, counter in (
            ("decision_reason_code", decision_counts),
            ("watch_reason_code", watch_counts),
            ("blocked_reason_code", blocked_counts),
        ):
            value = row.get(field)
            if isinstance(value, str) and value:
                counter[value] += 1

        for code in row.get("rationale_codes", []):
            if isinstance(code, str) and code:
                rationale_counts[code] += 1

        if row.get("setup_gate_pass") is False:
            gate_fail_counts["setup_gate_fail"] += 1
        if row.get("cost_gate_pass") is False:
            gate_fail_counts["cost_gate_fail"] += 1
        if row.get("trade_gate_pass") is False:
            gate_fail_counts["trade_gate_fail"] += 1
        if row.get("open_live_trade") is True:
            gate_fail_counts["open_live_trade"] += 1

        if len(examples[reason]) < 5:
            examples[reason].append(
                {
                    "pair_id": row.get("pair_id"),
                    "timeframe": row.get("timeframe"),
                    "bucket": bucket_name,
                    "setup_gate_pass": row.get("setup_gate_pass"),
                    "cost_gate_pass": row.get("cost_gate_pass"),
                    "trade_gate_pass": row.get("trade_gate_pass"),
                    "selected_config_source": row.get("selected_config_source"),
                    "approval_source": row.get("approval_source"),
                    "scheduler_relevance": scheduler_relevance(reason),
                }
            )

    return {
        "source": source,
        "generated_at": payload.get("generated_at"),
        "timeframe_filter": payload.get("timeframe_filter"),
        "learning_overlay_generated_at": payload.get("learning_overlay_generated_at"),
        "learning_overlay_fresh": payload.get("learning_overlay_fresh"),
        "total_rows": sum(bucket_counts.values()),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "timeframe_counts": dict(sorted(timeframe_counts.items())),
        "reason_counts": dict(reason_counts.most_common()),
        "decision_reason_counts": dict(decision_counts.most_common()),
        "watch_reason_counts": dict(watch_counts.most_common()),
        "blocked_reason_counts": dict(blocked_counts.most_common()),
        "rationale_counts": dict(rationale_counts.most_common()),
        "gate_fail_counts": dict(sorted(gate_fail_counts.items())),
        "scheduler_relevance_counts": dict(relevance_counts.most_common()),
        "examples_by_reason": dict(sorted(examples.items())),
    }


def summarize(paths: list[str]) -> dict[str, Any]:
    summaries = [summarize_payload(load_payload(path), path) for path in paths]
    aggregate_reasons: Counter[str] = Counter()
    aggregate_relevance: Counter[str] = Counter()
    aggregate_buckets: Counter[str] = Counter()
    for summary in summaries:
        aggregate_reasons.update(summary["reason_counts"])
        aggregate_relevance.update(summary["scheduler_relevance_counts"])
        aggregate_buckets.update(summary["bucket_counts"])
    return {
        "sources": paths,
        "source_count": len(paths),
        "aggregate": {
            "bucket_counts": dict(aggregate_buckets.most_common()),
            "reason_counts": dict(aggregate_reasons.most_common()),
            "scheduler_relevance_counts": dict(aggregate_relevance.most_common()),
        },
        "summaries": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "json_file",
        nargs="+",
        help="Trade Now JSON file(s), or '-' to read one response from stdin.",
    )
    parser.add_argument("--output-json", help="Optional path for the JSON report.")
    args = parser.parse_args()

    try:
        report = summarize(args.json_file)
    except Exception as error:  # noqa: BLE001
        print(f"trade-now audit failed: {error}", file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
