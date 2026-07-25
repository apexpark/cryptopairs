#!/usr/bin/env python3
"""Build an AUTO-2B shadow dynamic allowlist snapshot.

This tool is artifact-only. It ranks paper-observed pair/variant/direction
evidence and records what a dynamic allowlist would select, but it never calls
HTTP services, never writes runtime config, and never controls paper or live
entries.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import pathlib
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Optional, Sequence


SCHEMA_VERSION = 1
SELECTOR_VIEW_SCHEMA_VERSION = 2
MODE = "shadow_dynamic_allowlist_snapshot"
TIMEFRAME = "1m"
LONG_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{6})\d+((?:[+-]\d{2}:\d{2})?)$")
RFC3339_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
SUPPORTED_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}
SUPPORTED_SELECTOR_DIRECTIONS = {"LONG_SPREAD", "NONE", "SHORT_SPREAD"}
SELECTOR_VIEW_BUCKETS = ("TRADE_NOW", "WATCHLIST", "EXCLUDED")
SELECTOR_VIEW_PROFILE = "selector_view"
SELECTOR_VIEW_TICK_PROFILE = "selector_view_tick"
SELECTOR_VIEW_DECISION = "SELECTOR_VIEW_OBSERVED"
SELECTOR_VIEW_TICK_DECISION = "SELECTOR_VIEW_TICK_CAPTURED"
SELECTOR_VIEW_FORBIDDEN_FIELD_TOKENS = ("realized", "outcome", "pnl", "fill")
SELECTOR_VIEW_SYSTEM_PAIR_ID = "__SYSTEM__"
SELECTOR_VIEW_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "capture_profile",
        "run_id",
        "observed_at",
        "source_generated_at",
        "timeframe",
        "decision",
        "recorded_rows",
        "rows_per_bucket",
    }
)
SELECTOR_VIEW_REQUIRED_ROW_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "capture_profile",
        "run_id",
        "observed_at",
        "source_generated_at",
        "timeframe",
        "pair_id",
        "selected_variant",
        "cue_bucket",
        "direction_hint",
        "decision",
        "decision_reason_code",
        "blocked_reason_code",
        "watch_reason_code",
        "rationale_codes",
        "setup_gate_pass",
        "cost_gate_pass",
        "trade_gate_pass",
        "spread_z",
        "net_edge_bps",
        "opportunity_score",
        "observe_key",
    }
)
SELECTOR_VIEW_OPTIONAL_ROW_FIELDS = frozenset(
    {
        "selected_score_z",
        "entry_distance_z",
        "approval_source",
        "left_instrument",
        "right_instrument",
        "confidence_band",
        "expected_hold_bars",
        "open_live_trade",
        "portfolio_target_weight",
        "portfolio_risk_contribution",
        "requires_fresh_overlay",
        "learning_recommendation",
        "learning_trade_eligible",
        "learning_selection_selected",
        "learning_reason_codes",
        "learning_cycle_generated_at",
        "selected_config_source",
        "legacy_fallback_active",
        "decision_bucket",
    }
)
SELECTOR_VIEW_ROW_FIELDS = (
    SELECTOR_VIEW_REQUIRED_ROW_FIELDS | SELECTOR_VIEW_OPTIONAL_ROW_FIELDS
)

Key = tuple[str, str, str, str]
StaticAllowlistEntry = tuple[str, str, str, Optional[str]]
SelectorKey = tuple[str, str, str, Optional[str]]


@dataclasses.dataclass(frozen=True)
class SelectorConfig:
    min_closed_positions: int = 10
    min_avg_net_bps: float = 0.0
    max_tail_loss_bps: float = -60.0
    max_avg_exit_lag_seconds: int = 1800
    max_selected: int = 8
    min_score: float = 0.0


@dataclasses.dataclass(frozen=True)
class TradeEvent:
    key: Key
    entry_at: dt.datetime
    exit_at: dt.datetime
    realized_net_bps: float
    exit_lag_seconds: float | None = None


@dataclasses.dataclass(frozen=True)
class SelectorViewTick:
    run_id: str
    observed_at: dt.datetime
    source_generated_at: dt.datetime
    rows: tuple[dict[str, Any], ...]


def parse_timestamp(value: Any, field_name: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty timestamp string")
    normalized = value.replace("Z", "+00:00")
    normalized = LONG_FRACTIONAL_SECONDS_RE.sub(r"\1\2", normalized)
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone: {value}")
    return parsed.astimezone(dt.timezone.utc)


def parse_selector_timestamp(value: Any, field_name: str) -> dt.datetime:
    """Parse one selector-v2 identity timestamp under its RFC 3339 contract."""
    if not isinstance(value, str) or not RFC3339_TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"{field_name} is not a valid RFC 3339 timestamp: {value}")
    normalized = value.replace("t", "T", 1)
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        return parse_timestamp(normalized, field_name)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} is not a valid RFC 3339 timestamp: {value}"
        ) from exc


def format_timestamp(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def require_string(row: dict[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def numeric(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def optional_identity_string(row: dict[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string when present")


def direction_value(value: Any) -> str:
    if isinstance(value, str) and value in SUPPORTED_DIRECTIONS:
        return value
    raise ValueError(f"direction must be one of {sorted(SUPPORTED_DIRECTIONS)}")


def row_key(row: dict[str, Any]) -> Key:
    return (
        require_string(row, "pair_id"),
        require_string(row, "timeframe"),
        require_string(row, "selected_variant"),
        direction_value(row.get("direction")),
    )


def load_json_rows(paths: Sequence[pathlib.Path], source_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload_rows = payload.get("rows", payload.get("closed_positions"))
        else:
            payload_rows = payload
        if not isinstance(payload_rows, list):
            raise ValueError(f"{source_name} {path} must be a JSON array or object with rows")
        for row in payload_rows:
            if not isinstance(row, dict):
                raise ValueError(f"{source_name} {path} rows must be objects")
            rows.append(row)
    return rows


def read_jsonl_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} is not a JSON object")
        rows.append(payload)
    return rows


def selector_view_forbidden_fields(value: Any, prefix: str = "") -> list[str]:
    fields: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            field_path = f"{prefix}.{key}" if prefix else str(key)
            lowered = str(key).lower()
            if any(token in lowered for token in SELECTOR_VIEW_FORBIDDEN_FIELD_TOKENS):
                fields.append(field_path)
            fields.extend(selector_view_forbidden_fields(child, field_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            fields.extend(selector_view_forbidden_fields(child, f"{prefix}[{index}]"))
    return fields


def selector_view_key(row: dict[str, Any]) -> SelectorKey:
    pair_id = require_string(row, "pair_id")
    timeframe = require_string(row, "timeframe")
    if timeframe != TIMEFRAME:
        raise ValueError(f"selector-view timeframe must be {TIMEFRAME!r}")
    selected_variant = require_string(row, "selected_variant")
    direction = row.get("direction_hint")
    if direction is not None:
        if (
            not isinstance(direction, str)
            or direction not in SUPPORTED_SELECTOR_DIRECTIONS
        ):
            raise ValueError(
                "selector-view direction_hint must be null or one of "
                f"{sorted(SUPPORTED_SELECTOR_DIRECTIONS)}"
            )
    return (pair_id, timeframe, selected_variant, direction)


def selector_view_key_sort(key: SelectorKey) -> tuple[str, str, str, str]:
    return (key[0], key[1], key[2], key[3] or "")


def selector_view_key_object(key: SelectorKey) -> dict[str, str | None]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
    }


def selector_metric_number(value: Any, field_name: str) -> int | float:
    """Validate a finite JSON number without rounding large integers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _require_selector_constant(
    row: dict[str, Any], field_name: str, expected: Any, context: str
) -> None:
    if row.get(field_name) != expected:
        raise ValueError(f"{context}: {field_name} must equal {expected!r}")


def _require_selector_fields(
    row: dict[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    context: str,
) -> None:
    missing = sorted(required - set(row))
    unexpected = sorted(set(row) - allowed)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError(f"{context}: selector-view contract fields invalid: {'; '.join(details)}")


def _selector_manifest(
    row: dict[str, Any], context: str
) -> tuple[str, dt.datetime, dt.datetime, int, dict[str, int]]:
    _require_selector_fields(
        row,
        required=SELECTOR_VIEW_MANIFEST_FIELDS,
        allowed=SELECTOR_VIEW_MANIFEST_FIELDS,
        context=context,
    )
    _require_selector_constant(row, "schema_version", SELECTOR_VIEW_SCHEMA_VERSION, context)
    _require_selector_constant(row, "mode", "observe_only", context)
    _require_selector_constant(row, "capture_profile", SELECTOR_VIEW_TICK_PROFILE, context)
    _require_selector_constant(row, "timeframe", TIMEFRAME, context)
    _require_selector_constant(row, "decision", SELECTOR_VIEW_TICK_DECISION, context)
    run_id = require_string(row, "run_id")
    observed_at_raw = require_string(row, "observed_at")
    if run_id != observed_at_raw:
        raise ValueError(f"{context}: run_id must equal the manifest observed_at")
    parse_selector_timestamp(run_id, "run_id")
    observed_at = parse_selector_timestamp(observed_at_raw, "observed_at")
    source_generated_at = parse_selector_timestamp(
        row.get("source_generated_at"), "source_generated_at"
    )
    recorded_rows = row.get("recorded_rows")
    if isinstance(recorded_rows, bool) or not isinstance(recorded_rows, int):
        raise ValueError(f"{context}: recorded_rows must be an integer")
    if recorded_rows < 0:
        raise ValueError(f"{context}: recorded_rows must be non-negative")
    raw_counts = row.get("rows_per_bucket")
    if not isinstance(raw_counts, dict) or set(raw_counts) != set(SELECTOR_VIEW_BUCKETS):
        raise ValueError(
            f"{context}: rows_per_bucket must contain exactly {SELECTOR_VIEW_BUCKETS}"
        )
    counts: dict[str, int] = {}
    for bucket in SELECTOR_VIEW_BUCKETS:
        value = raw_counts.get(bucket)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"{context}: rows_per_bucket.{bucket} must be a non-negative integer"
            )
        counts[bucket] = value
    if sum(counts.values()) != recorded_rows:
        raise ValueError(f"{context}: manifest row counts do not sum to recorded_rows")
    return run_id, observed_at, source_generated_at, recorded_rows, counts


def _validate_selector_view_row(
    row: dict[str, Any], manifest: dict[str, Any], context: str
) -> SelectorKey:
    forbidden_fields = selector_view_forbidden_fields(row)
    if forbidden_fields:
        raise ValueError(
            f"{context}: selector-view row carries forbidden outcome fields: "
            + ", ".join(sorted(forbidden_fields))
        )
    _require_selector_fields(
        row,
        required=SELECTOR_VIEW_REQUIRED_ROW_FIELDS,
        allowed=SELECTOR_VIEW_ROW_FIELDS,
        context=context,
    )
    _require_selector_constant(row, "schema_version", SELECTOR_VIEW_SCHEMA_VERSION, context)
    _require_selector_constant(row, "mode", "observe_only", context)
    _require_selector_constant(row, "capture_profile", SELECTOR_VIEW_PROFILE, context)
    _require_selector_constant(row, "timeframe", TIMEFRAME, context)
    _require_selector_constant(row, "decision", SELECTOR_VIEW_DECISION, context)
    if row.get("run_id") != manifest.get("run_id"):
        raise ValueError(f"{context}: selector row run_id does not match its manifest")
    if row.get("observed_at") != manifest.get("observed_at"):
        raise ValueError(f"{context}: selector row observed_at does not match its manifest")
    if row.get("source_generated_at") != manifest.get("source_generated_at"):
        raise ValueError(
            f"{context}: selector row source_generated_at does not match its manifest"
        )
    observed_at = parse_selector_timestamp(row.get("observed_at"), "observed_at")
    parse_selector_timestamp(row.get("source_generated_at"), "source_generated_at")
    cue_bucket = row.get("cue_bucket")
    if cue_bucket not in SELECTOR_VIEW_BUCKETS:
        raise ValueError(f"{context}: cue_bucket is not a supported selector-view bucket")
    key = selector_view_key(row)
    for field_name in (
        "spread_z",
        "net_edge_bps",
        "opportunity_score",
    ):
        selector_metric_number(row.get(field_name), field_name)
    selected_score = row.get("selected_score_z")
    if selected_score is not None:
        selector_metric_number(selected_score, "selected_score_z")
    for field_name in (
        "entry_distance_z",
        "portfolio_target_weight",
        "portfolio_risk_contribution",
    ):
        value = row.get(field_name)
        if value is not None:
            selector_metric_number(value, field_name)
    for field_name in ("setup_gate_pass", "cost_gate_pass", "trade_gate_pass"):
        if not isinstance(row.get(field_name), bool):
            raise ValueError(f"{context}: {field_name} must be a boolean")
    for field_name in (
        "decision_reason_code",
        "blocked_reason_code",
        "watch_reason_code",
    ):
        value = row.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{context}: {field_name} must be a string or null")
    for field_name in (
        "approval_source",
        "left_instrument",
        "right_instrument",
        "confidence_band",
        "learning_recommendation",
        "learning_cycle_generated_at",
        "selected_config_source",
    ):
        value = row.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{context}: {field_name} must be a string or null")
    for field_name in (
        "open_live_trade",
        "requires_fresh_overlay",
        "learning_trade_eligible",
        "learning_selection_selected",
        "legacy_fallback_active",
    ):
        value = row.get(field_name)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{context}: {field_name} must be a boolean or null")
    expected_hold_bars = row.get("expected_hold_bars")
    if expected_hold_bars is not None and (
        isinstance(expected_hold_bars, bool) or not isinstance(expected_hold_bars, int)
    ):
        raise ValueError(f"{context}: expected_hold_bars must be an integer or null")
    rationale_codes = row.get("rationale_codes")
    if not isinstance(rationale_codes, list) or any(
        not isinstance(value, str) for value in rationale_codes
    ):
        raise ValueError(f"{context}: rationale_codes must be an array of strings")
    learning_reason_codes = row.get("learning_reason_codes")
    if learning_reason_codes is not None and (
        not isinstance(learning_reason_codes, list)
        or any(not isinstance(value, str) for value in learning_reason_codes)
    ):
        raise ValueError(
            f"{context}: learning_reason_codes must be an array of strings or null"
        )
    decision_bucket = row.get("decision_bucket")
    if decision_bucket is not None and decision_bucket not in SELECTOR_VIEW_BUCKETS:
        raise ValueError(f"{context}: decision_bucket is invalid")
    direction = key[3] or "NO_DIRECTION"
    minute_bucket = observed_at.replace(second=0, microsecond=0)
    expected_observe_key = ":".join(
        [
            "selector-view",
            "v2",
            key[1],
            key[0],
            key[2],
            direction,
            str(cue_bucket),
            minute_bucket.isoformat().replace("+00:00", "Z"),
        ]
    )
    if require_string(row, "observe_key") != expected_observe_key:
        raise ValueError(f"{context}: observe_key does not match selector row identity")
    return key


def _complete_selector_tick(
    *,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    expected_counts: dict[str, int],
    context: str,
) -> SelectorViewTick:
    actual_counts = {bucket: 0 for bucket in SELECTOR_VIEW_BUCKETS}
    seen_keys: set[SelectorKey] = set()
    for index, row in enumerate(rows, start=1):
        row_context = f"{context}: selector row {index}"
        key = _validate_selector_view_row(row, manifest, row_context)
        if key in seen_keys:
            raise ValueError(f"{row_context}: duplicate selector candidate within one tick")
        seen_keys.add(key)
        actual_counts[str(row["cue_bucket"])] += 1
    if actual_counts != expected_counts:
        raise ValueError(f"{context}: selector rows do not match manifest bucket counts")
    run_id, observed_at, source_generated_at, recorded_rows, _counts = _selector_manifest(
        manifest, context
    )
    if len(rows) != recorded_rows:
        raise ValueError(f"{context}: selector tick is truncated")
    return SelectorViewTick(
        run_id=run_id,
        observed_at=observed_at,
        source_generated_at=source_generated_at,
        rows=tuple(rows),
    )


def read_selector_view_ticks(paths: Sequence[pathlib.Path]) -> list[SelectorViewTick]:
    ticks: list[SelectorViewTick] = []
    seen_tick_ids: set[dt.datetime] = set()
    for path in sorted(paths, key=lambda item: str(item)):
        pending_manifest: dict[str, Any] | None = None
        pending_rows: list[dict[str, Any]] = []
        expected_rows = 0
        expected_counts: dict[str, int] = {}
        manifest_context = ""
        raw_input = path.read_text(encoding="utf-8")
        if raw_input and not raw_input.endswith("\n"):
            raise ValueError(f"{path}: selector-view JSONL lacks a terminating newline")
        for line_number, line in enumerate(raw_input.splitlines(), start=1):
            if not line.strip():
                continue
            context = f"{path}:{line_number}"
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{context}: invalid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{context}: selector-view JSONL rows must be objects")
            profile = payload.get("capture_profile")
            if profile == SELECTOR_VIEW_TICK_PROFILE:
                if pending_manifest is not None:
                    raise ValueError(f"{context}: new manifest before prior tick completed")
                run_id, observed_at, _source_at, expected_rows, expected_counts = (
                    _selector_manifest(payload, context)
                )
                tick_id = observed_at
                if tick_id in seen_tick_ids:
                    raise ValueError(f"{context}: duplicate selector-view tick")
                seen_tick_ids.add(tick_id)
                pending_manifest = payload
                pending_rows = []
                manifest_context = context
                if expected_rows == 0:
                    ticks.append(
                        _complete_selector_tick(
                            manifest=pending_manifest,
                            rows=pending_rows,
                            expected_counts=expected_counts,
                            context=manifest_context,
                        )
                    )
                    pending_manifest = None
                continue
            if profile == SELECTOR_VIEW_PROFILE:
                if pending_manifest is None:
                    raise ValueError(f"{context}: selector row has no leading tick manifest")
                pending_rows.append(payload)
                if len(pending_rows) == expected_rows:
                    ticks.append(
                        _complete_selector_tick(
                            manifest=pending_manifest,
                            rows=pending_rows,
                            expected_counts=expected_counts,
                            context=manifest_context,
                        )
                    )
                    pending_manifest = None
                    pending_rows = []
                continue
            if pending_manifest is not None:
                raise ValueError(
                    f"{context}: non-selector record interrupts a manifested selector tick"
                )
            # Refused B2-b ticks are represented by system records with no
            # selector manifest. They are not captured observations and are
            # deliberately ignored here. Any non-system entry row means the
            # caller supplied a narrow paper-feeding artifact by mistake, so
            # fail closed instead of silently mixing capture profiles.
            decision = payload.get("decision")
            if not (
                payload.get("pair_id") == SELECTOR_VIEW_SYSTEM_PAIR_ID
                and isinstance(decision, str)
                and decision.startswith("BLOCKED_")
            ):
                raise ValueError(f"{context}: non-selector record in selector-view input")
        if pending_manifest is not None:
            raise ValueError(f"{manifest_context}: selector tick is truncated at end of file")
    if not ticks:
        raise ValueError("no complete selector-view ticks found")
    return ticks


def collect_paths(files: Sequence[str], directories: Sequence[str], pattern: str) -> list[pathlib.Path]:
    paths = [pathlib.Path(value) for value in files]
    for directory in directories:
        root = pathlib.Path(directory)
        if root.exists():
            paths.extend(sorted(root.rglob(pattern)))
    return paths


def latest_positions_by_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, tuple[dt.datetime, dict[str, Any]]] = {}
    for row in rows:
        position_id = require_string(row, "paper_position_id")
        status = require_string(row, "status")
        if status == "CLOSED":
            event_time = parse_timestamp(row.get("exit_observed_at"), "exit_observed_at")
        elif status == "OPEN":
            event_time = parse_timestamp(row.get("entry_observed_at"), "entry_observed_at")
        else:
            raise ValueError(f"position status must be OPEN or CLOSED, got {status!r}")
        current = latest.get(position_id)
        if current is None or current[0] <= event_time:
            latest[position_id] = (event_time, row)
    return {position_id: row for position_id, (_, row) in latest.items()}


def events_from_positions(
    rows: Iterable[dict[str, Any]],
    counts: dict[str, int] | None = None,
) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    for row in latest_positions_by_id(rows).values():
        if row.get("status") != "CLOSED":
            if counts is not None:
                counts["position_rows_open_excluded"] = (
                    counts.get("position_rows_open_excluded", 0) + 1
                )
            continue
        key = row_key(row)
        entry_at = parse_timestamp(row.get("entry_observed_at"), "entry_observed_at")
        exit_at = parse_timestamp(row.get("exit_observed_at"), "exit_observed_at")
        exit_eligible_at = parse_timestamp(row.get("exit_eligible_at"), "exit_eligible_at")
        events.append(
            TradeEvent(
                key=key,
                entry_at=entry_at,
                exit_at=exit_at,
                realized_net_bps=numeric(row.get("realized_net_bps"), "realized_net_bps"),
                exit_lag_seconds=(exit_at - exit_eligible_at).total_seconds(),
            )
        )
    return events


def events_from_paper_trades(
    rows: Iterable[dict[str, Any]],
    counts: dict[str, int] | None = None,
) -> list[TradeEvent]:
    """Build trade events from paper-trade rows.

    Rows are deduplicated on the identity tuple (pair, timeframe, variant,
    direction, entry_ts, exit_ts, exit_mode, exit_kind); the LAST occurrence
    wins. Two genuinely different trades colliding on this tuple would be
    silently coalesced — accepted because the paper model cannot produce two
    distinct closed trades with identical identity fields, and duplicate rows
    from overlapping /paper-trades/download captures are the expected input
    hazard. Deduplicated-row counts are reported via `counts` so upstream
    data-quality duplication remains visible in the snapshot summary.
    """
    events: dict[tuple[str, ...], TradeEvent] = {}
    considered = 0
    for row in rows:
        if row.get("timeframe") != TIMEFRAME:
            if counts is not None:
                counts["trade_rows_skipped_non_timeframe"] = (
                    counts.get("trade_rows_skipped_non_timeframe", 0) + 1
                )
            continue
        if row.get("exit_ts") is None or row.get("net_bps") is None:
            if counts is not None:
                counts["trade_rows_skipped_incomplete"] = (
                    counts.get("trade_rows_skipped_incomplete", 0) + 1
                )
            continue
        considered += 1
        key = row_key(row)
        entry_at = parse_timestamp(row.get("entry_ts"), "entry_ts")
        exit_at = parse_timestamp(row.get("exit_ts"), "exit_ts")
        identity = (
            key[0],
            key[1],
            key[2],
            key[3],
            format_timestamp(entry_at) or "",
            format_timestamp(exit_at) or "",
            optional_identity_string(row, "exit_mode"),
            optional_identity_string(row, "exit_kind"),
        )
        events[identity] = TradeEvent(
            key=key,
            entry_at=entry_at,
            exit_at=exit_at,
            realized_net_bps=numeric(row.get("net_bps"), "net_bps"),
            exit_lag_seconds=None,
        )
    if counts is not None and considered > len(events):
        counts["trade_rows_deduplicated"] = (
            counts.get("trade_rows_deduplicated", 0) + considered - len(events)
        )
    return list(events.values())


def parse_allowlist(value: str | None) -> set[StaticAllowlistEntry]:
    if value is None or not value.strip():
        return set()
    entries: set[StaticAllowlistEntry] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in {2, 3} or not all(parts):
            raise ValueError(
                "static allowlist entries must be pair_id:selected_variant"
                " or pair_id:selected_variant:direction"
            )
        direction = direction_value(parts[2]) if len(parts) == 3 else None
        entries.add((parts[0], TIMEFRAME, parts[1], direction))
    return entries


def allowlist_from_run_config(path: str | None) -> set[StaticAllowlistEntry]:
    if path is None:
        return set()
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run config must be a JSON object")
    result: set[StaticAllowlistEntry] = set()
    for entry in payload.get("static_allowlist", []):
        if not isinstance(entry, dict):
            raise ValueError("run_config.static_allowlist entries must be objects")
        direction = entry.get("direction")
        result.add(
            (
                require_string(entry, "pair_id"),
                TIMEFRAME,
                require_string(entry, "selected_variant"),
                direction_value(direction) if direction is not None else None,
            )
        )
    return result


def expand_static_allowlist(
    entries: set[StaticAllowlistEntry],
    observed_keys: Iterable[Key],
) -> set[Key]:
    observed = set(observed_keys)
    expanded: set[Key] = set()
    for pair_id, timeframe, selected_variant, direction in entries:
        if direction is not None:
            expanded.add((pair_id, timeframe, selected_variant, direction))
            continue
        expanded.update(
            key
            for key in observed
            if key[0] == pair_id and key[1] == timeframe and key[2] == selected_variant
        )
    return expanded


def key_object(key: Key) -> dict[str, str]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
    }


def selector_number_summary(
    values: Sequence[int | float],
) -> dict[str, int | float] | None:
    if not values:
        return None
    decimals = [Decimal(value) if isinstance(value, int) else Decimal(str(value)) for value in values]
    required_precision = max(
        28,
        max(max(1, decimal.adjusted() + 1) for decimal in decimals) + 12,
    )
    try:
        with localcontext() as context:
            context.prec = required_precision
            mean = sum(decimals, Decimal(0)) / Decimal(len(decimals))
            quantum = Decimal("0.000001")
            rounded_min = min(decimals).quantize(quantum)
            rounded_max = max(decimals).quantize(quantum)
            rounded_mean = mean.quantize(quantum)
    except InvalidOperation as exc:
        raise ValueError("selector metric summary cannot be represented safely") from exc

    def json_number(value: Decimal) -> int | float:
        if value == value.to_integral_value():
            return int(value)
        converted = float(value)
        if not math.isfinite(converted) or Decimal(str(converted)) != value:
            raise ValueError("selector metric summary cannot be represented safely")
        return converted

    return {
        "min": json_number(rounded_min),
        "max": json_number(rounded_max),
        "mean": json_number(rounded_mean),
    }


def selector_matches_paper_key(selector_key: SelectorKey, paper_key: Key) -> bool:
    if selector_key[:3] != paper_key[:3]:
        return False
    return selector_key[3] is None or selector_key[3] == paper_key[3]


def selector_matches_static_entry(
    selector_key: SelectorKey, static_entry: StaticAllowlistEntry
) -> bool:
    if selector_key[:3] != static_entry[:3]:
        return False
    static_direction = static_entry[3]
    if static_direction is None:
        return True
    return selector_key[3] is not None and selector_key[3] == static_direction


def selector_view_blocks(
    *,
    ticks: Sequence[SelectorViewTick],
    cutoff: dt.datetime,
    paper_keys: set[Key],
    static_allowlist: set[StaticAllowlistEntry],
) -> tuple[dict[str, Any], dict[str, Any], set[SelectorKey]]:
    eligible_ticks = sorted(
        (tick for tick in ticks if tick.observed_at <= cutoff),
        key=lambda tick: (tick.observed_at, tick.run_id),
    )
    if not eligible_ticks:
        raise ValueError("no selector-view ticks at or before source_cutoff_at")
    rows_by_key: dict[SelectorKey, list[dict[str, Any]]] = defaultdict(list)
    bucket_keys: dict[str, set[SelectorKey]] = {
        bucket: set() for bucket in SELECTOR_VIEW_BUCKETS
    }
    for tick in eligible_ticks:
        for row in tick.rows:
            key = selector_view_key(row)
            rows_by_key[key].append(row)
            bucket_keys[str(row["cue_bucket"])].add(key)

    def metric_row(key: SelectorKey) -> dict[str, Any]:
        rows = rows_by_key[key]
        bucket_counts = {bucket: 0 for bucket in SELECTOR_VIEW_BUCKETS}
        scores: list[int | float] = []
        stated_edges: list[int | float] = []
        gate_reasons: Counter[str] = Counter()
        for row in rows:
            bucket_counts[str(row["cue_bucket"])] += 1
            selected_score = row.get("selected_score_z")
            if selected_score is not None:
                scores.append(
                    selector_metric_number(selected_score, "selected_score_z")
                )
            stated_edges.append(
                selector_metric_number(row.get("net_edge_bps"), "net_edge_bps")
            )
            for field_name in (
                "decision_reason_code",
                "blocked_reason_code",
                "watch_reason_code",
            ):
                reason = row.get(field_name)
                if isinstance(reason, str) and reason:
                    gate_reasons[reason] += 1
        ranked_reasons = [
            reason for reason, _count in sorted(gate_reasons.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {
            **selector_view_key_object(key),
            "evidence_kind": "selector_view",
            "metrics": {
                "rows_observed": len(rows),
                "time_in_tradable_now_ratio": round(
                    bucket_counts["TRADE_NOW"] / len(rows), 6
                ),
                "bucket_counts": bucket_counts,
                "score_z_summary": selector_number_summary(scores),
                "stated_net_edge_bps_summary": selector_number_summary(stated_edges),
                "top_gate_failure_reasons": ranked_reasons,
            },
        }

    prominent_keys = {
        key for key, rows in rows_by_key.items() if any(row["cue_bucket"] == "TRADE_NOW" for row in rows)
    }
    marginal_keys = set(rows_by_key) - prominent_keys
    selector_view = {
        "selector_view_prominent": [
            metric_row(key) for key in sorted(prominent_keys, key=selector_view_key_sort)
        ],
        "selector_view_marginal": [
            metric_row(key) for key in sorted(marginal_keys, key=selector_view_key_sort)
        ],
    }
    paper_evidenced_keys = {
        key
        for key in rows_by_key
        if any(selector_matches_paper_key(key, paper_key) for paper_key in paper_keys)
    }
    static_overlap_keys = {
        key
        for key in rows_by_key
        if any(
            selector_matches_static_entry(key, static_entry)
            for static_entry in static_allowlist
        )
    }
    selector_only = prominent_keys - static_overlap_keys
    universe = {
        "bucket_universe_counts": {
            bucket: len(bucket_keys[bucket]) for bucket in SELECTOR_VIEW_BUCKETS
        },
        "paper_evidenced_count": len(paper_evidenced_keys),
        "selector_view_only": [
            selector_view_key_object(key)
            for key in sorted(selector_only, key=selector_view_key_sort)
        ],
        "static_allowlist_overlap_count": len(static_overlap_keys),
    }
    return selector_view, universe, prominent_keys


def sum_bps(values: Sequence[float]) -> float:
    return round(sum(values), 4)


def avg_bps(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def score_components(
    *,
    closed_count: int,
    profitable_count: int,
    avg_net_bps: float,
    max_loss_bps: float,
    avg_exit_lag_seconds: float | None,
) -> dict[str, float]:
    win_rate = profitable_count / closed_count if closed_count else 0.0
    win_rate_bonus = round(max(0.0, win_rate - 0.5) * 12.0, 4)
    sample_size_bonus = round(min(closed_count, 50) * 0.03, 4)
    tail_loss_penalty = round(min(0.0, max_loss_bps) * 0.08, 4)
    # Clamp at zero: early exits (negative lag) must not become a score bonus.
    exit_lag_penalty = (
        round(-max(0.0, avg_exit_lag_seconds) / 900.0, 4)
        if avg_exit_lag_seconds is not None
        else 0.0
    )
    total_score = round(
        avg_net_bps
        + win_rate_bonus
        + sample_size_bonus
        + tail_loss_penalty
        + exit_lag_penalty,
        4,
    )
    return {
        "avg_net_bps": round(avg_net_bps, 4),
        "win_rate_bonus": win_rate_bonus,
        "sample_size_bonus": sample_size_bonus,
        "tail_loss_penalty": tail_loss_penalty,
        "exit_lag_penalty": exit_lag_penalty,
        "total_score": total_score,
    }


def candidate_row(
    *,
    key: Key,
    events: list[TradeEvent],
    config: SelectorConfig,
) -> dict[str, Any]:
    realized = [event.realized_net_bps for event in events]
    lag_values = [
        event.exit_lag_seconds for event in events if event.exit_lag_seconds is not None
    ]
    profitable = [value for value in realized if value > 0]
    losing = [value for value in realized if value <= 0]
    avg_net = sum(realized) / len(realized)
    max_loss = min(realized)
    avg_lag = (sum(lag_values) / len(lag_values)) if lag_values else None
    max_lag = max(lag_values) if lag_values else None
    components = score_components(
        closed_count=len(events),
        profitable_count=len(profitable),
        avg_net_bps=avg_net,
        max_loss_bps=max_loss,
        avg_exit_lag_seconds=avg_lag,
    )
    reasons: list[str] = []
    decision = "SHADOW_REJECTED"
    if len(events) < config.min_closed_positions:
        reasons.append("INSUFFICIENT_CLOSED_POSITIONS")
    if avg_net < config.min_avg_net_bps:
        reasons.append("AVG_NET_BPS_BELOW_THRESHOLD")
    if max_loss < config.max_tail_loss_bps:
        reasons.append("TAIL_LOSS_LIMIT_BREACHED")
        decision = "SHADOW_QUARANTINED"
    if avg_lag is not None and avg_lag > config.max_avg_exit_lag_seconds:
        reasons.append("AVG_EXIT_LAG_LIMIT_BREACHED")
    if components["total_score"] < config.min_score:
        reasons.append("SCORE_BELOW_THRESHOLD")
    if not reasons:
        decision = "SHADOW_SELECTED"
        reasons = ["PASSED_SHADOW_SELECTOR_GATES"]

    return {
        **key_object(key),
        "decision": decision,
        "reason_codes": reasons,
        "metrics": {
            "closed_positions": len(events),
            "profitable_closed_positions": len(profitable),
            "losing_closed_positions": len(losing),
            "win_rate": round(len(profitable) / len(events), 6),
            "sum_realized_net_bps": sum_bps(realized),
            "avg_realized_net_bps": round(avg_net, 4),
            "max_loss_bps": round(max_loss, 4),
            "avg_exit_lag_seconds": round(avg_lag, 4) if avg_lag is not None else None,
            "max_exit_lag_seconds": round(max_lag, 4) if max_lag is not None else None,
            "first_entry_at": format_timestamp(min(event.entry_at for event in events)),
            "last_exit_at": format_timestamp(max(event.exit_at for event in events)),
        },
        "score_components": components,
    }


def static_comparison(static_allowlist: set[Key], shadow_selected: set[Key]) -> dict[str, Any]:
    overlap = sorted(static_allowlist & shadow_selected)
    static_only = sorted(static_allowlist - shadow_selected)
    shadow_only = sorted(shadow_selected - static_allowlist)
    return {
        "static_allowlist_size": len(static_allowlist),
        "shadow_selected_size": len(shadow_selected),
        "overlap_count": len(overlap),
        "static_only_count": len(static_only),
        "shadow_only_count": len(shadow_only),
        "overlap": [key_object(key) for key in overlap],
        "static_only": [key_object(key) for key in static_only],
        "shadow_only": [key_object(key) for key in shadow_only],
    }


def snapshot_selected_keys(snapshot: dict[str, Any]) -> set[Key]:
    keys: set[Key] = set()
    for row in snapshot.get("selected", []):
        keys.add(
            (
                row["pair_id"],
                row["timeframe"],
                row["selected_variant"],
                row["direction"],
            )
        )
    return keys


def snapshot_selector_prominent_keys(snapshot: dict[str, Any]) -> set[SelectorKey] | None:
    selector_view = snapshot.get("selector_view")
    if selector_view is None:
        return None
    if snapshot.get("schema_version") != SELECTOR_VIEW_SCHEMA_VERSION:
        raise ValueError("previous snapshot selector_view requires schema_version 2")
    if not isinstance(selector_view, dict):
        raise ValueError("previous snapshot selector_view must be an object or null")
    rows = selector_view.get("selector_view_prominent")
    if not isinstance(rows, list):
        raise ValueError("previous snapshot selector_view_prominent must be an array")
    keys: set[SelectorKey] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("previous snapshot selector_view_prominent rows must be objects")
        direction = row.get("direction")
        if (
            direction is not None
            and direction not in SUPPORTED_SELECTOR_DIRECTIONS
        ):
            raise ValueError("previous snapshot selector direction is invalid")
        key: SelectorKey = (
            require_string(row, "pair_id"),
            require_string(row, "timeframe"),
            require_string(row, "selected_variant"),
            direction,
        )
        if key[1] != TIMEFRAME:
            raise ValueError("previous snapshot selector timeframe is invalid")
        if key in keys:
            raise ValueError("previous snapshot contains a duplicate prominent selector key")
        keys.add(key)
    return keys


def selector_view_churn_block(
    previous_snapshot: dict[str, Any], current_keys: set[SelectorKey]
) -> dict[str, Any] | None:
    previous_keys = snapshot_selector_prominent_keys(previous_snapshot)
    if previous_keys is None:
        return None
    added = current_keys - previous_keys
    removed = previous_keys - current_keys
    retained = current_keys & previous_keys
    return {
        "previous_prominent_count": len(previous_keys),
        "prominent_added": [
            selector_view_key_object(key)
            for key in sorted(added, key=selector_view_key_sort)
        ],
        "prominent_removed": [
            selector_view_key_object(key)
            for key in sorted(removed, key=selector_view_key_sort)
        ],
        "prominent_retained_count": len(retained),
        "churn_count": len(added) + len(removed),
        "stability_ratio": round(len(retained) / max(1, len(previous_keys)), 6),
    }


def churn_block(
    previous_snapshot: dict[str, Any] | None,
    selected_keys: set[Key],
    selector_prominent_keys: set[SelectorKey] | None = None,
) -> dict[str, Any] | None:
    """Cross-snapshot churn/stability metrics (AUTO-2 §3 exit criteria).

    None when no previous snapshot is supplied; churn and stability are
    inherently cross-snapshot quantities and require at least two runs.
    """
    if previous_snapshot is None:
        return None
    previous_keys = snapshot_selected_keys(previous_snapshot)
    added = sorted(selected_keys - previous_keys)
    removed = sorted(previous_keys - selected_keys)
    retained = selected_keys & previous_keys
    result = {
        "previous_generated_at": previous_snapshot.get("generated_at"),
        "previous_selected_count": len(previous_keys),
        "selected_added": [key_object(key) for key in added],
        "selected_removed": [key_object(key) for key in removed],
        "selected_retained_count": len(retained),
        "churn_count": len(added) + len(removed),
        "stability_ratio": round(len(retained) / max(1, len(previous_keys)), 6),
    }
    if selector_prominent_keys is not None:
        result["selector_view"] = selector_view_churn_block(
            previous_snapshot, selector_prominent_keys
        )
    return result


def validate_selector_config(config: SelectorConfig) -> None:
    for field_name in [
        "min_closed_positions",
        "max_avg_exit_lag_seconds",
        "max_selected",
    ]:
        value = getattr(config, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"selector_config.{field_name} must be an integer >= 1")
    for field_name in ["min_avg_net_bps", "max_tail_loss_bps", "min_score"]:
        value = getattr(config, field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"selector_config.{field_name} must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError(f"selector_config.{field_name} must be finite")


def build_snapshot(
    *,
    events: list[TradeEvent],
    source_cutoff_at: str,
    selector_config: SelectorConfig,
    static_allowlist: set[StaticAllowlistEntry] | None = None,
    generated_at: str | None = None,
    ingest_counts: dict[str, int] | None = None,
    previous_snapshot: dict[str, Any] | None = None,
    selector_ticks: Sequence[SelectorViewTick] | None = None,
) -> dict[str, Any]:
    validate_selector_config(selector_config)
    cutoff = parse_timestamp(source_cutoff_at, "source_cutoff_at")
    generated = (
        parse_timestamp(generated_at, "generated_at")
        if generated_at is not None
        else dt.datetime.now(dt.timezone.utc)
    )
    prior_events = [event for event in events if event.exit_at <= cutoff]
    buckets: dict[Key, list[TradeEvent]] = defaultdict(list)
    for event in prior_events:
        if event.key[1] != TIMEFRAME:
            continue
        buckets[event.key].append(event)

    rows = [
        candidate_row(key=key, events=sorted(group, key=lambda event: event.exit_at), config=selector_config)
        for key, group in buckets.items()
    ]
    selected_candidates = sorted(
        [row for row in rows if row["decision"] == "SHADOW_SELECTED"],
        key=lambda row: (
            -row["score_components"]["total_score"],
            -row["metrics"]["closed_positions"],
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
        ),
    )
    selected = selected_candidates[: selector_config.max_selected]
    overflow = selected_candidates[selector_config.max_selected :]
    for row in overflow:
        row["decision"] = "SHADOW_REJECTED"
        row["reason_codes"] = ["RANK_OUTSIDE_MAX_SELECTED"]
    rejected = sorted(
        [row for row in rows if row["decision"] == "SHADOW_REJECTED"],
        key=lambda row: (
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
        ),
    )
    quarantined = sorted(
        [row for row in rows if row["decision"] == "SHADOW_QUARANTINED"],
        key=lambda row: (
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
        ),
    )
    selected_keys = {
        (
            row["pair_id"],
            row["timeframe"],
            row["selected_variant"],
            row["direction"],
        )
        for row in selected
    }
    static_entries = set() if static_allowlist is None else static_allowlist
    static = expand_static_allowlist(static_entries, buckets.keys())
    selector_view: dict[str, Any] | None = None
    universe: dict[str, Any] | None = None
    selector_prominent_keys: set[SelectorKey] | None = None
    if selector_ticks is not None:
        selector_view, universe, selector_prominent_keys = selector_view_blocks(
            ticks=selector_ticks,
            cutoff=cutoff,
            paper_keys={event.key for event in prior_events},
            static_allowlist=static_entries,
        )
    snapshot: dict[str, Any] = {
        "schema_version": (
            SELECTOR_VIEW_SCHEMA_VERSION if selector_ticks is not None else SCHEMA_VERSION
        ),
        "mode": MODE,
        "generated_at": format_timestamp(generated),
        "source_cutoff_at": format_timestamp(cutoff),
        "selector_config": dataclasses.asdict(selector_config),
        "summary": {
            "eligible_universe_count": len(rows),
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "quarantined_count": len(quarantined),
            "source_event_count": len(prior_events),
            "events_dropped_post_cutoff": len(events) - len(prior_events),
            "trade_rows_skipped_non_timeframe": (ingest_counts or {}).get(
                "trade_rows_skipped_non_timeframe", 0
            ),
            "trade_rows_skipped_incomplete": (ingest_counts or {}).get(
                "trade_rows_skipped_incomplete", 0
            ),
            "trade_rows_deduplicated": (ingest_counts or {}).get(
                "trade_rows_deduplicated", 0
            ),
            "position_rows_open_excluded": (ingest_counts or {}).get(
                "position_rows_open_excluded", 0
            ),
        },
        "selected": selected,
        "rejected": rejected,
        "quarantined": quarantined,
        "static_allowlist_comparison": static_comparison(static, selected_keys),
        "churn": churn_block(
            previous_snapshot,
            selected_keys,
            selector_prominent_keys=selector_prominent_keys,
        ),
        "methodology": {
            "selection_boundary": (
                "AUTO-2B output is advisory shadow evidence only and must not control "
                "AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS."
            ),
            "lookahead_policy": (
                "Only closed events with exit timestamps at or before source_cutoff_at "
                "are scored."
            ),
            "scoring_definition": (
                "Score combines average net bps, win-rate bonus, sample-size bonus, "
                "tail-loss penalty, and exit-lag penalty."
            ),
            "execution_caveat": (
                "Selector-view evidence is not PnL, not fill evidence, carries no "
                "realized outcome claim, and is not permission for any eligibility "
                "change, dynamic paper, or live automation."
                if selector_ticks is not None
                else "This artifact is not live PnL, not a fill audit, and not "
                "permission to enable dynamic paper or live automation."
            ),
        },
    }
    if selector_ticks is not None:
        snapshot["selector_view"] = selector_view
        snapshot["universe"] = universe
    return snapshot


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# AUTO-2B Shadow Dynamic Allowlist Snapshot",
        "",
        f"- Generated at: `{snapshot['generated_at']}`",
        f"- Source cutoff at: `{snapshot['source_cutoff_at']}`",
        "- Mode: `shadow_dynamic_allowlist_snapshot`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in snapshot["summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Selected",
            "",
            "| Pair | Variant | Direction | Closed | Win rate | Sum bps | Avg bps | Max loss | Score |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in snapshot["selected"]:
        metrics = row["metrics"]
        score = row["score_components"]["total_score"]
        lines.append(
            "| {pair_id} | {selected_variant} | {direction} | {closed} | {win_rate} | "
            "{sum_bps} | {avg_bps} | {max_loss} | {score} |".format(
                pair_id=row["pair_id"],
                selected_variant=row["selected_variant"],
                direction=row["direction"],
                closed=metrics["closed_positions"],
                win_rate=metrics["win_rate"],
                sum_bps=metrics["sum_realized_net_bps"],
                avg_bps=metrics["avg_realized_net_bps"],
                max_loss=metrics["max_loss_bps"],
                score=score,
            )
        )
    if not snapshot["selected"]:
        lines.append("| none | none | none | 0 | 0 | 0 | 0 | 0 | 0 |")
    if snapshot.get("selector_view") is not None:
        selector_view = snapshot["selector_view"]
        lines.extend(
            [
                "",
                "## Selector-View Evidence (advisory only)",
                "",
                "These rows summarize the selector's stated view. They are not PnL, "
                "not fill evidence, and not permission for an eligibility change.",
                "",
                "| Class | Pair | Variant | Direction | Rows | Trade-now ratio | "
                "Buckets (T/W/E) | Score z (min/mean/max) | Stated edge bps "
                "(min/mean/max) | Gate reasons |",
                "|---|---|---|---|---:|---:|---|---|---|---|",
            ]
        )

        def summary_text(summary: dict[str, int | float] | None) -> str:
            if summary is None:
                return "none"
            return f"{summary['min']}/{summary['mean']}/{summary['max']}"

        for class_name, field_name in (
            ("prominent", "selector_view_prominent"),
            ("marginal", "selector_view_marginal"),
        ):
            for row in selector_view[field_name]:
                metrics = row["metrics"]
                bucket_counts = metrics["bucket_counts"]
                reasons = ", ".join(metrics["top_gate_failure_reasons"]) or "none"
                lines.append(
                    f"| {class_name} | {row['pair_id']} | {row['selected_variant']} | "
                    f"{row['direction'] or 'UNSPECIFIED'} | {metrics['rows_observed']} | "
                    f"{metrics['time_in_tradable_now_ratio']} | "
                    f"{bucket_counts['TRADE_NOW']}/{bucket_counts['WATCHLIST']}/"
                    f"{bucket_counts['EXCLUDED']} | "
                    f"{summary_text(metrics['score_z_summary'])} | "
                    f"{summary_text(metrics['stated_net_edge_bps_summary'])} | "
                    f"{reasons} |"
                )
        if not any(selector_view.values()):
            lines.append(
                "| none | none | none | none | 0 | 0 | 0/0/0 | none | none | none |"
            )
        universe = snapshot["universe"]
        lines.extend(
            [
                "",
                "## Selector-View Universe",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| trade_now_universe_count | {universe['bucket_universe_counts']['TRADE_NOW']} |",
                f"| watchlist_universe_count | {universe['bucket_universe_counts']['WATCHLIST']} |",
                f"| excluded_universe_count | {universe['bucket_universe_counts']['EXCLUDED']} |",
                f"| paper_evidenced_count | {universe['paper_evidenced_count']} |",
                f"| static_allowlist_overlap_count | {universe['static_allowlist_overlap_count']} |",
                f"| selector_view_only_count | {len(universe['selector_view_only'])} |",
            ]
        )
        lines.extend(
            [
                "",
                "### Selector-View Discovery (advisory only)",
                "",
                "Prominent candidates absent from the static allowlist. This list is "
                "not permission to alter eligibility.",
                "",
                "| Pair | Variant | Direction |",
                "|---|---|---|",
            ]
        )
        for row in universe["selector_view_only"]:
            lines.append(
                f"| {row['pair_id']} | {row['selected_variant']} | "
                f"{row['direction'] or 'UNSPECIFIED'} |"
            )
        if not universe["selector_view_only"]:
            lines.append("| none | none | none |")
    lines.extend(
        [
            "",
            "## Static Comparison",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    comparison = snapshot["static_allowlist_comparison"]
    for key in [
        "static_allowlist_size",
        "shadow_selected_size",
        "overlap_count",
        "static_only_count",
        "shadow_only_count",
    ]:
        lines.append(f"| {key} | {comparison[key]} |")
    if snapshot.get("churn"):
        churn = snapshot["churn"]
        lines.extend(
            [
                "",
                "## Churn vs Previous Snapshot",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| previous_generated_at | {churn['previous_generated_at']} |",
                f"| previous_selected_count | {churn['previous_selected_count']} |",
                f"| selected_added | {len(churn['selected_added'])} |",
                f"| selected_removed | {len(churn['selected_removed'])} |",
                f"| selected_retained_count | {churn['selected_retained_count']} |",
                f"| churn_count | {churn['churn_count']} |",
                f"| stability_ratio | {churn['stability_ratio']} |",
            ]
        )
        if churn.get("selector_view") is not None:
            selector_churn = churn["selector_view"]
            lines.extend(
                [
                    "",
                    "## Selector-View Churn vs Previous Snapshot",
                    "",
                    "| Metric | Value |",
                    "|---|---:|",
                    f"| previous_prominent_count | {selector_churn['previous_prominent_count']} |",
                    f"| prominent_added | {len(selector_churn['prominent_added'])} |",
                    f"| prominent_removed | {len(selector_churn['prominent_removed'])} |",
                    f"| prominent_retained_count | {selector_churn['prominent_retained_count']} |",
                    f"| churn_count | {selector_churn['churn_count']} |",
                    f"| stability_ratio | {selector_churn['stability_ratio']} |",
                ]
            )
    lines.extend(
        [
            "",
            "## Methodology",
            "",
            snapshot["methodology"]["selection_boundary"],
            "",
            snapshot["methodology"]["lookahead_policy"],
            "",
            snapshot["methodology"]["execution_caveat"],
        ]
    )
    return "\n".join(lines) + "\n"


def write_text(path_value: str | None, value: str) -> None:
    if path_value is None:
        return
    path = pathlib.Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 1") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be an integer >= 1")
    return parsed


def finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a finite number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("must be a finite number")
    return parsed


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-trades-json", action="append", default=[])
    parser.add_argument("--positions-jsonl", action="append", default=[])
    parser.add_argument("--paper-dir", action="append", default=[])
    parser.add_argument(
        "--selector-view-jsonl",
        action="append",
        default=[],
        help=(
            "B2-b selector-view capture JSONL; repeat for multiple files. "
            "Advisory input only and never an eligibility source."
        ),
    )
    parser.add_argument("--run-config-json", default=None)
    parser.add_argument("--static-allowlist", default=None)
    parser.add_argument("--source-cutoff-at", required=True)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--min-closed-positions", type=positive_int, default=10)
    parser.add_argument("--min-avg-net-bps", type=finite_float, default=0.0)
    parser.add_argument("--max-tail-loss-bps", type=finite_float, default=-60.0)
    parser.add_argument("--max-avg-exit-lag-seconds", type=positive_int, default=1800)
    parser.add_argument("--max-selected", type=positive_int, default=8)
    parser.add_argument("--min-score", type=finite_float, default=0.0)
    parser.add_argument("--previous-snapshot-json", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-markdown", default=None)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    trade_rows = load_json_rows(
        [pathlib.Path(value) for value in args.paper_trades_json],
        "paper-trades",
    )
    position_paths = collect_paths(
        args.positions_jsonl,
        args.paper_dir,
        "autopilot_paper_positions_*.jsonl",
    )
    position_rows: list[dict[str, Any]] = []
    for path in position_paths:
        position_rows.extend(read_jsonl_rows(path))
    ingest_counts: dict[str, int] = {}
    events = events_from_paper_trades(trade_rows, ingest_counts) + events_from_positions(
        position_rows, ingest_counts
    )
    selector_ticks = None
    if args.selector_view_jsonl:
        selector_ticks = read_selector_view_ticks(
            [pathlib.Path(value) for value in args.selector_view_jsonl]
        )
    if not events and selector_ticks is None:
        raise SystemExit("no closed paper events available for shadow allowlist")
    static_allowlist = parse_allowlist(args.static_allowlist) | allowlist_from_run_config(
        args.run_config_json
    )
    selector_config = SelectorConfig(
        min_closed_positions=args.min_closed_positions,
        min_avg_net_bps=args.min_avg_net_bps,
        max_tail_loss_bps=args.max_tail_loss_bps,
        max_avg_exit_lag_seconds=args.max_avg_exit_lag_seconds,
        max_selected=args.max_selected,
        min_score=args.min_score,
    )
    previous_snapshot = None
    if args.previous_snapshot_json is not None:
        previous_snapshot = json.loads(
            pathlib.Path(args.previous_snapshot_json).read_text(encoding="utf-8")
        )
        if not isinstance(previous_snapshot, dict):
            raise SystemExit("previous snapshot must be a JSON object")
    snapshot = build_snapshot(
        events=events,
        source_cutoff_at=args.source_cutoff_at,
        selector_config=selector_config,
        static_allowlist=static_allowlist,
        generated_at=args.generated_at,
        ingest_counts=ingest_counts,
        previous_snapshot=previous_snapshot,
        selector_ticks=selector_ticks,
    )
    output = json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False)
    if args.output_json:
        write_text(args.output_json, output + "\n")
    else:
        print(output)
    if args.output_markdown:
        write_text(args.output_markdown, render_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
