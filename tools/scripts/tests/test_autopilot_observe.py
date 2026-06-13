from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest
from copy import deepcopy
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import autopilot_observe as observe  # noqa: E402


OBSERVED_AT = dt.datetime(2026, 6, 13, 5, 30, tzinfo=dt.timezone.utc)


def candidate() -> dict[str, Any]:
    return {
        "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
        "left_instrument": "PF_DOGEUSD",
        "right_instrument": "PF_PEPEUSD",
        "timeframe": "1m",
        "selected_variant": "ROBUST_Z",
        "direction_hint": "SHORT_SPREAD",
        "spread_z": 2.12,
        "selected_score_z": 2.12,
        "entry_distance_z": 0.31,
        "opportunity_score": 35.9,
        "net_edge_bps": 19.5,
        "setup_gate_pass": True,
        "cost_gate_pass": True,
        "trade_gate_pass": True,
        "open_live_trade": False,
        "approval_source": "LEARNING_SELECTION",
        "decision_reason_code": "LEARNING_SELECTED_AND_LIVE_GATES_PASS",
    }


def base_routes() -> dict[str, dict[str, Any]]:
    return {
        "http://data/health": {"status": "ok"},
        "http://strategy/health": {"status": "ok"},
        "http://strategy/v1/strategy/pairs/trade-now?timeframe=1m": {
            "generated_at": "2026-06-13T05:29:57Z",
            "learning_overlay_fresh": True,
            "learning_overlay_age_seconds": 30.0,
            "tradable_now": [candidate()],
            "watchlist": [],
            "excluded": [],
        },
        "http://strategy/v1/strategy/observability/trade-now": {
            "generated_at": "2026-06-13T05:29:57Z",
            "learning_challenger_bypass_suppressed_total": 0,
            "learning_challenger_bypass_suppressed": [],
            "learning_eligible_override_tradable_total": 0,
            "learning_eligible_override_tradable": [],
            "learning_selection_cost_override_applied_total": 0,
            "learning_selection_cost_override_applied": [],
        },
        "http://execution/v1/execution/dispatch-mode": {
            "mode": "FAIL_CLOSED",
            "requires_live_arm": True,
            "sizing_tolerance_notional_drift_pct": 12.0,
            "sizing_tolerance_hedge_ratio_drift_pct": 25.0,
        },
        "http://execution/v1/execution/kill-switch": {
            "active": False,
            "reason": "",
            "updated_at": "2026-06-13T05:29:00Z",
        },
        "http://execution/v1/execution/portfolio/open-trades?exchange=kraken_futures&account_id=primary": {
            "exchange": "kraken_futures",
            "account_id": "primary",
            "generated_at": "2026-06-13T05:29:58Z",
            "warnings": [],
            "trades": [],
        },
    }


class RecordingGetClient:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.urls: list[str] = []

    def get_json(self, url: str, timeout_seconds: int) -> dict[str, Any]:
        self.urls.append(url)
        if "/v1/execution/order-intent" in url:
            raise AssertionError(f"observe-only sidecar requested execution submission URL {url}")
        return deepcopy(self.routes[url])


def config(**overrides: Any) -> observe.Config:
    values: dict[str, Any] = {
        "enabled": True,
        "data_service_url": "http://data",
        "strategy_service_url": "http://strategy",
        "execution_service_url": "http://execution",
        "exchange": "kraken_futures",
        "account_id": "primary",
        "timeframe": "1m",
        "allowed_pair_variants": {("PF_DOGEUSD__PF_PEPEUSD", "ROBUST_Z")},
        "quality_windows": {
            ("PF_DOGEUSD__PF_PEPEUSD", "1m", "ROBUST_Z"): observe.QualityWindow(
                rows=64,
                profitable_rate=0.73,
                avg_net_bps=7.4,
            )
        },
        "min_ready_window_rows": 20,
        "min_ready_window_avg_net_bps": 0.0,
    }
    values.update(overrides)
    return observe.Config(**values)


class AutopilotObserveTests(unittest.TestCase):
    def test_run_once_records_candidate_then_blocks_duplicate_replay(self) -> None:
        client = RecordingGetClient(base_routes())
        seen_keys: set[str] = set()

        first = observe.run_once(config(), client=client, observed_at=OBSERVED_AT, seen_keys=seen_keys)
        second = observe.run_once(config(), client=client, observed_at=OBSERVED_AT, seen_keys=seen_keys)

        self.assertEqual(first[0]["decision"], "OBSERVED_ENTRY_CANDIDATE")
        self.assertIn("QUALITY_GATE_PASS", first[0]["reason_codes"])
        self.assertEqual(second[0]["decision"], "BLOCKED_DUPLICATE_OBSERVATION")
        self.assertNotIn(
            "/v1/execution/order-intent",
            "\n".join(client.urls),
        )

    def test_data_health_failure_blocks_candidate_fail_closed(self) -> None:
        routes = base_routes()
        routes["http://data/health"] = {"status": "error"}

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_SOURCE_UNAVAILABLE")
        self.assertIn("DATA_HEALTH_NOT_OK", records[0]["reason_codes"])

    def test_kill_switch_active_blocks_candidate_fail_closed(self) -> None:
        routes = base_routes()
        routes["http://execution/v1/execution/kill-switch"]["active"] = True
        routes["http://execution/v1/execution/kill-switch"]["reason"] = "operator halt"

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_KILL_SWITCH")
        self.assertIn("KILL_SWITCH_ACTIVE", records[0]["reason_codes"])

    def test_quality_gate_failure_blocks_candidate(self) -> None:
        records = observe.run_once(
            config(
                quality_windows={
                    ("PF_DOGEUSD__PF_PEPEUSD", "1m", "ROBUST_Z"): observe.QualityWindow(
                        rows=3,
                        profitable_rate=0.4,
                        avg_net_bps=-2.1,
                    )
                }
            ),
            client=RecordingGetClient(base_routes()),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_QUALITY_GATE")
        self.assertIn("QUALITY_GATE_MIN_ROWS_FAIL", records[0]["reason_codes"])
        self.assertIn("QUALITY_GATE_MIN_AVG_NET_BPS_FAIL", records[0]["reason_codes"])

    def test_malformed_trade_now_response_writes_system_block_record(self) -> None:
        routes = base_routes()
        routes["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"] = {
            "generated_at": "2026-06-13T05:29:57Z",
            "tradable_now": {},
        }

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["pair_id"], "__SYSTEM__")
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertIn("TRADE_NOW_TRADABLE_NOW_NOT_LIST", records[0]["reason_codes"])

    def test_load_config_is_disabled_by_default_and_empty_allowlist_blocks_all(self) -> None:
        loaded = observe.load_config({})

        self.assertFalse(loaded.enabled)
        self.assertEqual(loaded.allowed_pair_variants, set())

        records = observe.run_once(
            loaded.replace(
                enabled=True,
                data_service_url="http://data",
                strategy_service_url="http://strategy",
                execution_service_url="http://execution",
                quality_windows={
                    ("PF_DOGEUSD__PF_PEPEUSD", "1m", "ROBUST_Z"): observe.QualityWindow(
                        rows=64,
                        profitable_rate=0.73,
                        avg_net_bps=7.4,
                    )
                },
            ),
            client=RecordingGetClient(base_routes()),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_NOT_ALLOWLISTED")
        self.assertIn("PAIR_VARIANT_NOT_ALLOWLISTED", records[0]["reason_codes"])
