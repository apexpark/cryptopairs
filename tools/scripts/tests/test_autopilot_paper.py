from __future__ import annotations

import datetime as dt
import inspect
import json
import math
import pathlib
import sys
import tempfile
import unittest
from typing import Any

from jsonschema import Draft202012Validator


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import autopilot_paper as paper  # noqa: E402


OBSERVED_AT = dt.datetime(2026, 6, 18, 6, 45, tzinfo=dt.timezone.utc)


def candidate(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema_version": 1,
        "mode": "observe_only",
        "run_id": "observe-run",
        "observed_at": "2026-06-18T06:45:00Z",
        "source_generated_at": "2026-06-18T06:44:52Z",
        "timeframe": "1m",
        "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
        "selected_variant": "ROBUST_Z",
        "approval_source": "LEARNING_SELECTION",
        "decision_reason_code": "LEARNING_SELECTED_AND_LIVE_GATES_PASS",
        "setup_gate_pass": True,
        "cost_gate_pass": True,
        "trade_gate_pass": True,
        "direction_hint": "SHORT_SPREAD",
        "spread_z": 1.25,
        "entry_distance_z": 0.42,
        "selected_score_z": 2.12,
        "net_edge_bps": 19.5,
        "opportunity_score": 35.9,
        "learning_overlay_fresh": True,
        "learning_overlay_age_seconds": 30.0,
        "dispatch_mode": "SIMULATE_ACK",
        "kill_switch_active": False,
        "conflicting_live_trade": False,
        "quality_window": {
            "rows": 64,
            "profitable_rate": 0.73,
            "avg_net_bps": 7.4,
            "min_rows": 20,
            "min_avg_net_bps": 0.0,
            "pass": True,
        },
        "decision": "OBSERVED_ENTRY_CANDIDATE",
        "observe_key": (
            "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
            "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:45:00Z"
        ),
        "evidence": {
            "data_health_status": "ok",
            "strategy_health_status": "ok",
            "trade_now_status": "ok",
            "trade_now_observability_status": "ok",
            "dispatch_mode_status": "ok",
            "kill_switch_status": "ok",
            "open_trades_status": "ok",
            "source_urls": [
                "http://127.0.0.1:8080/health",
                "http://127.0.0.1:8083/v1/strategy/pairs/trade-now?timeframe=1m",
                "http://127.0.0.1:8082/v1/execution/kill-switch",
            ],
        },
    }
    row.update(overrides)
    return row


def mark(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
        "timeframe": "1m",
        "selected_variant": "ROBUST_Z",
        "direction": "SHORT_SPREAD",
        "mark_at": "2026-06-18T06:50:15Z",
        "source_type": "paper_trade_outcome",
        "net_bps": 7.25,
    }
    row.update(overrides)
    return row


def config(**overrides: Any) -> paper.Config:
    values: dict[str, Any] = {
        "enabled": True,
        "allowed_pair_variants": {("PF_DOGEUSD__PF_PEPEUSD", "ROBUST_Z")},
        "hold_window_bars": 5,
        "cooldown_seconds": 300,
        "max_candidate_age_seconds": 120,
    }
    values.update(overrides)
    return paper.Config(**values)


class AutopilotPaperTests(unittest.TestCase):
    def validator(self, schema_name: str) -> Draft202012Validator:
        schema_path = REPO_ROOT / "specs/contracts" / schema_name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_load_config_is_disabled_by_default(self) -> None:
        loaded = paper.load_config({})

        self.assertFalse(loaded.enabled)
        self.assertEqual(loaded.allowed_pair_variants, set())

    def test_enabled_empty_static_allowlist_blocks_candidate(self) -> None:
        result = paper.run_once(
            config(allowed_pair_variants=set()),
            candidates=[candidate()],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_STATIC_ALLOWLIST_REQUIRED")
        self.assertEqual(result.positions, [])

    def test_non_1m_candidate_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[candidate(timeframe="15m")],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_TIMEFRAME_OUT_OF_SCOPE")
        self.assertEqual(result.decisions[0]["evidence"]["candidate_timeframe"], "15m")
        self.assertEqual(result.positions, [])

    def test_stale_candidate_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:45:00Z",
                    source_generated_at="2026-06-18T06:40:00Z",
                )
            ],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_STALE_INPUT")
        self.assertIn("CANDIDATE_SOURCE_STALE", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_future_source_timestamp_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:45:00Z",
                    source_generated_at="2026-06-18T06:45:01Z",
                )
            ],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_STALE_INPUT")
        self.assertIn("CANDIDATE_SOURCE_GENERATED_AT_FUTURE", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_future_candidate_observed_at_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:46:00Z",
                    source_generated_at="2026-06-18T06:44:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
                        "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:46:00Z"
                    ),
                )
            ],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_MALFORMED_INPUT")
        self.assertIn("CANDIDATE_OBSERVED_AT_FUTURE", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_source_timestamp_after_candidate_observed_at_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:45:00Z",
                    source_generated_at="2026-06-18T06:45:30Z",
                )
            ],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_STALE_INPUT")
        self.assertIn("CANDIDATE_SOURCE_AFTER_OBSERVED_AT", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_blocked_observe_decision_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[candidate(decision="BLOCKED_KILL_SWITCH")],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_OBSERVE_DECISION")
        self.assertIn("OBSERVE_DECISION_NOT_ENTRY_CANDIDATE", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_missing_observe_evidence_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[candidate(evidence=None)],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_MALFORMED_INPUT")
        self.assertIn("CANDIDATE_EVIDENCE_MISSING", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_empty_observe_source_urls_blocks_without_opening_position(self) -> None:
        row = candidate()
        row["evidence"] = dict(row["evidence"], source_urls=[])

        result = paper.run_once(
            config(),
            candidates=[row],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_MALFORMED_INPUT")
        self.assertIn("CANDIDATE_EVIDENCE_MISSING", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_observe_safety_state_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    dispatch_mode="FAIL_CLOSED",
                    kill_switch_active=True,
                    conflicting_live_trade=True,
                )
            ],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_OBSERVE_DECISION")
        self.assertIn("OBSERVE_DISPATCH_MODE_FAIL_CLOSED", result.decisions[0]["reason_codes"])
        self.assertIn("OBSERVE_KILL_SWITCH_ACTIVE", result.decisions[0]["reason_codes"])
        self.assertIn("OBSERVE_CONFLICTING_LIVE_TRADE", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_failed_observe_gates_block_without_opening_position(self) -> None:
        row = candidate(setup_gate_pass=False, cost_gate_pass=False, trade_gate_pass=False)
        row["quality_window"] = dict(row["quality_window"], **{"pass": False})

        result = paper.run_once(
            config(),
            candidates=[row],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_OBSERVE_DECISION")
        self.assertIn("OBSERVE_SETUP_GATE_NOT_PASS", result.decisions[0]["reason_codes"])
        self.assertIn("OBSERVE_COST_GATE_NOT_PASS", result.decisions[0]["reason_codes"])
        self.assertIn("OBSERVE_TRADE_GATE_NOT_PASS", result.decisions[0]["reason_codes"])
        self.assertIn("OBSERVE_QUALITY_WINDOW_NOT_PASS", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_missing_direction_blocks_without_opening_position(self) -> None:
        row = candidate()
        del row["direction_hint"]
        row["observe_key"] = (
            "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
            "ROBUST_Z:NO_DIRECTION:2026-06-18T06:45:00Z"
        )

        result = paper.run_once(
            config(),
            candidates=[row],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_MALFORMED_INPUT")
        self.assertIn("CANDIDATE_DIRECTION_MISSING", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_invalid_hold_window_blocks_candidate(self) -> None:
        result = paper.run_once(
            config(hold_window_bars=None),
            candidates=[candidate()],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_INVALID_HOLD_WINDOW")
        self.assertEqual(result.positions, [])

    def test_invalid_hold_window_block_record_matches_schema(self) -> None:
        result = paper.run_once(
            config(hold_window_bars=999),
            candidates=[candidate()],
            marks=[mark()],
            observed_at=OBSERVED_AT,
        )

        errors = sorted(
            self.validator("autopilot_paper_decision_record.schema.json").iter_errors(
                result.decisions[0]
            ),
            key=str,
        )
        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_INVALID_HOLD_WINDOW")
        self.assertEqual(errors, [])

    def test_candidate_opens_one_paper_position_and_second_poll_blocks_open_conflict(self) -> None:
        first = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )
        second = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
            existing_positions=first.positions,
        )

        self.assertEqual(first.decisions[0]["decision_type"], "PAPER_ENTRY_OPENED")
        self.assertEqual(first.positions[0]["status"], "OPEN")
        self.assertEqual(second.decisions[0]["decision_type"], "BLOCKED_OPEN_PAPER_POSITION")
        self.assertEqual(second.positions, [])

    def test_observe_record_with_minute_key_and_fractional_source_timestamp_opens_position(
        self,
    ) -> None:
        result = paper.run_once(
            config(
                allowed_pair_variants={
                    ("PF_XBTUSD__PF_BNBUSD", "COINTEGRATION_Z"),
                }
            ),
            candidates=[
                candidate(
                    pair_id="PF_XBTUSD__PF_BNBUSD",
                    selected_variant="COINTEGRATION_Z",
                    observed_at="2026-06-18T06:45:51Z",
                    source_generated_at="2026-06-18T06:45:51.265681741Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_XBTUSD__PF_BNBUSD:"
                        "COINTEGRATION_Z:SHORT_SPREAD:2026-06-18T06:45:00Z"
                    ),
                )
            ],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
        )

        self.assertEqual(result.decisions[0]["decision_type"], "PAPER_ENTRY_OPENED")
        self.assertEqual(result.positions[0]["status"], "OPEN")

    def test_naive_ledger_observed_at_raises_before_opening_position(self) -> None:
        with self.assertRaises(ValueError):
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=dt.datetime(2026, 6, 18, 6, 45),
            )

    def test_malformed_open_position_state_blocks_new_entries(self) -> None:
        malformed_open = dict(
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            ).positions[0]
        )
        del malformed_open["direction"]

        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:46:00Z",
                    source_generated_at="2026-06-18T06:45:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
                        "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:46:00Z"
                    ),
                )
            ],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
            existing_positions=[malformed_open],
        )

        self.assertEqual(
            result.decisions[0]["decision_type"],
            "BLOCKED_MALFORMED_EXISTING_POSITION_STATE",
        )
        self.assertIn("OPEN_PAPER_POSITION_STATE_MALFORMED", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_malformed_open_position_exit_eligible_at_blocks_all_new_entries(self) -> None:
        malformed_open = dict(
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            ).positions[0]
        )
        malformed_open["exit_eligible_at"] = "2026-06-18T06:50:00"

        result = paper.run_once(
            config(
                allowed_pair_variants={
                    ("PF_DOGEUSD__PF_PEPEUSD", "ROBUST_Z"),
                    ("PF_XBTUSD__PF_BNBUSD", "COINTEGRATION_Z"),
                }
            ),
            candidates=[
                candidate(
                    pair_id="PF_XBTUSD__PF_BNBUSD",
                    selected_variant="COINTEGRATION_Z",
                    observed_at="2026-06-18T06:46:00Z",
                    source_generated_at="2026-06-18T06:45:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_XBTUSD__PF_BNBUSD:"
                        "COINTEGRATION_Z:SHORT_SPREAD:2026-06-18T06:46:00Z"
                    ),
                )
            ],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
            existing_positions=[malformed_open],
        )

        self.assertEqual(
            result.decisions[0]["decision_type"],
            "BLOCKED_MALFORMED_EXISTING_POSITION_STATE",
        )
        self.assertEqual(result.positions, [])

    def test_malformed_open_position_derived_exit_eligible_at_blocks_before_exit(self) -> None:
        malformed_open = dict(
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            ).positions[0]
        )
        malformed_open["exit_eligible_at"] = "2026-06-18T06:46:00Z"

        result = paper.run_once(
            config(
                allowed_pair_variants={
                    ("PF_DOGEUSD__PF_PEPEUSD", "ROBUST_Z"),
                    ("PF_XBTUSD__PF_BNBUSD", "COINTEGRATION_Z"),
                }
            ),
            candidates=[
                candidate(
                    pair_id="PF_XBTUSD__PF_BNBUSD",
                    selected_variant="COINTEGRATION_Z",
                    observed_at="2026-06-18T06:47:00Z",
                    source_generated_at="2026-06-18T06:46:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_XBTUSD__PF_BNBUSD:"
                        "COINTEGRATION_Z:SHORT_SPREAD:2026-06-18T06:47:00Z"
                    ),
                )
            ],
            marks=[mark(mark_at="2026-06-18T06:46:30Z")],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=2),
            existing_positions=[malformed_open],
        )

        self.assertEqual(
            [decision["decision_type"] for decision in result.decisions],
            ["BLOCKED_MALFORMED_EXISTING_POSITION_STATE"],
        )
        self.assertEqual(result.positions, [])

    def test_generated_entry_decision_and_position_match_schemas(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        decision_errors = sorted(
            self.validator("autopilot_paper_decision_record.schema.json").iter_errors(
                result.decisions[0]
            ),
            key=str,
        )
        position_errors = sorted(
            self.validator("autopilot_paper_position.schema.json").iter_errors(
                result.positions[0]
            ),
            key=str,
        )
        self.assertEqual(decision_errors, [])
        self.assertEqual(position_errors, [])

    def test_expired_hold_window_closes_on_next_available_mark(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        closed = paper.run_once(
            config(),
            candidates=[],
            marks=[mark()],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(closed.decisions[0]["decision_type"], "PAPER_EXIT_COMPLETED")
        self.assertEqual(closed.positions[0]["status"], "CLOSED")
        self.assertEqual(closed.positions[0]["exit_observed_at"], "2026-06-18T06:50:15Z")
        self.assertEqual(closed.positions[0]["realized_net_bps"], 7.25)

    def test_naive_ledger_observed_at_raises_before_closing_position(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        with self.assertRaises(ValueError):
            paper.run_once(
                config(),
                candidates=[],
                marks=[mark()],
                observed_at=dt.datetime(2026, 6, 18, 6, 51),
                existing_positions=opened.positions,
            )

    def test_missing_mark_after_hold_window_defers_exit_without_fabricating_pnl(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        deferred = paper.run_once(
            config(),
            candidates=[],
            marks=[],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(deferred.decisions[0]["decision_type"], "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE")
        self.assertEqual(deferred.positions, [])
        self.assertIsNone(deferred.decisions[0]["realized_net_bps"])

    def test_future_mark_does_not_close_before_current_ledger_tick(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        deferred = paper.run_once(
            config(),
            candidates=[],
            marks=[mark(mark_at="2026-06-18T07:00:00Z")],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(deferred.decisions[0]["decision_type"], "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE")
        self.assertEqual(deferred.positions, [])
        self.assertIsNone(deferred.decisions[0]["realized_net_bps"])

    def test_naive_mark_timestamp_defers_exit_without_closing_position(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        deferred = paper.run_once(
            config(),
            candidates=[],
            marks=[mark(mark_at="2026-06-18T06:50:15")],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(deferred.decisions[0]["decision_type"], "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE")
        self.assertEqual(deferred.positions, [])
        self.assertIsNone(deferred.decisions[0]["realized_net_bps"])

    def test_malformed_open_position_state_is_not_exited_before_entry_block(self) -> None:
        malformed_open = dict(
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            ).positions[0]
        )
        malformed_open["entry_observe_key"] = None

        result = paper.run_once(
            config(
                allowed_pair_variants={
                    ("PF_DOGEUSD__PF_PEPEUSD", "ROBUST_Z"),
                    ("PF_XBTUSD__PF_BNBUSD", "COINTEGRATION_Z"),
                }
            ),
            candidates=[
                candidate(
                    pair_id="PF_XBTUSD__PF_BNBUSD",
                    selected_variant="COINTEGRATION_Z",
                    observed_at="2026-06-18T06:51:00Z",
                    source_generated_at="2026-06-18T06:50:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_XBTUSD__PF_BNBUSD:"
                        "COINTEGRATION_Z:SHORT_SPREAD:2026-06-18T06:51:00Z"
                    ),
                )
            ],
            marks=[mark()],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=[malformed_open],
        )

        self.assertEqual(
            [decision["decision_type"] for decision in result.decisions],
            ["BLOCKED_MALFORMED_EXISTING_POSITION_STATE"],
        )
        self.assertEqual(result.positions, [])

    def test_mark_without_numeric_net_bps_defers_exit_without_closing_position(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        deferred = paper.run_once(
            config(),
            candidates=[],
            marks=[mark(net_bps=None)],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(deferred.decisions[0]["decision_type"], "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE")
        self.assertEqual(deferred.positions, [])
        self.assertIsNone(deferred.decisions[0]["realized_net_bps"])

    def test_mark_with_non_finite_net_bps_defers_exit_without_closing_position(self) -> None:
        opened = paper.run_once(
            config(),
            candidates=[candidate()],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        deferred = paper.run_once(
            config(),
            candidates=[],
            marks=[mark(net_bps=math.nan)],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=opened.positions,
        )

        self.assertEqual(deferred.decisions[0]["decision_type"], "PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE")
        self.assertEqual(deferred.positions, [])
        self.assertIsNone(deferred.decisions[0]["realized_net_bps"])

    def test_cooldown_blocks_reentry_after_closed_position(self) -> None:
        closed_position = dict(
            paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            ).positions[0]
        )
        closed_position.update(
            {
                "status": "CLOSED",
                "exit_observed_at": "2026-06-18T06:50:15Z",
                "exit_reason": "HOLD_WINDOW_MARK",
                "realized_net_bps": 7.25,
            }
        )

        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:51:00Z",
                    source_generated_at="2026-06-18T06:50:58Z",
                    observe_key=(
                        "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
                        "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:51:00Z"
                    ),
                )
            ],
            marks=[mark(mark_at="2026-06-18T06:56:30Z")],
            observed_at=OBSERVED_AT + dt.timedelta(minutes=6),
            existing_positions=[closed_position],
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_COOLDOWN")
        self.assertEqual(result.positions, [])

    def test_write_artifacts_blocks_duplicate_entry_across_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            first = paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            )
            second = paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            )

            paths = paper.write_artifacts(first, output_dir, OBSERVED_AT)
            paper.write_artifacts(second, output_dir, OBSERVED_AT)

            decisions = [
                json.loads(line)
                for line in paths.decisions_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                [row["decision_type"] for row in decisions],
                ["PAPER_ENTRY_OPENED", "BLOCKED_DUPLICATE_CANDIDATE"],
            )

    def test_write_artifacts_blocks_duplicate_entry_from_prior_day_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            first = paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            )
            prior_day = output_dir / "20260617"
            prior_day.mkdir(parents=True)
            prior_decisions = prior_day / "autopilot_paper_decisions_20260617.jsonl"
            prior_decisions.write_text(
                json.dumps(first.decisions[0], sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

            second = paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            )
            paths = paper.write_artifacts(second, output_dir, OBSERVED_AT)

            decisions = [
                json.loads(line)
                for line in paths.decisions_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                [row["decision_type"] for row in decisions],
                ["BLOCKED_DUPLICATE_CANDIDATE"],
            )
            self.assertEqual(second.positions, [])

    def test_persisted_output_positions_block_same_key_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            first = paper.run_once(
                config(),
                candidates=[candidate()],
                marks=[],
                observed_at=OBSERVED_AT,
            )
            paper.write_artifacts(first, output_dir, OBSERVED_AT)

            second = paper.run_once(
                config(),
                candidates=[
                    candidate(
                        observed_at="2026-06-18T06:46:00Z",
                        source_generated_at="2026-06-18T06:45:58Z",
                        observe_key=(
                            "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
                            "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:46:00Z"
                        ),
                    )
                ],
                marks=[],
                observed_at=OBSERVED_AT + dt.timedelta(minutes=1),
                existing_positions=paper.read_persisted_positions(output_dir),
            )

            self.assertEqual(second.decisions[0]["decision_type"], "BLOCKED_OPEN_PAPER_POSITION")
            self.assertEqual(second.positions, [])

    def test_missing_observe_key_blocks_before_persisted_duplicate_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            row = candidate()
            del row["observe_key"]
            first = paper.run_once(
                config(),
                candidates=[row],
                marks=[],
                observed_at=OBSERVED_AT,
            )
            second = paper.run_once(
                config(),
                candidates=[row],
                marks=[],
                observed_at=OBSERVED_AT,
            )

            paths = paper.write_artifacts(first, output_dir, OBSERVED_AT)
            paper.write_artifacts(second, output_dir, OBSERVED_AT)

            decisions = [
                json.loads(line)
                for line in paths.decisions_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                [row["decision_type"] for row in decisions],
                ["BLOCKED_MALFORMED_INPUT", "BLOCKED_MALFORMED_INPUT"],
            )
            self.assertTrue(
                all("CANDIDATE_OBSERVE_KEY_MISSING" in row["reason_codes"] for row in decisions)
            )
            self.assertEqual(first.positions, [])
            self.assertEqual(second.positions, [])

    def test_naive_candidate_timestamp_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[
                candidate(
                    observed_at="2026-06-18T06:45:00",
                    source_generated_at="2026-06-18T06:44:58Z",
                )
            ],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_MALFORMED_INPUT")
        self.assertIn("CANDIDATE_OBSERVED_AT_INVALID", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_naive_source_timestamp_blocks_without_opening_position(self) -> None:
        result = paper.run_once(
            config(),
            candidates=[candidate(source_generated_at="2026-06-18T06:44:58")],
            marks=[],
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decisions[0]["decision_type"], "BLOCKED_STALE_INPUT")
        self.assertIn("CANDIDATE_SOURCE_GENERATED_AT_INVALID", result.decisions[0]["reason_codes"])
        self.assertEqual(result.positions, [])

    def test_no_execution_order_intent_or_dispatch_url_is_constructed(self) -> None:
        source = inspect.getsource(paper)

        self.assertNotIn("/v1/execution/order-intent", source)
        self.assertNotIn("/v1/execution/order-intent/dispatch", source)

    def test_missing_existing_positions_jsonl_raises_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = pathlib.Path(tmpdir) / "missing_positions.jsonl"

            with self.assertRaises(FileNotFoundError):
                paper.read_jsonl_rows(missing_path)


if __name__ == "__main__":
    unittest.main()
