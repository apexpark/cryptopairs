#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


TIMEFRAME = "1m"
CANDIDATE_DECISION = "OBSERVED_ENTRY_CANDIDATE"
MATCH_KEY_FIELDS = ["pair_id", "timeframe", "selected_variant", "direction"]
READY_GAP_SECONDS = 90


Key = tuple[str, str, str, str]


@dataclass(frozen=True)
class ReadyWindow:
    window_id: str
    key: Key
    start_at: dt.datetime
    end_at: dt.datetime
    ready_row_times: tuple[dt.datetime, ...]


@dataclass(frozen=True)
class PaperTrade:
    trade_id: str
    key: Key
    entry_ts: dt.datetime
    exit_ts: dt.datetime | None
    net_bps: float


def parse_timestamp(value: Any, field_name: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty timestamp string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone: {value}")
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


def base_key_fields(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        require_string(row, "pair_id"),
        require_string(row, "timeframe"),
        require_string(row, "selected_variant"),
    )


def direction_value(value: Any) -> str:
    return value if isinstance(value, str) and value else "NO_DIRECTION"


def observe_direction(record: dict[str, Any]) -> str:
    value = record.get("direction_hint")
    if isinstance(value, str) and value:
        return value
    observe_key = record.get("observe_key")
    if isinstance(observe_key, str):
        parts = observe_key.split(":", 6)
        if len(parts) >= 6 and parts[0] == "observe-only" and parts[1] == "v1":
            return direction_value(parts[5])
    return "NO_DIRECTION"


def observe_record_key(record: dict[str, Any]) -> Key:
    return (*base_key_fields(record), observe_direction(record))


def opportunity_record_key(row: dict[str, Any]) -> Key:
    return (*base_key_fields(row), direction_value(row.get("direction_hint")))


def paper_trade_key(row: dict[str, Any]) -> Key:
    return (*base_key_fields(row), direction_value(row.get("direction")))


def require_1m_rows(rows: list[dict[str, Any]], source_name: str) -> None:
    for index, row in enumerate(rows):
        timeframe = row.get("timeframe")
        if timeframe != TIMEFRAME:
            raise ValueError(f"AUTO-1C only accepts 1m {source_name} rows; row {index} has {timeframe!r}")


def validate_observe_records(records: list[dict[str, Any]]) -> None:
    for index, record in enumerate(records):
        timeframe = record.get("timeframe")
        if timeframe != TIMEFRAME:
            raise ValueError(f"AUTO-1C only accepts 1m observe records; row {index} has {timeframe!r}")


def rows_from_payload(payload: Any, source_name: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    else:
        raise ValueError(f"{source_name} must be a JSON array or an object with a rows array")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{source_name} rows must all be JSON objects")
    return list(rows)


def load_json_rows(paths: list[pathlib.Path], source_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(rows_from_payload(payload, source_name))
    return rows


def load_observe_jsonl(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            records.append(payload)
    return records


def collect_observe_paths(files: list[str], directories: list[str]) -> list[pathlib.Path]:
    paths = [pathlib.Path(value) for value in files]
    for directory in directories:
        root = pathlib.Path(directory)
        paths.extend(sorted(root.glob("**/autopilot_observe_*.jsonl")))
    unique_paths = sorted({path.resolve() for path in paths})
    if not unique_paths:
        raise ValueError("at least one --observe-jsonl file or --observe-dir with JSONL artifacts is required")
    return unique_paths


def derive_ready_windows(opportunity_rows: list[dict[str, Any]]) -> list[ReadyWindow]:
    rows_by_key: dict[Key, list[tuple[dt.datetime, dict[str, Any]]]] = defaultdict(list)
    for row in opportunity_rows:
        key = opportunity_record_key(row)
        evaluated_at = parse_timestamp(row.get("evaluated_at"), "evaluated_at")
        rows_by_key[key].append((evaluated_at, row))

    windows: list[ReadyWindow] = []
    for key, keyed_rows in rows_by_key.items():
        current_times: list[dt.datetime] = []
        previous_ready_at: dt.datetime | None = None
        window_index = 0
        for evaluated_at, row in sorted(keyed_rows, key=lambda item: item[0]):
            ready = row.get("actionable") is True and row.get("cost_gate_pass") is True
            gap_starts_new_window = (
                previous_ready_at is not None
                and (evaluated_at - previous_ready_at).total_seconds() > READY_GAP_SECONDS
            )
            if not ready or gap_starts_new_window:
                if current_times:
                    windows.append(ready_window(key, window_index, current_times))
                    window_index += 1
                current_times = []
                previous_ready_at = None
            if ready:
                current_times.append(evaluated_at)
                previous_ready_at = evaluated_at
        if current_times:
            windows.append(ready_window(key, window_index, current_times))
    return windows


def ready_window(key: Key, window_index: int, times: list[dt.datetime]) -> ReadyWindow:
    start_at = min(times)
    end_at = max(times)
    window_id = (
        f"ready-window:v1:{key[1]}:{key[0]}:{key[2]}:"
        f"{key[3]}:{format_timestamp(start_at)}:{format_timestamp(end_at)}:{window_index}"
    )
    return ReadyWindow(
        window_id=window_id,
        key=key,
        start_at=start_at,
        end_at=end_at,
        ready_row_times=tuple(sorted(times)),
    )


def normalize_paper_trades(paper_trade_rows: list[dict[str, Any]]) -> list[PaperTrade]:
    trades: dict[str, PaperTrade] = {}
    for row in paper_trade_rows:
        key = paper_trade_key(row)
        entry_ts = parse_timestamp(row.get("entry_ts"), "entry_ts")
        exit_ts = parse_timestamp(row["exit_ts"], "exit_ts") if row.get("exit_ts") else None
        raw_net_bps = row.get("net_bps")
        if not isinstance(raw_net_bps, (int, float)):
            raise ValueError("net_bps must be numeric for paper trade rows")
        direction = row.get("direction", "")
        exit_mode = row.get("exit_mode", "")
        trade_id = (
            f"paper-trade:v1:{key[1]}:{key[0]}:{key[2]}:"
            f"{key[3]}:{format_timestamp(entry_ts)}:{format_timestamp(exit_ts)}:{direction}:{exit_mode}"
        )
        trades[trade_id] = PaperTrade(
            trade_id=trade_id,
            key=key,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            net_bps=float(raw_net_bps),
        )
    return list(trades.values())


def matched_ready(
    *,
    candidate_key: Key,
    observed_at: dt.datetime,
    cutoff_at: dt.datetime,
    ready_windows: list[ReadyWindow],
) -> tuple[list[ReadyWindow], list[dt.datetime]]:
    windows: list[ReadyWindow] = []
    ready_row_times: list[dt.datetime] = []
    for window in ready_windows:
        if window.key != candidate_key:
            continue
        matching_times = [time for time in window.ready_row_times if observed_at <= time <= cutoff_at]
        if matching_times:
            windows.append(window)
            ready_row_times.extend(matching_times)
    return windows, ready_row_times


def matched_trades(
    *,
    candidate_key: Key,
    observed_at: dt.datetime,
    cutoff_at: dt.datetime,
    paper_trades: list[PaperTrade],
) -> list[PaperTrade]:
    trades_by_id: dict[str, PaperTrade] = {}
    for trade in paper_trades:
        if trade.key == candidate_key and observed_at <= trade.entry_ts <= cutoff_at:
            trades_by_id[trade.trade_id] = trade
    return list(trades_by_id.values())


def sum_bps(trades: list[PaperTrade]) -> float:
    return round(sum(trade.net_bps for trade in trades), 4)


def avg_bps(trades: list[PaperTrade]) -> float | None:
    if not trades:
        return None
    return round(sum(trade.net_bps for trade in trades) / len(trades), 4)


def build_report(
    *,
    observe_records: list[dict[str, Any]],
    opportunity_rows: list[dict[str, Any]],
    paper_trade_rows: list[dict[str, Any]],
    generated_at: str | None = None,
    lookahead_minutes: int = 240,
) -> dict[str, Any]:
    if lookahead_minutes <= 0:
        raise ValueError("lookahead_minutes must be positive")

    validate_observe_records(observe_records)
    require_1m_rows(opportunity_rows, "opportunity-history")
    require_1m_rows(paper_trade_rows, "paper-trade")

    generated_timestamp = (
        parse_timestamp(generated_at, "generated_at")
        if generated_at is not None
        else dt.datetime.now(dt.timezone.utc)
    )
    ready_windows = derive_ready_windows(opportunity_rows)
    paper_trades = normalize_paper_trades(paper_trade_rows)

    candidates = [record for record in observe_records if record.get("decision") == CANDIDATE_DECISION]
    observed_candidate_rows: list[dict[str, Any]] = []
    by_key: dict[Key, dict[str, Any]] = {}
    unique_ready_window_ids: set[str] = set()
    unique_paper_trades: dict[str, PaperTrade] = {}

    for record in sorted(candidates, key=lambda item: str(item.get("observed_at", ""))):
        candidate_key = observe_record_key(record)
        observed_at = parse_timestamp(record.get("observed_at"), "observed_at")
        cutoff_at = observed_at + dt.timedelta(minutes=lookahead_minutes)
        ready_matches, ready_row_times = matched_ready(
            candidate_key=candidate_key,
            observed_at=observed_at,
            cutoff_at=cutoff_at,
            ready_windows=ready_windows,
        )
        trade_matches = matched_trades(
            candidate_key=candidate_key,
            observed_at=observed_at,
            cutoff_at=cutoff_at,
            paper_trades=paper_trades,
        )
        ready_window_ids = {window.window_id for window in ready_matches}
        trade_ids = {trade.trade_id for trade in trade_matches}
        unique_ready_window_ids.update(ready_window_ids)
        for trade in trade_matches:
            unique_paper_trades[trade.trade_id] = trade

        pair_bucket = by_key.setdefault(
            candidate_key,
            {
                "pair_id": candidate_key[0],
                "timeframe": candidate_key[1],
                "selected_variant": candidate_key[2],
                "direction": candidate_key[3],
                "observed_candidate_records": 0,
                "first_observed_at": None,
                "last_observed_at": None,
                "observed_candidates_with_later_ready_window": 0,
                "observed_candidates_with_later_paper_trade": 0,
                "_ready_window_ids": set(),
                "_ready_row_ids": set(),
                "_paper_trades": {},
            },
        )
        pair_bucket["observed_candidate_records"] += 1
        pair_bucket["first_observed_at"] = min_optional_timestamp(
            pair_bucket["first_observed_at"],
            observed_at,
        )
        pair_bucket["last_observed_at"] = max_optional_timestamp(
            pair_bucket["last_observed_at"],
            observed_at,
        )
        if ready_window_ids:
            pair_bucket["observed_candidates_with_later_ready_window"] += 1
        if trade_ids:
            pair_bucket["observed_candidates_with_later_paper_trade"] += 1
        pair_bucket["_ready_window_ids"].update(ready_window_ids)
        pair_bucket["_ready_row_ids"].update(
            f"{candidate_key[1]}:{candidate_key[0]}:{candidate_key[2]}:{format_timestamp(time)}"
            f":{candidate_key[3]}"
            for time in ready_row_times
        )
        pair_bucket["_paper_trades"].update({trade.trade_id: trade for trade in trade_matches})

        observed_candidate_rows.append(
            {
                "observe_key": require_string(record, "observe_key"),
                "observed_at": format_timestamp(observed_at),
                "pair_id": candidate_key[0],
                "timeframe": candidate_key[1],
                "selected_variant": candidate_key[2],
                "direction": candidate_key[3],
                "source_generated_at": record.get("source_generated_at"),
                "quality_window": record.get("quality_window"),
                "later_ready_window_count": len(ready_window_ids),
                "later_ready_row_count": len(ready_row_times),
                "first_later_ready_at": format_timestamp(min(ready_row_times)) if ready_row_times else None,
                "later_paper_trade_count": len(trade_matches),
                "profitable_later_paper_trade_count": sum(1 for trade in trade_matches if trade.net_bps > 0),
                "sum_later_paper_net_bps": sum_bps(trade_matches),
                "avg_later_paper_net_bps": avg_bps(trade_matches),
            }
        )

    by_pair_variant = [finalize_pair_bucket(bucket) for bucket in by_key.values()]
    by_pair_variant.sort(
        key=lambda item: (
            -item["observed_candidate_records"],
            item["pair_id"],
            item["selected_variant"],
            item["direction"],
        )
    )

    unique_trade_list = list(unique_paper_trades.values())
    summary = {
        "observed_candidate_records": len(candidates),
        "unique_observed_candidate_keys": len(by_key),
        "observed_candidates_with_later_ready_window": sum(
            1 for row in observed_candidate_rows if row["later_ready_window_count"] > 0
        ),
        "observed_candidates_with_later_paper_trade": sum(
            1 for row in observed_candidate_rows if row["later_paper_trade_count"] > 0
        ),
        "unique_later_ready_windows": len(unique_ready_window_ids),
        "unique_later_paper_trades": len(unique_trade_list),
        "profitable_unique_later_paper_trades": sum(1 for trade in unique_trade_list if trade.net_bps > 0),
        "sum_unique_later_paper_net_bps": sum_bps(unique_trade_list),
        "avg_unique_later_paper_net_bps": avg_bps(unique_trade_list),
    }

    return {
        "schema_version": 1,
        "mode": "observe_only_attribution",
        "generated_at": format_timestamp(generated_timestamp),
        "scope": {
            "timeframe": TIMEFRAME,
            "candidate_decision": CANDIDATE_DECISION,
            "match_key": MATCH_KEY_FIELDS,
            "lookahead_minutes": lookahead_minutes,
        },
        "source_counts": {
            "observe_records": len(observe_records),
            "opportunity_rows": len(opportunity_rows),
            "paper_trade_rows": len(paper_trade_rows),
        },
        "summary": summary,
        "by_pair_variant": by_pair_variant,
        "observed_candidates": observed_candidate_rows,
        "methodology": {
            "ready_window_definition": (
                "A ready window is a contiguous 1m sequence where opportunity-history rows have "
                "actionable=true and cost_gate_pass=true. Gaps over 90 seconds start a new window."
            ),
            "paper_trade_definition": (
                "Paper trades are matched by pair_id, timeframe, selected_variant, and direction "
                "when entry_ts falls inside the observed_at plus lookahead window."
            ),
            "deduplication": (
                "Aggregate paper-trade counts deduplicate by pair/timeframe/variant/entry/exit/"
                "direction/exit_mode so repeated observations do not multiply simulated outcomes."
            ),
            "execution_caveat": (
                "This report is offline attribution of observe-only records against simulated paper "
                "outcomes. It is not an execution audit and does not prove live fillability."
            ),
        },
    }


def min_optional_timestamp(existing: dt.datetime | None, candidate: dt.datetime) -> dt.datetime:
    if existing is None:
        return candidate
    return min(existing, candidate)


def max_optional_timestamp(existing: dt.datetime | None, candidate: dt.datetime) -> dt.datetime:
    if existing is None:
        return candidate
    return max(existing, candidate)


def finalize_pair_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    paper_trades = list(bucket["_paper_trades"].values())
    return {
        "pair_id": bucket["pair_id"],
        "timeframe": bucket["timeframe"],
        "selected_variant": bucket["selected_variant"],
        "direction": bucket["direction"],
        "observed_candidate_records": bucket["observed_candidate_records"],
        "first_observed_at": format_timestamp(bucket["first_observed_at"]),
        "last_observed_at": format_timestamp(bucket["last_observed_at"]),
        "observed_candidates_with_later_ready_window": bucket[
            "observed_candidates_with_later_ready_window"
        ],
        "observed_candidates_with_later_paper_trade": bucket[
            "observed_candidates_with_later_paper_trade"
        ],
        "later_ready_windows": len(bucket["_ready_window_ids"]),
        "later_ready_rows": len(bucket["_ready_row_ids"]),
        "unique_later_paper_trades": len(paper_trades),
        "profitable_unique_later_paper_trades": sum(1 for trade in paper_trades if trade.net_bps > 0),
        "sum_unique_later_paper_net_bps": sum_bps(paper_trades),
        "avg_unique_later_paper_net_bps": avg_bps(paper_trades),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# AUTO-1C Observe-Only Attribution Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Timeframe: `{report['scope']['timeframe']}`",
        f"- Lookahead minutes: `{report['scope']['lookahead_minutes']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## By Pair/Variant",
            "",
            "| Pair | Variant | Direction | Observed | Ready windows | Paper trades | Profitable | Sum net bps | Avg net bps |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["by_pair_variant"]:
        lines.append(
            "| {pair_id} | {selected_variant} | {direction} | {observed_candidate_records} | "
            "{later_ready_windows} | {unique_later_paper_trades} | "
            "{profitable_unique_later_paper_trades} | {sum_unique_later_paper_net_bps} | "
            "{avg_unique_later_paper_net_bps} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Methodology",
            "",
            report["methodology"]["ready_window_definition"],
            "",
            report["methodology"]["paper_trade_definition"],
            "",
            report["methodology"]["deduplication"],
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
    parser = argparse.ArgumentParser(description="Build an AUTO-1C observe-only attribution report.")
    parser.add_argument("--observe-jsonl", action="append", default=[], help="Observe JSONL artifact file.")
    parser.add_argument(
        "--observe-dir",
        action="append",
        default=[],
        help="Directory containing autopilot_observe_*.jsonl artifacts.",
    )
    parser.add_argument(
        "--opportunity-history-json",
        action="append",
        default=[],
        help="Opportunity-history JSON response or rows array.",
    )
    parser.add_argument(
        "--paper-trades-json",
        action="append",
        default=[],
        help="Paper-trades JSON response or rows array.",
    )
    parser.add_argument("--lookahead-minutes", type=int, default=240)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-markdown", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    observe_paths = collect_observe_paths(args.observe_jsonl, args.observe_dir)
    opportunity_paths = [pathlib.Path(value) for value in args.opportunity_history_json]
    paper_trade_paths = [pathlib.Path(value) for value in args.paper_trades_json]
    observe_records = load_observe_jsonl(observe_paths)
    opportunity_rows = load_json_rows(opportunity_paths, "opportunity-history")
    paper_trade_rows = load_json_rows(paper_trade_paths, "paper-trades")
    report = build_report(
        observe_records=observe_records,
        opportunity_rows=opportunity_rows,
        paper_trade_rows=paper_trade_rows,
        generated_at=args.generated_at,
        lookahead_minutes=args.lookahead_minutes,
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
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"autopilot_observe_report: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
