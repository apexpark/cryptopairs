#!/usr/bin/env python3
"""Paper-only 1m autopilot ledger.

This tool consumes observe-like candidate records and paper mark/outcome rows,
then writes append-only paper decisions and paper position lifecycle records. It
does not call HTTP services and does not create execution intents.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Set, Tuple


SCHEMA_VERSION = 1
MODE = "paper_only"
SUPPORTED_TIMEFRAME = "1m"
DEFAULT_OUTPUT_DIR = Path("artifacts/autopilot_paper")
MAX_HOLD_WINDOW_BARS = 240
OBSERVE_MODE = "observe_only"
OBSERVE_EVIDENCE_FIELDS = (
    "data_health_status",
    "strategy_health_status",
    "trade_now_status",
    "trade_now_observability_status",
    "dispatch_mode_status",
    "kill_switch_status",
    "open_trades_status",
)

Key = Tuple[str, str, str, str]


@dataclasses.dataclass(frozen=True)
class Config:
    enabled: bool = False
    allowed_pair_variants: Set[Tuple[str, str]] = dataclasses.field(default_factory=set)
    hold_window_bars: Optional[int] = None
    cooldown_seconds: int = 300
    max_candidate_age_seconds: int = 120
    output_dir: Path = DEFAULT_OUTPUT_DIR

    def replace(self, **changes: Any) -> "Config":
        return dataclasses.replace(self, **changes)


@dataclasses.dataclass(frozen=True)
class RunResult:
    decisions: list[dict[str, Any]]
    positions: list[dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class ArtifactPaths:
    decisions_path: Path
    positions_path: Path


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def normalize_observed_at(value: Optional[dt.datetime]) -> dt.datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    return value.astimezone(dt.timezone.utc)


def bool_env(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def optional_int_env(value: Optional[str]) -> Optional[int]:
    if value is None or not value.strip():
        return None
    return int(value)


def int_env(value: Optional[str], default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def parse_allowed_pair_variants(value: Optional[str]) -> Set[Tuple[str, str]]:
    if value is None or not value.strip():
        return set()
    parsed: Set[Tuple[str, str]] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if item.count(":") != 1:
            raise ValueError(
                "AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS entries must be pair_id:selected_variant"
            )
        pair_id, selected_variant = item.split(":", 1)
        pair_id = pair_id.strip()
        selected_variant = selected_variant.strip()
        if not pair_id or not selected_variant:
            raise ValueError(
                "AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS entries must be non-empty"
            )
        parsed.add((pair_id, selected_variant))
    return parsed


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    source = os.environ if env is None else env
    return Config(
        enabled=bool_env(source.get("AUTOPILOT_PAPER_ENABLED"), False),
        allowed_pair_variants=parse_allowed_pair_variants(
            source.get("AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS")
        ),
        hold_window_bars=optional_int_env(source.get("AUTOPILOT_PAPER_HOLD_WINDOW_BARS")),
        cooldown_seconds=max(0, int_env(source.get("AUTOPILOT_PAPER_COOLDOWN_SECONDS"), 300)),
        max_candidate_age_seconds=max(
            1, int_env(source.get("AUTOPILOT_PAPER_MAX_CANDIDATE_AGE_SECONDS"), 120)
        ),
        output_dir=Path(source.get("AUTOPILOT_PAPER_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))),
    )


def direction_from_candidate(candidate: Mapping[str, Any]) -> Optional[str]:
    for field_name in ("direction_hint", "direction"):
        value = candidate.get(field_name)
        if isinstance(value, str) and value:
            return value
    observe_key = candidate.get("observe_key")
    if isinstance(observe_key, str):
        parts = observe_key.split(":", 6)
        if len(parts) >= 6 and parts[0] == "observe-only" and parts[1] == "v1":
            return parts[5] if parts[5] and parts[5] != "NO_DIRECTION" else None
    return None


def nullable_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    return None


def candidate_key(candidate: Mapping[str, Any]) -> Optional[Key]:
    pair_id = candidate.get("pair_id")
    timeframe = candidate.get("timeframe")
    selected_variant = candidate.get("selected_variant")
    direction = direction_from_candidate(candidate)
    if not isinstance(pair_id, str) or not pair_id:
        return None
    if not isinstance(timeframe, str) or not timeframe:
        return None
    if not isinstance(selected_variant, str) or not selected_variant:
        return None
    if direction is None:
        return None
    return (pair_id, timeframe, selected_variant, direction)


def candidate_identity_reason(candidate: Mapping[str, Any]) -> str:
    pair_id = candidate.get("pair_id")
    timeframe = candidate.get("timeframe")
    selected_variant = candidate.get("selected_variant")
    if not isinstance(pair_id, str) or not pair_id:
        return "CANDIDATE_IDENTITY_MISSING"
    if not isinstance(timeframe, str) or not timeframe:
        return "CANDIDATE_IDENTITY_MISSING"
    if not isinstance(selected_variant, str) or not selected_variant:
        return "CANDIDATE_IDENTITY_MISSING"
    if direction_from_candidate(candidate) is None:
        return "CANDIDATE_DIRECTION_MISSING"
    return "CANDIDATE_IDENTITY_MISSING"


def observe_key_reason(
    observe_key: Optional[str], key: Key, candidate_observed_at: dt.datetime
) -> Optional[str]:
    if observe_key is None:
        return "CANDIDATE_OBSERVE_KEY_MISSING"
    parts = observe_key.split(":", 6)
    if len(parts) != 7 or parts[0] != "observe-only" or parts[1] != "v1":
        return "CANDIDATE_OBSERVE_KEY_INVALID"
    observe_key_time = parse_iso(parts[6])
    if (
        parts[2] != key[1]
        or parts[3] != key[0]
        or parts[4] != key[2]
        or parts[5] != key[3]
        or observe_key_time != candidate_observed_at
    ):
        return "CANDIDATE_OBSERVE_KEY_MISMATCH"
    return None


def observe_malformed_reason_codes(
    candidate: Mapping[str, Any],
    key: Key,
    observe_key: Optional[str],
    candidate_observed_at: dt.datetime,
) -> list[str]:
    reasons: list[str] = []
    if candidate.get("schema_version") != 1:
        reasons.append("CANDIDATE_SCHEMA_VERSION_INVALID")
    if candidate.get("mode") != OBSERVE_MODE:
        reasons.append("CANDIDATE_MODE_INVALID")

    key_reason = observe_key_reason(observe_key, key, candidate_observed_at)
    if key_reason is not None:
        reasons.append(key_reason)

    evidence = candidate.get("evidence")
    if not isinstance(evidence, dict):
        reasons.append("CANDIDATE_EVIDENCE_MISSING")
    else:
        source_urls = evidence.get("source_urls")
        has_status_fields = all(isinstance(evidence.get(field), str) for field in OBSERVE_EVIDENCE_FIELDS)
        has_source_urls = (
            isinstance(source_urls, list)
            and len(source_urls) > 0
            and all(isinstance(url, str) and url for url in source_urls)
        )
        if not has_status_fields or not has_source_urls:
            reasons.append("CANDIDATE_EVIDENCE_MISSING")

    if candidate.get("dispatch_mode") not in {"FAIL_CLOSED", "SIMULATE_ACK", "LIVE_KRAKEN"}:
        reasons.append("CANDIDATE_DISPATCH_MODE_INVALID")
    if not isinstance(candidate.get("kill_switch_active"), bool):
        reasons.append("CANDIDATE_KILL_SWITCH_ACTIVE_INVALID")
    if not isinstance(candidate.get("conflicting_live_trade"), bool):
        reasons.append("CANDIDATE_CONFLICTING_LIVE_TRADE_INVALID")
    return reasons


def observe_ineligible_reason_codes(candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if candidate.get("dispatch_mode") == "FAIL_CLOSED":
        reasons.append("OBSERVE_DISPATCH_MODE_FAIL_CLOSED")
    if candidate.get("kill_switch_active") is True:
        reasons.append("OBSERVE_KILL_SWITCH_ACTIVE")
    if candidate.get("conflicting_live_trade") is True:
        reasons.append("OBSERVE_CONFLICTING_LIVE_TRADE")
    if candidate.get("setup_gate_pass") is not True:
        reasons.append("OBSERVE_SETUP_GATE_NOT_PASS")
    if candidate.get("cost_gate_pass") is not True:
        reasons.append("OBSERVE_COST_GATE_NOT_PASS")
    if candidate.get("trade_gate_pass") is not True:
        reasons.append("OBSERVE_TRADE_GATE_NOT_PASS")

    quality_window = candidate.get("quality_window")
    if not isinstance(quality_window, dict) or quality_window.get("pass") is not True:
        reasons.append("OBSERVE_QUALITY_WINDOW_NOT_PASS")

    evidence = candidate.get("evidence")
    if isinstance(evidence, dict) and any(
        evidence.get(field) != "ok" for field in OBSERVE_EVIDENCE_FIELDS
    ):
        reasons.append("OBSERVE_EVIDENCE_STATUS_NOT_OK")
    return reasons


def position_key(position: Mapping[str, Any]) -> Optional[Key]:
    pair_id = position.get("pair_id")
    timeframe = position.get("timeframe")
    selected_variant = position.get("selected_variant")
    direction = position.get("direction")
    values = [pair_id, timeframe, selected_variant, direction]
    if not all(isinstance(value, str) and value for value in values):
        return None
    return (str(pair_id), str(timeframe), str(selected_variant), str(direction))


def validate_hold_window(config: Config) -> Optional[str]:
    if not isinstance(config.hold_window_bars, int):
        return "HOLD_WINDOW_BARS_REQUIRED"
    if config.hold_window_bars < 1:
        return "HOLD_WINDOW_BARS_TOO_LOW"
    if config.hold_window_bars > MAX_HOLD_WINDOW_BARS:
        return "HOLD_WINDOW_BARS_TOO_HIGH"
    return None


def build_position_id(key: Key, entry_observed_at: dt.datetime) -> str:
    return ":".join(
        ["paper-position", "v1", key[1], key[0], key[2], key[3], iso(entry_observed_at)]
    )


def run_id(observed_at: dt.datetime) -> str:
    return f"{iso(observed_at)}-paper-1m"


def base_evidence(
    *,
    config: Config,
    candidate_timeframe: Optional[str] = SUPPORTED_TIMEFRAME,
    candidate_source: str = "observe_record",
    mark_source: Optional[str] = None,
    existing_open_position: bool = False,
    cooldown_until: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    return {
        "static_allowlist_size": len(config.allowed_pair_variants),
        "candidate_timeframe": candidate_timeframe,
        "candidate_source": candidate_source,
        "mark_source": mark_source,
        "existing_open_position": existing_open_position,
        "cooldown_until": iso(cooldown_until) if cooldown_until is not None else None,
    }


def decision_record(
    *,
    config: Config,
    observed_at: dt.datetime,
    decision_type: str,
    decision_reason: str,
    reason_codes: list[str],
    key: Key,
    source_generated_at: Optional[str],
    observe_key: Optional[str],
    paper_position_id: Optional[str],
    exit_eligible_at: Optional[dt.datetime] = None,
    exit_source_type: Optional[str] = None,
    exit_source_at: Optional[dt.datetime] = None,
    realized_net_bps: Optional[float] = None,
    evidence: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "run_id": run_id(observed_at),
        "observed_at": iso(observed_at),
        "decision_type": decision_type,
        "decision_reason": decision_reason,
        "reason_codes": reason_codes,
        "pair_id": key[0],
        "timeframe": SUPPORTED_TIMEFRAME,
        "selected_variant": key[2],
        "direction": key[3],
        "source_generated_at": source_generated_at,
        "observe_key": observe_key,
        "paper_position_id": paper_position_id,
        "hold_window_bars": config.hold_window_bars,
        "cooldown_seconds": config.cooldown_seconds,
        "exit_eligible_at": iso(exit_eligible_at) if exit_eligible_at is not None else None,
        "exit_source_type": exit_source_type,
        "exit_source_at": iso(exit_source_at) if exit_source_at is not None else None,
        "realized_net_bps": realized_net_bps,
        "evidence": evidence if evidence is not None else base_evidence(config=config),
    }


def open_position_from_candidate(
    *,
    config: Config,
    candidate: Mapping[str, Any],
    key: Key,
    entry_observed_at: dt.datetime,
) -> dict[str, Any]:
    exit_eligible_at = entry_observed_at + dt.timedelta(minutes=int(config.hold_window_bars or 0))
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "paper_position_id": build_position_id(key, entry_observed_at),
        "pair_id": key[0],
        "timeframe": SUPPORTED_TIMEFRAME,
        "selected_variant": key[2],
        "direction": key[3],
        "status": "OPEN",
        "entry_observed_at": iso(entry_observed_at),
        "entry_score_z": nullable_number(candidate.get("selected_score_z")),
        "entry_net_edge_bps": nullable_number(candidate.get("net_edge_bps")),
        "source_generated_at": candidate.get("source_generated_at")
        if isinstance(candidate.get("source_generated_at"), str)
        else None,
        "entry_observe_key": candidate.get("observe_key")
        if isinstance(candidate.get("observe_key"), str)
        else None,
        "hold_window_bars": int(config.hold_window_bars or 0),
        "exit_eligible_at": iso(exit_eligible_at),
        "exit_observed_at": None,
        "exit_reason": None,
        "exit_source_type": None,
        "realized_net_bps": None,
    }


def latest_positions_by_id(positions: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for position in positions:
        position_id = position.get("paper_position_id")
        if isinstance(position_id, str) and position_id:
            latest[position_id] = position
    return latest


def open_position_for_key(positions: Sequence[Mapping[str, Any]], key: Key) -> Optional[Mapping[str, Any]]:
    for position in latest_positions_by_id(positions).values():
        if position.get("status") == "OPEN" and position_key(position) == key:
            return position
    return None


def has_malformed_open_position_state(positions: Sequence[Mapping[str, Any]]) -> bool:
    for position in positions:
        position_id = position.get("paper_position_id")
        if position.get("status") == "OPEN" and not (isinstance(position_id, str) and position_id):
            return True
    for position in latest_positions_by_id(positions).values():
        if position.get("status") == "OPEN" and not valid_open_position_state(position):
            return True
    return False


def valid_open_position_state(position: Mapping[str, Any]) -> bool:
    if position.get("schema_version") != SCHEMA_VERSION or position.get("mode") != MODE:
        return False
    if not isinstance(position.get("paper_position_id"), str) or not position.get("paper_position_id"):
        return False
    key = position_key(position)
    if key is None:
        return False
    hold_window_bars = position.get("hold_window_bars")
    if (
        isinstance(hold_window_bars, bool)
        or not isinstance(hold_window_bars, int)
        or hold_window_bars < 1
        or hold_window_bars > MAX_HOLD_WINDOW_BARS
    ):
        return False
    entry_observed_at = parse_iso(position.get("entry_observed_at"))
    if entry_observed_at is None:
        return False
    if position.get("paper_position_id") != build_position_id(key, entry_observed_at):
        return False
    exit_eligible_at = parse_iso(position.get("exit_eligible_at"))
    if exit_eligible_at is None:
        return False
    if exit_eligible_at != entry_observed_at + dt.timedelta(minutes=hold_window_bars):
        return False
    source_generated_at = position.get("source_generated_at")
    source_generated = parse_iso(source_generated_at)
    if source_generated is None or source_generated > entry_observed_at:
        return False
    if not isinstance(position.get("entry_observe_key"), str) or not position.get("entry_observe_key"):
        return False
    if observe_key_reason(position.get("entry_observe_key"), key, entry_observed_at) is not None:
        return False
    for numeric_field in ("entry_score_z", "entry_net_edge_bps"):
        value = position.get(numeric_field)
        if value is not None and nullable_number(value) is None:
            return False
    return (
        position.get("exit_observed_at") is None
        and position.get("exit_reason") is None
        and position.get("exit_source_type") is None
        and position.get("realized_net_bps") is None
    )


def latest_closed_position_for_key(
    positions: Sequence[Mapping[str, Any]], key: Key
) -> Optional[Mapping[str, Any]]:
    closed: list[tuple[dt.datetime, Mapping[str, Any]]] = []
    for position in latest_positions_by_id(positions).values():
        if position.get("status") != "CLOSED" or position_key(position) != key:
            continue
        exit_at = parse_iso(position.get("exit_observed_at"))
        if exit_at is not None:
            closed.append((exit_at, position))
    if not closed:
        return None
    return sorted(closed, key=lambda item: item[0])[-1][1]


def cooldown_until_for_key(
    positions: Sequence[Mapping[str, Any]], key: Key, config: Config
) -> Optional[dt.datetime]:
    latest_closed = latest_closed_position_for_key(positions, key)
    if latest_closed is None:
        return None
    exit_at = parse_iso(latest_closed.get("exit_observed_at"))
    if exit_at is None:
        return None
    return exit_at + dt.timedelta(seconds=config.cooldown_seconds)


def mark_key(mark: Mapping[str, Any]) -> Optional[Key]:
    pair_id = mark.get("pair_id")
    timeframe = mark.get("timeframe")
    selected_variant = mark.get("selected_variant")
    direction = mark.get("direction")
    values = [pair_id, timeframe, selected_variant, direction]
    if not all(isinstance(value, str) and value for value in values):
        return None
    return (str(pair_id), str(timeframe), str(selected_variant), str(direction))


def mark_time(mark: Mapping[str, Any]) -> Optional[dt.datetime]:
    value = mark.get("mark_at", mark.get("observed_at"))
    return parse_iso(value)


def mark_source_type(mark: Mapping[str, Any]) -> str:
    value = mark.get("source_type")
    if value in {"paper_trade_outcome", "mark_adapter"}:
        return str(value)
    return "mark_adapter"


def first_exit_mark(
    marks: Sequence[Mapping[str, Any]],
    key: Key,
    exit_eligible_at: dt.datetime,
    observed_at: dt.datetime,
) -> Optional[Mapping[str, Any]]:
    candidates: list[tuple[dt.datetime, Mapping[str, Any]]] = []
    for mark in marks:
        if mark_key(mark) != key:
            continue
        mark_observed_at = mark_time(mark)
        if (
            mark_observed_at is not None
            and exit_eligible_at <= mark_observed_at <= observed_at
            and nullable_number(mark.get("net_bps")) is not None
        ):
            candidates.append((mark_observed_at, mark))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def maybe_exit_open_positions(
    *,
    config: Config,
    existing_positions: Sequence[Mapping[str, Any]],
    marks: Sequence[Mapping[str, Any]],
    observed_at: dt.datetime,
) -> RunResult:
    decisions: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    for position in latest_positions_by_id(existing_positions).values():
        if position.get("status") != "OPEN":
            continue
        key = position_key(position)
        exit_eligible_at = parse_iso(position.get("exit_eligible_at"))
        if key is None or exit_eligible_at is None or observed_at < exit_eligible_at:
            continue
        mark = first_exit_mark(marks, key, exit_eligible_at, observed_at)
        if mark is None:
            decisions.append(
                decision_record(
                    config=config,
                    observed_at=observed_at,
                    decision_type="PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE",
                    decision_reason="Hold window expired, but no valid paper outcome or mark was available.",
                    reason_codes=["EXIT_MARK_UNAVAILABLE"],
                    key=key,
                    source_generated_at=position.get("source_generated_at")
                    if isinstance(position.get("source_generated_at"), str)
                    else None,
                    observe_key=position.get("entry_observe_key")
                    if isinstance(position.get("entry_observe_key"), str)
                    else None,
                    paper_position_id=position.get("paper_position_id")
                    if isinstance(position.get("paper_position_id"), str)
                    else None,
                    exit_eligible_at=exit_eligible_at,
                    realized_net_bps=None,
                    evidence=base_evidence(config=config, candidate_source="open_paper_position"),
                )
            )
            continue
        exit_at = mark_time(mark)
        realized_net_bps = nullable_number(mark.get("net_bps"))
        closed = dict(position)
        closed.update(
            {
                "status": "CLOSED",
                "exit_observed_at": iso(exit_at) if exit_at is not None else None,
                "exit_reason": "HOLD_WINDOW_MARK",
                "exit_source_type": mark_source_type(mark),
                "realized_net_bps": realized_net_bps,
            }
        )
        positions.append(closed)
        decisions.append(
            decision_record(
                config=config,
                observed_at=observed_at,
                decision_type="PAPER_EXIT_COMPLETED",
                decision_reason="Fixed holding window expired and the next available paper mark closed the position.",
                reason_codes=["HOLD_WINDOW_EXPIRED", "EXIT_MARK_APPLIED"],
                key=key,
                source_generated_at=position.get("source_generated_at")
                if isinstance(position.get("source_generated_at"), str)
                else None,
                observe_key=position.get("entry_observe_key")
                if isinstance(position.get("entry_observe_key"), str)
                else None,
                paper_position_id=position.get("paper_position_id")
                if isinstance(position.get("paper_position_id"), str)
                else None,
                exit_eligible_at=exit_eligible_at,
                exit_source_type=mark_source_type(mark),
                exit_source_at=exit_at,
                realized_net_bps=realized_net_bps,
                evidence=base_evidence(
                    config=config,
                    candidate_source="open_paper_position",
                    mark_source=mark_source_type(mark),
                ),
            )
        )
    return RunResult(decisions=decisions, positions=positions)


def evaluate_candidate(
    *,
    config: Config,
    candidate: Mapping[str, Any],
    observed_at: dt.datetime,
    existing_positions: Sequence[Mapping[str, Any]],
) -> RunResult:
    key = candidate_key(candidate)
    fallback_key = ("__UNKNOWN__", SUPPORTED_TIMEFRAME, "__UNKNOWN__", "NO_DIRECTION")
    active_key = key if key is not None else fallback_key
    raw_observe_key = candidate.get("observe_key")
    observe_key = raw_observe_key if isinstance(raw_observe_key, str) and raw_observe_key else None
    source_generated_at = (
        candidate.get("source_generated_at")
        if isinstance(candidate.get("source_generated_at"), str)
        else None
    )

    def block(
        decision_type: str,
        reason: str,
        codes: list[str],
        **evidence_changes: Any,
    ) -> RunResult:
        evidence = base_evidence(config=config, **evidence_changes)
        return RunResult(
            decisions=[
                decision_record(
                    config=config,
                    observed_at=observed_at,
                    decision_type=decision_type,
                    decision_reason=reason,
                    reason_codes=codes,
                    key=active_key,
                    source_generated_at=source_generated_at,
                    observe_key=observe_key,
                    paper_position_id=None,
                    evidence=evidence,
                )
            ],
            positions=[],
        )

    if key is None:
        reason_code = candidate_identity_reason(candidate)
        return block(
            "BLOCKED_MALFORMED_INPUT",
            "Candidate row is missing pair, timeframe, selected variant, or direction identity.",
            [reason_code],
        )
    if candidate.get("decision") != "OBSERVED_ENTRY_CANDIDATE":
        return block(
            "BLOCKED_OBSERVE_DECISION",
            "Only OBSERVED_ENTRY_CANDIDATE observe records can open paper positions.",
            ["OBSERVE_DECISION_NOT_ENTRY_CANDIDATE"],
        )
    if not config.allowed_pair_variants:
        return block(
            "BLOCKED_STATIC_ALLOWLIST_REQUIRED",
            "Static paper allowlist is empty.",
            ["STATIC_ALLOWLIST_EMPTY"],
        )
    if key[1] != SUPPORTED_TIMEFRAME:
        return block(
            "BLOCKED_TIMEFRAME_OUT_OF_SCOPE",
            "AUTO-2A paper ledger only accepts 1m candidates.",
            ["CANDIDATE_TIMEFRAME_NOT_1M"],
            candidate_timeframe=key[1],
        )
    if (key[0], key[2]) not in config.allowed_pair_variants:
        return block(
            "BLOCKED_NOT_ALLOWLISTED",
            "Candidate pair/variant is not in the static paper allowlist.",
            ["PAIR_VARIANT_NOT_ALLOWLISTED"],
        )
    hold_reason = validate_hold_window(config)
    if hold_reason is not None:
        return block(
            "BLOCKED_INVALID_HOLD_WINDOW",
            "Hold-window configuration is missing or outside supported bounds.",
            [hold_reason],
        )
    candidate_observed_at = parse_iso(candidate.get("observed_at"))
    if candidate_observed_at is None:
        return block(
            "BLOCKED_MALFORMED_INPUT",
            "Candidate observed_at is missing or invalid.",
            ["CANDIDATE_OBSERVED_AT_INVALID"],
        )
    if candidate_observed_at > observed_at:
        return block(
            "BLOCKED_MALFORMED_INPUT",
            "Candidate observed_at is after the current paper ledger tick.",
            ["CANDIDATE_OBSERVED_AT_FUTURE"],
        )
    source_generated = parse_iso(source_generated_at)
    if source_generated is None:
        return block(
            "BLOCKED_STALE_INPUT",
            "Candidate source timestamp is missing or invalid.",
            ["CANDIDATE_SOURCE_GENERATED_AT_INVALID"],
        )
    if source_generated > observed_at:
        return block(
            "BLOCKED_STALE_INPUT",
            "Candidate source timestamp is after the current paper ledger tick.",
            ["CANDIDATE_SOURCE_GENERATED_AT_FUTURE"],
        )
    if source_generated > candidate_observed_at:
        return block(
            "BLOCKED_STALE_INPUT",
            "Candidate source timestamp is after the candidate observed_at.",
            ["CANDIDATE_SOURCE_AFTER_OBSERVED_AT"],
        )
    if (observed_at - source_generated).total_seconds() > config.max_candidate_age_seconds:
        return block(
            "BLOCKED_STALE_INPUT",
            "Candidate source timestamp is older than the configured age threshold.",
            ["CANDIDATE_SOURCE_STALE"],
        )
    if has_malformed_open_position_state(existing_positions):
        return block(
            "BLOCKED_MALFORMED_EXISTING_POSITION_STATE",
            "Existing open paper position state is malformed.",
            ["OPEN_PAPER_POSITION_STATE_MALFORMED"],
        )
    existing_open = open_position_for_key(existing_positions, key)
    if existing_open is not None:
        return block(
            "BLOCKED_OPEN_PAPER_POSITION",
            "A matching paper position is already open.",
            ["OPEN_PAPER_POSITION_EXISTS"],
            existing_open_position=True,
        )
    malformed_reasons = observe_malformed_reason_codes(
        candidate, key, observe_key, candidate_observed_at
    )
    if malformed_reasons:
        return block(
            "BLOCKED_MALFORMED_INPUT",
            "Candidate observe record is missing required eligibility evidence.",
            malformed_reasons,
        )
    ineligible_reasons = observe_ineligible_reason_codes(candidate)
    if ineligible_reasons:
        return block(
            "BLOCKED_OBSERVE_DECISION",
            "Observe candidate safety or readiness fields are not eligible for paper entry.",
            ineligible_reasons,
        )
    cooldown_until = cooldown_until_for_key(existing_positions, key, config)
    if cooldown_until is not None and candidate_observed_at < cooldown_until:
        return block(
            "BLOCKED_COOLDOWN",
            "A matching paper position exited recently and cooldown is still active.",
            ["PAPER_COOLDOWN_ACTIVE"],
            cooldown_until=cooldown_until,
        )

    opened = open_position_from_candidate(
        config=config,
        candidate=candidate,
        key=key,
        entry_observed_at=candidate_observed_at,
    )
    exit_eligible_at = parse_iso(opened["exit_eligible_at"])
    decision = decision_record(
        config=config,
        observed_at=observed_at,
        decision_type="PAPER_ENTRY_OPENED",
        decision_reason="Static allowlist candidate opened one paper-only position.",
        reason_codes=[
            "STATIC_ALLOWLIST_PAIR_VARIANT",
            "NO_OPEN_PAPER_POSITION",
            "NO_ACTIVE_COOLDOWN",
            "HOLD_WINDOW_VALID",
        ],
        key=key,
        source_generated_at=source_generated_at,
        observe_key=observe_key,
        paper_position_id=opened["paper_position_id"],
        exit_eligible_at=exit_eligible_at,
        evidence=base_evidence(config=config),
    )
    return RunResult(decisions=[decision], positions=[opened])


def run_once(
    config: Config,
    *,
    candidates: Sequence[Mapping[str, Any]],
    marks: Sequence[Mapping[str, Any]],
    observed_at: Optional[dt.datetime] = None,
    existing_positions: Optional[Sequence[Mapping[str, Any]]] = None,
) -> RunResult:
    if not config.enabled:
        return RunResult(decisions=[], positions=[])

    now_value = normalize_observed_at(observed_at)
    prior_positions = [] if existing_positions is None else list(existing_positions)

    if has_malformed_open_position_state(prior_positions):
        exit_result = RunResult(decisions=[], positions=[])
    else:
        exit_result = maybe_exit_open_positions(
            config=config,
            existing_positions=prior_positions,
            marks=marks,
            observed_at=now_value,
        )
    current_positions = prior_positions + exit_result.positions

    decisions = list(exit_result.decisions)
    positions = list(exit_result.positions)
    for candidate in candidates:
        result = evaluate_candidate(
            config=config,
            candidate=candidate,
            observed_at=now_value,
            existing_positions=current_positions + positions,
        )
        decisions.extend(result.decisions)
        positions.extend(result.positions)
        current_positions.extend(result.positions)

    return RunResult(decisions=decisions, positions=positions)


def read_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    else:
        raise ValueError(f"{path} must contain a JSON array or object with rows array")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} rows must all be objects")
    return list(rows)


def read_jsonl_rows(path: Path, *, missing_ok: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        if missing_ok:
            return rows
        raise FileNotFoundError(path)
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} is not a JSON object")
        rows.append(payload)
    return rows


def read_persisted_positions(output_dir: Path) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []
    positions: list[dict[str, Any]] = []
    for path in sorted(output_dir.glob("*/autopilot_paper_positions_*.jsonl")):
        positions.extend(read_jsonl_rows(path))
    return positions


def existing_entry_observe_keys(paths: Sequence[Path]) -> Set[str]:
    keys: Set[str] = set()
    for path in paths:
        for row in read_jsonl_rows(path, missing_ok=True):
            observe_key = row.get("observe_key")
            if row.get("decision_type") == "PAPER_ENTRY_OPENED" and isinstance(observe_key, str):
                keys.add(observe_key)
    return keys


def persisted_decision_paths(output_dir: Path, current_decisions_path: Path) -> list[Path]:
    paths = sorted(output_dir.glob("*/autopilot_paper_decisions_*.jsonl")) if output_dir.exists() else []
    if current_decisions_path not in paths:
        paths.append(current_decisions_path)
    return paths


def apply_persisted_duplicate_blocks(result: RunResult, decision_paths: Sequence[Path]) -> RunResult:
    existing_keys = existing_entry_observe_keys(decision_paths)
    decisions: list[dict[str, Any]] = []
    duplicate_position_ids: Set[str] = set()
    for decision in result.decisions:
        next_decision = dict(decision)
        observe_key = next_decision.get("observe_key")
        if (
            next_decision.get("decision_type") == "PAPER_ENTRY_OPENED"
            and isinstance(observe_key, str)
        ):
            if observe_key in existing_keys:
                next_decision["decision_type"] = "BLOCKED_DUPLICATE_CANDIDATE"
                next_decision["decision_reason"] = (
                    "Candidate observe key already opened a paper position in persisted artifacts."
                )
                reason_codes = next_decision.get("reason_codes")
                reasons = list(reason_codes) if isinstance(reason_codes, list) else []
                if "PERSISTED_OBSERVE_KEY_ALREADY_OPENED" not in reasons:
                    reasons.append("PERSISTED_OBSERVE_KEY_ALREADY_OPENED")
                next_decision["reason_codes"] = reasons
                position_id = next_decision.get("paper_position_id")
                if isinstance(position_id, str):
                    duplicate_position_ids.add(position_id)
            else:
                existing_keys.add(observe_key)
        decisions.append(next_decision)
    positions = [
        dict(position)
        for position in result.positions
        if position.get("paper_position_id") not in duplicate_position_ids
    ]
    return RunResult(decisions=decisions, positions=positions)


def write_artifacts(result: RunResult, output_dir: Path, observed_at: dt.datetime) -> ArtifactPaths:
    day = observed_at.strftime("%Y%m%d")
    target_dir = output_dir / day
    target_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = target_dir / f"autopilot_paper_decisions_{day}.jsonl"
    positions_path = target_dir / f"autopilot_paper_positions_{day}.jsonl"
    next_result = apply_persisted_duplicate_blocks(
        result, persisted_decision_paths(output_dir, decisions_path)
    )
    result.decisions[:] = next_result.decisions
    result.positions[:] = next_result.positions
    with decisions_path.open("a", encoding="utf-8") as handle:
        for decision in next_result.decisions:
            handle.write(json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n")
    with positions_path.open("a", encoding="utf-8") as handle:
        for position in next_result.positions:
            handle.write(json.dumps(position, sort_keys=True, separators=(",", ":")) + "\n")
    return ArtifactPaths(decisions_path=decisions_path, positions_path=positions_path)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one paper ledger tick")
    parser.add_argument("--enabled", action="store_true", help="override env and enable paper ledger")
    parser.add_argument("--candidates-jsonl", action="append", default=[])
    parser.add_argument("--marks-json", action="append", default=[])
    parser.add_argument("--existing-positions-jsonl", action="append", default=[])
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args(list(argv))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config = load_config()
    if args.enabled:
        config = config.replace(enabled=True)
    if args.output_dir:
        config = config.replace(output_dir=Path(args.output_dir))

    if not config.enabled:
        print(
            json.dumps(
                {
                    "enabled": False,
                    "recommended_action": "SET_AUTOPILOT_PAPER_ENABLED_TRUE_TO_RUN",
                },
                indent=2,
            )
        )
        return 0

    observed_at = utc_now()
    candidates: list[dict[str, Any]] = []
    for path_value in args.candidates_jsonl:
        candidates.extend(read_jsonl_rows(Path(path_value)))
    marks: list[dict[str, Any]] = []
    for path_value in args.marks_json:
        marks.extend(read_json_rows(Path(path_value)))
    existing_positions: list[dict[str, Any]] = read_persisted_positions(config.output_dir)
    for path_value in args.existing_positions_jsonl:
        existing_positions.extend(read_jsonl_rows(Path(path_value)))

    result = run_once(
        config,
        candidates=candidates,
        marks=marks,
        observed_at=observed_at,
        existing_positions=existing_positions,
    )
    paths = write_artifacts(result, config.output_dir, observed_at)
    summary: dict[str, Any] = {
        "generated_at": iso(observed_at),
        "decisions": {},
        "positions": len(result.positions),
        "decisions_path": str(paths.decisions_path),
        "positions_path": str(paths.positions_path),
    }
    for decision in result.decisions:
        decision_type = str(decision.get("decision_type", "UNKNOWN"))
        summary["decisions"][decision_type] = summary["decisions"].get(decision_type, 0) + 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
