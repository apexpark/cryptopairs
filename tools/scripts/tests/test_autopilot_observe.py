from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
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
            "mode": "SIMULATE_ACK",
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


def with_trade_now_candidate(routes: dict[str, dict[str, Any]], row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    updated = deepcopy(routes)
    updated["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"]["tradable_now"] = [row]
    return updated


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
    def test_observe_record_examples_validate_against_v2_schema(self) -> None:
        from jsonschema import Draft202012Validator

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        schema = json.loads(
            (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        entry_example = json.loads(
            (repo_root / "specs/examples/autopilot_observe_record.example.json")
            .read_text(encoding="utf-8")
        )
        selector_view_example = json.loads(
            (repo_root / "specs/examples/autopilot_observe_record.selector_view.example.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(sorted(validator.iter_errors(entry_example), key=str), [])
        self.assertEqual(
            sorted(validator.iter_errors(selector_view_example), key=str), []
        )
        self.assertEqual(selector_view_example["capture_profile"], "selector_view")
        self.assertEqual(selector_view_example["decision"], "SELECTOR_VIEW_OBSERVED")
        # Selector-view surfaces are observations, never outcomes: no property
        # name anywhere in the selector-view branch of the observe schema, nor
        # in the snapshot's selector_view/universe/churn.selector_view blocks,
        # may imply a realized or estimated outcome.
        def property_names(node: Any) -> list[str]:
            names: list[str] = []
            if isinstance(node, dict):
                for key, value in node.get("properties", {}).items():
                    names.append(key)
                    names.extend(property_names(value))
                for combinator in ("oneOf", "anyOf", "allOf"):
                    for sub in node.get(combinator, []):
                        names.extend(property_names(sub))
                if "items" in node:
                    names.extend(property_names(node["items"]))
            return names

        snapshot_schema = json.loads(
            (repo_root / "specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json")
            .read_text(encoding="utf-8")
        )
        guarded_nodes = [
            schema["oneOf"][1],
            snapshot_schema["properties"]["selector_view"],
            snapshot_schema["properties"]["universe"],
            snapshot_schema["properties"]["churn"]["oneOf"][1]["properties"]["selector_view"],
        ]
        forbidden_tokens = ("realized", "pnl", "outcome", "fill", "estimated", "simulated")
        for node in guarded_nodes:
            for field_name in property_names(node):
                for forbidden in forbidden_tokens:
                    self.assertNotIn(forbidden, field_name.lower())

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

    def test_fail_closed_dispatch_mode_blocks_candidate_fail_closed(self) -> None:
        routes = base_routes()
        routes["http://execution/v1/execution/dispatch-mode"]["mode"] = "FAIL_CLOSED"

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_DISPATCH_MODE")
        self.assertIn("DISPATCH_MODE_FAIL_CLOSED", records[0]["reason_codes"])

    def test_malformed_kill_switch_blocks_candidate_fail_closed(self) -> None:
        routes = base_routes()
        routes["http://execution/v1/execution/kill-switch"] = {"reason": "missing active"}

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_KILL_SWITCH")
        self.assertIn("KILL_SWITCH_ACTIVE_MALFORMED", records[0]["reason_codes"])

    def test_malformed_open_trades_blocks_candidate_fail_closed(self) -> None:
        routes = base_routes()
        routes[
            "http://execution/v1/execution/portfolio/open-trades?exchange=kraken_futures&account_id=primary"
        ] = {"trades": {}}

        records = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["decision"], "BLOCKED_OPEN_LIVE_TRADE")
        self.assertIn("OPEN_TRADES_MALFORMED", records[0]["reason_codes"])

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

    def test_malformed_candidate_identity_writes_schema_valid_system_block_record(self) -> None:
        row = candidate()
        del row["pair_id"]

        records = observe.run_once(
            config(),
            client=RecordingGetClient(with_trade_now_candidate(base_routes(), row)),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["pair_id"], "__SYSTEM__")
        self.assertEqual(records[0]["selected_variant"], "__NONE__")
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertIn("TRADE_NOW_ROW_IDENTITY_MISSING", records[0]["reason_codes"])

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

    def test_non_1m_config_blocks_before_polling_trade_now(self) -> None:
        loaded = observe.load_config(
            {
                "AUTOPILOT_OBSERVE_ENABLED": "true",
                "AUTOPILOT_OBSERVE_TIMEFRAMES": "15m",
                "AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS": "PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z",
            }
        )
        client = RecordingGetClient(base_routes())

        records = observe.run_once(
            loaded.replace(
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
                min_ready_window_rows=20,
                min_ready_window_avg_net_bps=0.0,
            ),
            client=client,
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(loaded.timeframe, "15m")
        self.assertEqual(client.urls, [])
        self.assertEqual(records[0]["pair_id"], "__SYSTEM__")
        self.assertEqual(records[0]["timeframe"], "1m")
        self.assertEqual(records[0]["decision"], "BLOCKED_TIMEFRAME_OUT_OF_SCOPE")
        self.assertIn("CONFIG_TIMEFRAME_NOT_1M", records[0]["reason_codes"])

    def test_mixed_timeframe_config_blocks_before_polling_trade_now(self) -> None:
        loaded = observe.load_config(
            {
                "AUTOPILOT_OBSERVE_ENABLED": "true",
                "AUTOPILOT_OBSERVE_TIMEFRAMES": "1m,15m",
                "AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS": "PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z",
            }
        )
        client = RecordingGetClient(base_routes())

        records = observe.run_once(
            loaded.replace(
                data_service_url="http://data",
                strategy_service_url="http://strategy",
                execution_service_url="http://execution",
            ),
            client=client,
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(loaded.timeframe, "1m,15m")
        self.assertEqual(client.urls, [])
        self.assertEqual(records[0]["decision"], "BLOCKED_TIMEFRAME_OUT_OF_SCOPE")
        self.assertIn("CONFIG_TIMEFRAME_NOT_1M", records[0]["reason_codes"])

    def test_non_1m_trade_now_row_blocks_with_schema_valid_timeframe(self) -> None:
        row = candidate()
        row["timeframe"] = "15m"

        records = observe.run_once(
            config(),
            client=RecordingGetClient(with_trade_now_candidate(base_routes(), row)),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )

        self.assertEqual(records[0]["timeframe"], "1m")
        self.assertEqual(records[0]["decision"], "BLOCKED_TIMEFRAME_OUT_OF_SCOPE")
        self.assertIn("ROW_TIMEFRAME_NOT_1M", records[0]["reason_codes"])

    def test_write_records_blocks_duplicate_candidate_across_process_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            first = observe.run_once(
                config(),
                client=RecordingGetClient(base_routes()),
                observed_at=OBSERVED_AT,
                seen_keys=set(),
            )
            second = observe.run_once(
                config(),
                client=RecordingGetClient(base_routes()),
                observed_at=OBSERVED_AT,
                seen_keys=set(),
            )

            path = observe.write_records(first, output_dir, OBSERVED_AT)
            observe.write_records(second, output_dir, OBSERVED_AT)

            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                [record["decision"] for record in records],
                ["OBSERVED_ENTRY_CANDIDATE", "BLOCKED_DUPLICATE_OBSERVATION"],
            )
            self.assertEqual(second[0]["decision"], "BLOCKED_DUPLICATE_OBSERVATION")
            self.assertIn("OBSERVE_KEY_ALREADY_WRITTEN", records[1]["reason_codes"])
