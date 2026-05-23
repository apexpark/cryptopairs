from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import strategy_tuning_apply as apply_script  # noqa: E402
import strategy_maintenance_cycle as cycle_script  # noqa: E402
import strategy_tuning_report as report_script  # noqa: E402


def test_parse_timeframes_dedup_and_filter() -> None:
    values = report_script.parse_timeframes("1m,15m,1m,2h,1h")
    assert values == ["1m", "15m", "1h"]


def test_parse_timeframes_fallback_to_defaults() -> None:
    values = report_script.parse_timeframes("2h,4h")
    assert values == ["1m", "15m", "1h"]


def test_evaluate_checks_and_promote_decision() -> None:
    thresholds = {
        "min_actionable_ratio_delta": 0.0,
        "min_cost_gate_pass_ratio_delta": 0.0,
        "max_guardrail_block_ratio_delta": 0.03,
        "max_shadow_disagreement_ratio_delta": 0.02,
        "max_reopt_error_count": 0,
        "allow_p1_alerts": False,
        "allow_p2_alerts": True,
    }
    deltas = {
        "actionable_ratio_mean": 0.01,
        "cost_gate_pass_ratio_mean": 0.02,
        "shadow_disagreement_ratio_mean": 0.0,
        "guardrail_block_ratio_mean": -0.01,
    }
    checks = report_script.evaluate_checks(
        thresholds=thresholds,
        deltas=deltas,
        reopt_error_count=0,
        p1_triggered=0,
        p2_triggered=1,
    )
    decision, reasons = report_script.decide(
        profile="candidate",
        baseline_report_present=True,
        checks=checks,
    )
    assert all(check["pass"] for check in checks)
    assert decision == "PROMOTE"
    assert reasons


def test_failed_check_reverts_candidate() -> None:
    checks = [
        {"name": "actionable_ratio_delta", "pass": False, "detail": "delta=-0.01"},
    ]
    decision, reasons = report_script.decide(
        profile="candidate",
        baseline_report_present=True,
        checks=checks,
    )
    assert decision == "REVERT"
    assert reasons[0].startswith("check_failed:")


def test_build_comparison_without_baseline() -> None:
    aggregate = {
        "actionable_ratio_mean": 0.1,
        "cost_gate_pass_ratio_mean": 0.2,
        "shadow_disagreement_ratio_mean": 0.0,
        "guardrail_block_ratio_mean": 0.3,
    }
    comparison, deltas = report_script.build_comparison(aggregate, None)
    assert comparison["baseline_report"] is None
    assert deltas["actionable_ratio_mean"] == 0.0


def test_apply_values_replaces_and_appends() -> None:
    lines = [
        "FOO=1\n",
        "STRATEGY_LOOKBACK_BARS_1M=520\n",
        "BAR=2\n",
    ]
    updates = {
        "STRATEGY_LOOKBACK_BARS_1M": 700,
        "STRATEGY_LOOKBACK_BARS_15M": 900,
        "STRATEGY_LOOKBACK_BARS_1H": 1200,
    }
    updated = apply_script.apply_values(lines, updates)
    text = "".join(updated)
    assert "STRATEGY_LOOKBACK_BARS_1M=700" in text
    assert "STRATEGY_LOOKBACK_BARS_15M=900" in text
    assert "STRATEGY_LOOKBACK_BARS_1H=1200" in text


def test_resolve_profile_modes() -> None:
    assert apply_script.resolve_profile("promote", None) == "candidate"
    assert apply_script.resolve_profile("revert", None) == "baseline"
    assert apply_script.resolve_profile("set-profile", "baseline") == "baseline"


def test_profile_values_requires_all_keys() -> None:
    policy = {
        "profiles": {
            "baseline": {
                "STRATEGY_LOOKBACK_BARS_1M": 520,
                "STRATEGY_LOOKBACK_BARS_15M": 720,
                "STRATEGY_LOOKBACK_BARS_1H": 900,
            }
        }
    }
    resolved = apply_script.profile_values(policy, "baseline")
    assert resolved["STRATEGY_LOOKBACK_BARS_1H"] == 900


def test_choose_restore_mode() -> None:
    baseline = {
        "STRATEGY_LOOKBACK_BARS_1M": 520,
        "STRATEGY_LOOKBACK_BARS_15M": 720,
        "STRATEGY_LOOKBACK_BARS_1H": 900,
    }
    candidate = {
        "STRATEGY_LOOKBACK_BARS_1M": 700,
        "STRATEGY_LOOKBACK_BARS_15M": 900,
        "STRATEGY_LOOKBACK_BARS_1H": 1200,
    }
    custom = {
        "STRATEGY_LOOKBACK_BARS_1M": 600,
        "STRATEGY_LOOKBACK_BARS_15M": 850,
        "STRATEGY_LOOKBACK_BARS_1H": 1000,
    }

    assert (
        cycle_script.choose_restore_mode(
            original_values=baseline,
            baseline_values=baseline,
            candidate_values=candidate,
        )
        == "revert"
    )
    assert (
        cycle_script.choose_restore_mode(
            original_values=candidate,
            baseline_values=baseline,
            candidate_values=candidate,
        )
        == "promote"
    )
    assert (
        cycle_script.choose_restore_mode(
            original_values=custom,
            baseline_values=baseline,
            candidate_values=candidate,
        )
        == "custom"
    )


def test_human_action_recommendation_mapping() -> None:
    assert cycle_script.human_action_recommendation("PROMOTE") == "PROMOTE"
    assert cycle_script.human_action_recommendation("revert") == "REVERT"
    assert cycle_script.human_action_recommendation("HOLD") == "LEAVE AS IS"


def test_render_human_summary_contains_recommendation() -> None:
    summary = cycle_script.render_human_summary(
        generated_at="2026-02-22T23:41:28Z",
        run_id="2026-02-22T23-41-28Z",
        status="PASS",
        decision="HOLD",
        decision_reasons=["candidate report step failed"],
        step_pass_summary={"health": True, "candidate_report": False},
        artifacts={
            "baseline_report": "artifacts/strategy_tuning/runs/example/baseline_report.json",
            "decision_report": "artifacts/strategy_tuning/runs/example/maintenance_decision.json",
            "cycle_report": "artifacts/strategy_tuning/runs/example/maintenance_cycle_report.json",
        },
    )

    assert "Recommended operator action: LEAVE AS IS" in summary
    assert "candidate report step failed" in summary
    assert "- health: PASS" in summary
    assert "- candidate_report: FAIL" in summary


def async_artifact_manifest(
    *,
    run_id: str = "reopt_test_001",
    status: str = "SUCCEEDED",
    request_fingerprint: str = "strategy_tuning_report:v1:test",
    service_version: str = "test-version",
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-05-19T00:00:02Z",
        "run_id": run_id,
        "status": status,
        "trigger_source": "MAINTENANCE_REPORT",
        "request_fingerprint": request_fingerprint,
        "service_version": service_version,
        "artifact_root": "artifacts/strategy_reoptimize",
        "run_artifact_dir": f"runs/{run_id}",
        "artifact_download_route": "DEFERRED_NO_DOWNLOAD_ROUTE",
        "complete": True,
        "total_bytes": 40,
        "artifacts": [
            {
                "kind": "REQUEST",
                "path": f"runs/{run_id}/request.json",
                "content_type": "application/json",
                "bytes": 10,
                "sha256": "a" * 64,
                "created_at": "2026-05-19T00:00:00Z",
                "required": True,
            },
            {
                "kind": "PROGRESS",
                "path": f"runs/{run_id}/progress.json",
                "content_type": "application/json",
                "bytes": 10,
                "sha256": "b" * 64,
                "created_at": "2026-05-19T00:00:01Z",
                "required": True,
            },
            {
                "kind": "SUMMARY",
                "path": f"runs/{run_id}/summary.json",
                "content_type": "application/json",
                "bytes": 10,
                "sha256": "c" * 64,
                "created_at": "2026-05-19T00:00:02Z",
                "required": True,
            },
            {
                "kind": "ERRORS",
                "path": f"runs/{run_id}/errors.json",
                "content_type": "application/json",
                "bytes": 10,
                "sha256": "d" * 64,
                "created_at": "2026-05-19T00:00:02Z",
                "required": True,
            },
        ],
        "fail_closed_reasons": [],
        "errors": [],
    }


def async_status_payload(
    *,
    status: str = "SUCCEEDED",
    request_fingerprint: str | None = "strategy_tuning_report:v1:test",
    service_version: str | None = "test-version",
    finished_at: str | None = "2026-05-19T00:00:02Z",
    artifact_manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    run_id = "reopt_test_001"
    manifest = artifact_manifest
    if manifest is None and status == "SUCCEEDED":
        manifest = async_artifact_manifest(
            run_id=run_id,
            status=status,
            request_fingerprint=request_fingerprint or "strategy_tuning_report:v1:test",
            service_version=service_version or "test-version",
        )
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-05-19T00:00:03Z",
        "run_id": run_id,
        "status": status,
        "trigger_source": "MAINTENANCE_REPORT",
        "requested_timeframes": ["1m", "15m", "1h"],
        "request_fingerprint": request_fingerprint,
        "service_version": service_version,
        "created_at": "2026-05-19T00:00:00Z",
        "started_at": "2026-05-19T00:00:01Z",
        "finished_at": finished_at,
        "cancel_requested_at": None,
        "lease_owner": "test-worker",
        "lease_generation": 1,
        "lease_acquired_at": "2026-05-19T00:00:01Z",
        "lease_expires_at": None,
        "heartbeat_at": "2026-05-19T00:00:01Z",
        "operator_action_required": False,
        "progress": {
            "phase": "TERMINAL",
            "requested_timeframes": ["1m", "15m", "1h"],
            "active_timeframe": None,
            "planned_timeframe_count": 3,
            "completed_timeframe_count": 3,
            "failed_timeframe_count": 0,
            "total_pairs_planned": 48,
            "pairs_completed": 48,
            "pairs_skipped": 0,
            "pairs_failed": 0,
            "selected_rows_written": 48,
            "drift_rows_written": 0,
            "transition_counts": {
                "initialize_decisions": 1,
                "unchanged_decisions": 45,
                "champion_locks": 2,
                "champion_promotions": 0,
            },
            "critical_error_count": 0,
            "non_critical_error_count": 0,
            "percent_complete": 100,
            "last_heartbeat_at": "2026-05-19T00:00:01Z",
        },
        "budgets": {
            "budget_state": "WITHIN_BUDGET",
            "max_run_seconds": 900,
            "max_timeframe_seconds": 300,
            "max_pairs_per_run": 96,
            "max_pairs_per_timeframe": 32,
            "max_in_flight_pair_evaluations": 1,
            "max_db_write_batch_size": 25,
            "max_artifact_bytes": 10485760,
            "min_cooldown_seconds": 3600,
            "lease_ttl_seconds": 120,
            "heartbeat_interval_seconds": 15,
            "exhausted_budget": None,
        },
        "recommendation": {
            "decision": "PROMOTION_CANDIDATE_AVAILABLE",
            "reason_codes": [],
            "summary": "Run completed and evidence is available for operator review.",
        },
        "fail_closed_reasons": [],
        "artifact_manifest": manifest,
        "errors": [],
    }


def test_async_reoptimize_unknown_status_fails_closed() -> None:
    payload = async_status_payload(status="NOT_A_STATUS", artifact_manifest=None)
    summary = report_script.evaluate_async_reoptimize_evidence(
        mode="async",
        payload=payload,
        timeframes=["1m", "15m", "1h"],
        expected_fingerprint="strategy_tuning_report:v1:test",
        max_age_seconds=None,
    )

    assert summary["force_hold"] is True
    assert summary["error_codes"] == ["ASYNC_REOPTIMIZE_SCHEMA_MISMATCH"]
    assert summary["mode"] == "async"


def test_latest_successful_requires_request_fingerprint() -> None:
    payload = async_status_payload(request_fingerprint=None)
    summary = report_script.evaluate_async_reoptimize_evidence(
        mode="latest-successful",
        payload=payload,
        timeframes=["1m", "15m", "1h"],
        expected_fingerprint="strategy_tuning_report:v1:test",
        max_age_seconds=3600,
        now=report_script.parse_datetime_utc("2026-05-19T00:00:04Z"),
        consumed_latest=True,
        require_fingerprint=True,
        require_service_version=True,
    )

    assert summary["force_hold"] is True
    assert summary["error_codes"] == ["ASYNC_REOPTIMIZE_REQUEST_FINGERPRINT_MISSING"]


def test_latest_successful_rejects_schema_invalid_artifact_manifest() -> None:
    manifest = async_artifact_manifest()
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    assert isinstance(artifacts[0], dict)
    artifacts[0].pop("content_type")
    payload = async_status_payload(artifact_manifest=manifest)

    summary = report_script.evaluate_async_reoptimize_evidence(
        mode="latest-successful",
        payload=payload,
        timeframes=["1m", "15m", "1h"],
        expected_fingerprint="strategy_tuning_report:v1:test",
        max_age_seconds=3600,
        now=report_script.parse_datetime_utc("2026-05-19T00:00:04Z"),
        consumed_latest=True,
        require_fingerprint=True,
        require_service_version=True,
    )

    assert summary["force_hold"] is True
    assert summary["error_codes"] == ["ASYNC_REOPTIMIZE_SCHEMA_MISMATCH"]
    assert "content_type" in summary["errors"][0]["error"]


def test_latest_successful_rejects_unexpected_status_field() -> None:
    payload = async_status_payload()
    payload["unexpected"] = True

    summary = report_script.evaluate_async_reoptimize_evidence(
        mode="latest-successful",
        payload=payload,
        timeframes=["1m", "15m", "1h"],
        expected_fingerprint="strategy_tuning_report:v1:test",
        max_age_seconds=3600,
        now=report_script.parse_datetime_utc("2026-05-19T00:00:04Z"),
        consumed_latest=True,
        require_fingerprint=True,
        require_service_version=True,
    )

    assert summary["force_hold"] is True
    assert summary["error_codes"] == ["ASYNC_REOPTIMIZE_SCHEMA_MISMATCH"]
    assert "unexpected" in summary["errors"][0]["error"]


def test_latest_successful_accepts_fresh_compatible_artifact_evidence() -> None:
    payload = async_status_payload()
    summary = report_script.evaluate_async_reoptimize_evidence(
        mode="latest-successful",
        payload=payload,
        timeframes=["1m", "15m", "1h"],
        expected_fingerprint="strategy_tuning_report:v1:test",
        max_age_seconds=3600,
        now=report_script.parse_datetime_utc("2026-05-19T00:00:04Z"),
        consumed_latest=True,
        require_fingerprint=True,
        require_service_version=True,
    )

    assert summary["force_hold"] is False
    assert summary["evidence_valid"] is True
    assert summary["artifact_required_kinds"] == ["ERRORS", "PROGRESS", "REQUEST", "SUMMARY"]


def test_run_report_step_passes_reoptimize_mode(tmp_path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run_subprocess(command: list[str], cwd: pathlib.Path, timeout_seconds: int) -> dict[str, object]:
        captured["command"] = command
        output_path = pathlib.Path(command[command.index("--output-json") + 1])
        output_path.write_text("{}", encoding="utf-8")
        return {
            "command": command,
            "started_at": "2026-05-19T00:00:00Z",
            "finished_at": "2026-05-19T00:00:00Z",
            "duration_ms": 0,
            "exit_code": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(cycle_script, "run_subprocess", fake_run_subprocess)
    output_path = tmp_path / "report.json"

    step = cycle_script.run_report_step(
        python_bin="python3",
        repo_root=tmp_path,
        timeout_seconds=60,
        strategy_service_url="http://strategy",
        execution_service_url="http://execution",
        exchange="kraken_futures",
        account_id="primary",
        window_minutes=60,
        policy_json=tmp_path / "policy.json",
        profile="candidate",
        output_json=output_path,
        reoptimize_mode="async",
        reoptimize_max_wait_seconds=123,
        reoptimize_poll_initial_seconds=1.5,
        reoptimize_poll_max_seconds=9.0,
        reoptimize_max_age_seconds=456,
        reoptimize_cancel_on_timeout=True,
    )

    command = captured["command"]
    assert step["pass"] is True
    assert command[command.index("--reoptimize-mode") + 1] == "async"
    assert command[command.index("--reoptimize-max-wait-seconds") + 1] == "123"
    assert command[command.index("--reoptimize-trigger-source") + 1] == "MAINTENANCE_REPORT"
    assert "--reoptimize-cancel-on-timeout" in command
