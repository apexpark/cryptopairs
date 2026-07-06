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
from collections import defaultdict
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
MODE = "shadow_dynamic_allowlist_snapshot"
TIMEFRAME = "1m"
LONG_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{6})\d+((?:[+-]\d{2}:\d{2})?)$")
SUPPORTED_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}

Key = tuple[str, str, str, str]


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


def events_from_positions(rows: Iterable[dict[str, Any]]) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    for row in latest_positions_by_id(rows).values():
        if row.get("status") != "CLOSED":
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


def events_from_paper_trades(rows: Iterable[dict[str, Any]]) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    for row in rows:
        if row.get("timeframe") != TIMEFRAME:
            continue
        if row.get("exit_ts") is None or row.get("net_bps") is None:
            continue
        key = row_key(row)
        events.append(
            TradeEvent(
                key=key,
                entry_at=parse_timestamp(row.get("entry_ts"), "entry_ts"),
                exit_at=parse_timestamp(row.get("exit_ts"), "exit_ts"),
                realized_net_bps=numeric(row.get("net_bps"), "net_bps"),
                exit_lag_seconds=None,
            )
        )
    return events


def parse_allowlist(value: str | None) -> set[Key]:
    if value is None or not value.strip():
        return set()
    entries: set[Key] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(
                "static allowlist entries must be pair_id:selected_variant:direction"
            )
        entries.add((parts[0], TIMEFRAME, parts[1], direction_value(parts[2])))
    return entries


def allowlist_from_run_config(path: str | None) -> set[Key]:
    if path is None:
        return set()
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("run config must be a JSON object")
    result: set[Key] = set()
    for entry in payload.get("static_allowlist", []):
        if not isinstance(entry, dict):
            raise ValueError("run_config.static_allowlist entries must be objects")
        direction = entry.get("direction")
        if direction is None:
            continue
        result.add(
            (
                require_string(entry, "pair_id"),
                TIMEFRAME,
                require_string(entry, "selected_variant"),
                direction_value(direction),
            )
        )
    return result


def key_object(key: Key) -> dict[str, str]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
    }


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
    exit_lag_penalty = (
        round(-(avg_exit_lag_seconds or 0.0) / 900.0, 4)
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


def build_snapshot(
    *,
    events: list[TradeEvent],
    source_cutoff_at: str,
    selector_config: SelectorConfig,
    static_allowlist: set[Key] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
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
    static = set() if static_allowlist is None else static_allowlist
    return {
        "schema_version": SCHEMA_VERSION,
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
        },
        "selected": selected,
        "rejected": rejected,
        "quarantined": quarantined,
        "static_allowlist_comparison": static_comparison(static, selected_keys),
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
                "This artifact is not live PnL, not a fill audit, and not permission "
                "to enable dynamic paper or live automation."
            ),
        },
    }


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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-trades-json", action="append", default=[])
    parser.add_argument("--positions-jsonl", action="append", default=[])
    parser.add_argument("--paper-dir", action="append", default=[])
    parser.add_argument("--run-config-json", default=None)
    parser.add_argument("--static-allowlist", default=None)
    parser.add_argument("--source-cutoff-at", required=True)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--min-closed-positions", type=int, default=10)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--max-tail-loss-bps", type=float, default=-60.0)
    parser.add_argument("--max-avg-exit-lag-seconds", type=int, default=1800)
    parser.add_argument("--max-selected", type=int, default=8)
    parser.add_argument("--min-score", type=float, default=0.0)
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
    events = events_from_paper_trades(trade_rows) + events_from_positions(position_rows)
    if not events:
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
    snapshot = build_snapshot(
        events=events,
        source_cutoff_at=args.source_cutoff_at,
        selector_config=selector_config,
        static_allowlist=static_allowlist,
        generated_at=args.generated_at,
    )
    output = json.dumps(snapshot, indent=2, sort_keys=True)
    if args.output_json:
        write_text(args.output_json, output + "\n")
    else:
        print(output)
    if args.output_markdown:
        write_text(args.output_markdown, render_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
