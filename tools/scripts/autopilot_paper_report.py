#!/usr/bin/env python3
"""Build an offline AUTO-2A paper-only trial report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any


SCHEMA_VERSION = 1
MODE = "paper_only_report"
PAPER_MODE = "paper_only"
TIMEFRAME = "1m"
MAX_HOLD_WINDOW_BARS = 240
MAX_RUNTIME_SECONDS = 259200
ALLOWLIST_MODES = {"pair_variant", "pair_variant_direction", "mixed"}
SUPPORTED_DIRECTIONS = {"LONG_SPREAD", "SHORT_SPREAD"}

Key = tuple[str, str, str, str]


def parse_timestamp(value: Any, field_name: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty timestamp string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone: {value}")
    return parsed.astimezone(dt.timezone.utc)


def format_timestamp(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def numeric(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def nullable_numeric(value: Any) -> float | None:
    if value is None:
        return None
    return numeric(value, "realized_net_bps")


def require_string(row: dict[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_integer(
    row: dict[str, Any],
    field_name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def normalize_run_config(run_config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(run_config, dict):
        raise ValueError("run_config must be a JSON object")
    allowed_fields = {
        "run_id",
        "timeframe",
        "static_allowlist_mode",
        "static_allowlist",
        "hold_window_bars",
        "max_runtime_seconds",
        "max_observe_candidate_age_seconds",
    }
    extra_fields = sorted(set(run_config) - allowed_fields)
    if extra_fields:
        raise ValueError(f"run_config has unsupported fields: {', '.join(extra_fields)}")

    run_id = require_string(run_config, "run_id")
    timeframe = require_string(run_config, "timeframe")
    if timeframe != TIMEFRAME:
        raise ValueError(f"AUTO-2A paper report only accepts 1m run_config; got {timeframe!r}")

    static_allowlist = run_config.get("static_allowlist")
    if not isinstance(static_allowlist, list) or not static_allowlist:
        raise ValueError("run_config.static_allowlist must be a non-empty array")

    raw_mode = run_config.get("static_allowlist_mode")
    if raw_mode is not None and raw_mode not in ALLOWLIST_MODES:
        raise ValueError(
            "run_config.static_allowlist_mode must be one of "
            f"{', '.join(sorted(ALLOWLIST_MODES))}"
        )

    normalized_allowlist: list[dict[str, str]] = []
    seen: set[tuple[str, str, str | None]] = set()
    direction_entries = 0
    for index, entry in enumerate(static_allowlist):
        if not isinstance(entry, dict):
            raise ValueError(f"run_config.static_allowlist[{index}] must be an object")
        extra_entry_fields = sorted(set(entry) - {"pair_id", "selected_variant", "direction"})
        if extra_entry_fields:
            raise ValueError(
                "run_config.static_allowlist[{index}] has unsupported fields: {fields}".format(
                    index=index,
                    fields=", ".join(extra_entry_fields),
                )
            )
        pair_id = require_string(entry, "pair_id")
        selected_variant = require_string(entry, "selected_variant")
        direction_value = entry.get("direction")
        if direction_value is not None:
            direction = require_string(entry, "direction")
            if direction not in SUPPORTED_DIRECTIONS:
                raise ValueError("run_config static allowlist direction must be LONG_SPREAD or SHORT_SPREAD")
            direction_entries += 1
        else:
            direction = None
        key = (pair_id, selected_variant, direction)
        if key in seen:
            rendered_key = f"{pair_id}:{selected_variant}"
            if direction is not None:
                rendered_key = f"{rendered_key}:{direction}"
            raise ValueError(f"run_config.static_allowlist contains duplicate {rendered_key}")
        seen.add(key)
        normalized_entry = {
            "pair_id": pair_id,
            "selected_variant": selected_variant,
        }
        if direction is not None:
            normalized_entry["direction"] = direction
        normalized_allowlist.append(normalized_entry)

    if raw_mode is None:
        if direction_entries == 0:
            static_allowlist_mode = "pair_variant"
        elif direction_entries == len(normalized_allowlist):
            static_allowlist_mode = "pair_variant_direction"
        else:
            static_allowlist_mode = "mixed"
    else:
        static_allowlist_mode = str(raw_mode)

    if static_allowlist_mode == "pair_variant" and direction_entries:
        raise ValueError("run_config direction entries require pair_variant_direction or mixed mode")
    if (
        static_allowlist_mode == "pair_variant_direction"
        and direction_entries != len(normalized_allowlist)
    ):
        raise ValueError("run_config pair_variant_direction mode requires direction on every entry")
    if static_allowlist_mode == "mixed" and (
        direction_entries == 0 or direction_entries == len(normalized_allowlist)
    ):
        raise ValueError("run_config mixed mode requires both pair-level and direction-level entries")

    return {
        "run_id": run_id,
        "timeframe": timeframe,
        "static_allowlist_mode": static_allowlist_mode,
        "static_allowlist": normalized_allowlist,
        "hold_window_bars": require_integer(
            run_config,
            "hold_window_bars",
            minimum=1,
            maximum=MAX_HOLD_WINDOW_BARS,
        ),
        "max_runtime_seconds": require_integer(
            run_config,
            "max_runtime_seconds",
            minimum=1,
            maximum=MAX_RUNTIME_SECONDS,
        ),
        "max_observe_candidate_age_seconds": require_integer(
            run_config,
            "max_observe_candidate_age_seconds",
            minimum=1,
            maximum=MAX_RUNTIME_SECONDS,
        ),
    }


def row_key(row: dict[str, Any]) -> Key:
    return (
        require_string(row, "pair_id"),
        require_string(row, "timeframe"),
        require_string(row, "selected_variant"),
        require_string(row, "direction"),
    )


def validate_paper_rows(rows: list[dict[str, Any]], source_name: str) -> None:
    for index, row in enumerate(rows):
        if row.get("schema_version") != SCHEMA_VERSION or row.get("mode") != PAPER_MODE:
            raise ValueError(f"{source_name} row {index} is not a v1 paper_only artifact")
        timeframe = row.get("timeframe")
        if timeframe != TIMEFRAME:
            raise ValueError(
                f"AUTO-2A paper report only accepts 1m {source_name} rows; "
                f"row {index} has {timeframe!r}"
            )


def position_event_time(position: dict[str, Any]) -> dt.datetime:
    status = position.get("status")
    if status == "CLOSED":
        return parse_timestamp(position.get("exit_observed_at"), "exit_observed_at")
    if status == "OPEN":
        return parse_timestamp(position.get("entry_observed_at"), "entry_observed_at")
    raise ValueError(f"position status must be OPEN or CLOSED, got {status!r}")


def latest_positions_by_id(positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, tuple[dt.datetime, dict[str, Any]]] = {}
    for position in positions:
        position_id = require_string(position, "paper_position_id")
        event_time = position_event_time(position)
        current = latest.get(position_id)
        if current is None or current[0] <= event_time:
            latest[position_id] = (event_time, position)
    return {position_id: position for position_id, (_, position) in latest.items()}


def sum_bps(values: list[float]) -> float:
    return round(sum(values), 4)


def avg_bps(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def initial_bucket(key: Key) -> dict[str, Any]:
    return {
        "pair_id": key[0],
        "timeframe": key[1],
        "selected_variant": key[2],
        "direction": key[3],
        "decision_records": 0,
        "entry_opened_decisions": 0,
        "exit_completed_decisions": 0,
        "exit_deferred_decisions": 0,
        "blocked_decisions": 0,
        "open_positions": 0,
        "closed_positions": 0,
        "profitable_closed_positions": 0,
        "_realized_net_bps": [],
    }


def finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    realized = list(bucket.pop("_realized_net_bps"))
    bucket["sum_realized_net_bps"] = sum_bps(realized)
    bucket["avg_realized_net_bps"] = avg_bps(realized)
    return bucket


def projected_position(position: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_position_id": require_string(position, "paper_position_id"),
        "pair_id": require_string(position, "pair_id"),
        "timeframe": require_string(position, "timeframe"),
        "selected_variant": require_string(position, "selected_variant"),
        "direction": require_string(position, "direction"),
        "status": require_string(position, "status"),
        "entry_observed_at": require_string(position, "entry_observed_at"),
        "exit_eligible_at": require_string(position, "exit_eligible_at"),
        "exit_observed_at": position.get("exit_observed_at"),
        "exit_source_type": position.get("exit_source_type"),
        "realized_net_bps": nullable_numeric(position.get("realized_net_bps")),
    }


def min_timestamp(values: list[dt.datetime]) -> str | None:
    return format_timestamp(min(values)) if values else None


def max_timestamp(values: list[dt.datetime]) -> str | None:
    return format_timestamp(max(values)) if values else None


def build_report(
    *,
    run_config: dict[str, Any],
    paper_decisions: list[dict[str, Any]],
    paper_positions: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_run_config = normalize_run_config(run_config)
    validate_paper_rows(paper_decisions, "decision")
    validate_paper_rows(paper_positions, "position")

    generated_timestamp = (
        parse_timestamp(generated_at, "generated_at")
        if generated_at is not None
        else dt.datetime.now(dt.timezone.utc)
    )
    latest_positions = latest_positions_by_id(paper_positions)
    buckets: dict[Key, dict[str, Any]] = {}
    observed_times: list[dt.datetime] = []
    block_breakdown: dict[str, int] = defaultdict(int)

    def bucket_for(key: Key) -> dict[str, Any]:
        return buckets.setdefault(key, initial_bucket(key))

    for decision in paper_decisions:
        decision_type = require_string(decision, "decision_type")
        key = row_key(decision)
        bucket = bucket_for(key)
        bucket["decision_records"] += 1
        if decision_type == "PAPER_ENTRY_OPENED":
            bucket["entry_opened_decisions"] += 1
        elif decision_type == "PAPER_EXIT_COMPLETED":
            bucket["exit_completed_decisions"] += 1
        elif decision_type == "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE":
            bucket["exit_deferred_decisions"] += 1
        elif decision_type.startswith("BLOCKED_"):
            bucket["blocked_decisions"] += 1
            block_breakdown[decision_type] += 1
        observed_times.append(parse_timestamp(decision.get("observed_at"), "observed_at"))

    open_positions: list[dict[str, Any]] = []
    closed_positions: list[dict[str, Any]] = []
    realized_values: list[float] = []
    for position in latest_positions.values():
        key = row_key(position)
        bucket = bucket_for(key)
        status = require_string(position, "status")
        projected = projected_position(position)
        observed_times.append(position_event_time(position))
        if status == "OPEN":
            bucket["open_positions"] += 1
            open_positions.append(projected)
        elif status == "CLOSED":
            realized_net_bps = numeric(position.get("realized_net_bps"), "realized_net_bps")
            bucket["closed_positions"] += 1
            if realized_net_bps > 0:
                bucket["profitable_closed_positions"] += 1
            bucket["_realized_net_bps"].append(realized_net_bps)
            realized_values.append(realized_net_bps)
            closed_positions.append(projected)
        else:
            raise ValueError(f"position status must be OPEN or CLOSED, got {status!r}")

    by_pair_variant = [finalize_bucket(bucket) for bucket in buckets.values()]
    by_pair_variant.sort(
        key=lambda row: (
            -row["closed_positions"],
            -row["open_positions"],
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
        )
    )
    open_positions.sort(key=lambda row: (row["pair_id"], row["selected_variant"], row["direction"]))
    closed_positions.sort(
        key=lambda row: (
            row["exit_observed_at"] or "",
            row["pair_id"],
            row["selected_variant"],
            row["direction"],
        )
    )

    summary = {
        "decision_records": len(paper_decisions),
        "entry_opened_decisions": sum(
            1 for row in paper_decisions if row.get("decision_type") == "PAPER_ENTRY_OPENED"
        ),
        "exit_completed_decisions": sum(
            1 for row in paper_decisions if row.get("decision_type") == "PAPER_EXIT_COMPLETED"
        ),
        "exit_deferred_decisions": sum(
            1
            for row in paper_decisions
            if row.get("decision_type") == "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE"
        ),
        "blocked_decisions": sum(
            1
            for row in paper_decisions
            if isinstance(row.get("decision_type"), str)
            and str(row.get("decision_type")).startswith("BLOCKED_")
        ),
        "block_breakdown": dict(sorted(block_breakdown.items())),
        "unique_positions": len(latest_positions),
        "open_positions": len(open_positions),
        "closed_positions": len(closed_positions),
        "profitable_closed_positions": sum(1 for value in realized_values if value > 0),
        "sum_realized_net_bps": sum_bps(realized_values),
        "avg_realized_net_bps": avg_bps(realized_values),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "generated_at": format_timestamp(generated_timestamp),
        "run_config": normalized_run_config,
        "scope": {
            "timeframe": TIMEFRAME,
            "position_identity": [
                "paper_position_id",
                "pair_id",
                "timeframe",
                "selected_variant",
                "direction",
            ],
            "run_started_at": min_timestamp(observed_times),
            "run_ended_at": max_timestamp(observed_times),
        },
        "source_counts": {
            "decision_records": len(paper_decisions),
            "position_records": len(paper_positions),
        },
        "summary": summary,
        "by_pair_variant": by_pair_variant,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "methodology": {
            "latest_position_state": (
                "Position state is derived from the latest append-only record per paper_position_id."
            ),
            "pnl_definition": (
                "Realized net bps is summed from latest CLOSED paper positions only."
            ),
            "execution_caveat": (
                "This report is offline paper simulation evidence. It is not live PnL, "
                "not a fill audit, and not permission to enable live automation."
            ),
        },
    }


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


def read_json_object(path: pathlib.Path, source_name: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{source_name} must be a JSON object")
    return payload


def collect_paths(files: list[str], directories: list[str], pattern: str, source_name: str) -> list[pathlib.Path]:
    paths = [pathlib.Path(value) for value in files]
    for directory in directories:
        root = pathlib.Path(directory)
        paths.extend(sorted(root.glob(f"**/{pattern}")))
    unique_paths = sorted({path.resolve() for path in paths})
    if not unique_paths:
        raise ValueError(f"at least one {source_name} JSONL file or --paper-dir is required")
    return unique_paths


def load_jsonl_paths(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl_rows(path))
    return rows


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    run_config = report["run_config"]
    allowlist = ", ".join(
        f"{row['pair_id']}:{row['selected_variant']}"
        + (f":{row['direction']}" if row.get("direction") else "")
        for row in run_config["static_allowlist"]
    )
    lines = [
        "# AUTO-2A Paper Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Run id: `{run_config['run_id']}`",
        f"- Timeframe: `{report['scope']['timeframe']}`",
        f"- Static allowlist mode: `{run_config['static_allowlist_mode']}`",
        f"- Static allowlist: `{allowlist}`",
        f"- Hold-window bars: `{run_config['hold_window_bars']}`",
        f"- Max runtime seconds: `{run_config['max_runtime_seconds']}`",
        "- Max observe candidate age seconds: "
        f"`{run_config['max_observe_candidate_age_seconds']}`",
        f"- Run started at: `{report['scope']['run_started_at']}`",
        f"- Run ended at: `{report['scope']['run_ended_at']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if isinstance(value, dict):
            continue
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Block Breakdown",
            "",
            "| Decision type | Count |",
            "|---|---:|",
        ]
    )
    for decision_type, count in summary["block_breakdown"].items():
        lines.append(f"| {decision_type} | {count} |")
    if not summary["block_breakdown"]:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## By Pair/Variant",
            "",
            "| Pair | Variant | Direction | Entries | Open | Closed | Profitable | Sum net bps | Avg net bps |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["by_pair_variant"]:
        lines.append(
            "| {pair_id} | {selected_variant} | {direction} | {entry_opened_decisions} | "
            "{open_positions} | {closed_positions} | {profitable_closed_positions} | "
            "{sum_realized_net_bps} | {avg_realized_net_bps} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Methodology",
            "",
            report["methodology"]["latest_position_state"],
            "",
            report["methodology"]["pnl_definition"],
            "",
            report["methodology"]["execution_caveat"],
            "",
        ]
    )
    return "\n".join(lines)


def write_text(path: str | None, value: str) -> None:
    if path is None:
        return
    output_path = pathlib.Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(value, encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", action="append", default=[])
    parser.add_argument("--decisions-jsonl", action="append", default=[])
    parser.add_argument("--positions-jsonl", action="append", default=[])
    parser.add_argument("--run-config-json", required=True)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-markdown", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    decision_paths = collect_paths(
        args.decisions_jsonl,
        args.paper_dir,
        "autopilot_paper_decisions_*.jsonl",
        "paper decision",
    )
    position_paths = collect_paths(
        args.positions_jsonl,
        args.paper_dir,
        "autopilot_paper_positions_*.jsonl",
        "paper position",
    )
    report = build_report(
        run_config=read_json_object(pathlib.Path(args.run_config_json), "run config"),
        paper_decisions=load_jsonl_paths(decision_paths),
        paper_positions=load_jsonl_paths(position_paths),
        generated_at=args.generated_at,
    )
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        write_text(args.output_json, output + "\n")
    else:
        print(output)
    if args.output_markdown:
        write_text(args.output_markdown, render_markdown(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"autopilot_paper_report: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
