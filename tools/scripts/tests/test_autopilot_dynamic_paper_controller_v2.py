from __future__ import annotations

import argparse
import ast
import copy
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools" / "scripts"
SUPPORT_PATH = Path(__file__).with_name("test_autopilot_dynamic_allowlist_v2.py")
PROVENANCE_SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_paper_provenance_v2.schema.json"
)
CONTROLLER_PATH = SCRIPTS_ROOT / "autopilot_dynamic_paper_controller_v2.py"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_dynamic_allowlist_v2 as governor  # noqa: E402
import autopilot_dynamic_paper_controller_v2 as controller  # noqa: E402


support_spec = importlib.util.spec_from_file_location(
    "auto2c_v2_test_support", SUPPORT_PATH
)
assert support_spec is not None and support_spec.loader is not None
support = importlib.util.module_from_spec(support_spec)
support_spec.loader.exec_module(support)


def write_json(path: Path, payload: object, *, newline: bool = True) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if newline:
        raw += b"\n"
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def generated_inputs(
    tmp_path: Path,
    *,
    first_bounded_paper_experiment: bool = False,
) -> tuple[dict[str, object], Path, str]:
    inputs = (
        support.first_bounded_paper_experiment_inputs(tmp_path / "inputs")
        if first_bounded_paper_experiment
        else support.production_inputs(tmp_path / "inputs")
    )
    output_root = tmp_path / "governor-output"
    args = governor.parse_args(support.arguments(inputs, output_root))
    result = governor.run_enabled(args)
    decision_path = Path(str(result["output_root"])) / governor.OUTPUT_JSON_NAME
    decision_hash = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    return inputs, decision_path, decision_hash


def controller_args(
    inputs: dict[str, object],
    decision_path: Path,
    decision_hash: str,
    *,
    tmp_path: Path,
) -> argparse.Namespace:
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    fixture = inputs["fixture"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    assert isinstance(fixture, dict)
    observe_source = tmp_path / "observe.jsonl"
    observe_source.write_bytes(b"")
    trial_parent = tmp_path / "trials"
    trial_parent.mkdir()
    return argparse.Namespace(
        verify_only=True,
        start=False,
        enabled=False,
        repository_root=str(REPO_ROOT),
        repository_git_sha="a" * 40,
        decision_json=str(decision_path),
        decision_sha256=decision_hash,
        current_snapshot_json=str(paths["current"]),
        current_snapshot_sha256=str(hashes["current"]),
        current_snapshot_producer_git_sha="1" * 40,
        previous_snapshot_json=str(paths["previous"]),
        previous_snapshot_sha256=str(hashes["previous"]),
        previous_snapshot_producer_git_sha="2" * 40,
        paper_run_config_json=str(paths["paper"]),
        paper_run_config_sha256=str(hashes["paper"]),
        paper_run_config_producer_git_sha="3" * 40,
        governor_config_json=str(paths["governor"]),
        governor_config_sha256=str(hashes["governor"]),
        evaluated_at=str(fixture["evaluated_at"]),
        prior_active_set_source=governor.PRIOR_SOURCE,
        controller_started_at=str(fixture["evaluated_at"]),
        observe_source_jsonl=str(observe_source),
        marks_url="http://127.0.0.1:8083/v1/paper-marks",
        trial_root_parent=str(trial_parent),
    )


@pytest.fixture
def verified_case(
    tmp_path: Path,
) -> tuple[dict[str, object], argparse.Namespace, controller.Verification]:
    inputs, decision_path, decision_hash = generated_inputs(tmp_path)
    args = controller_args(inputs, decision_path, decision_hash, tmp_path=tmp_path)
    verification = controller.read_and_verify(args)
    return inputs, args, verification


def provenance_validator() -> Draft202012Validator:
    schema = json.loads(PROVENANCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def observe_candidate(
    selected: dict[str, Any], observed_at: dt.datetime
) -> dict[str, Any]:
    key = selected["key"]
    observed_text = controller.format_timestamp(observed_at)
    source_text = controller.format_timestamp(observed_at - dt.timedelta(seconds=8))
    return {
        "schema_version": 1,
        "mode": "observe_only",
        "run_id": "synthetic-auto2d-observe",
        "observed_at": observed_text,
        "source_generated_at": source_text,
        "timeframe": "1m",
        "pair_id": key["pair_id"],
        "selected_variant": key["selected_variant"],
        "approval_source": "LEARNING_SELECTION",
        "decision_reason_code": "LEARNING_SELECTED_AND_LIVE_GATES_PASS",
        "setup_gate_pass": True,
        "cost_gate_pass": True,
        "trade_gate_pass": True,
        "direction_hint": key["direction"],
        "spread_z": 1.25,
        "entry_distance_z": 0.42,
        "selected_score_z": 2.12,
        "net_edge_bps": 19.5,
        "opportunity_score": 35.9,
        "learning_overlay_fresh": True,
        "learning_overlay_age_seconds": 30.0,
        "dispatch_mode": "SIMULATE_ACK",
        "kill_switch_active": False,
        "conflicting_live_trade": False,
        "quality_window": {
            "rows": 64,
            "profitable_rate": 0.73,
            "avg_net_bps": 7.4,
            "min_rows": 20,
            "min_avg_net_bps": 0.0,
            "pass": True,
        },
        "decision": "OBSERVED_ENTRY_CANDIDATE",
        "observe_key": (
            f"observe-only:v1:1m:{key['pair_id']}:"
            f"{key['selected_variant']}:{key['direction']}:"
            f"{observed_text}"
        ),
        "evidence": {
            "data_health_status": "ok",
            "strategy_health_status": "ok",
            "trade_now_status": "ok",
            "trade_now_observability_status": "ok",
            "dispatch_mode_status": "ok",
            "kill_switch_status": "ok",
            "open_trades_status": "ok",
            "source_urls": [
                "http://127.0.0.1:8080/health",
                ("http://127.0.0.1:8083/v1/strategy/pairs/trade-now?timeframe=1m"),
                "http://127.0.0.1:8082/v1/execution/kill-switch",
            ],
        },
    }


def test_default_is_byte_stable_no_io(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        mock.patch("builtins.open", side_effect=AssertionError("file I/O")),
        mock.patch.object(os, "open", side_effect=AssertionError("os I/O")),
        mock.patch.object(
            controller.subprocess,
            "run",
            side_effect=AssertionError("process I/O"),
        ),
        mock.patch.object(
            controller.urllib.request,
            "build_opener",
            side_effect=AssertionError("network I/O"),
        ),
    ):
        assert controller.main(["--decision-json", "/must/not/read"]) == 0
    assert capsys.readouterr().out == (
        '{"artifact_created":false,"files_read":false,'
        '"mode":"auto2d_bounded_paper_controller",'
        '"network_accessed":false,"start_invoked":false,'
        '"status":"DISABLED"}\n'
    )


def test_start_requires_both_gates_before_io(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        controller,
        "prepare_runtime_bindings",
        side_effect=AssertionError("must not inspect inputs"),
    ):
        assert controller.main(["--start"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["error_code"] == ("START_REQUIRES_EXPLICIT_ENABLED_GATE")
    assert diagnostic["artifact_created"] is False


def test_verify_only_rejects_enabled_gate_before_io(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with mock.patch.object(
        controller,
        "prepare_runtime_bindings",
        side_effect=AssertionError("must not inspect inputs"),
    ):
        assert controller.main(["--verify-only", "--enabled"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["error_code"] == "VERIFY_ONLY_MUST_REMAIN_READ_ONLY"
    assert diagnostic["artifact_created"] is False


def test_independent_recomputation_matches_production_shaped_decision(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, _args, verification = verified_case
    assert verification.decision == verification.expected_decision
    assert verification.decision["status"] == controller.ELIGIBLE_STATUS
    assert verification.decision["direction_counts"]["selector_none_count"] == 1
    assert verification.decision["direction_counts"]["selector_null_count"] == 1
    assert all(
        item["key"]["direction"] in controller.ACTIONABLE_DIRECTIONS
        for item in verification.selected_entries
    )


def test_first_bounded_paper_experiment_is_independently_verified_and_root_scoped(
    tmp_path: Path,
) -> None:
    inputs, decision_path, decision_hash = generated_inputs(
        tmp_path,
        first_bounded_paper_experiment=True,
    )
    args = controller_args(inputs, decision_path, decision_hash, tmp_path=tmp_path)
    verification = controller.read_and_verify(args)
    decision = verification.decision
    assert decision == verification.expected_decision
    assert decision["policy_version"] == (
        controller.FIRST_BOUNDED_PAPER_EXPERIMENT_POLICY_VERSION
    )
    assert decision["status"] == controller.ELIGIBLE_STATUS
    assert len(decision["candidates"]) == 4
    assert len(verification.selected_entries) == 3
    assert decision["calculations"]["removal_count"] == 3
    assert decision["calculations"]["churn_ratio"] == 1.25
    assert decision["calculations"]["selector_exploration_selected_count"] == 2

    observe_source = Path(args.observe_source_jsonl)
    trial_parent = Path(args.trial_root_parent)
    paths = controller.create_initial_outputs(
        parent=trial_parent,
        verification=verification,
        repository_root=REPO_ROOT,
        repository_git_sha="a" * 40,
        started_at=verification.evaluated_at,
        observe_source=observe_source,
        observe_identity=(observe_source.stat().st_dev, observe_source.stat().st_ino),
        marks_url=str(args.marks_url),
    )
    binding = json.loads(paths.binding.read_text(encoding="utf-8"))
    assert binding["universe_immutable"] is True
    assert binding["no_fallback"] is True
    assert binding["automatic_restart"] is False
    assert binding["first_bounded_paper_experiment"] == {
        "static_baseline_overlap_report_only": True,
        "static_paper_configuration_mutated": False,
        "dynamic_universe_scope": "CONTROLLER_OWNED_IMMUTABLE_TRIAL_ROOT_ONLY",
        "subsequent_paper_or_live_promotion_authority": False,
        "separate_promotion_policy_decision_required": True,
    }


def test_first_experiment_static_transition_mutation_fails_independent_recompute(
    tmp_path: Path,
) -> None:
    inputs, decision_path, _decision_hash = generated_inputs(
        tmp_path,
        first_bounded_paper_experiment=True,
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["policy"]["max_removals"] = 2
    decision_hash = write_json(decision_path, decision, newline=False)
    args = controller_args(inputs, decision_path, decision_hash, tmp_path=tmp_path)
    with pytest.raises(
        controller.ControllerInputError,
        match="DECISION_INDEPENDENT_RECOMPUTATION_MISMATCH",
    ):
        controller.read_and_verify(args)


def test_production_controller_does_not_import_v2_governor_or_test_oracle() -> None:
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "autopilot_dynamic_allowlist_v2" not in imported
    assert not any("test" in name for name in imported)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "GOVERNOR_BLOCKED"),
        (("decision_id",), "0" * 64),
        (("policy_envelope_sha256",), "0" * 64),
        (("policy", "max_additions"), 1),
        (("current_snapshot", "producer_git_sha"), "9" * 40),
        (("candidates", 0, "lane_rank"), 99),
        (("selected_entries", 0, "selection_sequence"), 4),
        (("truncated_candidates", 0, "reason_code"), "MUTATED"),
        (("additions",), []),
        (("calculations", "churn_ratio"), 0.0),
        (
            ("methodology", "realized_selector_relation"),
            "NUMERIC_MERGE",
        ),
        (
            ("authority_boundaries", "paper_trial_start_authority"),
            True,
        ),
    ],
)
def test_material_decision_mutations_fail_independent_recomputation(
    tmp_path: Path,
    path: tuple[object, ...],
    value: object,
) -> None:
    inputs, decision_path, decision_hash = generated_inputs(tmp_path)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    target: Any = decision
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    decision_hash = write_json(decision_path, decision, newline=False)
    args = controller_args(inputs, decision_path, decision_hash, tmp_path=tmp_path)
    with pytest.raises(
        controller.ControllerInputError,
        match="DECISION_INDEPENDENT_RECOMPUTATION_MISMATCH",
    ):
        controller.read_and_verify(args)


def test_unknown_selector_direction_fails_before_output(tmp_path: Path) -> None:
    inputs, decision_path, decision_hash = generated_inputs(tmp_path)
    paths = inputs["paths"]
    current = copy.deepcopy(inputs["current"])
    assert isinstance(paths, dict)
    assert isinstance(current, dict)
    current["selector_view"]["selector_view_marginal"][0]["direction"] = "SIDEWAYS"
    current_hash = write_json(paths["current"], current)
    inputs["hashes"]["current"] = current_hash
    args = controller_args(inputs, decision_path, decision_hash, tmp_path=tmp_path)
    with pytest.raises(
        controller.ControllerInputError,
        match="UNKNOWN_SELECTOR_DIRECTION",
    ):
        controller.read_and_verify(args)


def test_hash_provenance_and_read_only_input_preservation(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    before = {
        bound.path: (bound.raw_bytes, stat.S_IMODE(bound.path.stat().st_mode))
        for bound in verification.bound_inputs
    }
    controller.read_and_verify(args)
    after = {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in before
    }
    assert after == before


def test_verify_only_reports_absent_root_and_does_not_create(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    expected_root = Path(args.trial_root_parent) / controller.trial_id(
        verification.decision["decision_id"]
    )
    with (
        mock.patch.object(
            controller,
            "verify_repository",
            return_value=(REPO_ROOT, args.repository_git_sha),
        ),
        mock.patch.object(
            controller.paper,
            "utc_now",
            return_value=verification.evaluated_at,
        ),
    ):
        result = controller.run_verify_only(args)
    assert result["status"] == "VERIFIED_NOT_STARTED"
    assert result["artifact_created"] is False
    assert not expected_root.exists()


def test_verify_only_rejects_malformed_observe_source_before_root(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    observe_path = Path(args.observe_source_jsonl)
    observe_path.write_bytes(b'{"observe_key":"trailing-partial"}')
    expected_root = Path(args.trial_root_parent) / controller.trial_id(
        verification.decision["decision_id"]
    )
    with (
        mock.patch.object(
            controller,
            "verify_repository",
            return_value=(REPO_ROOT, args.repository_git_sha),
        ),
        mock.patch.object(
            controller.paper,
            "utc_now",
            return_value=verification.evaluated_at,
        ),
        pytest.raises(
            controller.ControllerInputError,
            match="OBSERVE_SOURCE_TRAILING_PARTIAL",
        ),
    ):
        controller.run_verify_only(args)
    assert not expected_root.exists()


def test_start_time_must_be_within_automatic_age_and_validity(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, _args, verification = verified_case
    controller.validate_start_time(
        verification,
        verification.evaluated_at + dt.timedelta(seconds=300),
    )
    with pytest.raises(
        controller.ControllerInputError,
        match="CONTROLLER_START_DECISION_STALE",
    ):
        controller.validate_start_time(
            verification,
            verification.evaluated_at + dt.timedelta(seconds=301),
        )
    with pytest.raises(
        controller.ControllerInputError,
        match="CONTROLLER_START_BEFORE_DECISION",
    ):
        controller.validate_start_time(
            verification,
            verification.evaluated_at - dt.timedelta(seconds=1),
        )
    controller.validate_wall_clock_start(
        verification,
        verification.evaluated_at,
        verification.evaluated_at + dt.timedelta(seconds=60),
    )
    with pytest.raises(
        controller.ControllerInputError,
        match="CONTROLLER_STARTED_AT_BINDING_STALE",
    ):
        controller.validate_wall_clock_start(
            verification,
            verification.evaluated_at,
            verification.evaluated_at + dt.timedelta(seconds=61),
        )
    with pytest.raises(
        controller.ControllerInputError,
        match="CONTROLLER_STARTED_AT_IN_FUTURE",
    ):
        controller.validate_wall_clock_start(
            verification,
            verification.evaluated_at + dt.timedelta(seconds=1),
            verification.evaluated_at,
        )


def test_trial_root_is_deterministic_exclusive_and_never_reused(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    parent = Path(args.trial_root_parent)
    paths = controller.create_trial_paths(parent, verification)
    assert paths.root.name == controller.trial_id(verification.decision["decision_id"])
    with pytest.raises(
        controller.ControllerInputError,
        match="TRIAL_ROOT_ALREADY_EXISTS_NO_RESTART",
    ):
        controller.create_trial_paths(parent, verification)
    assert paths.root.exists()


def test_parent_descriptor_creation_is_bound_to_locked_directory(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    parent = Path(args.trial_root_parent)
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        paths = controller.create_trial_paths(
            parent,
            verification,
            parent_descriptor=descriptor,
        )
    finally:
        os.close(descriptor)
    assert paths.root.is_dir()
    assert not paths.root.is_symlink()


def test_concurrent_parent_owner_refuses_before_root_creation(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    parent = Path(args.trial_root_parent)
    observe_path = Path(args.observe_source_jsonl)
    observe_metadata = observe_path.stat()
    expected_root = parent / controller.trial_id(verification.decision["decision_id"])
    with (
        mock.patch.object(
            controller,
            "prepare_runtime_bindings",
            return_value=(
                verification,
                REPO_ROOT,
                args.repository_git_sha,
                verification.evaluated_at,
                observe_path,
                (observe_metadata.st_dev, observe_metadata.st_ino),
                args.marks_url,
                parent,
            ),
        ),
        mock.patch.object(
            controller.fcntl,
            "flock",
            side_effect=BlockingIOError,
        ),
        pytest.raises(
            controller.ControllerInputError,
            match="CONTROLLER_CONCURRENT_OWNER",
        ),
    ):
        controller.run_start(args)
    assert not expected_root.exists()


def test_initial_output_failure_retains_and_reports_partial_root(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    parent = Path(args.trial_root_parent)
    observe_path = Path(args.observe_source_jsonl)
    observe_metadata = observe_path.stat()
    expected_root = parent / controller.trial_id(verification.decision["decision_id"])
    with (
        mock.patch.object(
            controller,
            "prepare_runtime_bindings",
            return_value=(
                verification,
                REPO_ROOT,
                args.repository_git_sha,
                verification.evaluated_at,
                observe_path,
                (observe_metadata.st_dev, observe_metadata.st_ino),
                args.marks_url,
                parent,
            ),
        ),
        mock.patch.object(controller, "recheck_verification_inputs", return_value=None),
        mock.patch.object(
            controller,
            "verify_repository",
            return_value=(REPO_ROOT, args.repository_git_sha),
        ),
        mock.patch.object(
            controller,
            "write_exclusive",
            side_effect=OSError("synthetic output failure"),
        ),
        pytest.raises(
            controller.ControllerInputError,
            match="INITIAL_OUTPUT_CREATE_FAILED",
        ) as captured,
    ):
        controller.run_start(args)
    assert captured.value.artifact_created is True
    assert captured.value.trial_root == str(expected_root)
    assert expected_root.is_dir()


def test_loop_reuses_paper_mechanics_and_finishes_naturally(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    started_at = verification.evaluated_at
    selected = dict(verification.selected_entries[1])
    candidate = observe_candidate(selected, started_at)
    observe_path = Path(args.observe_source_jsonl)
    raw = (json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n").encode()
    observe_path.write_bytes(raw)
    observe_metadata = observe_path.stat()
    paths = controller.create_initial_outputs(
        parent=Path(args.trial_root_parent),
        verification=verification,
        repository_root=REPO_ROOT,
        repository_git_sha=args.repository_git_sha,
        started_at=started_at,
        observe_source=observe_path,
        observe_identity=(
            observe_metadata.st_dev,
            observe_metadata.st_ino,
        ),
        marks_url=args.marks_url,
    )
    clock_values = iter([0.0, 0.0, 60.0, 300.0, 360.0, 86400.0])
    mark = {
        **selected["key"],
        "mark_at": controller.format_timestamp(started_at + dt.timedelta(minutes=5)),
        "source_type": "paper_trade_outcome",
        "net_bps": 7.25,
    }
    marks = iter(
        [
            ([], hashlib.sha256(b"[]").hexdigest()),
            ([mark], hashlib.sha256(b"[mark]").hexdigest()),
            ([], hashlib.sha256(b"[]").hexdigest()),
        ]
    )
    with (
        mock.patch.object(
            controller,
            "verify_repository",
            return_value=(REPO_ROOT, args.repository_git_sha),
        ),
        mock.patch.object(controller, "recheck_verification_inputs", return_value=None),
    ):
        result = controller.run_controller_loop(
            verification=verification,
            repository_root=REPO_ROOT,
            repository_git_sha=args.repository_git_sha,
            started_at=started_at,
            observe_source=observe_path,
            observe_identity=(
                observe_metadata.st_dev,
                observe_metadata.st_ino,
            ),
            marks_url=args.marks_url,
            paths=paths,
            monotonic=lambda: next(clock_values),
            sleeper=lambda _seconds: None,
            marks_fetcher=lambda _url: next(marks),
        )
    assert result["status"] == "COMPLETE"
    assert result["stop_reason"] == "NATURAL_COMPLETION"
    provenance = [
        json.loads(line)
        for line in paths.provenance.read_text(encoding="utf-8").splitlines()
    ]
    validator = provenance_validator()
    assert all(list(validator.iter_errors(record)) == [] for record in provenance)
    lifecycle = [
        record["subject"]["lifecycle_status"]
        for record in provenance
        if record["record_type"] == "TRIAL_MANIFEST"
    ]
    assert lifecycle == ["RUNNING", "EXIT_ONLY", "COMPLETE"]
    assert any(
        record["record_type"] == "PAPER_POSITION_BINDING"
        and record["subject"]["position_status"] == "OPEN"
        for record in provenance
    )
    assert any(
        record["record_type"] == "PAPER_POSITION_BINDING"
        and record["subject"]["position_status"] == "CLOSED"
        for record in provenance
    )


def test_exposure_caps_are_controller_owned(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, _args, verification = verified_case
    selected = controller.selected_entry_map(verification)
    keys = list(selected)
    key = keys[0]
    position = {
        "schema_version": 1,
        "mode": "paper_only",
        "paper_position_id": "open-1",
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
        "status": "OPEN",
    }
    assert (
        controller.exposure_refusal(
            candidate_key=key,
            candidate_origin=selected[key],
            positions=[position],
            selected=selected,
        )
        == "MAX_OPEN_POSITIONS_PER_EXACT_KEY"
    )


def test_out_of_universe_paper_result_refuses_before_artifact_write(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
    tmp_path: Path,
) -> None:
    _inputs, args, verification = verified_case
    paths = controller.TrialPaths(
        root=tmp_path / "trial",
        binding=tmp_path / "trial" / controller.BINDING_NAME,
        provenance=tmp_path / "trial" / controller.PROVENANCE_NAME,
        events=tmp_path / "trial" / controller.EVENTS_NAME,
        paper_root=tmp_path / "trial" / controller.PAPER_ROOT_NAME,
    )
    out_of_universe = {
        "pair_id": "PF_UNKNOWN__PF_OUTSIDE",
        "timeframe": "1m",
        "selected_variant": "ROBUST_Z",
        "direction": "LONG_SPREAD",
    }
    with (
        mock.patch.object(
            controller.paper,
            "write_artifacts",
            side_effect=AssertionError("must validate before writing"),
        ) as writer,
        pytest.raises(
            controller.ControllerInputError,
            match="PAPER_DECISION_OUTSIDE_IMMUTABLE_UNIVERSE",
        ),
    ):
        controller.persist_paper_result(
            result=controller.paper.RunResult(
                decisions=[out_of_universe],
                positions=[],
            ),
            paths=paths,
            verification=verification,
            repository_git_sha=args.repository_git_sha,
            started_at=verification.evaluated_at,
            observed_at=verification.evaluated_at,
            selected=controller.selected_entry_map(verification),
        )
    writer.assert_not_called()
    assert not paths.paper_root.exists()


def test_expired_decision_stops_without_fallback(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    started_at = verification.evaluated_at
    verification = dataclasses.replace(
        verification,
        valid_until=started_at + dt.timedelta(seconds=60),
    )
    observe_path = Path(args.observe_source_jsonl)
    observe_metadata = observe_path.stat()
    paths = controller.create_initial_outputs(
        parent=Path(args.trial_root_parent),
        verification=verification,
        repository_root=REPO_ROOT,
        repository_git_sha=args.repository_git_sha,
        started_at=started_at,
        observe_source=observe_path,
        observe_identity=(observe_metadata.st_dev, observe_metadata.st_ino),
        marks_url=args.marks_url,
    )
    clock_values = iter([0.0, 60.0])
    with (
        mock.patch.object(
            controller,
            "verify_repository",
            return_value=(REPO_ROOT, args.repository_git_sha),
        ),
        mock.patch.object(controller, "recheck_verification_inputs", return_value=None),
    ):
        result = controller.run_controller_loop(
            verification=verification,
            repository_root=REPO_ROOT,
            repository_git_sha=args.repository_git_sha,
            started_at=started_at,
            observe_source=observe_path,
            observe_identity=(observe_metadata.st_dev, observe_metadata.st_ino),
            marks_url=args.marks_url,
            paths=paths,
            monotonic=lambda: next(clock_values),
            sleeper=lambda _seconds: None,
            marks_fetcher=lambda _url: ([], hashlib.sha256(b"[]").hexdigest()),
        )
    assert result["status"] == "NO_GO"
    assert result["stop_reason"] == "DECISION_EXPIRED"
    assert result["unresolved_open_position_count"] == 0
    final_manifest = json.loads(
        paths.provenance.read_text(encoding="utf-8").splitlines()[-1]
    )
    assert final_manifest["subject"]["lifecycle_status"] == "NO_GO"
    assert final_manifest["subject"]["stop_reason"] == "DECISION_EXPIRED"
    assert not paths.paper_root.exists()
    binding = json.loads(paths.binding.read_text(encoding="utf-8"))
    assert binding["no_fallback"] is True
    assert binding["universe_immutable"] is True


def test_partial_root_is_retained_after_post_creation_failure(
    verified_case: tuple[
        dict[str, object], argparse.Namespace, controller.Verification
    ],
) -> None:
    _inputs, args, verification = verified_case
    observe_path = Path(args.observe_source_jsonl)
    observe_metadata = observe_path.stat()
    paths = controller.create_initial_outputs(
        parent=Path(args.trial_root_parent),
        verification=verification,
        repository_root=REPO_ROOT,
        repository_git_sha=args.repository_git_sha,
        started_at=verification.evaluated_at,
        observe_source=observe_path,
        observe_identity=(
            observe_metadata.st_dev,
            observe_metadata.st_ino,
        ),
        marks_url=args.marks_url,
    )
    assert paths.root.exists()
    assert paths.binding.exists()
    assert paths.provenance.exists()
    with pytest.raises(controller.ControllerInputError):
        controller.stable_read_bytes(
            observe_path,
            source="OBSERVE_SOURCE",
            expected_identity=(0, 0),
        )
    assert paths.root.exists()
    assert paths.binding.exists()


def test_post_root_refusal_reports_retained_artifact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = controller.ControllerInputError(
        "MARKS_GET_FAILED",
        artifact_created=True,
        trial_root="/retained/trial",
    )
    with mock.patch.object(controller, "run_start", side_effect=error):
        assert controller.main(["--enabled", "--start"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["status"] == "NO_GO"
    assert diagnostic["artifact_created"] is True
    assert diagnostic["trial_root"] == "/retained/trial"
    assert diagnostic["automatic_retry"] is False
    assert diagnostic["repair_or_cleanup_attempted"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8083/marks",
        "http://example.com:8083/marks",
        "http://localhost:8083/marks",
        "http://user:pass@127.0.0.1:8083/marks",
        "http://127.0.0.1/marks",
        "http://127.0.0.1:not-a-port/marks",
        "http://[::1/marks",
        "file:///tmp/marks.json",
    ],
)
def test_marks_adapter_rejects_non_exact_loopback_get_surfaces(url: str) -> None:
    with pytest.raises(controller.ControllerInputError):
        controller.require_loopback_get_url(url)


def test_network_adapter_constructs_get_and_refuses_redirects() -> None:
    source = CONTROLLER_PATH.read_text(encoding="utf-8")
    assert 'method="GET"' in source
    assert "_NoRedirect" in source
    assert "ProxyHandler({})" in source
    assert "POST" not in source


def test_paper_trade_response_is_adapted_to_existing_mark_mechanics() -> None:
    rows = [
        {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "selected_variant": "ROBUST_Z",
            "direction": "SHORT_SPREAD",
            "entry_ts": "2026-07-28T00:00:00Z",
            "exit_ts": "2026-07-28T00:05:00Z",
            "net_bps": 7.25,
        },
        {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "selected_variant": "ROBUST_Z",
            "direction": "SHORT_SPREAD",
            "entry_ts": "2026-07-28T00:10:00Z",
            "exit_ts": None,
            "net_bps": None,
        },
    ]
    assert controller.adapt_paper_marks(rows) == [
        {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "timeframe": "1m",
            "selected_variant": "ROBUST_Z",
            "direction": "SHORT_SPREAD",
            "mark_at": "2026-07-28T00:05:00Z",
            "source_type": "paper_trade_outcome",
            "net_bps": 7.25,
        }
    ]
    with pytest.raises(
        controller.ControllerInputError,
        match="REALIZED_MARK_DIRECTION_NON_ACTIONABLE",
    ):
        controller.adapt_paper_marks([{**rows[0], "direction": "NONE"}])


def test_observe_partial_duplicate_conflict_and_unknown_direction_fail_closed() -> None:
    with pytest.raises(
        controller.ControllerInputError,
        match="OBSERVE_SOURCE_TRAILING_PARTIAL",
    ):
        controller.parse_jsonl_observe_rows(b'{"observe_key":"x"}')
    first = b'{"observe_key":"x","direction_hint":"LONG_SPREAD"}\n'
    conflicting = b'{"observe_key":"x","direction_hint":"SHORT_SPREAD"}\n'
    with pytest.raises(
        controller.ControllerInputError,
        match="OBSERVE_SOURCE_DUPLICATE_IDENTITY_CONFLICT",
    ):
        controller.parse_jsonl_observe_rows(first + conflicting)
    rows = controller.parse_jsonl_observe_rows(
        b'{"observe_key":"x","direction_hint":"SIDEWAYS"}\n'
    )
    with pytest.raises(
        controller.ControllerInputError, match="UNKNOWN_OBSERVE_DIRECTION"
    ):
        controller.actionable_observe_rows(rows, {}, set())
