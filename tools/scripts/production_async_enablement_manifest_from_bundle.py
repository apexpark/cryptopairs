#!/usr/bin/env python3
"""Build production async enablement evidence from an operator raw bundle.

The script only reads files already captured by the operator. It does not SSH,
does not query services, and emits fail-closed evidence when required inputs
are absent or contradictory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from production_async_enablement_evidence_check import REQUIRED_ALERT_RULES, validate_manifest
from slice_f_evidence_manifest_from_bundle import (
    ACTIVE_STATUSES,
    artifact_ref,
    extract_json_object,
    first_env_value,
    now_utc,
    parse_env,
    parse_metric_value,
    parse_promotion_revert_gating,
    parse_repair_provenance,
    parse_repo_identity,
    parse_status_payload,
    parse_threshold_approval,
    read_text,
)


SCHEMA_VERSION = "1.0.0"
SCHEDULER_ENABLE_ENV_KEYS = (
    "STRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED",
    "STRATEGY_REOPT_SCHEDULER_ENABLED",
    "STRATEGY_REOPT_SCHEDULE_ENABLED",
)
ARTIFACT_CANDIDATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "repo_identity": ("JSON", ("repo_identity.json", "host_identity.json", "host_identity.txt")),
    "operator_approval": ("JSON", ("operator_approval.json", "production_async_approval.json")),
    "runner_flags_before": ("JSON", ("runner_flags_before.json", "runner_flags_before.txt")),
    "runner_flags_during": ("JSON", ("runner_flags_during.json", "runner_flags_during.txt")),
    "runner_flags_after": ("JSON", ("runner_flags_after.json", "runner_flags_after.txt")),
    "budget_values": ("JSON", ("budget_values.json", "budget_values.txt", "runner_flags_during.txt")),
    "status_progression": ("STATUS", ("status_progression.json", "status_progression.txt")),
    "status_after": ("STATUS", ("status_after.json", "status_after.txt")),
    "metrics_before": ("METRICS", ("metrics_before.prom", "metrics_before.txt")),
    "metrics_during": ("METRICS", ("metrics_during.prom", "metrics_during.txt")),
    "metrics_after": ("METRICS", ("metrics_after.prom", "metrics_after.txt")),
    "alerts_config": ("ALERTS", ("alerts_config.json", "alerts_config.txt")),
    "alerts_before": ("ALERTS", ("alerts_before.json", "alerts_before.txt")),
    "alerts_during": ("ALERTS", ("alerts_during.json", "alerts_during.txt")),
    "alerts_after": ("ALERTS", ("alerts_after.json", "alerts_after.txt")),
    "strategy_logs_before": ("LOG", ("strategy_logs_before.log", "strategy_logs_before.txt")),
    "strategy_logs_during": ("LOG", ("strategy_logs_during.log", "strategy_logs_during.txt")),
    "strategy_logs_after": ("LOG", ("strategy_logs_after.log", "strategy_logs_after.txt")),
    "threshold_approval": ("THRESHOLD", ("threshold_approval.json", "threshold_approval.txt")),
    "cpu_baseline": ("THRESHOLD", ("cpu_baseline.json", "cpu_baseline.txt")),
    "cpu_during_after": ("THRESHOLD", ("cpu_during_after.json", "cpu_during_after.txt")),
    "hot_endpoint_latency_baseline": ("THRESHOLD", ("hot_endpoint_latency_baseline.json", "hot_endpoint_latency_baseline.txt")),
    "hot_endpoint_latency_after": ("THRESHOLD", ("hot_endpoint_latency_after.json", "hot_endpoint_latency_after.txt")),
    "artifact_manifest": ("JSON", ("artifact_manifest.json", "strategy_reoptimize_run_artifact_manifest.json")),
    "repair_provenance_inventory": ("PROVENANCE", ("repair_provenance_inventory.json", "repair_provenance_inventory.txt")),
    "trade_now_repair_provenance_block": ("PROVENANCE", ("trade_now_repair_provenance_block.json", "trade_now_before.json")),
    "entry_exit_disabled": ("SAFETY", ("entry_exit_disabled.json", "execution_flags.txt")),
    "promotion_revert_gating": ("SAFETY", ("promotion_revert_gating.json", "promotion_revert_gating.txt")),
}
LOG_EVENTS = {
    "reoptimize_run_enqueue_attempted",
    "reoptimize_run_enqueued",
    "reoptimize_lease_acquired",
    "reoptimize_lease_heartbeat",
    "reoptimize_recommendation_finalized",
    "reoptimize_fail_closed",
}


def find_first(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


def collect_artifacts(root: Path, captured_at: str) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    artifacts: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    used: set[Path] = set()
    for artifact_id, (kind, candidates) in ARTIFACT_CANDIDATES.items():
        path = find_first(root, candidates)
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in used:
            continue
        used.add(resolved)
        paths[artifact_id] = path
        artifacts.append(artifact_ref(root, artifact_id, kind, path, captured_at))
    return artifacts, paths


def parse_bool_env(env: dict[str, str], key: str) -> bool:
    return env.get(key, "").lower() == "true"


def scheduler_enabled(env: dict[str, str]) -> bool:
    return str(first_env_value(env, SCHEDULER_ENABLE_ENV_KEYS) or "").lower() == "true"


def parse_approval(text: str) -> dict[str, Any]:
    payload = extract_json_object(text) or {}
    timeframes = payload.get("approved_timeframes")
    if not isinstance(timeframes, list):
        timeframes = payload.get("timeframes")
    return {
        "present": bool(payload.get("present", bool(payload))),
        "reference": payload.get("reference"),
        "approved_at": payload.get("approved_at"),
        "approved_by": payload.get("approved_by"),
        "scope": payload.get("scope"),
        "approved_timeframes": [tf for tf in (timeframes or []) if tf in {"1m", "15m", "1h"}],
        "expected_scheduled_run_count": int(payload.get("expected_scheduled_run_count", 0) or 0),
        "scheduler_window_start": payload.get("scheduler_window_start"),
        "scheduler_window_end": payload.get("scheduler_window_end"),
        "abort_owner": payload.get("abort_owner"),
        "rollback_owner": payload.get("rollback_owner"),
        "host_evidence_owner": payload.get("host_evidence_owner", "unknown"),
    }


def parse_progression(text: str) -> list[str]:
    payload = extract_json_object(text)
    if isinstance(payload, dict):
        values = payload.get("progression") or payload.get("statuses") or []
    else:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = []
        values = raw if isinstance(raw, list) else []
    statuses = {"QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED", "CANCELED", "SUCCEEDED", "DEGRADED", "FAILED", "EXPIRED"}
    parsed = [value for value in values if isinstance(value, str) and value in statuses]
    if parsed:
        return parsed
    return [status for status in statuses if status in text]


def parse_artifact_manifest(text: str) -> dict[str, Any]:
    payload = extract_json_object(text) or {}
    timeframes = payload.get("requested_timeframes")
    return {
        "present": bool(payload),
        "valid": bool(
            payload
            and payload.get("schema_version") == "1.0.0"
            and payload.get("complete") is True
            and payload.get("status") == "SUCCEEDED"
            and payload.get("trigger_source") == "SCHEDULED"
            and isinstance(timeframes, list)
        ),
        "trigger_source": payload.get("trigger_source") if payload else None,
        "requested_timeframes": [tf for tf in (timeframes or []) if tf in {"1m", "15m", "1h"}],
    }


def parse_status_evidence(status_text: str, progression_text: str, artifact_text: str) -> dict[str, Any]:
    status = parse_status_payload(status_text)
    artifact = parse_artifact_manifest(artifact_text)
    return {
        "payload_valid": status["payload_valid"],
        "final_status": status["status"],
        "recommendation_decision": status["recommendation_decision"],
        "budget_state": status["budget_state"],
        "fail_closed_reasons": status["fail_closed_reasons"],
        "progression": parse_progression(progression_text) or [status["status"]],
        "scheduled_run_count": 1 if artifact["trigger_source"] == "SCHEDULED" else 0,
        "manual_run_count": 1 if artifact["trigger_source"] == "MANUAL_API" else 0,
        "artifact_manifest_present": artifact["present"],
        "artifact_manifest_valid": artifact["valid"],
        "artifact_trigger_source": artifact["trigger_source"],
        "artifact_requested_timeframes": artifact["requested_timeframes"],
    }


def active_counts(text: str) -> dict[str, int]:
    return {
        status: parse_metric_value(text, "strategy_reoptimize_active_runs", "status", status)
        for status in ACTIVE_STATUSES
    }


def parse_metrics(before: str, during: str, after: str) -> dict[str, Any]:
    return {
        "active_runs_before": active_counts(before),
        "active_runs_during_peak": active_counts(during),
        "active_runs_after": active_counts(after),
        "scheduler_enqueued_delta": parse_metric_value(after, "strategy_reoptimize_scheduler_enqueue_total", "trigger", "SCHEDULED")
        - parse_metric_value(before, "strategy_reoptimize_scheduler_enqueue_total", "trigger", "SCHEDULED"),
        "manual_enqueued_delta": parse_metric_value(after, "strategy_reoptimize_scheduler_enqueue_total", "trigger", "MANUAL_API")
        - parse_metric_value(before, "strategy_reoptimize_scheduler_enqueue_total", "trigger", "MANUAL_API"),
        "missing_telemetry_delta": parse_metric_value(after, "strategy_reoptimize_telemetry_missing_total")
        - parse_metric_value(before, "strategy_reoptimize_telemetry_missing_total"),
        "status_unknown_delta": parse_metric_value(after, "strategy_reoptimize_status_unknown_total")
        - parse_metric_value(before, "strategy_reoptimize_status_unknown_total"),
        "budget_exhausted_delta": parse_metric_value(after, "strategy_reoptimize_budget_exhausted_total")
        - parse_metric_value(before, "strategy_reoptimize_budget_exhausted_total"),
        "unsafe_promotion_delta": parse_metric_value(after, "strategy_reoptimize_fail_closed_total", "reason", "UNSAFE_PROMOTION_ATTEMPT")
        - parse_metric_value(before, "strategy_reoptimize_fail_closed_total", "reason", "UNSAFE_PROMOTION_ATTEMPT"),
        "repair_provenance_active_delta": parse_metric_value(after, "strategy_reoptimize_fail_closed_total", "reason", "REPAIR_PROVENANCE_ACTIVE")
        - parse_metric_value(before, "strategy_reoptimize_fail_closed_total", "reason", "REPAIR_PROVENANCE_ACTIVE"),
    }


def parse_alerting(text: str) -> dict[str, Any]:
    payload = extract_json_object(text) or {}
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    normalized = []
    for rule_id in sorted(REQUIRED_ALERT_RULES):
        source = next((rule for rule in rules if isinstance(rule, dict) and rule.get("id") == rule_id), {})
        normalized.append(
            {
                "id": rule_id,
                "configured": bool(source.get("configured")),
                "routed": bool(source.get("routed")),
                "query_present": bool(source.get("query_present")),
                "before_state_captured": bool(source.get("before_state_captured")),
                "during_state_captured": bool(source.get("during_state_captured")),
                "after_state_captured": bool(source.get("after_state_captured")),
            }
        )
    return {
        "configured": bool(payload.get("configured")),
        "routed": bool(payload.get("routed")),
        "missing_data_blocks": bool(payload.get("missing_data_blocks")),
        "evidence_state": payload.get("evidence_state", "UNKNOWN"),
        "rules": normalized,
    }


def logs_useful(text: str) -> tuple[bool, set[str]]:
    events = {event for event in LOG_EVENTS if event in text}
    return bool(events), events


def parse_logs(before: str, during: str, after: str) -> dict[str, Any]:
    before_useful, before_events = logs_useful(before)
    during_useful, during_events = logs_useful(during)
    after_useful, after_events = logs_useful(after)
    return {
        "before_useful": before_useful,
        "during_useful": during_useful,
        "after_useful": after_useful,
        "events_seen": sorted(before_events | during_events | after_events),
    }


def parse_thresholds(approval_text: str, cpu_before: str, latency_before: str, cpu_after: str, latency_after: str) -> dict[str, Any]:
    approval = parse_threshold_approval(approval_text, cpu_before, latency_before)
    cpu = approval.get("cpu") if isinstance(approval.get("cpu"), dict) else {}
    endpoints = approval.get("hot_endpoints") if isinstance(approval.get("hot_endpoints"), list) else []
    return {
        "approved_before_window": approval.get("approved_before_canary") is True,
        "cpu": {
            "baseline_captured": cpu.get("baseline_captured") is True,
            "during_after_captured": bool(cpu_after.strip()),
            "within_threshold": "THRESHOLD_BREACH" not in cpu_after,
        },
        "hot_endpoints": [
            {
                "method": endpoint.get("method", "GET"),
                "path": endpoint.get("path", "unknown"),
                "baseline_captured": endpoint.get("baseline_captured") is True,
                "during_after_captured": bool(latency_after.strip()),
                "within_threshold": "THRESHOLD_BREACH" not in latency_after,
            }
            for endpoint in endpoints
            if isinstance(endpoint, dict)
        ],
    }


def build_manifest(bundle_root: Path, generated_at: str, bundle_id: str) -> dict[str, Any]:
    artifacts, paths = collect_artifacts(bundle_root, generated_at)
    text = {artifact_id: read_text(path) for artifact_id, path in paths.items()}

    before_env = parse_env(text.get("runner_flags_before", ""))
    during_env = parse_env(text.get("runner_flags_during", ""))
    after_env = parse_env(text.get("runner_flags_after", ""))
    approval = parse_approval(text.get("operator_approval", ""))
    artifact_manifest = text.get("artifact_manifest", "")
    artifact_scope = parse_artifact_manifest(artifact_manifest)

    gating = parse_promotion_revert_gating(text.get("promotion_revert_gating", ""))
    execution_env = parse_env(text.get("entry_exit_disabled", ""))
    repair = parse_repair_provenance(
        text.get("repair_provenance_inventory", ""),
        text.get("trade_now_repair_provenance_block", ""),
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "bundle_id": bundle_id,
        "overall_pass": False,
        "recommended_action": "KEEP_DISABLED_KEEP_HOLD",
        "operator_approval": approval,
        "repo_identity": parse_repo_identity(text.get("repo_identity", ""), bundle_root),
        "enablement_scope": {
            "trigger_source": "SCHEDULED",
            "requested_timeframes": artifact_scope["requested_timeframes"] or approval["approved_timeframes"],
            "expected_scheduled_run_count": approval["expected_scheduled_run_count"],
            "worker_enabled_before": parse_bool_env(before_env, "STRATEGY_REOPT_WORKER_ENABLED"),
            "scheduler_enabled_before": scheduler_enabled(before_env),
            "worker_enabled_during": parse_bool_env(during_env, "STRATEGY_REOPT_WORKER_ENABLED"),
            "scheduler_enabled_during": scheduler_enabled(during_env),
            "worker_enabled_after": parse_bool_env(after_env, "STRATEGY_REOPT_WORKER_ENABLED"),
            "scheduler_enabled_after": scheduler_enabled(after_env),
        },
        "status_evidence": parse_status_evidence(
            text.get("status_after", ""),
            text.get("status_progression", ""),
            artifact_manifest,
        ),
        "metrics": parse_metrics(
            text.get("metrics_before", ""),
            text.get("metrics_during", ""),
            text.get("metrics_after", ""),
        ),
        "alerting": parse_alerting(
            "\n".join(
                [
                    text.get("alerts_config", ""),
                    text.get("alerts_before", ""),
                    text.get("alerts_during", ""),
                    text.get("alerts_after", ""),
                ]
            )
        ),
        "thresholds": parse_thresholds(
            text.get("threshold_approval", ""),
            text.get("cpu_baseline", ""),
            text.get("hot_endpoint_latency_baseline", ""),
            text.get("cpu_during_after", ""),
            text.get("hot_endpoint_latency_after", ""),
        ),
        "logs": parse_logs(
            text.get("strategy_logs_before", ""),
            text.get("strategy_logs_during", ""),
            text.get("strategy_logs_after", ""),
        ),
        "safety": {
            "live_entry_enabled": execution_env.get("EXECUTION_DISPATCH_MODE") != "fail_closed",
            "live_exit_enabled": execution_env.get("EXECUTION_DISPATCH_MODE") != "fail_closed",
            "automatic_promote_enabled": False,
            "automatic_revert_enabled": False,
            "promote_confirm_gated": gating.get("promote_confirm_gated") is True,
            "revert_confirm_gated": gating.get("revert_confirm_gated") is True,
            "repair_provenance_blocked": repair.get("inventory_captured") is True and repair.get("all_recanonicalized_rows_blocked") is True,
        },
        "artifacts": artifacts,
        "stop_conditions": [],
    }
    errors = validate_manifest({**manifest, "overall_pass": True, "recommended_action": "READY_FOR_OPERATOR_REVIEW"})
    if not errors:
        manifest["overall_pass"] = True
        manifest["recommended_action"] = "READY_FOR_OPERATOR_REVIEW"
    else:
        manifest["stop_conditions"] = ["MANIFEST_INVALID"]
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_root", help="Operator-captured production async enablement raw bundle")
    parser.add_argument("--output", "--output-json", dest="output", default=None, help="Output manifest path")
    args = parser.parse_args()

    root = Path(args.bundle_root)
    if not root.exists() or not root.is_dir():
        print(f"bundle root not found or not a directory: {root}", file=sys.stderr)
        return 1

    manifest = build_manifest(root, now_utc(), root.name)
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if manifest["overall_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
