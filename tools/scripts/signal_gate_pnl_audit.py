#!/usr/bin/env python3
"""Audit signal-marker trades against gate state and leg-level PnL attribution."""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TIMEFRAME_STEP_SECONDS = {
    "1m": 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(raw: str) -> dt.datetime:
    value = raw
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_pair_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    values = [item.strip() for item in raw.split(",")]
    return [item for item in values if item]


def timeframe_step(timeframe: str) -> int:
    return TIMEFRAME_STEP_SECONDS.get(timeframe, 60)


def http_get_json(url: str, timeout_seconds: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, timeout_seconds: int, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass
class IndexedSeries:
    epochs: list[int]
    values: list[float]

    def value_at(self, epoch: int, tolerance_seconds: int) -> float | None:
        if not self.epochs:
            return None
        position = bisect.bisect_left(self.epochs, epoch)
        candidates: list[tuple[int, float]] = []
        if position < len(self.epochs):
            candidates.append((self.epochs[position], self.values[position]))
        if position > 0:
            candidates.append((self.epochs[position - 1], self.values[position - 1]))
        best: tuple[int, float] | None = None
        best_distance = tolerance_seconds + 1
        for candidate_epoch, candidate_value in candidates:
            distance = abs(candidate_epoch - epoch)
            should_select = distance <= tolerance_seconds and (
                distance < best_distance
                or (
                    distance == best_distance
                    and best is not None
                    and candidate_epoch <= epoch
                )
            )
            if should_select:
                best = (candidate_epoch, candidate_value)
                best_distance = distance
        if best is None:
            return None
        return best[1]


def build_indexed_series(candles: list[dict[str, Any]]) -> IndexedSeries:
    rows = []
    for candle in candles:
        ts_raw = candle.get("ts")
        close_raw = candle.get("close")
        if not isinstance(ts_raw, str):
            continue
        if not isinstance(close_raw, (int, float)):
            continue
        epoch = int(parse_iso(ts_raw).timestamp())
        rows.append((epoch, float(close_raw)))
    rows.sort(key=lambda item: item[0])
    return IndexedSeries(
        epochs=[item[0] for item in rows],
        values=[item[1] for item in rows],
    )


@dataclass
class IndexedHistory:
    epochs: list[int]
    rows: list[dict[str, Any]]

    def nearest(self, epoch: int, tolerance_seconds: int) -> dict[str, Any] | None:
        if not self.epochs:
            return None
        position = bisect.bisect_left(self.epochs, epoch)
        candidates: list[tuple[int, dict[str, Any]]] = []
        if position < len(self.epochs):
            candidates.append((self.epochs[position], self.rows[position]))
        if position > 0:
            candidates.append((self.epochs[position - 1], self.rows[position - 1]))

        selected: dict[str, Any] | None = None
        best_distance = tolerance_seconds + 1
        for candidate_epoch, candidate_row in candidates:
            distance = abs(candidate_epoch - epoch)
            should_select = distance <= tolerance_seconds and (
                distance < best_distance
                or (
                    distance == best_distance
                    and selected is not None
                    and candidate_epoch <= epoch
                )
            )
            if should_select:
                selected = candidate_row
                best_distance = distance
        return selected


def build_history_index(rows: list[dict[str, Any]]) -> IndexedHistory:
    prepared = []
    for row in rows:
        ts_raw = row.get("evaluated_at")
        if not isinstance(ts_raw, str):
            continue
        prepared.append((int(parse_iso(ts_raw).timestamp()), row))
    prepared.sort(key=lambda item: item[0])
    return IndexedHistory(
        epochs=[item[0] for item in prepared],
        rows=[item[1] for item in prepared],
    )


def pair_markers_to_round_trips(markers: list[dict[str, Any]], point_count: int) -> list[tuple[int, int, str]]:
    filtered = []
    for marker in markers:
        index = marker.get("index")
        kind = marker.get("kind")
        if not isinstance(index, int) or not isinstance(kind, str):
            continue
        if index < 0 or index >= point_count:
            continue
        filtered.append((index, kind))
    filtered.sort(key=lambda item: item[0])

    trips: list[tuple[int, int, str]] = []
    open_entry: int | None = None
    for marker_index, marker_kind in filtered:
        if marker_kind == "entry":
            if open_entry is None:
                open_entry = marker_index
            continue
        if marker_kind not in {"exit", "stop"}:
            continue
        if open_entry is None:
            continue
        if marker_index <= open_entry:
            continue
        trips.append((open_entry, marker_index, marker_kind))
        open_entry = None
    return trips


def infer_direction(entry_z: float, entry_band: float) -> str | None:
    if entry_z <= -abs(entry_band):
        return "LONG_SPREAD"
    if entry_z >= abs(entry_band):
        return "SHORT_SPREAD"
    return None


def compute_leg_returns_bps(
    direction: str,
    hedge_ratio: float,
    left_entry: float,
    left_exit: float,
    right_entry: float,
    right_exit: float,
) -> tuple[float, float, float]:
    if left_entry <= 0 or right_entry <= 0:
        raise ValueError("entry prices must be positive")

    left_return = (left_exit / left_entry) - 1.0
    right_return = (right_exit / right_entry) - 1.0
    hr = abs(float(hedge_ratio))

    if direction == "LONG_SPREAD":
        left_leg_return = left_return
        right_leg_return = -hr * right_return
    elif direction == "SHORT_SPREAD":
        left_leg_return = -left_return
        right_leg_return = hr * right_return
    else:
        raise ValueError(f"unsupported direction: {direction}")

    left_bps = left_leg_return * 10_000.0
    right_bps = right_leg_return * 10_000.0
    return left_bps, right_bps, left_bps + right_bps


def fetch_pair_ids(args: argparse.Namespace) -> list[str]:
    explicit_pairs = parse_pair_list(args.pairs)
    if explicit_pairs:
        return explicit_pairs
    payload = http_get_json(
        f"{args.strategy_service_url}/v1/strategy/pairs/cues",
        args.timeout_seconds,
        {"timeframe": args.timeframe, "limit": args.limit},
    )
    pairs = []
    for row in payload.get("cues", []):
        cue = row.get("cue", {})
        pair_id = cue.get("pair_id")
        if isinstance(pair_id, str) and pair_id:
            pairs.append(pair_id)
    unique: list[str] = []
    for pair in pairs:
        if pair not in unique:
            unique.append(pair)
    return unique


def fetch_history_by_pair(args: argparse.Namespace) -> dict[str, IndexedHistory]:
    payload = http_get_json(
        f"{args.strategy_service_url}/v1/strategy/pairs/opportunity-history",
        args.timeout_seconds,
        {
            "timeframe": args.timeframe,
            "hours": args.hours,
            "only_pass": "false",
            "limit": args.history_limit,
        },
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("rows", []):
        pair_id = row.get("pair_id")
        if isinstance(pair_id, str):
            grouped[pair_id].append(row)
    return {pair_id: build_history_index(rows) for pair_id, rows in grouped.items()}


def fetch_candle_series(
    data_service_url: str,
    timeout_seconds: int,
    instrument: str,
    timeframe: str,
    start_ts: dt.datetime,
    end_ts: dt.datetime,
) -> tuple[IndexedSeries, dict[str, Any]]:
    payload = http_post_json(
        f"{data_service_url}/v1/data/query",
        timeout_seconds,
        {
            "instrument": instrument,
            "timeframe": timeframe,
            "start_ts": iso(start_ts),
            "end_ts": iso(end_ts),
        },
    )
    return build_indexed_series(payload.get("candles", [])), payload.get("integrity", {})


def analyze_pair(
    args: argparse.Namespace,
    pair_id: str,
    history_index: IndexedHistory | None,
    tolerance_seconds: int,
) -> dict[str, Any]:
    backtest = http_get_json(
        f"{args.strategy_service_url}/v1/strategy/pairs/backtest",
        args.timeout_seconds,
        {
            "timeframe": args.timeframe,
            "pair_id": pair_id,
            "bars": args.bars,
            "exit_mode": args.exit_mode,
        },
    )
    points = backtest.get("points", [])
    markers = backtest.get("markers", [])
    if not points:
        return {
            "pair_id": pair_id,
            "status": "NO_POINTS",
            "trades": [],
        }

    timestamps = [parse_iso(point["ts"]) for point in points if isinstance(point.get("ts"), str)]
    if not timestamps:
        return {
            "pair_id": pair_id,
            "status": "NO_TIMESTAMPS",
            "trades": [],
        }

    step = timeframe_step(args.timeframe)
    start_ts = min(timestamps) - dt.timedelta(seconds=step)
    end_ts = max(timestamps) + dt.timedelta(seconds=step)
    left_series, left_integrity = fetch_candle_series(
        args.data_service_url,
        args.timeout_seconds,
        backtest["left_instrument"],
        args.timeframe,
        start_ts,
        end_ts,
    )
    right_series, right_integrity = fetch_candle_series(
        args.data_service_url,
        args.timeout_seconds,
        backtest["right_instrument"],
        args.timeframe,
        start_ts,
        end_ts,
    )

    round_trips = pair_markers_to_round_trips(markers, len(points))
    blocked_reason_counts: Counter[str] = Counter()
    trade_rows = []
    blocked_at_entry = 0
    pass_at_entry = 0
    unknown_gate_at_entry = 0
    profitable_blocked_net = 0
    missing_price_count = 0

    for entry_idx, exit_idx, exit_kind in round_trips:
        entry_point = points[entry_idx]
        exit_point = points[exit_idx]
        if not isinstance(entry_point.get("ts"), str) or not isinstance(exit_point.get("ts"), str):
            continue
        entry_ts = parse_iso(entry_point["ts"])
        exit_ts = parse_iso(exit_point["ts"])
        entry_epoch = int(entry_ts.timestamp())
        exit_epoch = int(exit_ts.timestamp())
        entry_z = float(entry_point.get("z", 0.0))
        exit_z = float(exit_point.get("z", 0.0))
        direction = infer_direction(entry_z, float(backtest.get("entry_band", 0.0)))

        history_row = history_index.nearest(entry_epoch, tolerance_seconds) if history_index else None
        gate_state = "UNKNOWN"
        cost_gate_pass_at_entry: bool | None = None
        edge_bps_at_entry: float | None = None
        setup_reasons: list[str] = []
        cost_reasons: list[str] = []

        if history_row is not None:
            is_actionable = bool(history_row.get("actionable"))
            gate_state = "PASS" if is_actionable else "BLOCK"
            if is_actionable:
                pass_at_entry += 1
            else:
                blocked_at_entry += 1
            cost_gate_pass_at_entry = bool(history_row.get("cost_gate_pass"))
            edge_raw = history_row.get("net_edge_bps")
            if isinstance(edge_raw, (int, float)):
                edge_bps_at_entry = float(edge_raw)
            setup_reasons = [str(code) for code in history_row.get("rationale_codes", [])]
            cost_reasons = [str(code) for code in history_row.get("cost_gate_rationale_codes", [])]
            for code in setup_reasons + cost_reasons:
                blocked_reason_counts[code] += 1
        else:
            unknown_gate_at_entry += 1

        left_entry = left_series.value_at(entry_epoch, tolerance_seconds)
        left_exit = left_series.value_at(exit_epoch, tolerance_seconds)
        right_entry = right_series.value_at(entry_epoch, tolerance_seconds)
        right_exit = right_series.value_at(exit_epoch, tolerance_seconds)

        trade_row: dict[str, Any] = {
            "entry_ts": iso(entry_ts),
            "exit_ts": iso(exit_ts),
            "entry_index": entry_idx,
            "exit_index": exit_idx,
            "bars_held": exit_idx - entry_idx,
            "entry_z": entry_z,
            "exit_z": exit_z,
            "direction": direction or "UNKNOWN",
            "exit_kind": exit_kind,
            "gate_state_at_entry": gate_state,
            "cost_gate_pass_at_entry": cost_gate_pass_at_entry,
            "net_edge_bps_at_entry": edge_bps_at_entry,
            "setup_reasons_at_entry": setup_reasons,
            "cost_reasons_at_entry": cost_reasons,
        }

        if direction is None or None in (left_entry, left_exit, right_entry, right_exit):
            missing_price_count += 1
            trade_row["pnl_status"] = "UNAVAILABLE"
            trade_rows.append(trade_row)
            continue

        left_bps, right_bps, gross_bps = compute_leg_returns_bps(
            direction=direction,
            hedge_ratio=float(backtest.get("hedge_ratio", 1.0)),
            left_entry=float(left_entry),
            left_exit=float(left_exit),
            right_entry=float(right_entry),
            right_exit=float(right_exit),
        )
        round_trip_cost_bps = float(backtest.get("round_trip_cost_bps", 0.0))
        net_bps = gross_bps - round_trip_cost_bps

        trade_row.update(
            {
                "pnl_status": "AVAILABLE",
                "left_entry": float(left_entry),
                "left_exit": float(left_exit),
                "right_entry": float(right_entry),
                "right_exit": float(right_exit),
                "left_leg_bps": left_bps,
                "right_leg_bps": right_bps,
                "gross_bps": gross_bps,
                "round_trip_cost_bps": round_trip_cost_bps,
                "net_bps": net_bps,
            }
        )
        if gate_state == "BLOCK" and net_bps > 0.0:
            profitable_blocked_net += 1

        trade_rows.append(trade_row)

    available = [trade for trade in trade_rows if trade.get("pnl_status") == "AVAILABLE"]
    gross_wins = sum(1 for trade in available if float(trade.get("gross_bps", 0.0)) > 0.0)
    net_wins = sum(1 for trade in available if float(trade.get("net_bps", 0.0)) > 0.0)
    avg_gross_bps = (
        sum(float(trade.get("gross_bps", 0.0)) for trade in available) / len(available)
        if available
        else 0.0
    )
    avg_net_bps = (
        sum(float(trade.get("net_bps", 0.0)) for trade in available) / len(available)
        if available
        else 0.0
    )
    avg_left_leg_bps = (
        sum(float(trade.get("left_leg_bps", 0.0)) for trade in available) / len(available)
        if available
        else 0.0
    )
    avg_right_leg_bps = (
        sum(float(trade.get("right_leg_bps", 0.0)) for trade in available) / len(available)
        if available
        else 0.0
    )

    return {
        "pair_id": pair_id,
        "status": "OK",
        "timeframe": args.timeframe,
        "exit_mode": args.exit_mode,
        "left_instrument": backtest.get("left_instrument"),
        "right_instrument": backtest.get("right_instrument"),
        "selected_variant": backtest.get("selected_variant"),
        "entry_band": backtest.get("entry_band"),
        "exit_band": backtest.get("exit_band"),
        "stop_band": backtest.get("stop_band"),
        "hedge_ratio": backtest.get("hedge_ratio"),
        "round_trip_cost_bps": backtest.get("round_trip_cost_bps"),
        "left_integrity": left_integrity,
        "right_integrity": right_integrity,
        "history_rows_available": len(history_index.rows) if history_index else 0,
        "trades_total": len(trade_rows),
        "trades_with_pnl": len(available),
        "entries_pass_at_entry": pass_at_entry,
        "entries_block_at_entry": blocked_at_entry,
        "entries_unknown_gate_at_entry": unknown_gate_at_entry,
        "profitable_blocked_entries_net": profitable_blocked_net,
        "missing_price_or_direction": missing_price_count,
        "gross_win_rate": (gross_wins / len(available)) if available else 0.0,
        "net_win_rate": (net_wins / len(available)) if available else 0.0,
        "avg_gross_bps": avg_gross_bps,
        "avg_net_bps": avg_net_bps,
        "avg_left_leg_bps": avg_left_leg_bps,
        "avg_right_leg_bps": avg_right_leg_bps,
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items(), key=lambda item: item[0])),
        "trades": trade_rows,
    }


def aggregate_summary(pair_reports: list[dict[str, Any]]) -> dict[str, Any]:
    trade_rows = [trade for pair in pair_reports for trade in pair.get("trades", [])]
    pnl_rows = [trade for trade in trade_rows if trade.get("pnl_status") == "AVAILABLE"]

    blocked_entries = sum(1 for trade in trade_rows if trade.get("gate_state_at_entry") == "BLOCK")
    pass_entries = sum(1 for trade in trade_rows if trade.get("gate_state_at_entry") == "PASS")
    unknown_entries = sum(1 for trade in trade_rows if trade.get("gate_state_at_entry") == "UNKNOWN")
    profitable_blocked_entries = sum(
        1
        for trade in pnl_rows
        if trade.get("gate_state_at_entry") == "BLOCK" and float(trade.get("net_bps", 0.0)) > 0.0
    )

    blocked_reason_counts: Counter[str] = Counter()
    for pair in pair_reports:
        for reason, count in pair.get("blocked_reason_counts", {}).items():
            blocked_reason_counts[str(reason)] += int(count)

    gross_win_rate = (
        sum(1 for trade in pnl_rows if float(trade.get("gross_bps", 0.0)) > 0.0) / len(pnl_rows)
        if pnl_rows
        else 0.0
    )
    net_win_rate = (
        sum(1 for trade in pnl_rows if float(trade.get("net_bps", 0.0)) > 0.0) / len(pnl_rows)
        if pnl_rows
        else 0.0
    )
    avg_gross_bps = (
        sum(float(trade.get("gross_bps", 0.0)) for trade in pnl_rows) / len(pnl_rows)
        if pnl_rows
        else 0.0
    )
    avg_net_bps = (
        sum(float(trade.get("net_bps", 0.0)) for trade in pnl_rows) / len(pnl_rows)
        if pnl_rows
        else 0.0
    )

    top_profitable_blocked = sorted(
        [
            {
                "pair_id": pair["pair_id"],
                "profitable_blocked_entries_net": pair.get("profitable_blocked_entries_net", 0),
                "entries_block_at_entry": pair.get("entries_block_at_entry", 0),
                "avg_net_bps": pair.get("avg_net_bps", 0.0),
            }
            for pair in pair_reports
            if int(pair.get("profitable_blocked_entries_net", 0)) > 0
        ],
        key=lambda row: (row["profitable_blocked_entries_net"], row["avg_net_bps"]),
        reverse=True,
    )

    return {
        "pairs_analyzed": len(pair_reports),
        "trades_total": len(trade_rows),
        "trades_with_pnl": len(pnl_rows),
        "entries_pass_at_entry": pass_entries,
        "entries_block_at_entry": blocked_entries,
        "entries_unknown_gate_at_entry": unknown_entries,
        "profitable_blocked_entries_net": profitable_blocked_entries,
        "gross_win_rate": gross_win_rate,
        "net_win_rate": net_win_rate,
        "avg_gross_bps": avg_gross_bps,
        "avg_net_bps": avg_net_bps,
        "blocked_reason_counts": dict(sorted(blocked_reason_counts.items(), key=lambda item: item[0])),
        "top_profitable_blocked_pairs": top_profitable_blocked[:10],
    }


def build_human_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            f"Signal/Gate audit ({report['timeframe']}, exit_mode={report['exit_mode']})",
            f"Pairs analyzed: {summary['pairs_analyzed']}",
            f"Trades: {summary['trades_total']} total, {summary['trades_with_pnl']} with leg-PnL",
            (
                "Entry gate states: "
                f"PASS={summary['entries_pass_at_entry']} "
                f"BLOCK={summary['entries_block_at_entry']} "
                f"UNKNOWN={summary['entries_unknown_gate_at_entry']}"
            ),
            (
                "PnL quality: "
                f"gross_win_rate={summary['gross_win_rate']:.2%} "
                f"net_win_rate={summary['net_win_rate']:.2%} "
                f"avg_net={summary['avg_net_bps']:.2f}bp"
            ),
            (
                "Blocked-but-net-profitable entries: "
                f"{summary['profitable_blocked_entries_net']}"
            ),
        ]
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    pair_ids = fetch_pair_ids(args)
    history_by_pair = fetch_history_by_pair(args)
    tolerance_seconds = max(1, args.match_tolerance_seconds)

    pair_reports = []
    errors = []
    for pair_id in pair_ids:
        try:
            pair_report = analyze_pair(
                args=args,
                pair_id=pair_id,
                history_index=history_by_pair.get(pair_id),
                tolerance_seconds=tolerance_seconds,
            )
            pair_reports.append(pair_report)
        except Exception as error:  # noqa: BLE001
            errors.append({"pair_id": pair_id, "error": str(error)})

    summary = aggregate_summary(pair_reports)
    report = {
        "generated_at": iso(utc_now()),
        "timeframe": args.timeframe,
        "hours": args.hours,
        "bars": args.bars,
        "exit_mode": args.exit_mode,
        "pair_ids": pair_ids,
        "summary": summary,
        "pairs": pair_reports,
        "errors": errors,
        "notes": [
            "Signal markers are recomputed from historical z-score thresholds.",
            "Per-trade gate state is matched from opportunity-history at nearest evaluated_at.",
            "Net PnL is modeled as gross leg PnL minus round_trip_cost_bps from backtest config.",
        ],
    }
    report["human_summary"] = build_human_summary(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:8083")
    parser.add_argument("--data-service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeframe", default="1m", choices=["1m", "15m", "1h"])
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--bars", type=int, default=600)
    parser.add_argument("--exit-mode", default="mean_revert", choices=["mean_revert", "opposite_extreme"])
    parser.add_argument("--pairs", default=None, help="Comma-separated pair ids. Defaults to live cues.")
    parser.add_argument("--limit", type=int, default=16, help="Cue fetch limit when --pairs is not supplied.")
    parser.add_argument("--history-limit", type=int, default=20_000)
    parser.add_argument("--match-tolerance-seconds", type=int, default=75)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--output-json",
        default="artifacts/analysis/signal_gate_pnl_audit.json",
    )
    args = parser.parse_args()

    args.hours = max(1, min(args.hours, 168))
    args.bars = max(120, min(args.bars, 2_000))
    args.limit = max(1, min(args.limit, 100))
    args.history_limit = max(1, min(args.history_limit, 20_000))
    args.timeout_seconds = max(3, args.timeout_seconds)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": str(error),
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
