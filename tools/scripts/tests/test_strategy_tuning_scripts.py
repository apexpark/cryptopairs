from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import strategy_tuning_apply as apply_script  # noqa: E402
import strategy_maintenance_cycle as cycle_script  # noqa: E402
import strategy_maintenance_action_worker as action_worker  # noqa: E402
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


def test_run_deploy_forwards_health_window(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        assert kwargs["text"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(apply_script.subprocess, "run", fake_run)

    apply_script.run_deploy(
        deploy_script=pathlib.Path("scripts/deploy.sh"),
        env_file=pathlib.Path("/opt/cryptopairs/.env.hosted"),
        services="strategy-service",
        skip_pull=True,
        dry_run=False,
        deploy_health_retries=90,
        deploy_health_sleep_secs=2,
    )

    command = captured["command"]
    assert command[:2] == ["bash", "scripts/deploy.sh"]
    assert command[command.index("--health-retries") + 1] == "90"
    assert command[command.index("--health-sleep-secs") + 1] == "2"


def test_cycle_apply_step_forwards_deploy_health_window(tmp_path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run_subprocess(
        command: list[str],
        cwd: pathlib.Path,
        timeout_seconds: int,
    ) -> dict[str, object]:
        captured["command"] = command
        assert cwd == tmp_path
        assert timeout_seconds == 420
        output_path = pathlib.Path(command[command.index("--output-json") + 1])
        output_path.write_text('{"pass": true}\n', encoding="utf-8")
        return {
            "command": command,
            "exit_code": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(cycle_script, "run_subprocess", fake_run_subprocess)

    output_json = tmp_path / "apply.json"
    step = cycle_script.run_apply_step(
        python_bin="python3",
        repo_root=tmp_path,
        timeout_seconds=420,
        mode="promote",
        output_json=output_json,
        policy_json=tmp_path / "policy.json",
        env_file=pathlib.Path("/opt/cryptopairs/.env.hosted"),
        deploy_script=tmp_path / "scripts/deploy.sh",
        services="strategy-service",
        skip_pull=True,
        dry_run=False,
        deploy_health_retries=90,
        deploy_health_sleep_secs=2,
    )

    command = captured["command"]
    assert step["pass"] is True
    assert command[command.index("--deploy-health-retries") + 1] == "90"
    assert command[command.index("--deploy-health-sleep-secs") + 1] == "2"


def test_action_worker_forwards_default_deploy_health_window(tmp_path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 300
        output_path = pathlib.Path(command[command.index("--output-json") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"pass": true}\n', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(action_worker.subprocess, "run", fake_run)
    result, timeout_error = action_worker.run_apply(
        tmp_path,
        {
            "apply_script_path": "tools/scripts/strategy_tuning_apply.py",
            "env_file_path": "/opt/cryptopairs/.env.hosted",
            "deploy_script_path": "scripts/deploy.sh",
            "output_json_path": str(tmp_path / "worker" / "apply.json"),
            "policy_json_path": "infra/config/strategy_tuning_policy.json",
            "mode": "promote",
            "services": "strategy-service",
            "skip_pull": True,
            "timeout_secs": 300,
        },
    )

    command = captured["command"]
    assert result is not None
    assert timeout_error is None
    assert command[command.index("--deploy-health-retries") + 1] == "90"
    assert command[command.index("--deploy-health-sleep-secs") + 1] == "2"


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
