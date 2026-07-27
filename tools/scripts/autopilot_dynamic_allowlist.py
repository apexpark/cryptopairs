#!/usr/bin/env python3
"""Build one offline AUTO-2C governed dynamic-allowlist decision.

The tool is disabled by default. Explicit enablement reads only named local
evidence files, validates them fail-closed, and exclusively creates one
advisory JSON decision plus one Markdown report. It cannot alter paper/live
eligibility, runtime configuration, services, orders, or deployments.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional


DISABLED_MODE = "auto2c_governor_scaffold"
DECISION_MODE = "governed_dynamic_allowlist_decision"
DISABLED_DIAGNOSTIC = {
    "artifact_created": False,
    "mode": DISABLED_MODE,
    "status": "DISABLED",
}

ACTIONABLE_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}
SELECTOR_DIRECTIONS = {None, "LONG_SPREAD", "NONE", "SHORT_SPREAD"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)

OUTPUT_JSON_NAME = "autopilot_dynamic_allowlist_decision.json"
OUTPUT_MARKDOWN_NAME = "autopilot_dynamic_allowlist_decision.md"

SELECTOR_CONFIG = {
    "min_closed_positions": 5,
    "min_avg_net_bps": 0,
    "max_tail_loss_bps": -60,
    "max_avg_exit_lag_seconds": 1800,
    "max_selected": 8,
    "min_score": 0,
}
GOVERNOR_CONFIG = {
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
    "SOURCE_CUTOFF_SEPARATION_TOO_SHORT": "source_cutoff_separation",
    "CURRENT_SOURCE_STALE": "current_source_freshness",
    "STATIC_BASELINE_EMPTY": "static_baseline",
    "NO_QUALIFYING_ENTRIES": "candidate_qualification",
    "MAX_GOVERNED_ENTRIES_EXCEEDED": "maximum_selection",
    "PAIR_VARIANT_DIRECTION_LIMIT_EXCEEDED": "pair_variant_concentration",
    "INSTRUMENT_CONCENTRATION_LIMIT_EXCEEDED": "instrument_concentration",
    "MAX_CHANGED_ENTRIES_EXCEEDED": "transition_change",
    "MAX_CHURN_RATIO_EXCEEDED": "transition_churn",
}

ExactKey = tuple[str, str, str, str]
SelectorKey = tuple[str, str, str, Optional[str]]


class GovernorInputError(ValueError):
    """An untrusted or internally inconsistent input must create no artifact."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class BoundInput:
    path: Path
    expected_sha256: str
    sha256: str
    raw_bytes: bytes
    payload: dict[str, Any]
    stat_identity: tuple[int, int, int, int]


@dataclasses.dataclass(frozen=True)
class SnapshotEvidence:
    bound: BoundInput
    schema_version: int
    generated_at: dt.datetime
    source_cutoff_at: dt.datetime
    selected: frozenset[ExactKey]
    rejected: frozenset[ExactKey]
    quarantined: frozenset[ExactKey]
    selector_prominent: frozenset[SelectorKey] | None
    selector_marginal: frozenset[SelectorKey] | None
    selector_churn_available: bool
    direction_counts: Mapping[str, int]


@dataclasses.dataclass(frozen=True)
class DecisionResult:
    decision: dict[str, Any]
    markdown: str


def fail(code: str) -> None:
    raise GovernorInputError(code)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_file_bytes(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def duplicate_rejecting_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        fail("NON_FINITE_JSON_NUMBER")
    return parsed


def parse_json_strict(raw_bytes: bytes, source: str) -> dict[str, Any]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GovernorInputError(f"{source}_NOT_UTF8") from error
    try:
        payload = json.loads(
            text,
            object_pairs_hook=duplicate_rejecting_object,
            parse_float=finite_float,
            parse_constant=lambda _value: fail("NON_FINITE_JSON_NUMBER"),
        )
    except GovernorInputError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise GovernorInputError(f"{source}_MALFORMED_JSON") from error
    if not isinstance(payload, dict):
        fail(f"{source}_NOT_OBJECT")
    return payload


def require_absolute_path(value: str | None, field: str) -> Path:
    if not isinstance(value, str) or not value:
        fail(f"{field}_REQUIRED")
    path = Path(value)
    if not path.is_absolute():
        fail(f"{field}_NOT_ABSOLUTE")
    if Path(os.path.normpath(value)) != path:
        fail(f"{field}_NOT_NORMALIZED")
    return path


def require_sha256(value: str | None, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        fail(f"{field}_INVALID")
    return value


def require_git_sha(value: str | None, field: str) -> str:
    if not isinstance(value, str) or GIT_SHA_RE.fullmatch(value) is None:
        fail(f"{field}_INVALID")
    return value


def file_stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def read_bound_input(
    path_value: str | None,
    expected_sha256: str | None,
    source: str,
) -> BoundInput:
    path = require_absolute_path(path_value, f"{source}_PATH")
    expected = require_sha256(expected_sha256, f"{source}_SHA256")
    try:
        path_lstat = path.lstat()
    except FileNotFoundError as error:
        raise GovernorInputError(f"{source}_MISSING") from error
    if stat.S_ISLNK(path_lstat.st_mode):
        fail(f"{source}_SYMLINK")
    if not stat.S_ISREG(path_lstat.st_mode):
        fail(f"{source}_NOT_REGULAR")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise GovernorInputError(f"{source}_OPEN_FAILED") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            fail(f"{source}_NOT_REGULAR")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if file_stat_identity(before) != file_stat_identity(after):
        fail(f"{source}_CHANGED_DURING_READ")
    if (path_lstat.st_dev, path_lstat.st_ino) != (before.st_dev, before.st_ino):
        fail(f"{source}_PATH_RACE")
    raw_bytes = b"".join(chunks)
    actual = hashlib.sha256(raw_bytes).hexdigest()
    if actual != expected:
        fail(f"{source}_HASH_MISMATCH")
    payload = parse_json_strict(raw_bytes, source)
    return BoundInput(
        path=path,
        expected_sha256=expected,
        sha256=actual,
        raw_bytes=raw_bytes,
        payload=payload,
        stat_identity=file_stat_identity(after),
    )


def recheck_bound_input(bound: BoundInput, source: str) -> None:
    refreshed = read_bound_input(str(bound.path), bound.expected_sha256, source)
    if refreshed.stat_identity != bound.stat_identity:
        fail(f"{source}_CHANGED_BEFORE_OUTPUT")


def require_exact_keys(
    value: object,
    expected: set[str],
    field: str,
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{field}_NOT_OBJECT")
    allowed = expected | (optional or set())
    if set(value) != expected and not (
        expected.issubset(value) and set(value).issubset(allowed)
    ):
        fail(f"{field}_FIELDS_INVALID")
    return value


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{field}_INVALID")
    return value


def require_integer(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(f"{field}_INVALID")
    return value


def require_number(
    value: object,
    field: str,
    *,
    nullable: bool = False,
) -> float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{field}_INVALID")
    parsed = float(value)
    if not math.isfinite(parsed):
        fail(f"{field}_NON_FINITE")
    return parsed


def parse_timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or RFC3339_RE.fullmatch(value) is None:
        fail(f"{field}_INVALID")
    try:
        parsed = dt.datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00")
        )
    except ValueError as error:
        raise GovernorInputError(f"{field}_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{field}_INVALID")
    return parsed.astimezone(dt.timezone.utc)


def format_timestamp(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def validate_pair_id(value: object, field: str) -> str:
    pair_id = require_string(value, field)
    if pair_id.count("__") != 1:
        fail(f"{field}_INVALID")
    left, right = pair_id.split("__")
    if not left or not right or any(char.isspace() for char in pair_id):
        fail(f"{field}_INVALID")
    return pair_id


def exact_key_from_object(value: object, field: str) -> ExactKey:
    row = require_exact_keys(
        value,
        {"pair_id", "timeframe", "selected_variant", "direction"},
        field,
    )
    pair_id = validate_pair_id(row["pair_id"], f"{field}_PAIR_ID")
    if row["timeframe"] != "1m":
        fail(f"{field}_TIMEFRAME_INVALID")
    variant = require_string(row["selected_variant"], f"{field}_VARIANT")
    direction = row["direction"]
    if direction not in ACTIONABLE_DIRECTIONS:
        fail(f"{field}_DIRECTION_INVALID")
    return (pair_id, "1m", variant, str(direction))


def selector_key_from_row(value: object, field: str) -> SelectorKey:
    row = require_exact_keys(
        value,
        {
            "pair_id",
            "timeframe",
            "selected_variant",
            "direction",
            "evidence_kind",
            "metrics",
        },
        field,
    )
    pair_id = validate_pair_id(row["pair_id"], f"{field}_PAIR_ID")
    if row["timeframe"] != "1m" or row["evidence_kind"] != "selector_view":
        fail(f"{field}_IDENTITY_INVALID")
    variant = require_string(row["selected_variant"], f"{field}_VARIANT")
    direction = row["direction"]
    if direction not in SELECTOR_DIRECTIONS:
        fail("UNKNOWN_SELECTOR_DIRECTION")
    validate_selector_metrics(row["metrics"], f"{field}_METRICS")
    return (pair_id, "1m", variant, direction)


def key_object(key: ExactKey) -> dict[str, str]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
    }


def selector_key_sort(key: SelectorKey) -> tuple[str, str, str, str]:
    return (key[0], key[1], key[2], "" if key[3] is None else key[3])


def exact_key_set(
    values: object,
    field: str,
    *,
    allow_empty: bool = True,
) -> frozenset[ExactKey]:
    if not isinstance(values, list) or (not allow_empty and not values):
        fail(f"{field}_INVALID")
    keys = [exact_key_from_object(value, f"{field}_{index}") for index, value in enumerate(values)]
    if len(keys) != len(set(keys)):
        fail(f"{field}_DUPLICATE")
    return frozenset(keys)


def validate_metrics(value: object, field: str) -> None:
    row = require_exact_keys(
        value,
        {
            "closed_positions",
            "profitable_closed_positions",
            "losing_closed_positions",
            "win_rate",
            "sum_realized_net_bps",
            "avg_realized_net_bps",
            "max_loss_bps",
            "avg_exit_lag_seconds",
            "max_exit_lag_seconds",
            "first_entry_at",
            "last_exit_at",
        },
        field,
    )
    closed = require_integer(row["closed_positions"], f"{field}_CLOSED", 1)
    profitable = require_integer(row["profitable_closed_positions"], f"{field}_PROFITABLE")
    losing = require_integer(row["losing_closed_positions"], f"{field}_LOSING")
    if profitable + losing != closed:
        fail(f"{field}_POSITION_COUNTS_MISMATCH")
    win_rate = require_number(row["win_rate"], f"{field}_WIN_RATE")
    assert win_rate is not None
    if win_rate < 0 or win_rate > 1:
        fail(f"{field}_WIN_RATE_INVALID")
    if not math.isclose(
        win_rate,
        profitable / closed,
        abs_tol=0.0001,
    ):
        fail(f"{field}_WIN_RATE_MISMATCH")
    for name in ("sum_realized_net_bps", "avg_realized_net_bps", "max_loss_bps"):
        require_number(row[name], f"{field}_{name.upper()}")
    if not math.isclose(
        float(row["avg_realized_net_bps"]),
        float(row["sum_realized_net_bps"]) / closed,
        abs_tol=0.0001,
    ):
        fail(f"{field}_AVERAGE_NET_MISMATCH")
    require_number(row["avg_exit_lag_seconds"], f"{field}_AVG_EXIT_LAG", nullable=True)
    require_number(row["max_exit_lag_seconds"], f"{field}_MAX_EXIT_LAG", nullable=True)
    first = parse_timestamp(row["first_entry_at"], f"{field}_FIRST_ENTRY")
    last = parse_timestamp(row["last_exit_at"], f"{field}_LAST_EXIT")
    if first > last:
        fail(f"{field}_TIME_ORDER_INVALID")


def validate_score_components(value: object, field: str) -> None:
    row = require_exact_keys(
        value,
        {
            "avg_net_bps",
            "win_rate_bonus",
            "sample_size_bonus",
            "tail_loss_penalty",
            "exit_lag_penalty",
            "total_score",
        },
        field,
    )
    for name, number in row.items():
        require_number(number, f"{field}_{name.upper()}")
    component_sum = sum(
        float(row[name])
        for name in (
            "avg_net_bps",
            "win_rate_bonus",
            "sample_size_bonus",
            "tail_loss_penalty",
            "exit_lag_penalty",
        )
    )
    if not math.isclose(
        float(row["total_score"]),
        component_sum,
        abs_tol=0.001,
    ):
        fail(f"{field}_TOTAL_MISMATCH")


def candidate_key(value: object, field: str, expected_decision: str) -> ExactKey:
    row = require_exact_keys(
        value,
        {
            "pair_id",
            "timeframe",
            "selected_variant",
            "direction",
            "decision",
            "reason_codes",
            "metrics",
            "score_components",
        },
        field,
    )
    key = exact_key_from_object(
        {
            "pair_id": row["pair_id"],
            "timeframe": row["timeframe"],
            "selected_variant": row["selected_variant"],
            "direction": row["direction"],
        },
        field,
    )
    if row["decision"] != expected_decision:
        fail(f"{field}_DECISION_MISMATCH")
    reasons = row["reason_codes"]
    if (
        not isinstance(reasons, list)
        or not reasons
        or any(not isinstance(reason, str) or not reason for reason in reasons)
    ):
        fail(f"{field}_REASONS_INVALID")
    validate_metrics(row["metrics"], f"{field}_METRICS")
    validate_score_components(row["score_components"], f"{field}_SCORE")
    return key


def candidate_set(
    values: object,
    field: str,
    expected_decision: str,
) -> frozenset[ExactKey]:
    if not isinstance(values, list):
        fail(f"{field}_NOT_ARRAY")
    keys = [
        candidate_key(row, f"{field}_{index}", expected_decision)
        for index, row in enumerate(values)
    ]
    if len(keys) != len(set(keys)):
        fail(f"{field}_DUPLICATE")
    return frozenset(keys)


def validate_selector_summary(value: object, field: str) -> None:
    if value is None:
        return
    row = require_exact_keys(value, {"min", "max", "mean"}, field)
    numbers = [
        require_number(row[name], f"{field}_{name.upper()}", nullable=True)
        for name in ("min", "mean", "max")
    ]
    present = [number for number in numbers if number is not None]
    if present and len(present) != 3:
        fail(f"{field}_PARTIAL")
    if len(present) == 3 and not (present[0] <= present[1] <= present[2]):
        fail(f"{field}_ORDER_INVALID")


def validate_selector_metrics(value: object, field: str) -> None:
    row = require_exact_keys(
        value,
        {
            "rows_observed",
            "time_in_tradable_now_ratio",
            "bucket_counts",
            "top_gate_failure_reasons",
        },
        field,
        optional={"score_z_summary", "stated_net_edge_bps_summary"},
    )
    rows_observed = require_integer(row["rows_observed"], f"{field}_ROWS")
    ratio = require_number(row["time_in_tradable_now_ratio"], f"{field}_RATIO")
    assert ratio is not None
    if ratio < 0 or ratio > 1:
        fail(f"{field}_RATIO_INVALID")
    counts = require_exact_keys(
        row["bucket_counts"],
        {"TRADE_NOW", "WATCHLIST", "EXCLUDED"},
        f"{field}_BUCKETS",
    )
    bucket_counts = {
        name: require_integer(counts[name], f"{field}_{name}")
        for name in ("TRADE_NOW", "WATCHLIST", "EXCLUDED")
    }
    if sum(bucket_counts.values()) != rows_observed:
        fail(f"{field}_ROW_COUNT_MISMATCH")
    expected_ratio = (
        bucket_counts["TRADE_NOW"] / rows_observed
        if rows_observed
        else 0.0
    )
    if not math.isclose(ratio, expected_ratio, abs_tol=0.0005):
        fail(f"{field}_RATIO_MISMATCH")
    reasons = row["top_gate_failure_reasons"]
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) for reason in reasons
    ):
        fail(f"{field}_REASONS_INVALID")
    for optional in ("score_z_summary", "stated_net_edge_bps_summary"):
        if optional in row:
            validate_selector_summary(row[optional], f"{field}_{optional.upper()}")


def validate_selector_view(
    value: object,
    field: str,
) -> tuple[frozenset[SelectorKey], frozenset[SelectorKey]]:
    row = require_exact_keys(
        value,
        {"selector_view_prominent", "selector_view_marginal"},
        field,
    )
    groups: dict[str, frozenset[SelectorKey]] = {}
    for name in ("selector_view_prominent", "selector_view_marginal"):
        values = row[name]
        if not isinstance(values, list):
            fail(f"{field}_{name.upper()}_NOT_ARRAY")
        keys = [
            selector_key_from_row(item, f"{field}_{name}_{index}")
            for index, item in enumerate(values)
        ]
        if len(keys) != len(set(keys)):
            fail(f"{field}_{name.upper()}_DUPLICATE")
        groups[name] = frozenset(keys)
    prominent = groups["selector_view_prominent"]
    marginal = groups["selector_view_marginal"]
    if prominent & marginal:
        fail(f"{field}_CLASSIFICATION_OVERLAP")
    return prominent, marginal


def validate_universe(value: object, field: str) -> None:
    row = require_exact_keys(
        value,
        {
            "bucket_universe_counts",
            "paper_evidenced_count",
            "selector_view_only",
            "static_allowlist_overlap_count",
        },
        field,
    )
    counts = require_exact_keys(
        row["bucket_universe_counts"],
        {"TRADE_NOW", "WATCHLIST", "EXCLUDED"},
        f"{field}_BUCKETS",
    )
    for name, count in counts.items():
        require_integer(count, f"{field}_{name}")
    require_integer(row["paper_evidenced_count"], f"{field}_PAPER_EVIDENCED")
    require_integer(
        row["static_allowlist_overlap_count"],
        f"{field}_STATIC_OVERLAP",
    )
    values = row["selector_view_only"]
    if not isinstance(values, list):
        fail(f"{field}_SELECTOR_ONLY_NOT_ARRAY")
    seen: set[SelectorKey] = set()
    for index, value in enumerate(values):
        item = require_exact_keys(
            value,
            {"pair_id", "timeframe", "selected_variant"},
            f"{field}_SELECTOR_ONLY_{index}",
            optional={"direction"},
        )
        direction = item.get("direction")
        if direction not in SELECTOR_DIRECTIONS:
            fail("UNKNOWN_SELECTOR_DIRECTION")
        key: SelectorKey = (
            validate_pair_id(item["pair_id"], f"{field}_PAIR_ID"),
            require_string(item["timeframe"], f"{field}_TIMEFRAME"),
            require_string(item["selected_variant"], f"{field}_VARIANT"),
            direction,
        )
        if key[1] != "1m" or key in seen:
            fail(f"{field}_SELECTOR_ONLY_INVALID")
        seen.add(key)


def validate_summary(
    value: object,
    selected: frozenset[ExactKey],
    rejected: frozenset[ExactKey],
    quarantined: frozenset[ExactKey],
    field: str,
) -> None:
    row = require_exact_keys(
        value,
        {
            "eligible_universe_count",
            "selected_count",
            "rejected_count",
            "quarantined_count",
            "source_event_count",
            "events_dropped_post_cutoff",
            "trade_rows_skipped_non_timeframe",
            "trade_rows_skipped_incomplete",
            "trade_rows_deduplicated",
            "position_rows_open_excluded",
        },
        field,
    )
    counts = {name: require_integer(number, f"{field}_{name.upper()}") for name, number in row.items()}
    expected = {
        "selected_count": len(selected),
        "rejected_count": len(rejected),
        "quarantined_count": len(quarantined),
        "eligible_universe_count": len(selected | rejected | quarantined),
    }
    if any(counts[name] != number for name, number in expected.items()):
        fail(f"{field}_COUNT_MISMATCH")


def validate_methodology(value: object, field: str) -> None:
    row = require_exact_keys(
        value,
        {
            "selection_boundary",
            "lookahead_policy",
            "scoring_definition",
            "execution_caveat",
        },
        field,
    )
    for name, text in row.items():
        require_string(text, f"{field}_{name.upper()}")


def validate_static_comparison_shape(
    value: object,
    field: str,
) -> tuple[frozenset[ExactKey], frozenset[ExactKey], frozenset[ExactKey]]:
    row = require_exact_keys(
        value,
        {
            "static_allowlist_size",
            "shadow_selected_size",
            "overlap_count",
            "static_only_count",
            "shadow_only_count",
            "overlap",
            "static_only",
            "shadow_only",
        },
        field,
    )
    overlap = exact_key_set(row["overlap"], f"{field}_OVERLAP")
    static_only = exact_key_set(row["static_only"], f"{field}_STATIC_ONLY")
    shadow_only = exact_key_set(row["shadow_only"], f"{field}_SHADOW_ONLY")
    if overlap & static_only or overlap & shadow_only or static_only & shadow_only:
        fail(f"{field}_SET_OVERLAP")
    expected = {
        "overlap_count": len(overlap),
        "static_only_count": len(static_only),
        "shadow_only_count": len(shadow_only),
        "static_allowlist_size": len(overlap | static_only),
        "shadow_selected_size": len(overlap | shadow_only),
    }
    for name, number in expected.items():
        if require_integer(row[name], f"{field}_{name.upper()}") != number:
            fail(f"{field}_COUNT_MISMATCH")
    return overlap, static_only, shadow_only


def validate_key_array_with_direction(
    value: object,
    field: str,
    *,
    selector: bool,
) -> frozenset[ExactKey] | frozenset[SelectorKey]:
    if not isinstance(value, list):
        fail(f"{field}_NOT_ARRAY")
    if selector:
        keys: list[SelectorKey] = []
        for index, item in enumerate(value):
            row = require_exact_keys(
                item,
                {"pair_id", "timeframe", "selected_variant"},
                f"{field}_{index}",
                optional={"direction"},
            )
            direction = row.get("direction")
            if direction not in SELECTOR_DIRECTIONS:
                fail("UNKNOWN_SELECTOR_DIRECTION")
            key: SelectorKey = (
                validate_pair_id(row["pair_id"], f"{field}_PAIR_ID"),
                require_string(row["timeframe"], f"{field}_TIMEFRAME"),
                require_string(row["selected_variant"], f"{field}_VARIANT"),
                direction,
            )
            if key[1] != "1m":
                fail(f"{field}_TIMEFRAME_INVALID")
            keys.append(key)
        if len(keys) != len(set(keys)):
            fail(f"{field}_DUPLICATE")
        return frozenset(keys)
    return exact_key_set(value, field)


def validate_churn_shape(value: object, field: str) -> bool:
    if value is None:
        return False
    row = require_exact_keys(
        value,
        {
            "previous_generated_at",
            "previous_selected_count",
            "selected_added",
            "selected_removed",
            "selected_retained_count",
            "churn_count",
            "stability_ratio",
        },
        field,
        optional={"selector_view"},
    )
    if row["previous_generated_at"] is not None:
        parse_timestamp(row["previous_generated_at"], f"{field}_PREVIOUS_GENERATED")
    previous_count = require_integer(
        row["previous_selected_count"],
        f"{field}_PREVIOUS_COUNT",
    )
    added = exact_key_set(row["selected_added"], f"{field}_ADDED")
    removed = exact_key_set(row["selected_removed"], f"{field}_REMOVED")
    retained = require_integer(row["selected_retained_count"], f"{field}_RETAINED")
    churn_count = require_integer(row["churn_count"], f"{field}_COUNT")
    stability = require_number(row["stability_ratio"], f"{field}_STABILITY")
    assert stability is not None
    if (
        churn_count != len(added) + len(removed)
        or retained + len(removed) != previous_count
    ):
        fail(f"{field}_COUNT_MISMATCH")
    expected_stability = round(retained / max(1, previous_count), 6)
    if not math.isclose(stability, expected_stability, abs_tol=1e-6):
        fail(f"{field}_STABILITY_MISMATCH")
    selector = row.get("selector_view")
    if selector is None:
        return False
    selector_row = require_exact_keys(
        selector,
        {
            "previous_prominent_count",
            "prominent_added",
            "prominent_removed",
            "prominent_retained_count",
            "churn_count",
            "stability_ratio",
        },
        f"{field}_SELECTOR",
    )
    selector_previous = require_integer(
        selector_row["previous_prominent_count"],
        f"{field}_SELECTOR_PREVIOUS",
    )
    selector_added = validate_key_array_with_direction(
        selector_row["prominent_added"],
        f"{field}_SELECTOR_ADDED",
        selector=True,
    )
    selector_removed = validate_key_array_with_direction(
        selector_row["prominent_removed"],
        f"{field}_SELECTOR_REMOVED",
        selector=True,
    )
    selector_retained = require_integer(
        selector_row["prominent_retained_count"],
        f"{field}_SELECTOR_RETAINED",
    )
    selector_churn = require_integer(
        selector_row["churn_count"],
        f"{field}_SELECTOR_COUNT",
    )
    selector_stability = require_number(
        selector_row["stability_ratio"],
        f"{field}_SELECTOR_STABILITY",
    )
    assert selector_stability is not None
    if (
        selector_churn != len(selector_added) + len(selector_removed)
        or selector_retained + len(selector_removed) != selector_previous
        or not math.isclose(
            selector_stability,
            round(selector_retained / max(1, selector_previous), 6),
            abs_tol=1e-6,
        )
    ):
        fail(f"{field}_SELECTOR_COUNT_MISMATCH")
    return True


def validate_snapshot(bound: BoundInput, role: str) -> SnapshotEvidence:
    payload = bound.payload
    required = {
        "schema_version",
        "mode",
        "generated_at",
        "source_cutoff_at",
        "selector_config",
        "summary",
        "selected",
        "rejected",
        "quarantined",
        "static_allowlist_comparison",
        "methodology",
        "churn",
    }
    row = require_exact_keys(
        payload,
        required,
        f"{role}_SNAPSHOT",
        optional={"selector_view", "universe"},
    )
    schema_version = require_integer(
        row["schema_version"],
        f"{role}_SCHEMA_VERSION",
        1,
    )
    if schema_version not in {1, 2}:
        fail(f"{role}_SCHEMA_VERSION_INVALID")
    if role == "CURRENT" and schema_version != 2:
        fail("CURRENT_SNAPSHOT_NOT_SCHEMA_V2")
    if row["mode"] != "shadow_dynamic_allowlist_snapshot":
        fail(f"{role}_MODE_INVALID")
    generated_at = parse_timestamp(row["generated_at"], f"{role}_GENERATED_AT")
    source_cutoff = parse_timestamp(
        row["source_cutoff_at"],
        f"{role}_SOURCE_CUTOFF_AT",
    )
    if generated_at < source_cutoff:
        fail(f"{role}_GENERATED_BEFORE_CUTOFF")
    if row["selector_config"] != SELECTOR_CONFIG:
        fail(f"{role}_SELECTOR_CONFIG_MISMATCH")

    selected = candidate_set(row["selected"], f"{role}_SELECTED", "SHADOW_SELECTED")
    rejected = candidate_set(row["rejected"], f"{role}_REJECTED", "SHADOW_REJECTED")
    quarantined = candidate_set(
        row["quarantined"],
        f"{role}_QUARANTINED",
        "SHADOW_QUARANTINED",
    )
    if selected & rejected or selected & quarantined or rejected & quarantined:
        fail(f"{role}_REALIZED_SET_OVERLAP")
    validate_summary(row["summary"], selected, rejected, quarantined, f"{role}_SUMMARY")
    validate_methodology(row["methodology"], f"{role}_METHODOLOGY")
    validate_static_comparison_shape(
        row["static_allowlist_comparison"],
        f"{role}_STATIC_COMPARISON",
    )
    selector_churn_available = validate_churn_shape(row["churn"], f"{role}_CHURN")

    selector_prominent: frozenset[SelectorKey] | None = None
    selector_marginal: frozenset[SelectorKey] | None = None
    selector_view = row.get("selector_view")
    universe = row.get("universe")
    if schema_version == 1:
        churn = row["churn"]
        if (
            selector_view is not None
            or universe is not None
            or (isinstance(churn, dict) and "selector_view" in churn)
        ):
            fail(f"{role}_SCHEMA_V1_SELECTOR_EVIDENCE")
    elif selector_view is None or universe is None:
        if selector_view is not None or universe is not None:
            fail(f"{role}_PARTIAL_SELECTOR_EVIDENCE")
    else:
        selector_prominent, selector_marginal = validate_selector_view(
            selector_view,
            f"{role}_SELECTOR_VIEW",
        )
        validate_universe(universe, f"{role}_UNIVERSE")

    selector_values = (
        (selector_prominent or frozenset()) | (selector_marginal or frozenset())
    )
    selector_counts = Counter(key[3] for key in selector_values)
    realized_counts = Counter(
        key[3] for key in selected | rejected | quarantined
    )
    direction_counts = {
        "selector_long_spread_count": selector_counts["LONG_SPREAD"],
        "selector_short_spread_count": selector_counts["SHORT_SPREAD"],
        "selector_none_count": selector_counts["NONE"],
        "selector_null_count": selector_counts[None],
        "selector_unknown_count": 0,
        "realized_long_spread_count": realized_counts["LONG_SPREAD"],
        "realized_short_spread_count": realized_counts["SHORT_SPREAD"],
        "realized_none_count": 0,
        "realized_null_count": 0,
        "realized_unknown_count": 0,
    }
    return SnapshotEvidence(
        bound=bound,
        schema_version=schema_version,
        generated_at=generated_at,
        source_cutoff_at=source_cutoff,
        selected=selected,
        rejected=rejected,
        quarantined=quarantined,
        selector_prominent=selector_prominent,
        selector_marginal=selector_marginal,
        selector_churn_available=selector_churn_available,
        direction_counts=direction_counts,
    )


def validate_paper_config(bound: BoundInput) -> frozenset[ExactKey]:
    row = require_exact_keys(
        bound.payload,
        {
            "run_id",
            "timeframe",
            "static_allowlist_mode",
            "static_allowlist",
            "hold_window_bars",
            "max_runtime_seconds",
            "max_observe_candidate_age_seconds",
        },
        "PAPER_CONFIG",
    )
    require_string(row["run_id"], "PAPER_CONFIG_RUN_ID")
    if row["timeframe"] != "1m":
        fail("PAPER_CONFIG_TIMEFRAME_INVALID")
    if row["static_allowlist_mode"] != "pair_variant_direction":
        fail("PAPER_CONFIG_NOT_DIRECTION_LEVEL")
    require_integer(row["hold_window_bars"], "PAPER_CONFIG_HOLD_WINDOW", 1)
    require_integer(row["max_runtime_seconds"], "PAPER_CONFIG_MAX_RUNTIME", 1)
    require_integer(
        row["max_observe_candidate_age_seconds"],
        "PAPER_CONFIG_MAX_CANDIDATE_AGE",
        1,
    )
    values = row["static_allowlist"]
    if not isinstance(values, list) or not values:
        fail("STATIC_BASELINE_EMPTY")
    entries: list[ExactKey] = []
    for index, value in enumerate(values):
        item = require_exact_keys(
            value,
            {"pair_id", "selected_variant", "direction"},
            f"PAPER_CONFIG_ALLOWLIST_{index}",
        )
        entries.append(
            exact_key_from_object(
                {
                    "pair_id": item["pair_id"],
                    "timeframe": "1m",
                    "selected_variant": item["selected_variant"],
                    "direction": item["direction"],
                },
                f"PAPER_CONFIG_ALLOWLIST_{index}",
            )
        )
    if len(entries) != len(set(entries)):
        fail("PAPER_CONFIG_ALLOWLIST_DUPLICATE")
    return frozenset(entries)


def validate_governor_config(bound: BoundInput) -> None:
    if bound.payload != GOVERNOR_CONFIG:
        fail("GOVERNOR_CONFIG_MISMATCH")


def validate_static_comparison(
    snapshot: SnapshotEvidence,
    baseline: frozenset[ExactKey],
    role: str,
) -> None:
    overlap, static_only, shadow_only = validate_static_comparison_shape(
        snapshot.bound.payload["static_allowlist_comparison"],
        f"{role}_STATIC_COMPARISON",
    )
    if (
        overlap != baseline & snapshot.selected
        or static_only != baseline - snapshot.selected
        or shadow_only != snapshot.selected - baseline
    ):
        fail(f"{role}_STATIC_COMPARISON_MISMATCH")


def validate_current_churn(
    current: SnapshotEvidence,
    previous: SnapshotEvidence,
) -> None:
    churn = current.bound.payload["churn"]
    if churn is None:
        return
    if churn["previous_generated_at"] != previous.bound.payload["generated_at"]:
        fail("CURRENT_CHURN_PREVIOUS_IDENTITY_MISMATCH")
    expected_added = current.selected - previous.selected
    expected_removed = previous.selected - current.selected
    expected_retained = current.selected & previous.selected
    if (
        exact_key_set(churn["selected_added"], "CURRENT_CHURN_ADDED")
        != expected_added
        or exact_key_set(churn["selected_removed"], "CURRENT_CHURN_REMOVED")
        != expected_removed
        or churn["previous_selected_count"] != len(previous.selected)
        or churn["selected_retained_count"] != len(expected_retained)
    ):
        fail("CURRENT_CHURN_REALIZED_MISMATCH")
    selector_churn = churn.get("selector_view")
    if current.selector_prominent is None or previous.selector_prominent is None:
        if selector_churn is not None:
            fail("CURRENT_CHURN_SELECTOR_UNEXPECTED")
        return
    if selector_churn is None:
        return
    expected_selector_added = (
        current.selector_prominent - previous.selector_prominent
    )
    expected_selector_removed = (
        previous.selector_prominent - current.selector_prominent
    )
    expected_selector_retained = (
        current.selector_prominent & previous.selector_prominent
    )
    if (
        validate_key_array_with_direction(
            selector_churn["prominent_added"],
            "CURRENT_CHURN_SELECTOR_ADDED",
            selector=True,
        )
        != expected_selector_added
        or validate_key_array_with_direction(
            selector_churn["prominent_removed"],
            "CURRENT_CHURN_SELECTOR_REMOVED",
            selector=True,
        )
        != expected_selector_removed
        or selector_churn["previous_prominent_count"]
        != len(previous.selector_prominent)
        or selector_churn["prominent_retained_count"]
        != len(expected_selector_retained)
    ):
        fail("CURRENT_CHURN_SELECTOR_MISMATCH")


def validate_previous_decision(bound: BoundInput) -> frozenset[ExactKey]:
    payload = bound.payload
    required = {
        "schema_version",
        "mode",
        "decision_id",
        "status",
        "proposed_entries",
        "authority",
        "operator_approval_required",
        "authority_boundaries",
    }
    if not required.issubset(payload):
        fail("PREVIOUS_DECISION_FIELDS_INVALID")
    if (
        payload["schema_version"] != 1
        or payload["mode"] != DECISION_MODE
        or payload["status"]
        not in {"ELIGIBLE_FOR_OPERATOR_REVIEW", "GOVERNOR_BLOCKED"}
        or not isinstance(payload["decision_id"], str)
        or SHA256_RE.fullmatch(payload["decision_id"]) is None
        or payload["authority"] != "advisory_pending_operator_approval"
        or payload["operator_approval_required"] is not True
    ):
        fail("PREVIOUS_DECISION_INVALID")
    boundaries = payload["authority_boundaries"]
    if not isinstance(boundaries, dict) or any(boundaries.values()):
        fail("PREVIOUS_DECISION_AUTHORITY_INVALID")
    proposed = exact_key_set(
        payload["proposed_entries"],
        "PREVIOUS_DECISION_PROPOSED",
    )
    if payload["status"] == "GOVERNOR_BLOCKED" and proposed:
        fail("PREVIOUS_DECISION_BLOCKED_NONEMPTY")
    return proposed


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


def snapshot_reference(
    snapshot: SnapshotEvidence,
    producer_git_sha: str,
) -> dict[str, Any]:
    selector_config_sha = hashlib.sha256(
        canonical_json_bytes(SELECTOR_CONFIG)
    ).hexdigest()
    return {
        "path": str(snapshot.bound.path),
        "sha256": snapshot.bound.sha256,
        "schema_version": snapshot.schema_version,
        "generated_at": format_timestamp(snapshot.generated_at),
        "source_cutoff_at": format_timestamp(snapshot.source_cutoff_at),
        "producer_git_sha": producer_git_sha,
        "selector_config_sha256": selector_config_sha,
        "selector_view_present": snapshot.selector_prominent is not None,
        "selector_view_churn_available": snapshot.selector_churn_available,
    }


def concentration_counts(
    keys: frozenset[ExactKey],
) -> tuple[Counter[tuple[str, str, str]], Counter[str]]:
    pair_variant: Counter[tuple[str, str, str]] = Counter()
    instruments: Counter[str] = Counter()
    for pair_id, timeframe, variant, _direction in keys:
        pair_variant[(pair_id, timeframe, variant)] += 1
        left, right = pair_id.split("__")
        instruments[left] += 1
        instruments[right] += 1
    return pair_variant, instruments


def build_gate_results(reasons: list[str]) -> tuple[dict[str, Any], dict[str, int]]:
    by_gate: dict[str, list[str]] = {name: [] for name in GATE_NAMES}
    for reason in reasons:
        gate = REASON_TO_GATE[reason]
        by_gate[gate].append(reason)
    gate_results = {
        gate: {
            "verdict": "BLOCK" if gate_reasons else "PASS",
            "reason_codes": gate_reasons,
        }
        for gate, gate_reasons in by_gate.items()
    }
    block_count = sum(
        result["verdict"] == "BLOCK" for result in gate_results.values()
    )
    return gate_results, {
        "pass_count": len(GATE_NAMES) - block_count,
        "block_count": block_count,
        "total_count": len(GATE_NAMES),
    }


def build_decision(
    *,
    current: SnapshotEvidence,
    previous: SnapshotEvidence,
    baseline: frozenset[ExactKey],
    paper: BoundInput,
    paper_producer_git_sha: str,
    governor: BoundInput,
    current_producer_git_sha: str,
    previous_producer_git_sha: str,
    evaluated_at: dt.datetime,
) -> dict[str, Any]:
    if current.bound.sha256 == previous.bound.sha256:
        fail("SNAPSHOT_HASH_REUSED")
    if current.source_cutoff_at <= previous.source_cutoff_at:
        fail("SOURCE_CUTOFF_ORDER_INVALID")
    if current.source_cutoff_at > evaluated_at:
        fail("CURRENT_SOURCE_FROM_FUTURE")
    validate_static_comparison(current, baseline, "CURRENT")
    validate_static_comparison(previous, baseline, "PREVIOUS")
    validate_current_churn(current, previous)

    reasons: list[str] = []
    previous_comparable = (
        previous.schema_version == 2
        and previous.selector_prominent is not None
        and previous.selector_churn_available
    )
    current_comparable = (
        current.schema_version == 2
        and current.selector_prominent is not None
        and current.selector_churn_available
    )
    if previous.schema_version != 2:
        reasons.append("PREVIOUS_SNAPSHOT_NOT_SCHEMA_V2")
    if not previous_comparable or not current_comparable:
        reasons.append("SELECTOR_CHURN_UNAVAILABLE")

    separation = int(
        (current.source_cutoff_at - previous.source_cutoff_at).total_seconds()
    )
    age = int((evaluated_at - current.source_cutoff_at).total_seconds())
    if separation < GOVERNOR_CONFIG["min_source_cutoff_separation_seconds"]:
        reasons.append("SOURCE_CUTOFF_SEPARATION_TOO_SHORT")
    if age > GOVERNOR_CONFIG["max_current_source_age_seconds"]:
        reasons.append("CURRENT_SOURCE_STALE")

    rejected_or_quarantined = (
        current.rejected
        | current.quarantined
        | previous.rejected
        | previous.quarantined
    )
    current_prominent = frozenset(
        key
        for key in (current.selector_prominent or frozenset())
        if key[3] in ACTIONABLE_DIRECTIONS
    )
    previous_prominent = frozenset(
        key
        for key in (previous.selector_prominent or frozenset())
        if key[3] in ACTIONABLE_DIRECTIONS
    )
    qualifying = frozenset(
        key
        for key in (
            baseline
            & current.selected
            & previous.selected
            & current_prominent
            & previous_prominent
        )
        if key not in rejected_or_quarantined
    )
    if not qualifying:
        reasons.append("NO_QUALIFYING_ENTRIES")

    pair_variant, instruments = concentration_counts(qualifying)
    if len(qualifying) > GOVERNOR_CONFIG["max_governed_entries"]:
        reasons.append("MAX_GOVERNED_ENTRIES_EXCEEDED")
    if any(
        count > GOVERNOR_CONFIG["max_directions_per_pair_variant"]
        for count in pair_variant.values()
    ):
        reasons.append("PAIR_VARIANT_DIRECTION_LIMIT_EXCEEDED")
    if any(
        count > GOVERNOR_CONFIG["max_entries_per_full_instrument"]
        for count in instruments.values()
    ):
        reasons.append("INSTRUMENT_CONCENTRATION_LIMIT_EXCEEDED")

    proposed = frozenset() if reasons else qualifying
    change_count = len(baseline ^ proposed)
    churn_ratio = change_count / len(baseline) if baseline else None
    if change_count > GOVERNOR_CONFIG["max_changed_entries"]:
        reasons.append("MAX_CHANGED_ENTRIES_EXCEEDED")
    if (
        churn_ratio is not None
        and churn_ratio > GOVERNOR_CONFIG["max_churn_ratio"]
    ):
        reasons.append("MAX_CHURN_RATIO_EXCEEDED")
    if reasons:
        proposed = frozenset()
        change_count = len(baseline)
        churn_ratio = 1.0 if baseline else None

    additions = proposed - baseline
    if additions:
        fail("ADDITION_FORBIDDEN")
    removals = baseline - proposed
    retained = baseline & proposed
    status = (
        "GOVERNOR_BLOCKED"
        if reasons
        else "ELIGIBLE_FOR_OPERATOR_REVIEW"
    )
    evaluated_at_text = format_timestamp(evaluated_at)
    valid_until = format_timestamp(
        evaluated_at
        + dt.timedelta(seconds=GOVERNOR_CONFIG["validity_seconds"])
    )
    gate_results, gate_summary = build_gate_results(reasons)

    pair_variant_rows = [
        {
            "pair_id": pair_id,
            "timeframe": timeframe,
            "selected_variant": variant,
            "direction_count": count,
        }
        for (pair_id, timeframe, variant), count in sorted(pair_variant.items())
    ]
    instrument_rows = [
        {"instrument_id": instrument_id, "entry_count": count}
        for instrument_id, count in sorted(instruments.items())
    ]
    decision = {
        "schema_version": 1,
        "mode": DECISION_MODE,
        "decision_id": decision_id(
            current_snapshot_sha256=current.bound.sha256,
            previous_snapshot_sha256=previous.bound.sha256,
            paper_run_config_sha256=paper.sha256,
            governor_config_sha256=governor.sha256,
            evaluated_at=evaluated_at_text,
        ),
        "status": status,
        "evaluated_at": evaluated_at_text,
        "valid_until": valid_until,
        "current_snapshot": snapshot_reference(
            current,
            current_producer_git_sha,
        ),
        "previous_snapshot": snapshot_reference(
            previous,
            previous_producer_git_sha,
        ),
        "paper_run_config": {
            "path": str(paper.path),
            "sha256": paper.sha256,
            "producer_git_sha": paper_producer_git_sha,
            "static_allowlist_mode": "pair_variant_direction",
            "static_allowlist_entry_count": len(baseline),
        },
        "selector_config": SELECTOR_CONFIG,
        "governor_config": GOVERNOR_CONFIG,
        "governor_config_source": {
            "path": str(governor.path),
            "sha256": governor.sha256,
        },
        "baseline_entries": [key_object(key) for key in sorted(baseline)],
        "proposed_entries": [key_object(key) for key in sorted(proposed)],
        "additions": [key_object(key) for key in sorted(additions)],
        "removals": [key_object(key) for key in sorted(removals)],
        "retained_entries": [key_object(key) for key in sorted(retained)],
        "direction_counts": dict(current.direction_counts),
        "gate_results": gate_results,
        "gate_summary": gate_summary,
        "calculations": {
            "source_cutoff_separation_seconds": separation,
            "current_source_age_seconds": age,
            "baseline_entry_count": len(baseline),
            "qualifying_entry_count": len(qualifying),
            "proposed_entry_count": len(proposed),
            "change_count": change_count,
            "churn_ratio": churn_ratio,
            "pair_variant_concentrations": pair_variant_rows,
            "instrument_concentrations": instrument_rows,
        },
        "reason_codes": reasons,
        "methodology": {
            "transition_posture": "DEMOTION_ONLY_STATIC_BASELINE_SUBSET",
            "candidate_overflow_behavior": "BLOCK_EMPTY_NO_RANK_OR_TRUNCATE",
            "selector_realized_evidence_relation": "SET_MEMBERSHIP_ONLY_NO_NUMERIC_MERGE",
            "none_direction_behavior": "NON_ACTIONABLE_DISTINCT_FROM_NULL",
            "null_direction_behavior": "NON_ACTIONABLE_MISSING_DIRECTION",
            "unknown_direction_behavior": "REJECT_INPUT_NO_ARTIFACT",
            "serialization_behavior": "CANONICAL_SORTED_BYTE_IDENTICAL_FOR_IDENTICAL_INPUTS",
            "output_path_behavior": "EXCLUSIVE_CREATE_NO_OVERWRITE_OR_REPAIR",
            "input_behavior": "READ_ONLY_HASH_PRESERVING",
            "fallback_behavior": "NO_FALLBACK_OR_AUTOMATIC_ROLLBACK",
        },
        "authority": "advisory_pending_operator_approval",
        "operator_approval_required": True,
        "operator_approval_binding": {
            "append_only_operator_decision_required": True,
            "decision_id_required": True,
            "decision_json_sha256_required": True,
            "governor_config_sha256_required": True,
            "valid_until_required": True,
            "bounded_paper_run_id_required": True,
        },
        "authority_boundaries": {
            "paper_eligibility_authority": False,
            "live_eligibility_authority": False,
            "execution_authority": False,
            "runtime_configuration_write_authority": False,
            "deployment_authority": False,
        },
    }
    validate_decision_semantics(decision)
    return decision


def validate_decision_semantics(decision: dict[str, Any]) -> None:
    baseline = exact_key_set(decision["baseline_entries"], "DECISION_BASELINE")
    proposed = exact_key_set(decision["proposed_entries"], "DECISION_PROPOSED")
    additions = exact_key_set(decision["additions"], "DECISION_ADDITIONS")
    removals = exact_key_set(decision["removals"], "DECISION_REMOVALS")
    retained = exact_key_set(decision["retained_entries"], "DECISION_RETAINED")
    if (
        not proposed.issubset(baseline)
        or additions
        or removals != baseline - proposed
        or retained != baseline & proposed
    ):
        fail("DECISION_TRANSITION_INCONSISTENT")
    status = decision["status"]
    reasons = decision["reason_codes"]
    if status == "GOVERNOR_BLOCKED":
        if proposed or not reasons:
            fail("DECISION_BLOCKED_INCONSISTENT")
    elif status == "ELIGIBLE_FOR_OPERATOR_REVIEW":
        if not proposed or reasons:
            fail("DECISION_ELIGIBLE_INCONSISTENT")
    else:
        fail("DECISION_STATUS_INVALID")
    if any(decision["authority_boundaries"].values()):
        fail("DECISION_AUTHORITY_INVALID")


def render_markdown(
    decision: dict[str, Any],
    *,
    previous_decision: BoundInput | None,
    previous_proposed: frozenset[ExactKey] | None,
) -> str:
    churn_ratio = decision["calculations"]["churn_ratio"]
    churn_text = "null" if churn_ratio is None else f"{churn_ratio:.6f}"
    lines = [
        "# AUTO-2C Governed Dynamic-Allowlist Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Decision ID: `{decision['decision_id']}`",
        f"- Evaluated at: `{decision['evaluated_at']}`",
        f"- Valid until: `{decision['valid_until']}`",
        "- Authority: `advisory_pending_operator_approval`",
        "- Paper eligibility authority: `false`",
        "- Live eligibility authority: `false`",
        "",
        "## Bound Inputs",
        "",
        f"- Current snapshot: `{decision['current_snapshot']['path']}`",
        f"- Current SHA-256: `{decision['current_snapshot']['sha256']}`",
        f"- Previous snapshot: `{decision['previous_snapshot']['path']}`",
        f"- Previous SHA-256: `{decision['previous_snapshot']['sha256']}`",
        f"- Paper run config: `{decision['paper_run_config']['path']}`",
        f"- Paper config SHA-256: `{decision['paper_run_config']['sha256']}`",
        f"- Governor config: `{decision['governor_config_source']['path']}`",
        f"- Governor config SHA-256: `{decision['governor_config_source']['sha256']}`",
        "",
        "## Transition",
        "",
        f"- Baseline entries: `{len(decision['baseline_entries'])}`",
        f"- Qualifying entries: `{decision['calculations']['qualifying_entry_count']}`",
        f"- Proposed entries: `{len(decision['proposed_entries'])}`",
        f"- Changed exact keys: `{decision['calculations']['change_count']}`",
        f"- Churn ratio: `{churn_text}`",
        "",
        "| Pair | Timeframe | Variant | Direction |",
        "|---|---|---|---|",
    ]
    for key in decision["proposed_entries"]:
        lines.append(
            f"| {key['pair_id']} | {key['timeframe']} | "
            f"{key['selected_variant']} | {key['direction']} |"
        )
    if not decision["proposed_entries"]:
        lines.append("| _none_ | - | - | - |")
    lines.extend(["", "## Gate Results", "", "| Gate | Verdict | Reasons |", "|---|---|---|"])
    for gate in GATE_NAMES:
        result = decision["gate_results"][gate]
        reasons = ", ".join(result["reason_codes"]) or "-"
        lines.append(f"| {gate} | {result['verdict']} | {reasons} |")
    lines.extend(
        [
            "",
            "## Direction Evidence",
            "",
            f"- Selector `NONE`: `{decision['direction_counts']['selector_none_count']}`",
            f"- Selector null: `{decision['direction_counts']['selector_null_count']}`",
            "- Unknown selector directions: `0`",
            "- Realized `NONE`, null, or unknown directions: `0`",
        ]
    )
    if previous_decision is not None and previous_proposed is not None:
        current_proposed = exact_key_set(
            decision["proposed_entries"],
            "MARKDOWN_CURRENT_PROPOSED",
        )
        added = sorted(current_proposed - previous_proposed)
        removed = sorted(previous_proposed - current_proposed)
        lines.extend(
            [
                "",
                "## Non-Authoritative Previous-Decision Comparison",
                "",
                f"- Path: `{previous_decision.path}`",
                f"- SHA-256: `{previous_decision.sha256}`",
                f"- Proposed additions vs comparison: `{len(added)}`",
                f"- Proposed removals vs comparison: `{len(removed)}`",
                "- This comparison does not affect status, qualification, "
                "fallback, eligibility, or authority.",
            ]
        )
    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "This artifact is advisory only. It cannot alter paper or live "
            "eligibility, runtime configuration, services, orders, execution, "
            "or deployment. A later bounded paper trial requires a separate "
            "append-only Operator approval naming the exact decision JSON hash.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_output_paths(
    output_json_value: str | None,
    output_markdown_value: str | None,
) -> tuple[Path, Path, Path]:
    output_json = require_absolute_path(output_json_value, "OUTPUT_JSON")
    output_markdown = require_absolute_path(
        output_markdown_value,
        "OUTPUT_MARKDOWN",
    )
    if output_json.name != OUTPUT_JSON_NAME:
        fail("OUTPUT_JSON_NAME_INVALID")
    if output_markdown.name != OUTPUT_MARKDOWN_NAME:
        fail("OUTPUT_MARKDOWN_NAME_INVALID")
    if output_json.parent != output_markdown.parent:
        fail("OUTPUT_PARENT_MISMATCH")
    output_root = output_json.parent
    if output_root.exists() or output_root.is_symlink():
        fail("OUTPUT_ROOT_EXISTS")
    parent = output_root.parent
    try:
        parent_stat = parent.lstat()
    except FileNotFoundError as error:
        raise GovernorInputError("OUTPUT_ROOT_PARENT_MISSING") from error
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        fail("OUTPUT_ROOT_PARENT_INVALID")
    return output_root, output_json, output_markdown


def write_outputs_exclusively(
    output_root: Path,
    output_json: Path,
    output_markdown: Path,
    json_bytes: bytes,
    markdown_bytes: bytes,
) -> None:
    try:
        output_root.mkdir(mode=0o700)
    except FileExistsError as error:
        raise GovernorInputError("OUTPUT_ROOT_EXISTS") from error
    try:
        with output_json.open("xb") as handle:
            handle.write(json_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        with output_markdown.open("xb") as handle:
            handle.write(markdown_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(output_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        # A crash/failure residue is deliberately retained. Reuse and repair
        # are forbidden; the caller must choose a fresh output root.
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="Explicitly run one offline advisory governor evaluation.",
    )
    parser.add_argument("--current-snapshot-json")
    parser.add_argument("--current-snapshot-sha256")
    parser.add_argument("--current-snapshot-producer-git-sha")
    parser.add_argument("--previous-snapshot-json")
    parser.add_argument("--previous-snapshot-sha256")
    parser.add_argument("--previous-snapshot-producer-git-sha")
    parser.add_argument("--paper-run-config-json")
    parser.add_argument("--paper-run-config-sha256")
    parser.add_argument("--paper-run-config-producer-git-sha")
    parser.add_argument("--governor-config-json")
    parser.add_argument("--governor-config-sha256")
    parser.add_argument("--evaluated-at")
    parser.add_argument("--previous-decision-json")
    parser.add_argument("--previous-decision-sha256")
    parser.add_argument("--output-json")
    parser.add_argument("--output-markdown")
    return parser.parse_args(argv)


def run_enabled(args: argparse.Namespace) -> dict[str, Any]:
    current_producer = require_git_sha(
        args.current_snapshot_producer_git_sha,
        "CURRENT_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    previous_producer = require_git_sha(
        args.previous_snapshot_producer_git_sha,
        "PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA",
    )
    paper_producer = require_git_sha(
        args.paper_run_config_producer_git_sha,
        "PAPER_RUN_CONFIG_PRODUCER_GIT_SHA",
    )
    evaluated_at = parse_timestamp(args.evaluated_at, "EVALUATED_AT")
    evaluated_at = evaluated_at.replace(microsecond=0)
    output_root, output_json, output_markdown = validate_output_paths(
        args.output_json,
        args.output_markdown,
    )

    current_bound = read_bound_input(
        args.current_snapshot_json,
        args.current_snapshot_sha256,
        "CURRENT_SNAPSHOT",
    )
    previous_bound = read_bound_input(
        args.previous_snapshot_json,
        args.previous_snapshot_sha256,
        "PREVIOUS_SNAPSHOT",
    )
    paper_bound = read_bound_input(
        args.paper_run_config_json,
        args.paper_run_config_sha256,
        "PAPER_RUN_CONFIG",
    )
    governor_bound = read_bound_input(
        args.governor_config_json,
        args.governor_config_sha256,
        "GOVERNOR_CONFIG",
    )
    previous_decision_bound: BoundInput | None = None
    previous_proposed: frozenset[ExactKey] | None = None
    if (args.previous_decision_json is None) != (
        args.previous_decision_sha256 is None
    ):
        fail("PREVIOUS_DECISION_BINDING_INCOMPLETE")
    if args.previous_decision_json is not None:
        previous_decision_bound = read_bound_input(
            args.previous_decision_json,
            args.previous_decision_sha256,
            "PREVIOUS_DECISION",
        )
        previous_proposed = validate_previous_decision(previous_decision_bound)

    current = validate_snapshot(current_bound, "CURRENT")
    previous = validate_snapshot(previous_bound, "PREVIOUS")
    baseline = validate_paper_config(paper_bound)
    validate_governor_config(governor_bound)
    decision = build_decision(
        current=current,
        previous=previous,
        baseline=baseline,
        paper=paper_bound,
        paper_producer_git_sha=paper_producer,
        governor=governor_bound,
        current_producer_git_sha=current_producer,
        previous_producer_git_sha=previous_producer,
        evaluated_at=evaluated_at,
    )
    markdown = render_markdown(
        decision,
        previous_decision=previous_decision_bound,
        previous_proposed=previous_proposed,
    )
    decision_bytes = json_file_bytes(decision)
    markdown_bytes = markdown.encode("utf-8")

    bound_inputs = [
        ("CURRENT_SNAPSHOT", current_bound),
        ("PREVIOUS_SNAPSHOT", previous_bound),
        ("PAPER_RUN_CONFIG", paper_bound),
        ("GOVERNOR_CONFIG", governor_bound),
    ]
    if previous_decision_bound is not None:
        bound_inputs.append(("PREVIOUS_DECISION", previous_decision_bound))
    for source, bound in bound_inputs:
        recheck_bound_input(bound, source)

    write_outputs_exclusively(
        output_root,
        output_json,
        output_markdown,
        decision_bytes,
        markdown_bytes,
    )
    return {
        "artifact_created": True,
        "authority": "advisory_pending_operator_approval",
        "decision_id": decision["decision_id"],
        "decision_json": str(output_json),
        "decision_json_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        "decision_markdown": str(output_markdown),
        "decision_markdown_sha256": hashlib.sha256(markdown_bytes).hexdigest(),
        "mode": DECISION_MODE,
        "operator_approval_required": True,
        "output_root": str(output_root),
        "status": decision["status"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.enabled:
        print(
            json.dumps(DISABLED_DIAGNOSTIC, sort_keys=True, separators=(",", ":"))
        )
        return 0
    try:
        diagnostic = run_enabled(args)
    except GovernorInputError as error:
        print(
            json.dumps(
                {
                    "artifact_created": False,
                    "error_code": error.code,
                    "mode": DECISION_MODE,
                    "status": "INPUT_REJECTED",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "artifact_created": False,
                    "error_code": "OUTPUT_WRITE_FAILED_PARTIAL_ROOT_RETAINED",
                    "mode": DECISION_MODE,
                    "status": "OUTPUT_REJECTED",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 3
    print(json.dumps(diagnostic, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
