import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

import pytest
from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_allowlist_decision.schema.json"
)
EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_decision.example.json"
)
RFC3339_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)


def is_rfc3339_timestamp(value: object) -> bool:
    if not isinstance(value, str) or RFC3339_TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


@pytest.fixture
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    format_checker = FormatChecker()
    format_checker.checks("date-time")(is_rfc3339_timestamp)
    return Draft202012Validator(schema, format_checker=format_checker)


def assert_invalid(validator: Draft202012Validator, payload: dict) -> None:
    assert list(validator.iter_errors(payload))


def eligible_payload(example: dict) -> dict:
    payload = copy.deepcopy(example)
    keys = [
        {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "timeframe": "1m",
            "selected_variant": "ROBUST_Z",
            "direction": "LONG_SPREAD",
        },
        {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "timeframe": "1m",
            "selected_variant": "ROBUST_Z",
            "direction": "SHORT_SPREAD",
        },
        {
            "pair_id": "PF_XBTUSD__PF_BNBUSD",
            "timeframe": "1m",
            "selected_variant": "COINTEGRATION_Z",
            "direction": "LONG_SPREAD",
        },
        {
            "pair_id": "PF_TAOUSD__PF_HYPEUSD",
            "timeframe": "1m",
            "selected_variant": "COINTEGRATION_Z",
            "direction": "SHORT_SPREAD",
        },
    ]
    payload["status"] = "ELIGIBLE_FOR_OPERATOR_REVIEW"
    payload["previous_snapshot"]["schema_version"] = 2
    payload["previous_snapshot"]["selector_view_present"] = True
    payload["previous_snapshot"]["selector_view_churn_available"] = True
    payload["current_snapshot"]["selector_view_churn_available"] = True
    payload["baseline_entries"] = keys
    payload["proposed_entries"] = keys[:3]
    payload["removals"] = keys[3:]
    payload["retained_entries"] = keys[:3]
    payload["reason_codes"] = []
    for result in payload["gate_results"].values():
        result["verdict"] = "PASS"
        result["reason_codes"] = []
    payload["gate_summary"] = {
        "pass_count": 19,
        "block_count": 0,
        "total_count": 19,
    }
    payload["calculations"] = {
        "source_cutoff_separation_seconds": 172800,
        "current_source_age_seconds": 1200,
        "baseline_entry_count": 4,
        "qualifying_entry_count": 3,
        "proposed_entry_count": 3,
        "change_count": 1,
        "churn_ratio": 0.25,
        "pair_variant_concentrations": [
            {
                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                "timeframe": "1m",
                "selected_variant": "ROBUST_Z",
                "direction_count": 2,
            },
            {
                "pair_id": "PF_XBTUSD__PF_BNBUSD",
                "timeframe": "1m",
                "selected_variant": "COINTEGRATION_Z",
                "direction_count": 1,
            },
        ],
        "instrument_concentrations": [
            {"instrument_id": "PF_DOGEUSD", "entry_count": 2},
            {"instrument_id": "PF_PEPEUSD", "entry_count": 2},
            {"instrument_id": "PF_XBTUSD", "entry_count": 1},
            {"instrument_id": "PF_BNBUSD", "entry_count": 1},
        ],
    }
    return payload


def test_schema_and_blocked_example_validate(
    validator: Draft202012Validator, example: dict
) -> None:
    assert list(validator.iter_errors(example)) == []


def test_synthetic_eligible_shape_validates(
    validator: Draft202012Validator, example: dict
) -> None:
    assert list(validator.iter_errors(eligible_payload(example))) == []


def test_format_checker_rejects_invalid_timestamp(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["evaluated_at"] = "not-rfc3339"
    assert_invalid(validator, payload)


@pytest.mark.parametrize("direction", [None, "NONE", "UNKNOWN"])
def test_non_actionable_or_unknown_directions_cannot_enter_exact_keys(
    validator: Draft202012Validator, example: dict, direction: Optional[str]
) -> None:
    payload = copy.deepcopy(example)
    payload["baseline_entries"][0]["direction"] = direction
    assert_invalid(validator, payload)


def test_blocked_decision_requires_empty_proposed_set(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["proposed_entries"] = [copy.deepcopy(payload["baseline_entries"][0])]
    assert_invalid(validator, payload)


def test_blocked_decision_requires_a_reason(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["reason_codes"] = []
    assert_invalid(validator, payload)


def test_demotion_only_forbids_additions(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["additions"] = [copy.deepcopy(payload["baseline_entries"][0])]
    assert_invalid(validator, payload)


def test_none_and_null_counts_remain_distinct(
    validator: Draft202012Validator, example: dict
) -> None:
    assert example["direction_counts"]["selector_none_count"] == 12
    assert example["direction_counts"]["selector_null_count"] == 2
    payload = copy.deepcopy(example)
    del payload["direction_counts"]["selector_null_count"]
    assert_invalid(validator, payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transition_posture", "ALLOW_ADDITIONS"),
        ("max_governed_entries", 5),
        ("max_changed_entries", 2),
        ("change_measure", "RETAINED_ONLY"),
        ("max_churn_ratio", 0.5),
        ("freshness_reference", "GENERATED_AT"),
        ("fallback_behavior", "USE_PREVIOUS"),
    ],
)
def test_ratified_governor_policy_is_contractual(
    validator: Draft202012Validator,
    example: dict,
    field: str,
    value: object,
) -> None:
    payload = copy.deepcopy(example)
    payload["governor_config"][field] = value
    assert_invalid(validator, payload)


def test_governor_config_is_bound_by_exact_source_hash(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    del payload["governor_config_source"]["sha256"]
    assert_invalid(validator, payload)


def test_unknown_direction_evidence_cannot_form_a_decision(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["direction_counts"]["selector_unknown_count"] = 1
    assert_invalid(validator, payload)


def test_eligible_decision_requires_comparable_v2_selector_history(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = eligible_payload(example)
    payload["previous_snapshot"]["schema_version"] = 1
    payload["previous_snapshot"]["selector_view_present"] = False
    payload["previous_snapshot"]["selector_view_churn_available"] = False
    assert_invalid(validator, payload)


def test_schema_v1_reference_cannot_claim_selector_view_evidence(
    validator: Draft202012Validator, example: dict
) -> None:
    payload = copy.deepcopy(example)
    payload["previous_snapshot"]["selector_view_present"] = True
    assert_invalid(validator, payload)


def test_eligible_decision_enforces_freshness_and_transition_caps(
    validator: Draft202012Validator, example: dict
) -> None:
    stale = eligible_payload(example)
    stale["calculations"]["current_source_age_seconds"] = 1801
    assert_invalid(validator, stale)

    excess_change = eligible_payload(example)
    excess_change["calculations"]["change_count"] = 2
    assert_invalid(validator, excess_change)

    excess_churn = eligible_payload(example)
    excess_churn["calculations"]["churn_ratio"] = 0.250001
    assert_invalid(validator, excess_churn)


def test_authority_boundaries_are_false(
    validator: Draft202012Validator, example: dict
) -> None:
    for field in example["authority_boundaries"]:
        payload = copy.deepcopy(example)
        payload["authority_boundaries"][field] = True
        assert_invalid(validator, payload)


def test_exact_hash_operator_approval_binding_is_required(
    validator: Draft202012Validator, example: dict
) -> None:
    for field in example["operator_approval_binding"]:
        payload = copy.deepcopy(example)
        payload["operator_approval_binding"][field] = False
        assert_invalid(validator, payload)
