from __future__ import annotations

import pathlib
import sys
from copy import deepcopy

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import signal_learning_cycle as learning  # noqa: E402


BASE_POLICY = {
    "confidence_gates": {
        "min_cycles_for_confidence": 6,
        "min_combined_trades": 20,
        "min_expectancy_trades_for_score": 40,
        "min_paper_trades_for_score": 12,
        "min_combined_avg_net_bps": 2.0,
        "min_combined_robust_net_bps": 1.5,
        "max_negative_avg_net_bps": -2.0,
        "max_negative_robust_net_bps": -1.5,
        "positive_cycle_score_threshold": 0.25,
        "negative_cycle_score_threshold": -0.25,
        "required_positive_cycle_ratio": 0.7,
        "required_negative_cycle_ratio": 0.7,
        "max_history_points": 120,
    },
    "arbitration": {
        "enabled": True,
        "min_timeframes_for_enable": 2,
        "min_confidence_for_promote": 0.75,
        "min_trades_per_timeframe": 50,
        "demote_veto_confidence": 0.8,
        "demote_veto_min_trades": 80,
    },
    "sizing_caps": {
        "high_conf_threshold": 0.9,
        "mid_conf_threshold": 0.75,
        "high_conf_min_trades": 120,
        "mid_conf_min_trades": 80,
        "high_conf_cap": 1.75,
        "mid_conf_cap": 1.25,
        "low_conf_cap": 0.9,
    },
    "selection": {
        "enabled": True,
        "top_k": 3,
        "min_utility_score": 0.45,
        "min_paper_trades_for_selection": 12,
        "allow_low_sample_backfill": True,
        "max_per_base_asset": 1,
        "robust_scale_bps": 20.0,
        "depth_scale_trades": 120.0,
        "weights": {
            "cycle_score": 0.35,
            "confidence": 0.25,
            "robust_net_bps": 0.25,
            "trade_depth": 0.15,
        },
        "reason_penalties": {
            "PAPER_LOW_SAMPLE": 0.03,
        },
    },
    "hard_vetoes": [],
    "mutation": {
        "cooldown_cycles_between_mutations": 6,
        "entry_band_step": 0.05,
        "size_step": 0.1,
        "entry_band_multiplier_min": 0.8,
        "entry_band_multiplier_max": 1.4,
        "size_multiplier_min": 0.25,
        "size_multiplier_max": 1.75,
        "disable_when_size_multiplier_below": 0.3,
        "severe_negative_avg_net_bps": -8.0,
    },
}


def history_with_score(score: float, count: int) -> list[dict[str, float]]:
    return [{"cycle_score": score} for _ in range(count)]


def test_recommendation_holds_when_cycles_insufficient() -> None:
    decision, confidence, reasons = learning.evaluate_recommendation(
        history=history_with_score(0.5, 3),
        combined_avg_net_bps=5.0,
        combined_robust_net_bps=5.0,
        combined_trades=100,
        policy=BASE_POLICY,
    )
    assert decision == "HOLD"
    assert confidence == 0.0
    assert "INSUFFICIENT_CYCLES" in reasons


def test_recommendation_promote_on_stable_positive_signal() -> None:
    decision, confidence, reasons = learning.evaluate_recommendation(
        history=history_with_score(0.5, 10),
        combined_avg_net_bps=6.0,
        combined_robust_net_bps=6.0,
        combined_trades=80,
        policy=BASE_POLICY,
    )
    assert decision == "PROMOTE"
    assert confidence >= 0.7
    assert "POSITIVE_STABILITY_CONFIRMED" in reasons


def test_recommendation_demote_on_stable_negative_signal() -> None:
    decision, confidence, reasons = learning.evaluate_recommendation(
        history=history_with_score(-0.6, 10),
        combined_avg_net_bps=-4.0,
        combined_robust_net_bps=-4.0,
        combined_trades=80,
        policy=BASE_POLICY,
    )
    assert decision == "DEMOTE"
    assert confidence >= 0.7
    assert "NEGATIVE_STABILITY_CONFIRMED" in reasons


def test_apply_mutation_respects_phase_offset() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["mutation"]["cooldown_cycles_between_mutations"] = 6
    updated, mutated, reasons = learning.apply_mutation(
        prior={
            "entry_band_multiplier": 1.0,
            "size_multiplier": 1.0,
            "enabled": True,
            "last_mutation_cycle": 0,
            "mutation_phase_offset": 2,
        },
        mutation_key="1m|PF_XBTUSD__PF_SOLUSD",
        recommendation="PROMOTE",
        confidence=0.9,
        combined_avg_net_bps=7.0,
        cycle_index=11,
        policy=policy,
    )
    assert mutated is False
    assert updated["entry_band_multiplier"] == 1.0
    assert "MUTATION_PHASE_OFFSET_WAIT" in reasons


def test_apply_mutation_respects_cooldown_after_phase_match() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["mutation"]["cooldown_cycles_between_mutations"] = 2
    updated, mutated, reasons = learning.apply_mutation(
        prior={
            "entry_band_multiplier": 1.0,
            "size_multiplier": 1.0,
            "enabled": True,
            "last_mutation_cycle": 3,
            "mutation_phase_offset": 0,
        },
        mutation_key="1m|PF_XBTUSD__PF_SOLUSD",
        recommendation="PROMOTE",
        confidence=0.95,
        combined_avg_net_bps=7.0,
        cycle_index=4,
        policy=policy,
    )
    assert mutated is False
    assert "MUTATION_COOLDOWN_ACTIVE" in reasons


def test_apply_mutation_demote_can_disable_pair_on_severe_negative() -> None:
    updated, mutated, reasons = learning.apply_mutation(
        prior={
            "entry_band_multiplier": 1.35,
            "size_multiplier": 0.35,
            "enabled": True,
            "last_mutation_cycle": 1,
            "mutation_phase_offset": 0,
        },
        mutation_key="1m|PF_XBTUSD__PF_SOLUSD",
        recommendation="DEMOTE",
        confidence=0.95,
        combined_avg_net_bps=-10.0,
        cycle_index=12,
        policy=BASE_POLICY,
    )
    assert mutated is True
    assert updated["enabled"] is False
    assert "PAIR_DISABLED_ON_SEVERE_NEGATIVE" in reasons


def test_apply_confidence_tier_size_cap_lowers_large_size_for_low_tier() -> None:
    updated, changed, reasons = learning.apply_confidence_tier_size_cap(
        prior={"size_multiplier": 1.4},
        confidence=0.6,
        combined_trades=40,
        policy=BASE_POLICY,
    )
    assert changed is True
    assert updated["size_cap_tier"] == "LOW"
    assert updated["size_multiplier"] == 0.9
    assert "SIZE_CAP_TIER_LOW_APPLIED" in reasons


def test_cross_timeframe_arbitration_marks_trade_eligible_with_consensus() -> None:
    rows_by_pair = {
        "PF_XBTUSD__PF_SOLUSD": [
            {
                "_logic_key": "1m|PF_XBTUSD__PF_SOLUSD",
                "pair_id": "PF_XBTUSD__PF_SOLUSD",
                "timeframe": "1m",
                "recommendation": "PROMOTE",
                "confidence": 0.9,
                "combined_trades": 90,
                "enabled": True,
            },
            {
                "_logic_key": "15m|PF_XBTUSD__PF_SOLUSD",
                "pair_id": "PF_XBTUSD__PF_SOLUSD",
                "timeframe": "15m",
                "recommendation": "PROMOTE",
                "confidence": 0.85,
                "combined_trades": 100,
                "enabled": True,
            },
        ]
    }
    logic_pairs = {
        "1m|PF_XBTUSD__PF_SOLUSD": {"reason_codes": []},
        "15m|PF_XBTUSD__PF_SOLUSD": {"reason_codes": []},
    }
    state_pairs = {}
    summary = learning.apply_cross_timeframe_arbitration(
        rows_by_pair=rows_by_pair,
        logic_pairs=logic_pairs,
        state_pairs=state_pairs,
        policy=BASE_POLICY,
    )
    assert summary["pairs_with_consensus"] == 1
    assert summary["trade_eligible_timeframes"] == 2
    assert rows_by_pair["PF_XBTUSD__PF_SOLUSD"][0]["trade_eligible"] is True
    assert rows_by_pair["PF_XBTUSD__PF_SOLUSD"][1]["trade_eligible"] is True


def test_cross_timeframe_arbitration_applies_hard_veto_until_recovery() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["hard_vetoes"] = [
        {
            "pair_id": "PF_XBTUSD__PF_ADAUSD",
            "timeframe": "1h",
            "enabled": True,
            "veto_reason": "HARD_VETO_1H_NEGATIVE_POCKET",
            "recovery": {
                "min_cycles": 12,
                "min_confidence": 0.8,
                "min_trades": 140,
                "min_robust_net_bps": 3.0,
                "required_positive_ratio": 0.75,
            },
        }
    ]
    rows_by_pair = {
        "PF_XBTUSD__PF_ADAUSD": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_ADAUSD",
                "pair_id": "PF_XBTUSD__PF_ADAUSD",
                "timeframe": "1h",
                "recommendation": "PROMOTE",
                "confidence": 0.95,
                "combined_trades": 180,
                "enabled": True,
            },
            {
                "_logic_key": "15m|PF_XBTUSD__PF_ADAUSD",
                "pair_id": "PF_XBTUSD__PF_ADAUSD",
                "timeframe": "15m",
                "recommendation": "PROMOTE",
                "confidence": 0.92,
                "combined_trades": 180,
                "enabled": True,
            },
        ]
    }
    logic_pairs = {
        "1h|PF_XBTUSD__PF_ADAUSD": {"reason_codes": []},
        "15m|PF_XBTUSD__PF_ADAUSD": {"reason_codes": []},
    }
    state_pairs = {
        "1h|PF_XBTUSD__PF_ADAUSD": {
            "history": history_with_score(0.1, 12),
        }
    }
    for item in state_pairs["1h|PF_XBTUSD__PF_ADAUSD"]["history"]:
        item["recommendation_confidence"] = 0.6
        item["combined_trades"] = 60
        item["combined_robust_net_bps"] = 0.5

    summary = learning.apply_cross_timeframe_arbitration(
        rows_by_pair=rows_by_pair,
        logic_pairs=logic_pairs,
        state_pairs=state_pairs,
        policy=policy,
    )

    tf_1h = rows_by_pair["PF_XBTUSD__PF_ADAUSD"][0]
    assert summary["pairs_with_veto"] == 1
    assert tf_1h["hard_veto_active"] is True
    assert tf_1h["trade_eligible"] is False
    assert "HARD_VETO_1H_NEGATIVE_POCKET" in tf_1h["arbitration_reason_codes"]


def test_parse_left_base_asset_extracts_symbol() -> None:
    assert learning.parse_left_base_asset("PF_XBTUSD__PF_SOLUSD") == "XBT"
    assert learning.parse_left_base_asset("PI_ETHUSD__PI_XRPUSD") == "ETH"


def test_universe_selection_returns_ranked_top_k_and_marks_rows() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"] = {
        "enabled": True,
        "top_k": 2,
        "min_utility_score": 0.4,
        "max_per_base_asset": 1,
        "robust_scale_bps": 20.0,
        "depth_scale_trades": 120.0,
        "weights": {
            "cycle_score": 0.35,
            "confidence": 0.25,
            "robust_net_bps": 0.25,
            "trade_depth": 0.15,
        },
    }
    timeframe_rows_map = {
        "1m": [
            {
                "_logic_key": "1m|PF_XBTUSD__PF_SOLUSD",
                "pair_id": "PF_XBTUSD__PF_SOLUSD",
                "timeframe": "1m",
                "trade_eligible": True,
                "cycle_score": 0.5,
                "confidence": 0.91,
                "combined_robust_net_bps": 9.0,
                "combined_trades": 140,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            }
        ],
        "15m": [
            {
                "_logic_key": "15m|PF_XBTUSD__PF_AVAXUSD",
                "pair_id": "PF_XBTUSD__PF_AVAXUSD",
                "timeframe": "15m",
                "trade_eligible": True,
                "cycle_score": 0.45,
                "confidence": 0.86,
                "combined_robust_net_bps": 8.0,
                "combined_trades": 110,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            },
            {
                "_logic_key": "15m|PF_ETHUSD__PF_SOLUSD",
                "pair_id": "PF_ETHUSD__PF_SOLUSD",
                "timeframe": "15m",
                "trade_eligible": True,
                "cycle_score": 0.41,
                "confidence": 0.84,
                "combined_robust_net_bps": 7.5,
                "combined_trades": 105,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            },
            {
                "_logic_key": "15m|PF_XRPUSD__PF_ADAUSD",
                "pair_id": "PF_XRPUSD__PF_ADAUSD",
                "timeframe": "15m",
                "trade_eligible": False,
                "cycle_score": 0.9,
                "confidence": 0.99,
                "combined_robust_net_bps": 20.0,
                "combined_trades": 200,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            },
        ],
    }
    logic_pairs = {
        "1m|PF_XBTUSD__PF_SOLUSD": {},
        "15m|PF_XBTUSD__PF_AVAXUSD": {},
        "15m|PF_ETHUSD__PF_SOLUSD": {},
        "15m|PF_XRPUSD__PF_ADAUSD": {},
    }
    selection = learning.apply_universe_selection(
        timeframe_rows_map=timeframe_rows_map,
        logic_pairs=logic_pairs,
        selection_state={},
        policy=policy,
    )
    assert selection["enabled"] is True
    assert selection["candidate_count"] == 3
    assert selection["selected_count"] == 2
    assert selection["selected_with_paper_low_sample_count"] == 0
    assert isinstance(selection["top1_dwell_cycles_by_pair_tf"], dict)
    assert selection["selection_turnover_rate"] == 0.0
    assert selection["top_1"] is not None
    assert selection["top_1"]["pair_id"] == "PF_XBTUSD__PF_SOLUSD"
    assert len(selection["top_k"]) == 2
    assert timeframe_rows_map["15m"][2]["selection_selected"] is False
    assert logic_pairs["1m|PF_XBTUSD__PF_SOLUSD"]["selection_selected"] is True
    assert logic_pairs["15m|PF_XRPUSD__PF_ADAUSD"]["selection_selected"] is False


def test_universe_selection_reason_penalty_reorders_candidates() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"] = {
        "enabled": True,
        "top_k": 1,
        "min_utility_score": 0.45,
        "max_per_base_asset": 1,
        "robust_scale_bps": 20.0,
        "depth_scale_trades": 120.0,
        "weights": {
            "cycle_score": 0.35,
            "confidence": 0.25,
            "robust_net_bps": 0.25,
            "trade_depth": 0.15,
        },
        "reason_penalties": {
            "PAPER_LOW_SAMPLE": 0.05,
        },
    }
    timeframe_rows_map = {
        "1h": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_LINKUSD",
                "pair_id": "PF_XBTUSD__PF_LINKUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.90,
                "confidence": 1.0,
                "combined_robust_net_bps": 35.0,
                "combined_trades": 220,
                "paper_trades": 5,
                "reason_codes": ["POSITIVE_STABILITY_CONFIRMED", "PAPER_LOW_SAMPLE"],
                "arbitration_reason_codes": [],
            },
            {
                "_logic_key": "1h|PF_SOLUSD__PF_AVAXUSD",
                "pair_id": "PF_SOLUSD__PF_AVAXUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.88,
                "confidence": 1.0,
                "combined_robust_net_bps": 34.5,
                "combined_trades": 220,
                "paper_trades": 25,
                "reason_codes": ["POSITIVE_STABILITY_CONFIRMED"],
                "arbitration_reason_codes": [],
            },
        ]
    }
    logic_pairs = {
        "1h|PF_XBTUSD__PF_LINKUSD": {},
        "1h|PF_SOLUSD__PF_AVAXUSD": {},
    }
    selection = learning.apply_universe_selection(
        timeframe_rows_map=timeframe_rows_map,
        logic_pairs=logic_pairs,
        selection_state={},
        policy=policy,
    )
    assert selection["top_1"] is not None
    assert selection["top_1"]["pair_id"] == "PF_SOLUSD__PF_AVAXUSD"
    assert selection["selected_with_paper_low_sample_count"] == 0


def test_universe_selection_low_sample_backfill_adds_reason_code() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"] = {
        "enabled": True,
        "top_k": 1,
        "min_utility_score": 0.2,
        "min_paper_trades_for_selection": 20,
        "allow_low_sample_backfill": True,
        "max_per_base_asset": 1,
        "robust_scale_bps": 20.0,
        "depth_scale_trades": 120.0,
        "weights": {
            "cycle_score": 0.35,
            "confidence": 0.25,
            "robust_net_bps": 0.25,
            "trade_depth": 0.15,
        },
    }
    timeframe_rows_map = {
        "1h": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_LINKUSD",
                "pair_id": "PF_XBTUSD__PF_LINKUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.8,
                "confidence": 0.9,
                "combined_robust_net_bps": 12.0,
                "combined_trades": 100,
                "paper_trades": 5,
                "reason_codes": ["PAPER_LOW_SAMPLE"],
                "arbitration_reason_codes": [],
            }
        ]
    }
    logic_pairs = {
        "1h|PF_XBTUSD__PF_LINKUSD": {"reason_codes": []},
    }
    selection = learning.apply_universe_selection(
        timeframe_rows_map=timeframe_rows_map,
        logic_pairs=logic_pairs,
        selection_state={},
        policy=policy,
    )
    assert selection["selected_count"] == 1
    assert selection["top_1"] is not None
    assert selection["top_1"]["pair_id"] == "PF_XBTUSD__PF_LINKUSD"
    assert "SELECTION_LOW_SAMPLE_BACKFILL" in timeframe_rows_map["1h"][0]["reason_codes"]
    assert "SELECTION_LOW_SAMPLE_BACKFILL" in logic_pairs["1h|PF_XBTUSD__PF_LINKUSD"]["reason_codes"]


def test_universe_selection_skips_low_sample_when_backfill_disabled() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"] = {
        "enabled": True,
        "top_k": 1,
        "min_utility_score": 0.2,
        "min_paper_trades_for_selection": 20,
        "allow_low_sample_backfill": False,
        "max_per_base_asset": 1,
        "robust_scale_bps": 20.0,
        "depth_scale_trades": 120.0,
        "weights": {
            "cycle_score": 0.35,
            "confidence": 0.25,
            "robust_net_bps": 0.25,
            "trade_depth": 0.15,
        },
    }
    timeframe_rows_map = {
        "1h": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_LINKUSD",
                "pair_id": "PF_XBTUSD__PF_LINKUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.8,
                "confidence": 0.9,
                "combined_robust_net_bps": 12.0,
                "combined_trades": 100,
                "paper_trades": 5,
                "reason_codes": ["PAPER_LOW_SAMPLE"],
                "arbitration_reason_codes": [],
            }
        ]
    }
    logic_pairs = {
        "1h|PF_XBTUSD__PF_LINKUSD": {"reason_codes": []},
    }
    selection = learning.apply_universe_selection(
        timeframe_rows_map=timeframe_rows_map,
        logic_pairs=logic_pairs,
        selection_state={},
        policy=policy,
    )
    assert selection["selected_count"] == 0
    assert selection["top_1"] is None
    assert timeframe_rows_map["1h"][0]["selection_selected"] is False


def test_universe_selection_tracks_top1_dwell_and_turnover() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"]["top_k"] = 1
    state: dict[str, object] = {}
    logic_pairs = {
        "1h|PF_XBTUSD__PF_LINKUSD": {},
        "1h|PF_SOLUSD__PF_AVAXUSD": {},
    }
    first_rows = {
        "1h": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_LINKUSD",
                "pair_id": "PF_XBTUSD__PF_LINKUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.95,
                "confidence": 1.0,
                "combined_robust_net_bps": 40.0,
                "combined_trades": 220,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            }
        ]
    }
    s1 = learning.apply_universe_selection(
        timeframe_rows_map=first_rows,
        logic_pairs=logic_pairs,
        selection_state=state,
        policy=policy,
    )
    assert s1["selection_turnover_rate"] == 0.0
    assert s1["top1_dwell_cycles_by_pair_tf"]["PF_XBTUSD__PF_LINKUSD|1h"] == 1

    second_rows = {
        "1h": [
            {
                "_logic_key": "1h|PF_SOLUSD__PF_AVAXUSD",
                "pair_id": "PF_SOLUSD__PF_AVAXUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.96,
                "confidence": 1.0,
                "combined_robust_net_bps": 41.0,
                "combined_trades": 220,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            }
        ]
    }
    s2 = learning.apply_universe_selection(
        timeframe_rows_map=second_rows,
        logic_pairs=logic_pairs,
        selection_state=state,
        policy=policy,
    )
    assert s2["selection_turnover_rate"] == 1.0
    assert s2["top1_dwell_cycles_by_pair_tf"]["PF_XBTUSD__PF_LINKUSD|1h"] == 1
    assert s2["top1_dwell_cycles_by_pair_tf"]["PF_SOLUSD__PF_AVAXUSD|1h"] == 1


def test_universe_selection_applies_top1_dwell_penalty() -> None:
    policy = deepcopy(BASE_POLICY)
    policy["selection"]["top_k"] = 1
    policy["selection"]["dwell_penalty_start_cycles"] = 3
    policy["selection"]["dwell_penalty_per_cycle"] = 0.10
    policy["selection"]["dwell_penalty_cap"] = 0.30

    state: dict[str, object] = {
        "last_top1_key": "PF_XBTUSD__PF_LINKUSD|1h",
        "top1_dwell_cycles_by_pair_tf": {
            "PF_XBTUSD__PF_LINKUSD|1h": 5,
        },
        "observed_cycles": 5,
        "top1_switches": 0,
    }
    rows = {
        "1h": [
            {
                "_logic_key": "1h|PF_XBTUSD__PF_LINKUSD",
                "pair_id": "PF_XBTUSD__PF_LINKUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.95,
                "confidence": 1.0,
                "combined_robust_net_bps": 40.0,
                "combined_trades": 220,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            },
            {
                "_logic_key": "1h|PF_SOLUSD__PF_AVAXUSD",
                "pair_id": "PF_SOLUSD__PF_AVAXUSD",
                "timeframe": "1h",
                "trade_eligible": True,
                "cycle_score": 0.94,
                "confidence": 1.0,
                "combined_robust_net_bps": 40.0,
                "combined_trades": 220,
                "paper_trades": 30,
                "reason_codes": [],
                "arbitration_reason_codes": [],
            },
        ]
    }
    logic_pairs = {
        "1h|PF_XBTUSD__PF_LINKUSD": {},
        "1h|PF_SOLUSD__PF_AVAXUSD": {},
    }

    selection = learning.apply_universe_selection(
        timeframe_rows_map=rows,
        logic_pairs=logic_pairs,
        selection_state=state,
        policy=policy,
    )

    assert selection["top_1"] is not None
    assert selection["top_1"]["pair_id"] == "PF_SOLUSD__PF_AVAXUSD"
    assert "TOP1_DWELL_PENALTY_APPLIED" in rows["1h"][0]["reason_codes"]
    assert selection["selection_turnover_rate"] > 0.0
