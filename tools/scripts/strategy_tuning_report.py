#!/usr/bin/env python3
"""Deterministic strategy tuning reporter with promote/hold/revert recommendations."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SUPPORTED_TIMEFRAMES = ("1m", "15m", "1h")
REOPTIMIZE_MODES = ("sync", "async", "latest-successful", "skip")
ASYNC_REOPTIMIZE_STATUSES = {
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
ASYNC_REOPTIMIZE_ACTIVE_STATUSES = {"QUEUED", "LEASED", "RUNNING", "CANCEL_REQUESTED"}
ASYNC_REOPTIMIZE_TERMINAL_STATUSES = {
    "CANCELED",
    "SUCCEEDED",
    "DEGRADED",
    "FAILED",
    "EXPIRED",
}
ASYNC_REOPTIMIZE_TRIGGER_SOURCES = {
    "SCHEDULED",
    "MANUAL_API",
    "MAINTENANCE_REPORT",
    "RECOVERY",
}
ASYNC_REOPTIMIZE_RECOMMENDATIONS = {
    "HOLD",
    "OPERATOR_REVIEW_REQUIRED",
    "PROMOTION_CANDIDATE_AVAILABLE",
    "REVERT_REVIEW_REQUIRED",
}
ASYNC_REOPTIMIZE_FAIL_CLOSED_REASONS = {
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
ASYNC_REOPTIMIZE_REQUIRED_ARTIFACT_KINDS = {"REQUEST", "PROGRESS", "SUMMARY", "ERRORS"}
ASYNC_REOPTIMIZE_ARTIFACT_KINDS = {
    "REQUEST",
    "PROGRESS",
    "SUMMARY",
    "ERRORS",
    "TIMEFRAME_DETAIL",
    "OPERATOR_SUMMARY",
}
ASYNC_REOPTIMIZE_CONTENT_TYPES = {"application/json", "text/markdown"}
ASYNC_REOPTIMIZE_PHASES = {
    "QUEUED",
    "PRECHECK",
    "TIMEFRAME_PRECHECK",
    "PAIR_EVALUATION",
    "PERSIST_SELECTED_ROWS",
    "PERSIST_SHADOW_MODEL",
    "TIMEFRAME_SUMMARY",
    "RUN_SUMMARY",
    "ARTIFACT_WRITE",
    "TERMINAL",
}
ASYNC_REOPTIMIZE_BUDGET_STATES = {"WITHIN_BUDGET", "EXHAUSTED", "UNKNOWN"}
ASYNC_REOPTIMIZE_EXHAUSTED_BUDGETS = {
    "RUN_WALL_CLOCK",
    "TIMEFRAME_WALL_CLOCK",
    "PAIR_EVALUATIONS_RUN",
    "PAIR_EVALUATIONS_TIMEFRAME",
    "PAIR_CONCURRENCY",
    "DB_WRITE_BATCH",
    "ARTIFACT_BYTES",
    "COOLDOWN",
    "LEASE_TTL",
}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
ARTIFACT_PATH_RE = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/-]+$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


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


def join_service_url(base_url: str, route: str) -> str:
    if route.startswith("http://") or route.startswith("https://"):
        return route
    return f"{base_url.rstrip('/')}/{route.lstrip('/')}"


def is_safe_reoptimize_cancel_route(route: Any) -> bool:
    if not isinstance(route, str):
        return False
    route = route.strip()
    return route.startswith("/v1/strategy/reoptimize/runs/") and route.endswith("/cancel")


def parse_datetime_utc(raw: Any) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_int_at_least(value: Any, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def is_number_between(value: Any, minimum: float, maximum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= float(value) <= maximum


def validate_object_shape(
    value: Any,
    *,
    name: str,
    required: set[str],
    allowed: set[str],
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{name} missing or not an object"]
    errors = [f"{name} missing {key}" for key in sorted(required - set(value))]
    extra = sorted(set(value) - allowed)
    errors.extend(f"{name} unexpected {key}" for key in extra)
    return errors


def validate_datetime_field(
    value: Any,
    *,
    name: str,
    nullable: bool = False,
) -> list[str]:
    if value is None and nullable:
        return []
    if parse_datetime_utc(value) is None:
        return [f"{name} invalid"]
    return []


def validate_run_id(value: Any, *, name: str, nullable: bool = False) -> list[str]:
    if value is None and nullable:
        return []
    if not isinstance(value, str) or RUN_ID_RE.fullmatch(value) is None:
        return [f"{name} invalid"]
    return []


def validate_nullable_string(
    value: Any,
    *,
    name: str,
    max_len: int | None = None,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str) or not value:
        return [f"{name} invalid"]
    if max_len is not None and len(value) > max_len:
        return [f"{name} invalid"]
    if pattern is not None and pattern.fullmatch(value) is None:
        return [f"{name} invalid"]
    return []


def validate_fail_closed_reason_list(value: Any, *, name: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{name} invalid"]
    if any(not isinstance(reason, str) for reason in value):
        return [f"{name} invalid"]
    if len(set(value)) != len(value):
        return [f"{name} duplicate values"]
    invalid = [reason for reason in value if reason not in ASYNC_REOPTIMIZE_FAIL_CLOSED_REASONS]
    if invalid:
        return [f"{name} invalid"]
    return []


def validate_timeframe_list(value: Any, *, name: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(timeframe, str) or timeframe not in SUPPORTED_TIMEFRAMES
            for timeframe in value
        )
        or len(set(value)) != len(value)
    ):
        return [f"{name} invalid"]
    return []


def validate_async_reoptimize_error(error: Any, *, name: str) -> list[str]:
    required = {
        "code",
        "severity",
        "message",
        "phase",
        "timeframe",
        "pair_id",
        "retryable",
        "occurred_at",
    }
    errors = validate_object_shape(error, name=name, required=required, allowed=required)
    if errors:
        return errors
    assert isinstance(error, dict)
    if not isinstance(error.get("code"), str) or not error["code"]:
        errors.append(f"{name} code invalid")
    if error.get("severity") not in {"CRITICAL", "NON_CRITICAL"}:
        errors.append(f"{name} severity invalid")
    if not isinstance(error.get("message"), str) or not error["message"]:
        errors.append(f"{name} message invalid")
    if error.get("phase") not in ASYNC_REOPTIMIZE_PHASES:
        errors.append(f"{name} phase invalid")
    if error.get("timeframe") is not None and error.get("timeframe") not in SUPPORTED_TIMEFRAMES:
        errors.append(f"{name} timeframe invalid")
    if error.get("pair_id") is not None and not isinstance(error.get("pair_id"), str):
        errors.append(f"{name} pair_id invalid")
    if not isinstance(error.get("retryable"), bool):
        errors.append(f"{name} retryable invalid")
    errors.extend(validate_datetime_field(error.get("occurred_at"), name=f"{name} occurred_at"))
    return errors


def validate_async_reoptimize_error_list(value: Any, *, name: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{name} invalid"]
    errors: list[str] = []
    for index, error in enumerate(value):
        errors.extend(validate_async_reoptimize_error(error, name=f"{name}[{index}]"))
    return errors


def validate_async_reoptimize_transition_counts(value: Any) -> list[str]:
    required = {
        "initialize_decisions",
        "unchanged_decisions",
        "champion_locks",
        "champion_promotions",
    }
    errors = validate_object_shape(value, name="transition_counts", required=required, allowed=required)
    if errors:
        return errors
    assert isinstance(value, dict)
    for key in sorted(required):
        if not is_int_at_least(value.get(key), 0):
            errors.append(f"transition_counts {key} invalid")
    return errors


def validate_async_reoptimize_progress(progress: Any) -> list[str]:
    required = {
        "phase",
        "requested_timeframes",
        "active_timeframe",
        "planned_timeframe_count",
        "completed_timeframe_count",
        "failed_timeframe_count",
        "total_pairs_planned",
        "pairs_completed",
        "pairs_skipped",
        "pairs_failed",
        "selected_rows_written",
        "drift_rows_written",
        "transition_counts",
        "critical_error_count",
        "non_critical_error_count",
        "percent_complete",
        "last_heartbeat_at",
    }
    errors = validate_object_shape(progress, name="progress", required=required, allowed=required)
    if errors:
        return errors
    assert isinstance(progress, dict)
    if progress.get("phase") not in ASYNC_REOPTIMIZE_PHASES:
        errors.append("progress phase invalid")
    errors.extend(validate_timeframe_list(progress.get("requested_timeframes"), name="progress requested_timeframes"))
    if progress.get("active_timeframe") is not None and progress.get("active_timeframe") not in SUPPORTED_TIMEFRAMES:
        errors.append("progress active_timeframe invalid")
    for key in (
        "planned_timeframe_count",
        "completed_timeframe_count",
        "failed_timeframe_count",
        "total_pairs_planned",
        "pairs_completed",
        "pairs_skipped",
        "pairs_failed",
        "selected_rows_written",
        "drift_rows_written",
        "critical_error_count",
        "non_critical_error_count",
    ):
        if not is_int_at_least(progress.get(key), 0):
            errors.append(f"progress {key} invalid")
    if not is_number_between(progress.get("percent_complete"), 0, 100):
        errors.append("progress percent_complete invalid")
    errors.extend(validate_async_reoptimize_transition_counts(progress.get("transition_counts")))
    errors.extend(
        validate_datetime_field(
            progress.get("last_heartbeat_at"),
            name="progress last_heartbeat_at",
            nullable=True,
        )
    )
    return errors


def validate_async_reoptimize_budgets(budgets: Any) -> list[str]:
    required = {
        "budget_state",
        "max_run_seconds",
        "max_timeframe_seconds",
        "max_pairs_per_run",
        "max_pairs_per_timeframe",
        "max_in_flight_pair_evaluations",
        "max_db_write_batch_size",
        "max_artifact_bytes",
        "min_cooldown_seconds",
        "lease_ttl_seconds",
        "heartbeat_interval_seconds",
        "exhausted_budget",
    }
    errors = validate_object_shape(budgets, name="budgets", required=required, allowed=required)
    if errors:
        return errors
    assert isinstance(budgets, dict)
    if budgets.get("budget_state") not in ASYNC_REOPTIMIZE_BUDGET_STATES:
        errors.append("budgets budget_state invalid")
    for key in (
        "max_run_seconds",
        "max_timeframe_seconds",
        "max_pairs_per_run",
        "max_pairs_per_timeframe",
        "max_in_flight_pair_evaluations",
        "max_db_write_batch_size",
        "max_artifact_bytes",
        "lease_ttl_seconds",
        "heartbeat_interval_seconds",
    ):
        value = budgets.get(key)
        if value is not None and not is_int_at_least(value, 1):
            errors.append(f"budgets {key} invalid")
    min_cooldown = budgets.get("min_cooldown_seconds")
    if min_cooldown is not None and not is_int_at_least(min_cooldown, 0):
        errors.append("budgets min_cooldown_seconds invalid")
    exhausted = budgets.get("exhausted_budget")
    if exhausted is not None and exhausted not in ASYNC_REOPTIMIZE_EXHAUSTED_BUDGETS:
        errors.append("budgets exhausted_budget invalid")
    return errors


def validate_async_reoptimize_recommendation(recommendation: Any) -> list[str]:
    required = {"decision", "reason_codes", "summary"}
    errors = validate_object_shape(
        recommendation,
        name="recommendation",
        required=required,
        allowed=required,
    )
    if errors:
        return errors
    assert isinstance(recommendation, dict)
    if recommendation.get("decision") not in ASYNC_REOPTIMIZE_RECOMMENDATIONS:
        errors.append("recommendation decision invalid")
    errors.extend(validate_fail_closed_reason_list(recommendation.get("reason_codes"), name="recommendation reason_codes"))
    if not isinstance(recommendation.get("summary"), str) or not recommendation["summary"]:
        errors.append("recommendation summary invalid")
    return errors


def expected_reoptimize_request_fingerprint(
    *,
    profile: str,
    timeframes: list[str],
    policy_path: Path,
    policy: dict[str, Any],
) -> str:
    material = {
        "script": "strategy_tuning_report.py",
        "schema": 1,
        "profile": profile,
        "timeframes": timeframes,
        "policy_path": str(policy_path),
        "policy_version": int(policy.get("version", 1)),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()
    return f"strategy_tuning_report:v1:{digest[:32]}"


def resolve_reoptimize_mode(args: argparse.Namespace) -> str:
    if args.skip_reoptimize:
        return "skip"
    mode = str(getattr(args, "reoptimize_mode", "sync"))
    if mode not in REOPTIMIZE_MODES:
        return "sync"
    return mode


def reoptimize_report_error(
    code: str,
    message: str,
    timeframes: list[str],
) -> dict[str, str]:
    timeframe = timeframes[0] if timeframes else "1m"
    return {
        "pair_id": "*",
        "timeframe": timeframe,
        "code": code,
        "severity": "CRITICAL",
        "error": f"{code}: {message}",
    }


def base_reoptimize_summary(mode: str) -> dict[str, Any]:
    return {
        "pairs_processed": 0,
        "cues_generated": 0,
        "cost_gate_pass": 0,
        "cost_gate_fail": 0,
        "errors": [],
        "mode": mode,
        "force_hold": False,
        "evidence_valid": False,
        "error_codes": [],
        "fail_closed_reasons": [],
    }


def fail_closed_reoptimize_summary(
    *,
    mode: str,
    code: str,
    message: str,
    timeframes: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = base_reoptimize_summary(mode)
    summary.update(
        {
            "force_hold": True,
            "error_codes": [code],
            "fail_closed_reasons": [code],
            "errors": [reoptimize_report_error(code, message, timeframes)],
        }
    )
    if extra:
        summary.update(extra)
    return summary


def validate_async_reoptimize_artifact_manifest(manifest: Any) -> list[str]:
    required = {
        "schema_version",
        "generated_at",
        "run_id",
        "status",
        "trigger_source",
        "request_fingerprint",
        "service_version",
        "artifact_root",
        "run_artifact_dir",
        "artifact_download_route",
        "complete",
        "total_bytes",
        "artifacts",
        "fail_closed_reasons",
        "errors",
    }
    errors = validate_object_shape(
        manifest,
        name="artifact_manifest",
        required=required,
        allowed=required,
    )
    if errors:
        return errors
    assert isinstance(manifest, dict)
    if manifest.get("schema_version") != "1.0.0":
        errors.append("artifact_manifest schema_version mismatch")
    errors.extend(validate_datetime_field(manifest.get("generated_at"), name="artifact_manifest generated_at"))
    errors.extend(validate_run_id(manifest.get("run_id"), name="artifact_manifest run_id"))
    if manifest.get("complete") is not True:
        errors.append("artifact_manifest is not complete")
    if manifest.get("status") not in ASYNC_REOPTIMIZE_STATUSES:
        errors.append("artifact_manifest status unknown")
    if manifest.get("trigger_source") not in ASYNC_REOPTIMIZE_TRIGGER_SOURCES:
        errors.append("artifact_manifest trigger_source unknown")
    errors.extend(
        validate_nullable_string(
            manifest.get("request_fingerprint"),
            name="artifact_manifest request_fingerprint",
            max_len=256,
            pattern=FINGERPRINT_RE,
        )
    )
    errors.extend(
        validate_nullable_string(
            manifest.get("service_version"),
            name="artifact_manifest service_version",
            max_len=128,
        )
    )
    if not isinstance(manifest.get("artifact_root"), str) or not manifest["artifact_root"]:
        errors.append("artifact_manifest artifact_root invalid")
    if not isinstance(manifest.get("artifact_download_route"), str) or not manifest[
        "artifact_download_route"
    ].strip():
        errors.append("artifact_manifest artifact_download_route missing")
    run_artifact_dir = manifest.get("run_artifact_dir")
    if not isinstance(run_artifact_dir, str) or ARTIFACT_PATH_RE.fullmatch(run_artifact_dir) is None:
        errors.append("artifact_manifest run_artifact_dir invalid")
    if not is_int_at_least(manifest.get("total_bytes"), 0):
        errors.append("artifact_manifest total_bytes invalid")
    errors.extend(
        validate_fail_closed_reason_list(
            manifest.get("fail_closed_reasons"),
            name="artifact_manifest fail_closed_reasons",
        )
    )
    errors.extend(validate_async_reoptimize_error_list(manifest.get("errors"), name="artifact_manifest errors"))

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifact_manifest artifacts missing")
        return errors

    required_kinds: set[str] = set()
    artifact_required = {"kind", "path", "content_type", "bytes", "sha256", "created_at", "required"}
    for index, artifact in enumerate(artifacts):
        artifact_name = f"artifact_manifest artifacts[{index}]"
        artifact_errors = validate_object_shape(
            artifact,
            name=artifact_name,
            required=artifact_required,
            allowed=artifact_required,
        )
        if artifact_errors:
            errors.extend(artifact_errors)
            continue
        assert isinstance(artifact, dict)
        kind = artifact.get("kind")
        if kind not in ASYNC_REOPTIMIZE_ARTIFACT_KINDS:
            errors.append(f"{artifact_name} kind invalid")
        if artifact.get("required") is True and isinstance(kind, str):
            required_kinds.add(kind)
        path = artifact.get("path")
        if not isinstance(path, str) or ARTIFACT_PATH_RE.fullmatch(path) is None:
            errors.append(f"{artifact_name} path invalid")
        if artifact.get("content_type") not in ASYNC_REOPTIMIZE_CONTENT_TYPES:
            errors.append(f"{artifact_name} content_type invalid")
        if not is_int_at_least(artifact.get("bytes"), 0):
            errors.append(f"{artifact_name} bytes invalid")
        sha256 = artifact.get("sha256")
        if not isinstance(sha256, str) or SHA256_RE.fullmatch(sha256) is None:
            errors.append(f"{artifact_name} sha256 invalid")
        errors.extend(validate_datetime_field(artifact.get("created_at"), name=f"{artifact_name} created_at"))
        if not isinstance(artifact.get("required"), bool):
            errors.append(f"{artifact_name} required invalid")

    missing = sorted(ASYNC_REOPTIMIZE_REQUIRED_ARTIFACT_KINDS - required_kinds)
    if missing:
        errors.append(f"missing required artifact kinds: {','.join(missing)}")
    return errors


def validate_async_reoptimize_status_payload(payload: Any) -> list[str]:
    required = {
        "schema_version",
        "generated_at",
        "run_id",
        "status",
        "trigger_source",
        "requested_timeframes",
        "request_fingerprint",
        "service_version",
        "created_at",
        "started_at",
        "finished_at",
        "cancel_requested_at",
        "lease_owner",
        "lease_generation",
        "lease_acquired_at",
        "lease_expires_at",
        "heartbeat_at",
        "operator_action_required",
        "progress",
        "budgets",
        "recommendation",
        "fail_closed_reasons",
        "artifact_manifest",
        "errors",
    }
    errors = validate_object_shape(
        payload,
        name="payload",
        required=required,
        allowed=required,
    )
    if errors:
        return errors
    assert isinstance(payload, dict)
    if payload.get("schema_version") != "1.0.0":
        errors.append("schema_version mismatch")
    errors.extend(validate_datetime_field(payload.get("generated_at"), name="generated_at"))
    errors.extend(validate_run_id(payload.get("run_id"), name="run_id"))
    if payload.get("status") not in ASYNC_REOPTIMIZE_STATUSES:
        errors.append("unknown status")
    if payload.get("trigger_source") not in ASYNC_REOPTIMIZE_TRIGGER_SOURCES:
        errors.append("unknown trigger_source")
    errors.extend(validate_timeframe_list(payload.get("requested_timeframes"), name="requested_timeframes"))
    errors.extend(
        validate_nullable_string(
            payload.get("request_fingerprint"),
            name="request_fingerprint",
            max_len=256,
            pattern=FINGERPRINT_RE,
        )
    )
    errors.extend(
        validate_nullable_string(
            payload.get("service_version"),
            name="service_version",
            max_len=128,
        )
    )
    for key in (
        "created_at",
        "started_at",
        "finished_at",
        "cancel_requested_at",
        "lease_acquired_at",
        "lease_expires_at",
        "heartbeat_at",
    ):
        errors.extend(validate_datetime_field(payload.get(key), name=key, nullable=key != "created_at"))
    if payload.get("lease_owner") is not None and not isinstance(payload.get("lease_owner"), str):
        errors.append("lease_owner invalid")
    if not is_int_at_least(payload.get("lease_generation"), 0):
        errors.append("lease_generation invalid")
    if not isinstance(payload.get("operator_action_required"), bool):
        errors.append("operator_action_required invalid")
    errors.extend(validate_async_reoptimize_progress(payload.get("progress")))
    errors.extend(validate_async_reoptimize_budgets(payload.get("budgets")))
    errors.extend(validate_async_reoptimize_recommendation(payload.get("recommendation")))
    errors.extend(validate_fail_closed_reason_list(payload.get("fail_closed_reasons"), name="fail_closed_reasons"))
    errors.extend(validate_async_reoptimize_error_list(payload.get("errors"), name="errors"))
    manifest = payload.get("artifact_manifest")
    if manifest is not None:
        errors.extend(validate_async_reoptimize_artifact_manifest(manifest))
    return errors


def validate_async_reoptimize_enqueue_payload(payload: Any) -> list[str]:
    required = {
        "schema_version",
        "generated_at",
        "accepted",
        "run_id",
        "status",
        "trigger_source",
        "requested_timeframes",
        "request_fingerprint",
        "service_version",
        "queued_at",
        "status_route",
        "cancel_route",
        "active_run_id",
        "operator_action_required",
        "progress",
        "budgets",
        "recommendation",
        "fail_closed_reasons",
        "artifact_manifest",
        "errors",
    }
    errors = validate_object_shape(
        payload,
        name="payload",
        required=required,
        allowed=required,
    )
    if errors:
        return errors
    assert isinstance(payload, dict)
    if payload.get("schema_version") != "1.0.0":
        errors.append("schema_version mismatch")
    errors.extend(validate_datetime_field(payload.get("generated_at"), name="generated_at"))
    if not isinstance(payload.get("accepted"), bool):
        errors.append("accepted invalid")
    if payload.get("status") not in ASYNC_REOPTIMIZE_STATUSES:
        errors.append("unknown status")
    if payload.get("trigger_source") not in ASYNC_REOPTIMIZE_TRIGGER_SOURCES:
        errors.append("unknown trigger_source")
    errors.extend(validate_timeframe_list(payload.get("requested_timeframes"), name="requested_timeframes"))
    errors.extend(
        validate_nullable_string(
            payload.get("request_fingerprint"),
            name="request_fingerprint",
            max_len=256,
            pattern=FINGERPRINT_RE,
        )
    )
    errors.extend(
        validate_nullable_string(
            payload.get("service_version"),
            name="service_version",
            max_len=128,
        )
    )
    errors.extend(validate_datetime_field(payload.get("queued_at"), name="queued_at", nullable=True))
    for nullable_route in ("status_route", "cancel_route"):
        value = payload.get(nullable_route)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{nullable_route} invalid")
    errors.extend(validate_run_id(payload.get("run_id"), name="run_id", nullable=True))
    errors.extend(validate_run_id(payload.get("active_run_id"), name="active_run_id", nullable=True))
    if not isinstance(payload.get("operator_action_required"), bool):
        errors.append("operator_action_required invalid")
    errors.extend(validate_async_reoptimize_progress(payload.get("progress")))
    errors.extend(validate_async_reoptimize_budgets(payload.get("budgets")))
    errors.extend(validate_async_reoptimize_recommendation(payload.get("recommendation")))
    errors.extend(validate_fail_closed_reason_list(payload.get("fail_closed_reasons"), name="fail_closed_reasons"))
    errors.extend(validate_async_reoptimize_error_list(payload.get("errors"), name="errors"))
    manifest = payload.get("artifact_manifest")
    if manifest is not None:
        errors.extend(validate_async_reoptimize_artifact_manifest(manifest))
    return errors


def async_reoptimize_critical_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    critical: list[dict[str, Any]] = []
    manifest = payload.get("artifact_manifest")
    manifest_errors = manifest.get("errors", []) if isinstance(manifest, dict) else []
    for source in (payload.get("errors", []), manifest_errors):
        if not isinstance(source, list):
            continue
        critical.extend(
            error
            for error in source
            if isinstance(error, dict) and str(error.get("severity", "")).upper() == "CRITICAL"
        )
    progress = payload.get("progress", {})
    if isinstance(progress, dict) and int(progress.get("critical_error_count", 0) or 0) > 0:
        critical.append(
            {
                "code": "CRITICAL_ERROR_COUNT",
                "message": "progress critical_error_count is non-zero",
            }
        )
    return critical


def async_reoptimize_required_artifact_kinds(payload: dict[str, Any]) -> list[str]:
    manifest = payload.get("artifact_manifest")
    if not isinstance(manifest, dict):
        return []
    kinds: set[str] = set()
    for artifact in manifest.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("required") is True:
            kind = artifact.get("kind")
            if isinstance(kind, str):
                kinds.add(kind)
    return sorted(kinds)


def async_summary_from_status_payload(
    *,
    mode: str,
    payload: dict[str, Any],
    expected_fingerprint: str,
    poll_count: int = 0,
    elapsed_ms: int = 0,
    consumed_latest: bool = False,
) -> dict[str, Any]:
    progress = payload.get("progress", {}) if isinstance(payload.get("progress"), dict) else {}
    manifest = payload.get("artifact_manifest")
    summary = base_reoptimize_summary(mode)
    summary.update(
        {
            "pairs_processed": int(progress.get("pairs_completed", 0) or 0)
            + int(progress.get("pairs_skipped", 0) or 0)
            + int(progress.get("pairs_failed", 0) or 0),
            "cues_generated": int(progress.get("selected_rows_written", 0) or 0),
            "mode": mode,
            "evidence_valid": True,
            "run_id": payload.get("run_id"),
            "status": payload.get("status"),
            "trigger_source": payload.get("trigger_source"),
            "request_fingerprint": payload.get("request_fingerprint"),
            "expected_request_fingerprint": expected_fingerprint,
            "service_version": payload.get("service_version"),
            "poll_count": poll_count,
            "elapsed_ms": elapsed_ms,
            "consumed_latest": consumed_latest,
            "timed_out": False,
            "artifact_manifest_present": isinstance(manifest, dict),
            "artifact_required_kinds": async_reoptimize_required_artifact_kinds(payload),
            "first_status": payload.get("status"),
            "last_status": payload.get("status"),
        }
    )
    return summary


def evaluate_async_reoptimize_evidence(
    *,
    mode: str,
    payload: Any,
    timeframes: list[str],
    expected_fingerprint: str,
    max_age_seconds: int | None,
    now: dt.datetime | None = None,
    poll_count: int = 0,
    elapsed_ms: int = 0,
    consumed_latest: bool = False,
    require_fingerprint: bool = False,
    require_service_version: bool = False,
) -> dict[str, Any]:
    validation_errors = validate_async_reoptimize_status_payload(payload)
    extra: dict[str, Any] = {
        "poll_count": poll_count,
        "elapsed_ms": elapsed_ms,
        "expected_request_fingerprint": expected_fingerprint,
        "consumed_latest": consumed_latest,
    }
    if isinstance(payload, dict):
        extra.update(
            {
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "trigger_source": payload.get("trigger_source"),
                "request_fingerprint": payload.get("request_fingerprint"),
                "service_version": payload.get("service_version"),
                "artifact_manifest_present": isinstance(payload.get("artifact_manifest"), dict),
                "artifact_required_kinds": async_reoptimize_required_artifact_kinds(payload),
            }
        )
    if validation_errors:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_SCHEMA_MISMATCH",
            message="; ".join(validation_errors),
            timeframes=timeframes,
            extra=extra,
        )

    assert isinstance(payload, dict)
    status = str(payload.get("status"))
    if status in ASYNC_REOPTIMIZE_ACTIVE_STATUSES:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_NOT_TERMINAL",
            message=f"run status {status} did not reach a terminal state before deadline",
            timeframes=timeframes,
            extra=extra,
        )
    if status != "SUCCEEDED":
        return fail_closed_reoptimize_summary(
            mode=mode,
            code=f"ASYNC_REOPTIMIZE_{status}",
            message=f"terminal async reoptimization status is {status}",
            timeframes=timeframes,
            extra=extra,
        )

    requested_timeframes = payload.get("requested_timeframes", [])
    if requested_timeframes != timeframes:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_TIMEFRAME_MISMATCH",
            message=f"requested_timeframes={requested_timeframes!r} expected={timeframes!r}",
            timeframes=timeframes,
            extra=extra,
        )

    finished_at = parse_datetime_utc(payload.get("finished_at"))
    if finished_at is None:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_FINISHED_AT_MISSING",
            message="terminal SUCCEEDED status did not include a valid finished_at timestamp",
            timeframes=timeframes,
            extra=extra,
        )
    if max_age_seconds is not None:
        now = now or dt.datetime.now(dt.timezone.utc)
        age_seconds = (now - finished_at).total_seconds()
        extra["age_seconds"] = max(0, int(age_seconds))
        if age_seconds < 0 or age_seconds > max_age_seconds:
            return fail_closed_reoptimize_summary(
                mode=mode,
                code="ASYNC_REOPTIMIZE_STALE_STATUS",
                message=f"finished_at age {age_seconds:.0f}s exceeds {max_age_seconds}s",
                timeframes=timeframes,
                extra=extra,
            )

    actual_fingerprint = payload.get("request_fingerprint")
    if require_fingerprint and not actual_fingerprint:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_REQUEST_FINGERPRINT_MISSING",
            message="status payload does not include request compatibility evidence",
            timeframes=timeframes,
            extra=extra,
        )
    if actual_fingerprint and actual_fingerprint != expected_fingerprint:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_REQUEST_FINGERPRINT_MISMATCH",
            message=f"request_fingerprint={actual_fingerprint!r} expected={expected_fingerprint!r}",
            timeframes=timeframes,
            extra=extra,
        )
    if require_service_version and not payload.get("service_version"):
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_SERVICE_VERSION_MISSING",
            message="status payload does not include service version/build identity",
            timeframes=timeframes,
            extra=extra,
        )

    fail_closed_reasons = payload.get("fail_closed_reasons", [])
    if fail_closed_reasons:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_FAIL_CLOSED_REASONS",
            message=f"fail_closed_reasons={fail_closed_reasons!r}",
            timeframes=timeframes,
            extra=extra,
        )
    critical_errors = async_reoptimize_critical_errors(payload)
    if critical_errors:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_CRITICAL_ERRORS",
            message=f"critical_errors={critical_errors!r}",
            timeframes=timeframes,
            extra=extra,
        )

    manifest = payload.get("artifact_manifest")
    manifest_errors = validate_async_reoptimize_artifact_manifest(manifest)
    if manifest_errors:
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_ARTIFACT_INVALID",
            message="; ".join(manifest_errors),
            timeframes=timeframes,
            extra=extra,
        )
    if isinstance(manifest, dict):
        if manifest.get("run_id") != payload.get("run_id") or manifest.get("status") != status:
            return fail_closed_reoptimize_summary(
                mode=mode,
                code="ASYNC_REOPTIMIZE_ARTIFACT_MISMATCH",
                message="artifact manifest run/status does not match status payload",
                timeframes=timeframes,
                extra=extra,
            )

    progress = payload.get("progress", {})
    if (
        progress.get("phase") != "TERMINAL"
        or int(progress.get("planned_timeframe_count", -1) or -1) != len(timeframes)
        or int(progress.get("completed_timeframe_count", -1) or -1) != len(timeframes)
        or int(progress.get("failed_timeframe_count", 0) or 0) != 0
    ):
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_PROGRESS_INCOMPLETE",
            message="progress does not prove all requested timeframes completed successfully",
            timeframes=timeframes,
            extra=extra,
        )

    recommendation = payload.get("recommendation", {})
    if recommendation.get("decision") != "PROMOTION_CANDIDATE_AVAILABLE":
        return fail_closed_reoptimize_summary(
            mode=mode,
            code="ASYNC_REOPTIMIZE_RECOMMENDATION_HOLD",
            message=f"runner recommendation is {recommendation.get('decision')}",
            timeframes=timeframes,
            extra=extra,
        )

    return async_summary_from_status_payload(
        mode=mode,
        payload=payload,
        expected_fingerprint=expected_fingerprint,
        poll_count=poll_count,
        elapsed_ms=elapsed_ms,
        consumed_latest=consumed_latest,
    )


def attempt_async_reoptimize_cancel(
    *,
    args: argparse.Namespace,
    cancel_route: Any,
    enqueued_by_script: bool,
) -> dict[str, Any]:
    if not args.reoptimize_cancel_on_timeout or not enqueued_by_script:
        return {"cancel_attempted": False, "cancel_result": None, "cancel_error": None}
    if not is_safe_reoptimize_cancel_route(cancel_route):
        return {
            "cancel_attempted": False,
            "cancel_result": None,
            "cancel_error": "cancel endpoint unavailable",
        }
    try:
        payload = http_json(
            join_service_url(args.strategy_service_url, cancel_route),
            args.timeout_seconds,
            method="POST",
            payload={},
        )
    except Exception as error:  # noqa: BLE001
        return {
            "cancel_attempted": True,
            "cancel_result": "FAILED",
            "cancel_error": str(error),
        }
    if not isinstance(payload, dict):
        return {
            "cancel_attempted": True,
            "cancel_result": "FAILED",
            "cancel_error": "cancel response was not a JSON object",
        }
    return {
        "cancel_attempted": True,
        "cancel_result": payload.get("cancel_result"),
        "cancel_error": None,
    }


def collect_latest_successful_reoptimize_summary(
    *,
    args: argparse.Namespace,
    timeframes: list[str],
    expected_fingerprint: str,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        payload = http_json(
            join_service_url(args.strategy_service_url, "/v1/strategy/reoptimize/runs/latest"),
            args.timeout_seconds,
        )
    except Exception as error:  # noqa: BLE001
        return fail_closed_reoptimize_summary(
            mode="latest-successful",
            code="ASYNC_REOPTIMIZE_HTTP_ERROR",
            message=str(error),
            timeframes=timeframes,
            extra={"consumed_latest": True},
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return evaluate_async_reoptimize_evidence(
        mode="latest-successful",
        payload=payload,
        timeframes=timeframes,
        expected_fingerprint=expected_fingerprint,
        max_age_seconds=args.reoptimize_max_age_seconds,
        poll_count=1,
        elapsed_ms=elapsed_ms,
        consumed_latest=True,
        require_fingerprint=True,
        require_service_version=True,
    )


def poll_async_reoptimize_status(
    *,
    args: argparse.Namespace,
    status_route: str,
    deadline_monotonic: float,
    timeframes: list[str],
    expected_fingerprint: str,
    started_monotonic: float,
) -> dict[str, Any]:
    poll_count = 0
    first_status: str | None = None
    last_status: str | None = None
    interval = args.reoptimize_poll_initial_seconds
    status_url = join_service_url(args.strategy_service_url, status_route)

    while True:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            return fail_closed_reoptimize_summary(
                mode="async",
                code="ASYNC_REOPTIMIZE_TIMEOUT",
                message="deadline expired before a terminal async status was observed",
                timeframes=timeframes,
                extra={
                    "poll_count": poll_count,
                    "elapsed_ms": int((time.monotonic() - started_monotonic) * 1000),
                    "first_status": first_status,
                    "last_status": last_status,
                    "timed_out": True,
                    "expected_request_fingerprint": expected_fingerprint,
                },
            )
        try:
            payload = http_json(status_url, min(args.timeout_seconds, max(1, int(remaining))))
        except Exception as error:  # noqa: BLE001
            return fail_closed_reoptimize_summary(
                mode="async",
                code="ASYNC_REOPTIMIZE_HTTP_ERROR",
                message=str(error),
                timeframes=timeframes,
                extra={
                    "poll_count": poll_count,
                    "elapsed_ms": int((time.monotonic() - started_monotonic) * 1000),
                    "first_status": first_status,
                    "last_status": last_status,
                    "expected_request_fingerprint": expected_fingerprint,
                },
            )
        poll_count += 1
        validation_errors = validate_async_reoptimize_status_payload(payload)
        if validation_errors:
            return fail_closed_reoptimize_summary(
                mode="async",
                code="ASYNC_REOPTIMIZE_SCHEMA_MISMATCH",
                message="; ".join(validation_errors),
                timeframes=timeframes,
                extra={
                    "poll_count": poll_count,
                    "elapsed_ms": int((time.monotonic() - started_monotonic) * 1000),
                    "first_status": first_status,
                    "last_status": last_status,
                    "expected_request_fingerprint": expected_fingerprint,
                },
            )
        assert isinstance(payload, dict)
        status = str(payload.get("status"))
        first_status = first_status or status
        last_status = status
        if status in ASYNC_REOPTIMIZE_TERMINAL_STATUSES:
            summary = evaluate_async_reoptimize_evidence(
                mode="async",
                payload=payload,
                timeframes=timeframes,
                expected_fingerprint=expected_fingerprint,
                max_age_seconds=None,
                poll_count=poll_count,
                elapsed_ms=int((time.monotonic() - started_monotonic) * 1000),
                consumed_latest=False,
                require_fingerprint=False,
                require_service_version=False,
            )
            summary["first_status"] = first_status
            summary["last_status"] = last_status
            return summary

        sleep_seconds = min(interval, max(0.0, deadline_monotonic - time.monotonic()))
        if sleep_seconds <= 0:
            continue
        time.sleep(sleep_seconds)
        interval = min(args.reoptimize_poll_max_seconds, interval * 1.5)


def collect_async_reoptimize_summary(
    *,
    args: argparse.Namespace,
    timeframes: list[str],
    expected_fingerprint: str,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + args.reoptimize_max_wait_seconds
    enqueue_payload = {
        "timeframes": timeframes,
        "trigger_source": args.reoptimize_trigger_source,
    }
    try:
        enqueue_response = http_json(
            join_service_url(args.strategy_service_url, "/v1/strategy/reoptimize/runs"),
            min(args.timeout_seconds, max(1, int(args.reoptimize_max_wait_seconds))),
            method="POST",
            payload=enqueue_payload,
        )
    except Exception as error:  # noqa: BLE001
        return fail_closed_reoptimize_summary(
            mode="async",
            code="ASYNC_REOPTIMIZE_HTTP_ERROR",
            message=str(error),
            timeframes=timeframes,
            extra={"expected_request_fingerprint": expected_fingerprint},
        )

    enqueue_errors = validate_async_reoptimize_enqueue_payload(enqueue_response)
    enqueue_extra = {
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "expected_request_fingerprint": expected_fingerprint,
    }
    if isinstance(enqueue_response, dict):
        enqueue_extra.update(
            {
                "accepted": enqueue_response.get("accepted"),
                "run_id": enqueue_response.get("run_id"),
                "active_run_id": enqueue_response.get("active_run_id"),
                "status": enqueue_response.get("status"),
                "trigger_source": enqueue_response.get("trigger_source"),
                "status_route": enqueue_response.get("status_route"),
                "cancel_route": enqueue_response.get("cancel_route"),
                "request_fingerprint": enqueue_response.get("request_fingerprint"),
                "service_version": enqueue_response.get("service_version"),
            }
        )
    if enqueue_errors:
        return fail_closed_reoptimize_summary(
            mode="async",
            code="ASYNC_REOPTIMIZE_SCHEMA_MISMATCH",
            message="; ".join(enqueue_errors),
            timeframes=timeframes,
            extra=enqueue_extra,
        )

    assert isinstance(enqueue_response, dict)
    if enqueue_response.get("accepted") is not True:
        return fail_closed_reoptimize_summary(
            mode="async",
            code="ASYNC_REOPTIMIZE_ENQUEUE_REJECTED",
            message=str(
                enqueue_response.get("recommendation", {}).get(
                    "summary",
                    "async enqueue did not accept a run",
                )
            ),
            timeframes=timeframes,
            extra={
                **enqueue_extra,
                "fail_closed_reasons": enqueue_response.get("fail_closed_reasons", []),
            },
        )

    status_route = enqueue_response.get("status_route")
    if not isinstance(status_route, str) or not status_route.strip():
        return fail_closed_reoptimize_summary(
            mode="async",
            code="ASYNC_REOPTIMIZE_STATUS_ROUTE_MISSING",
            message="accepted enqueue response did not include a status_route",
            timeframes=timeframes,
            extra=enqueue_extra,
        )

    summary = poll_async_reoptimize_status(
        args=args,
        status_route=status_route,
        deadline_monotonic=deadline,
        timeframes=timeframes,
        expected_fingerprint=expected_fingerprint,
        started_monotonic=started,
    )
    summary.update(
        {
            "accepted": enqueue_response.get("accepted"),
            "active_run_id": enqueue_response.get("active_run_id"),
            "status_route": status_route,
            "cancel_route": enqueue_response.get("cancel_route"),
        }
    )
    if summary.get("timed_out") is True:
        summary.update(
            attempt_async_reoptimize_cancel(
                args=args,
                cancel_route=enqueue_response.get("cancel_route"),
                enqueued_by_script=enqueue_response.get("active_run_id") is None,
            )
        )
    return summary


def collect_reoptimize_summary(
    *,
    args: argparse.Namespace,
    timeframes: list[str],
    policy_path: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    mode = resolve_reoptimize_mode(args)
    if mode == "skip":
        return base_reoptimize_summary("skip")

    if mode == "sync":
        reopt_payload = {"timeframes": timeframes}
        reopt_response = http_json(
            join_service_url(args.strategy_service_url, "/v1/strategy/pairs/reoptimize"),
            args.timeout_seconds,
            method="POST",
            payload=reopt_payload,
        )
        summary = base_reoptimize_summary("sync")
        summary.update(
            {
                "pairs_processed": int(reopt_response.get("pairs_processed", 0)),
                "cues_generated": int(reopt_response.get("cues_generated", 0)),
                "cost_gate_pass": int(reopt_response.get("cost_gate_pass", 0)),
                "cost_gate_fail": int(reopt_response.get("cost_gate_fail", 0)),
                "errors": reopt_response.get("errors", []),
                "evidence_valid": True,
            }
        )
        return summary

    expected_fingerprint = expected_reoptimize_request_fingerprint(
        profile=args.profile,
        timeframes=timeframes,
        policy_path=policy_path,
        policy=policy,
    )
    if mode == "latest-successful":
        return collect_latest_successful_reoptimize_summary(
            args=args,
            timeframes=timeframes,
            expected_fingerprint=expected_fingerprint,
        )
    return collect_async_reoptimize_summary(
        args=args,
        timeframes=timeframes,
        expected_fingerprint=expected_fingerprint,
    )


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

    reopt_summary = collect_reoptimize_summary(
        args=args,
        timeframes=timeframes,
        policy_path=policy_path,
        policy=policy,
    )

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
    if reopt_summary.get("force_hold"):
        decision = "HOLD"
        error_codes = reopt_summary.get("error_codes", []) or ["ASYNC_REOPTIMIZE_FAIL_CLOSED"]
        async_reasons = [f"reoptimize_fail_closed:{code}" for code in error_codes]
        decision_reasons = [
            *async_reasons,
            "Fail-closed async reoptimization evidence forced HOLD.",
            *decision_reasons,
        ]

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
            "errors": [
                {
                    "pair_id": "*",
                    "timeframe": "1m",
                    "code": "REPORTER_EXECUTION_FAILED",
                    "severity": "CRITICAL",
                    "error": str(error),
                }
            ],
            "mode": resolve_reoptimize_mode(args),
            "force_hold": True,
            "evidence_valid": False,
            "error_codes": ["REPORTER_EXECUTION_FAILED"],
            "fail_closed_reasons": ["REPORTER_EXECUTION_FAILED"],
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
        "--reoptimize-mode",
        choices=REOPTIMIZE_MODES,
        default="sync",
        help="Reoptimization mode. --skip-reoptimize remains compatibility sugar for skip.",
    )
    parser.add_argument("--reoptimize-max-wait-seconds", type=int, default=300)
    parser.add_argument("--reoptimize-poll-initial-seconds", type=float, default=2.0)
    parser.add_argument("--reoptimize-poll-max-seconds", type=float, default=30.0)
    parser.add_argument("--reoptimize-max-age-seconds", type=int, default=3600)
    parser.add_argument(
        "--reoptimize-trigger-source",
        choices=sorted(ASYNC_REOPTIMIZE_TRIGGER_SOURCES),
        default="MANUAL_API",
    )
    parser.add_argument(
        "--reoptimize-cancel-on-timeout",
        dest="reoptimize_cancel_on_timeout",
        action="store_true",
    )
    parser.add_argument(
        "--no-reoptimize-cancel-on-timeout",
        dest="reoptimize_cancel_on_timeout",
        action="store_false",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/strategy_tuning/report.json",
    )
    parser.set_defaults(reoptimize_cancel_on_timeout=False)
    args = parser.parse_args()

    args.window_minutes = max(1, min(args.window_minutes, 24 * 60))
    args.timeout_seconds = max(3, args.timeout_seconds)
    args.limit = max(1, min(args.limit, 100))
    args.reoptimize_max_wait_seconds = max(1, min(args.reoptimize_max_wait_seconds, 3600))
    args.reoptimize_poll_initial_seconds = max(
        0.1,
        min(args.reoptimize_poll_initial_seconds, 60.0),
    )
    args.reoptimize_poll_max_seconds = max(
        args.reoptimize_poll_initial_seconds,
        min(args.reoptimize_poll_max_seconds, 120.0),
    )
    args.reoptimize_max_age_seconds = max(1, min(args.reoptimize_max_age_seconds, 86_400))

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
