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


def test_enabled_scaffold_refuses_before_input_or_output_access(
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "--enabled",
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
        assert scaffold.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "GOVERNOR_NOT_IMPLEMENTED\n"


def test_concurrent_enabled_invocations_refuse_without_artifacts(
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "decision.json"
    output_markdown = tmp_path / "decision.md"
    command = [
        sys.executable,
        str(SCRIPTS_ROOT / "autopilot_dynamic_allowlist.py"),
        "--enabled",
        "--current-snapshot-json",
        str(tmp_path / "missing-current.json"),
        "--previous-snapshot-json",
        str(tmp_path / "missing-previous.json"),
        "--paper-run-config-json",
        str(tmp_path / "missing-paper.json"),
        "--governor-config-json",
        str(tmp_path / "missing-governor.json"),
        "--evaluated-at",
        "2026-07-27T00:30:00Z",
        "--output-json",
        str(output_json),
        "--output-markdown",
        str(output_markdown),
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
    assert [process.returncode for process in completed] == [2, 2]
    assert [process.stdout for process in completed] == ["", ""]
    assert [process.stderr for process in completed] == [
        "GOVERNOR_NOT_IMPLEMENTED\n",
        "GOVERNOR_NOT_IMPLEMENTED\n",
    ]
    assert not output_json.exists()
    assert not output_markdown.exists()


def test_production_scaffold_contains_no_governor_or_file_io_surface() -> None:
    source = inspect.getsource(scaffold)
    assert "tools.scripts.tests" not in source
    assert "test_autopilot_dynamic_allowlist" not in source
    for forbidden in (
        "open(",
        ".read_text(",
        ".write_text(",
        "Path(",
        "pathlib",
        "urllib",
        "requests",
        "subprocess",
        "def evaluate_",
        "def rank_",
        "decision_id",
        "sha256",
    ):
        assert forbidden not in source
