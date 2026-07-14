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
import os
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
            profitable_rate=_optional_float(row.get("profitable_rate")),
            avg_net_bps=_optional_float(row.get("avg_net_bps")),
        )
    return windows


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


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
        min_ready_window_rows=optional_int_env(
            source.get("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS")
        ),
        min_ready_window_avg_net_bps=optional_float_env(
            source.get("AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS")
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
    if trade_now is None:
        return None
    value = trade_now.get("generated_at")
    return value if isinstance(value, str) else None


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
        "learning_overlay_age_seconds": nullable_number(
            None if trade_now is None else trade_now.get("learning_overlay_age_seconds")
        ),
        "dispatch_mode": dispatch_mode_value(dispatch_mode),
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


def nullable_number(value: Any) -> float | int | None:
    return value if isinstance(value, (float, int)) and not isinstance(value, bool) else None


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


class _SelectorViewRowMalformed(Exception):
    """Internal sentinel: a cue row cannot be faithfully recorded; omit it."""


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


def selector_view_record(
    *,
    row: dict[str, Any],
    cue_bucket: str,
    observed_at: dt.datetime,
    source_generated: str | None,
) -> dict[str, Any]:
    def opt_str(value: Any) -> Any:
        return value if isinstance(value, str) and value else None

    def opt_num(value: Any) -> Any:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [code for code in value if isinstance(code, str)]

    def required_num(value: Any) -> float:
        # The v2 schema requires these as non-null numbers; an absent or
        # non-numeric stated figure means the row is malformed. Raise so the
        # caller omits it (fail closed) rather than fabricating a 0.0.
        parsed = opt_num(value)
        if parsed is None:
            raise _SelectorViewRowMalformed
        return float(parsed)

    record: dict[str, Any] = {
        "schema_version": SELECTOR_VIEW_SCHEMA_VERSION,
        "mode": "observe_only",
        "capture_profile": "selector_view",
        "run_id": iso(observed_at),
        "observed_at": iso(observed_at),
        "source_generated_at": source_generated if isinstance(source_generated, str) else iso(observed_at),
        "timeframe": SUPPORTED_TIMEFRAME,
        "pair_id": str(row.get("pair_id", SYSTEM_PAIR_ID)),
        "selected_variant": str(row.get("selected_variant", SYSTEM_VARIANT)),
        "cue_bucket": cue_bucket,
        "direction_hint": opt_str(row.get("direction_hint")),
        "decision": "SELECTOR_VIEW_OBSERVED",
        "decision_reason_code": opt_str(row.get("decision_reason_code")),
        "blocked_reason_code": opt_str(row.get("blocked_reason_code")),
        "watch_reason_code": opt_str(row.get("watch_reason_code")),
        "rationale_codes": str_list(row.get("rationale_codes")),
        "setup_gate_pass": bool(row.get("setup_gate_pass")),
        "cost_gate_pass": bool(row.get("cost_gate_pass")),
        "trade_gate_pass": bool(row.get("trade_gate_pass")),
        "spread_z": required_num(row.get("spread_z")),
        "net_edge_bps": required_num(row.get("net_edge_bps")),
        "opportunity_score": required_num(row.get("opportunity_score")),
        "observe_key": selector_view_observe_key(row, cue_bucket, observed_at),
    }
    for field_name in SELECTOR_VIEW_PASSTHROUGH:
        if field_name in ("decision_bucket",):
            record[field_name] = opt_str(row.get(field_name))
        elif field_name in (
            "open_live_trade",
            "requires_fresh_overlay",
            "learning_trade_eligible",
            "learning_selection_selected",
            "legacy_fallback_active",
        ):
            value = row.get(field_name)
            record[field_name] = bool(value) if isinstance(value, bool) else None
        elif field_name in ("expected_hold_bars",):
            value = row.get(field_name)
            record[field_name] = value if isinstance(value, int) and not isinstance(value, bool) else None
        elif field_name in (
            "portfolio_target_weight",
            "portfolio_risk_contribution",
            "selected_score_z",
            "entry_distance_z",
        ):
            record[field_name] = opt_num(row.get(field_name))
        elif field_name == "learning_reason_codes":
            value = row.get(field_name)
            record[field_name] = (
                [code for code in value if isinstance(code, str)]
                if isinstance(value, list)
                else None
            )
        else:
            record[field_name] = opt_str(row.get(field_name))
    return record


def malformed_bucket_marker(
    endpoint_key: str, observed_at: dt.datetime
) -> dict[str, Any]:
    return {
        "schema_version": SELECTOR_VIEW_SCHEMA_VERSION,
        "mode": "observe_only",
        "capture_profile": "selector_view",
        "run_id": iso(observed_at),
        "observed_at": iso(observed_at),
        "source_generated_at": iso(observed_at),
        "timeframe": SUPPORTED_TIMEFRAME,
        "pair_id": SYSTEM_PAIR_ID,
        "selected_variant": SYSTEM_VARIANT,
        "cue_bucket": "TRADE_NOW",
        "direction_hint": None,
        "decision": "SELECTOR_VIEW_OBSERVED",
        "decision_reason_code": None,
        "blocked_reason_code": f"CUE_BUCKET_MALFORMED:{endpoint_key}",
        "watch_reason_code": None,
        "rationale_codes": ["CUE_BUCKET_NOT_LIST"],
        "setup_gate_pass": False,
        "cost_gate_pass": False,
        "trade_gate_pass": False,
        "spread_z": 0.0,
        "net_edge_bps": 0.0,
        "opportunity_score": 0.0,
        "observe_key": ":".join(
            ["selector-view", "v2", SUPPORTED_TIMEFRAME, SYSTEM_PAIR_ID,
             SYSTEM_VARIANT, "NO_DIRECTION", f"MALFORMED_{endpoint_key.upper()}",
             iso(observed_at.astimezone(dt.timezone.utc).replace(second=0, microsecond=0))],
        ),
    }


def selector_view_records(
    *,
    trade_now: dict[str, Any],
    observed_at: dt.datetime,
) -> list[dict[str, Any]]:
    """Emit one selector-view row per candidate across all cue buckets.

    These are observations of the champion/challenger selector's stated view,
    never entry candidates and never outcomes. Fail-closed to omission: a row
    that is not an object, fails identity, or cannot be faithfully recorded
    (missing/non-numeric required stated figure, or any unexpected shape) is
    omitted — no partial or fabricated record is written. A bucket that is
    present but not a list yields a single diagnostic marker record so the
    malformed response is visible downstream rather than silently empty.
    """
    source_generated = source_generated_at(trade_now)
    records: list[dict[str, Any]] = []
    for endpoint_key, cue_bucket in CUE_BUCKETS:
        bucket = trade_now.get(endpoint_key)
        if bucket is None:
            continue
        if not isinstance(bucket, list):
            records.append(malformed_bucket_marker(endpoint_key, observed_at))
            continue
        for row in bucket:
            if not isinstance(row, dict):
                continue
            if candidate_identity_reason(row) is not None:
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
                continue
    return records


def run_once(
    config: Config,
    *,
    client: Any | None = None,
    observed_at: dt.datetime | None = None,
    seen_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
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
        # trade_now is a dict, and selector_view_records fails closed to
        # omission per row and marks any non-list bucket.
        return selector_view_records(trade_now=trade_now, observed_at=now_value)

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
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return path


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
        "--max-runtime-seconds",
        type=int,
        default=None,
        help="bound a looped run; exit after this many seconds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
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

    seen_keys: set[str] = set()
    client = JsonGetClient()
    started_at = utc_now()
    while True:
        observed_at = utc_now()
        records = run_once(config, client=client, observed_at=observed_at, seen_keys=seen_keys)
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
        if config.max_runtime_seconds is not None:
            elapsed = (utc_now() - started_at).total_seconds()
            if elapsed + config.interval_seconds >= config.max_runtime_seconds:
                print(
                    json.dumps(
                        {"generated_at": iso(utc_now()), "status": "max_runtime_reached"},
                        sort_keys=True,
                    )
                )
                return 0
        time.sleep(config.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
