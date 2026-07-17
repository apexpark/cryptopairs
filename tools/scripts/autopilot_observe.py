#!/usr/bin/env python3
"""Observe-only 1m autopilot sidecar.

The sidecar records what an autopilot would have considered. It never submits
execution order intents and exposes only read-only HTTP GET calls.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
MODE = "observe_only"
SYSTEM_PAIR_ID = "__SYSTEM__"
SYSTEM_VARIANT = "__NONE__"
ALLOWED_APPROVAL_SOURCES = {
    "LEARNING_SELECTION",
    "LEARNING_ELIGIBLE_OVERRIDE",
}
ALLOWED_DISPATCH_MODES = {"SIMULATE_ACK", "LIVE_KRAKEN"}
SUPPORTED_TIMEFRAME = "1m"


@dataclasses.dataclass(frozen=True)
class QualityWindow:
    rows: int | None = None
    profitable_rate: float | None = None
    avg_net_bps: float | None = None

    def evaluate(
        self,
        min_rows: int | None,
        min_avg_net_bps: float | None,
    ) -> tuple[dict[str, Any], list[str]]:
        reasons: list[str] = []
        if min_rows is not None and (self.rows is None or self.rows < min_rows):
            reasons.append("QUALITY_GATE_MIN_ROWS_FAIL")
        if min_avg_net_bps is not None and (
            self.avg_net_bps is None or self.avg_net_bps < min_avg_net_bps
        ):
            reasons.append("QUALITY_GATE_MIN_AVG_NET_BPS_FAIL")

        return (
            {
                "rows": self.rows,
                "profitable_rate": self.profitable_rate,
                "avg_net_bps": self.avg_net_bps,
                "min_rows": min_rows,
                "min_avg_net_bps": min_avg_net_bps,
                "pass": not reasons,
            },
            reasons,
        )


@dataclasses.dataclass(frozen=True)
class Config:
    enabled: bool = False
    data_service_url: str = "http://127.0.0.1:8080"
    strategy_service_url: str = "http://127.0.0.1:8083"
    execution_service_url: str = "http://127.0.0.1:8082"
    exchange: str = "kraken_futures"
    account_id: str = "primary"
    timeframe: str = "1m"
    interval_seconds: int = 60
    timeout_seconds: int = 10
    max_signal_age_seconds: int = 120
    require_fresh_overlay: bool = True
    allowed_pair_variants: set[tuple[str, str]] = dataclasses.field(default_factory=set)
    min_ready_window_rows: int | None = None
    min_ready_window_avg_net_bps: float | None = None
    quality_windows: dict[tuple[str, str, str], QualityWindow] = dataclasses.field(
        default_factory=dict
    )
    output_dir: Path = Path("artifacts/autopilot_observe")
    loop: bool = False
    capture_selector_view: bool = False
    max_runtime_seconds: int | None = None

    def replace(self, **changes: Any) -> "Config":
        return dataclasses.replace(self, **changes)


class JsonGetClient:
    def get_json(self, url: str, timeout_seconds: int) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"expected object JSON from {url}")
        return payload


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def int_env(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def optional_int_env(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def optional_float_env(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


def _nonneg_int_or_none(value: int | None) -> int | None:
    # quality_window.min_rows is schema minimum 0.
    if value is not None and value < 0:
        raise ValueError("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS must be >= 0")
    return value


def _finite_or_none(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS must be finite")
    return value


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def parse_allowed_pair_variants(value: str | None) -> set[tuple[str, str]]:
    if value is None or not value.strip():
        return set()
    parsed: set[tuple[str, str]] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(
                "AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS entries must be pair_id:selected_variant"
            )
        pair_id, selected_variant = item.split(":", 1)
        pair_id = pair_id.strip()
        selected_variant = selected_variant.strip()
        if not pair_id or not selected_variant:
            raise ValueError(
                "AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS entries must be non-empty"
            )
        parsed.add((pair_id, selected_variant))
    return parsed


def parse_timeframe_config(value: str | None) -> str:
    if value is None:
        return SUPPORTED_TIMEFRAME
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        return SUPPORTED_TIMEFRAME
    if parts == [SUPPORTED_TIMEFRAME]:
        return SUPPORTED_TIMEFRAME
    return ",".join(parts)


def load_quality_windows(path_value: str | None) -> dict[tuple[str, str, str], QualityWindow]:
    if path_value is None or not path_value.strip():
        return {}
    path = Path(path_value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("quality windows JSON must be a list of objects")
    windows: dict[tuple[str, str, str], QualityWindow] = {}
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("quality window rows must be objects")
        pair_id = str(row.get("pair_id", "")).strip()
        timeframe = str(row.get("timeframe", "")).strip()
        selected_variant = str(row.get("selected_variant", "")).strip()
        if not pair_id or not timeframe or not selected_variant:
            raise ValueError("quality window rows require pair_id, timeframe, selected_variant")
        windows[(pair_id, timeframe, selected_variant)] = QualityWindow(
            rows=_optional_int(row.get("rows")),
            profitable_rate=_rate_float(row.get("profitable_rate")),
            avg_net_bps=_optional_float(row.get("avg_net_bps")),
        )
    return windows


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("quality window integer values must be integers")
    if value < 0:
        raise ValueError("quality window integer values must be >= 0")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("quality window numeric values must be numbers")
    try:
        parsed = float(value)
    except OverflowError:
        raise ValueError("quality window numeric values must be finite")
    if not math.isfinite(parsed):
        raise ValueError("quality window numeric values must be finite")
    return parsed


def _rate_float(value: Any) -> float | None:
    parsed = _optional_float(value)
    if parsed is not None and not (0.0 <= parsed <= 1.0):
        raise ValueError("profitable_rate must be within [0, 1]")
    return parsed


def load_config(env: Mapping[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    data_url = source.get(
        "DATA_SERVICE_URL",
        source.get("AUTOPILOT_OBSERVE_DATA_SERVICE_URL", "http://127.0.0.1:8080"),
    )
    strategy_url = source.get(
        "STRATEGY_SERVICE_URL",
        source.get("AUTOPILOT_OBSERVE_STRATEGY_SERVICE_URL", "http://127.0.0.1:8083"),
    )
    execution_url = source.get(
        "EXECUTION_SERVICE_URL",
        source.get("AUTOPILOT_OBSERVE_EXECUTION_SERVICE_URL", "http://127.0.0.1:8082"),
    )
    return Config(
        enabled=bool_env(source.get("AUTOPILOT_OBSERVE_ENABLED"), False),
        data_service_url=normalize_base_url(data_url),
        strategy_service_url=normalize_base_url(strategy_url),
        execution_service_url=normalize_base_url(execution_url),
        exchange=source.get("AUTOPILOT_OBSERVE_EXCHANGE", "kraken_futures"),
        account_id=source.get("AUTOPILOT_OBSERVE_ACCOUNT_ID", "primary"),
        timeframe=parse_timeframe_config(source.get("AUTOPILOT_OBSERVE_TIMEFRAMES")),
        interval_seconds=max(
            1, int_env(source.get("AUTOPILOT_OBSERVE_INTERVAL_SECONDS"), 60)
        ),
        timeout_seconds=max(
            1, int_env(source.get("AUTOPILOT_OBSERVE_TIMEOUT_SECONDS"), 10)
        ),
        max_signal_age_seconds=max(
            1, int_env(source.get("AUTOPILOT_OBSERVE_MAX_SIGNAL_AGE_SECONDS"), 120)
        ),
        require_fresh_overlay=bool_env(
            source.get("AUTOPILOT_OBSERVE_REQUIRE_FRESH_OVERLAY"), True
        ),
        allowed_pair_variants=parse_allowed_pair_variants(
            source.get("AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS")
        ),
        min_ready_window_rows=_nonneg_int_or_none(
            optional_int_env(source.get("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS"))
        ),
        min_ready_window_avg_net_bps=_finite_or_none(
            optional_float_env(source.get("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS"))
        ),
        quality_windows=load_quality_windows(
            source.get("AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON")
        ),
        output_dir=Path(
            source.get("AUTOPILOT_OBSERVE_OUTPUT_DIR", "artifacts/autopilot_observe")
        ),
        loop=bool_env(source.get("AUTOPILOT_OBSERVE_LOOP"), False),
        capture_selector_view=bool_env(
            source.get("AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW"), False
        ),
        max_runtime_seconds=optional_int_env(
            source.get("AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS")
        ),
    )


def build_url(base: str, path: str, query: dict[str, str] | None = None) -> str:
    url = f"{base}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


def fetch_source(
    client: Any,
    url: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        return client.get_json(url, timeout_seconds), "ok", None
    except Exception as error:  # noqa: BLE001
        return None, "error", str(error)


def build_observe_key(row: dict[str, Any], observed_at: dt.datetime) -> str:
    minute_bucket = observed_at.astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
    direction = row.get("direction_hint")
    if not isinstance(direction, str) or not direction:
        direction = "NO_DIRECTION"
    return ":".join(
        [
            "observe-only",
            "v1",
            SUPPORTED_TIMEFRAME,
            str(row.get("pair_id", SYSTEM_PAIR_ID)),
            str(row.get("selected_variant", SYSTEM_VARIANT)),
            direction,
            iso(minute_bucket),
        ]
    )


def source_generated_at(trade_now: dict[str, Any] | None) -> str | None:
    # The v1 record field is format:"date-time"; record it only if it is a
    # valid ISO datetime (with a time component), else null — never a raw
    # non-timestamp string, even on a BLOCKED_STALE_INPUT record.
    if trade_now is None:
        return None
    value = trade_now.get("generated_at")
    if not isinstance(value, str) or "T" not in value or parse_iso(value) is None:
        return None
    return value


def evidence_status(
    data_health: dict[str, Any] | None,
    strategy_health: dict[str, Any] | None,
    statuses: dict[str, str],
    urls: list[str],
) -> dict[str, Any]:
    return {
        "data_health_status": health_status(data_health, statuses["data_health"]),
        "strategy_health_status": health_status(strategy_health, statuses["strategy_health"]),
        "trade_now_status": statuses["trade_now"],
        "trade_now_observability_status": statuses["trade_now_observability"],
        "dispatch_mode_status": statuses["dispatch_mode"],
        "kill_switch_status": statuses["kill_switch"],
        "open_trades_status": statuses["open_trades"],
        "source_urls": urls,
    }


def blocked_before_poll_evidence() -> dict[str, Any]:
    return {
        "data_health_status": "not_requested",
        "strategy_health_status": "not_requested",
        "trade_now_status": "not_requested",
        "trade_now_observability_status": "not_requested",
        "dispatch_mode_status": "not_requested",
        "kill_switch_status": "not_requested",
        "open_trades_status": "not_requested",
        "source_urls": [],
    }


def health_status(payload: dict[str, Any] | None, fetch_status: str) -> str:
    if fetch_status != "ok" or payload is None:
        return "error"
    value = payload.get("status")
    return value if isinstance(value, str) else "unknown"


def candidate_identity_reason(row: dict[str, Any]) -> str | None:
    pair_id = row.get("pair_id")
    selected_variant = row.get("selected_variant")
    if not isinstance(pair_id, str) or not pair_id.strip():
        return "TRADE_NOW_ROW_IDENTITY_MISSING"
    if not isinstance(selected_variant, str) or not selected_variant.strip():
        return "TRADE_NOW_ROW_IDENTITY_MISSING"
    return None


def system_record(
    *,
    observed_at: dt.datetime,
    decision: str,
    reason_codes: list[str],
    trade_now: dict[str, Any] | None,
    dispatch_mode: dict[str, Any] | None,
    kill_switch: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return record_from_row(
        row={
            "pair_id": SYSTEM_PAIR_ID,
            "selected_variant": SYSTEM_VARIANT,
            "timeframe": SUPPORTED_TIMEFRAME,
        },
        observed_at=observed_at,
        decision=decision,
        reason_codes=reason_codes,
        trade_now=trade_now,
        dispatch_mode=dispatch_mode,
        kill_switch=kill_switch,
        conflicting_live_trade=None,
        quality_window=None,
        evidence=evidence,
    )


def record_from_row(
    *,
    row: dict[str, Any],
    observed_at: dt.datetime,
    decision: str,
    reason_codes: list[str],
    trade_now: dict[str, Any] | None,
    dispatch_mode: dict[str, Any] | None,
    kill_switch: dict[str, Any] | None,
    conflicting_live_trade: bool | None,
    quality_window: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "run_id": f"{iso(observed_at)}-1m",
        "observed_at": iso(observed_at),
        "source_generated_at": source_generated_at(trade_now),
        "timeframe": SUPPORTED_TIMEFRAME,
        "pair_id": str(row.get("pair_id", "")),
        "selected_variant": str(row.get("selected_variant", "")),
        "approval_source": nullable_string(row.get("approval_source")),
        "decision_reason_code": nullable_string(row.get("decision_reason_code")),
        "setup_gate_pass": nullable_bool(row.get("setup_gate_pass")),
        "cost_gate_pass": nullable_bool(row.get("cost_gate_pass")),
        "trade_gate_pass": nullable_bool(row.get("trade_gate_pass")),
        "spread_z": nullable_number(row.get("spread_z")),
        "entry_distance_z": nullable_number(row.get("entry_distance_z")),
        "selected_score_z": nullable_number(row.get("selected_score_z")),
        "net_edge_bps": nullable_number(row.get("net_edge_bps")),
        "opportunity_score": nullable_number(row.get("opportunity_score")),
        "learning_overlay_fresh": nullable_bool(
            None if trade_now is None else trade_now.get("learning_overlay_fresh")
        ),
        "learning_overlay_age_seconds": nonneg_number(
            None if trade_now is None else trade_now.get("learning_overlay_age_seconds")
        ),
        "dispatch_mode": schema_dispatch_mode(dispatch_mode),
        "kill_switch_active": nullable_bool(None if kill_switch is None else kill_switch.get("active")),
        "conflicting_live_trade": conflicting_live_trade,
        "quality_window": quality_window,
        "decision": decision,
        "reason_codes": reason_codes,
        "observe_key": build_observe_key(row, observed_at),
        "evidence": evidence,
    }


def nullable_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def nullable_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def is_finite_number(value: Any) -> bool:
    """True for a finite JSON number (not bool). Never raises.

    Python ints cannot be NaN/inf and never overflow, so they are always
    finite — but ``math.isfinite`` on a huge int raises OverflowError, so
    ints are short-circuited before any float conversion.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def nullable_number(value: Any) -> float | int | None:
    # Reject bools and non-finite (NaN/inf) so no record — entry, selector,
    # or system — can ever serialize invalid JSON. Ints are preserved exactly
    # (no lossy float() conversion) and never overflow.
    return value if is_finite_number(value) else None


def nonneg_number(value: Any) -> float | int | None:
    # The v1 schema requires learning_overlay_age_seconds >= 0. A negative or
    # non-finite value is not schema-representable, so record null (the block
    # reason logic reads staleness separately) rather than an invalid record.
    number = nullable_number(value)
    if number is None or number < 0:
        return None
    return number


# The v1 record schema constrains dispatch_mode to this enum (or null).
SCHEMA_DISPATCH_MODES = frozenset({"FAIL_CLOSED", "SIMULATE_ACK", "LIVE_KRAKEN"})


def schema_dispatch_mode(dispatch_mode: dict[str, Any] | None) -> str | None:
    # Record only a schema-valid dispatch mode; an unknown/garbage upstream
    # value is recorded as null (the DISPATCH_MODE_UNKNOWN reason is emitted
    # separately) so the record itself stays schema-valid even fail-closed.
    name = dispatch_mode_value(dispatch_mode)
    return name if name in SCHEMA_DISPATCH_MODES else None


def dispatch_mode_value(dispatch_mode: dict[str, Any] | None) -> str | None:
    if dispatch_mode is None:
        return None
    value = dispatch_mode.get("mode")
    return value if isinstance(value, str) else None


def dispatch_mode_block_reason(dispatch_mode_name: str | None) -> str | None:
    if dispatch_mode_name == "FAIL_CLOSED":
        return "DISPATCH_MODE_FAIL_CLOSED"
    if dispatch_mode_name not in ALLOWED_DISPATCH_MODES:
        return "DISPATCH_MODE_UNKNOWN"
    return None


def kill_switch_block_reason(kill_switch: dict[str, Any] | None) -> str | None:
    if kill_switch is None:
        return "KILL_SWITCH_UNAVAILABLE"
    active = kill_switch.get("active")
    if not isinstance(active, bool):
        return "KILL_SWITCH_ACTIVE_MALFORMED"
    if active:
        return "KILL_SWITCH_ACTIVE"
    return None


def source_reason_codes(
    data_health: dict[str, Any] | None,
    strategy_health: dict[str, Any] | None,
    statuses: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    if health_status(data_health, statuses["data_health"]) != "ok":
        reasons.append("DATA_HEALTH_NOT_OK")
    if health_status(strategy_health, statuses["strategy_health"]) != "ok":
        reasons.append("STRATEGY_HEALTH_NOT_OK")
    for key, reason in [
        ("trade_now", "TRADE_NOW_UNAVAILABLE"),
        ("trade_now_observability", "TRADE_NOW_OBSERVABILITY_UNAVAILABLE"),
        ("dispatch_mode", "DISPATCH_MODE_UNAVAILABLE"),
        ("kill_switch", "KILL_SWITCH_UNAVAILABLE"),
        ("open_trades", "OPEN_TRADES_UNAVAILABLE"),
    ]:
        if statuses[key] != "ok":
            reasons.append(reason)
    return reasons


def quality_for_candidate(
    config: Config,
    row: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    key = (
        str(row.get("pair_id", "")),
        str(row.get("timeframe", config.timeframe)),
        str(row.get("selected_variant", "")),
    )
    window = config.quality_windows.get(key)
    if window is None:
        if config.min_ready_window_rows is None and config.min_ready_window_avg_net_bps is None:
            return None, []
        return (
            {
                "rows": None,
                "profitable_rate": None,
                "avg_net_bps": None,
                "min_rows": config.min_ready_window_rows,
                "min_avg_net_bps": config.min_ready_window_avg_net_bps,
                "pass": False,
            },
            ["QUALITY_GATE_WINDOW_MISSING"],
        )
    return window.evaluate(config.min_ready_window_rows, config.min_ready_window_avg_net_bps)


def open_trades_conflict_status(
    open_trades: dict[str, Any] | None,
    row: dict[str, Any],
) -> tuple[bool | None, str | None]:
    if open_trades is None:
        return None, None
    trades = open_trades.get("trades")
    if not isinstance(trades, list):
        return None, "OPEN_TRADES_MALFORMED"
    pair_id = row.get("pair_id")
    return (
        any(isinstance(trade, dict) and trade.get("pair_id") == pair_id for trade in trades),
        None,
    )


def signal_age_reason(
    config: Config,
    trade_now: dict[str, Any],
    observed_at: dt.datetime,
) -> str | None:
    generated_at = parse_iso(trade_now.get("generated_at"))
    if generated_at is None:
        return "TRADE_NOW_GENERATED_AT_INVALID"
    age_seconds = (observed_at.astimezone(dt.timezone.utc) - generated_at).total_seconds()
    if age_seconds > config.max_signal_age_seconds:
        return "TRADE_NOW_SIGNAL_STALE"
    return None


def evaluate_candidate(
    *,
    config: Config,
    row: dict[str, Any],
    observed_at: dt.datetime,
    seen_keys: set[str],
    trade_now: dict[str, Any],
    dispatch_mode: dict[str, Any] | None,
    kill_switch: dict[str, Any] | None,
    open_trades: dict[str, Any] | None,
    evidence: dict[str, Any],
    source_reasons: list[str],
) -> dict[str, Any]:
    reasons: list[str] = []
    decision = "OBSERVED_ENTRY_CANDIDATE"

    quality_window, quality_reasons = quality_for_candidate(config, row)
    open_trades_conflict, open_trades_reason = open_trades_conflict_status(open_trades, row)
    conflicting_live_trade = bool(row.get("open_live_trade")) or bool(open_trades_conflict)
    observe_key = build_observe_key(row, observed_at)

    stale_reason = signal_age_reason(config, trade_now, observed_at)
    dispatch_mode_name = dispatch_mode_value(dispatch_mode)
    dispatch_reason = dispatch_mode_block_reason(dispatch_mode_name)
    kill_switch_reason = kill_switch_block_reason(kill_switch)
    row_timeframe = str(row.get("timeframe", SUPPORTED_TIMEFRAME))

    if source_reasons:
        decision = "BLOCKED_SOURCE_UNAVAILABLE"
        reasons.extend(source_reasons)
    elif row_timeframe != SUPPORTED_TIMEFRAME:
        decision = "BLOCKED_TIMEFRAME_OUT_OF_SCOPE"
        reasons.append("ROW_TIMEFRAME_NOT_1M")
    elif stale_reason is not None:
        decision = "BLOCKED_STALE_INPUT"
        reasons.append(stale_reason)
    elif kill_switch_reason is not None:
        decision = "BLOCKED_KILL_SWITCH"
        reasons.append(kill_switch_reason)
    elif dispatch_reason is not None:
        decision = "BLOCKED_DISPATCH_MODE"
        reasons.append(dispatch_reason)
    elif open_trades_reason is not None:
        decision = "BLOCKED_OPEN_LIVE_TRADE"
        reasons.append(open_trades_reason)
    elif conflicting_live_trade:
        decision = "BLOCKED_OPEN_LIVE_TRADE"
        reasons.append("CONFLICTING_LIVE_TRADE")
    elif (str(row.get("pair_id", "")), str(row.get("selected_variant", ""))) not in config.allowed_pair_variants:
        decision = "BLOCKED_NOT_ALLOWLISTED"
        reasons.append("PAIR_VARIANT_NOT_ALLOWLISTED")
    elif not all(
        row.get(field) is True
        for field in ("setup_gate_pass", "cost_gate_pass", "trade_gate_pass")
    ):
        decision = "BLOCKED_LIVE_GATE"
        reasons.append("TRADE_NOW_LIVE_GATE_FAIL")
    elif str(row.get("approval_source", "")) not in ALLOWED_APPROVAL_SOURCES:
        decision = "BLOCKED_LIVE_GATE"
        reasons.append("APPROVAL_SOURCE_NOT_ALLOWED")
    elif config.require_fresh_overlay and trade_now.get("learning_overlay_fresh") is not True:
        decision = "BLOCKED_LEARNING_OVERLAY_STALE"
        reasons.append("LEARNING_OVERLAY_NOT_FRESH")
    elif quality_reasons:
        decision = "BLOCKED_QUALITY_GATE"
        reasons.extend(quality_reasons)
    elif observe_key in seen_keys:
        decision = "BLOCKED_DUPLICATE_OBSERVATION"
        reasons.append("OBSERVE_KEY_ALREADY_SEEN")
    else:
        reasons.extend(
            [
                "TRADE_NOW_LIVE_GATES_PASS",
                "ALLOWLIST_PAIR_VARIANT",
                "QUALITY_GATE_PASS",
            ]
        )
        seen_keys.add(observe_key)

    return record_from_row(
        row=row,
        observed_at=observed_at,
        decision=decision,
        reason_codes=reasons,
        trade_now=trade_now,
        dispatch_mode=dispatch_mode,
        kill_switch=kill_switch,
        conflicting_live_trade=conflicting_live_trade,
        quality_window=quality_window,
        evidence=evidence,
    )


SELECTOR_VIEW_SCHEMA_VERSION = 2
# Capture profile of the per-tick completeness record (the "tick manifest").
# Distinct from the per-candidate "selector_view" profile so a manifest is never
# miscounted as an observed candidate.
SELECTOR_VIEW_TICK_PROFILE = "selector_view_tick"


class _SelectorViewRowMalformed(Exception):
    """Internal sentinel: a cue row cannot be faithfully recorded; omit it."""


_MISSING = object()


def selector_view_freshness_reason(
    config: Config, trade_now: dict[str, Any], observed_at: dt.datetime
) -> str | None:
    """Reject an invalid, stale, OR future cue timestamp.

    Unlike the entry path's one-sided staleness check, a future generated_at
    (clock skew / bad data) is also rejected — a negative age must not be
    recorded as a fresh selector observation.
    """
    raw = trade_now.get("generated_at")
    # Require a full ISO datetime with the 'T' date/time separator (the real
    # cue format, e.g. "2026-06-13T05:29:57Z"). A date-only value, a
    # date+offset with no time, or a ":"-containing-but-timeless string parses
    # to something misleading and must not read as fresh.
    if not isinstance(raw, str) or "T" not in raw:
        return "TRADE_NOW_GENERATED_AT_INVALID"
    generated_at = parse_iso(raw)
    if generated_at is None:
        return "TRADE_NOW_GENERATED_AT_INVALID"
    age_seconds = (observed_at.astimezone(dt.timezone.utc) - generated_at).total_seconds()
    if age_seconds > config.max_signal_age_seconds:
        return "TRADE_NOW_SIGNAL_STALE"
    if age_seconds < -config.max_signal_age_seconds:
        return "TRADE_NOW_SIGNAL_FUTURE"
    return None




CUE_BUCKETS = (
    ("tradable_now", "TRADE_NOW"),
    ("watchlist", "WATCHLIST"),
    ("excluded", "EXCLUDED"),
)
# decisionRowBase passthrough fields recorded verbatim as stated-view
# observations. These are the selector's own stated figures, never outcomes.
SELECTOR_VIEW_PASSTHROUGH = (
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
    "selected_score_z",
    "entry_distance_z",
    "approval_source",
)


def selector_view_observe_key(
    row: dict[str, Any], cue_bucket: str, observed_at: dt.datetime
) -> str:
    minute_bucket = observed_at.astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
    direction = row.get("direction_hint")
    if not isinstance(direction, str) or not direction:
        direction = "NO_DIRECTION"
    return ":".join(
        [
            "selector-view",
            "v2",
            SUPPORTED_TIMEFRAME,
            str(row.get("pair_id", SYSTEM_PAIR_ID)),
            str(row.get("selected_variant", SYSTEM_VARIANT)),
            direction,
            cue_bucket,
            iso(minute_bucket),
        ]
    )


def _finite_number(value: Any) -> float | int:
    """A finite JSON number (not bool); omit the row otherwise.

    The value is preserved as-is — an int stays an int (no lossy float()
    conversion that would silently round values above 2**53) — and ints
    never overflow, so no OverflowError is possible.
    """
    if not is_finite_number(value):
        raise _SelectorViewRowMalformed
    return value


def _nullable_finite_number(value: Any) -> float | int | None:
    if value is None:
        return None
    return _finite_number(value)


ALLOWED_CUE_BUCKETS = frozenset({"TRADE_NOW", "WATCHLIST", "EXCLUDED"})


def _nullable_cue_bucket(value: Any) -> str | None:
    # decision_bucket is enum-constrained (or null) in the v2 selector-view
    # schema, but the schema does NOT require it to equal cue_bucket. isinstance
    # guard first so an unhashable list/dict omits the row rather than raising
    # on the `in frozenset` test; a present value must be a valid enum member.
    # A value that legitimately differs from cue_bucket is recorded faithfully
    # (both the source bucket and the selector's stated bucket are evidence).
    if value is None:
        return None
    if not isinstance(value, str) or value not in ALLOWED_CUE_BUCKETS:
        raise _SelectorViewRowMalformed
    return value


def _required_bool(value: Any) -> bool:
    # Strict: only a real JSON bool. "false"/0/None are NOT coerced.
    if not isinstance(value, bool):
        raise _SelectorViewRowMalformed
    return value


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _SelectorViewRowMalformed
    return value or None


def _required_str_list(value: Any) -> list[str]:
    # decisionRowBase requires rationale_codes as a non-null array of strings.
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _SelectorViewRowMalformed
    return list(value)


def _nullable_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    return _required_str_list(value)


def _nullable_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _SelectorViewRowMalformed
    return value


def selector_view_record(
    *,
    row: dict[str, Any],
    cue_bucket: str,
    observed_at: dt.datetime,
    source_generated: str,
) -> dict[str, Any]:
    """Faithfully transcribe one cue row into a selector-view record.

    Strict, all-or-nothing: every field must already be the correct JSON type
    the v2 contract requires. Any wrong-typed field (a bool-as-string, a
    non-finite or overflowing number, a non-string in a code list, an
    unexpected timeframe) raises _SelectorViewRowMalformed so the caller omits
    the row. Nothing is coerced or fabricated.
    """
    # Fabrication guards: timeframe is written as the constant "1m", so an
    # absent or non-1m source timeframe must omit the row rather than invent
    # one; rationale_codes is a required non-null array (below), so an absent
    # or null value omits rather than fabricating []. Every stated number/bool
    # is strictly validated by its helper and omits the row on any wrong type.
    if row.get("timeframe") != SUPPORTED_TIMEFRAME:
        raise _SelectorViewRowMalformed

    record: dict[str, Any] = {
        "schema_version": SELECTOR_VIEW_SCHEMA_VERSION,
        "mode": "observe_only",
        "capture_profile": "selector_view",
        "run_id": iso(observed_at),
        "observed_at": iso(observed_at),
        "source_generated_at": source_generated,
        "timeframe": SUPPORTED_TIMEFRAME,
        "pair_id": row["pair_id"],
        "selected_variant": row["selected_variant"],
        "cue_bucket": cue_bucket,
        "direction_hint": _nullable_str(row.get("direction_hint")),
        "decision": "SELECTOR_VIEW_OBSERVED",
        "decision_reason_code": _nullable_str(row.get("decision_reason_code")),
        "blocked_reason_code": _nullable_str(row.get("blocked_reason_code")),
        "watch_reason_code": _nullable_str(row.get("watch_reason_code")),
        "rationale_codes": _required_str_list(row.get("rationale_codes")),
        "setup_gate_pass": _required_bool(row.get("setup_gate_pass")),
        "cost_gate_pass": _required_bool(row.get("cost_gate_pass")),
        "trade_gate_pass": _required_bool(row.get("trade_gate_pass")),
        "spread_z": _finite_number(row.get("spread_z")),
        "net_edge_bps": _finite_number(row.get("net_edge_bps")),
        "opportunity_score": _finite_number(row.get("opportunity_score")),
        "observe_key": selector_view_observe_key(row, cue_bucket, observed_at),
    }
    bool_fields = {
        "open_live_trade",
        "requires_fresh_overlay",
        "learning_trade_eligible",
        "learning_selection_selected",
        "legacy_fallback_active",
    }
    num_fields = {
        "portfolio_target_weight",
        "portfolio_risk_contribution",
        "selected_score_z",
        "entry_distance_z",
    }
    for field_name in SELECTOR_VIEW_PASSTHROUGH:
        raw = row.get(field_name)
        if field_name == "decision_bucket":
            record[field_name] = _nullable_cue_bucket(raw)
        elif field_name in bool_fields:
            record[field_name] = None if raw is None else _required_bool(raw)
        elif field_name == "expected_hold_bars":
            record[field_name] = _nullable_int(raw)
        elif field_name in num_fields:
            record[field_name] = _nullable_finite_number(raw)
        elif field_name == "learning_reason_codes":
            record[field_name] = _nullable_str_list(raw)
        else:
            record[field_name] = _nullable_str(raw)
    return record


def selector_view_tick_record(
    *,
    observed_at: dt.datetime,
    source_generated: str,
    rows_per_bucket: dict[str, int],
) -> dict[str, Any]:
    """Record that one selector-view tick was captured completely.

    Emitted once per successfully captured tick, immediately *before* that
    tick's rows. It is the positive marker of a completed capture, and it
    exists because absence of rows is otherwise ambiguous: a tick where the
    selector legitimately returned an empty universe writes no rows at all,
    which on disk is indistinguishable from a tick that never ran (host down,
    process stopped, loop not started). A consumer (B2-c) reads a tick as
    captured only if this record is present, and reads an empty universe as a
    real observation — not as missing data — only on the strength of it.

    ``rows_per_bucket`` states how many rows follow for each cue bucket, so a
    truncated tail (e.g. a hard kill mid-append) is detectable as a shortfall
    against the stated counts rather than read as a smaller universe. Because
    the manifest is written first, truncation can only ever remove rows the
    manifest already accounted for.

    A refused tick emits no manifest — only the ``BLOCKED_*`` system record —
    so "captured" and "refused" stay mutually exclusive.
    """
    return {
        "schema_version": SELECTOR_VIEW_SCHEMA_VERSION,
        "mode": MODE,
        "capture_profile": SELECTOR_VIEW_TICK_PROFILE,
        "run_id": iso(observed_at),
        "observed_at": iso(observed_at),
        "source_generated_at": source_generated,
        "timeframe": SUPPORTED_TIMEFRAME,
        "decision": "SELECTOR_VIEW_TICK_CAPTURED",
        "recorded_rows": sum(rows_per_bucket.values()),
        "rows_per_bucket": rows_per_bucket,
    }


def selector_view_records(
    *,
    config: Config,
    trade_now: dict[str, Any],
    observed_at: dt.datetime,
    dispatch_mode: dict[str, Any] | None,
    kill_switch: dict[str, Any] | None,
    evidence: dict[str, Any],
    source_reasons: list[str],
) -> list[dict[str, Any]]:
    """Emit one selector-view row per candidate across all cue buckets.

    These are observations of the champion/challenger selector's stated view,
    never entry candidates and never outcomes. Nothing is coerced or fabricated.

    Completeness is all-or-nothing: a tick either records every candidate the
    endpoint returned, or records no selector rows at all. A captured tick is
    led by a ``selector_view_tick`` manifest stating the per-bucket row counts
    that follow (see ``selector_view_tick_record``), so a consumer can tell a
    captured tick from a tick that never ran — including the all-empty universe,
    which is a valid observation that emits a manifest and zero rows. A whole
    tick is refused (a single system record, no manifest and no selector rows)
    whenever the view cannot be trusted as current *or complete* — mirroring the
    entry path's fail-closed posture so a stale, degraded, or partial cue
    response is never recorded as a fresh, trustworthy observation (a silently
    shrunken universe reads downstream as false churn, and a silently
    under-recorded bucket reads as false stability):
      - degraded source health / another read-only fetch failed → the same
        ``source_reasons`` the entry path computes → ``BLOCKED_SOURCE_UNAVAILABLE``;
      - invalid/stale/future ``generated_at`` (outside ±``max_signal_age_seconds``)
        → ``BLOCKED_STALE_INPUT`` / ``BLOCKED_MALFORMED_RESPONSE``;
      - ANY of the three cue buckets absent or not-a-list → the whole tick is
        refused with a single ``BLOCKED_MALFORMED_RESPONSE`` and NO selector
        rows, so a partial universe can never be mistaken for real churn;
      - ANY returned candidate that is not an object, fails identity, or cannot
        be faithfully transcribed (wrong-typed, non-finite, or overflowing
        field) → the whole tick is refused with ``BLOCKED_MALFORMED_RESPONSE``
        and bounded ``SELECTOR_VIEW_ROW_{NOT_OBJECT,IDENTITY_INVALID,MALFORMED}
        :<bucket>`` reason codes. Such a row is never dropped while its
        neighbours are emitted, so B2-c cannot mistake an incomplete tick for a
        complete one. An empty bucket is complete and valid; only candidates the
        endpoint actually returned can make a tick incomplete.
    """

    def refuse(decision: str, reasons: list[str]) -> list[dict[str, Any]]:
        return [
            system_record(
                observed_at=observed_at,
                decision=decision,
                reason_codes=reasons,
                trade_now=trade_now,
                dispatch_mode=dispatch_mode,
                kill_switch=kill_switch,
                evidence=evidence,
            )
        ]

    if source_reasons:
        return refuse("BLOCKED_SOURCE_UNAVAILABLE", source_reasons)
    freshness_reason = selector_view_freshness_reason(config, trade_now, observed_at)
    if freshness_reason is not None:
        decision = (
            "BLOCKED_MALFORMED_RESPONSE"
            if freshness_reason == "TRADE_NOW_GENERATED_AT_INVALID"
            else "BLOCKED_STALE_INPUT"
        )
        return refuse(decision, [freshness_reason])
    # Whole-tick bucket validation up front: the endpoint must return all three
    # buckets as lists. Any missing or non-list bucket makes the universe
    # partial, so refuse the entire tick rather than record a partial universe
    # (which reads downstream as false churn/stability).
    for endpoint_key, _cue_bucket in CUE_BUCKETS:
        bucket = trade_now.get(endpoint_key, _MISSING)
        if bucket is _MISSING:
            return refuse("BLOCKED_MALFORMED_RESPONSE", [f"CUE_BUCKET_MISSING:{endpoint_key}"])
        if not isinstance(bucket, list):
            return refuse("BLOCKED_MALFORMED_RESPONSE", [f"CUE_BUCKET_NOT_LIST:{endpoint_key}"])

    # Non-null past this point only because the freshness gate above already
    # rejected every value source_generated_at() would reject: the two apply the
    # same str / "T" / parse_iso test. Both the selector rows and the tick
    # manifest declare source_generated_at as a required non-nullable string, so
    # loosening either predicate without the other would emit records that
    # violate their own schema branch. Keep the two in step.
    #
    # Normalized, not passed through raw: the manifest branch declares
    # format:"date-time" (RFC 3339), but the gate's predicate is
    # datetime.fromisoformat, which is strictly *wider* — it accepts values RFC
    # 3339 rejects, e.g. a naive "2026-06-13T05:29:57" with no offset, ISO basic
    # "20260613T052957", or a one-digit fraction. Recording those raw emits a
    # manifest that fails its own branch. parse_iso has already resolved the
    # instant (reading naive as UTC), so iso() restates that exact instant in the
    # form the contract declares. Scoped to the selector-view path deliberately:
    # the shared source_generated_at() also feeds entry rows on the narrow
    # paper-feeding path, which this slice must leave byte-identical.
    parsed_source = parse_iso(source_generated_at(trade_now))
    if parsed_source is None:
        # Unreachable: the freshness gate above rejects every value that would
        # land here. Fail closed rather than emit an out-of-contract manifest if
        # that ever stops being true.
        return refuse("BLOCKED_STALE_INPUT", ["CUE_GENERATED_AT_UNPARSEABLE"])
    source_generated = iso(parsed_source)
    records: list[dict[str, Any]] = []
    # Whole-tick completeness accounting. A candidate the endpoint returned but
    # that cannot be faithfully transcribed makes the universe partial, exactly
    # like a missing bucket above, so it refuses the tick rather than silently
    # shrinking the recorded universe. Reason codes stay bounded (3 causes x 3
    # buckets = 9 max) and never interpolate row-supplied values such as
    # pair_id, which would be unbounded and attacker-influenced.
    incomplete_reasons: set[str] = set()
    omitted_per_bucket: dict[str, int] = {}
    rows_per_bucket: dict[str, int] = {cue_bucket: 0 for _key, cue_bucket in CUE_BUCKETS}

    def omit(endpoint_key: str, cause: str) -> None:
        incomplete_reasons.add(f"SELECTOR_VIEW_ROW_{cause}:{endpoint_key}")
        omitted_per_bucket[endpoint_key] = omitted_per_bucket.get(endpoint_key, 0) + 1

    for endpoint_key, cue_bucket in CUE_BUCKETS:
        for row in trade_now[endpoint_key]:  # each bucket validated as a list above
            if not isinstance(row, dict):
                omit(endpoint_key, "NOT_OBJECT")
                continue
            if candidate_identity_reason(row) is not None:
                omit(endpoint_key, "IDENTITY_INVALID")
                continue
            try:
                records.append(
                    selector_view_record(
                        row=row,
                        cue_bucket=cue_bucket,
                        observed_at=observed_at,
                        source_generated=source_generated,
                    )
                )
            except _SelectorViewRowMalformed:
                omit(endpoint_key, "MALFORMED")
                continue
            rows_per_bucket[cue_bucket] += 1

    if incomplete_reasons:
        # Diagnostic first (per-bucket counts are useful for locating the bad
        # rows), then refuse the whole tick. The JSONL artifact carries the
        # refusal, so an incomplete universe can never reach B2-c as if it were
        # a complete one — no partial tick is ever emitted alongside good rows.
        print(
            json.dumps(
                {
                    "observed_at": iso(observed_at),
                    "selector_view_tick_refused": "INCOMPLETE_UNIVERSE",
                    "omitted_per_bucket": omitted_per_bucket,
                    "would_have_recorded": len(records),
                    "reason_codes": sorted(incomplete_reasons),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return refuse("BLOCKED_MALFORMED_RESPONSE", sorted(incomplete_reasons))
    # Complete tick. The manifest leads so that it accounts for every row that
    # follows; an all-empty universe yields a manifest and no rows, which is a
    # positively recorded observation rather than the silence of a missed tick.
    return [
        selector_view_tick_record(
            observed_at=observed_at,
            source_generated=source_generated,
            rows_per_bucket=rows_per_bucket,
        ),
        *records,
    ]


def run_once(
    config: Config,
    *,
    client: Any | None = None,
    observed_at: dt.datetime | None = None,
    seen_keys: set[str] | None = None,
    stop: StopSignal | None = None,
) -> list[dict[str, Any]] | None:
    """Run one observation tick and return its records.

    Returns None only when ``stop`` is supplied and a stop was requested while
    polling, meaning the tick was abandoned before anything was recorded. With
    no ``stop`` (the default, and every non-loop caller) this always returns a
    list.
    """
    if not config.enabled:
        return []

    if config.timeframe != SUPPORTED_TIMEFRAME:
        now_value = utc_now() if observed_at is None else observed_at
        return [
            system_record(
                observed_at=now_value,
                decision="BLOCKED_TIMEFRAME_OUT_OF_SCOPE",
                reason_codes=["CONFIG_TIMEFRAME_NOT_1M"],
                trade_now=None,
                dispatch_mode=None,
                kill_switch=None,
                evidence=blocked_before_poll_evidence(),
            )
        ]

    active_client = JsonGetClient() if client is None else client
    now_value = utc_now() if observed_at is None else observed_at
    seen = set() if seen_keys is None else seen_keys

    urls = {
        "data_health": build_url(config.data_service_url, "/health"),
        "strategy_health": build_url(config.strategy_service_url, "/health"),
        "trade_now": build_url(
            config.strategy_service_url,
            "/v1/strategy/pairs/trade-now",
            {"timeframe": config.timeframe},
        ),
        "trade_now_observability": build_url(
            config.strategy_service_url, "/v1/strategy/observability/trade-now"
        ),
        "dispatch_mode": build_url(config.execution_service_url, "/v1/execution/dispatch-mode"),
        "kill_switch": build_url(config.execution_service_url, "/v1/execution/kill-switch"),
        "open_trades": build_url(
            config.execution_service_url,
            "/v1/execution/portfolio/open-trades",
            {"exchange": config.exchange, "account_id": config.account_id},
        ),
    }

    payloads: dict[str, dict[str, Any] | None] = {}
    statuses: dict[str, str] = {}
    for key, url in urls.items():
        # A tick makes seven sequential fetches, each able to burn the full
        # timeout against an unresponsive endpoint. Waiting out all of them
        # before honouring a stop would take far longer than the runbook's
        # escalation gate and push the operator toward the `kill -9` this
        # handling exists to avoid — and the degraded case that makes the tick
        # slow is exactly when a stop is most likely. Nothing is written until
        # the tick completes, so a stop here abandons the tick outright: no
        # partial view is recorded, and the tick reads downstream as missing,
        # which it is. Only a stop during the append needs the tick to finish.
        if stop is not None and stop.requested:
            return None
        payload, status, _error = fetch_source(active_client, url, config.timeout_seconds)
        payloads[key] = payload
        statuses[key] = status

    evidence = evidence_status(
        payloads["data_health"],
        payloads["strategy_health"],
        statuses,
        list(urls.values()),
    )
    source_reasons = source_reason_codes(
        payloads["data_health"],
        payloads["strategy_health"],
        statuses,
    )

    trade_now = payloads["trade_now"]
    if trade_now is None:
        return [
            system_record(
                observed_at=now_value,
                decision="BLOCKED_SOURCE_UNAVAILABLE",
                reason_codes=source_reasons or ["TRADE_NOW_UNAVAILABLE"],
                trade_now=None,
                dispatch_mode=payloads["dispatch_mode"],
                kill_switch=payloads["kill_switch"],
                evidence=evidence,
            )
        ]

    if config.capture_selector_view:
        # Pure observational mode: emit selector-view rows across all three cue
        # buckets and nothing else. The entry-candidate path (below) is not
        # invoked, so a dedicated selector-view run produces a clean,
        # single-purpose artifact and does not double the record volume with
        # uniformly-blocked entry rows. Fail-closed: the source-unavailable
        # system record above already fired if trade_now was absent; here
        # trade_now is a dict, and selector_view_records applies the same
        # source-health and staleness gates the entry path uses, then refuses
        # the whole tick — recording no selector rows at all — if the view is
        # degraded, stale, or incomplete in any way.
        return selector_view_records(
            config=config,
            trade_now=trade_now,
            observed_at=now_value,
            dispatch_mode=payloads["dispatch_mode"],
            kill_switch=payloads["kill_switch"],
            evidence=evidence,
            source_reasons=source_reasons,
        )

    tradable_now = trade_now.get("tradable_now")
    if not isinstance(tradable_now, list):
        return [
            system_record(
                observed_at=now_value,
                decision="BLOCKED_MALFORMED_RESPONSE",
                reason_codes=["TRADE_NOW_TRADABLE_NOW_NOT_LIST"],
                trade_now=trade_now,
                dispatch_mode=payloads["dispatch_mode"],
                kill_switch=payloads["kill_switch"],
                evidence=evidence,
            )
        ]

    records = []
    for row in tradable_now:
        if not isinstance(row, dict):
            records.append(
                system_record(
                    observed_at=now_value,
                    decision="BLOCKED_MALFORMED_RESPONSE",
                    reason_codes=["TRADE_NOW_ROW_NOT_OBJECT"],
                    trade_now=trade_now,
                    dispatch_mode=payloads["dispatch_mode"],
                    kill_switch=payloads["kill_switch"],
                    evidence=evidence,
                )
            )
            continue
        identity_reason = candidate_identity_reason(row)
        if identity_reason is not None:
            records.append(
                system_record(
                    observed_at=now_value,
                    decision="BLOCKED_MALFORMED_RESPONSE",
                    reason_codes=[identity_reason],
                    trade_now=trade_now,
                    dispatch_mode=payloads["dispatch_mode"],
                    kill_switch=payloads["kill_switch"],
                    evidence=evidence,
                )
            )
            continue
        records.append(
            evaluate_candidate(
                config=config,
                row=row,
                observed_at=now_value,
                seen_keys=seen,
                trade_now=trade_now,
                dispatch_mode=payloads["dispatch_mode"],
                kill_switch=payloads["kill_switch"],
                open_trades=payloads["open_trades"],
                evidence=evidence,
                source_reasons=source_reasons,
            )
        )
    return records


def existing_observed_candidate_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            observe_key = payload.get("observe_key")
            if (
                payload.get("decision") == "OBSERVED_ENTRY_CANDIDATE"
                and isinstance(observe_key, str)
                and observe_key
            ):
                keys.add(observe_key)
    return keys


def apply_persisted_duplicate_blocks(
    records: list[dict[str, Any]],
    existing_keys: set[str],
) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for record in records:
        next_record = dict(record)
        observe_key = next_record.get("observe_key")
        if next_record.get("decision") == "OBSERVED_ENTRY_CANDIDATE" and isinstance(
            observe_key, str
        ):
            if observe_key in existing_keys:
                next_record["decision"] = "BLOCKED_DUPLICATE_OBSERVATION"
                reason_codes = next_record.get("reason_codes")
                reasons = list(reason_codes) if isinstance(reason_codes, list) else []
                if "OBSERVE_KEY_ALREADY_WRITTEN" not in reasons:
                    reasons.append("OBSERVE_KEY_ALREADY_WRITTEN")
                next_record["reason_codes"] = reasons
            else:
                existing_keys.add(observe_key)
        written.append(next_record)
    return written


def json_safe(value: Any) -> Any:
    """Recursively replace any non-finite float (NaN/inf) with None.

    A final, whole-record guarantee that the writer can never emit invalid
    JSON, even if a non-finite value is nested somewhere a per-field helper
    did not reach. Applied to every record before serialization; combined
    with ``allow_nan=False`` this makes an invalid write impossible without
    ever crashing the tick (the sanitize runs first).
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def write_records(records: list[dict[str, Any]], output_dir: Path, observed_at: dt.datetime) -> Path:
    day = observed_at.strftime("%Y%m%d")
    target_dir = output_dir / day
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"autopilot_observe_{day}.jsonl"
    records_to_write = apply_persisted_duplicate_blocks(
        records,
        existing_observed_candidate_keys(path),
    )
    records[:] = records_to_write
    with path.open("a", encoding="utf-8") as handle:
        for record in records_to_write:
            handle.write(
                json.dumps(
                    json_safe(record), sort_keys=True, separators=(",", ":"), allow_nan=False
                )
                + "\n"
            )
    return path


class StopSignal:
    """Records a stop request so the loop exits at a checkpoint, never mid-append.

    Installed only by a selector-view loop (the narrow paper-feeding loop is
    required to keep its pre-slice signal behaviour).

    What this does and does not promise depends on when the signal lands:

    - **During polling, with a fetch boundary still ahead**: the tick is
      abandoned at that boundary and nothing is written. No manifest, no rows —
      on disk that tick simply never happened, which is the same thing a
      consumer reads for a tick that never ran.
    - **During the final fetch**: the flag is only tested at the *top* of each of
      the seven fetches, so a signal arriving during the last one has no boundary
      left to be honoured at. That tick completes and is appended like any other
      — the right outcome, since its data is whole by then.
    - **During or after record construction**, including mid-append inside
      ``write_records``: the append completes and the tick is durable.

    So it is not the case that every in-flight tick finishes, nor that every
    signal during polling abandons one. The guarantee is narrower and more
    useful: no tick is ever left half-written — each is either fully appended or
    never written at all. Without a handler, the default SIGTERM disposition
    terminates the process immediately, which can land in the middle of the
    append and leave a truncated final line. Setting a flag instead lets the
    interpreter deliver the signal between bytecodes, run this handler, and
    resume the append; the loop then exits at its own checkpoint with the file
    closed.
    """

    def __init__(self) -> None:
        self.requested = False
        self.signum: int | None = None

    def request(self, signum: int, _frame: Any = None) -> None:
        if not self.requested:
            self.requested = True
            self.signum = signum

    def install(self) -> None:
        # SIGINT is handled the same way: the default KeyboardInterrupt is
        # raised at an arbitrary bytecode and can abort an in-flight append
        # just as SIGTERM can. A disposition already set to SIG_IGN is left
        # alone — a shell backgrounding this run (`nohup ... &`) hands it an
        # ignored SIGINT deliberately, and re-arming it here would make the run
        # newly killable by a signal its launcher meant it to survive.
        for signum in (signal.SIGTERM, signal.SIGINT):
            if signal.getsignal(signum) is signal.SIG_IGN:
                continue
            signal.signal(signum, self.request)


def sleep_until_interval_or_stop(seconds: float, stop: StopSignal) -> None:
    """Sleep, but notice a stop request promptly.

    PEP 475 resumes an interrupted ``time.sleep`` for the remaining duration
    once the handler returns, so a single long sleep would swallow a stop for
    up to a full interval (300s in the selector-view runbook). Sleeping in short
    slices keeps the stop responsive without busy-waiting.
    """
    deadline = time.monotonic() + seconds
    while not stop.requested:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.5, remaining))


# A selector-view run and the narrow paper-feeding run are both launched as
# `python3 tools/scripts/autopilot_observe.py` with their configuration supplied
# by the environment, so a bare `autopilot_observe.py` match in `ps` output
# cannot tell the two apart and can send a stop signal to the wrong run. The
# selector-view runbook therefore passes the explicit --capture-selector-view
# flag, which puts the distinguishing token in the process's own argv.
SELECTOR_VIEW_FLAG = "--capture-selector-view"
OBSERVE_SCRIPT_NAME = "autopilot_observe.py"


def selector_view_argv_matches(argv: list[str]) -> bool:
    """True for an argv that is this script run in selector-view capture.

    Establishes *kind*, not *identity*. A True here means the process is **a**
    selector-view capture — decisively not the narrow paper-feeding run, which is
    what this check exists to separate. It does **not** mean the process is *the*
    run a caller intended to stop: a second concurrent capture, or a recycled PID
    now held by a different capture, matches just as well. **Nothing establishes
    identity today, including the caller's PID file** — a PID file records a PID,
    which is the very thing that gets recycled, so it identifies a run only while
    that process is known to have been alive continuously. There is no procedural
    substitute either: a sequential recycle (the first capture exits, a later one
    is handed its PID) defeats every "one at a time" rule, because the two never
    coexist. Establishing identity is follow-up OBS-3; until it lands, the runbook
    treats this check as screening only and an early stop needs explicit Operator
    authorization.

    Token-exact, never a substring test: it gates a signal, so a false positive
    stops the wrong process. The script must be the program actually being run —
    executed directly, or as the argument to a python interpreter (any
    interpreter flags in between are fine) — so an unrelated process that merely
    *mentions* both tokens is not mistaken for a capture. A command that
    reaches selector-view capture only via the environment returns False: the
    caller then refuses to signal rather than guessing.
    """
    if not argv or SELECTOR_VIEW_FLAG not in argv:
        return False

    def is_this_script(token: str) -> bool:
        return token == OBSERVE_SCRIPT_NAME or token.endswith("/" + OBSERVE_SCRIPT_NAME)

    if is_this_script(argv[0]):
        return True  # executed directly via its shebang
    if os.path.basename(argv[0]).startswith("python"):
        for token in argv[1:]:
            if is_this_script(token):
                return True
            if not token.startswith("-"):
                return False  # first non-flag argument is something else
    return False


def process_argv(pid: int) -> tuple[list[str] | None, bool]:
    """Exact argv of ``pid`` plus whether it is trustworthy for identity.

    ``/proc/<pid>/cmdline`` is NUL-separated, so on the Linux deployment host
    this recovers argv exactly. Elsewhere the only portable source is ``ps``,
    which renders argv space-joined and unquoted — the original token
    boundaries are unrecoverable, so an argument *value* containing the
    selector-view flag would be re-split into a token that looks like the flag
    itself. That is a false positive on a check that gates a kill, so the ps
    path is reported as inexact and refused rather than trusted.
    """
    cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = cmdline.read_bytes()
    except OSError:
        pass  # not Linux, or no such process — fall through to ps
    else:
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        return (argv or None), True

    try:
        completed = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None, False
    if completed.returncode != 0:
        return None, False
    command = completed.stdout.strip()
    if not command:
        return None, False
    try:
        return shlex.split(command), False
    except ValueError:
        return None, False


def verify_selector_view_pid(pid: int) -> tuple[bool, dict[str, Any]]:
    """Confirm ``pid`` is a selector-view capture before anyone signals it."""
    argv, exact = process_argv(pid)
    if argv is None:
        return False, {
            "pid": pid,
            "verdict": "NO_SUCH_PROCESS",
            "safe_to_signal": False,
            "detail": "No process with this PID; the PID file is stale. Do not signal it.",
        }
    command = " ".join(argv)
    if not selector_view_argv_matches(argv):
        return False, {
            "pid": pid,
            "verdict": "NOT_SELECTOR_VIEW_CAPTURE",
            "safe_to_signal": False,
            "command": command,
            "detail": (
                "This PID is not a selector-view capture (no "
                f"{SELECTOR_VIEW_FLAG} in its argv). It may be the narrow "
                "paper-feeding run or an unrelated process. Do not signal it."
            ),
        }
    if not exact:
        return False, {
            "pid": pid,
            "verdict": "IDENTITY_NOT_VERIFIABLE",
            "safe_to_signal": False,
            "command": command,
            "detail": (
                "This PID looks like a selector-view capture, but argv could "
                "not be read exactly (no /proc on this platform), and `ps` "
                "output cannot be split back into argv reliably — an argument "
                "value could masquerade as the flag. Refusing to confirm. Run "
                "this check on the capture host."
            ),
        }
    return True, {
        "pid": pid,
        "verdict": "SELECTOR_VIEW_CAPTURE",
        "safe_to_signal": True,
        "command": command,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one observation tick")
    parser.add_argument("--loop", action="store_true", help="run until interrupted")
    parser.add_argument("--enabled", action="store_true", help="override env and enable observer")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--quality-windows-json", default=None)
    parser.add_argument(
        "--capture-selector-view",
        action="store_true",
        help="record the cue endpoint's full selector view across all buckets (observation only)",
    )
    parser.add_argument(
        "--verify-selector-view-pid",
        type=int,
        default=None,
        metavar="PID",
        help=(
            "check whether PID is a selector-view capture and exit; "
            "exit 0 only if it is safe to signal (observation only, signals nothing)"
        ),
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=None,
        help="bound a looped run; exit after this many seconds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Read-only identity probe. Answered before any config/enablement handling
    # so the stop procedure can use it regardless of how the environment is set,
    # and so it stays a pure question: it inspects a PID and signals nothing.
    if args.verify_selector_view_pid is not None:
        safe, verdict = verify_selector_view_pid(args.verify_selector_view_pid)
        print(json.dumps(verdict, sort_keys=True), file=sys.stdout if safe else sys.stderr)
        return 0 if safe else 2

    config = load_config()
    if args.enabled:
        config = config.replace(enabled=True)
    if args.output_dir:
        config = config.replace(output_dir=Path(args.output_dir))
    if args.quality_windows_json:
        config = config.replace(quality_windows=load_quality_windows(args.quality_windows_json))
    if args.loop:
        config = config.replace(loop=True)
    if args.once:
        config = config.replace(loop=False)
    if args.capture_selector_view:
        config = config.replace(capture_selector_view=True)
    if args.max_runtime_seconds is not None:
        config = config.replace(max_runtime_seconds=args.max_runtime_seconds)

    if not config.enabled:
        print(
            json.dumps(
                {
                    "enabled": False,
                    "recommended_action": "SET_AUTOPILOT_OBSERVE_ENABLED_TRUE_TO_RUN",
                },
                indent=2,
            )
        )
        return 0

    # A selector-view loop captures the whole universe every tick, so an
    # unbounded one is both an unattended loop and unbounded disk growth.
    # Refuse startup unless a positive runtime bound is configured. Placed
    # after the disabled-default early return above, so this guard never fires
    # on a disabled probe, and scoped to selector-view loops so the narrow
    # paper-feeding loop's existing operator-authorized behaviour is unchanged.
    # (This comment used to say the placement kept the disabled probe
    # "byte-identical". It does not: load_config runs before that early return,
    # so a malformed quality-windows file fails a disabled probe too — see
    # OBS-2. The guard's placement is still right; the claim was not.)
    # A one-shot (--once) selector-view run is inherently bounded and exempt.
    if config.loop and config.capture_selector_view:
        if config.max_runtime_seconds is None or config.max_runtime_seconds <= 0:
            print(
                json.dumps(
                    {
                        "error": "SELECTOR_VIEW_LOOP_REQUIRES_MAX_RUNTIME",
                        "detail": (
                            "AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS (or "
                            "--max-runtime-seconds) must be a positive integer "
                            "to start a selector-view loop."
                        ),
                        "max_runtime_seconds": config.max_runtime_seconds,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2

    seen_keys: set[str] = set()
    client = JsonGetClient()
    # Monotonic, not wall-clock: this is the bound that keeps a selector-view
    # capture from running unattended, so it must not be steerable by the
    # system clock. `utc_now()` is `datetime.now()`, which an NTP correction can
    # step in either direction — backwards, and the loop runs past the runtime
    # the Operator authorized; forwards, and it exits early mid-window.
    # `time.monotonic()` cannot be stepped, and it is already what
    # `sleep_until_interval_or_stop` uses, so the two now measure the same clock.
    started_at = time.monotonic()
    # Scoped to selector-view loops only. This slice (work order AG-20260713-009)
    # requires the narrow paper-feeding run to stay byte-identical to pre-slice
    # behaviour, and installing a handler would change how it dies on SIGTERM —
    # so the narrow loop keeps its default signal disposition and its plain
    # sleep. `stop` stays None there, which also leaves run_once on its
    # always-returns-a-list path. Giving the narrow loop the same graceful stop
    # is a recorded follow-up, not this slice's call to make.
    stop: StopSignal | None = None
    if config.loop and config.capture_selector_view:
        stop = StopSignal()
        stop.install()

    def stopped_exit(detail: str) -> int:
        assert stop is not None  # only reachable on the selector-view path
        print(
            json.dumps(
                {
                    "generated_at": iso(utc_now()),
                    "status": "stopped_by_signal",
                    "signal": stop.signum,
                    "detail": detail,
                },
                sort_keys=True,
            )
        )
        return 0

    while True:
        observed_at = utc_now()
        records = run_once(
            config, client=client, observed_at=observed_at, seen_keys=seen_keys, stop=stop
        )
        if records is None:
            # Selector-view only (the narrow loop passes stop=None and never
            # gets here). A stop arrived while polling, before any record
            # existed, so this tick is abandoned unwritten — the tick simply
            # never happened on disk, which is precisely what a missing manifest
            # already means to a consumer.
            print(
                json.dumps(
                    {
                        "generated_at": iso(observed_at),
                        "status": "tick_abandoned_on_stop",
                        "detail": "stop signal received while polling; nothing was recorded",
                    },
                    sort_keys=True,
                )
            )
            return stopped_exit(
                "stop signal received while polling; the unwritten tick was abandoned"
            )
        # Past polling the tick is committed: a stop arriving now (including
        # mid-append inside write_records) only sets the flag, so this tick's
        # append completes and the exit checkpoint below is the first place the
        # stop takes effect. This is the only window in which a tick is finished
        # rather than abandoned.
        output_path = write_records(records, config.output_dir, observed_at)
        summary: dict[str, Any] = {
            "generated_at": iso(observed_at),
            "records": len(records),
            "output_path": str(output_path),
            "decisions": {},
        }
        if config.capture_selector_view:
            summary["selector_view_records"] = sum(
                1 for record in records if record.get("capture_profile") == "selector_view"
            )
        for record in records:
            decision = record.get("decision", "UNKNOWN")
            summary["decisions"][decision] = summary["decisions"].get(decision, 0) + 1
        print(json.dumps(summary, sort_keys=True))
        if not config.loop:
            return 0
        # A stop requested during the tick just written: exit before sleeping, so
        # a stop never starts one more tick. No-op for the narrow loop.
        if stop is not None and stop.requested:
            # Reached when the stop landed too late to abandon the tick — during
            # record construction, during the append, or during the final fetch
            # (which has no boundary left to honour it at). In every case the
            # tick above is already written in full.
            return stopped_exit(
                "stop signal received once the tick was past abandoning; its append completed"
            )
        if config.max_runtime_seconds is not None:
            elapsed = time.monotonic() - started_at
            if elapsed + config.interval_seconds >= config.max_runtime_seconds:
                print(
                    json.dumps(
                        {"generated_at": iso(utc_now()), "status": "max_runtime_reached"},
                        sort_keys=True,
                    )
                )
                return 0
        if stop is None:
            # Narrow paper-feeding loop: the pre-slice sleep, unchanged.
            time.sleep(config.interval_seconds)
            continue
        sleep_until_interval_or_stop(config.interval_seconds, stop)
        # Covers a stop landing anywhere between the tick's append and the end of
        # the sleep, including the gap before the sleep starts — in every case
        # the previous tick is already durable and no tick is in flight.
        if stop.requested:
            return stopped_exit(
                "stop signal received between ticks; no tick was in flight"
            )


if __name__ == "__main__":
    sys.exit(main())
