from __future__ import annotations

import copy
import json
import pathlib
import sys

from jsonschema import Draft202012Validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import production_async_enablement_evidence_check as pae_check  # noqa: E402
import production_async_enablement_manifest_from_bundle as pae_manifest  # noqa: E402


def load_example(name: str) -> dict[str, object]:
    path = REPO_ROOT / "specs" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def validate_against_schema(example: dict[str, object]) -> None:
    schema = json.loads(
        (
            REPO_ROOT
            / "specs"
            / "contracts"
            / "production_async_reoptimize_enablement_evidence_manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert not errors, [error.message for error in errors]


def test_pae_pass_example_validates_schema_and_semantics() -> None:
    example = load_example("production_async_reoptimize_enablement_evidence_manifest.pass.example.json")

    validate_against_schema(example)
    assert pae_check.validate_manifest(example) == []


def test_pae_fail_example_is_schema_valid_but_semantically_blocked() -> None:
    example = load_example("production_async_reoptimize_enablement_evidence_manifest.fail.example.json")

    validate_against_schema(example)
    errors = pae_check.validate_manifest(example)

    assert "production enablement approval is missing" in errors
    assert "scheduler must be enabled during approved window" in errors
    assert "artifact manifest missing" in errors


def test_pae_checker_rejects_manual_run_contamination() -> None:
    manifest = copy.deepcopy(
        load_example("production_async_reoptimize_enablement_evidence_manifest.pass.example.json")
    )
    manifest["status_evidence"]["manual_run_count"] = 1  # type: ignore[index]
    manifest["metrics"]["manual_enqueued_delta"] = 1  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = pae_check.validate_manifest(manifest)

    assert "manual run contamination detected" in errors
    assert "manual enqueue delta must be zero" in errors


def test_pae_checker_rejects_scheduler_enabled_after_rollback() -> None:
    manifest = copy.deepcopy(
        load_example("production_async_reoptimize_enablement_evidence_manifest.pass.example.json")
    )
    manifest["enablement_scope"]["scheduler_enabled_after"] = True  # type: ignore[index]
    manifest["metrics"]["active_runs_after"]["RUNNING"] = 1  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = pae_check.validate_manifest(manifest)

    assert "worker and scheduler must be disabled after rollback" in errors
    assert "active async gauges were nonzero after rollback" in errors


def test_pae_checker_rejects_artifact_scope_mismatch() -> None:
    manifest = copy.deepcopy(
        load_example("production_async_reoptimize_enablement_evidence_manifest.pass.example.json")
    )
    manifest["status_evidence"]["artifact_trigger_source"] = "MANUAL_API"  # type: ignore[index]
    manifest["status_evidence"]["artifact_requested_timeframes"] = ["1m", "15m"]  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = pae_check.validate_manifest(manifest)

    assert "artifact trigger source must be SCHEDULED" in errors
    assert "artifact requested timeframes do not match scope" in errors


def test_pae_generator_builds_passing_manifest_from_bundle(tmp_path: pathlib.Path) -> None:
    approval = {
        "present": True,
        "reference": "operator-approved-pae-test",
        "approved_at": "2026-05-27T00:00:00Z",
        "approved_by": "operator",
        "scope": "one scheduled 1m run",
        "approved_timeframes": ["1m"],
        "expected_scheduled_run_count": 1,
        "scheduler_window_start": "2026-05-27T00:05:00Z",
        "scheduler_window_end": "2026-05-27T00:15:00Z",
        "abort_owner": "operator",
        "rollback_owner": "operator",
        "host_evidence_owner": "operator",
    }
    alert_rules = [
        {
            "id": rule_id,
            "configured": True,
            "routed": True,
            "query_present": True,
            "before_state_captured": True,
            "during_state_captured": True,
            "after_state_captured": True,
        }
        for rule_id in sorted(pae_check.REQUIRED_ALERT_RULES)
    ]
    threshold = load_example("slice_f_threshold_approval.example.json")

    files = {
        "host_identity.txt": "## main...origin/main\n86af22f8d18d3e8c251e5fcae60866ee88f7b95d\n",
        "operator_approval.json": json.dumps(approval),
        "runner_flags_before.txt": "STRATEGY_REOPT_WORKER_ENABLED=false\nSTRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED=false\n",
        "runner_flags_during.txt": "STRATEGY_REOPT_WORKER_ENABLED=true\nSTRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED=true\n",
        "runner_flags_after.txt": "STRATEGY_REOPT_WORKER_ENABLED=false\nSTRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED=false\n",
        "budget_values.txt": "STRATEGY_REOPT_MAX_RUN_SECONDS=300\n",
        "status_progression.json": json.dumps({"progression": ["QUEUED", "LEASED", "RUNNING", "SUCCEEDED"]}),
        "status_after.json": json.dumps(
            {
                "status": "SUCCEEDED",
                "recommendation": {"decision": "PROMOTION_CANDIDATE_AVAILABLE"},
                "budgets": {"budget_state": "WITHIN_BUDGET"},
                "fail_closed_reasons": [],
            }
        ),
        "metrics_before.prom": "\n".join(
            [
                'strategy_reoptimize_active_runs{status="QUEUED"} 0',
                'strategy_reoptimize_active_runs{status="LEASED"} 0',
                'strategy_reoptimize_active_runs{status="RUNNING"} 0',
                'strategy_reoptimize_active_runs{status="CANCEL_REQUESTED"} 0',
                'strategy_reoptimize_scheduler_enqueue_total{trigger="SCHEDULED",result="ENQUEUED"} 0',
            ]
        ),
        "metrics_during.prom": "\n".join(
            [
                'strategy_reoptimize_active_runs{status="QUEUED"} 0',
                'strategy_reoptimize_active_runs{status="LEASED"} 0',
                'strategy_reoptimize_active_runs{status="RUNNING"} 1',
                'strategy_reoptimize_active_runs{status="CANCEL_REQUESTED"} 0',
            ]
        ),
        "metrics_after.prom": "\n".join(
            [
                'strategy_reoptimize_active_runs{status="QUEUED"} 0',
                'strategy_reoptimize_active_runs{status="LEASED"} 0',
                'strategy_reoptimize_active_runs{status="RUNNING"} 0',
                'strategy_reoptimize_active_runs{status="CANCEL_REQUESTED"} 0',
                'strategy_reoptimize_scheduler_enqueue_total{trigger="SCHEDULED",result="ENQUEUED"} 1',
            ]
        ),
        "alerts_config.json": json.dumps(
            {
                "configured": True,
                "routed": True,
                "missing_data_blocks": True,
                "evidence_state": "DEPLOYED",
                "rules": alert_rules,
            }
        ),
        "alerts_before.json": "{}",
        "alerts_during.json": "{}",
        "alerts_after.json": "{}",
        "strategy_logs_before.log": "reoptimize_run_enqueue_attempted\n",
        "strategy_logs_during.log": "reoptimize_run_enqueued\nreoptimize_lease_acquired\nreoptimize_lease_heartbeat\n",
        "strategy_logs_after.log": "reoptimize_recommendation_finalized\n",
        "threshold_approval.json": json.dumps(threshold),
        "cpu_baseline.txt": "CPU baseline captured\n",
        "cpu_during_after.txt": "CPU after within threshold\n",
        "hot_endpoint_latency_baseline.txt": "GET /v1/strategy/pairs/trade-now baseline\n",
        "hot_endpoint_latency_after.txt": "GET /v1/strategy/pairs/trade-now after\n",
        "artifact_manifest.json": json.dumps(
            {
                "schema_version": "1.0.0",
                "complete": True,
                "status": "SUCCEEDED",
                "trigger_source": "SCHEDULED",
                "requested_timeframes": ["1m"],
            }
        ),
        "repair_provenance_inventory.txt": "RECANONICALIZED_LEGACY_ROW count=0\n",
        "trade_now_repair_provenance_block.json": '{"tradable_now":[],"watchlist":[],"excluded":[]}\n',
        "execution_flags.txt": "EXECUTION_DISPATCH_MODE=fail_closed\n",
        "promotion_revert_gating.txt": (
            "=== PROMOTE without confirm ===\n"
            "HTTP/1.1 400 Bad Request\n\n"
            '{"error":"confirm=true is required to run maintenance actions"}\n'
            "=== REVERT without confirm ===\n"
            "HTTP/1.1 400 Bad Request\n\n"
            '{"error":"confirm=true is required to run maintenance actions"}\n'
        ),
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    manifest = pae_manifest.build_manifest(
        tmp_path,
        "2026-05-27T00:20:00Z",
        "pae-test-bundle",
    )

    assert manifest["overall_pass"] is True
    assert manifest["recommended_action"] == "READY_FOR_OPERATOR_REVIEW"
    validate_against_schema(manifest)
    assert pae_check.validate_manifest(manifest) == []
