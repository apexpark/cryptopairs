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
