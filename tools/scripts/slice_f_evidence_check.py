#!/usr/bin/env python3
"""Validate a Slice F async reoptimization canary evidence manifest.

The manifest schema checks shape. This script checks the safety semantics that
must hold before any operator-only Slice F canary can be trusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_ALERT_RULES = {
    "stuck_lease",
    "failed_degraded_runs",
    "schedule_missed",
    "budget_exhaustion",
    "cancellation_failure",
    "missing_telemetry",
    "unknown_status",
    "unsafe_promotion",
    "repair_provenance_active",
}

BASE_REQUIRED_ARTIFACTS = {
    "repo_identity",
    "runner_flags_before",
    "status_before",
    "metrics_before",
    "alerts_config",
    "alerts_before",
    "strategy_logs_before",
    "repair_provenance_inventory",
    "trade_now_repair_provenance_block",
    "entry_exit_disabled",
    "promotion_revert_gating",
}

CANARY_REQUIRED_ARTIFACTS = {
    "operator_approval",
    "runner_flags_after",
    "budget_values",
    "status_progression",
    "status_after",
    "metrics_during",
    "metrics_after",
    "alerts_after",
    "strategy_logs_during",
    "strategy_logs_after",
    "cpu_baseline",
    "cpu_during_after",
    "hot_endpoint_latency_baseline",
    "hot_endpoint_latency_after",
}

REQUIRED_CHECKS = {
    "operator_approval_present",
    "alerting_ready",
    "thresholds_approved",
    "strategy_logs_useful",
    "status_contract_valid",
    "metrics_bounded_and_present",
    "active_async_gauges_zero_before",
    "status_progression_known",
    "recommendation_safe",
    "entry_exit_disabled",
    "promotion_revert_confirm_gated",
    "repair_provenance_blocked",
    "cpu_within_threshold",
    "hot_endpoint_latency_within_threshold",
    "artifact_evidence_valid",
    "stop_conditions_absent",
}

NON_SUCCESS_STATUSES = {
    "QUEUED",
    "LEASED",
    "RUNNING",
    "CANCEL_REQUESTED",
    "CANCELED",
    "DEGRADED",
    "FAILED",
    "EXPIRED",
}

SAFE_NON_SUCCESS_RECOMMENDATIONS = {"HOLD", "OPERATOR_REVIEW_REQUIRED"}


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


def check_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for check in manifest.get("checks", []):
        if isinstance(check, dict) and isinstance(check.get("id"), str):
            checks[check["id"]] = check
    return checks


def active_count_total(counts: dict[str, Any]) -> int:
    return sum(int(counts.get(status, 0)) for status in ("QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED"))


def verify_artifact_files(manifest: dict[str, Any], bundle_root: Path, errors: list[str]) -> None:
    for artifact in manifest.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        path_value = artifact.get("path")
        artifact_id = artifact.get("id", "<unknown>")
        expected_sha = artifact.get("sha256")
        if not isinstance(path_value, str) or not isinstance(expected_sha, str):
            errors.append(f"artifact {artifact_id}: path or sha256 missing")
            continue
        artifact_path = bundle_root / path_value
        try:
            resolved = artifact_path.resolve()
            root = bundle_root.resolve()
        except OSError as error:
            errors.append(f"artifact {artifact_id}: cannot resolve path: {error}")
            continue
        if not str(resolved).startswith(str(root)):
            errors.append(f"artifact {artifact_id}: path escapes bundle root")
            continue
        if not resolved.exists():
            errors.append(f"artifact {artifact_id}: file missing at {path_value}")
            continue
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if digest != expected_sha:
            errors.append(f"artifact {artifact_id}: sha256 mismatch")


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    canary = bool(manifest.get("canary_authorized"))

    if manifest.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")

    repo_identity = manifest.get("repo_identity", {})
    if not isinstance(repo_identity, dict):
        errors.append("repo_identity missing")
    else:
        if repo_identity.get("captured_by") != "operator":
            errors.append("host/repo identity must be operator-captured")
        if repo_identity.get("dirty_status") == "UNKNOWN":
            errors.append("host/repo dirty status is unknown")

    approval = manifest.get("operator_approval", {})
    if canary:
        if not isinstance(approval, dict) or approval.get("present") is not True:
            errors.append("canary is authorized but operator approval is missing")
        else:
            required_approval_fields = [
                "reference",
                "approved_at",
                "approved_by",
                "scope",
                "abort_owner",
                "rollback_owner",
            ]
            for field in required_approval_fields:
                if not approval.get(field):
                    errors.append(f"operator approval missing {field}")
            if approval.get("host_evidence_owner") != "operator":
                errors.append("host evidence owner must be operator")

    artifacts = artifact_ids(manifest)
    required_artifacts = set(BASE_REQUIRED_ARTIFACTS)
    if canary:
        required_artifacts.update(CANARY_REQUIRED_ARTIFACTS)
    missing_artifacts = sorted(required_artifacts - artifacts)
    for artifact_id in missing_artifacts:
        errors.append(f"required artifact missing: {artifact_id}")

    checks = check_map(manifest)
    missing_checks = sorted(REQUIRED_CHECKS - set(checks))
    for check_id in missing_checks:
        errors.append(f"required check missing: {check_id}")
    for check_id, check in sorted(checks.items()):
        status = check.get("status")
        if status == "FAIL":
            errors.append(f"check failed: {check_id}: {check.get('failure_reason')}")
        if canary and status == "NOT_APPLICABLE":
            errors.append(f"check cannot be NOT_APPLICABLE for canary: {check_id}")
        if not canary and check_id not in {
            "operator_approval_present",
            "cpu_within_threshold",
            "hot_endpoint_latency_within_threshold",
            "artifact_evidence_valid",
        } and status != "PASS":
            errors.append(f"readiness check must PASS: {check_id}")
        for artifact_id in check.get("evidence_artifact_ids", []):
            if artifact_id not in artifacts:
                errors.append(f"check {check_id} references missing artifact {artifact_id}")

    alerting = manifest.get("alerting", {})
    if not isinstance(alerting, dict):
        errors.append("alerting object missing")
    else:
        if alerting.get("configured") is not True:
            errors.append("alerting is not configured")
        if alerting.get("routed") is not True:
            errors.append("alerting is not routed")
        if alerting.get("missing_data_blocks") is not True:
            errors.append("alerting does not render missing data as blocked")
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
            for field in ("configured", "routed", "query_present", "before_state_captured"):
                if rule.get(field) is not True:
                    errors.append(f"alert rule {rule_id} missing {field}")
            if canary and rule.get("after_state_captured") is not True:
                errors.append(f"alert rule {rule_id} missing after_state_captured")

    thresholds = manifest.get("thresholds", {})
    if not isinstance(thresholds, dict):
        errors.append("thresholds object missing")
    else:
        if thresholds.get("approved_before_canary") is not True:
            errors.append("CPU/hot endpoint thresholds were not approved before canary")
        cpu = thresholds.get("cpu", {})
        if not isinstance(cpu, dict):
            errors.append("CPU threshold missing")
        else:
            if cpu.get("baseline_captured") is not True:
                errors.append("CPU baseline missing")
            if canary and cpu.get("post_run_captured") is not True:
                errors.append("CPU post-run sample missing")
            if canary and cpu.get("within_threshold") is not True:
                errors.append("CPU threshold breached or unproven")
        hot_endpoints = thresholds.get("hot_endpoints", [])
        if not hot_endpoints:
            errors.append("hot endpoint threshold list is empty")
        for endpoint in hot_endpoints:
            if not isinstance(endpoint, dict):
                errors.append("hot endpoint threshold entry invalid")
                continue
            if not endpoint.get("method") or not endpoint.get("path"):
                errors.append("hot endpoint threshold missing method/path")
            if endpoint.get("baseline_captured") is not True:
                errors.append(f"hot endpoint {endpoint.get('path')} baseline missing")
            if canary and endpoint.get("post_run_captured") is not True:
                errors.append(f"hot endpoint {endpoint.get('path')} post-run sample missing")
            if canary and endpoint.get("within_threshold") is not True:
                errors.append(f"hot endpoint {endpoint.get('path')} threshold breached or unproven")

    logs = manifest.get("logs", {})
    if not isinstance(logs, dict):
        errors.append("logs object missing")
    else:
        if logs.get("before_useful") is not True:
            errors.append("strategy_logs_before is not useful")
        if canary:
            if logs.get("during_useful") is not True:
                errors.append("strategy_logs_during is not useful")
            if logs.get("after_useful") is not True:
                errors.append("strategy_logs_after is not useful")
            events = set(logs.get("events_seen", []))
            for event in ("reoptimize_run_enqueued", "reoptimize_lease_acquired", "reoptimize_recommendation_finalized"):
                if event not in events:
                    errors.append(f"canary logs missing event {event}")
        elif logs.get("disabled_state_evidence") is not True:
            errors.append("readiness logs do not prove disabled state")

    for index, payload in enumerate(manifest.get("status_payloads", [])):
        if not isinstance(payload, dict):
            errors.append(f"status_payloads[{index}] is not an object")
            continue
        status = payload.get("status")
        decision = payload.get("recommendation_decision")
        budget_state = payload.get("budget_state")
        if payload.get("payload_valid") is not True:
            errors.append(f"status payload {payload.get('artifact_id')} did not validate")
        if status in NON_SUCCESS_STATUSES and decision not in SAFE_NON_SUCCESS_RECOMMENDATIONS:
            errors.append(f"status {status} must map to HOLD or OPERATOR_REVIEW_REQUIRED")
        if status in {"QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED"} and canary:
            errors.append(f"canary status remained non-terminal: {status}")
        if budget_state in {"UNKNOWN", "EXHAUSTED"}:
            errors.append(f"budget state is fail-closed: {budget_state}")

    metrics = manifest.get("metrics", {})
    if not isinstance(metrics, dict):
        errors.append("metrics object missing")
    else:
        before_total = active_count_total(metrics.get("active_runs_before", {}))
        if before_total != 0:
            errors.append("active async gauges were nonzero before approval")
        if canary and active_count_total(metrics.get("active_runs_after", {})) != 0:
            errors.append("active async gauges were nonzero after canary")
        for field in (
            "missing_telemetry_delta",
            "status_unknown_delta",
            "budget_exhausted_delta",
            "unsafe_promotion_delta",
        ):
            if int(metrics.get(field, 0)) != 0:
                errors.append(f"{field} increased")

    safety = manifest.get("safety", {})
    if not isinstance(safety, dict):
        errors.append("safety object missing")
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

    repair = manifest.get("repair_provenance", {})
    if not isinstance(repair, dict):
        errors.append("repair_provenance object missing")
    else:
        if repair.get("inventory_captured") is not True:
            errors.append("repair provenance inventory missing")
        if repair.get("all_recanonicalized_rows_blocked") is not True:
            errors.append("repair provenance is not fully blocked")
        rows = repair.get("rows", [])
        audited = int(repair.get("recanonicalized_rows_audited", 0))
        if audited != len(rows):
            errors.append("recanonicalized_rows_audited does not match row evidence count")
        for row in rows:
            pair_id = row.get("pair_id", "<unknown>") if isinstance(row, dict) else "<invalid>"
            if not isinstance(row, dict):
                errors.append("repair provenance row is not an object")
                continue
            if row.get("decision_bucket") != "EXCLUDED":
                errors.append(f"{pair_id}: recanonicalized row is not excluded")
            if row.get("decision_reason_code") != "PROVENANCE_POLICY_BLOCKED":
                errors.append(f"{pair_id}: missing PROVENANCE_POLICY_BLOCKED decision reason")
            if row.get("blocked_reason_code") != "RECANONICALIZED_LEGACY_ROW_ACTIVE":
                errors.append(f"{pair_id}: missing RECANONICALIZED_LEGACY_ROW_ACTIVE blocked reason")
            if "RECANONICALIZED_LEGACY_ROW_ACTIVE" not in row.get("rationale_codes", []):
                errors.append(f"{pair_id}: missing RECANONICALIZED_LEGACY_ROW_ACTIVE rationale")
            if row.get("live_trade_eligible") is not False:
                errors.append(f"{pair_id}: recanonicalized row is live trade eligible")
            if row.get("graduated_to_non_repair_source") is not False:
                errors.append(f"{pair_id}: recanonicalized row graduated to non-repair source")

    stop_conditions = manifest.get("stop_conditions", [])
    if stop_conditions:
        errors.append(f"stop conditions present: {', '.join(stop_conditions)}")

    expected_overall = not errors
    if manifest.get("overall_pass") is not expected_overall:
        errors.append("overall_pass does not match semantic validation result")
    if errors and manifest.get("recommended_action") != "KEEP_DISABLED_KEEP_HOLD":
        errors.append("failing evidence must recommend KEEP_DISABLED_KEEP_HOLD")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to slice_f_reoptimize_canary_evidence_manifest JSON")
    parser.add_argument(
        "--bundle-root",
        default=None,
        help="Optional root used with --verify-files for relative artifact paths",
    )
    parser.add_argument(
        "--verify-files",
        action="store_true",
        help="Verify referenced artifact files exist under --bundle-root and match sha256",
    )
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
        bundle_root = Path(args.bundle_root) if args.bundle_root else manifest_path.parent
        verify_artifact_files(manifest, bundle_root, errors)

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
