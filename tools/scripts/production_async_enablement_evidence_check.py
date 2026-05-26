#!/usr/bin/env python3
"""Validate production async reoptimization enablement evidence.

The schema checks shape. This script checks the safety semantics for a
separately approved scheduler-enabled window. It validates only local
operator-provided evidence and never connects to a host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from slice_f_evidence_check import REQUIRED_ALERT_RULES


SCHEMA_VERSION = "1.0.0"
REQUIRED_ARTIFACTS = {
    "repo_identity",
    "operator_approval",
    "runner_flags_before",
    "runner_flags_during",
    "runner_flags_after",
    "budget_values",
    "status_progression",
    "status_after",
    "metrics_before",
    "metrics_during",
    "metrics_after",
    "alerts_config",
    "alerts_before",
    "alerts_during",
    "alerts_after",
    "strategy_logs_before",
    "strategy_logs_during",
    "strategy_logs_after",
    "threshold_approval",
    "cpu_baseline",
    "cpu_during_after",
    "hot_endpoint_latency_baseline",
    "hot_endpoint_latency_after",
    "artifact_manifest",
    "repair_provenance_inventory",
    "trade_now_repair_provenance_block",
    "entry_exit_disabled",
    "promotion_revert_gating",
}
BLOCKING_DELTAS = (
    "missing_telemetry_delta",
    "status_unknown_delta",
    "budget_exhausted_delta",
    "unsafe_promotion_delta",
    "repair_provenance_active_delta",
)
REQUIRED_LOG_EVENTS = {
    "reoptimize_run_enqueued",
    "reoptimize_lease_acquired",
    "reoptimize_recommendation_finalized",
}
SAFE_SUCCESS_RECOMMENDATIONS = {
    "HOLD",
    "OPERATOR_REVIEW_REQUIRED",
    "PROMOTION_CANDIDATE_AVAILABLE",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("manifest root must be an object")
    return value


def artifact_ids(manifest: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for artifact in manifest.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("id"), str):
            ids.add(artifact["id"])
    return ids


def active_count_total(counts: dict[str, Any]) -> int:
    return sum(int(counts.get(status, 0)) for status in ("QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED"))


def sorted_unique(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(item for item in value if isinstance(item, str))


def verify_artifact_files(manifest: dict[str, Any], bundle_root: Path, errors: list[str]) -> None:
    for artifact in manifest.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        artifact_id = artifact.get("id", "<unknown>")
        path_value = artifact.get("path")
        expected_sha = artifact.get("sha256")
        if not isinstance(path_value, str) or not isinstance(expected_sha, str):
            errors.append(f"artifact {artifact_id}: path or sha256 missing")
            continue
        artifact_path = bundle_root / path_value
        try:
            resolved = artifact_path.resolve()
            root = bundle_root.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            errors.append(f"artifact {artifact_id}: invalid path {path_value}: {error}")
            continue
        if not resolved.exists():
            errors.append(f"artifact {artifact_id}: file missing at {path_value}")
            continue
        try:
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as error:
            errors.append(f"artifact {artifact_id}: cannot read file at {path_value}: {error}")
            continue
        if digest != expected_sha:
            errors.append(f"artifact {artifact_id}: sha256 mismatch")


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    artifacts = artifact_ids(manifest)
    for artifact_id in sorted(REQUIRED_ARTIFACTS - artifacts):
        errors.append(f"required artifact missing: {artifact_id}")
    for artifact in manifest.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("id") in REQUIRED_ARTIFACTS and artifact.get("required") is not True:
            errors.append(f"required artifact {artifact.get('id')} must be marked required")

    repo = manifest.get("repo_identity", {})
    if not isinstance(repo, dict):
        errors.append("repo_identity missing")
    else:
        if repo.get("captured_by") != "operator":
            errors.append("host/repo identity must be operator-captured")
        if repo.get("dirty_status") != "CLEAN":
            errors.append("host/repo dirty status must be CLEAN")
        if repo.get("evidence_root") != "OUTSIDE_REPO":
            errors.append("host evidence bundle must be captured outside /opt/cryptopairs")

    approval = manifest.get("operator_approval", {})
    if not isinstance(approval, dict) or approval.get("present") is not True:
        errors.append("production enablement approval is missing")
    else:
        for field in (
            "reference",
            "approved_at",
            "approved_by",
            "scope",
            "scheduler_window_start",
            "scheduler_window_end",
            "abort_owner",
            "rollback_owner",
        ):
            if not approval.get(field):
                errors.append(f"operator approval missing {field}")
        if approval.get("host_evidence_owner") != "operator":
            errors.append("host evidence owner must be operator")
        if int(approval.get("expected_scheduled_run_count", 0)) <= 0:
            errors.append("expected scheduled run count must be positive")

    scope = manifest.get("enablement_scope", {})
    if not isinstance(scope, dict):
        errors.append("enablement_scope missing")
    else:
        if scope.get("trigger_source") != "SCHEDULED":
            errors.append("enablement trigger_source must be SCHEDULED")
        if scope.get("worker_enabled_before") is not False or scope.get("scheduler_enabled_before") is not False:
            errors.append("worker and scheduler must be disabled before enablement window")
        if scope.get("worker_enabled_during") is not True:
            errors.append("worker must be enabled during approved window")
        if scope.get("scheduler_enabled_during") is not True:
            errors.append("scheduler must be enabled during approved window")
        if scope.get("worker_enabled_after") is not False or scope.get("scheduler_enabled_after") is not False:
            errors.append("worker and scheduler must be disabled after rollback")
        if sorted_unique(scope.get("requested_timeframes")) != sorted_unique(approval.get("approved_timeframes")):
            errors.append("requested timeframes do not match approved timeframes")
        if scope.get("expected_scheduled_run_count") != approval.get("expected_scheduled_run_count"):
            errors.append("scope expected run count does not match approval")

    status = manifest.get("status_evidence", {})
    if not isinstance(status, dict):
        errors.append("status_evidence missing")
    else:
        if status.get("payload_valid") is not True:
            errors.append("status payload did not validate")
        if status.get("final_status") != "SUCCEEDED":
            errors.append(f"final status must be SUCCEEDED: {status.get('final_status')}")
        if status.get("recommendation_decision") not in SAFE_SUCCESS_RECOMMENDATIONS:
            errors.append(f"unsafe success recommendation: {status.get('recommendation_decision')}")
        if status.get("budget_state") != "WITHIN_BUDGET":
            errors.append(f"budget state must be WITHIN_BUDGET: {status.get('budget_state')}")
        if status.get("fail_closed_reasons"):
            errors.append("status payload contains fail-closed reasons")
        if status.get("scheduled_run_count") != approval.get("expected_scheduled_run_count"):
            errors.append("scheduled run count does not match approval")
        if int(status.get("manual_run_count", 0)) != 0:
            errors.append("manual run contamination detected")
        if status.get("artifact_manifest_present") is not True:
            errors.append("artifact manifest missing")
        if status.get("artifact_manifest_valid") is not True:
            errors.append("artifact manifest invalid")
        if status.get("artifact_trigger_source") != "SCHEDULED":
            errors.append("artifact trigger source must be SCHEDULED")
        if sorted_unique(status.get("artifact_requested_timeframes")) != sorted_unique(scope.get("requested_timeframes")):
            errors.append("artifact requested timeframes do not match scope")
        progression = status.get("progression", [])
        if "SUCCEEDED" not in progression:
            errors.append("status progression does not include SUCCEEDED")
        for unsafe_status in ("DEGRADED", "FAILED", "EXPIRED", "CANCELED"):
            if unsafe_status in progression:
                errors.append(f"status progression contains fail-closed terminal state: {unsafe_status}")

    metrics = manifest.get("metrics", {})
    if not isinstance(metrics, dict):
        errors.append("metrics missing")
    else:
        if active_count_total(metrics.get("active_runs_before", {})) != 0:
            errors.append("active async gauges were nonzero before approval")
        if active_count_total(metrics.get("active_runs_during_peak", {})) <= 0:
            errors.append("active async gauges did not show an enabled-window lifecycle")
        if active_count_total(metrics.get("active_runs_after", {})) != 0:
            errors.append("active async gauges were nonzero after rollback")
        if metrics.get("scheduler_enqueued_delta") != approval.get("expected_scheduled_run_count"):
            errors.append("scheduler enqueue delta does not match approved run count")
        if int(metrics.get("manual_enqueued_delta", 0)) != 0:
            errors.append("manual enqueue delta must be zero")
        for field in BLOCKING_DELTAS:
            if int(metrics.get(field, 0)) != 0:
                errors.append(f"{field} increased")

    alerting = manifest.get("alerting", {})
    if not isinstance(alerting, dict):
        errors.append("alerting missing")
    else:
        if alerting.get("configured") is not True:
            errors.append("alerting is not configured")
        if alerting.get("routed") is not True:
            errors.append("alerting is not routed")
        if alerting.get("missing_data_blocks") is not True:
            errors.append("alerting does not render missing data as blocked")
        if alerting.get("evidence_state") != "DEPLOYED":
            errors.append("alerting evidence must be DEPLOYED")
        rules = {
            rule.get("id"): rule
            for rule in alerting.get("rules", [])
            if isinstance(rule, dict) and isinstance(rule.get("id"), str)
        }
        for rule_id in sorted(REQUIRED_ALERT_RULES):
            rule = rules.get(rule_id)
            if not rule:
                errors.append(f"alert rule missing: {rule_id}")
                continue
            for field in (
                "configured",
                "routed",
                "query_present",
                "before_state_captured",
                "during_state_captured",
                "after_state_captured",
            ):
                if rule.get(field) is not True:
                    errors.append(f"alert rule {rule_id} missing {field}")

    thresholds = manifest.get("thresholds", {})
    if not isinstance(thresholds, dict):
        errors.append("thresholds missing")
    else:
        if thresholds.get("approved_before_window") is not True:
            errors.append("thresholds were not approved before enablement window")
        cpu = thresholds.get("cpu", {})
        if not isinstance(cpu, dict):
            errors.append("CPU threshold evidence missing")
        else:
            for field in ("baseline_captured", "during_after_captured", "within_threshold"):
                if cpu.get(field) is not True:
                    errors.append(f"CPU threshold missing {field}")
        for endpoint in thresholds.get("hot_endpoints", []):
            if not isinstance(endpoint, dict):
                errors.append("hot endpoint threshold entry invalid")
                continue
            for field in ("baseline_captured", "during_after_captured", "within_threshold"):
                if endpoint.get(field) is not True:
                    errors.append(f"hot endpoint {endpoint.get('path')} missing {field}")
        if not thresholds.get("hot_endpoints"):
            errors.append("hot endpoint threshold list is empty")

    logs = manifest.get("logs", {})
    if not isinstance(logs, dict):
        errors.append("logs missing")
    else:
        for field in ("before_useful", "during_useful", "after_useful"):
            if logs.get(field) is not True:
                errors.append(f"logs missing {field}")
        events = set(logs.get("events_seen", []))
        for event in sorted(REQUIRED_LOG_EVENTS):
            if event not in events:
                errors.append(f"logs missing event {event}")

    safety = manifest.get("safety", {})
    if not isinstance(safety, dict):
        errors.append("safety missing")
    else:
        if safety.get("live_entry_enabled") is not False:
            errors.append("live ENTRY is not disabled")
        if safety.get("live_exit_enabled") is not False:
            errors.append("live EXIT is not disabled")
        if safety.get("automatic_promote_enabled") is not False:
            errors.append("automatic PROMOTE is enabled")
        if safety.get("automatic_revert_enabled") is not False:
            errors.append("automatic REVERT is enabled")
        if safety.get("promote_confirm_gated") is not True:
            errors.append("PROMOTE is not confirmation-gated")
        if safety.get("revert_confirm_gated") is not True:
            errors.append("REVERT is not confirmation-gated")
        if safety.get("repair_provenance_blocked") is not True:
            errors.append("repair provenance is not blocked")

    if manifest.get("stop_conditions"):
        errors.append(f"stop conditions present: {', '.join(manifest.get('stop_conditions', []))}")

    expected_overall = not errors
    if manifest.get("overall_pass") is not expected_overall:
        errors.append("overall_pass does not match semantic validation result")
    if errors and manifest.get("recommended_action") != "KEEP_DISABLED_KEEP_HOLD":
        errors.append("failing evidence must recommend KEEP_DISABLED_KEEP_HOLD")
    if not errors and manifest.get("recommended_action") != "READY_FOR_OPERATOR_REVIEW":
        errors.append("passing evidence must recommend READY_FOR_OPERATOR_REVIEW")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to production async enablement evidence manifest JSON")
    parser.add_argument("--bundle-root", default=None, help="Bundle root for --verify-files")
    parser.add_argument("--verify-files", action="store_true", help="Verify artifact files and sha256")
    parser.add_argument("--output-json", default=None, help="Optional validation report path")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    try:
        manifest = load_json(manifest_path)
    except Exception as error:  # noqa: BLE001
        report = {
            "manifest": str(manifest_path),
            "pass": False,
            "errors": [f"unable to load manifest: {error}"],
            "recommended_action": "KEEP_DISABLED_KEEP_HOLD",
        }
        print(json.dumps(report, indent=2))
        return 1

    errors = validate_manifest(manifest)
    if args.verify_files:
        verify_artifact_files(manifest, Path(args.bundle_root) if args.bundle_root else manifest_path.parent, errors)

    report = {
        "manifest": str(manifest_path),
        "bundle_id": manifest.get("bundle_id"),
        "pass": not errors,
        "errors": errors,
        "recommended_action": "READY_FOR_OPERATOR_REVIEW" if not errors else "KEEP_DISABLED_KEEP_HOLD",
    }
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
