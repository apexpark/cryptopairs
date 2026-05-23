#!/usr/bin/env python3
"""Build a Slice F evidence manifest from an operator-provided raw bundle.

The script only reads local files already captured by the operator. It does not
connect to a host, does not verify runtime state itself, and emits fail-closed
manifest fields when evidence is absent or contradictory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slice_f_evidence_check import REQUIRED_ALERT_RULES


SCHEMA_VERSION = "1.1.0"
HOST_REPO_ROOT = Path("/opt/cryptopairs")
RUN_STATUSES = {
    "QUEUED",
    "LEASED",
    "RUNNING",
    "CANCEL_REQUESTED",
    "CANCELED",
    "SUCCEEDED",
    "DEGRADED",
    "FAILED",
    "EXPIRED",
}
RECOMMENDATIONS = {
    "HOLD",
    "OPERATOR_REVIEW_REQUIRED",
    "PROMOTION_CANDIDATE_AVAILABLE",
    "REVERT_REVIEW_REQUIRED",
}
FAIL_CLOSED_REASONS = {
    "MISSING_TELEMETRY",
    "UNKNOWN_STATUS",
    "STALE_STATUS",
    "LEASE_LOST",
    "BUDGET_EXHAUSTED",
    "CANCELED",
    "ARTIFACT_FAILED",
    "INTEGRITY_UNKNOWN",
    "RISK_UNKNOWN",
    "ACCOUNTING_ANOMALY",
    "SCHEDULE_MISSED",
    "UNSAFE_PROMOTION_ATTEMPT",
    "CONFIG_INVALID",
    "REPAIR_PROVENANCE_ACTIVE",
}
LOG_EVENTS = {
    "strategy reoptimize worker disabled",
    "reoptimize_run_enqueue_attempted",
    "reoptimize_run_enqueued",
    "reoptimize_run_enqueue_rejected",
    "reoptimize_lease_acquired",
    "reoptimize_lease_heartbeat",
    "reoptimize_lease_lost",
    "reoptimize_budget_exhausted",
    "reoptimize_cancel_observed",
    "reoptimize_recommendation_finalized",
    "reoptimize_fail_closed",
}
ACTIVE_STATUSES = ("QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED")
REQUIRED_BUDGET_ENV = {
    "STRATEGY_REOPT_HEARTBEAT_INTERVAL_SECONDS",
    "STRATEGY_REOPT_LEASE_TTL_SECONDS",
    "STRATEGY_REOPT_MAX_ARTIFACT_BYTES",
    "STRATEGY_REOPT_MAX_DB_WRITE_BATCH_SIZE",
    "STRATEGY_REOPT_MAX_IN_FLIGHT_PAIR_EVALUATIONS",
    "STRATEGY_REOPT_MAX_PAIRS_PER_RUN",
    "STRATEGY_REOPT_MAX_PAIRS_PER_TIMEFRAME",
    "STRATEGY_REOPT_MAX_RUN_SECONDS",
    "STRATEGY_REOPT_MAX_TIMEFRAME_SECONDS",
    "STRATEGY_REOPT_MIN_COOLDOWN_SECONDS",
}


ARTIFACT_CANDIDATES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "repo_identity": ("JSON", "repo_identity", ("repo_identity.json", "host_identity.json", "host_identity.txt")),
    "runner_flags_before": (
        "JSON",
        "runner_flags",
        ("runner_flags_before.json", "runner_flags_before.txt", "strategy_reopt_flags.txt"),
    ),
    "status_before": (
        "STATUS",
        "status",
        ("status_before.json", "status_before.txt", "reopt_latest_before.txt"),
    ),
    "metrics_before": ("METRICS", "metrics", ("metrics_before.prom", "metrics_before.txt", "strategy_metrics_before.txt")),
    "alerts_config": ("ALERTS", "alerts", ("alerts_config.json", "alerts_config.txt", "alerting_services.txt")),
    "alerts_before": ("ALERTS", "alerts", ("alerts_before.json", "alerts_before.txt")),
    "strategy_logs_before": (
        "LOG",
        "logs",
        ("strategy_logs_before.log", "strategy_logs_before.txt", "strategy_startup_logs.txt"),
    ),
    "threshold_approval": (
        "THRESHOLD",
        "thresholds",
        ("threshold_approval.json", "threshold_approval.txt"),
    ),
    "cpu_baseline": ("THRESHOLD", "thresholds", ("cpu_baseline.json", "cpu_baseline.txt", "docker_stats_3x_before.txt")),
    "hot_endpoint_latency_baseline": (
        "THRESHOLD",
        "thresholds",
        ("hot_endpoint_latency_baseline.json", "hot_endpoint_latency_baseline.txt", "hot_endpoint_latency_before.txt"),
    ),
    "repair_provenance_inventory": (
        "PROVENANCE",
        "provenance",
        ("repair_provenance_inventory.json", "repair_provenance_inventory.txt"),
    ),
    "trade_now_repair_provenance_block": (
        "PROVENANCE",
        "provenance",
        ("trade_now_repair_provenance_block.json", "trade_now_1m_before.json", "trade_now_before.json"),
    ),
    "entry_exit_disabled": ("SAFETY", "safety", ("entry_exit_disabled.json", "execution_flags.txt")),
    "promotion_revert_gating": (
        "SAFETY",
        "safety",
        ("promotion_revert_gating.json", "promotion_revert_gating.txt", "promote_revert_requires_confirm.txt"),
    ),
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_first(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_ref(root: Path, artifact_id: str, kind: str, path: Path, captured_at: str) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "path": path.relative_to(root).as_posix(),
        "kind": kind,
        "required": True,
        "sha256": sha256(path),
        "captured_at": captured_at,
    }


def collect_artifacts(root: Path, captured_at: str) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    artifacts: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    used_paths: set[Path] = set()
    for artifact_id, (kind, _group, candidates) in ARTIFACT_CANDIDATES.items():
        path = find_first(root, candidates)
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in used_paths:
            continue
        used_paths.add(resolved)
        paths[artifact_id] = path
        artifacts.append(artifact_ref(root, artifact_id, kind, path, captured_at))
    return artifacts, paths


def parse_env(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            env[key] = value.strip()
    return env


def evidence_root_location(bundle_root: Path) -> str:
    try:
        resolved = bundle_root.resolve()
        host_root = HOST_REPO_ROOT.resolve(strict=False)
    except OSError:
        return "UNKNOWN"
    if resolved == host_root or host_root in resolved.parents:
        return "INSIDE_REPO"
    return "OUTSIDE_REPO"


def parse_repo_identity(text: str, bundle_root: Path) -> dict[str, Any]:
    branch = "unknown"
    dirty = "UNKNOWN"
    commit = "0000000"
    status_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            status_lines.append(line)
            branch = line[3:].split("...", 1)[0].strip() or branch
            dirty = "CLEAN"
        elif re.match(r"^(\?\?|[ MARCUD?!]{1,2})\s+", line):
            status_lines.append(line)
    for line in status_lines:
        if not line.startswith("## "):
            dirty = "DIRTY"
    matches = re.findall(r"\b[a-f0-9]{7,40}\b", text)
    for match in matches:
        if len(match) >= 7:
            commit = match
            break
    return {
        "branch": branch,
        "commit": commit,
        "dirty_status": dirty,
        "captured_by": "operator" if text.strip() else "unknown",
        "evidence_root": evidence_root_location(bundle_root),
    }


def extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_status_payload(text: str) -> dict[str, Any]:
    payload = extract_json_object(text)
    if not payload:
        return {
            "artifact_id": "status_before",
            "schema_name": "strategy_reoptimize_run_status_response",
            "payload_valid": False,
            "status": "FAILED",
            "recommendation_decision": "HOLD",
            "fail_closed_reasons": ["MISSING_TELEMETRY"],
            "budget_state": "UNKNOWN",
        }

    status = payload.get("status")
    recommendation = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    decision = recommendation.get("decision")
    budgets = payload.get("budgets") if isinstance(payload.get("budgets"), dict) else {}
    budget_state = budgets.get("budget_state")
    fail_closed = payload.get("fail_closed_reasons")
    if not isinstance(fail_closed, list):
        fail_closed = []
    bounded_reasons = [reason for reason in fail_closed if isinstance(reason, str) and reason in FAIL_CLOSED_REASONS]
    payload_valid = status in RUN_STATUSES and decision in RECOMMENDATIONS and budget_state in {"WITHIN_BUDGET", "EXHAUSTED", "UNKNOWN"}
    if not payload_valid and "UNKNOWN_STATUS" not in bounded_reasons:
        bounded_reasons.append("UNKNOWN_STATUS")
    return {
        "artifact_id": "status_before",
        "schema_name": "strategy_reoptimize_run_status_response",
        "payload_valid": bool(payload_valid),
        "status": status if status in RUN_STATUSES else "FAILED",
        "recommendation_decision": decision if decision in RECOMMENDATIONS else "HOLD",
        "fail_closed_reasons": sorted(set(bounded_reasons)),
        "budget_state": budget_state if budget_state in {"WITHIN_BUDGET", "EXHAUSTED", "UNKNOWN"} else "UNKNOWN",
    }


def parse_metric_value(text: str, metric: str, label_name: str | None = None, label_value: str | None = None) -> int:
    total = 0
    for line in text.splitlines():
        if not line.startswith(metric):
            continue
        if label_name and label_value and f'{label_name}="{label_value}"' not in line:
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        try:
            total += int(float(parts[1]))
        except ValueError:
            continue
    return total


def parse_metrics(text: str) -> dict[str, Any]:
    active = {
        status: parse_metric_value(text, "strategy_reoptimize_active_runs", "status", status)
        for status in ACTIVE_STATUSES
    }
    return {
        "active_runs_before": active,
        "active_runs_after": dict(active),
        "missing_telemetry_delta": parse_metric_value(text, "strategy_reoptimize_telemetry_missing_total"),
        "status_unknown_delta": parse_metric_value(text, "strategy_reoptimize_status_unknown_total"),
        "budget_exhausted_delta": parse_metric_value(text, "strategy_reoptimize_budget_exhausted_total"),
        "unsafe_promotion_delta": parse_metric_value(
            text,
            "strategy_reoptimize_fail_closed_total",
            "reason",
            "UNSAFE_PROMOTION_ATTEMPT",
        ),
        "repair_provenance_active_delta": parse_metric_value(
            text,
            "strategy_reoptimize_fail_closed_total",
            "reason",
            "REPAIR_PROVENANCE_ACTIVE",
        ),
    }


def parse_alerting(text: str) -> dict[str, Any]:
    payload = extract_json_object(text)
    if (
        isinstance(payload, dict)
        and "rules" in payload
        and {"configured", "routed", "missing_data_blocks", "routing_destination", "dashboard_or_query_path"}
        <= set(payload)
    ):
        payload = dict(payload)
        payload.setdefault("evidence_state", "DEPLOYED" if payload.get("configured") is True else "UNKNOWN")
        payload.setdefault("absence_reason", None if payload.get("configured") is True else "alerting absence reason not captured")
        return payload
    if isinstance(payload, dict) and payload.get("template_only") is True:
        template_rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
        query_present_by_id = {
            rule.get("id"): bool(rule.get("query_template"))
            for rule in template_rules
            if isinstance(rule, dict) and isinstance(rule.get("id"), str)
        }
        return {
            "configured": False,
            "routed": False,
            "missing_data_blocks": False,
            "routing_destination": None,
            "dashboard_or_query_path": None,
            "evidence_state": "TEMPLATE_ONLY",
            "absence_reason": "repo alert template captured, but deployed/routed host alerting was not captured",
            "rules": [
                {
                    "id": rule_id,
                    "configured": False,
                    "routed": False,
                    "query_present": bool(query_present_by_id.get(rule_id)),
                    "before_state_captured": False,
                    "after_state_captured": False,
                }
                for rule_id in sorted(REQUIRED_ALERT_RULES)
            ],
        }
    lower_text = text.lower()
    unavailable = (
        "no alert" in lower_text
        or "no active alert" in lower_text
        or "no deployed" in lower_text
        or "not configured" in lower_text
        or "not provided" in lower_text
        or "missing alert" in lower_text
        or "absent" in lower_text
        or not text.strip()
    )
    absence_reason = "alerting evidence absent" if not text.strip() else text.strip().splitlines()[0][:240]
    return {
        "configured": False,
        "routed": False,
        "missing_data_blocks": False,
        "routing_destination": None,
        "dashboard_or_query_path": None,
        "evidence_state": "ABSENT" if unavailable else "UNKNOWN",
        "absence_reason": absence_reason,
        "rules": [
            {
                "id": rule_id,
                "configured": False,
                "routed": False,
                "query_present": False,
                "before_state_captured": not unavailable and bool(text.strip()),
                "after_state_captured": False,
            }
            for rule_id in sorted(REQUIRED_ALERT_RULES)
        ],
    }


def threshold_placeholder(cpu_text: str, latency_text: str) -> dict[str, Any]:
    has_baseline = bool(cpu_text.strip() or latency_text.strip())
    return {
        "approved_before_canary": False,
        "evidence_state": "BASELINE_ONLY" if has_baseline else "ABSENT",
        "absence_reason": "operator-approved CPU/hot endpoint thresholds were not captured",
        "cpu": {
            "metric_source": "operator evidence missing",
            "query": "operator evidence missing",
            "aggregation_window_seconds": 1,
            "baseline_window_seconds": 1,
            "threshold_type": "ABSOLUTE",
            "threshold_value": 0,
            "baseline_captured": bool(cpu_text.strip()),
            "post_run_captured": False,
            "within_threshold": False,
        },
        "hot_endpoints": [
            {
                "method": "GET",
                "path": "/v1/strategy/pairs/cues",
                "metric_source": "operator evidence missing",
                "query": "operator evidence missing",
                "statistic": "p95",
                "baseline_window_seconds": 1,
                "threshold_type": "ABSOLUTE",
                "threshold_value": 0,
                "baseline_captured": bool(latency_text.strip()),
                "post_run_captured": False,
                "within_threshold": False,
            }
        ],
    }


def valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def missing_required_value(value: Any) -> bool:
    return value is None or value == ""


def parse_threshold_approval(approval_text: str, cpu_text: str, latency_text: str) -> dict[str, Any]:
    thresholds = threshold_placeholder(cpu_text, latency_text)
    payload = extract_json_object(approval_text)
    if not isinstance(payload, dict) or payload.get("approved_before_canary") is not True:
        return thresholds
    approval = payload.get("approval")
    if not isinstance(approval, dict):
        return thresholds
    required_approval = ("reference", "approved_at", "approved_by", "scope", "abort_rule")
    if any(missing_required_value(approval.get(field)) for field in required_approval):
        return thresholds
    if approval.get("host_evidence_owner") != "operator":
        return thresholds

    cpu = payload.get("cpu")
    hot_endpoints = payload.get("hot_endpoints")
    if not isinstance(cpu, dict) or not isinstance(hot_endpoints, list) or not hot_endpoints:
        return thresholds
    cpu_required = (
        "metric_source",
        "query",
        "aggregation_window_seconds",
        "baseline_window_seconds",
        "threshold_type",
        "threshold_value",
    )
    if any(missing_required_value(cpu.get(field)) for field in cpu_required):
        return thresholds
    if cpu.get("threshold_type") not in {"ABSOLUTE", "RELATIVE_INCREASE"}:
        return thresholds
    if not valid_positive_int(cpu.get("aggregation_window_seconds")):
        return thresholds
    if not valid_positive_int(cpu.get("baseline_window_seconds")):
        return thresholds
    if not valid_number(cpu.get("threshold_value")):
        return thresholds

    parsed_hot_endpoints: list[dict[str, Any]] = []
    endpoint_required = (
        "method",
        "path",
        "metric_source",
        "query",
        "statistic",
        "baseline_window_seconds",
        "threshold_type",
        "threshold_value",
    )
    for endpoint in hot_endpoints:
        if not isinstance(endpoint, dict):
            return thresholds
        if any(missing_required_value(endpoint.get(field)) for field in endpoint_required):
            return thresholds
        if endpoint.get("method") not in {"GET", "POST"}:
            return thresholds
        if endpoint.get("statistic") not in {"p95", "p99", "max"}:
            return thresholds
        if endpoint.get("threshold_type") not in {"ABSOLUTE", "RELATIVE_INCREASE"}:
            return thresholds
        if not valid_positive_int(endpoint.get("baseline_window_seconds")):
            return thresholds
        if not valid_number(endpoint.get("threshold_value")):
            return thresholds
        parsed_hot_endpoints.append(
            {
                "method": endpoint["method"],
                "path": endpoint["path"],
                "metric_source": endpoint["metric_source"],
                "query": endpoint["query"],
                "statistic": endpoint["statistic"],
                "baseline_window_seconds": endpoint["baseline_window_seconds"],
                "threshold_type": endpoint["threshold_type"],
                "threshold_value": endpoint["threshold_value"],
                "baseline_captured": bool(latency_text.strip()),
                "post_run_captured": False,
                "within_threshold": bool(latency_text.strip()),
            }
        )

    thresholds["approved_before_canary"] = True
    thresholds["evidence_state"] = "APPROVED"
    thresholds["absence_reason"] = None
    thresholds["cpu"] = {
        "metric_source": cpu["metric_source"],
        "query": cpu["query"],
        "aggregation_window_seconds": cpu["aggregation_window_seconds"],
        "baseline_window_seconds": cpu["baseline_window_seconds"],
        "threshold_type": cpu["threshold_type"],
        "threshold_value": cpu["threshold_value"],
        "baseline_captured": bool(cpu_text.strip()),
        "post_run_captured": False,
        "within_threshold": bool(cpu_text.strip()),
    }
    thresholds["hot_endpoints"] = parsed_hot_endpoints
    return thresholds


def parse_logs(text: str) -> dict[str, Any]:
    events_seen = sorted(event for event in LOG_EVENTS if event in text)
    capture_statement = (
        "SLICE_F_DISABLED_STATE_EVIDENCE" in text
        and "STRATEGY_REOPT_WORKER_ENABLED=false" in text
        and (
            "ACTIVE_ASYNC_GAUGES_ZERO=true" in text
            or "active_async_gauges_zero=true" in text
        )
    )
    disabled = "strategy reoptimize worker disabled" in events_seen or capture_statement
    disabled_source = "NONE"
    if "strategy reoptimize worker disabled" in events_seen:
        disabled_source = "LOG_EVENT"
    elif capture_statement:
        disabled_source = "CAPTURE_STATEMENT"
    return {
        "before_useful": bool(events_seen) or capture_statement,
        "during_useful": False,
        "after_useful": False,
        "disabled_state_evidence": disabled,
        "disabled_state_source": disabled_source,
        "events_seen": events_seen,
    }


def section_contains_confirm_required(section: str) -> bool:
    lower = section.lower()
    return "confirm=true is required" in lower and (
        "400" in lower
        or "bad request" in lower
        or "required to run maintenance actions" in lower
    )


def labeled_text_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"(?im)^\s*(?:=+\s*)?(PROMOTE|REVERT)\b[^\n]*", text))
    for index, match in enumerate(matches):
        label = match.group(1).upper()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[label] = text[match.start():end]
    return sections


def parse_promotion_revert_gating(text: str) -> dict[str, bool]:
    payload = extract_json_object(text)
    sections: dict[str, str] = {}
    if isinstance(payload, dict):
        for label in ("PROMOTE", "REVERT"):
            value = payload.get(label.lower())
            if value is None:
                value = payload.get(label)
            if value is not None:
                sections[label] = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    if not sections:
        sections = labeled_text_sections(text)

    promote_text = sections.get("PROMOTE", "")
    revert_text = sections.get("REVERT", "")
    return {
        "promote_probe_labeled": bool(promote_text),
        "revert_probe_labeled": bool(revert_text),
        "promote_confirm_gated": section_contains_confirm_required(promote_text),
        "revert_confirm_gated": section_contains_confirm_required(revert_text),
    }


def iter_trade_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in ("tradable_now", "watchlist", "excluded"):
        value = payload.get(bucket)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    return rows


def parse_repair_provenance(inventory_text: str, trade_now_text: str) -> dict[str, Any]:
    payload = extract_json_object(trade_now_text) or {}
    rows: list[dict[str, Any]] = []
    for row in iter_trade_rows(payload):
        if row.get("selected_config_source") != "RECANONICALIZED_LEGACY_ROW":
            continue
        rows.append(
            {
                "pair_id": str(row.get("pair_id") or "unknown"),
                "timeframe": row.get("timeframe") if row.get("timeframe") in {"1m", "15m", "1h"} else "1m",
                "selected_config_source": "RECANONICALIZED_LEGACY_ROW",
                "decision_bucket": row.get("decision_bucket") if row.get("decision_bucket") in {"EXCLUDED", "WATCHLIST", "TRADE_NOW"} else "TRADE_NOW",
                "decision_reason_code": str(row.get("decision_reason_code") or ""),
                "blocked_reason_code": row.get("blocked_reason_code") if row.get("blocked_reason_code") is None or isinstance(row.get("blocked_reason_code"), str) else None,
                "rationale_codes": [
                    code for code in row.get("rationale_codes", []) if isinstance(code, str)
                ],
                "live_trade_eligible": bool(row.get("decision_bucket") == "TRADE_NOW" or row.get("open_live_trade")),
                "graduated_to_non_repair_source": row.get("selected_config_source") != "RECANONICALIZED_LEGACY_ROW",
            }
        )
    all_blocked = bool(inventory_text.strip()) and bool(trade_now_text.strip())
    for row in rows:
        if row["decision_bucket"] != "EXCLUDED":
            all_blocked = False
        if row["decision_reason_code"] != "PROVENANCE_POLICY_BLOCKED":
            all_blocked = False
        if row["blocked_reason_code"] != "RECANONICALIZED_LEGACY_ROW_ACTIVE":
            all_blocked = False
        if "RECANONICALIZED_LEGACY_ROW_ACTIVE" not in row["rationale_codes"]:
            all_blocked = False
        if row["live_trade_eligible"] is not False:
            all_blocked = False
    return {
        "inventory_captured": bool(inventory_text.strip()),
        "all_recanonicalized_rows_blocked": all_blocked,
        "recanonicalized_rows_audited": len(rows),
        "rows": rows,
    }


def status_check_pass(status_payload: dict[str, Any]) -> bool:
    return (
        status_payload.get("payload_valid") is True
        and status_payload.get("status") == "SUCCEEDED"
        and not status_payload.get("fail_closed_reasons")
        and status_payload.get("budget_state") == "WITHIN_BUDGET"
    )


def check(status: str, evidence: list[str], failure: str | None = None) -> dict[str, Any]:
    return {
        "id": "",
        "status": status,
        "evidence_artifact_ids": evidence,
        "failure_reason": failure,
    }


def named_check(check_id: str, status: str, evidence: list[str], failure: str | None = None) -> dict[str, Any]:
    item = check(status, evidence, failure)
    item["id"] = check_id
    return item


def add_stop(stops: set[str], condition: str) -> None:
    stops.add(condition)


def build_manifest(bundle_root: Path, generated_at: str, bundle_id: str) -> dict[str, Any]:
    artifacts, paths = collect_artifacts(bundle_root, generated_at)
    artifact_set = {artifact["id"] for artifact in artifacts}
    text = {artifact_id: read_text(path) for artifact_id, path in paths.items()}

    repo = parse_repo_identity(text.get("repo_identity", ""), bundle_root)
    runner_env = parse_env(text.get("runner_flags_before", ""))
    status_payload = parse_status_payload(text.get("status_before", ""))
    metrics = parse_metrics(text.get("metrics_before", ""))
    alerting = parse_alerting(text.get("alerts_config", "") + "\n" + text.get("alerts_before", ""))
    thresholds = parse_threshold_approval(
        text.get("threshold_approval", ""),
        text.get("cpu_baseline", ""),
        text.get("hot_endpoint_latency_baseline", ""),
    )
    logs = parse_logs(text.get("strategy_logs_before", ""))
    execution_env = parse_env(text.get("entry_exit_disabled", ""))
    gating_text = text.get("promotion_revert_gating", "")
    repair = parse_repair_provenance(
        text.get("repair_provenance_inventory", ""),
        text.get("trade_now_repair_provenance_block", ""),
    )

    runner_enabled = runner_env.get("STRATEGY_REOPT_WORKER_ENABLED", "").lower() == "true"
    scheduler_value = runner_env.get("STRATEGY_REOPT_SCHEDULER_ENABLED") or runner_env.get("STRATEGY_REOPT_SCHEDULE_ENABLED")
    scheduler_enabled = str(scheduler_value).lower() == "true"
    budget_missing = sorted(REQUIRED_BUDGET_ENV - set(runner_env))
    scheduler_missing = scheduler_value is None

    live_disabled = execution_env.get("EXECUTION_DISPATCH_MODE") == "fail_closed"
    gating = parse_promotion_revert_gating(gating_text)
    promote_confirm = gating["promote_confirm_gated"]
    revert_confirm = gating["revert_confirm_gated"]

    alert_ready = (
        alerting.get("configured") is True
        and alerting.get("routed") is True
        and alerting.get("missing_data_blocks") is True
        and {rule.get("id") for rule in alerting.get("rules", []) if isinstance(rule, dict)} == REQUIRED_ALERT_RULES
        and all(
            isinstance(rule, dict)
            and rule.get("configured") is True
            and rule.get("routed") is True
            and rule.get("query_present") is True
            and rule.get("before_state_captured") is True
            for rule in alerting.get("rules", [])
        )
    )
    thresholds_ready = thresholds.get("approved_before_canary") is True
    status_ready = status_check_pass(status_payload)
    active_zero = sum(int(metrics["active_runs_before"].get(status, 0)) for status in ACTIVE_STATUSES) == 0
    metrics_zero_delta = all(
        int(metrics.get(field, 0)) == 0
        for field in (
            "missing_telemetry_delta",
            "status_unknown_delta",
            "budget_exhausted_delta",
            "unsafe_promotion_delta",
            "repair_provenance_active_delta",
        )
    )

    stops: set[str] = set()
    required_artifacts = {
        "repo_identity",
        "runner_flags_before",
        "status_before",
        "metrics_before",
        "alerts_config",
        "alerts_before",
        "strategy_logs_before",
        "threshold_approval",
        "cpu_baseline",
        "hot_endpoint_latency_baseline",
        "repair_provenance_inventory",
        "trade_now_repair_provenance_block",
        "entry_exit_disabled",
        "promotion_revert_gating",
    }
    if required_artifacts - artifact_set or budget_missing or scheduler_missing:
        add_stop(stops, "MANIFEST_INVALID")
    if (
        repo.get("captured_by") != "operator"
        or repo.get("dirty_status") != "CLEAN"
        or repo.get("evidence_root") != "OUTSIDE_REPO"
    ):
        add_stop(stops, "HOST_IDENTITY_UNKNOWN")
    if not alert_ready:
        add_stop(stops, "ALERTING_NOT_READY")
    if not thresholds_ready:
        add_stop(stops, "THRESHOLDS_NOT_APPROVED")
    if not logs.get("before_useful") or not logs.get("disabled_state_evidence"):
        add_stop(stops, "WEAK_STRATEGY_LOGS")
    if not status_ready:
        add_stop(stops, "STATUS_INVALID_OR_UNKNOWN")
    if status_payload.get("budget_state") in {"UNKNOWN", "EXHAUSTED"} or int(metrics.get("budget_exhausted_delta", 0)) != 0:
        add_stop(stops, "BUDGET_UNKNOWN_OR_EXHAUSTED")
    if int(metrics.get("missing_telemetry_delta", 0)) != 0:
        add_stop(stops, "MISSING_TELEMETRY")
    if int(metrics.get("status_unknown_delta", 0)) != 0 or "UNKNOWN_STATUS" in status_payload.get("fail_closed_reasons", []):
        add_stop(stops, "UNKNOWN_STATUS")
    if not active_zero:
        add_stop(stops, "ACTIVE_RUN_BEFORE_APPROVAL")
    if runner_enabled or scheduler_enabled:
        add_stop(stops, "MANIFEST_INVALID")
    if not live_disabled:
        add_stop(stops, "ENTRY_EXIT_NOT_DISABLED")
    if not promote_confirm or not revert_confirm:
        add_stop(stops, "PROMOTE_REVERT_NOT_CONFIRM_GATED")
    if not repair.get("inventory_captured") or not repair.get("all_recanonicalized_rows_blocked"):
        add_stop(stops, "REPAIR_PROVENANCE_NOT_BLOCKED")
    if int(metrics.get("repair_provenance_active_delta", 0)) != 0:
        add_stop(stops, "REPAIR_PROVENANCE_NOT_BLOCKED")

    checks = [
        named_check("operator_approval_present", "NOT_APPLICABLE", []),
        named_check(
            "alerting_ready",
            "PASS" if alert_ready else "FAIL",
            [artifact_id for artifact_id in ("alerts_config", "alerts_before") if artifact_id in artifact_set],
            None if alert_ready else "alerting config/routing/active state evidence is missing or incomplete",
        ),
        named_check(
            "thresholds_approved",
            "PASS" if thresholds_ready else "FAIL",
            [
                artifact_id
                for artifact_id in ("threshold_approval", "cpu_baseline", "hot_endpoint_latency_baseline")
                if artifact_id in artifact_set
            ],
            None if thresholds_ready else "operator-approved CPU/hot endpoint thresholds are missing",
        ),
        named_check(
            "strategy_logs_useful",
            "PASS" if logs.get("before_useful") and logs.get("disabled_state_evidence") else "FAIL",
            ["strategy_logs_before"] if "strategy_logs_before" in artifact_set else [],
            None if logs.get("before_useful") and logs.get("disabled_state_evidence") else "strategy_logs_before is empty or lacks disabled-state evidence",
        ),
        named_check(
            "status_contract_valid",
            "PASS" if status_ready else "FAIL",
            ["status_before"] if "status_before" in artifact_set else [],
            None if status_ready else "status payload is missing, unknown, non-success, or fail-closed",
        ),
        named_check(
            "metrics_bounded_and_present",
            "PASS" if "metrics_before" in artifact_set and metrics_zero_delta else "FAIL",
            ["metrics_before"] if "metrics_before" in artifact_set else [],
            None if "metrics_before" in artifact_set and metrics_zero_delta else "metrics are missing or contain fail-closed deltas",
        ),
        named_check(
            "active_async_gauges_zero_before",
            "PASS" if active_zero else "FAIL",
            ["metrics_before"] if "metrics_before" in artifact_set else [],
            None if active_zero else "active async gauges were nonzero before approval",
        ),
        named_check(
            "status_progression_known",
            "PASS" if status_ready else "FAIL",
            ["status_before"] if "status_before" in artifact_set else [],
            None if status_ready else "status progression is not known-good",
        ),
        named_check(
            "recommendation_safe",
            "PASS" if status_payload.get("recommendation_decision") in {"HOLD", "OPERATOR_REVIEW_REQUIRED"} else "FAIL",
            ["status_before"] if "status_before" in artifact_set else [],
            None if status_payload.get("recommendation_decision") in {"HOLD", "OPERATOR_REVIEW_REQUIRED"} else "recommendation was not evidence-only safe",
        ),
        named_check(
            "entry_exit_disabled",
            "PASS" if live_disabled else "FAIL",
            ["entry_exit_disabled"] if "entry_exit_disabled" in artifact_set else [],
            None if live_disabled else "live ENTRY/EXIT disabled evidence missing",
        ),
        named_check(
            "promotion_revert_confirm_gated",
            "PASS" if promote_confirm and revert_confirm else "FAIL",
            ["promotion_revert_gating"] if "promotion_revert_gating" in artifact_set else [],
            None if promote_confirm and revert_confirm else "PROMOTE and REVERT probes must be labeled separately and each show confirm=true rejection",
        ),
        named_check(
            "repair_provenance_blocked",
            "PASS" if repair.get("inventory_captured") and repair.get("all_recanonicalized_rows_blocked") else "FAIL",
            [
                artifact_id
                for artifact_id in ("repair_provenance_inventory", "trade_now_repair_provenance_block")
                if artifact_id in artifact_set
            ],
            None if repair.get("inventory_captured") and repair.get("all_recanonicalized_rows_blocked") else "repair provenance block evidence missing or unsafe",
        ),
        named_check(
            "cpu_within_threshold",
            "NOT_APPLICABLE",
            ["cpu_baseline"] if "cpu_baseline" in artifact_set else [],
            None,
        ),
        named_check(
            "hot_endpoint_latency_within_threshold",
            "NOT_APPLICABLE",
            ["hot_endpoint_latency_baseline"] if "hot_endpoint_latency_baseline" in artifact_set else [],
            None,
        ),
        named_check("artifact_evidence_valid", "NOT_APPLICABLE", [], None),
        named_check(
            "stop_conditions_absent",
            "PASS" if not stops else "FAIL",
            [],
            None if not stops else "one or more Slice F stop conditions are present",
        ),
    ]

    overall_pass = not stops and all(item["status"] in {"PASS", "NOT_APPLICABLE"} for item in checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "bundle_id": bundle_id,
        "canary_authorized": False,
        "overall_pass": overall_pass,
        "recommended_action": "READY_FOR_OPERATOR_REVIEW" if overall_pass else "KEEP_DISABLED_KEEP_HOLD",
        "operator_approval": {
            "present": False,
            "reference": None,
            "approved_at": None,
            "approved_by": None,
            "scope": None,
            "abort_owner": None,
            "rollback_owner": None,
            "host_evidence_owner": "operator",
        },
        "repo_identity": repo,
        "canary_scope": {
            "timeframes": [],
            "trigger_source": None,
            "runner_enabled_before": runner_enabled,
            "scheduler_enabled_before": scheduler_enabled,
            "runner_enabled_after": runner_enabled,
            "scheduler_enabled_after": scheduler_enabled,
        },
        "alerting": alerting,
        "thresholds": thresholds,
        "logs": logs,
        "status_payloads": [status_payload],
        "metrics": metrics,
        "safety": {
            "live_entry_enabled": not live_disabled,
            "live_exit_enabled": not live_disabled,
            "automatic_promote_enabled": False,
            "automatic_revert_enabled": False,
            "promote_confirm_gated": promote_confirm,
            "revert_confirm_gated": revert_confirm,
            "promote_probe_labeled": gating["promote_probe_labeled"],
            "revert_probe_labeled": gating["revert_probe_labeled"],
        },
        "repair_provenance": repair,
        "artifacts": artifacts,
        "checks": checks,
        "stop_conditions": sorted(stops),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_root", help="Operator-provided raw evidence bundle directory")
    parser.add_argument("--output", default=None, help="Output manifest path; defaults to <bundle_root>/slice_f_manifest.json")
    parser.add_argument("--bundle-id", default=None, help="Manifest bundle_id; defaults to bundle directory name")
    parser.add_argument("--generated-at", default=None, help="RFC3339 UTC timestamp; defaults to current UTC")
    args = parser.parse_args()

    bundle_root = Path(args.bundle_root).resolve()
    if not bundle_root.exists() or not bundle_root.is_dir():
        print(json.dumps({"pass": False, "error": "bundle_root must be an existing directory"}), file=sys.stderr)
        return 2
    generated_at = args.generated_at or now_utc()
    bundle_id = args.bundle_id or re.sub(r"[^A-Za-z0-9._:-]", "_", bundle_root.name or "slice-f-bundle")
    output = Path(args.output).resolve() if args.output else bundle_root / "slice_f_manifest.json"

    manifest = build_manifest(bundle_root, generated_at, bundle_id)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    report = {
        "manifest": str(output),
        "bundle_id": manifest["bundle_id"],
        "overall_pass": manifest["overall_pass"],
        "recommended_action": manifest["recommended_action"],
        "stop_conditions": manifest["stop_conditions"],
        "host_verification_claimed_by_agent": False,
    }
    print(json.dumps(report, indent=2))
    return 0 if manifest["overall_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
