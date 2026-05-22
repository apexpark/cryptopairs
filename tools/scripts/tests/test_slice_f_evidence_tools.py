from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import slice_f_evidence_check as evidence_check  # noqa: E402
import slice_f_evidence_manifest_from_bundle as manifest_from_bundle  # noqa: E402
import validate_slice_f_alert_rules as alert_rules  # noqa: E402


def load_example(name: str) -> dict[str, object]:
    path = REPO_ROOT / "specs" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_slice_f_checker_accepts_zero_recanonicalized_rows_example() -> None:
    manifest = load_example("slice_f_reoptimize_canary_evidence_manifest.zero_recanonicalized_rows.example.json")

    assert evidence_check.validate_manifest(manifest) == []


def test_slice_f_checker_rejects_dirty_host_identity() -> None:
    manifest = copy.deepcopy(load_example("slice_f_reoptimize_canary_evidence_manifest.pass.example.json"))
    manifest["repo_identity"]["dirty_status"] = "DIRTY"  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = evidence_check.validate_manifest(manifest)

    assert "host/repo dirty status must be CLEAN" in errors


def test_slice_f_checker_rejects_failed_unknown_status() -> None:
    manifest = copy.deepcopy(load_example("slice_f_reoptimize_canary_evidence_manifest.pass.example.json"))
    status_payload = manifest["status_payloads"][0]  # type: ignore[index]
    status_payload["status"] = "FAILED"  # type: ignore[index]
    status_payload["fail_closed_reasons"] = ["UNKNOWN_STATUS"]  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = evidence_check.validate_manifest(manifest)

    assert "status is fail-closed and cannot pass Slice F evidence: FAILED" in errors
    assert "status payload contains blocking fail-closed reason: UNKNOWN_STATUS" in errors


def test_slice_f_checker_rejects_runner_enabled_without_operator_canary() -> None:
    manifest = copy.deepcopy(load_example("slice_f_reoptimize_canary_evidence_manifest.pass.example.json"))
    manifest["canary_scope"]["runner_enabled_before"] = True  # type: ignore[index]
    manifest["overall_pass"] = False
    manifest["recommended_action"] = "KEEP_DISABLED_KEEP_HOLD"

    errors = evidence_check.validate_manifest(manifest)

    assert "runner must be disabled before Slice F evidence window" in errors


def test_slice_f_alert_template_covers_required_rules() -> None:
    template = alert_rules.load_json(
        REPO_ROOT / "infra" / "alerts" / "slice_f_reoptimization_alert_rules.example.json"
    )

    assert alert_rules.validate_template(template) == []


def test_slice_f_manifest_generator_treats_repo_alert_template_as_not_deployed() -> None:
    template = alert_rules.load_json(
        REPO_ROOT / "infra" / "alerts" / "slice_f_reoptimization_alert_rules.example.json"
    )

    alerting = manifest_from_bundle.parse_alerting(json.dumps(template))

    assert alerting["configured"] is False
    assert alerting["routed"] is False
    assert alerting["missing_data_blocks"] is False
    assert {rule["id"] for rule in alerting["rules"]} == evidence_check.REQUIRED_ALERT_RULES
    assert all(rule["configured"] is False for rule in alerting["rules"])


def test_slice_f_raw_bundle_manifest_fails_closed_for_missing_alerting_thresholds_and_unknown_status(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "host_identity.txt").write_text(
        "Fri May 22 00:00:00 UTC 2026\n"
        "cryptopairs-data-01\n"
        "## main...origin/main\n"
        "85240676e60818d08df86826e857d73b31f8c78e\n",
        encoding="utf-8",
    )
    (tmp_path / "strategy_reopt_flags.txt").write_text(
        "\n".join(
            [
                "STRATEGY_REOPT_HEARTBEAT_INTERVAL_SECONDS=15",
                "STRATEGY_REOPT_INTERVAL_SECS=3600",
                "STRATEGY_REOPT_LEASE_TTL_SECONDS=120",
                "STRATEGY_REOPT_MAX_ARTIFACT_BYTES=10485760",
                "STRATEGY_REOPT_MAX_DB_WRITE_BATCH_SIZE=25",
                "STRATEGY_REOPT_MAX_IN_FLIGHT_PAIR_EVALUATIONS=1",
                "STRATEGY_REOPT_MAX_PAIRS_PER_RUN=96",
                "STRATEGY_REOPT_MAX_PAIRS_PER_TIMEFRAME=32",
                "STRATEGY_REOPT_MAX_RUN_SECONDS=900",
                "STRATEGY_REOPT_MAX_TIMEFRAME_SECONDS=300",
                "STRATEGY_REOPT_MIN_COOLDOWN_SECONDS=3600",
                "STRATEGY_REOPT_WORKER_ENABLED=false",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "reopt_latest_before.txt").write_text(
        'HTTP/1.1 200 OK\n\n{"status":"FAILED","recommendation":{"decision":"HOLD"},'
        '"budgets":{"budget_state":"WITHIN_BUDGET"},"fail_closed_reasons":["UNKNOWN_STATUS"]}\n',
        encoding="utf-8",
    )
    (tmp_path / "metrics_before.txt").write_text(
        '\n'.join(
            [
                'strategy_reoptimize_active_runs{status="QUEUED"} 0',
                'strategy_reoptimize_active_runs{status="LEASED"} 0',
                'strategy_reoptimize_active_runs{status="RUNNING"} 0',
                'strategy_reoptimize_active_runs{status="CANCEL_REQUESTED"} 0',
                'strategy_reoptimize_status_unknown_total{reason="STATUS_ROW_MISSING"} 1',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "alerting_services.txt").write_text(
        "No alerting surface configured or available to operator on this host.\n",
        encoding="utf-8",
    )
    (tmp_path / "alerts_before.txt").write_text(
        "No alerting surface configured or available to operator on this host.\n",
        encoding="utf-8",
    )
    (tmp_path / "strategy_logs_before.txt").write_text(
        "2026-05-21T05:07:48Z INFO strategy_service: strategy reoptimize worker disabled\n",
        encoding="utf-8",
    )
    (tmp_path / "docker_stats_3x_before.txt").write_text("CPU baseline captured without approved threshold\n", encoding="utf-8")
    (tmp_path / "hot_endpoint_latency_baseline.txt").write_text("GET /v1/strategy/pairs/cues 0.005\n", encoding="utf-8")
    (tmp_path / "execution_flags.txt").write_text("EXECUTION_DISPATCH_MODE=fail_closed\n", encoding="utf-8")
    (tmp_path / "promotion_revert_gating.txt").write_text(
        "PROMOTE confirm=true is required\nREVERT confirm=true is required\n",
        encoding="utf-8",
    )
    (tmp_path / "repair_provenance_inventory.txt").write_text(
        "RECANONICALIZED_LEGACY_ROW count=0\n",
        encoding="utf-8",
    )
    (tmp_path / "trade_now_1m_before.json").write_text(
        '{"tradable_now":[],"watchlist":[],"excluded":[]}\n',
        encoding="utf-8",
    )

    manifest = manifest_from_bundle.build_manifest(
        tmp_path,
        "2026-05-22T00:00:00Z",
        "slice-f-test-bundle",
    )

    assert manifest["overall_pass"] is False
    assert "ALERTING_NOT_READY" in manifest["stop_conditions"]
    assert "THRESHOLDS_NOT_APPROVED" in manifest["stop_conditions"]
    assert "STATUS_INVALID_OR_UNKNOWN" in manifest["stop_conditions"]
    assert "UNKNOWN_STATUS" in manifest["stop_conditions"]
    assert evidence_check.validate_manifest(manifest)
