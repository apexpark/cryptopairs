from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest
from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools" / "scripts"
FIXTURE_PATH = (
    SCRIPTS_ROOT / "tests" / "fixtures" / "autopilot_dynamic_allowlist_v2_cases.json"
)
SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_allowlist_decision_v2.schema.json"
)
SNAPSHOT_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_shadow_allowlist_snapshot.example.json"
)
RUNBOOK_PATH = (
    REPO_ROOT / "docs" / "playbooks" / "autopilot-dynamic-allowlist-v2-runbook.md"
)
FIRST_EXPERIMENT_CONFIG_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_governor_config_v2.first_bounded_paper_experiment.example.json"
)
WORK_ORDER_PATH = (
    REPO_ROOT
    / ".agentic"
    / "runs"
    / "AG-20260728-017-auto2c-v2-governor-runbook"
    / "00-work-order.md"
)
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_dynamic_allowlist as v1  # noqa: E402
import autopilot_dynamic_allowlist_v2 as governor  # noqa: E402


PROTECTED_HASHES = {
    "tools/scripts/autopilot_dynamic_allowlist.py": (
        "86e1ef61d2a1ff34314e7dab6477b2e8c84977645882d9acbd9db9d6c542f2ae"
    ),
    "specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json": (
        "6abf514fd1a88a61cf7868078d2eab230358ffd73430410beba7131cb8d11686"
    ),
    "specs/examples/autopilot_dynamic_allowlist_decision_v2.eligible.example.json": (
        "aa7e36a502738249809cd7fb799139fd72d9ab800dac2b46b3a6a2e9c4608643"
    ),
    "specs/examples/autopilot_dynamic_allowlist_decision_v2.blocked.example.json": (
        "5031b3fcde5b168c885ef6c586599ad382693c09b5d64f1651549d7a7415fdc1"
    ),
}


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def key_tuple(value: dict) -> tuple[str, str, str, str]:
    return (
        value["pair_id"],
        value["timeframe"],
        value["selected_variant"],
        value["direction"],
    )


def paper_key(value: dict) -> dict:
    return {
        "pair_id": value["pair_id"],
        "selected_variant": value["selected_variant"],
        "direction": value["direction"],
    }


def write_json(path: Path, payload: object) -> str:
    raw = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def realized_row(
    template: dict,
    key: dict,
    *,
    score: float,
    closed: int,
) -> dict:
    row = copy.deepcopy(template)
    row.update(key)
    row["decision"] = "SHADOW_SELECTED"
    row["reason_codes"] = ["PASSED_SHADOW_SELECTOR_GATES"]
    row["metrics"] = {
        "closed_positions": closed,
        "profitable_closed_positions": closed,
        "losing_closed_positions": 0,
        "win_rate": 1.0,
        "sum_realized_net_bps": score * closed,
        "avg_realized_net_bps": score,
        "max_loss_bps": 0.0,
        "avg_exit_lag_seconds": 60.0,
        "max_exit_lag_seconds": 60.0,
        "first_entry_at": "2026-07-20T00:00:00Z",
        "last_exit_at": "2026-07-27T00:00:00Z",
    }
    row["score_components"] = {
        "avg_net_bps": score,
        "win_rate_bonus": 0.0,
        "sample_size_bonus": 0.0,
        "tail_loss_penalty": 0.0,
        "exit_lag_penalty": 0.0,
        "total_score": score,
    }
    return row


def selector_row(
    template: dict,
    key: dict,
    *,
    rows: int,
    trade_now: int,
    edge: float,
) -> dict:
    row = copy.deepcopy(template)
    row.update(key)
    row["evidence_kind"] = "selector_view"
    row["metrics"] = {
        "rows_observed": rows,
        "time_in_tradable_now_ratio": trade_now / rows,
        "bucket_counts": {
            "TRADE_NOW": trade_now,
            "WATCHLIST": rows - trade_now,
            "EXCLUDED": 0,
        },
        "score_z_summary": {
            "min": 1.0,
            "mean": 2.0,
            "max": 3.0,
        },
        "stated_net_edge_bps_summary": {
            "min": edge - 0.5,
            "mean": edge,
            "max": edge + 0.5,
        },
        "top_gate_failure_reasons": ["WATCH_ENTRY_DISTANCE"],
    }
    return row


def snapshot_payload(
    *,
    generated_at: str,
    source_cutoff_at: str,
    previous_generated_at: str,
    keys: dict[str, dict],
    current: bool,
) -> dict:
    snapshot = json.loads(SNAPSHOT_EXAMPLE_PATH.read_text(encoding="utf-8"))
    selected_template = snapshot["selected"][0]
    selector_template = snapshot["selector_view"]["selector_view_prominent"][0]
    baseline_names = (
        "baseline_long",
        "baseline_short",
        "baseline_xbt",
        "baseline_tao",
    )
    baseline = [keys[name] for name in baseline_names]
    realized_specs = {
        "baseline_long": (13.0, 22),
        "baseline_short": (11.0, 19),
        "baseline_xbt": (9.0, 16),
        "baseline_tao": (7.5, 13),
    }
    if not current:
        realized_specs = {
            "baseline_long": (12.0, 20),
            "baseline_short": (10.0, 18),
            "baseline_xbt": (8.0, 15),
            "baseline_tao": (7.0, 12),
        }
    selected = [
        realized_row(
            selected_template,
            keys[name],
            score=score,
            closed=closed,
        )
        for name, (score, closed) in realized_specs.items()
    ]
    selected.sort(key=key_tuple)

    selector_specs = {
        "baseline_long": (20, 5, 5.0),
        "baseline_short": (19, 4, 4.2),
        "baseline_xbt": (17, 4, 3.5),
        "baseline_tao": (15, 3, 2.8),
        "exploration_eth": (20, 6, 4.0),
        "exploration_sui": (18, 5, 3.0),
        "exploration_ada": (16, 4, 2.6),
    }
    if not current:
        selector_specs = {
            "baseline_long": (18, 4, 4.5),
            "baseline_short": (20, 4, 4.0),
            "baseline_xbt": (20, 3, 3.2),
            "baseline_tao": (25, 3, 2.5),
            "exploration_eth": (21, 5, 3.8),
            "exploration_sui": (21, 4, 2.8),
            "exploration_ada": (20, 3, 2.4),
        }
    prominent = [
        selector_row(
            selector_template,
            keys[name],
            rows=rows,
            trade_now=trade_now,
            edge=edge,
        )
        for name, (rows, trade_now, edge) in selector_specs.items()
    ]
    prominent.sort(key=key_tuple)
    none_key = {
        "pair_id": "PF_NONEAUSD__PF_NONEBUSD",
        "timeframe": "1m",
        "selected_variant": "NONE_SENTINEL",
        "direction": "NONE",
    }
    null_key = {
        "pair_id": "PF_NULLAUSD__PF_NULLBUSD",
        "timeframe": "1m",
        "selected_variant": "NULL_SENTINEL",
        "direction": None,
    }
    marginal = [
        selector_row(
            selector_template,
            none_key,
            rows=20,
            trade_now=0,
            edge=0.0,
        ),
        selector_row(
            selector_template,
            null_key,
            rows=20,
            trade_now=0,
            edge=0.0,
        ),
    ]

    snapshot["schema_version"] = 2
    snapshot["generated_at"] = generated_at
    snapshot["source_cutoff_at"] = source_cutoff_at
    snapshot["selected"] = selected
    snapshot["rejected"] = []
    snapshot["quarantined"] = []
    snapshot["summary"].update(
        {
            "eligible_universe_count": len(selected),
            "selected_count": len(selected),
            "rejected_count": 0,
            "quarantined_count": 0,
        }
    )
    snapshot["selector_view"] = {
        "selector_view_prominent": prominent,
        "selector_view_marginal": marginal,
    }
    snapshot["static_allowlist_comparison"] = {
        "static_allowlist_size": len(baseline),
        "shadow_selected_size": len(selected),
        "overlap_count": len(baseline),
        "static_only_count": 0,
        "shadow_only_count": 0,
        "overlap": sorted(baseline, key=key_tuple),
        "static_only": [],
        "shadow_only": [],
    }
    snapshot["churn"] = {
        "previous_generated_at": previous_generated_at,
        "previous_selected_count": len(selected),
        "selected_added": [],
        "selected_removed": [],
        "selected_retained_count": len(selected),
        "churn_count": 0,
        "stability_ratio": 1.0,
        "selector_view": {
            "previous_prominent_count": len(prominent),
            "prominent_added": [],
            "prominent_removed": [],
            "prominent_retained_count": len(prominent),
            "churn_count": 0,
            "stability_ratio": 1.0,
        },
    }
    snapshot["universe"] = {
        "bucket_universe_counts": {
            "TRADE_NOW": len(prominent),
            "WATCHLIST": len(marginal),
            "EXCLUDED": 0,
        },
        "paper_evidenced_count": len(selected),
        "selector_view_only": sorted(
            [
                keys["exploration_eth"],
                keys["exploration_sui"],
                keys["exploration_ada"],
            ],
            key=key_tuple,
        ),
        "static_allowlist_overlap_count": len(selected),
    }
    return snapshot


def production_inputs(tmp_path: Path) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fixture = load_fixture()
    keys = fixture["keys"]
    previous = snapshot_payload(
        generated_at="2026-07-27T00:03:00Z",
        source_cutoff_at=fixture["previous_source_cutoff_at"],
        previous_generated_at="2026-07-26T00:03:00Z",
        keys=keys,
        current=False,
    )
    current = snapshot_payload(
        generated_at="2026-07-28T00:03:00Z",
        source_cutoff_at=fixture["current_source_cutoff_at"],
        previous_generated_at=previous["generated_at"],
        keys=keys,
        current=True,
    )
    paper = {
        "run_id": "synthetic-auto2c-v2-paper-evidence",
        "timeframe": "1m",
        "static_allowlist_mode": "pair_variant_direction",
        "static_allowlist": [
            paper_key(keys[name])
            for name in (
                "baseline_long",
                "baseline_short",
                "baseline_xbt",
                "baseline_tao",
            )
        ],
        "hold_window_bars": 15,
        "max_runtime_seconds": 259200,
        "max_observe_candidate_age_seconds": 900,
    }
    paths = {
        "current": tmp_path / "current_snapshot.json",
        "previous": tmp_path / "previous_snapshot.json",
        "paper": tmp_path / "paper_run_config.json",
        "governor": tmp_path / "governor_config.json",
    }
    hashes = {
        "current": write_json(paths["current"], current),
        "previous": write_json(paths["previous"], previous),
        "paper": write_json(paths["paper"], paper),
        "governor": write_json(paths["governor"], governor.GOVERNOR_CONFIG),
    }
    return {
        "fixture": fixture,
        "paths": paths,
        "hashes": hashes,
        "current": current,
        "previous": previous,
        "paper": paper,
        "governor": copy.deepcopy(governor.GOVERNOR_CONFIG),
    }


def first_bounded_paper_experiment_inputs(tmp_path: Path) -> dict[str, object]:
    inputs = production_inputs(tmp_path)
    keys = inputs["fixture"]["keys"]
    assert isinstance(keys, dict)
    baseline_names = (
        "baseline_long",
        "baseline_short",
        "baseline_xbt",
        "baseline_tao",
    )
    baseline = [keys[name] for name in baseline_names]
    sui_long = {
        **keys["exploration_sui"],
        "direction": "LONG_SPREAD",
    }
    xbt_short = {
        **keys["baseline_xbt"],
        "direction": "SHORT_SPREAD",
    }

    for current_flag, name in ((False, "previous"), (True, "current")):
        snapshot = inputs[name]
        assert isinstance(snapshot, dict)
        selected = [
            row
            for row in snapshot["selected"]
            if key_tuple(row) == key_tuple(keys["baseline_xbt"])
        ]
        template = snapshot["selector_view"]["selector_view_prominent"][0]
        specs = (
            (keys["baseline_xbt"], 20, 4, 3.5),
            (keys["exploration_sui"], 20, 6, 4.2),
            (sui_long, 20, 5, 3.8),
            (xbt_short, 20, 4, 3.4),
        )
        if not current_flag:
            specs = (
                (keys["baseline_xbt"], 20, 3, 3.2),
                (keys["exploration_sui"], 20, 5, 4.0),
                (sui_long, 20, 4, 3.6),
                (xbt_short, 20, 3, 3.1),
            )
        prominent = sorted(
            [
                selector_row(
                    template,
                    key,
                    rows=rows,
                    trade_now=trade_now,
                    edge=edge,
                )
                for key, rows, trade_now, edge in specs
            ],
            key=key_tuple,
        )
        snapshot["selected"] = selected
        snapshot["summary"].update(
            {
                "eligible_universe_count": 1,
                "selected_count": 1,
                "rejected_count": 0,
                "quarantined_count": 0,
            }
        )
        snapshot["selector_view"]["selector_view_prominent"] = prominent
        snapshot["static_allowlist_comparison"] = {
            "static_allowlist_size": 4,
            "shadow_selected_size": 1,
            "overlap_count": 1,
            "static_only_count": 3,
            "shadow_only_count": 0,
            "overlap": [keys["baseline_xbt"]],
            "static_only": sorted(
                [keys[name] for name in baseline_names if name != "baseline_xbt"],
                key=key_tuple,
            ),
            "shadow_only": [],
        }
        snapshot["churn"].update(
            {
                "previous_selected_count": 1,
                "selected_added": [],
                "selected_removed": [],
                "selected_retained_count": 1,
                "churn_count": 0,
                "stability_ratio": 1.0,
                "selector_view": {
                    "previous_prominent_count": 4,
                    "prominent_added": [],
                    "prominent_removed": [],
                    "prominent_retained_count": 4,
                    "churn_count": 0,
                    "stability_ratio": 1.0,
                },
            }
        )
        snapshot["universe"] = {
            "bucket_universe_counts": {
                "TRADE_NOW": 4,
                "WATCHLIST": 2,
                "EXCLUDED": 0,
            },
            "paper_evidenced_count": 1,
            "selector_view_only": sorted(
                [keys["exploration_sui"], sui_long, xbt_short],
                key=key_tuple,
            ),
            "static_allowlist_overlap_count": 1,
        }

    paper = inputs["paper"]
    assert isinstance(paper, dict)
    paper["static_allowlist"] = [paper_key(key) for key in baseline]
    inputs["governor"] = copy.deepcopy(
        governor.FIRST_BOUNDED_PAPER_EXPERIMENT_GOVERNOR_CONFIG
    )
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    for name in ("current", "previous", "paper", "governor"):
        hashes[name] = write_json(paths[name], inputs[name])
    return inputs


def arguments(inputs: dict[str, object], output_root: Path) -> list[str]:
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    return [
        "--enabled",
        "--current-snapshot-json",
        str(paths["current"]),
        "--current-snapshot-sha256",
        str(hashes["current"]),
        "--current-snapshot-producer-git-sha",
        "1" * 40,
        "--previous-snapshot-json",
        str(paths["previous"]),
        "--previous-snapshot-sha256",
        str(hashes["previous"]),
        "--previous-snapshot-producer-git-sha",
        "2" * 40,
        "--paper-run-config-json",
        str(paths["paper"]),
        "--paper-run-config-sha256",
        str(hashes["paper"]),
        "--paper-run-config-producer-git-sha",
        "3" * 40,
        "--governor-config-json",
        str(paths["governor"]),
        "--governor-config-sha256",
        str(hashes["governor"]),
        "--evaluated-at",
        str(inputs["fixture"]["evaluated_at"]),
        "--prior-active-set-source",
        governor.PRIOR_SOURCE,
        "--output-json",
        str(output_root / governor.OUTPUT_JSON_NAME),
        "--output-markdown",
        str(output_root / governor.OUTPUT_MARKDOWN_NAME),
    ]


def decision_validator() -> Draft202012Validator:
    return Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def run_success(
    inputs: dict[str, object],
    output_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict, bytes, bytes]:
    assert governor.main(arguments(inputs, output_root)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    diagnostic = json.loads(captured.out)
    json_bytes = (output_root / governor.OUTPUT_JSON_NAME).read_bytes()
    markdown_bytes = (output_root / governor.OUTPUT_MARKDOWN_NAME).read_bytes()
    return diagnostic, json_bytes, markdown_bytes


def test_default_mode_is_bounded_disabled_and_performs_no_io(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [
        "--current-snapshot-json",
        "/must/not/read/current.json",
        "--output-json",
        "/must/not/write/decision.json",
    ]
    with (
        mock.patch("builtins.open", side_effect=AssertionError("file access")),
        mock.patch.object(Path, "open", side_effect=AssertionError("path access")),
        mock.patch.object(os, "open", side_effect=AssertionError("os access")),
    ):
        assert governor.main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        '{"artifact_created":false,"mode":"auto2c_v2_governor","status":"DISABLED"}\n'
    )
    assert captured.err == ""


def test_enabled_creates_schema_valid_ranked_truncated_non_actuating_decision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "output"
    diagnostic, raw, markdown = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    fixture = inputs["fixture"]
    assert list(decision_validator().iter_errors(decision)) == []
    assert not raw.endswith(b"\n")
    assert diagnostic["status"] == fixture["expected"]["status"]
    assert diagnostic["json_sha256"] == hashlib.sha256(raw).hexdigest()
    assert diagnostic["markdown_sha256"] == hashlib.sha256(markdown).hexdigest()
    for field, expected in fixture["expected"].items():
        if field in decision["calculations"]:
            assert decision["calculations"][field] == expected
    assert len(decision["candidates"]) == 7
    assert decision["selected_entries"][0]["evidence_class"] == "SELECTOR_EXPLORATION"
    assert decision["selected_entries"][0]["selection_rule"] == (
        "RESERVE_BEST_QUALIFYING_ADDITION"
    )
    assert len(decision["truncated_candidates"]) == 3
    assert decision["skipped_candidates"] == []
    assert decision["direction_counts"]["selector_none_count"] == 1
    assert decision["direction_counts"]["selector_null_count"] == 1
    assert not any(decision["authority_boundaries"].values())
    assert decision["per_output_operator_approval_required"] is False
    assert b"advisory and non-actuating" in markdown


def test_first_bounded_paper_experiment_selects_three_of_four_without_static_churn_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = first_bounded_paper_experiment_inputs(tmp_path)
    diagnostic, raw, markdown = run_success(inputs, tmp_path / "experiment", capsys)
    decision = json.loads(raw)
    assert list(decision_validator().iter_errors(decision)) == []
    assert diagnostic["status"] == "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
    assert decision["policy_version"] == (
        governor.FIRST_BOUNDED_PAPER_EXPERIMENT_POLICY_VERSION
    )
    assert decision["policy"] == governor.FIRST_BOUNDED_PAPER_EXPERIMENT_POLICY
    assert len(decision["candidates"]) == 4
    assert [
        (
            item["key"]["pair_id"],
            item["key"]["direction"],
            item["evidence_class"],
        )
        for item in decision["selected_entries"]
    ] == [
        ("PF_SUIUSD__PF_ARBUSD", "SHORT_SPREAD", "SELECTOR_EXPLORATION"),
        ("PF_XBTUSD__PF_BNBUSD", "LONG_SPREAD", "REALIZED_AND_SELECTOR"),
        ("PF_XBTUSD__PF_BNBUSD", "SHORT_SPREAD", "SELECTOR_EXPLORATION"),
    ]
    assert decision["truncated_candidates"] == []
    assert [item["reason_code"] for item in decision["skipped_candidates"]] == [
        "SKIPPED_ADDITION_INSTRUMENT_CONCENTRATION"
    ]
    assert decision["calculations"]["selector_exploration_selected_count"] == 2
    assert decision["calculations"]["removal_count"] == 3
    assert decision["calculations"]["churn_ratio"] == 1.25
    assert decision["gate_results"]["transition_limits"] == {
        "verdict": "PASS",
        "reason_codes": [],
    }
    assert decision["methodology"]["static_baseline_transition_behavior"] == (
        "REPORT_OVERLAP_ONLY_NO_REMOVAL_OR_CHURN_GATE"
    )
    assert (
        decision["authority_boundaries"]["subsequent_paper_or_live_promotion_authority"]
        is False
    )
    assert b"Static-baseline overlap is reported" in markdown
    assert b"separate policy decision" in markdown


def test_historical_policy_still_blocks_same_static_transition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = first_bounded_paper_experiment_inputs(tmp_path)
    inputs["governor"] = copy.deepcopy(governor.GOVERNOR_CONFIG)
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    hashes["governor"] = write_json(paths["governor"], inputs["governor"])
    diagnostic, raw, _ = run_success(inputs, tmp_path / "historical", capsys)
    decision = json.loads(raw)
    assert list(decision_validator().iter_errors(decision)) == []
    assert diagnostic["status"] == "GOVERNOR_BLOCKED"
    assert decision["policy_version"] == governor.POLICY_VERSION
    assert decision["reason_codes"] == ["TRANSITION_LIMITS_UNSATISFIABLE"]
    assert decision["selected_entries"] == []


def test_first_experiment_policy_hash_and_decision_id_recompute_exactly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = first_bounded_paper_experiment_inputs(tmp_path)
    _, raw, _ = run_success(inputs, tmp_path / "identity", capsys)
    decision = json.loads(raw)
    assert decision["policy_envelope_sha256"] == governor.policy_envelope_sha256(
        governor.FIRST_BOUNDED_PAPER_EXPERIMENT_ROUTE
    )
    assert decision["decision_id"] == governor.decision_id(
        current_snapshot_sha256=decision["current_snapshot"]["sha256"],
        previous_snapshot_sha256=decision["previous_snapshot"]["sha256"],
        paper_run_config_sha256=decision["paper_run_config"]["sha256"],
        governor_config_sha256=decision["governor_config_source"]["sha256"],
        policy_hash=decision["policy_envelope_sha256"],
        prior_set_hash=decision["prior_active_set_sha256"],
        evaluated_at=decision["evaluated_at"],
    )


def test_first_experiment_governor_config_example_is_exact() -> None:
    assert (
        json.loads(FIRST_EXPERIMENT_CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
        == governor.FIRST_BOUNDED_PAPER_EXPERIMENT_GOVERNOR_CONFIG
    )


def test_first_experiment_stale_evidence_is_schema_valid_blocked_and_empty(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = first_bounded_paper_experiment_inputs(tmp_path)
    inputs["fixture"]["evaluated_at"] = "2026-07-28T00:30:01Z"
    _, raw, _ = run_success(inputs, tmp_path / "stale-experiment", capsys)
    decision = json.loads(raw)
    assert list(decision_validator().iter_errors(decision)) == []
    assert decision["policy_version"] == (
        governor.FIRST_BOUNDED_PAPER_EXPERIMENT_POLICY_VERSION
    )
    assert decision["status"] == "GOVERNOR_BLOCKED"
    assert decision["reason_codes"] == ["CURRENT_SOURCE_STALE"]
    for field in (
        "candidates",
        "selection_steps",
        "selected_entries",
        "truncated_candidates",
        "skipped_candidates",
        "additions",
        "removals",
        "retained_entries",
    ):
        assert decision[field] == []


def test_first_experiment_config_mutation_rejects_without_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = first_bounded_paper_experiment_inputs(tmp_path)
    governor_config = copy.deepcopy(inputs["governor"])
    governor_config["policy"]["max_removals"] = 2
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    hashes["governor"] = write_json(paths["governor"], governor_config)
    root = tmp_path / "mutated-experiment"
    assert governor.main(arguments(inputs, root)) == 2
    assert "GOVERNOR_CONFIG_MISMATCH" in capsys.readouterr().err
    assert not root.exists()


def test_policy_hash_prior_hash_and_decision_id_recompute_exactly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "identity"
    _, raw, _ = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    assert decision["policy_envelope_sha256"] == governor.policy_envelope_sha256()
    baseline = frozenset(key_tuple(item) for item in decision["prior_active_entries"])
    assert decision["prior_active_set_sha256"] == governor.prior_active_set_sha256(
        baseline
    )
    assert decision["decision_id"] == governor.decision_id(
        current_snapshot_sha256=decision["current_snapshot"]["sha256"],
        previous_snapshot_sha256=decision["previous_snapshot"]["sha256"],
        paper_run_config_sha256=decision["paper_run_config"]["sha256"],
        governor_config_sha256=decision["governor_config_source"]["sha256"],
        policy_hash=decision["policy_envelope_sha256"],
        prior_set_hash=decision["prior_active_set_sha256"],
        evaluated_at=decision["evaluated_at"],
    )


def test_production_output_passes_merged_independent_contract_auditor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "independent-audit"
    _, raw, _ = run_success(inputs, root, capsys)
    auditor_path = (
        SCRIPTS_ROOT / "tests" / "test_autopilot_dynamic_allowlist_v2_contract.py"
    )
    spec = importlib.util.spec_from_file_location(
        "merged_v2_contract_auditor",
        auditor_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.audit_eligible(json.loads(raw))


def test_repeat_invocation_to_distinct_roots_is_byte_deterministic_and_preserves_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    paths = inputs["paths"]
    assert isinstance(paths, dict)
    before = {
        name: (path.read_bytes(), stat.st_mode, stat.st_mtime_ns)
        for name, path in paths.items()
        for stat in (path.stat(),)
    }
    _, first_json, first_markdown = run_success(
        inputs,
        tmp_path / "first",
        capsys,
    )
    _, second_json, second_markdown = run_success(
        inputs,
        tmp_path / "second",
        capsys,
    )
    assert second_json == first_json
    assert second_markdown == first_markdown
    after = {
        name: (path.read_bytes(), stat.st_mode, stat.st_mtime_ns)
        for name, path in paths.items()
        for stat in (path.stat(),)
    }
    assert after == before


def test_verify_only_reconstructs_existing_output_without_modification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "output"
    _, raw, markdown = run_success(inputs, root, capsys)
    verify_args = arguments(inputs, root)
    verify_args[0] = "--verify-only"
    verify_args.extend(
        [
            "--expected-output-json-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--expected-output-markdown-sha256",
            hashlib.sha256(markdown).hexdigest(),
        ]
    )
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()
    }
    assert governor.main(verify_args) == 0
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["verification"] == "PASS"
    assert diagnostic["artifact_created"] is False
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.iterdir()
    } == before


def test_verify_only_rejects_wrong_hash_and_reconstruction_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "output"
    _, raw, markdown = run_success(inputs, root, capsys)
    args = arguments(inputs, root)
    args[0] = "--verify-only"
    args.extend(
        [
            "--expected-output-json-sha256",
            "0" * 64,
            "--expected-output-markdown-sha256",
            hashlib.sha256(markdown).hexdigest(),
        ]
    )
    assert governor.main(args) == 2
    assert "OUTPUT_JSON_HASH_MISMATCH" in capsys.readouterr().err

    changed_inputs = production_inputs(tmp_path / "changed")
    changed_root = tmp_path / "copied-output"
    changed_root.mkdir()
    (changed_root / governor.OUTPUT_JSON_NAME).write_bytes(raw)
    (changed_root / governor.OUTPUT_MARKDOWN_NAME).write_bytes(markdown)
    args = arguments(changed_inputs, changed_root)
    args[0] = "--verify-only"
    args.extend(
        [
            "--expected-output-json-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--expected-output-markdown-sha256",
            hashlib.sha256(markdown).hexdigest(),
        ]
    )
    assert governor.main(args) == 2
    assert "OUTPUT_JSON_RECONSTRUCTION_MISMATCH" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda payload: payload.__setitem__(
                "source_cutoff_at",
                "2026-07-27T00:00:01Z",
            ),
            "SOURCE_CUTOFF_SEPARATION_TOO_SHORT",
        ),
        (
            lambda payload: None,
            "CURRENT_SOURCE_STALE",
        ),
    ],
)
def test_trusted_policy_time_failures_create_schema_valid_blocked_empty_decision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutator,
    reason: str,
) -> None:
    inputs = production_inputs(tmp_path)
    if reason == "SOURCE_CUTOFF_SEPARATION_TOO_SHORT":
        previous = copy.deepcopy(inputs["previous"])
        mutator(previous)
        paths = inputs["paths"]
        hashes = inputs["hashes"]
        hashes["previous"] = write_json(paths["previous"], previous)
    else:
        inputs["fixture"]["evaluated_at"] = "2026-07-28T00:30:01Z"
    root = tmp_path / "blocked"
    _, raw, _ = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    assert list(decision_validator().iter_errors(decision)) == []
    assert decision["status"] == "GOVERNOR_BLOCKED"
    assert decision["reason_codes"] == [reason]
    for field in (
        "candidates",
        "selection_steps",
        "selected_entries",
        "truncated_candidates",
        "skipped_candidates",
        "additions",
        "removals",
        "retained_entries",
    ):
        assert decision[field] == []


def test_fractional_second_snapshot_time_rejects_without_rounding_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    current = copy.deepcopy(inputs["current"])
    previous = copy.deepcopy(inputs["previous"])
    current["source_cutoff_at"] = "2026-07-27T23:59:59.500000Z"
    current["generated_at"] = "2026-07-28T00:03:00Z"
    previous["source_cutoff_at"] = "2026-07-26T23:59:59.500000Z"
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    hashes["current"] = write_json(paths["current"], current)
    hashes["previous"] = write_json(paths["previous"], previous)
    root = tmp_path / "fractional-stale"
    assert governor.main(arguments(inputs, root)) == 2
    assert "CURRENT_SNAPSHOT_TIMESTAMP_NOT_CANONICAL_SECONDS" in capsys.readouterr().err
    assert not root.exists()


def test_transition_limit_failure_retains_candidates_but_clears_all_outcomes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    current = copy.deepcopy(inputs["current"])
    previous = copy.deepcopy(inputs["previous"])
    for snapshot in (current, previous):
        snapshot["selector_view"]["selector_view_prominent"] = [
            row
            for row in snapshot["selector_view"]["selector_view_prominent"]
            if row["pair_id"] == "PF_ETHUSD__PF_SOLUSD"
        ]
        snapshot["churn"]["selector_view"].update(
            {
                "previous_prominent_count": 1,
                "prominent_retained_count": 1,
            }
        )
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    hashes["current"] = write_json(paths["current"], current)
    hashes["previous"] = write_json(paths["previous"], previous)
    root = tmp_path / "blocked-transition"
    _, raw, _ = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    assert decision["status"] == "GOVERNOR_BLOCKED"
    assert decision["reason_codes"] == ["TRANSITION_LIMITS_UNSATISFIABLE"]
    assert len(decision["candidates"]) == 1
    for field in (
        "selection_steps",
        "selected_entries",
        "truncated_candidates",
        "skipped_candidates",
        "additions",
        "removals",
        "retained_entries",
    ):
        assert decision[field] == []


def test_previous_schema_v1_and_missing_selector_churn_reject_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for mutation, expected in (
        ("schema", "PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2"),
        ("churn", "PREVIOUS_SELECTOR_EVIDENCE_INCOMPLETE"),
    ):
        case_root = tmp_path / mutation
        inputs = production_inputs(case_root)
        previous = copy.deepcopy(inputs["previous"])
        if mutation == "schema":
            previous["schema_version"] = 1
            previous.pop("selector_view")
            previous.pop("universe")
            previous["churn"].pop("selector_view")
        else:
            previous["churn"].pop("selector_view")
        paths = inputs["paths"]
        hashes = inputs["hashes"]
        hashes["previous"] = write_json(paths["previous"], previous)
        output = case_root / "output"
        assert governor.main(arguments(inputs, output)) == 2
        assert expected in capsys.readouterr().err
        assert not output.exists()


@pytest.mark.parametrize(
    ("input_name", "mutator", "expected"),
    [
        (
            "current",
            lambda payload: payload["selector_view"]["selector_view_marginal"][
                0
            ].__setitem__("direction", "SIDEWAYS"),
            "UNKNOWN_SELECTOR_DIRECTION",
        ),
        (
            "paper",
            lambda payload: payload["static_allowlist"][0].__setitem__(
                "direction",
                "NONE",
            ),
            "PAPER_CONFIG_ALLOWLIST_0_DIRECTION_INVALID",
        ),
        (
            "governor",
            lambda payload: payload["policy"].__setitem__(
                "max_selected_entries",
                5,
            ),
            "GOVERNOR_CONFIG_MISMATCH",
        ),
    ],
)
def test_unknown_nonactionable_or_policy_mutation_rejects_without_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    input_name: str,
    mutator,
    expected: str,
) -> None:
    inputs = production_inputs(tmp_path)
    payload = copy.deepcopy(inputs[input_name])
    mutator(payload)
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    hashes[input_name] = write_json(paths[input_name], payload)
    root = tmp_path / "rejected"
    assert governor.main(arguments(inputs, root)) == 2
    assert expected in capsys.readouterr().err
    assert not root.exists()


def test_none_and_null_remain_distinct_nonactionable_and_never_candidates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "directions"
    _, raw, _ = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    candidate_directions = {
        candidate["key"]["direction"] for candidate in decision["candidates"]
    }
    assert candidate_directions == {"LONG_SPREAD", "SHORT_SPREAD"}
    assert decision["direction_counts"]["selector_none_count"] == 1
    assert decision["direction_counts"]["selector_null_count"] == 1


def test_hash_mismatch_malformed_duplicate_key_and_nonfinite_reject_without_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path / "hash")
    args = arguments(inputs, tmp_path / "hash" / "output")
    args[args.index("--current-snapshot-sha256") + 1] = "0" * 64
    assert governor.main(args) == 2
    assert "CURRENT_SNAPSHOT_HASH_MISMATCH" in capsys.readouterr().err

    for name, raw, expected in (
        ("malformed", b"{", "CURRENT_SNAPSHOT_MALFORMED_JSON"),
        (
            "duplicate",
            b'{"schema_version":2,"schema_version":2}',
            "DUPLICATE_JSON_KEY",
        ),
        (
            "nonfinite",
            b'{"schema_version":NaN}',
            "NON_FINITE_JSON_NUMBER",
        ),
    ):
        case = tmp_path / name
        inputs = production_inputs(case)
        path = inputs["paths"]["current"]
        path.write_bytes(raw)
        inputs["hashes"]["current"] = hashlib.sha256(raw).hexdigest()
        root = case / "output"
        assert governor.main(arguments(inputs, root)) == 2
        assert expected in capsys.readouterr().err
        assert not root.exists()


def test_symlink_and_nonregular_input_reject_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path / "symlink")
    original = inputs["paths"]["current"]
    link = tmp_path / "symlink" / "linked.json"
    link.symlink_to(original)
    inputs["paths"]["current"] = link
    root = tmp_path / "symlink" / "output"
    assert governor.main(arguments(inputs, root)) == 2
    assert "CURRENT_SNAPSHOT_SYMLINK" in capsys.readouterr().err
    assert not root.exists()

    if hasattr(os, "mkfifo"):
        fifo_case = tmp_path / "fifo"
        inputs = production_inputs(fifo_case)
        fifo = fifo_case / "fifo.json"
        os.mkfifo(fifo)
        inputs["paths"]["current"] = fifo
        root = fifo_case / "output"
        assert governor.main(arguments(inputs, root)) == 2
        assert "CURRENT_SNAPSHOT_NOT_REGULAR" in capsys.readouterr().err
        assert not root.exists()


def test_preoutput_mutation_recheck_rejects_without_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = production_inputs(tmp_path)
    original = governor.recheck_inputs

    def mutate_then_recheck(bound_inputs) -> None:
        inputs["paths"]["current"].write_bytes(b"mutated")
        original(bound_inputs)

    monkeypatch.setattr(governor, "recheck_inputs", mutate_then_recheck)
    root = tmp_path / "output"
    assert governor.main(arguments(inputs, root)) == 2
    assert "CURRENT_SNAPSHOT_HASH_MISMATCH" in capsys.readouterr().err
    assert not root.exists()


def test_output_collision_and_concurrent_invocations_allow_exactly_one_winner(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "output"
    run_success(inputs, root, capsys)
    assert governor.main(arguments(inputs, root)) == 2
    assert "OUTPUT_ROOT_EXISTS" in capsys.readouterr().err

    inputs = production_inputs(tmp_path / "concurrent")
    root = tmp_path / "concurrent" / "output"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _index: governor.main(arguments(inputs, root)),
                range(2),
            )
        )
    capsys.readouterr()
    assert sorted(results) == [0, 2]
    assert (root / governor.OUTPUT_JSON_NAME).is_file()
    assert (root / governor.OUTPUT_MARKDOWN_NAME).is_file()


def test_partial_output_root_is_retained_and_never_repaired(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = production_inputs(tmp_path)
    root = tmp_path / "partial"
    original_open = Path.open

    def fail_markdown(path: Path, mode: str = "r", *args, **kwargs):
        if path.name == governor.OUTPUT_MARKDOWN_NAME and mode == "xb":
            raise OSError("bounded test failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_markdown)
    assert governor.main(arguments(inputs, root)) == 2
    capsys.readouterr()
    assert root.is_dir()
    assert (root / governor.OUTPUT_JSON_NAME).is_file()
    assert not (root / governor.OUTPUT_MARKDOWN_NAME).exists()
    monkeypatch.setattr(Path, "open", original_open)
    assert governor.main(arguments(inputs, root)) == 2
    assert "OUTPUT_ROOT_EXISTS" in capsys.readouterr().err


def test_previous_accepted_v2_prior_source_fails_before_any_file_access(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    args = arguments(inputs, tmp_path / "output")
    args[args.index("--prior-active-set-source") + 1] = (
        governor.UNSUPPORTED_PRIOR_SOURCE
    )
    with mock.patch.object(
        v1,
        "read_bound_input",
        side_effect=AssertionError("input read"),
    ):
        assert governor.main(args) == 2
    assert (
        "PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE_NOT_IMPLEMENTED" in capsys.readouterr().err
    )


def test_candidate_ranking_ties_use_exact_key_and_overflow_never_blocks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    for name in ("current", "previous"):
        snapshot = copy.deepcopy(inputs[name])
        for row in snapshot["selector_view"]["selector_view_prominent"]:
            if row["pair_id"] in {
                "PF_SUIUSD__PF_ARBUSD",
                "PF_ADAUSD__PF_DOTUSD",
            }:
                row["metrics"]["rows_observed"] = 20
                row["metrics"]["bucket_counts"] = {
                    "TRADE_NOW": 4,
                    "WATCHLIST": 16,
                    "EXCLUDED": 0,
                }
                row["metrics"]["time_in_tradable_now_ratio"] = 0.2
                row["metrics"]["stated_net_edge_bps_summary"] = {
                    "min": 2.0,
                    "mean": 2.5,
                    "max": 3.0,
                }
        inputs[name] = snapshot
        inputs["hashes"][name] = write_json(inputs["paths"][name], snapshot)
    root = tmp_path / "ranked"
    _, raw, _ = run_success(inputs, root, capsys)
    decision = json.loads(raw)
    lane = [
        candidate
        for candidate in decision["candidates"]
        if candidate["evidence_class"] == "SELECTOR_EXPLORATION"
    ]
    tied = [
        key_tuple(candidate["key"])
        for candidate in lane
        if candidate["key"]["pair_id"]
        in {"PF_SUIUSD__PF_ARBUSD", "PF_ADAUSD__PF_DOTUSD"}
    ]
    assert tied == sorted(tied)
    assert decision["status"] == "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
    assert (
        decision["calculations"]["qualifying_candidate_count"]
        > (decision["calculations"]["selected_entry_count"])
    )


def test_concentration_skip_continues_to_next_candidate() -> None:
    baseline = frozenset(
        {
            ("PF_DOGEUSD__PF_PEPEUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        }
    )

    def candidate(key: tuple[str, str, str, str], rank: int) -> governor.Candidate:
        metrics = governor.SelectorMetrics(20, 5, 0.25, 3.0)
        return governor.Candidate(
            key=key,
            evidence_class="SELECTOR_EXPLORATION",
            current_selector=metrics,
            previous_selector=metrics,
            current_realized=None,
            previous_realized=None,
            rank_components={
                "minimum_total_b2c_score": None,
                "minimum_closed_position_count": None,
                "minimum_trade_now_ratio": 0.25,
                "minimum_trade_now_count": 5,
                "minimum_selector_stated_mean_net_edge_bps": 3.0,
                "exact_key_tiebreak": "|".join(key),
            },
            lane_rank=rank,
            absent_from_prior_active_set=True,
        )

    first = candidate(
        ("PF_XBTUSD__PF_BNBUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        1,
    )
    violating = candidate(
        ("PF_XBTUSD__PF_ETHUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        2,
    )
    safe = candidate(
        ("PF_SOLUSD__PF_AVAXUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        3,
    )
    selections, _steps, _truncated, skipped = governor.allocate_candidates(
        [first, violating, safe],
        baseline,
    )
    assert skipped[0]["reason_code"] == "SKIPPED_ADDITION_INSTRUMENT_CONCENTRATION"
    assert [selection.candidate.key for selection in selections] == [
        first.key,
        safe.key,
    ]


def test_reserved_exploration_skips_transition_unsafe_top_rank_and_uses_next() -> None:
    baseline = frozenset(
        {
            ("PF_XBTUSD__PF_BNBUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
            ("PF_XBTUSD__PF_ETHUSD", "1m", "ROBUST_Z", "SHORT_SPREAD"),
            ("PF_SOLUSD__PF_AVAXUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
            ("PF_SOLUSD__PF_DOTUSD", "1m", "ROBUST_Z", "SHORT_SPREAD"),
        }
    )
    selector = governor.SelectorMetrics(20, 5, 0.25, 3.0)

    def realized(key: tuple[str, str, str, str], rank: int) -> governor.Candidate:
        evidence = governor.RealizedMetrics(10.0 - rank, 20 - rank)
        return governor.Candidate(
            key=key,
            evidence_class="REALIZED_AND_SELECTOR",
            current_selector=selector,
            previous_selector=selector,
            current_realized=evidence,
            previous_realized=evidence,
            rank_components={
                "minimum_total_b2c_score": evidence.total_b2c_score,
                "minimum_closed_position_count": evidence.closed_position_count,
                "minimum_trade_now_ratio": 0.25,
                "minimum_trade_now_count": 5,
                "minimum_selector_stated_mean_net_edge_bps": 3.0,
                "exact_key_tiebreak": "|".join(key),
            },
            lane_rank=rank,
            absent_from_prior_active_set=False,
        )

    def exploration(
        key: tuple[str, str, str, str],
        rank: int,
    ) -> governor.Candidate:
        return governor.Candidate(
            key=key,
            evidence_class="SELECTOR_EXPLORATION",
            current_selector=selector,
            previous_selector=selector,
            current_realized=None,
            previous_realized=None,
            rank_components={
                "minimum_total_b2c_score": None,
                "minimum_closed_position_count": None,
                "minimum_trade_now_ratio": 0.25,
                "minimum_trade_now_count": 5,
                "minimum_selector_stated_mean_net_edge_bps": 3.0,
                "exact_key_tiebreak": "|".join(key),
            },
            lane_rank=rank,
            absent_from_prior_active_set=True,
        )

    realized_lane = [
        realized(key, rank) for rank, key in enumerate(sorted(baseline), 1)
    ]
    unsafe = exploration(
        ("PF_XBTUSD__PF_SOLUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        1,
    )
    safe = exploration(
        ("PF_ADAUSD__PF_LINKUSD", "1m", "ROBUST_Z", "LONG_SPREAD"),
        2,
    )
    selections, steps, truncated, skipped = governor.allocate_candidates(
        [*realized_lane, unsafe, safe],
        baseline,
    )
    assert skipped[0]["key"] == v1.key_object(unsafe.key)
    assert skipped[0]["reason_code"] == "SKIPPED_INSTRUMENT_CONCENTRATION"
    assert steps[0]["result"] == "SKIPPED"
    assert selections[0].candidate.key == safe.key
    assert governor.transition_is_valid(
        selections,
        [*realized_lane, unsafe, safe],
        baseline,
    )
    assert len(truncated) == 1


def test_schema_and_contract_surfaces_are_preserved_byte_identically() -> None:
    for relative, expected in PROTECTED_HASHES.items():
        assert (
            hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() == expected
        )


def test_runbook_documents_exact_config_cli_modes_and_fail_closed_boundaries() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    policy_section = runbook.split(
        "## Exact policy configuration",
        maxsplit=1,
    )[1]
    config_block = policy_section.split(
        "```json\n",
        maxsplit=1,
    )[1].split("\n```", maxsplit=1)[0]
    assert json.loads(config_block) == governor.GOVERNOR_CONFIG
    for flag in (
        "--enabled",
        "--verify-only",
        "--current-snapshot-json",
        "--current-snapshot-sha256",
        "--current-snapshot-producer-git-sha",
        "--previous-snapshot-json",
        "--previous-snapshot-sha256",
        "--previous-snapshot-producer-git-sha",
        "--paper-run-config-json",
        "--paper-run-config-sha256",
        "--paper-run-config-producer-git-sha",
        "--governor-config-json",
        "--governor-config-sha256",
        "--evaluated-at",
        "--prior-active-set-source",
        "--output-json",
        "--output-markdown",
        "--expected-output-json-sha256",
        "--expected-output-markdown-sha256",
    ):
        assert flag in runbook
    for statement in (
        "Do not retry automatically.",
        "A partial root is diagnostic residue",
        "There is no fallback.",
        "independently implemented AUTO-2D verifier",
        "`NONE` and null",
        "non-actuating",
    ):
        assert statement in runbook


def test_work_order_records_e3_as_separately_gated_not_run() -> None:
    work_order = WORK_ORDER_PATH.read_text(encoding="utf-8")
    assert "`NOT RUN — separately gated`" in work_order
    assert "synthetic evidence is not E3" in work_order
    assert "AUTO-2D" in work_order
    assert "Tier 3 draft PR" in work_order


def test_production_module_has_no_auto2d_test_or_actuation_import() -> None:
    source = inspect.getsource(governor)
    forbidden = (
        "autopilot_paper",
        "import auto2d",
        "from auto2d",
        "test_autopilot",
        "docker",
        "subprocess",
        "requests",
    )
    for token in forbidden:
        assert token not in source.lower()
    assert "autopilot_dynamic_allowlist as v1" in source


def test_bounded_subprocess_default_and_unsupported_prior_create_no_output(
    tmp_path: Path,
) -> None:
    command = [
        sys.executable,
        str(SCRIPTS_ROOT / "autopilot_dynamic_allowlist_v2.py"),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == (
        '{"artifact_created":false,"mode":"auto2c_v2_governor","status":"DISABLED"}\n'
    )
    output = tmp_path / "must-not-exist"
    completed = subprocess.run(
        command
        + [
            "--enabled",
            "--current-snapshot-producer-git-sha",
            "1" * 40,
            "--previous-snapshot-producer-git-sha",
            "2" * 40,
            "--paper-run-config-producer-git-sha",
            "3" * 40,
            "--evaluated-at",
            "2026-07-28T00:30:00Z",
            "--prior-active-set-source",
            governor.UNSUPPORTED_PRIOR_SOURCE,
            "--output-json",
            str(output / governor.OUTPUT_JSON_NAME),
            "--output-markdown",
            str(output / governor.OUTPUT_MARKDOWN_NAME),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE_NOT_IMPLEMENTED" in completed.stderr
    assert not output.exists()
