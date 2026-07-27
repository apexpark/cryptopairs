from __future__ import annotations

import copy
import datetime as dt
import hashlib
import inspect
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools" / "scripts"
FIXTURE_PATH = (
    SCRIPTS_ROOT
    / "tests"
    / "fixtures"
    / "autopilot_dynamic_allowlist_cases.json"
)
DECISION_SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_dynamic_allowlist_decision.schema.json"
)
DECISION_EXAMPLE_PATH = (
    REPO_ROOT
    / "specs"
    / "examples"
    / "autopilot_dynamic_allowlist_decision.example.json"
)
SNAPSHOT_SCHEMA_PATH = (
    REPO_ROOT
    / "specs"
    / "contracts"
    / "autopilot_shadow_allowlist_snapshot.schema.json"
)
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_dynamic_allowlist as scaffold  # noqa: E402


ACTIONABLE_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}
SELECTOR_DIRECTIONS = {None, "LONG_SPREAD", "NONE", "SHORT_SPREAD"}
ADOPTED_SELECTOR_CONFIG = {
    "min_closed_positions": 5,
    "min_avg_net_bps": 0,
    "max_tail_loss_bps": -60,
    "max_avg_exit_lag_seconds": 1800,
    "max_selected": 8,
    "min_score": 0,
}
ADOPTED_GOVERNOR_CONFIG = {
    "transition_posture": "DEMOTION_ONLY",
    "required_comparable_v2_snapshots": 2,
    "min_source_cutoff_separation_seconds": 86400,
    "max_current_source_age_seconds": 1800,
    "max_governed_entries": 4,
    "max_directions_per_pair_variant": 2,
    "max_entries_per_full_instrument": 2,
    "max_changed_entries": 1,
    "change_measure": "BASELINE_PROPOSED_SYMMETRIC_DIFFERENCE",
    "max_churn_ratio": 0.25,
    "churn_denominator": "NON_EMPTY_BASELINE_ENTRY_COUNT",
    "freshness_reference": "CURRENT_SNAPSHOT_SOURCE_CUTOFF_AT",
    "validity_seconds": 86400,
    "validity_reference": "EXPLICIT_EVALUATED_AT",
    "candidate_overflow_behavior": "BLOCK_EMPTY_NO_TRUNCATION",
    "fallback_behavior": "NO_FALLBACK",
}
GATE_NAMES = (
    "provenance",
    "current_snapshot_schema",
    "previous_snapshot_schema",
    "snapshot_hash_distinct",
    "selector_config_match",
    "source_cutoff_order",
    "source_cutoff_separation",
    "current_source_freshness",
    "comparable_selector_history",
    "direction_domain",
    "evidence_segregation",
    "static_baseline",
    "candidate_qualification",
    "maximum_selection",
    "pair_variant_concentration",
    "instrument_concentration",
    "transition_change",
    "transition_churn",
    "expiry",
)
REASON_TO_GATE = {
    "PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2": "previous_snapshot_schema",
    "SELECTOR_CHURN_UNAVAILABLE": "comparable_selector_history",
    "NO_QUALIFYING_ENTRIES": "candidate_qualification",
    "MAX_GOVERNED_ENTRIES_EXCEEDED": "maximum_selection",
    "PAIR_VARIANT_CONCENTRATION_EXCEEDED": "pair_variant_concentration",
    "INSTRUMENT_CONCENTRATION_EXCEEDED": "instrument_concentration",
    "MAX_CHANGED_ENTRIES_EXCEEDED": "transition_change",
    "MAX_CHURN_RATIO_EXCEEDED": "transition_churn",
}


class VectorAuditError(ValueError):
    """A synthetic specification vector violates a fail-closed invariant."""


def parse_json_strict(value: str) -> object:
    return json.loads(
        value,
        parse_constant=lambda constant: (_ for _ in ()).throw(
            VectorAuditError(f"NON_FINITE_JSON:{constant}")
        ),
    )


def parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise VectorAuditError("MALFORMED_TIMESTAMP") from error
    if parsed.tzinfo is None:
        raise VectorAuditError("NAIVE_TIMESTAMP")
    return parsed.astimezone(dt.timezone.utc)


def format_utc(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_bundle() -> dict:
    payload = parse_json_strict(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def case_by_id(bundle: dict, case_id: str) -> dict:
    return next(case for case in bundle["cases"] if case["case_id"] == case_id)


def materialize_raw_content(binding: dict) -> str:
    if "content" in binding:
        return binding["content"]
    template_path = REPO_ROOT / binding["template"]
    payload = parse_json_strict(template_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VectorAuditError("RAW_TEMPLATE_NOT_OBJECT")
    payload.update(copy.deepcopy(binding["top_level_overrides"]))
    for dotted_path in binding["delete_paths"]:
        parts = dotted_path.split(".")
        parent = payload
        for part in parts[:-1]:
            parent = parent[part]
        del parent[parts[-1]]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def raw_file(bundle: dict, name: str) -> tuple[dict, dict]:
    binding = bundle["raw_files"][name]
    content = materialize_raw_content(binding)
    actual_hash = sha256_bytes(content)
    if actual_hash != binding["sha256"]:
        raise VectorAuditError(f"RAW_HASH_MISMATCH:{name}")
    parsed = parse_json_strict(content)
    if not isinstance(parsed, dict):
        raise VectorAuditError(f"RAW_JSON_NOT_OBJECT:{name}")
    return binding, parsed


def exact_key_tuple(bundle: dict, name: str) -> tuple[str, str, str, str]:
    try:
        key = bundle["exact_keys"][name]
    except KeyError as error:
        raise VectorAuditError(f"UNKNOWN_EXACT_KEY:{name}") from error
    if set(key) != {"pair_id", "timeframe", "selected_variant", "direction"}:
        raise VectorAuditError(f"MALFORMED_EXACT_KEY:{name}")
    pair_id = key["pair_id"]
    if (
        not isinstance(pair_id, str)
        or pair_id.count("__") != 1
        or any(not instrument for instrument in pair_id.split("__"))
    ):
        raise VectorAuditError(f"MALFORMED_PAIR_ID:{name}")
    if key["timeframe"] != "1m" or not key["selected_variant"]:
        raise VectorAuditError(f"MALFORMED_EXACT_KEY:{name}")
    if key["direction"] not in ACTIONABLE_DIRECTIONS:
        raise VectorAuditError(f"NON_ACTIONABLE_EXACT_KEY:{name}")
    return (
        pair_id,
        key["timeframe"],
        key["selected_variant"],
        key["direction"],
    )


def require_unique_sorted_names(
    bundle: dict, names: list[str], field: str
) -> list[str]:
    if len(names) != len(set(names)):
        raise VectorAuditError(f"DUPLICATE_EXACT_KEY:{field}")
    expected = sorted(names, key=lambda name: exact_key_tuple(bundle, name))
    if names != expected:
        raise VectorAuditError(f"NONDETERMINISTIC_KEY_ORDER:{field}")
    return names


def concentration_counts(
    bundle: dict, names: list[str]
) -> tuple[Counter[tuple[str, str, str]], Counter[str]]:
    pair_variant: Counter[tuple[str, str, str]] = Counter()
    instrument: Counter[str] = Counter()
    for name in names:
        pair_id, timeframe, variant, _direction = exact_key_tuple(bundle, name)
        pair_variant[(pair_id, timeframe, variant)] += 1
        left, right = pair_id.split("__")
        instrument[left] += 1
        instrument[right] += 1
    return pair_variant, instrument


def direction_counts(case: dict) -> dict[str, int]:
    selector = Counter(case["current_snapshot"]["selector_directions"])
    realized = Counter(case["paper_evidence"]["realized_directions"])
    return {
        "selector_long_spread_count": selector["LONG_SPREAD"],
        "selector_short_spread_count": selector["SHORT_SPREAD"],
        "selector_none_count": selector["NONE"],
        "selector_null_count": selector[None],
        "selector_unknown_count": sum(
            count
            for direction, count in selector.items()
            if direction not in SELECTOR_DIRECTIONS
        ),
        "realized_long_spread_count": realized["LONG_SPREAD"],
        "realized_short_spread_count": realized["SHORT_SPREAD"],
        "realized_none_count": realized["NONE"],
        "realized_null_count": realized[None],
        "realized_unknown_count": sum(
            count
            for direction, count in realized.items()
            if direction not in ACTIONABLE_DIRECTIONS
        ),
    }


def decision_id(
    *,
    current_snapshot_sha256: str,
    previous_snapshot_sha256: str,
    paper_run_config_sha256: str,
    governor_config_sha256: str,
    evaluated_at: str,
) -> str:
    envelope = {
        "current_snapshot_sha256": current_snapshot_sha256,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "paper_run_config_sha256": paper_run_config_sha256,
        "governor_config_sha256": governor_config_sha256,
        "evaluated_at": evaluated_at,
    }
    return hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()


def audit_case(bundle: dict, case: dict) -> dict:
    identity = bundle["canonical_identity"]
    if identity != {
        "exact_key_order": [
            "pair_id",
            "timeframe",
            "selected_variant",
            "direction",
        ],
        "exact_key_sort": "LEXICOGRAPHIC_TUPLE",
        "decision_id_algorithm": "SHA256_MINIFIED_SORTED_UTF8_JSON",
        "decision_id_fields": [
            "current_snapshot_sha256",
            "previous_snapshot_sha256",
            "paper_run_config_sha256",
            "governor_config_sha256",
            "evaluated_at",
        ],
        "decision_id_trailing_newline": False,
        "raw_file_hash_binding": "SHA256_EXACT_BYTES",
    }:
        raise VectorAuditError("CANONICAL_IDENTITY_MISMATCH")
    if bundle["selector_config"] != ADOPTED_SELECTOR_CONFIG:
        raise VectorAuditError("ADOPTED_SELECTOR_CONFIG_MISMATCH")
    if bundle["governor_config"] != ADOPTED_GOVERNOR_CONFIG:
        raise VectorAuditError("ADOPTED_GOVERNOR_CONFIG_MISMATCH")
    selector_config_sha256 = hashlib.sha256(
        canonical_json_bytes(bundle["selector_config"])
    ).hexdigest()

    governor_binding, governor_raw = raw_file(bundle, "governor_config")
    if governor_raw != bundle["governor_config"]:
        raise VectorAuditError("GOVERNOR_CONFIG_RAW_SEMANTIC_MISMATCH")

    current_binding, current_raw = raw_file(
        bundle, case["current_snapshot"]["raw_file"]
    )
    previous_binding, previous_raw = raw_file(
        bundle, case["previous_snapshot"]["raw_file"]
    )
    paper_binding, paper_raw = raw_file(bundle, case["paper_evidence"]["raw_file"])
    if current_binding["sha256"] == previous_binding["sha256"]:
        raise VectorAuditError("SNAPSHOT_HASH_REUSED")

    for name, evidence in (
        ("current_snapshot", case["current_snapshot"]),
        ("previous_snapshot", case["previous_snapshot"]),
        ("paper_evidence", case["paper_evidence"]),
    ):
        if evidence["complete"] is not True:
            raise VectorAuditError(f"INCOMPLETE_EVIDENCE:{name}")
        if evidence["duplicate_identity_count"] != 0:
            raise VectorAuditError(f"DUPLICATE_EVIDENCE:{name}")

    if "realized_entries" in case["current_snapshot"] or "realized_entries" in case[
        "previous_snapshot"
    ]:
        raise VectorAuditError("REALIZED_SELECTOR_EVIDENCE_MIXED")
    if "prominent_entries" in case["paper_evidence"]:
        raise VectorAuditError("SELECTOR_REALIZED_EVIDENCE_MIXED")

    if current_raw["schema_version"] != 2:
        raise VectorAuditError("CURRENT_SNAPSHOT_NOT_SCHEMA_V2")
    if not isinstance(current_raw.get("selector_view"), dict) or not isinstance(
        current_raw.get("churn", {}).get("selector_view"), dict
    ):
        raise VectorAuditError("CURRENT_SELECTOR_VIEW_UNAVAILABLE")

    for snapshot_name, snapshot, raw in (
        ("current_snapshot", case["current_snapshot"], current_raw),
        ("previous_snapshot", case["previous_snapshot"], previous_raw),
    ):
        if snapshot["selector_config"] != bundle["selector_config"]:
            raise VectorAuditError(f"SELECTOR_CONFIG_MISMATCH:{snapshot_name}")
        directions = (
            snapshot["selector_directions"] + snapshot["marginal_directions"]
        )
        unknown = [direction for direction in directions if direction not in SELECTOR_DIRECTIONS]
        if unknown:
            raise VectorAuditError(f"UNKNOWN_SELECTOR_DIRECTION:{unknown[0]}")
        require_unique_sorted_names(
            bundle, snapshot["prominent_entries"], f"{snapshot_name}.prominent_entries"
        )
        if (
            bundle["raw_files"][snapshot["raw_file"]]["selector_config_sha256"]
            != selector_config_sha256
        ):
            raise VectorAuditError("SELECTOR_CONFIG_HASH_MISMATCH")

    counts = direction_counts(case)
    if counts["selector_none_count"] == 0 or counts["selector_null_count"] == 0:
        raise VectorAuditError("NONE_NULL_DISTINCTION_NOT_EXERCISED")
    if counts["selector_unknown_count"] != 0:
        raise VectorAuditError("UNKNOWN_SELECTOR_DIRECTION")
    if any(
        counts[field] != 0
        for field in (
            "realized_none_count",
            "realized_null_count",
            "realized_unknown_count",
        )
    ):
        raise VectorAuditError("UNKNOWN_REALIZED_DIRECTION")

    baseline = require_unique_sorted_names(
        bundle,
        case["paper_evidence"]["static_allowlist_entries"],
        "paper_evidence.static_allowlist_entries",
    )
    realized = require_unique_sorted_names(
        bundle,
        case["paper_evidence"]["realized_entries"],
        "paper_evidence.realized_entries",
    )
    if paper_raw != {
        "mode": "pair_variant_direction",
        "run_id": "synthetic-paper-v1",
        "static_allowlist_entry_count": len(baseline),
    }:
        raise VectorAuditError("PAPER_CONFIG_RAW_SEMANTIC_MISMATCH")

    claimed_proposed = require_unique_sorted_names(
        bundle, case["expected"]["proposed_entries"], "expected.proposed_entries"
    )
    if not set(claimed_proposed).issubset(baseline):
        raise VectorAuditError("ADDITION_FORBIDDEN")
    if (
        case["expected"]["status"] == "GOVERNOR_BLOCKED"
        and claimed_proposed
    ):
        raise VectorAuditError("BLOCKED_DECISION_NOT_EMPTY")

    previous_comparable = (
        previous_raw["schema_version"] == 2
        and isinstance(previous_raw.get("selector_view"), dict)
        and isinstance(previous_raw.get("churn", {}).get("selector_view"), dict)
    )
    current_prominent = set(case["current_snapshot"]["prominent_entries"])
    previous_prominent = set(case["previous_snapshot"]["prominent_entries"])
    qualifying = (
        sorted(
            set(baseline)
            & set(realized)
            & current_prominent
            & previous_prominent,
            key=lambda name: exact_key_tuple(bundle, name),
        )
        if previous_comparable
        else []
    )

    reasons: list[str] = []
    if previous_raw["schema_version"] != 2:
        reasons.append("PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2")
    if not previous_comparable:
        reasons.append("SELECTOR_CHURN_UNAVAILABLE")

    current_cutoff = parse_utc(current_raw["source_cutoff_at"])
    previous_cutoff = parse_utc(previous_raw["source_cutoff_at"])
    evaluated_at = parse_utc(case["evaluated_at"])
    separation = int((current_cutoff - previous_cutoff).total_seconds())
    age = int((evaluated_at - current_cutoff).total_seconds())
    if separation <= 0:
        raise VectorAuditError("SOURCE_CUTOFF_ORDER_INVALID")
    if separation < bundle["governor_config"][
        "min_source_cutoff_separation_seconds"
    ]:
        reasons.append("SOURCE_CUTOFF_SEPARATION_TOO_SHORT")
    if age < 0:
        raise VectorAuditError("CURRENT_SOURCE_FROM_FUTURE")
    if age > bundle["governor_config"]["max_current_source_age_seconds"]:
        reasons.append("CURRENT_SOURCE_STALE")
    if not qualifying:
        reasons.append("NO_QUALIFYING_ENTRIES")

    pair_variant, instrument = concentration_counts(bundle, qualifying)
    if len(qualifying) > bundle["governor_config"]["max_governed_entries"]:
        reasons.append("MAX_GOVERNED_ENTRIES_EXCEEDED")
    if any(
        count
        > bundle["governor_config"]["max_directions_per_pair_variant"]
        for count in pair_variant.values()
    ):
        reasons.append("PAIR_VARIANT_CONCENTRATION_EXCEEDED")
    if any(
        count > bundle["governor_config"]["max_entries_per_full_instrument"]
        for count in instrument.values()
    ):
        reasons.append("INSTRUMENT_CONCENTRATION_EXCEEDED")

    proposed = [] if reasons else qualifying
    changes = len(set(baseline) ^ set(proposed))
    churn = changes / len(baseline) if baseline else None
    if not baseline:
        reasons.append("STATIC_BASELINE_EMPTY")
    if changes > bundle["governor_config"]["max_changed_entries"]:
        reasons.append("MAX_CHANGED_ENTRIES_EXCEEDED")
    if churn is not None and churn > bundle["governor_config"]["max_churn_ratio"]:
        reasons.append("MAX_CHURN_RATIO_EXCEEDED")
    if reasons:
        proposed = []

    additions = sorted(
        set(proposed) - set(baseline),
        key=lambda name: exact_key_tuple(bundle, name),
    )
    if additions:
        raise VectorAuditError("ADDITION_FORBIDDEN")
    removals = sorted(
        set(baseline) - set(proposed),
        key=lambda name: exact_key_tuple(bundle, name),
    )
    retained = sorted(
        set(baseline) & set(proposed),
        key=lambda name: exact_key_tuple(bundle, name),
    )
    status = (
        "GOVERNOR_BLOCKED" if reasons else "ELIGIBLE_FOR_OPERATOR_REVIEW"
    )
    valid_until = format_utc(
        evaluated_at
        + dt.timedelta(seconds=bundle["governor_config"]["validity_seconds"])
    )
    computed_decision_id = decision_id(
        current_snapshot_sha256=current_binding["sha256"],
        previous_snapshot_sha256=previous_binding["sha256"],
        paper_run_config_sha256=paper_binding["sha256"],
        governor_config_sha256=governor_binding["sha256"],
        evaluated_at=case["evaluated_at"],
    )
    result = {
        "status": status,
        "reason_codes": reasons,
        "qualifying_entries": qualifying,
        "proposed_entries": proposed,
        "retained_entries": retained,
        "removals": removals,
        "additions": additions,
        "source_cutoff_separation_seconds": separation,
        "current_source_age_seconds": age,
        "change_count": changes,
        "churn_ratio": churn,
        "valid_until": valid_until,
        "decision_id": computed_decision_id,
        "direction_counts": counts,
        "pair_variant_concentrations": pair_variant,
        "instrument_concentrations": instrument,
        "raw_hashes": {
            "current": current_binding["sha256"],
            "previous": previous_binding["sha256"],
            "paper": paper_binding["sha256"],
            "governor": governor_binding["sha256"],
        },
        "raw_metadata": {
            "current": current_raw,
            "previous": previous_raw,
        },
    }
    for field, expected in case["expected"].items():
        if result[field] != expected:
            raise VectorAuditError(
                f"EXPECTED_{field.upper()}_MISMATCH:"
                f"expected={expected!r}:computed={result[field]!r}:"
                f"reasons={reasons!r}"
            )
    return result


def decision_key(bundle: dict, name: str) -> dict:
    return copy.deepcopy(bundle["exact_keys"][name])


def materialize_decision(bundle: dict, case: dict, result: dict) -> dict:
    payload = json.loads(DECISION_EXAMPLE_PATH.read_text(encoding="utf-8"))
    current_raw = result["raw_metadata"]["current"]
    previous_raw = result["raw_metadata"]["previous"]

    def snapshot_reference(which: str, raw: dict) -> dict:
        raw_name = case[f"{which}_snapshot"]["raw_file"]
        binding = bundle["raw_files"][raw_name]
        selector_view_present = isinstance(raw.get("selector_view"), dict)
        selector_view_churn_available = isinstance(
            raw.get("churn", {}).get("selector_view"), dict
        )
        return {
            "path": f"/synthetic/{raw_name}.json",
            "sha256": binding["sha256"],
            "schema_version": raw["schema_version"],
            "generated_at": raw["generated_at"],
            "source_cutoff_at": raw["source_cutoff_at"],
            "producer_git_sha": binding["producer_git_sha"],
            "selector_config_sha256": binding["selector_config_sha256"],
            "selector_view_present": selector_view_present,
            "selector_view_churn_available": selector_view_churn_available,
        }

    payload["decision_id"] = result["decision_id"]
    payload["status"] = result["status"]
    payload["evaluated_at"] = case["evaluated_at"]
    payload["valid_until"] = result["valid_until"]
    payload["current_snapshot"] = snapshot_reference("current", current_raw)
    payload["previous_snapshot"] = snapshot_reference("previous", previous_raw)
    payload["paper_run_config"] = {
        "path": "/synthetic/paper_run_config.json",
        "sha256": result["raw_hashes"]["paper"],
        "producer_git_sha": "5555555555555555555555555555555555555555",
        "static_allowlist_mode": "pair_variant_direction",
        "static_allowlist_entry_count": len(
            case["paper_evidence"]["static_allowlist_entries"]
        ),
    }
    payload["selector_config"] = copy.deepcopy(bundle["selector_config"])
    payload["governor_config"] = copy.deepcopy(bundle["governor_config"])
    payload["governor_config_source"] = {
        "path": "/synthetic/governor_config.json",
        "sha256": result["raw_hashes"]["governor"],
    }
    for field in (
        "baseline_entries",
        "proposed_entries",
        "additions",
        "removals",
        "retained_entries",
    ):
        source = (
            case["paper_evidence"]["static_allowlist_entries"]
            if field == "baseline_entries"
            else result[field]
        )
        payload[field] = [decision_key(bundle, name) for name in source]
    payload["direction_counts"] = result["direction_counts"]

    blocked_by_gate: dict[str, list[str]] = {name: [] for name in GATE_NAMES}
    for reason in result["reason_codes"]:
        gate = REASON_TO_GATE.get(reason)
        if gate is not None:
            blocked_by_gate[gate].append(reason)
    payload["gate_results"] = {
        gate: {
            "verdict": "BLOCK" if reason_codes else "PASS",
            "reason_codes": reason_codes,
        }
        for gate, reason_codes in blocked_by_gate.items()
    }
    blocked_count = sum(
        result["verdict"] == "BLOCK"
        for result in payload["gate_results"].values()
    )
    payload["gate_summary"] = {
        "pass_count": len(GATE_NAMES) - blocked_count,
        "block_count": blocked_count,
        "total_count": len(GATE_NAMES),
    }
    payload["reason_codes"] = result["reason_codes"]

    pair_variant_rows = [
        {
            "pair_id": pair_id,
            "timeframe": timeframe,
            "selected_variant": variant,
            "direction_count": count,
        }
        for (pair_id, timeframe, variant), count in sorted(
            result["pair_variant_concentrations"].items()
        )
    ]
    instrument_rows = [
        {"instrument_id": instrument_id, "entry_count": count}
        for instrument_id, count in sorted(
            result["instrument_concentrations"].items()
        )
    ]
    payload["calculations"] = {
        "source_cutoff_separation_seconds": result[
            "source_cutoff_separation_seconds"
        ],
        "current_source_age_seconds": result["current_source_age_seconds"],
        "baseline_entry_count": len(payload["baseline_entries"]),
        "qualifying_entry_count": len(result["qualifying_entries"]),
        "proposed_entry_count": len(payload["proposed_entries"]),
        "change_count": result["change_count"],
        "churn_ratio": result["churn_ratio"],
        "pair_variant_concentrations": pair_variant_rows,
        "instrument_concentrations": instrument_rows,
    }
    return payload


def rewrite_raw_json(bundle: dict, raw_name: str, mutator) -> None:
    binding = bundle["raw_files"][raw_name]
    parsed = parse_json_strict(materialize_raw_content(binding))
    assert isinstance(parsed, dict)
    mutator(parsed)
    content = json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n"
    binding["content"] = content
    binding.pop("template", None)
    binding.pop("top_level_overrides", None)
    binding.pop("delete_paths", None)
    binding["sha256"] = sha256_bytes(content)


def append_raw_whitespace_without_rehash(bundle: dict, raw_name: str) -> None:
    binding = bundle["raw_files"][raw_name]
    binding["content"] = materialize_raw_content(binding) + " "
    binding.pop("template", None)
    binding.pop("top_level_overrides", None)
    binding.pop("delete_paths", None)


def test_specification_vectors_are_deterministic_and_schema_valid() -> None:
    bundle = load_bundle()
    validator = Draft202012Validator(
        json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    snapshot_validator = Draft202012Validator(
        json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    for raw_name in (
        "current_snapshot",
        "previous_snapshot_v2",
        "previous_snapshot_v1",
    ):
        _binding, snapshot = raw_file(bundle, raw_name)
        assert list(snapshot_validator.iter_errors(snapshot)) == []
    results = []
    for case in bundle["cases"]:
        result = audit_case(bundle, case)
        results.append(result)
        decision = materialize_decision(bundle, case, result)
        assert list(validator.iter_errors(decision)) == []
        assert decision["authority"] == "advisory_pending_operator_approval"
        assert decision["operator_approval_required"] is True
        assert not any(decision["authority_boundaries"].values())
    assert [result["status"] for result in results] == [
        "ELIGIBLE_FOR_OPERATOR_REVIEW",
        "GOVERNOR_BLOCKED",
    ]


def test_comparable_v2_vector_exercises_all_adopted_boundaries() -> None:
    bundle = load_bundle()
    result = audit_case(bundle, case_by_id(bundle, "comparable_v2_boundary_eligible"))
    assert result["source_cutoff_separation_seconds"] == 86400
    assert result["current_source_age_seconds"] == 1800
    assert len(result["proposed_entries"]) == 3
    assert max(result["pair_variant_concentrations"].values()) == 2
    assert max(result["instrument_concentrations"].values()) == 2
    assert result["change_count"] == 1
    assert result["churn_ratio"] == 0.25
    assert result["direction_counts"]["selector_none_count"] == 2
    assert result["direction_counts"]["selector_null_count"] == 1
    assert result["direction_counts"]["selector_unknown_count"] == 0
    assert result["valid_until"] == "2026-07-28T00:30:00Z"
    assert result["additions"] == []


@pytest.mark.parametrize("payload", ["{", '{"value":NaN}'])
def test_strict_vector_parser_rejects_malformed_or_nonfinite_json(
    payload: str,
) -> None:
    with pytest.raises((json.JSONDecodeError, VectorAuditError)):
        parse_json_strict(payload)


def test_v1_predecessor_production_shape_blocks_with_empty_output() -> None:
    bundle = load_bundle()
    result = audit_case(
        bundle, case_by_id(bundle, "production_shaped_v1_predecessor_blocked")
    )
    assert result["status"] == "GOVERNOR_BLOCKED"
    assert result["proposed_entries"] == []
    assert result["qualifying_entries"] == []
    assert "PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2" in result["reason_codes"]
    assert "SELECTOR_CHURN_UNAVAILABLE" in result["reason_codes"]


def test_decision_id_uses_raw_file_hashes_not_parsed_json_semantics() -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "comparable_v2_boundary_eligible")
    original = audit_case(bundle, case)["decision_id"]
    raw_name = case["current_snapshot"]["raw_file"]
    binding = bundle["raw_files"][raw_name]
    parsed = parse_json_strict(materialize_raw_content(binding))
    binding["content"] = json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    binding.pop("template", None)
    binding.pop("top_level_overrides", None)
    binding.pop("delete_paths", None)
    binding["sha256"] = sha256_bytes(binding["content"])
    changed = decision_id(
        current_snapshot_sha256=binding["sha256"],
        previous_snapshot_sha256=bundle["raw_files"][
            case["previous_snapshot"]["raw_file"]
        ]["sha256"],
        paper_run_config_sha256=bundle["raw_files"]["paper_run_config"]["sha256"],
        governor_config_sha256=bundle["raw_files"]["governor_config"]["sha256"],
        evaluated_at=case["evaluated_at"],
    )
    assert changed != original


def test_repeat_audit_is_byte_deterministic() -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "comparable_v2_boundary_eligible")
    first_result = audit_case(bundle, case)
    first = canonical_json_bytes(
        materialize_decision(bundle, case, first_result)
    )
    second_case = copy.deepcopy(case)
    second_result = audit_case(bundle, second_case)
    second = canonical_json_bytes(
        materialize_decision(bundle, second_case, second_result)
    )
    assert first == second


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda bundle, case: append_raw_whitespace_without_rehash(
                bundle, "current_snapshot"
            ),
            "RAW_HASH_MISMATCH:current_snapshot",
        ),
        (
            lambda bundle, case: case["current_snapshot"]["selector_config"].__setitem__(
                "max_selected", 7
            ),
            "SELECTOR_CONFIG_MISMATCH:current_snapshot",
        ),
        (
            lambda bundle, case: bundle["governor_config"].__setitem__(
                "max_governed_entries", 5
            ),
            "ADOPTED_GOVERNOR_CONFIG_MISMATCH",
        ),
        (
            lambda bundle, case: case["current_snapshot"][
                "selector_directions"
            ].append("SIDEWAYS"),
            "UNKNOWN_SELECTOR_DIRECTION:SIDEWAYS",
        ),
        (
            lambda bundle, case: case["paper_evidence"][
                "realized_directions"
            ].append("NONE"),
            "UNKNOWN_REALIZED_DIRECTION",
        ),
        (
            lambda bundle, case: case["current_snapshot"].__setitem__(
                "complete", False
            ),
            "INCOMPLETE_EVIDENCE:current_snapshot",
        ),
        (
            lambda bundle, case: case["previous_snapshot"].__setitem__(
                "duplicate_identity_count", 1
            ),
            "DUPLICATE_EVIDENCE:previous_snapshot",
        ),
        (
            lambda bundle, case: case["current_snapshot"].__setitem__(
                "realized_entries", ["doge_pepe_long"]
            ),
            "REALIZED_SELECTOR_EVIDENCE_MIXED",
        ),
        (
            lambda bundle, case: case["paper_evidence"].__setitem__(
                "prominent_entries", ["doge_pepe_long"]
            ),
            "SELECTOR_REALIZED_EVIDENCE_MIXED",
        ),
        (
            lambda bundle, case: bundle["exact_keys"]["doge_pepe_long"].__setitem__(
                "direction", "NONE"
            ),
            "NON_ACTIONABLE_EXACT_KEY:doge_pepe_long",
        ),
        (
            lambda bundle, case: case["paper_evidence"][
                "static_allowlist_entries"
            ].append("doge_pepe_long"),
            "DUPLICATE_EXACT_KEY:paper_evidence.static_allowlist_entries",
        ),
        (
            lambda bundle, case: case["expected"].__setitem__(
                "proposed_entries",
                sorted(
                    case["expected"]["proposed_entries"] + ["tao_hype_short"],
                    key=lambda name: exact_key_tuple(bundle, name),
                ),
            ),
            "EXPECTED_PROPOSED_ENTRIES_MISMATCH",
        ),
    ],
)
def test_mutation_checkpoints_fail_closed(mutation, expected_error: str) -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "comparable_v2_boundary_eligible")
    mutation(bundle, case)
    with pytest.raises(VectorAuditError, match=expected_error):
        audit_case(bundle, case)


def test_stale_and_insufficiently_separated_inputs_block() -> None:
    stale_bundle = load_bundle()
    stale_case = case_by_id(stale_bundle, "comparable_v2_boundary_eligible")
    stale_case["evaluated_at"] = "2026-07-27T00:30:01Z"
    with pytest.raises(VectorAuditError, match="CURRENT_SOURCE_STALE"):
        audit_case(stale_bundle, stale_case)

    separation_bundle = load_bundle()
    separation_case = case_by_id(
        separation_bundle, "comparable_v2_boundary_eligible"
    )
    rewrite_raw_json(
        separation_bundle,
        "previous_snapshot_v2",
        lambda raw: raw.__setitem__(
            "source_cutoff_at", "2026-07-26T00:00:01Z"
        ),
    )
    with pytest.raises(
        VectorAuditError, match="SOURCE_CUTOFF_SEPARATION_TOO_SHORT"
    ):
        audit_case(separation_bundle, separation_case)


def test_snapshot_identity_reuse_fails_closed() -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "comparable_v2_boundary_eligible")
    case["previous_snapshot"]["raw_file"] = "current_snapshot"
    with pytest.raises(VectorAuditError, match="SNAPSHOT_HASH_REUSED"):
        audit_case(bundle, case)


def test_maximum_selection_and_instrument_concentration_fail_closed() -> None:
    selection_bundle = load_bundle()
    selection_case = case_by_id(
        selection_bundle, "comparable_v2_boundary_eligible"
    )
    selection_bundle["exact_keys"]["sol_avax_long"] = {
        "pair_id": "PF_SOLUSD__PF_AVAXUSD",
        "timeframe": "1m",
        "selected_variant": "ROBUST_Z",
        "direction": "LONG_SPREAD",
    }
    for field in ("static_allowlist_entries", "realized_entries"):
        selection_case["paper_evidence"][field].append("sol_avax_long")
    for snapshot in ("current_snapshot", "previous_snapshot"):
        selection_case[snapshot]["prominent_entries"].append("sol_avax_long")
    selection_case["current_snapshot"]["prominent_entries"].append(
        "tao_hype_short"
    )
    for field in ("qualifying_entries", "proposed_entries"):
        selection_case["expected"][field].extend(
            ["sol_avax_long", "tao_hype_short"]
        )
    for field in ("static_allowlist_entries", "realized_entries"):
        selection_case["paper_evidence"][field].sort(
            key=lambda name: exact_key_tuple(selection_bundle, name)
        )
    for snapshot in ("current_snapshot", "previous_snapshot"):
        selection_case[snapshot]["prominent_entries"].sort(
            key=lambda name: exact_key_tuple(selection_bundle, name)
        )
    for field in ("qualifying_entries", "proposed_entries"):
        selection_case["expected"][field].sort(
            key=lambda name: exact_key_tuple(selection_bundle, name)
        )
    rewrite_raw_json(
        selection_bundle,
        "paper_run_config",
        lambda raw: raw.__setitem__("static_allowlist_entry_count", 5),
    )
    with pytest.raises(
        VectorAuditError, match="MAX_GOVERNED_ENTRIES_EXCEEDED"
    ):
        audit_case(selection_bundle, selection_case)

    concentration_bundle = load_bundle()
    concentration_case = case_by_id(
        concentration_bundle, "comparable_v2_boundary_eligible"
    )
    concentration_bundle["exact_keys"]["xbt_bnb_long"][
        "pair_id"
    ] = "PF_DOGEUSD__PF_BNBUSD"
    for field in ("static_allowlist_entries", "realized_entries"):
        concentration_case["paper_evidence"][field].sort(
            key=lambda name: exact_key_tuple(concentration_bundle, name)
        )
    for snapshot in ("current_snapshot", "previous_snapshot"):
        concentration_case[snapshot]["prominent_entries"].sort(
            key=lambda name: exact_key_tuple(concentration_bundle, name)
        )
    for field in (
        "qualifying_entries",
        "proposed_entries",
        "retained_entries",
        "removals",
    ):
        concentration_case["expected"][field].sort(
            key=lambda name: exact_key_tuple(concentration_bundle, name)
        )
    with pytest.raises(
        VectorAuditError, match="INSTRUMENT_CONCENTRATION_EXCEEDED"
    ):
        audit_case(concentration_bundle, concentration_case)


def test_one_change_and_baseline_denominator_churn_are_enforced() -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "comparable_v2_boundary_eligible")
    case["current_snapshot"]["prominent_entries"].remove("xbt_bnb_long")
    with pytest.raises(VectorAuditError) as error:
        audit_case(bundle, case)
    assert "MAX_CHANGED_ENTRIES_EXCEEDED" in str(error.value)
    assert "MAX_CHURN_RATIO_EXCEEDED" in str(error.value)


def test_blocked_claim_cannot_contain_proposed_entries() -> None:
    bundle = load_bundle()
    case = case_by_id(bundle, "production_shaped_v1_predecessor_blocked")
    case["expected"]["proposed_entries"] = ["doge_pepe_long"]
    with pytest.raises(VectorAuditError, match="BLOCKED_DECISION_NOT_EMPTY"):
        audit_case(bundle, case)


def write_json_input(path: Path, payload: object) -> str:
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def exact_key_object(key: tuple[str, str, str, str]) -> dict[str, str]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
    }


def production_snapshot(
    *,
    generated_at: str,
    source_cutoff_at: str,
    previous_generated_at: str,
) -> dict:
    snapshot = json.loads(
        (
            REPO_ROOT
            / "specs"
            / "examples"
            / "autopilot_shadow_allowlist_snapshot.example.json"
        ).read_text(encoding="utf-8")
    )
    baseline = (
        "PF_DOGEUSD__PF_PEPEUSD",
        "1m",
        "ROBUST_Z",
        "SHORT_SPREAD",
    )
    baseline_object = exact_key_object(baseline)
    selected = copy.deepcopy(snapshot["selected"][0])
    selected.update(baseline_object)
    selected["decision"] = "SHADOW_SELECTED"
    selected["reason_codes"] = ["PASSED_SHADOW_SELECTOR_GATES"]
    snapshot["selected"] = [selected]
    snapshot["rejected"] = []
    snapshot["quarantined"] = []
    snapshot["summary"].update(
        {
            "eligible_universe_count": 1,
            "selected_count": 1,
            "rejected_count": 0,
            "quarantined_count": 0,
        }
    )

    prominent = copy.deepcopy(
        snapshot["selector_view"]["selector_view_prominent"][0]
    )
    prominent.update(baseline_object)
    none_row = copy.deepcopy(prominent)
    none_row.update(
        {
            "pair_id": "PF_NONEAUSD__PF_NONEBUSD",
            "selected_variant": "NONE_SENTINEL",
            "direction": "NONE",
        }
    )
    null_row = copy.deepcopy(prominent)
    null_row.update(
        {
            "pair_id": "PF_NULLAUSD__PF_NULLBUSD",
            "selected_variant": "NULL_SENTINEL",
            "direction": None,
        }
    )
    snapshot["selector_view"] = {
        "selector_view_prominent": [prominent],
        "selector_view_marginal": [none_row, null_row],
    }
    snapshot["static_allowlist_comparison"] = {
        "static_allowlist_size": 1,
        "shadow_selected_size": 1,
        "overlap_count": 1,
        "static_only_count": 0,
        "shadow_only_count": 0,
        "overlap": [baseline_object],
        "static_only": [],
        "shadow_only": [],
    }
    snapshot["churn"] = {
        "previous_generated_at": previous_generated_at,
        "previous_selected_count": 1,
        "selected_added": [],
        "selected_removed": [],
        "selected_retained_count": 1,
        "churn_count": 0,
        "stability_ratio": 1.0,
        "selector_view": {
            "previous_prominent_count": 1,
            "prominent_added": [],
            "prominent_removed": [],
            "prominent_retained_count": 1,
            "churn_count": 0,
            "stability_ratio": 1.0,
        },
    }
    snapshot["generated_at"] = generated_at
    snapshot["source_cutoff_at"] = source_cutoff_at
    return snapshot


def production_inputs(tmp_path: Path) -> dict[str, object]:
    previous = production_snapshot(
        generated_at="2026-07-26T00:01:00Z",
        source_cutoff_at="2026-07-26T00:00:00Z",
        previous_generated_at="2026-07-25T00:01:00Z",
    )
    current = production_snapshot(
        generated_at="2026-07-27T00:01:00Z",
        source_cutoff_at="2026-07-27T00:00:00Z",
        previous_generated_at="2026-07-26T00:01:00Z",
    )
    baseline = {
        "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
        "selected_variant": "ROBUST_Z",
        "direction": "SHORT_SPREAD",
    }
    paper = {
        "run_id": "synthetic-paper-v1",
        "timeframe": "1m",
        "static_allowlist_mode": "pair_variant_direction",
        "static_allowlist": [baseline],
        "hold_window_bars": 15,
        "max_runtime_seconds": 259200,
        "max_observe_candidate_age_seconds": 900,
    }
    paths = {
        "current": tmp_path / "current.json",
        "previous": tmp_path / "previous.json",
        "paper": tmp_path / "paper.json",
        "governor": tmp_path / "governor.json",
    }
    hashes = {
        "current": write_json_input(paths["current"], current),
        "previous": write_json_input(paths["previous"], previous),
        "paper": write_json_input(paths["paper"], paper),
        "governor": write_json_input(paths["governor"], ADOPTED_GOVERNOR_CONFIG),
    }
    return {
        "paths": paths,
        "hashes": hashes,
        "current": current,
        "previous": previous,
        "paper": paper,
    }


def production_arguments(
    inputs: dict[str, object],
    output_root: Path,
) -> list[str]:
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
        "2026-07-27T00:30:00Z",
        "--output-json",
        str(output_root / scaffold.OUTPUT_JSON_NAME),
        "--output-markdown",
        str(output_root / scaffold.OUTPUT_MARKDOWN_NAME),
    ]


def test_default_scaffold_is_bounded_disabled_and_never_accesses_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "--current-snapshot-json",
        "/must/not/read/current.json",
        "--previous-snapshot-json",
        "/must/not/read/previous.json",
        "--paper-run-config-json",
        "/must/not/read/paper.json",
        "--governor-config-json",
        "/must/not/read/governor.json",
        "--evaluated-at",
        "2026-07-27T00:30:00Z",
        "--previous-decision-json",
        "/must/not/read/decision.json",
        "--output-json",
        "/must/not/write/decision.json",
        "--output-markdown",
        "/must/not/write/decision.md",
    ]
    with (
        mock.patch("builtins.open", side_effect=AssertionError("file access")),
        mock.patch.object(
            Path, "read_text", side_effect=AssertionError("path read")
        ),
        mock.patch.object(
            Path, "write_text", side_effect=AssertionError("path write")
        ),
    ):
        assert scaffold.main(arguments) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        '{"artifact_created":false,"mode":"auto2c_governor_scaffold",'
        '"status":"DISABLED"}\n'
    )
    assert captured.err == ""


def test_enabled_governor_creates_schema_valid_deterministic_advisory_outputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    paths = inputs["paths"]
    assert isinstance(paths, dict)
    input_before = {
        name: (path.read_bytes(), path.stat().st_mtime_ns)
        for name, path in paths.items()
    }
    first_root = tmp_path / "first"
    assert scaffold.main(production_arguments(inputs, first_root)) == 0
    captured = capsys.readouterr()
    diagnostic = json.loads(captured.out)
    assert captured.err == ""
    assert diagnostic["artifact_created"] is True
    assert diagnostic["status"] == "ELIGIBLE_FOR_OPERATOR_REVIEW"
    decision_bytes = (first_root / scaffold.OUTPUT_JSON_NAME).read_bytes()
    markdown_bytes = (first_root / scaffold.OUTPUT_MARKDOWN_NAME).read_bytes()
    decision = json.loads(decision_bytes)
    validator = Draft202012Validator(
        json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    assert list(validator.iter_errors(decision)) == []
    assert decision["proposed_entries"] == decision["baseline_entries"]
    assert decision["additions"] == []
    assert decision["direction_counts"]["selector_none_count"] == 1
    assert decision["direction_counts"]["selector_null_count"] == 1
    assert decision["authority"] == "advisory_pending_operator_approval"
    assert not any(decision["authority_boundaries"].values())
    expected_id = scaffold.decision_id(
        current_snapshot_sha256=str(inputs["hashes"]["current"]),
        previous_snapshot_sha256=str(inputs["hashes"]["previous"]),
        paper_run_config_sha256=str(inputs["hashes"]["paper"]),
        governor_config_sha256=str(inputs["hashes"]["governor"]),
        evaluated_at="2026-07-27T00:30:00Z",
    )
    assert decision["decision_id"] == expected_id

    second_root = tmp_path / "second"
    assert scaffold.main(production_arguments(inputs, second_root)) == 0
    capsys.readouterr()
    assert (second_root / scaffold.OUTPUT_JSON_NAME).read_bytes() == decision_bytes
    assert (
        second_root / scaffold.OUTPUT_MARKDOWN_NAME
    ).read_bytes() == markdown_bytes
    assert {
        name: (path.read_bytes(), path.stat().st_mtime_ns)
        for name, path in paths.items()
    } == input_before


def test_v1_previous_snapshot_produces_schema_valid_blocked_empty_decision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    previous = copy.deepcopy(inputs["previous"])
    current = copy.deepcopy(inputs["current"])
    assert isinstance(previous, dict)
    assert isinstance(current, dict)
    previous["schema_version"] = 1
    previous.pop("selector_view")
    previous.pop("universe")
    previous["churn"].pop("selector_view")
    current["churn"]["selector_view"] = None
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    hashes["previous"] = write_json_input(paths["previous"], previous)
    hashes["current"] = write_json_input(paths["current"], current)
    output_root = tmp_path / "blocked"
    assert scaffold.main(production_arguments(inputs, output_root)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    decision = json.loads((output_root / scaffold.OUTPUT_JSON_NAME).read_bytes())
    assert decision["status"] == "GOVERNOR_BLOCKED"
    assert decision["proposed_entries"] == []
    assert "PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2" in decision["reason_codes"]
    assert "SELECTOR_CHURN_UNAVAILABLE" in decision["reason_codes"]
    validator = Draft202012Validator(
        json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    assert list(validator.iter_errors(decision)) == []


@pytest.mark.parametrize(
    ("input_name", "mutator", "expected_code"),
    [
        (
            "current",
            lambda payload: payload["selector_view"][
                "selector_view_marginal"
            ][0].__setitem__("direction", "SIDEWAYS"),
            "UNKNOWN_SELECTOR_DIRECTION",
        ),
        (
            "paper",
            lambda payload: payload["static_allowlist"][0].__setitem__(
                "direction", "NONE"
            ),
            "PAPER_CONFIG_ALLOWLIST_0_DIRECTION_INVALID",
        ),
    ],
)
def test_unknown_selector_or_nonactionable_realized_direction_creates_no_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    input_name: str,
    mutator,
    expected_code: str,
) -> None:
    inputs = production_inputs(tmp_path)
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    payload = copy.deepcopy(inputs[input_name])
    mutator(payload)
    hashes[input_name] = write_json_input(paths[input_name], payload)
    output_root = tmp_path / "rejected"
    assert scaffold.main(production_arguments(inputs, output_root)) == 2
    captured = capsys.readouterr()
    assert expected_code in captured.err
    assert not output_root.exists()


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda payload: payload["selector_view"][
                "selector_view_prominent"
            ][0]["metrics"].__setitem__("time_in_tradable_now_ratio", 0.99),
            "CURRENT_SELECTOR_VIEW_selector_view_prominent_0_METRICS_RATIO_MISMATCH",
        ),
        (
            lambda payload: payload["selected"][0]["metrics"].__setitem__(
                "avg_realized_net_bps", 99.0
            ),
            "CURRENT_SELECTED_0_METRICS_AVERAGE_NET_MISMATCH",
        ),
    ],
)
def test_internally_inconsistent_snapshot_creates_no_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutator,
    expected_code: str,
) -> None:
    inputs = production_inputs(tmp_path)
    paths = inputs["paths"]
    hashes = inputs["hashes"]
    assert isinstance(paths, dict)
    assert isinstance(hashes, dict)
    current = copy.deepcopy(inputs["current"])
    mutator(current)
    hashes["current"] = write_json_input(paths["current"], current)
    output_root = tmp_path / "inconsistent"
    assert scaffold.main(production_arguments(inputs, output_root)) == 2
    assert expected_code in capsys.readouterr().err
    assert not output_root.exists()


def test_hash_mismatch_and_preoutput_mutation_create_no_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = production_inputs(tmp_path)
    hashes = inputs["hashes"]
    paths = inputs["paths"]
    assert isinstance(hashes, dict)
    assert isinstance(paths, dict)
    hashes["current"] = "0" * 64
    mismatch_root = tmp_path / "hash-mismatch"
    assert scaffold.main(production_arguments(inputs, mismatch_root)) == 2
    assert "CURRENT_SNAPSHOT_HASH_MISMATCH" in capsys.readouterr().err
    assert not mismatch_root.exists()

    hashes["current"] = hashlib.sha256(paths["current"].read_bytes()).hexdigest()
    original_recheck = scaffold.recheck_bound_input
    mutated = False

    def mutate_before_recheck(bound, source: str) -> None:
        nonlocal mutated
        if source == "CURRENT_SNAPSHOT" and not mutated:
            mutated = True
            bound.path.write_bytes(bound.raw_bytes + b" ")
        original_recheck(bound, source)

    monkeypatch.setattr(scaffold, "recheck_bound_input", mutate_before_recheck)
    mutation_root = tmp_path / "mutation"
    assert scaffold.main(production_arguments(inputs, mutation_root)) == 2
    assert "CURRENT_SNAPSHOT_HASH_MISMATCH" in capsys.readouterr().err
    assert not mutation_root.exists()


@pytest.mark.parametrize(
    ("replacement_kind", "expected_code"),
    [
        ("symlink", "CURRENT_SNAPSHOT_SYMLINK"),
        ("directory", "CURRENT_SNAPSHOT_NOT_REGULAR"),
    ],
)
def test_nonregular_or_symlink_input_creates_no_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    replacement_kind: str,
    expected_code: str,
) -> None:
    inputs = production_inputs(tmp_path)
    paths = inputs["paths"]
    assert isinstance(paths, dict)
    original = paths["current"]
    replacement = tmp_path / f"current-{replacement_kind}"
    if replacement_kind == "symlink":
        replacement.symlink_to(original)
    else:
        replacement.mkdir()
    paths["current"] = replacement
    output_root = tmp_path / "rejected-nonregular"
    assert scaffold.main(production_arguments(inputs, output_root)) == 2
    assert expected_code in capsys.readouterr().err
    assert not output_root.exists()


def test_exclusive_output_collision_refuses_without_modifying_existing_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    output_root = tmp_path / "existing"
    output_root.mkdir()
    marker = output_root / "marker"
    marker.write_text("preserve", encoding="utf-8")
    assert scaffold.main(production_arguments(inputs, output_root)) == 2
    assert "OUTPUT_ROOT_EXISTS" in capsys.readouterr().err
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert sorted(path.name for path in output_root.iterdir()) == ["marker"]


def test_concurrent_enabled_invocations_allow_exactly_one_exclusive_output(
    tmp_path: Path,
) -> None:
    inputs = production_inputs(tmp_path)
    output_root = tmp_path / "concurrent"
    command = [
        sys.executable,
        str(SCRIPTS_ROOT / "autopilot_dynamic_allowlist.py"),
        *production_arguments(inputs, output_root),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        completed = list(
            executor.map(
                lambda _index: subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                ),
                range(2),
            )
        )
    assert sorted(process.returncode for process in completed) == [0, 2]
    assert sum("OUTPUT_ROOT_EXISTS" in process.stderr for process in completed) == 1
    assert (output_root / scaffold.OUTPUT_JSON_NAME).is_file()
    assert (output_root / scaffold.OUTPUT_MARKDOWN_NAME).is_file()


def test_output_write_failure_retains_partial_root_and_never_repairs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = production_inputs(tmp_path)
    output_root = tmp_path / "partial"
    original_open = Path.open

    def fail_markdown_open(path: Path, *args, **kwargs):
        if path.name == scaffold.OUTPUT_MARKDOWN_NAME:
            raise OSError("injected write failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_markdown_open)
    assert scaffold.main(production_arguments(inputs, output_root)) == 3
    assert "OUTPUT_WRITE_FAILED_PARTIAL_ROOT_RETAINED" in capsys.readouterr().err
    assert output_root.is_dir()
    assert (output_root / scaffold.OUTPUT_JSON_NAME).is_file()
    assert not (output_root / scaffold.OUTPUT_MARKDOWN_NAME).exists()


def test_previous_decision_is_hash_bound_markdown_comparison_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = production_inputs(tmp_path)
    first_root = tmp_path / "without-comparison"
    assert scaffold.main(production_arguments(inputs, first_root)) == 0
    capsys.readouterr()
    previous_decision = first_root / scaffold.OUTPUT_JSON_NAME
    previous_hash = hashlib.sha256(previous_decision.read_bytes()).hexdigest()

    second_root = tmp_path / "with-comparison"
    arguments = production_arguments(inputs, second_root)
    arguments.extend(
        [
            "--previous-decision-json",
            str(previous_decision),
            "--previous-decision-sha256",
            previous_hash,
        ]
    )
    assert scaffold.main(arguments) == 0
    capsys.readouterr()
    assert (
        second_root / scaffold.OUTPUT_JSON_NAME
    ).read_bytes() == previous_decision.read_bytes()
    markdown = (
        second_root / scaffold.OUTPUT_MARKDOWN_NAME
    ).read_text(encoding="utf-8")
    assert "Non-Authoritative Previous-Decision Comparison" in markdown
    assert "does not affect status, qualification" in markdown


def test_production_governor_has_no_test_or_runtime_actuation_dependencies() -> None:
    source = inspect.getsource(scaffold)
    assert "tools.scripts.tests" not in source
    assert "test_autopilot_dynamic_allowlist" not in source
    for forbidden in (
        "urllib",
        "requests",
        "subprocess",
        "docker",
        "compose",
        "paper_eligibility_authority\": True",
        "live_eligibility_authority\": True",
    ):
        assert forbidden not in source
