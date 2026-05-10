#!/usr/bin/env python3
"""Monitor strategy outputs and recursively update a confidence-gated signal-logic artifact.

This script is deliberately non-invasive:
1) It reads strategy APIs.
2) It writes cycle reports, rolling state, and a proposed signal-logic file.
3) It does not mutate runtime strategy settings, DB rows, or deploy state.
"""

from __future__ import annotations

import argparse
import binascii
import datetime as dt
import json
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SUPPORTED_TIMEFRAMES = ("1m", "15m", "1h")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return utc_now().strftime("%Y-%m-%dT%H-%M-%SZ")


def parse_timeframes(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    ordered: list[str] = []
    for value in values:
        if value in SUPPORTED_TIMEFRAMES and value not in ordered:
            ordered.append(value)
    return ordered


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def trimmed_mean(values: list[float], trim_ratio: float = 0.1) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) < 5:
        return float(sum(ordered)) / float(len(ordered))
    trim_count = int(len(ordered) * trim_ratio)
    if trim_count * 2 >= len(ordered):
        return float(sum(ordered)) / float(len(ordered))
    kept = ordered[trim_count : len(ordered) - trim_count]
    if not kept:
        return float(sum(ordered)) / float(len(ordered))
    return float(sum(kept)) / float(len(kept))


def unique_codes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def pair_phase_offset(key: str, cooldown: int) -> int:
    if cooldown <= 0:
        return 0
    return binascii.crc32(key.encode("utf-8")) % cooldown


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def http_get_json(url: str, timeout_seconds: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_cues(
    strategy_service_url: str,
    timeframe: str,
    limit: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    return http_get_json(
        f"{strategy_service_url}/v1/strategy/pairs/cues",
        timeout_seconds,
        {"timeframe": timeframe, "limit": limit},
    )


def fetch_expectancy(
    strategy_service_url: str,
    pair_id: str,
    timeframe: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    return http_get_json(
        f"{strategy_service_url}/v1/strategy/pairs/expectancy",
        timeout_seconds,
        {"pair_id": pair_id, "timeframe": timeframe},
    )


def fetch_paper_trades(
    strategy_service_url: str,
    pair_id: str,
    timeframe: str,
    hours: int,
    limit: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    return http_get_json(
        f"{strategy_service_url}/v1/strategy/pairs/paper-trades",
        timeout_seconds,
        {
            "pair_id": pair_id,
            "timeframe": timeframe,
            "hours": hours,
            "limit": limit,
        },
    )


def summarize_paper_trades(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    usable = [row for row in rows if isinstance(row, dict) and isinstance(row.get("net_bps"), (int, float))]
    if not usable:
        return {
            "count": 0,
            "win_rate": 0.0,
            "avg_net_bps": 0.0,
            "median_net_bps": 0.0,
            "trimmed_mean_net_bps": 0.0,
            "avg_hold_bars": 0.0,
            "last_exit_ts": None,
        }
    net_values = [float(row.get("net_bps", 0.0)) for row in usable]
    count = len(usable)
    wins = sum(1 for value in net_values if value > 0.0)
    avg_net_bps = sum(net_values) / float(count)
    median_net_bps = float(statistics.median(net_values))
    trimmed_mean_net_bps = trimmed_mean(net_values, trim_ratio=0.1)
    avg_hold_bars = sum(float(row.get("bars_held", 0.0)) for row in usable) / float(count)
    last_exit = max(
        (str(row.get("exit_ts")) for row in usable if isinstance(row.get("exit_ts"), str)),
        default=None,
    )
    return {
        "count": count,
        "win_rate": safe_div(float(wins), float(count)),
        "avg_net_bps": avg_net_bps,
        "median_net_bps": median_net_bps,
        "trimmed_mean_net_bps": trimmed_mean_net_bps,
        "avg_hold_bars": avg_hold_bars,
        "last_exit_ts": last_exit,
    }


def compute_cycle_score(
    expectancy_metrics: dict[str, Any] | None,
    paper_summary: dict[str, Any],
    cue: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[float, list[str]]:
    gates = policy.get("confidence_gates", {})
    min_expectancy_trades = int(gates.get("min_expectancy_trades_for_score", 40))
    min_paper_trades = int(gates.get("min_paper_trades_for_score", 12))
    reasons: list[str] = []

    components: list[float] = []
    component_weights: list[float] = []

    if expectancy_metrics:
        e_trades = int(expectancy_metrics.get("trades", 0))
        if e_trades >= min_expectancy_trades:
            e_net = float(expectancy_metrics.get("p50_net_bps", expectancy_metrics.get("avg_net_bps", 0.0)))
            e_win = float(expectancy_metrics.get("win_rate", 0.0))
            expectancy_score = (
                0.55 * clamp(e_net / 20.0, -1.0, 1.0)
                + 0.35 * clamp((e_win - 0.5) / 0.2, -1.0, 1.0)
                + 0.10 * clamp(e_trades / 100.0, 0.0, 1.0)
            )
            components.append(expectancy_score)
            component_weights.append(0.5)
        else:
            reasons.append("EXPECTANCY_LOW_SAMPLE")
    else:
        reasons.append("EXPECTANCY_UNAVAILABLE")

    p_count = int(paper_summary.get("count", 0))
    if p_count >= min_paper_trades:
        p_net = float(paper_summary.get("trimmed_mean_net_bps", 0.0))
        p_win = float(paper_summary.get("win_rate", 0.0))
        paper_score = (
            0.55 * clamp(p_net / 20.0, -1.0, 1.0)
            + 0.35 * clamp((p_win - 0.5) / 0.2, -1.0, 1.0)
            + 0.10 * clamp(p_count / 80.0, 0.0, 1.0)
        )
        components.append(paper_score)
        component_weights.append(0.5)
    else:
        reasons.append("PAPER_LOW_SAMPLE")

    if not components:
        reasons.append("INSUFFICIENT_SAMPLE_FOR_SCORE")
        base_score = 0.0
    else:
        weighted_sum = sum(value * weight for value, weight in zip(components, component_weights))
        base_score = safe_div(weighted_sum, sum(component_weights))

    trade_gate = cue.get("trade_gate", {})
    gate_bias = 0.0
    if isinstance(trade_gate, dict):
        gate_bias = 0.05 if bool(trade_gate.get("pass")) else -0.05

    score = clamp(base_score + gate_bias, -1.0, 1.0)
    return score, reasons


def combine_net_metrics(
    expectancy_metrics: dict[str, Any] | None,
    paper_summary: dict[str, Any],
) -> dict[str, Any]:
    e_count = int(expectancy_metrics.get("trades", 0)) if expectancy_metrics else 0
    e_avg = float(expectancy_metrics.get("avg_net_bps", 0.0)) if expectancy_metrics else 0.0
    e_robust = float(expectancy_metrics.get("p50_net_bps", e_avg)) if expectancy_metrics else 0.0

    p_count = int(paper_summary.get("count", 0))
    p_avg = float(paper_summary.get("avg_net_bps", 0.0))
    p_robust = float(paper_summary.get("trimmed_mean_net_bps", 0.0))

    total = e_count + p_count
    if total <= 0:
        return {
            "combined_avg_net_bps": 0.0,
            "combined_robust_net_bps": 0.0,
            "combined_trades": 0,
            "expectancy_trades": e_count,
            "paper_trades": p_count,
        }
    return {
        "combined_avg_net_bps": ((e_avg * e_count) + (p_avg * p_count)) / float(total),
        "combined_robust_net_bps": ((e_robust * e_count) + (p_robust * p_count)) / float(total),
        "combined_trades": total,
        "expectancy_trades": e_count,
        "paper_trades": p_count,
    }


def evaluate_recommendation(
    *,
    history: list[dict[str, Any]],
    combined_avg_net_bps: float,
    combined_robust_net_bps: float,
    combined_trades: int,
    policy: dict[str, Any],
) -> tuple[str, float, list[str]]:
    gates = policy.get("confidence_gates", {})
    min_cycles = int(gates.get("min_cycles_for_confidence", 6))
    min_trades = int(gates.get("min_combined_trades", 20))
    min_avg = float(gates.get("min_combined_avg_net_bps", 2.0))
    min_robust = float(gates.get("min_combined_robust_net_bps", 1.5))
    max_neg = float(gates.get("max_negative_avg_net_bps", -2.0))
    max_neg_robust = float(gates.get("max_negative_robust_net_bps", -1.5))
    pos_threshold = float(gates.get("positive_cycle_score_threshold", 0.25))
    neg_threshold = float(gates.get("negative_cycle_score_threshold", -0.25))
    req_pos_ratio = float(gates.get("required_positive_cycle_ratio", 0.7))
    req_neg_ratio = float(gates.get("required_negative_cycle_ratio", 0.7))

    reasons: list[str] = []
    if len(history) < min_cycles:
        reasons.append("INSUFFICIENT_CYCLES")
        return "HOLD", 0.0, reasons
    if combined_trades < min_trades:
        reasons.append("INSUFFICIENT_TRADES")
        return "HOLD", 0.0, reasons

    scores = [float(row.get("cycle_score", 0.0)) for row in history]
    positive_ratio = safe_div(sum(1 for score in scores if score >= pos_threshold), len(scores))
    negative_ratio = safe_div(sum(1 for score in scores if score <= neg_threshold), len(scores))
    confidence = max(positive_ratio, negative_ratio)

    if (
        positive_ratio >= req_pos_ratio
        and combined_avg_net_bps >= min_avg
        and combined_robust_net_bps >= min_robust
    ):
        reasons.append("POSITIVE_STABILITY_CONFIRMED")
        return "PROMOTE", confidence, reasons
    if (
        negative_ratio >= req_neg_ratio
        and combined_avg_net_bps <= max_neg
        and combined_robust_net_bps <= max_neg_robust
    ):
        reasons.append("NEGATIVE_STABILITY_CONFIRMED")
        return "DEMOTE", confidence, reasons

    reasons.append("MIXED_SIGNAL")
    return "HOLD", confidence, reasons


def apply_mutation(
    *,
    prior: dict[str, Any],
    mutation_key: str,
    recommendation: str,
    confidence: float,
    combined_avg_net_bps: float,
    cycle_index: int,
    policy: dict[str, Any],
) -> tuple[dict[str, Any], bool, list[str]]:
    mutation = policy.get("mutation", {})
    cooldown = int(mutation.get("cooldown_cycles_between_mutations", 6))
    entry_step = float(mutation.get("entry_band_step", 0.05))
    size_step = float(mutation.get("size_step", 0.1))
    entry_min = float(mutation.get("entry_band_multiplier_min", 0.8))
    entry_max = float(mutation.get("entry_band_multiplier_max", 1.4))
    size_min = float(mutation.get("size_multiplier_min", 0.25))
    size_max = float(mutation.get("size_multiplier_max", 1.75))
    disable_cut = float(mutation.get("disable_when_size_multiplier_below", 0.3))
    severe_neg = float(mutation.get("severe_negative_avg_net_bps", -8.0))

    updated = dict(prior)
    updated.setdefault("entry_band_multiplier", 1.0)
    updated.setdefault("size_multiplier", 1.0)
    updated.setdefault("enabled", True)
    updated.setdefault("last_mutation_cycle", 0)
    updated.setdefault("mutation_phase_offset", pair_phase_offset(mutation_key, max(1, cooldown)))

    reasons: list[str] = []
    if recommendation not in {"PROMOTE", "DEMOTE"}:
        reasons.append("NO_MUTATION_FOR_HOLD")
        return updated, False, reasons
    if confidence < 0.7:
        reasons.append("LOW_CONFIDENCE")
        return updated, False, reasons

    phase_offset = int(updated.get("mutation_phase_offset", 0))
    if cooldown > 0 and ((cycle_index + phase_offset) % cooldown) != 0:
        reasons.append("MUTATION_PHASE_OFFSET_WAIT")
        return updated, False, reasons

    last_mutation = int(updated.get("last_mutation_cycle", 0))
    if cycle_index - last_mutation < cooldown:
        reasons.append("MUTATION_COOLDOWN_ACTIVE")
        return updated, False, reasons

    if recommendation == "PROMOTE":
        updated["entry_band_multiplier"] = clamp(
            float(updated["entry_band_multiplier"]) - entry_step,
            entry_min,
            entry_max,
        )
        updated["size_multiplier"] = clamp(
            float(updated["size_multiplier"]) + size_step,
            size_min,
            size_max,
        )
        updated["enabled"] = True
        reasons.append("PROMOTE_MUTATION_APPLIED")
    elif recommendation == "DEMOTE":
        updated["entry_band_multiplier"] = clamp(
            float(updated["entry_band_multiplier"]) + entry_step,
            entry_min,
            entry_max,
        )
        updated["size_multiplier"] = clamp(
            float(updated["size_multiplier"]) - size_step,
            size_min,
            size_max,
        )
        if (
            float(updated["size_multiplier"]) <= disable_cut
            and combined_avg_net_bps <= severe_neg
        ):
            updated["enabled"] = False
            reasons.append("PAIR_DISABLED_ON_SEVERE_NEGATIVE")
        reasons.append("DEMOTE_MUTATION_APPLIED")

    updated["last_mutation_cycle"] = cycle_index
    return updated, True, reasons


def apply_confidence_tier_size_cap(
    *,
    prior: dict[str, Any],
    confidence: float,
    combined_trades: int,
    policy: dict[str, Any],
) -> tuple[dict[str, Any], bool, list[str]]:
    cfg = policy.get("sizing_caps", {})
    high_conf_threshold = float(cfg.get("high_conf_threshold", 0.9))
    mid_conf_threshold = float(cfg.get("mid_conf_threshold", 0.75))
    high_conf_min_trades = int(cfg.get("high_conf_min_trades", 120))
    mid_conf_min_trades = int(cfg.get("mid_conf_min_trades", 80))
    high_cap = float(cfg.get("high_conf_cap", 1.75))
    mid_cap = float(cfg.get("mid_conf_cap", 1.25))
    low_cap = float(cfg.get("low_conf_cap", 0.9))

    updated = dict(prior)
    reasons: list[str] = []
    size_multiplier = float(updated.get("size_multiplier", 1.0))

    if confidence >= high_conf_threshold and combined_trades >= high_conf_min_trades:
        cap = high_cap
        tier = "HIGH"
    elif confidence >= mid_conf_threshold and combined_trades >= mid_conf_min_trades:
        cap = mid_cap
        tier = "MID"
    else:
        cap = low_cap
        tier = "LOW"

    updated["size_cap_tier"] = tier
    updated["size_cap_value"] = cap
    if size_multiplier > cap:
        updated["size_multiplier"] = cap
        reasons.append(f"SIZE_CAP_TIER_{tier}_APPLIED")
        return updated, True, reasons
    return updated, False, reasons


def build_default_logic_entry(pair_id: str, timeframe: str) -> dict[str, Any]:
    return {
        "pair_id": pair_id,
        "timeframe": timeframe,
        "enabled": True,
        "trade_eligible": False,
        "entry_band_multiplier": 1.0,
        "size_multiplier": 1.0,
        "size_cap_tier": "LOW",
        "size_cap_value": 0.9,
        "last_mutation_cycle": 0,
        "mutation_phase_offset": 0,
        "recommendation": "HOLD",
        "confidence": 0.0,
        "reason_codes": ["INITIALIZED"],
        "arbitration_reason_codes": ["NOT_EVALUATED"],
        "evidence": {},
    }


def find_hard_veto_rule(policy: dict[str, Any], pair_id: str, timeframe: str) -> dict[str, Any] | None:
    rules = policy.get("hard_vetoes", [])
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not bool(rule.get("enabled", False)):
            continue
        if str(rule.get("pair_id", "")) != pair_id:
            continue
        if str(rule.get("timeframe", "")) != timeframe:
            continue
        return rule
    return None


def is_hard_veto_recovered(
    history: list[dict[str, Any]],
    rule: dict[str, Any],
    policy: dict[str, Any],
) -> bool:
    recovery = rule.get("recovery", {})
    if not isinstance(recovery, dict):
        return False
    min_cycles = int(recovery.get("min_cycles", 12))
    min_confidence = float(recovery.get("min_confidence", 0.8))
    min_trades = int(recovery.get("min_trades", 140))
    min_robust = float(recovery.get("min_robust_net_bps", 3.0))
    req_pos_ratio = float(recovery.get("required_positive_ratio", 0.75))
    pos_threshold = float(policy.get("confidence_gates", {}).get("positive_cycle_score_threshold", 0.25))

    if len(history) < min_cycles:
        return False
    window = history[-min_cycles:]
    positive_ratio = safe_div(
        sum(1 for row in window if float(row.get("cycle_score", 0.0)) >= pos_threshold),
        len(window),
    )
    latest = window[-1]
    latest_confidence = float(latest.get("recommendation_confidence", 0.0))
    latest_trades = int(latest.get("combined_trades", 0))
    latest_robust = float(latest.get("combined_robust_net_bps", 0.0))

    return (
        latest_confidence >= min_confidence
        and latest_trades >= min_trades
        and latest_robust >= min_robust
        and positive_ratio >= req_pos_ratio
    )


def apply_cross_timeframe_arbitration(
    *,
    rows_by_pair: dict[str, list[dict[str, Any]]],
    logic_pairs: dict[str, dict[str, Any]],
    state_pairs: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, int]:
    arbitration = policy.get("arbitration", {})
    arbitration_enabled = bool(arbitration.get("enabled", True))
    min_timeframes_for_enable = int(arbitration.get("min_timeframes_for_enable", 2))
    min_confidence_for_promote = float(arbitration.get("min_confidence_for_promote", 0.75))
    min_trades_per_timeframe = int(arbitration.get("min_trades_per_timeframe", 50))
    demote_veto_confidence = float(arbitration.get("demote_veto_confidence", 0.8))
    demote_veto_min_trades = int(arbitration.get("demote_veto_min_trades", 80))

    arbitration_summary = {
        "pairs_with_veto": 0,
        "pairs_with_consensus": 0,
        "hard_veto_timeframes": 0,
        "trade_eligible_timeframes": 0,
    }

    for pair_id, rows in rows_by_pair.items():
        pair_veto = False
        pair_veto_codes: list[str] = []
        hard_veto_rows = 0
        qualified_promotes = 0

        for row in rows:
            row["hard_veto_active"] = False
            row["hard_veto_reason"] = None
            rule = find_hard_veto_rule(policy, pair_id, str(row.get("timeframe", "")))
            if rule is None:
                continue
            history = state_pairs.get(str(row.get("_logic_key", "")), {}).get("history", [])
            if not isinstance(history, list):
                history = []
            recovered = is_hard_veto_recovered(history, rule, policy)
            if recovered:
                row["hard_veto_recovered"] = True
                continue
            row["hard_veto_active"] = True
            row["hard_veto_recovered"] = False
            row["hard_veto_reason"] = str(rule.get("veto_reason", "HARD_VETO_ACTIVE"))
            pair_veto = True
            hard_veto_rows += 1
            pair_veto_codes.append(str(row["hard_veto_reason"]))

        demote_veto = any(
            str(row.get("recommendation")) == "DEMOTE"
            and float(row.get("confidence", 0.0)) >= demote_veto_confidence
            and int(row.get("combined_trades", 0)) >= demote_veto_min_trades
            for row in rows
        )
        if demote_veto:
            pair_veto = True
            pair_veto_codes.append("PAIR_DEMOTE_VETO")

        for row in rows:
            is_qualified = (
                str(row.get("recommendation")) == "PROMOTE"
                and float(row.get("confidence", 0.0)) >= min_confidence_for_promote
                and int(row.get("combined_trades", 0)) >= min_trades_per_timeframe
                and not bool(row.get("hard_veto_active", False))
            )
            if is_qualified:
                qualified_promotes += 1

        pair_consensus = qualified_promotes >= min_timeframes_for_enable
        if pair_veto:
            arbitration_summary["pairs_with_veto"] += 1
        if pair_consensus:
            arbitration_summary["pairs_with_consensus"] += 1
        arbitration_summary["hard_veto_timeframes"] += hard_veto_rows

        for row in rows:
            arb_reasons: list[str] = []
            if bool(row.get("hard_veto_active", False)):
                arb_reasons.append(str(row.get("hard_veto_reason", "HARD_VETO_ACTIVE")))
            if demote_veto:
                arb_reasons.append("PAIR_DEMOTE_VETO")
            if arbitration_enabled and not pair_consensus:
                arb_reasons.append("PAIR_CROSS_TF_CONSENSUS_NOT_MET")

            row_conf = float(row.get("confidence", 0.0))
            row_trades = int(row.get("combined_trades", 0))
            if row_conf < min_confidence_for_promote:
                arb_reasons.append("ROW_CONFIDENCE_BELOW_PROMOTE_THRESHOLD")
            if row_trades < min_trades_per_timeframe:
                arb_reasons.append("ROW_TRADES_BELOW_PROMOTE_THRESHOLD")

            row_enabled = bool(row.get("enabled", True))
            row_promote = str(row.get("recommendation")) == "PROMOTE"
            row_trade_eligible = (
                row_enabled
                and row_promote
                and not pair_veto
                and (not arbitration_enabled or pair_consensus)
                and row_conf >= min_confidence_for_promote
                and row_trades >= min_trades_per_timeframe
                and not bool(row.get("hard_veto_active", False))
            )
            row["trade_eligible"] = row_trade_eligible
            row["arbitration_reason_codes"] = unique_codes(arb_reasons)
            if row_trade_eligible:
                arbitration_summary["trade_eligible_timeframes"] += 1

            logic_key = str(row.get("_logic_key", ""))
            if logic_key in logic_pairs:
                logic_pairs[logic_key]["trade_eligible"] = row_trade_eligible
                logic_pairs[logic_key]["arbitration_reason_codes"] = row["arbitration_reason_codes"]
                logic_pairs[logic_key]["hard_veto_active"] = bool(row.get("hard_veto_active", False))
                logic_pairs[logic_key]["hard_veto_reason"] = row.get("hard_veto_reason")
                merged_codes = unique_codes(
                    [*logic_pairs[logic_key].get("reason_codes", []), *row["arbitration_reason_codes"]]
                )
                logic_pairs[logic_key]["reason_codes"] = merged_codes

    return arbitration_summary


def parse_left_base_asset(pair_id: str) -> str:
    left = pair_id.split("__", 1)[0]
    for prefix in ("PF_", "PI_", "FI_"):
        if left.startswith(prefix):
            left = left[len(prefix) :]
            break
    if left.endswith("USD") and len(left) > 3:
        left = left[:-3]
    return left or "UNKNOWN"


def compute_selection_utility(row: dict[str, Any], selection_cfg: dict[str, Any]) -> float:
    weights = selection_cfg.get("weights", {})
    w_cycle = float(weights.get("cycle_score", 0.35))
    w_conf = float(weights.get("confidence", 0.25))
    w_robust = float(weights.get("robust_net_bps", 0.25))
    w_depth = float(weights.get("trade_depth", 0.15))

    robust_scale_bps = float(selection_cfg.get("robust_scale_bps", 20.0))
    depth_scale_trades = float(selection_cfg.get("depth_scale_trades", 120.0))

    cycle_component = clamp((float(row.get("cycle_score", 0.0)) + 1.0) / 2.0, 0.0, 1.0)
    confidence_component = clamp(float(row.get("confidence", 0.0)), 0.0, 1.0)
    robust_component = clamp(float(row.get("combined_robust_net_bps", 0.0)) / max(0.1, robust_scale_bps), 0.0, 1.0)
    depth_component = clamp(float(row.get("combined_trades", 0.0)) / max(1.0, depth_scale_trades), 0.0, 1.0)

    return (
        w_cycle * cycle_component
        + w_conf * confidence_component
        + w_robust * robust_component
        + w_depth * depth_component
    )


def apply_selection_reason_penalties(
    row: dict[str, Any],
    base_utility: float,
    selection_cfg: dict[str, Any],
) -> float:
    penalties = selection_cfg.get("reason_penalties", {})
    if not isinstance(penalties, dict):
        return clamp(base_utility, 0.0, 1.0)

    utility = base_utility
    row_reasons = [*list(row.get("reason_codes", [])), *list(row.get("arbitration_reason_codes", []))]
    for reason in row_reasons:
        penalty = penalties.get(reason)
        if isinstance(penalty, (int, float)):
            utility -= float(penalty)
    return clamp(utility, 0.0, 1.0)


def apply_universe_selection(
    *,
    timeframe_rows_map: dict[str, list[dict[str, Any]]],
    logic_pairs: dict[str, dict[str, Any]],
    selection_state: dict[str, Any] | None = None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    selection_cfg = policy.get("selection", {})
    confidence_gates = policy.get("confidence_gates", {})
    enabled = bool(selection_cfg.get("enabled", True))
    top_k = max(1, int(selection_cfg.get("top_k", 3)))
    min_utility_score = float(selection_cfg.get("min_utility_score", 0.45))
    min_paper_trades_for_selection = int(
        selection_cfg.get(
            "min_paper_trades_for_selection",
            confidence_gates.get("min_paper_trades_for_score", 12),
        )
    )
    allow_low_sample_backfill = bool(selection_cfg.get("allow_low_sample_backfill", True))
    max_per_base_asset = max(1, int(selection_cfg.get("max_per_base_asset", 1)))
    dwell_penalty_start_cycles = int(selection_cfg.get("dwell_penalty_start_cycles", 24))
    dwell_penalty_per_cycle = float(selection_cfg.get("dwell_penalty_per_cycle", 0.01))
    dwell_penalty_cap = float(selection_cfg.get("dwell_penalty_cap", 0.20))

    for rows in timeframe_rows_map.values():
        for row in rows:
            row["selection_utility"] = None
            row["selection_selected"] = False
            logic_key = str(row.get("_logic_key", ""))
            if logic_key in logic_pairs:
                logic_pairs[logic_key]["selection_utility"] = None
                logic_pairs[logic_key]["selection_selected"] = False

    if not enabled:
        return {
            "enabled": False,
            "candidate_count": 0,
            "qualified_count": 0,
            "selected_count": 0,
            "selected_with_paper_low_sample_count": 0,
            "top1_dwell_cycles_by_pair_tf": {},
            "selection_turnover_rate": 0.0,
            "top_1": None,
            "top_k": [],
        }

    candidates: list[dict[str, Any]] = []
    last_top1_key = None
    top1_dwell_map: dict[str, Any] = {}
    if selection_state is not None:
        maybe_last_top1_key = selection_state.get("last_top1_key")
        if isinstance(maybe_last_top1_key, str):
            last_top1_key = maybe_last_top1_key
        maybe_dwell_map = selection_state.get("top1_dwell_cycles_by_pair_tf")
        if isinstance(maybe_dwell_map, dict):
            top1_dwell_map = maybe_dwell_map

    for rows in timeframe_rows_map.values():
        for row in rows:
            if not bool(row.get("trade_eligible", False)):
                continue
            raw_utility = compute_selection_utility(row, selection_cfg)
            utility = apply_selection_reason_penalties(row, raw_utility, selection_cfg)
            if (
                last_top1_key is not None
                and dwell_penalty_cap > 0.0
                and dwell_penalty_per_cycle > 0.0
            ):
                row_key = f"{row.get('pair_id', '')}|{row.get('timeframe', '')}"
                if row_key == last_top1_key:
                    dwell_cycles = int(top1_dwell_map.get(row_key, 0))
                    if dwell_cycles >= dwell_penalty_start_cycles:
                        cycles_over = dwell_cycles - dwell_penalty_start_cycles + 1
                        penalty = min(dwell_penalty_cap, max(0.0, cycles_over * dwell_penalty_per_cycle))
                        post_penalty = clamp(utility - penalty, 0.0, 1.0)
                        if post_penalty < utility:
                            reason_codes = row.get("reason_codes")
                            if not isinstance(reason_codes, list):
                                reason_codes = []
                                row["reason_codes"] = reason_codes
                            if "TOP1_DWELL_PENALTY_APPLIED" not in reason_codes:
                                reason_codes.append("TOP1_DWELL_PENALTY_APPLIED")
                        utility = post_penalty
            row["selection_utility"] = round(utility, 6)
            candidates.append(row)

    qualified = [row for row in candidates if float(row.get("selection_utility", 0.0)) >= min_utility_score]
    qualified.sort(
        key=lambda row: (
            -float(row.get("selection_utility", 0.0)),
            -float(row.get("confidence", 0.0)),
            -float(row.get("combined_robust_net_bps", 0.0)),
            -float(row.get("combined_trades", 0.0)),
            str(row.get("pair_id", "")),
            str(row.get("timeframe", "")),
        )
    )
    qualified_primary = [
        row for row in qualified if int(row.get("paper_trades", 0)) >= min_paper_trades_for_selection
    ]
    qualified_backfill = [
        row for row in qualified if int(row.get("paper_trades", 0)) < min_paper_trades_for_selection
    ]

    selected: list[dict[str, Any]] = []
    base_counts: dict[str, int] = defaultdict(int)

    def maybe_select_row(row: dict[str, Any], *, low_sample_backfill: bool) -> bool:
        base = parse_left_base_asset(str(row.get("pair_id", "")))
        if base_counts[base] >= max_per_base_asset:
            return False
        if low_sample_backfill:
            reason_codes = row.get("reason_codes")
            if not isinstance(reason_codes, list):
                reason_codes = []
                row["reason_codes"] = reason_codes
            if "SELECTION_LOW_SAMPLE_BACKFILL" not in reason_codes:
                reason_codes.append("SELECTION_LOW_SAMPLE_BACKFILL")
        row["selection_selected"] = True
        logic_key = str(row.get("_logic_key", ""))
        if logic_key in logic_pairs:
            logic_pairs[logic_key]["selection_selected"] = True
            logic_pairs[logic_key]["selection_utility"] = row.get("selection_utility")
            if low_sample_backfill:
                logic_reason_codes = logic_pairs[logic_key].get("reason_codes")
                if not isinstance(logic_reason_codes, list):
                    logic_reason_codes = []
                logic_pairs[logic_key]["reason_codes"] = unique_codes(
                    [*logic_reason_codes, "SELECTION_LOW_SAMPLE_BACKFILL"]
                )
        selected.append(row)
        base_counts[base] += 1
        return len(selected) >= top_k

    for row in qualified_primary:
        if maybe_select_row(row, low_sample_backfill=False):
            break
    if len(selected) < top_k and allow_low_sample_backfill:
        for row in qualified_backfill:
            if maybe_select_row(row, low_sample_backfill=True):
                break

    selected_with_paper_low_sample_count = sum(
        1 for row in selected if "PAPER_LOW_SAMPLE" in set(row.get("reason_codes", []))
    )

    def public_selection_view(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "pair_id": str(row.get("pair_id", "")),
            "timeframe": str(row.get("timeframe", "")),
            "selection_utility": float(row.get("selection_utility", 0.0)),
            "confidence": float(row.get("confidence", 0.0)),
            "combined_robust_net_bps": float(row.get("combined_robust_net_bps", 0.0)),
            "combined_trades": int(row.get("combined_trades", 0)),
            "reason_codes": list(row.get("reason_codes", [])),
            "arbitration_reason_codes": list(row.get("arbitration_reason_codes", [])),
        }

    top_public = [public_selection_view(row) for row in selected]
    top_1 = top_public[0] if top_public else None

    top1_dwell_cycles_by_pair_tf: dict[str, int] = {}
    selection_turnover_rate = 0.0
    if selection_state is not None:
        if not isinstance(selection_state.get("top1_dwell_cycles_by_pair_tf"), dict):
            selection_state["top1_dwell_cycles_by_pair_tf"] = {}
        dwell_map = dict(selection_state.get("top1_dwell_cycles_by_pair_tf", {}))
        observed_cycles = int(selection_state.get("observed_cycles", 0)) + 1
        switches = int(selection_state.get("top1_switches", 0))
        last_top1_key = selection_state.get("last_top1_key")
        current_top1_key = None
        if top_1 is not None:
            current_top1_key = f"{top_1['pair_id']}|{top_1['timeframe']}"
            dwell_map[current_top1_key] = int(dwell_map.get(current_top1_key, 0)) + 1
        if (
            isinstance(last_top1_key, str)
            and isinstance(current_top1_key, str)
            and last_top1_key != current_top1_key
        ):
            switches += 1
        selection_state["observed_cycles"] = observed_cycles
        selection_state["top1_switches"] = switches
        selection_state["last_top1_key"] = current_top1_key
        selection_state["top1_dwell_cycles_by_pair_tf"] = dwell_map
        top1_dwell_cycles_by_pair_tf = {str(k): int(v) for k, v in dwell_map.items()}
        selection_turnover_rate = round(safe_div(float(switches), float(max(1, observed_cycles - 1))), 6)

    return {
        "enabled": True,
        "candidate_count": len(candidates),
        "qualified_count": len(qualified),
        "selected_count": len(top_public),
        "selected_with_paper_low_sample_count": selected_with_paper_low_sample_count,
        "top1_dwell_cycles_by_pair_tf": top1_dwell_cycles_by_pair_tf,
        "selection_turnover_rate": selection_turnover_rate,
        "top_1": top_1,
        "top_k": top_public,
    }


def run_one_cycle(
    *,
    strategy_service_url: str,
    timeframes: list[str],
    policy: dict[str, Any],
    timeout_seconds: int,
    cycle_index: int,
    state_payload: dict[str, Any],
    logic_payload: dict[str, Any],
) -> dict[str, Any]:
    sampling = policy.get("sampling", {})
    cues_limit = int(sampling.get("cues_limit", 20))
    paper_hours = int(sampling.get("paper_hours", 72))
    paper_limit = int(sampling.get("paper_limit", 800))

    state_pairs = state_payload.setdefault("pairs", {})
    logic_pairs = logic_payload.setdefault("pairs", {})
    max_history = int(policy.get("confidence_gates", {}).get("max_history_points", 120))

    timeframe_rows_map: dict[str, list[dict[str, Any]]] = {timeframe: [] for timeframe in timeframes}
    timeframe_errors_map: dict[str, list[dict[str, Any]]] = {timeframe: [] for timeframe in timeframes}
    rows_by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)

    promoted = 0
    demoted = 0
    holds = 0
    mutated = 0

    for timeframe in timeframes:
        try:
            cues_payload = fetch_cues(strategy_service_url, timeframe, cues_limit, timeout_seconds)
            cue_rows = cues_payload.get("cues", [])
            if not isinstance(cue_rows, list):
                cue_rows = []
        except Exception as error:  # noqa: BLE001
            timeframe_errors_map[timeframe].append({"stage": "cues", "error": str(error)})
            continue

        for cue_row in cue_rows:
            cue = cue_row.get("cue", {})
            pair_id = cue.get("pair_id")
            if not isinstance(pair_id, str) or not pair_id:
                continue
            logic_key = f"{timeframe}|{pair_id}"
            expectancy_payload: dict[str, Any] = {}
            paper_payload: dict[str, Any] = {}
            expectancy_metrics: dict[str, Any] | None = None

            try:
                expectancy_payload = fetch_expectancy(
                    strategy_service_url,
                    pair_id,
                    timeframe,
                    timeout_seconds,
                )
                if expectancy_payload.get("status") == "AVAILABLE":
                    metrics = expectancy_payload.get("metrics")
                    if isinstance(metrics, dict):
                        expectancy_metrics = metrics
            except Exception as error:  # noqa: BLE001
                timeframe_errors_map[timeframe].append(
                    {"pair_id": pair_id, "stage": "expectancy", "error": str(error)}
                )

            try:
                paper_payload = fetch_paper_trades(
                    strategy_service_url,
                    pair_id,
                    timeframe,
                    paper_hours,
                    paper_limit,
                    timeout_seconds,
                )
            except Exception as error:  # noqa: BLE001
                timeframe_errors_map[timeframe].append(
                    {"pair_id": pair_id, "stage": "paper_trades", "error": str(error)}
                )
                paper_payload = {"rows": []}

            paper_summary = summarize_paper_trades(paper_payload)
            cycle_score, score_reasons = compute_cycle_score(expectancy_metrics, paper_summary, cue, policy)
            combined = combine_net_metrics(expectancy_metrics, paper_summary)
            combined_avg_net_bps = float(combined["combined_avg_net_bps"])
            combined_robust_net_bps = float(combined["combined_robust_net_bps"])
            combined_trades = int(combined["combined_trades"])

            state_entry = state_pairs.setdefault(
                logic_key,
                {"pair_id": pair_id, "timeframe": timeframe, "history": []},
            )
            history = state_entry.setdefault("history", [])
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "ts": utc_now_iso(),
                    "cycle_score": cycle_score,
                    "combined_avg_net_bps": combined_avg_net_bps,
                    "combined_robust_net_bps": combined_robust_net_bps,
                    "combined_trades": combined_trades,
                    "expectancy_avg_net_bps": float(expectancy_metrics.get("avg_net_bps", 0.0))
                    if expectancy_metrics
                    else 0.0,
                    "expectancy_robust_net_bps": float(expectancy_metrics.get("p50_net_bps", 0.0))
                    if expectancy_metrics
                    else 0.0,
                    "paper_avg_net_bps": float(paper_summary.get("avg_net_bps", 0.0)),
                    "paper_robust_net_bps": float(paper_summary.get("trimmed_mean_net_bps", 0.0)),
                }
            )
            if len(history) > max_history:
                history = history[-max_history:]
            state_entry["history"] = history

            recommendation, confidence, rec_reasons = evaluate_recommendation(
                history=history,
                combined_avg_net_bps=combined_avg_net_bps,
                combined_robust_net_bps=combined_robust_net_bps,
                combined_trades=combined_trades,
                policy=policy,
            )
            history[-1]["recommendation_confidence"] = confidence

            prior_logic = logic_pairs.get(logic_key, build_default_logic_entry(pair_id, timeframe))
            updated_logic, did_mutate, mutation_reasons = apply_mutation(
                prior=prior_logic,
                mutation_key=logic_key,
                recommendation=recommendation,
                confidence=confidence,
                combined_avg_net_bps=combined_avg_net_bps,
                cycle_index=cycle_index,
                policy=policy,
            )
            updated_logic, _, size_cap_reasons = apply_confidence_tier_size_cap(
                prior=updated_logic,
                confidence=confidence,
                combined_trades=combined_trades,
                policy=policy,
            )

            reason_codes = unique_codes([*score_reasons, *rec_reasons, *mutation_reasons, *size_cap_reasons])
            updated_logic.update(
                {
                    "pair_id": pair_id,
                    "timeframe": timeframe,
                    "recommendation": recommendation,
                    "confidence": round(confidence, 6),
                    "reason_codes": reason_codes,
                    "evidence": {
                        "combined_trades": combined_trades,
                        "expectancy_trades": int(combined["expectancy_trades"]),
                        "paper_trades": int(combined["paper_trades"]),
                        "combined_avg_net_bps": round(combined_avg_net_bps, 6),
                        "combined_robust_net_bps": round(combined_robust_net_bps, 6),
                        "latest_cycle_score": round(cycle_score, 6),
                        "history_points": len(history),
                        "expectancy_status": expectancy_payload.get("status"),
                        "expectancy_decision_state": expectancy_payload.get("decision_state"),
                        "paper_trade_count": paper_summary.get("count", 0),
                    },
                }
            )
            logic_pairs[logic_key] = updated_logic

            if recommendation == "PROMOTE":
                promoted += 1
            elif recommendation == "DEMOTE":
                demoted += 1
            else:
                holds += 1
            if did_mutate:
                mutated += 1

            row = {
                "_logic_key": logic_key,
                "pair_id": pair_id,
                "timeframe": timeframe,
                "recommendation": recommendation,
                "confidence": round(confidence, 6),
                "cycle_score": round(cycle_score, 6),
                "combined_avg_net_bps": round(combined_avg_net_bps, 6),
                "combined_robust_net_bps": round(combined_robust_net_bps, 6),
                "combined_trades": combined_trades,
                "expectancy_trades": int(combined["expectancy_trades"]),
                "paper_trades": int(combined["paper_trades"]),
                "entry_band_multiplier": round(float(updated_logic["entry_band_multiplier"]), 6),
                "size_multiplier": round(float(updated_logic["size_multiplier"]), 6),
                "size_cap_tier": str(updated_logic.get("size_cap_tier", "LOW")),
                "enabled": bool(updated_logic["enabled"]),
                "mutated": did_mutate,
                "reason_codes": reason_codes,
                "trade_eligible": False,
                "arbitration_reason_codes": [],
            }
            timeframe_rows_map[timeframe].append(row)
            rows_by_pair[pair_id].append(row)

    arbitration_summary = apply_cross_timeframe_arbitration(
        rows_by_pair=rows_by_pair,
        logic_pairs=logic_pairs,
        state_pairs=state_pairs,
        policy=policy,
    )
    selection_summary = apply_universe_selection(
        timeframe_rows_map=timeframe_rows_map,
        logic_pairs=logic_pairs,
        selection_state=state_payload.setdefault("selection_state", {}),
        policy=policy,
    )

    timeframe_reports: list[dict[str, Any]] = []
    for timeframe in timeframes:
        rows = timeframe_rows_map.get(timeframe, [])
        public_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
        errors = timeframe_errors_map.get(timeframe, [])
        timeframe_reports.append(
            {
                "timeframe": timeframe,
                "status": "OK" if not errors else "DEGRADED",
                "pair_count": len(public_rows),
                "trade_eligible_count": sum(1 for row in public_rows if bool(row.get("trade_eligible"))),
                "selected_count": sum(1 for row in public_rows if bool(row.get("selection_selected"))),
                "errors": errors,
                "pairs": public_rows,
            }
        )

    summary = {
        "pairs_evaluated": sum(int(row.get("pair_count", 0)) for row in timeframe_reports),
        "promote_recommendations": promoted,
        "demote_recommendations": demoted,
        "hold_recommendations": holds,
        "mutated_pairs": mutated,
        "trade_eligible_timeframes": int(arbitration_summary["trade_eligible_timeframes"]),
        "pairs_with_consensus": int(arbitration_summary["pairs_with_consensus"]),
        "pairs_with_veto": int(arbitration_summary["pairs_with_veto"]),
        "hard_veto_timeframes": int(arbitration_summary["hard_veto_timeframes"]),
        "selection_selected_count": int(selection_summary["selected_count"]),
        "degraded_timeframes": sum(1 for row in timeframe_reports if row.get("status") == "DEGRADED"),
    }
    return {"summary": summary, "timeframes": timeframe_reports, "selection": selection_summary}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:18083")
    parser.add_argument("--timeframes", default="1m,15m,1h")
    parser.add_argument("--policy-json", default="infra/config/signal_learning_policy.json")
    parser.add_argument("--state-json", default="artifacts/signal_learning/state.json")
    parser.add_argument("--logic-json", default="artifacts/signal_learning/signal_logic.json")
    parser.add_argument("--output-root", default="artifacts/signal_learning/runs")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timeframes = parse_timeframes(args.timeframes)
    if not timeframes:
        raise SystemExit("No valid timeframe provided. Use 1m,15m,1h.")
    if args.cycles <= 0:
        raise SystemExit("--cycles must be >= 1")

    policy_path = Path(args.policy_json)
    state_path = Path(args.state_json)
    logic_path = Path(args.logic_json)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    policy = load_json(policy_path)

    if state_path.exists():
        state_payload = load_json(state_path)
    else:
        state_payload = {"schema_version": "1.0.0", "updated_at": utc_now_iso(), "cycle_index": 0, "pairs": {}}

    if logic_path.exists():
        logic_payload = load_json(logic_path)
    else:
        logic_payload = {"schema_version": "1.0.0", "generated_at": utc_now_iso(), "pairs": {}}

    for cycle_offset in range(args.cycles):
        cycle_index = int(state_payload.get("cycle_index", 0)) + 1
        cycle_started = utc_now_iso()
        run = run_one_cycle(
            strategy_service_url=args.strategy_service_url.rstrip("/"),
            timeframes=timeframes,
            policy=policy,
            timeout_seconds=args.timeout_seconds,
            cycle_index=cycle_index,
            state_payload=state_payload,
            logic_payload=logic_payload,
        )
        cycle_finished = utc_now_iso()

        state_payload["cycle_index"] = cycle_index
        state_payload["updated_at"] = cycle_finished
        logic_payload["generated_at"] = cycle_finished
        logic_payload["source_cycle_index"] = cycle_index
        logic_payload["policy_path"] = str(policy_path)

        cycle_report = {
            "schema_version": "1.0.0",
            "generated_at": cycle_finished,
            "cycle_index": cycle_index,
            "started_at": cycle_started,
            "finished_at": cycle_finished,
            "strategy_service_url": args.strategy_service_url,
            "policy_path": str(policy_path),
            "state_path": str(state_path),
            "logic_path": str(logic_path),
            "timeframes": timeframes,
            "summary": run["summary"],
            "selection": run["selection"],
            "timeframe_reports": run["timeframes"],
            "notes": [
                "This cycle is observational and recommendation-only.",
                "No runtime strategy settings are modified by this script.",
                "Cross-timeframe arbitration and hard-veto rules gate trade eligibility.",
                "Universe selection ranks eligible candidates and outputs top recommendations only.",
            ],
        }

        cycle_path = output_root / f"{utc_stamp()}-signal-learning-cycle.json"
        write_json(cycle_path, cycle_report)
        write_json(state_path, state_payload)
        write_json(logic_path, logic_payload)

        print(
            f"[cycle {cycle_index}] pairs={cycle_report['summary']['pairs_evaluated']} "
            f"promote={cycle_report['summary']['promote_recommendations']} "
            f"demote={cycle_report['summary']['demote_recommendations']} "
            f"eligible={cycle_report['summary']['trade_eligible_timeframes']} "
            f"mutated={cycle_report['summary']['mutated_pairs']} "
            f"report={cycle_path}"
        )

        if cycle_offset < args.cycles - 1:
            time.sleep(max(1, args.sleep_seconds))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
