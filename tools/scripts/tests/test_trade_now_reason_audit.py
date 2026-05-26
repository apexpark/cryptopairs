from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trade_now_reason_audit  # noqa: E402


def test_trade_now_reason_audit_summarizes_contract_example() -> None:
    example = REPO_ROOT / "specs" / "examples" / "strategy_pairs_trade_now_response.example.json"

    report = trade_now_reason_audit.summarize([str(example)])

    aggregate = report["aggregate"]
    assert aggregate["bucket_counts"] == {
        "TRADE_NOW": 3,
        "EXCLUDED": 2,
        "WATCHLIST": 1,
    }
    assert aggregate["reason_counts"]["RECANONICALIZED_LEGACY_ROW_ACTIVE"] == 1
    assert aggregate["reason_counts"]["PENDING_CHALLENGER_REQUIRES_PROMOTION"] == 1
    assert aggregate["scheduler_relevance_counts"]["provenance_block_not_scheduler"] == 1
    assert aggregate["scheduler_relevance_counts"]["governance_policy_not_scheduler"] == 1


def test_trade_now_reason_audit_classifies_wait_setup_relevance(tmp_path: pathlib.Path) -> None:
    payload = {
        "generated_at": "2026-05-27T00:00:00Z",
        "timeframe_filter": "1m",
        "learning_overlay_generated_at": "2026-05-27T00:00:00Z",
        "learning_overlay_age_seconds": 0,
        "learning_overlay_fresh": True,
        "learning_overlay_ttl_seconds": 86400,
        "tradable_now": [],
        "watchlist": [
            {
                "pair_id": "PF_XBTUSD__PF_ETHUSD",
                "timeframe": "1m",
                "decision_bucket": "WATCHLIST",
                "decision_reason_code": "APPROVED_BUT_WAITING_ON_LIVE_CONDITIONS",
                "watch_reason_code": "SETUP_GATE_NOT_PASSING",
                "blocked_reason_code": None,
                "rationale_codes": ["LIVE_SETUP_GATE_FAIL"],
                "setup_gate_pass": False,
                "cost_gate_pass": True,
                "trade_gate_pass": False,
                "open_live_trade": False,
                "selected_config_source": "AUTO_CHAMPION",
                "approval_source": "LEARNING_SELECTION",
            }
        ],
        "excluded": [
            {
                "pair_id": "PF_XBTUSD__PF_DOGEUSD",
                "timeframe": "1m",
                "decision_bucket": "EXCLUDED",
                "decision_reason_code": "PROVENANCE_POLICY_BLOCKED",
                "watch_reason_code": None,
                "blocked_reason_code": "RECANONICALIZED_LEGACY_ROW_ACTIVE",
                "rationale_codes": ["RECANONICALIZED_LEGACY_ROW_ACTIVE"],
                "setup_gate_pass": True,
                "cost_gate_pass": True,
                "trade_gate_pass": True,
                "open_live_trade": False,
                "selected_config_source": "RECANONICALIZED_LEGACY_ROW",
                "approval_source": "NONE",
            }
        ],
    }
    path = tmp_path / "trade-now.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = trade_now_reason_audit.summarize([str(path)])

    assert report["aggregate"]["reason_counts"] == {
        "SETUP_GATE_NOT_PASSING": 1,
        "RECANONICALIZED_LEGACY_ROW_ACTIVE": 1,
    }
    assert report["aggregate"]["scheduler_relevance_counts"] == {
        "market_or_live_gate_not_scheduler": 1,
        "provenance_block_not_scheduler": 1,
    }
