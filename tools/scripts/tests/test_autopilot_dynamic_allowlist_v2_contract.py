import copy
import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[3]
DECISION_SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_allowlist_decision_v2.schema.json"
)
PROVENANCE_SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_paper_provenance_v2.schema.json"
)
ELIGIBLE_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_decision_v2.eligible.example.json"
)
BLOCKED_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_decision_v2.blocked.example.json"
)
FIRST_EXPERIMENT_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_decision_v2.first_bounded_paper_experiment.example.json"
)
PROVENANCE_EXAMPLE_PATHS = [
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_paper_trial_manifest_v2.example.json",
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_paper_decision_binding_v2.example.json",
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_paper_position_binding_v2.example.json",
]
PROTECTED_V1_HASHES = {
    "specs/contracts/autopilot_dynamic_allowlist_decision.schema.json": "6c35dbefab09930792e37687ce96b8c7360759386bdb182cc71693cc9899ce37",
    "specs/examples/autopilot_dynamic_allowlist_decision.example.json": "3b2dacf18a2d2ff07241006934c27b2327e02300ec70808f31b68559e9169a42",
    "tools/scripts/tests/test_autopilot_dynamic_allowlist_contract.py": "6f5229cd15b87ae47d51183210c7976739af8e82161ef8ceeb27119bc4ae2175",
    "specs/contracts/autopilot_paper_decision_record.schema.json": "e38aa099abf52f2375a31c1df695f5feeafa5ca5341aa151dc8dd84ba06dae15",
    "specs/contracts/autopilot_paper_position.schema.json": "0b1497f4cd877dbcbb03a96ad512397b1cd3860678867fb5ba628ff35d7e97a8",
    "tools/scripts/autopilot_dynamic_allowlist.py": "86e1ef61d2a1ff34314e7dab6477b2e8c84977645882d9acbd9db9d6c542f2ae",
    "tools/scripts/autopilot_paper.py": "d894c7819814af9084de8c3245986c725a775d7c77194a39f94f6fee8828d2cd",
}
RFC3339_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_rfc3339(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(
        value.replace("Z", "+00:00").replace("z", "+00:00")
    )


def is_rfc3339_timestamp(value: object) -> bool:
    if not isinstance(value, str) or RFC3339_TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        parsed = parse_rfc3339(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def make_validator(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    checker = FormatChecker()
    checker.checks("date-time")(is_rfc3339_timestamp)
    return Draft202012Validator(schema, format_checker=checker)


def key_tuple(key: dict) -> tuple[str, str, str, str]:
    return (
        key["pair_id"],
        key["timeframe"],
        key["selected_variant"],
        key["direction"],
    )


def key_string(key: dict) -> str:
    return "|".join(key_tuple(key))


def key_set(entries: list[dict]) -> set[tuple[str, str, str, str]]:
    return {key_tuple(entry.get("key", entry)) for entry in entries}


def policy_hash(payload: dict) -> str:
    envelope = {
        "policy": payload["policy"],
        "policy_version": payload["policy_version"],
    }
    return sha256_bytes(canonical_json_bytes(envelope))


def prior_set_hash(payload: dict) -> str:
    entries = sorted(payload["prior_active_entries"], key=key_tuple)
    return sha256_bytes(canonical_json_bytes(entries))


def decision_id(payload: dict) -> str:
    envelope = {
        "current_snapshot_sha256": payload["current_snapshot"]["sha256"],
        "evaluated_at": payload["evaluated_at"],
        "governor_config_sha256": payload["governor_config_source"]["sha256"],
        "paper_run_config_sha256": payload["paper_run_config"]["sha256"],
        "policy_envelope_sha256": payload["policy_envelope_sha256"],
        "previous_snapshot_sha256": payload["previous_snapshot"]["sha256"],
        "prior_active_set_sha256": payload["prior_active_set_sha256"],
    }
    return sha256_bytes(canonical_json_bytes(envelope))


def candidate_rank(candidate: dict) -> tuple:
    rank = candidate["rank_components"]
    if candidate["evidence_class"] == "REALIZED_AND_SELECTOR":
        return (
            -rank["minimum_total_b2c_score"],
            -rank["minimum_closed_position_count"],
            -rank["minimum_trade_now_ratio"],
            rank["exact_key_tiebreak"],
        )
    return (
        -rank["minimum_trade_now_ratio"],
        -rank["minimum_trade_now_count"],
        -rank["minimum_selector_stated_mean_net_edge_bps"],
        rank["exact_key_tiebreak"],
    )


def instrument_ids(key: dict) -> tuple[str, str]:
    left, right = key["pair_id"].split("__")
    return left, right


def concentrations(
    entries: list[dict], additions: list[dict]
) -> tuple[Counter, Counter, Counter]:
    pair_counts: Counter = Counter()
    pair_variant_direction_counts: Counter = Counter()
    instrument_counts: Counter = Counter()
    addition_keys = key_set(additions)
    addition_instrument_counts: Counter = Counter()
    for entry in entries:
        key = entry.get("key", entry)
        pair_counts[key["pair_id"]] += 1
        pair_variant_direction_counts[
            (key["pair_id"], key["timeframe"], key["selected_variant"])
        ] += 1
        for instrument in instrument_ids(key):
            instrument_counts[instrument] += 1
            if key_tuple(key) in addition_keys:
                addition_instrument_counts[instrument] += 1
    return (
        pair_counts,
        pair_variant_direction_counts,
        instrument_counts,
        addition_instrument_counts,
    )


def audit_common(payload: dict) -> None:
    assert payload["policy_envelope_sha256"] == policy_hash(payload)
    assert payload["prior_active_set_sha256"] == prior_set_hash(payload)
    assert payload["decision_id"] == decision_id(payload)
    assert (
        payload["current_snapshot"]["sha256"] != payload["previous_snapshot"]["sha256"]
    )
    assert (
        payload["current_snapshot"]["selector_config_sha256"]
        == (payload["previous_snapshot"]["selector_config_sha256"])
    )
    assert payload["current_snapshot"]["schema_version"] == 2
    assert payload["previous_snapshot"]["schema_version"] == 2
    assert payload["methodology"]["realized_selector_relation"] == (
        "SEPARATE_STREAMS_SET_MEMBERSHIP_NO_NUMERIC_MERGE"
    )
    assert payload["methodology"]["none_direction_behavior"] == (
        "NON_ACTIONABLE_DISTINCT_FROM_NULL"
    )
    assert payload["methodology"]["null_direction_behavior"] == (
        "NON_ACTIONABLE_MISSING_DIRECTION"
    )
    assert payload["methodology"]["unknown_direction_behavior"] == (
        "REJECT_INPUT_NO_ARTIFACT"
    )
    assert payload["direction_counts"]["selector_unknown_count"] == 0
    assert payload["direction_counts"]["realized_none_count"] == 0
    assert payload["direction_counts"]["realized_null_count"] == 0
    assert payload["direction_counts"]["realized_unknown_count"] == 0
    assert payload["direction_counts"]["selector_none_count"] > 0
    assert payload["direction_counts"]["selector_null_count"] > 0
    assert payload["per_output_operator_approval_required"] is False
    assert payload["auto2d_verification"]["independent_recomputation_required"] is True
    assert payload["auto2d_verification"]["governor_self_approval_accepted"] is False
    assert payload["auto2d_verification"]["schema_v1_decision_accepted"] is False
    assert payload["auto2d_verification"]["raw_snapshot_accepted_as_decision"] is False
    assert not any(payload["authority_boundaries"].values())
    assert payload["policy"]["fallback_behavior"] == "NO_FALLBACK"
    assert (
        parse_rfc3339(payload["valid_until"]) - parse_rfc3339(payload["evaluated_at"])
    ).total_seconds() == payload["policy"]["decision_validity_seconds"]


def audit_eligible(payload: dict) -> None:
    audit_common(payload)
    first_experiment = (
        payload["policy_version"] == "auto2c-v2-first-bounded-paper-experiment-1"
    )
    assert payload["status"] == "POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION"
    assert payload["reason_codes"] == []
    assert all(
        result["verdict"] == "PASS" for result in payload["gate_results"].values()
    )
    assert payload["gate_summary"] == {
        "pass_count": 13,
        "block_count": 0,
        "total_count": 13,
    }

    separation = (
        parse_rfc3339(payload["current_snapshot"]["source_cutoff_at"])
        - parse_rfc3339(payload["previous_snapshot"]["source_cutoff_at"])
    ).total_seconds()
    age = (
        parse_rfc3339(payload["evaluated_at"])
        - parse_rfc3339(payload["current_snapshot"]["source_cutoff_at"])
    ).total_seconds()
    assert separation == payload["calculations"]["source_cutoff_separation_seconds"]
    assert separation >= payload["policy"]["min_source_cutoff_separation_seconds"]
    assert age == payload["calculations"]["current_source_age_seconds"]
    assert age <= payload["policy"]["max_current_source_age_seconds"]

    candidates = payload["candidates"]
    assert len(key_set(candidates)) == len(candidates)
    for candidate in candidates:
        key = candidate["key"]
        rank = candidate["rank_components"]
        assert key["direction"] in {"LONG_SPREAD", "SHORT_SPREAD"}
        assert rank["exact_key_tiebreak"] == key_string(key)
        for snapshot_name in ("current_selector", "previous_selector"):
            selector = candidate[snapshot_name]
            assert (
                selector["selector_row_count"]
                >= payload["policy"]["min_selector_rows_each_snapshot"]
            )
            assert (
                selector["trade_now_count"]
                >= payload["policy"]["min_trade_now_count_each_snapshot"]
            )
            assert (
                selector["time_in_trade_now_ratio"]
                >= payload["policy"]["min_trade_now_ratio_each_snapshot"]
            )
            assert math.isfinite(selector["selector_stated_mean_net_edge_bps"])
            assert selector["selector_stated_mean_net_edge_bps"] > 0
        assert rank["minimum_trade_now_ratio"] == min(
            candidate["current_selector"]["time_in_trade_now_ratio"],
            candidate["previous_selector"]["time_in_trade_now_ratio"],
        )
        assert rank["minimum_trade_now_count"] == min(
            candidate["current_selector"]["trade_now_count"],
            candidate["previous_selector"]["trade_now_count"],
        )
        assert rank["minimum_selector_stated_mean_net_edge_bps"] == min(
            candidate["current_selector"]["selector_stated_mean_net_edge_bps"],
            candidate["previous_selector"]["selector_stated_mean_net_edge_bps"],
        )
        if candidate["evidence_class"] == "REALIZED_AND_SELECTOR":
            assert candidate["current_realized"] is not None
            assert candidate["previous_realized"] is not None
            assert rank["minimum_total_b2c_score"] == min(
                candidate["current_realized"]["total_b2c_score"],
                candidate["previous_realized"]["total_b2c_score"],
            )
            assert rank["minimum_closed_position_count"] == min(
                candidate["current_realized"]["closed_position_count"],
                candidate["previous_realized"]["closed_position_count"],
            )
            assert candidate["absent_from_prior_active_set"] is False
        else:
            assert candidate["evidence_class"] == "SELECTOR_EXPLORATION"
            assert candidate["current_realized"] is None
            assert candidate["previous_realized"] is None
            assert rank["minimum_total_b2c_score"] is None
            assert rank["minimum_closed_position_count"] is None
            assert candidate["absent_from_prior_active_set"] is True

    for evidence_class in ("REALIZED_AND_SELECTOR", "SELECTOR_EXPLORATION"):
        lane = [item for item in candidates if item["evidence_class"] == evidence_class]
        assert lane == sorted(lane, key=candidate_rank)
        assert [item["lane_rank"] for item in lane] == list(range(1, len(lane) + 1))

    selected = payload["selected_entries"]
    selected_keys = key_set(selected)
    prior_keys = key_set(payload["prior_active_entries"])
    candidate_keys = key_set(candidates)
    truncated_keys = key_set(payload["truncated_candidates"])
    skipped_keys = key_set(payload["skipped_candidates"])
    assert [item["selection_sequence"] for item in selected] == list(
        range(1, len(selected) + 1)
    )
    assert key_set(payload["additions"]) == selected_keys - prior_keys
    assert key_set(payload["removals"]) == prior_keys - selected_keys
    assert key_set(payload["retained_entries"]) == prior_keys & selected_keys
    assert selected_keys | truncated_keys | skipped_keys == candidate_keys
    assert not (selected_keys & truncated_keys)
    assert not (selected_keys & skipped_keys)
    assert payload["selection_steps"][0]["rule"] == "RESERVE_BEST_QUALIFYING_ADDITION"
    assert key_tuple(payload["selection_steps"][0]["candidate_key"]) == key_tuple(
        selected[0]["key"]
    )
    assert selected[0]["evidence_class"] == "SELECTOR_EXPLORATION"
    assert selected[0]["key"]["pair_id"] == (
        "PF_SUIUSD__PF_ARBUSD" if first_experiment else "PF_ETHUSD__PF_SOLUSD"
    )

    additions = payload["additions"]
    removals = payload["removals"]
    symmetric_difference = prior_keys ^ selected_keys
    denominator = max(
        payload["policy"]["churn_floor_capacity"],
        len(prior_keys),
    )
    assert payload["calculations"]["change_count"] == len(symmetric_difference)
    assert payload["calculations"]["churn_denominator_count"] == denominator
    assert (
        payload["calculations"]["churn_ratio"]
        == len(symmetric_difference) / denominator
    )
    assert len(selected) <= payload["policy"]["max_selected_entries"]
    assert len(additions) <= payload["policy"]["max_additions"]
    if first_experiment:
        assert payload["policy"]["max_removals"] is None
        assert payload["policy"]["max_churn_ratio"] is None
        assert payload["methodology"]["static_baseline_transition_behavior"] == (
            "REPORT_OVERLAP_ONLY_NO_REMOVAL_OR_CHURN_GATE"
        )
        assert (
            payload["authority_boundaries"][
                "subsequent_paper_or_live_promotion_authority"
            ]
            is False
        )
    else:
        assert len(removals) <= payload["policy"]["max_removals"]
        assert (
            payload["calculations"]["churn_ratio"]
            <= payload["policy"]["max_churn_ratio"]
        )
    exploration_count = sum(
        item["evidence_class"] == "SELECTOR_EXPLORATION" for item in selected
    )
    assert (
        exploration_count
        == payload["calculations"]["selector_exploration_selected_count"]
    )
    assert (
        1 <= exploration_count <= payload["policy"]["max_selector_exploration_entries"]
    )

    pair_counts, pair_variant_counts, instrument_counts, addition_instrument_counts = (
        concentrations(selected, additions)
    )
    assert max(pair_counts.values()) <= payload["policy"]["max_entries_per_pair_id"]
    assert (
        max(pair_variant_counts.values())
        <= (payload["policy"]["max_directions_per_pair_variant"])
    )
    assert (
        max(instrument_counts.values())
        <= (payload["policy"]["max_entries_per_full_instrument"])
    )
    assert (
        max(addition_instrument_counts.values())
        <= (payload["policy"]["max_new_additions_per_full_instrument"])
    )
    assert payload["calculations"]["selected_entry_count"] == len(selected)
    assert payload["calculations"]["addition_count"] == len(additions)
    assert payload["calculations"]["removal_count"] == len(removals)
    assert payload["calculations"]["qualifying_candidate_count"] == len(candidates)


def fits_concentration(selected: list[dict], candidate: dict, policy: dict) -> bool:
    pair_counts, pair_variant_counts, instrument_counts, _ = concentrations(
        selected, []
    )
    key = candidate["key"]
    pair_variant = (key["pair_id"], key["timeframe"], key["selected_variant"])
    return (
        pair_counts[key["pair_id"]] < policy["max_entries_per_pair_id"]
        and pair_variant_counts[pair_variant]
        < policy["max_directions_per_pair_variant"]
        and all(
            instrument_counts[instrument] < policy["max_entries_per_full_instrument"]
            for instrument in instrument_ids(key)
        )
    )


@pytest.fixture
def eligible() -> dict:
    return load_json(ELIGIBLE_EXAMPLE_PATH)


@pytest.fixture
def blocked() -> dict:
    return load_json(BLOCKED_EXAMPLE_PATH)


@pytest.fixture
def first_experiment() -> dict:
    return load_json(FIRST_EXPERIMENT_EXAMPLE_PATH)


@pytest.fixture
def decision_validator() -> Draft202012Validator:
    return make_validator(DECISION_SCHEMA_PATH)


@pytest.fixture
def provenance_validator() -> Draft202012Validator:
    return make_validator(PROVENANCE_SCHEMA_PATH)


def test_v2_schemas_and_examples_validate(
    decision_validator: Draft202012Validator,
    provenance_validator: Draft202012Validator,
    eligible: dict,
    blocked: dict,
    first_experiment: dict,
) -> None:
    assert list(decision_validator.iter_errors(eligible)) == []
    assert list(decision_validator.iter_errors(blocked)) == []
    assert list(decision_validator.iter_errors(first_experiment)) == []
    for path in PROVENANCE_EXAMPLE_PATHS:
        assert list(provenance_validator.iter_errors(load_json(path))) == []


def test_eligible_example_passes_independent_semantic_audit(eligible: dict) -> None:
    audit_eligible(eligible)


def test_first_experiment_example_passes_independent_semantic_audit(
    first_experiment: dict,
) -> None:
    audit_eligible(first_experiment)
    assert len(first_experiment["candidates"]) == 4
    assert len(first_experiment["selected_entries"]) == 3
    assert len(first_experiment["skipped_candidates"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["policy"].__setitem__("max_removals", 2),
        lambda payload: payload["policy"].__setitem__("max_churn_ratio", 0.5),
        lambda payload: payload["policy"].pop("policy_route"),
        lambda payload: payload["methodology"].pop(
            "static_baseline_transition_behavior"
        ),
        lambda payload: payload["authority_boundaries"].pop(
            "subsequent_paper_or_live_promotion_authority"
        ),
    ],
)
def test_first_experiment_route_metadata_is_contractual(
    decision_validator: Draft202012Validator,
    first_experiment: dict,
    mutation,
) -> None:
    payload = copy.deepcopy(first_experiment)
    mutation(payload)
    assert list(decision_validator.iter_errors(payload))


def test_historical_policy_cannot_smuggle_experiment_route_fields(
    decision_validator: Draft202012Validator,
    eligible: dict,
) -> None:
    payload = copy.deepcopy(eligible)
    payload["policy"]["policy_route"] = "FIRST_BOUNDED_PAPER_EXPERIMENT"
    assert list(decision_validator.iter_errors(payload))


def test_blocked_decision_is_empty_non_actuating_and_reasoned(blocked: dict) -> None:
    audit_common(blocked)
    assert blocked["status"] == "GOVERNOR_BLOCKED"
    assert blocked["reason_codes"] == ["CURRENT_SOURCE_STALE"]
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
        assert blocked[field] == []
    assert blocked["gate_results"]["current_source_freshness"]["verdict"] == "BLOCK"
    assert blocked["calculations"]["current_source_age_seconds"] == 1801


@pytest.mark.parametrize("direction", [None, "NONE", "UNKNOWN_DIRECTION"])
def test_none_null_and_unknown_cannot_enter_actionable_exact_keys(
    decision_validator: Draft202012Validator,
    eligible: dict,
    direction: object,
) -> None:
    payload = copy.deepcopy(eligible)
    payload["selected_entries"][0]["key"]["direction"] = direction
    assert list(decision_validator.iter_errors(payload))


def test_none_and_null_evidence_counts_remain_distinct(
    decision_validator: Draft202012Validator,
    eligible: dict,
) -> None:
    assert eligible["direction_counts"]["selector_none_count"] == 30
    assert eligible["direction_counts"]["selector_null_count"] == 4
    payload = copy.deepcopy(eligible)
    del payload["direction_counts"]["selector_null_count"]
    assert list(decision_validator.iter_errors(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("required_comparable_v2_snapshots", 1),
        ("min_source_cutoff_separation_seconds", 86399),
        ("max_current_source_age_seconds", 1801),
        ("max_selected_entries", 5),
        ("max_additions", 3),
        ("max_selector_exploration_entries", 3),
        ("max_entries_per_pair_id", 3),
        ("max_entries_per_full_instrument", 3),
        ("max_churn_ratio", 0.51),
        ("decision_validity_seconds", 108001),
        ("fallback_behavior", "USE_PREVIOUS"),
        ("candidate_overflow_behavior", "BLOCK"),
        ("concentration_overflow_behavior", "BLOCK"),
        ("max_simultaneously_open_paper_positions", 3),
        ("controller_hard_runtime_seconds", 90001),
    ],
)
def test_ratified_policy_values_are_contractual(
    decision_validator: Draft202012Validator,
    eligible: dict,
    field: str,
    value: object,
) -> None:
    payload = copy.deepcopy(eligible)
    payload["policy"][field] = value
    assert list(decision_validator.iter_errors(payload))


def test_ranking_mutations_fail_independent_audit(eligible: dict) -> None:
    for mutation in (
        lambda payload: payload["candidates"][0]["rank_components"].__setitem__(
            "minimum_total_b2c_score", 99
        ),
        lambda payload: payload["candidates"][0].__setitem__("lane_rank", 2),
        lambda payload: payload["candidates"].__setitem__(
            slice(0, 2), list(reversed(payload["candidates"][0:2]))
        ),
    ):
        payload = copy.deepcopy(eligible)
        mutation(payload)
        with pytest.raises(AssertionError):
            audit_eligible(payload)


def test_hash_identity_and_time_mutations_fail_independent_audit(
    eligible: dict,
) -> None:
    for mutation in (
        lambda payload: payload.__setitem__("decision_id", "0" * 64),
        lambda payload: payload.__setitem__("policy_envelope_sha256", "0" * 64),
        lambda payload: payload.__setitem__("prior_active_set_sha256", "0" * 64),
        lambda payload: payload["current_snapshot"].__setitem__(
            "selector_config_sha256", "0" * 64
        ),
        lambda payload: payload["calculations"].__setitem__(
            "source_cutoff_separation_seconds", 86399
        ),
        lambda payload: payload["calculations"].__setitem__(
            "current_source_age_seconds", 1801
        ),
    ):
        payload = copy.deepcopy(eligible)
        mutation(payload)
        with pytest.raises(AssertionError):
            audit_eligible(payload)


def test_eligible_status_requires_complete_comparable_selector_history(
    decision_validator: Draft202012Validator,
    eligible: dict,
) -> None:
    for snapshot in ("current_snapshot", "previous_snapshot"):
        for field in ("selector_view_present", "selector_view_churn_available"):
            payload = copy.deepcopy(eligible)
            payload[snapshot][field] = False
            assert list(decision_validator.iter_errors(payload))


def test_set_and_churn_mutations_fail_independent_audit(eligible: dict) -> None:
    for mutation in (
        lambda payload: payload["additions"].clear(),
        lambda payload: payload["removals"].clear(),
        lambda payload: payload["retained_entries"].clear(),
        lambda payload: payload["calculations"].__setitem__("change_count", 1),
        lambda payload: payload["calculations"].__setitem__("churn_ratio", 0.25),
    ):
        payload = copy.deepcopy(eligible)
        mutation(payload)
        with pytest.raises(AssertionError):
            audit_eligible(payload)


def test_concentration_overflow_is_skipped_and_next_candidate_is_considered(
    eligible: dict,
) -> None:
    selected = copy.deepcopy(eligible["selected_entries"][1:3])
    violating = copy.deepcopy(eligible["candidates"][3])
    violating["key"]["pair_id"] = "PF_DOGEUSD__PF_PEPEUSD"
    next_candidate = copy.deepcopy(eligible["candidates"][2])
    assert fits_concentration(selected, violating, eligible["policy"]) is False
    assert fits_concentration(selected, next_candidate, eligible["policy"]) is True
    considered = [
        candidate
        for candidate in (violating, next_candidate)
        if fits_concentration(selected, candidate, eligible["policy"])
    ]
    assert [key_string(candidate["key"]) for candidate in considered] == [
        key_string(next_candidate["key"])
    ]


def test_blocked_status_rejects_nonempty_proposed_state(
    decision_validator: Draft202012Validator,
    blocked: dict,
    eligible: dict,
) -> None:
    payload = copy.deepcopy(blocked)
    payload["selected_entries"] = [copy.deepcopy(eligible["selected_entries"][0])]
    assert list(decision_validator.iter_errors(payload))


def test_automatic_acceptance_is_independent_and_non_actuating(eligible: dict) -> None:
    assert eligible["per_output_operator_approval_required"] is False
    assert (
        eligible["authority"]
        == "non_actuating_requires_independent_auto2d_verification"
    )
    assert all(
        eligible["auto2d_verification"][field] is True
        for field in (
            "independent_recomputation_required",
            "policy_envelope_hash_match_required",
            "decision_hash_match_required",
            "raw_input_hash_recheck_required",
            "immutable_universe_required",
        )
    )
    assert not any(eligible["authority_boundaries"].values())


def test_output_cardinality_limits_reject_excess(
    decision_validator: Draft202012Validator,
    eligible: dict,
) -> None:
    mutations = (
        ("selected_entries", [copy.deepcopy(eligible["selected_entries"][0])] * 5),
        (
            "additions",
            [
                copy.deepcopy(eligible["candidates"][index]["key"])
                for index in (3, 4, 5)
            ],
        ),
        (
            "removals",
            [
                copy.deepcopy(eligible["candidates"][index]["key"])
                for index in (0, 1, 2)
            ],
        ),
    )
    for field, value in mutations:
        payload = copy.deepcopy(eligible)
        payload[field] = value
        errors = list(decision_validator.iter_errors(payload))
        assert errors
        assert any(error.validator == "maxItems" for error in errors)


def test_direction_and_authority_mutations_fail_schema(
    decision_validator: Draft202012Validator,
    eligible: dict,
) -> None:
    for direction_field in (
        "selector_unknown_count",
        "realized_none_count",
        "realized_null_count",
        "realized_unknown_count",
    ):
        payload = copy.deepcopy(eligible)
        payload["direction_counts"][direction_field] = 1
        assert list(decision_validator.iter_errors(payload))
    for boundary in eligible["authority_boundaries"]:
        payload = copy.deepcopy(eligible)
        payload["authority_boundaries"][boundary] = True
        assert list(decision_validator.iter_errors(payload))
    for verification_field in eligible["auto2d_verification"]:
        payload = copy.deepcopy(eligible)
        payload["auto2d_verification"][verification_field] = not (
            payload["auto2d_verification"][verification_field]
        )
        assert list(decision_validator.iter_errors(payload))


def test_provenance_examples_bind_exact_decision_and_trial_limits(
    eligible: dict,
) -> None:
    raw_decision_sha = sha256_bytes(ELIGIBLE_EXAMPLE_PATH.read_bytes())
    selected_by_key = {
        key_tuple(item["key"]): item for item in eligible["selected_entries"]
    }
    for path in PROVENANCE_EXAMPLE_PATHS:
        payload = load_json(path)
        decision = payload["governed_decision"]
        assert decision["sha256"] == raw_decision_sha
        assert decision["decision_id"] == eligible["decision_id"]
        assert decision["policy_envelope_sha256"] == eligible["policy_envelope_sha256"]
        assert decision["independent_verification"]["verdict"] == "PASS"
        assert payload["append_only"] is True
        assert payload["universe_immutable"] is True
        assert payload["no_fallback"] is True
        assert payload["automatic_restart"] is False
        assert payload["trial_bounds"]["max_selected_universe"] == 4
        assert payload["trial_bounds"]["max_simultaneously_open_positions"] == 2
        assert (
            payload["trial_bounds"]["max_automatic_start_decision_age_seconds"] == 300
        )
        assert payload["trial_bounds"]["entry_window_seconds"] == 86400
        assert payload["trial_bounds"]["exit_only_grace_seconds"] == 3600
        assert payload["trial_bounds"]["controller_hard_runtime_seconds"] == 90000
        assert not any(
            value
            for field, value in payload["authority_boundaries"].items()
            if field != "paper_only"
        )
        assert payload["authority_boundaries"]["paper_only"] is True
        if payload["selection_origin"] is not None:
            origin = payload["selection_origin"]
            selected = selected_by_key[key_tuple(origin["key"])]
            assert origin["evidence_class"] == selected["evidence_class"]
            assert origin["lane_rank"] == selected["lane_rank"]
            assert origin["selection_sequence"] == selected["selection_sequence"]


def test_manifest_universe_exactly_matches_governor_selection(eligible: dict) -> None:
    manifest = load_json(PROVENANCE_EXAMPLE_PATHS[0])
    assert manifest["record_type"] == "TRIAL_MANIFEST"
    expected_universe = [
        {field: value for field, value in selected.items() if field != "selection_rule"}
        for selected in eligible["selected_entries"]
    ]
    assert manifest["subject"]["dynamic_universe"] == expected_universe
    bounds = manifest["trial_bounds"]
    assert (
        parse_rfc3339(bounds["controller_started_at"])
        - parse_rfc3339(bounds["decision_evaluated_at"])
    ).total_seconds() <= eligible["policy"]["max_automatic_start_decision_age_seconds"]
    assert (
        parse_rfc3339(bounds["entry_deadline"])
        - parse_rfc3339(bounds["controller_started_at"])
    ).total_seconds() == eligible["policy"]["entry_window_seconds"]
    assert (
        parse_rfc3339(bounds["exit_only_deadline"])
        - parse_rfc3339(bounds["entry_deadline"])
    ).total_seconds() == eligible["policy"]["exit_only_grace_seconds"]
    assert (
        parse_rfc3339(bounds["hard_deadline"])
        - parse_rfc3339(bounds["controller_started_at"])
    ).total_seconds() == eligible["policy"]["controller_hard_runtime_seconds"]


def test_provenance_rejects_v1_or_unverified_decision(
    provenance_validator: Draft202012Validator,
) -> None:
    payload = load_json(PROVENANCE_EXAMPLE_PATHS[0])
    for field, value in (
        ("schema_version", 1),
        ("status", "ELIGIBLE_FOR_OPERATOR_REVIEW"),
    ):
        mutated = copy.deepcopy(payload)
        mutated["governed_decision"][field] = value
        assert list(provenance_validator.iter_errors(mutated))
    mutated = copy.deepcopy(payload)
    mutated["governed_decision"]["independent_verification"][
        "rank_and_transition_recomputed"
    ] = False
    assert list(provenance_validator.iter_errors(mutated))


def test_provenance_rejects_weakened_lifecycle_or_authority(
    provenance_validator: Draft202012Validator,
) -> None:
    payload = load_json(PROVENANCE_EXAMPLE_PATHS[0])
    for field, value in (
        ("max_automatic_start_decision_age_seconds", 301),
        ("entry_window_seconds", 86401),
        ("exit_only_grace_seconds", 3601),
        ("controller_hard_runtime_seconds", 90001),
    ):
        mutated = copy.deepcopy(payload)
        mutated["trial_bounds"][field] = value
        assert list(provenance_validator.iter_errors(mutated))
    mutated = copy.deepcopy(payload)
    mutated["authority_boundaries"]["live_order_authority"] = True
    assert list(provenance_validator.iter_errors(mutated))


def test_v1_and_existing_paper_surfaces_remain_byte_identical() -> None:
    for relative_path, expected_hash in PROTECTED_V1_HASHES.items():
        assert sha256_bytes((REPO_ROOT / relative_path).read_bytes()) == expected_hash
