from __future__ import annotations

import contextlib
import inspect
import io
import json
import math
import pathlib
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools/scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_shadow_allowlist as shadow  # noqa: E402


def event(
    *,
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    selected_variant: str = "ROBUST_Z",
    direction: str = "SHORT_SPREAD",
    entry_at: str = "2026-07-01T00:00:00Z",
    exit_at: str = "2026-07-01T00:06:00Z",
    realized_net_bps: float = 8.0,
    exit_lag_seconds: float | None = 60.0,
) -> shadow.TradeEvent:
    return shadow.TradeEvent(
        key=(pair_id, "1m", selected_variant, direction),
        entry_at=shadow.parse_timestamp(entry_at, "entry_at"),
        exit_at=shadow.parse_timestamp(exit_at, "exit_at"),
        realized_net_bps=realized_net_bps,
        exit_lag_seconds=exit_lag_seconds,
    )


def closed_position(
    *,
    paper_position_id: str = (
        "paper-position:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
        "ROBUST_Z:SHORT_SPREAD:2026-07-01T00:00:00Z"
    ),
    status: str = "CLOSED",
    realized_net_bps: float | None = 8.0,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "paper_only",
        "paper_position_id": paper_position_id,
        "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
        "timeframe": "1m",
        "selected_variant": "ROBUST_Z",
        "direction": "SHORT_SPREAD",
        "status": status,
        "entry_observed_at": "2026-07-01T00:00:00Z",
        "entry_score_z": 2.2,
        "entry_net_edge_bps": 10.5,
        "source_generated_at": "2026-07-01T00:00:00Z",
        "entry_observe_key": (
            "observe-only:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
            "ROBUST_Z:SHORT_SPREAD:2026-07-01T00:00:00Z"
        ),
        "hold_window_bars": 5,
        "exit_eligible_at": "2026-07-01T00:05:00Z",
        "exit_observed_at": "2026-07-01T00:06:00Z" if status == "CLOSED" else None,
        "exit_reason": "HOLD_WINDOW_MARK" if status == "CLOSED" else None,
        "exit_source_type": "paper_trade_outcome" if status == "CLOSED" else None,
        "realized_net_bps": realized_net_bps if status == "CLOSED" else None,
    }


class AutopilotShadowAllowlistTests(unittest.TestCase):
    def test_example_matches_schema_and_is_shadow_only(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json")
            .read_text(encoding="utf-8")
        )
        example = json.loads(
            (REPO_ROOT / "specs/examples/autopilot_shadow_allowlist_snapshot.example.json")
            .read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(example), key=str)

        self.assertEqual(errors, [])
        self.assertEqual(example["mode"], "shadow_dynamic_allowlist_snapshot")
        self.assertIn("advisory", example["methodology"]["selection_boundary"])
        self.assertNotIn("order_intent", json.dumps(example))

    def test_positive_leg_selects_and_tail_loss_leg_quarantines(self) -> None:
        good_events = [
            event(realized_net_bps=value, exit_at=f"2026-07-01T00:{index + 10:02d}:00Z")
            for index, value in enumerate([12, 8, 5, -4, 9, 7])
        ]
        bad_events = [
            event(
                pair_id="PF_TAOUSD__PF_HYPEUSD",
                selected_variant="COINTEGRATION_Z",
                realized_net_bps=value,
                exit_at=f"2026-07-01T01:{index + 10:02d}:00Z",
            )
            for index, value in enumerate([16, 12, 3, 0.4, -118])
        ]

        snapshot = shadow.build_snapshot(
            events=good_events + bad_events,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=5),
            static_allowlist={
                ("PF_DOGEUSD__PF_PEPEUSD", "1m", "ROBUST_Z", "SHORT_SPREAD"),
                ("PF_TAOUSD__PF_HYPEUSD", "1m", "COINTEGRATION_Z", "SHORT_SPREAD"),
            },
            generated_at="2026-07-02T00:10:00Z",
        )

        self.assertEqual(snapshot["summary"]["selected_count"], 1)
        self.assertEqual(snapshot["selected"][0]["pair_id"], "PF_DOGEUSD__PF_PEPEUSD")
        self.assertEqual(snapshot["quarantined"][0]["pair_id"], "PF_TAOUSD__PF_HYPEUSD")
        self.assertIn("TAIL_LOSS_LIMIT_BREACHED", snapshot["quarantined"][0]["reason_codes"])
        self.assertEqual(snapshot["static_allowlist_comparison"]["static_only_count"], 1)

    def test_source_cutoff_prevents_lookahead(self) -> None:
        events = [
            event(realized_net_bps=-8, exit_at="2026-07-01T00:10:00Z"),
            event(realized_net_bps=-4, exit_at="2026-07-01T00:20:00Z"),
            event(realized_net_bps=100, exit_at="2026-07-03T00:20:00Z"),
        ]

        snapshot = shadow.build_snapshot(
            events=events,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=2),
            generated_at="2026-07-02T00:10:00Z",
        )

        self.assertEqual(snapshot["summary"]["source_event_count"], 2)
        self.assertEqual(snapshot["summary"]["selected_count"], 0)
        self.assertEqual(snapshot["rejected"][0]["metrics"]["sum_realized_net_bps"], -12)

    def test_pair_level_static_allowlist_expands_over_observed_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_config_path = pathlib.Path(tmp) / "run_config.json"
            run_config_path.write_text(
                json.dumps(
                    {
                        "static_allowlist": [
                            {
                                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                                "selected_variant": "ROBUST_Z",
                            },
                            {
                                "pair_id": "PF_XBTUSD__PF_BNBUSD",
                                "selected_variant": "COINTEGRATION_Z",
                                "direction": "LONG_SPREAD",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            static_allowlist = shadow.allowlist_from_run_config(str(run_config_path))

        snapshot = shadow.build_snapshot(
            events=[
                event(direction="LONG_SPREAD", realized_net_bps=11),
                event(direction="SHORT_SPREAD", realized_net_bps=12),
                event(
                    pair_id="PF_XBTUSD__PF_BNBUSD",
                    selected_variant="COINTEGRATION_Z",
                    direction="LONG_SPREAD",
                    realized_net_bps=13,
                ),
            ],
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=1),
            static_allowlist=static_allowlist,
            generated_at="2026-07-02T00:10:00Z",
        )

        comparison = snapshot["static_allowlist_comparison"]
        self.assertEqual(comparison["static_allowlist_size"], 3)
        self.assertEqual(comparison["overlap_count"], 3)
        self.assertEqual(comparison["static_only_count"], 0)
        self.assertEqual(comparison["shadow_only_count"], 0)

    def test_low_sample_rejects_without_quarantine(self) -> None:
        snapshot = shadow.build_snapshot(
            events=[event(realized_net_bps=20)],
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=3),
            generated_at="2026-07-02T00:10:00Z",
        )

        self.assertEqual(snapshot["summary"]["selected_count"], 0)
        self.assertEqual(snapshot["summary"]["rejected_count"], 1)
        self.assertIn("INSUFFICIENT_CLOSED_POSITIONS", snapshot["rejected"][0]["reason_codes"])

    def test_positions_ingest_latest_closed_state_and_exit_lag(self) -> None:
        rows = [
            closed_position(status="OPEN", realized_net_bps=None),
            closed_position(status="CLOSED", realized_net_bps=9.5),
        ]

        events = shadow.events_from_positions(rows)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].realized_net_bps, 9.5)
        self.assertEqual(events[0].exit_lag_seconds, 60)

    def test_paper_trades_deduplicate_by_stable_closed_trade_identity(self) -> None:
        base_row = {
            "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
            "timeframe": "1m",
            "selected_variant": "ROBUST_Z",
            "direction": "SHORT_SPREAD",
            "entry_ts": "2026-07-01T00:00:00Z",
            "exit_ts": "2026-07-01T00:10:00Z",
            "exit_mode": "mean_revert",
            "exit_kind": "exit",
            "net_bps": 12,
        }

        events = shadow.events_from_paper_trades(
            [
                base_row,
                {**base_row, "net_bps": 9},
                {**base_row, "exit_kind": "stop", "net_bps": -6},
            ]
        )

        self.assertEqual(len(events), 2)
        realized = sorted(event.realized_net_bps for event in events)
        self.assertEqual(realized, [-6, 9])

    def test_cli_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            rows_path = root / "paper_trades.json"
            rows_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                                "timeframe": "1m",
                                "selected_variant": "ROBUST_Z",
                                "direction": "SHORT_SPREAD",
                                "entry_ts": "2026-07-01T00:00:00Z",
                                "exit_ts": "2026-07-01T00:10:00Z",
                                "net_bps": 12,
                            },
                            {
                                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                                "timeframe": "1m",
                                "selected_variant": "ROBUST_Z",
                                "direction": "SHORT_SPREAD",
                                "entry_ts": "2026-07-01T00:20:00Z",
                                "exit_ts": "2026-07-01T00:30:00Z",
                                "net_bps": 8,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output_json = root / "snapshot.json"
            output_md = root / "snapshot.md"

            exit_code = shadow.main(
                [
                    "--paper-trades-json",
                    str(rows_path),
                    "--source-cutoff-at",
                    "2026-07-02T00:00:00Z",
                    "--min-closed-positions",
                    "2",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_md),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["selected_count"], 1)
            self.assertIn("AUTO-2B Shadow", output_md.read_text(encoding="utf-8"))

    def test_invalid_selector_config_fails_before_snapshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_selected"):
            shadow.build_snapshot(
                events=[event()],
                source_cutoff_at="2026-07-02T00:00:00Z",
                selector_config=shadow.SelectorConfig(max_selected=0),
                generated_at="2026-07-02T00:10:00Z",
            )

    def test_invalid_cli_positive_integer_rejected(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                shadow.parse_args(
                    [
                        "--source-cutoff-at",
                        "2026-07-02T00:00:00Z",
                        "--max-selected",
                        "0",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("must be an integer >= 1", stderr.getvalue())

    def test_non_finite_selector_config_fails_before_snapshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_score"):
            shadow.build_snapshot(
                events=[event()],
                source_cutoff_at="2026-07-02T00:00:00Z",
                selector_config=shadow.SelectorConfig(min_score=math.nan),
                generated_at="2026-07-02T00:10:00Z",
            )

    def test_invalid_cli_finite_float_rejected(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                shadow.parse_args(
                    [
                        "--source-cutoff-at",
                        "2026-07-02T00:00:00Z",
                        "--min-score",
                        "nan",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("must be a finite number", stderr.getvalue())

    def test_rank_outside_max_selected_demotes_overflow(self) -> None:
        pairs = ["PF_AUSD__PF_BUSD", "PF_CUSD__PF_DUSD", "PF_EUSD__PF_FUSD"]
        events = []
        for rank, pair_id in enumerate(pairs):
            events.extend(
                event(
                    pair_id=pair_id,
                    realized_net_bps=20.0 - rank * 5,
                    exit_at=f"2026-07-01T0{rank}:{index + 10:02d}:00Z",
                )
                for index in range(5)
            )

        snapshot = shadow.build_snapshot(
            events=events,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=5, max_selected=2),
            generated_at="2026-07-02T00:10:00Z",
        )

        self.assertEqual(len(snapshot["selected"]), 2)
        overflow = [
            row
            for row in snapshot["rejected"]
            if row["reason_codes"] == ["RANK_OUTSIDE_MAX_SELECTED"]
        ]
        self.assertEqual(len(overflow), 1)
        self.assertEqual(overflow[0]["pair_id"], "PF_EUSD__PF_FUSD")
        self.assertEqual(
            snapshot["summary"]["selected_count"]
            + snapshot["summary"]["rejected_count"]
            + snapshot["summary"]["quarantined_count"],
            snapshot["summary"]["eligible_universe_count"],
        )

    def test_threshold_gates_reject_with_expected_reason_codes(self) -> None:
        slow_exit = [
            event(
                pair_id="PF_SLOWUSD__PF_LAGUSD",
                realized_net_bps=9.0,
                exit_lag_seconds=4000.0,
                exit_at=f"2026-07-01T00:{index + 10:02d}:00Z",
            )
            for index in range(5)
        ]
        negative_avg = [
            event(
                pair_id="PF_NEGUSD__PF_AVGUSD",
                realized_net_bps=-2.0,
                exit_at=f"2026-07-01T01:{index + 10:02d}:00Z",
            )
            for index in range(5)
        ]

        snapshot = shadow.build_snapshot(
            events=slow_exit + negative_avg,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(
                min_closed_positions=5,
                max_avg_exit_lag_seconds=1800,
                min_score=0.0,
            ),
            generated_at="2026-07-02T00:10:00Z",
        )

        reasons_by_pair = {
            row["pair_id"]: row["reason_codes"] for row in snapshot["rejected"]
        }
        self.assertIn(
            "AVG_EXIT_LAG_LIMIT_BREACHED", reasons_by_pair["PF_SLOWUSD__PF_LAGUSD"]
        )
        self.assertIn(
            "AVG_NET_BPS_BELOW_THRESHOLD", reasons_by_pair["PF_NEGUSD__PF_AVGUSD"]
        )
        self.assertIn(
            "SCORE_BELOW_THRESHOLD", reasons_by_pair["PF_NEGUSD__PF_AVGUSD"]
        )
        self.assertEqual(snapshot["selected"], [])

    def test_negative_exit_lag_is_not_a_score_bonus(self) -> None:
        components = shadow.score_components(
            closed_count=10,
            profitable_count=7,
            avg_net_bps=5.0,
            max_loss_bps=-10.0,
            avg_exit_lag_seconds=-120.0,
        )

        self.assertEqual(components["exit_lag_penalty"], 0.0)

    def test_summary_counts_dropped_and_deduplicated_rows(self) -> None:
        counts: dict[str, int] = {}
        trade_rows = [
            {"timeframe": "5m"},
            {"timeframe": "1m", "exit_ts": None, "net_bps": 4.0},
            {
                "timeframe": "1m",
                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                "selected_variant": "ROBUST_Z",
                "direction": "SHORT_SPREAD",
                "entry_ts": "2026-07-01T00:00:00Z",
                "exit_ts": "2026-07-01T00:06:00Z",
                "net_bps": 9.0,
            },
            {
                "timeframe": "1m",
                "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                "selected_variant": "ROBUST_Z",
                "direction": "SHORT_SPREAD",
                "entry_ts": "2026-07-01T00:00:00Z",
                "exit_ts": "2026-07-01T00:06:00Z",
                "net_bps": 9.0,
            },
        ]
        position_rows = [closed_position(status="OPEN", realized_net_bps=None)]

        events = shadow.events_from_paper_trades(trade_rows, counts)
        events += shadow.events_from_positions(position_rows, counts)
        late_event = event(exit_at="2026-07-03T00:00:00Z")

        snapshot = shadow.build_snapshot(
            events=events + [late_event],
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=1),
            generated_at="2026-07-02T00:10:00Z",
            ingest_counts=counts,
        )

        summary = snapshot["summary"]
        self.assertEqual(summary["trade_rows_skipped_non_timeframe"], 1)
        self.assertEqual(summary["trade_rows_skipped_incomplete"], 1)
        self.assertEqual(summary["trade_rows_deduplicated"], 1)
        self.assertEqual(summary["position_rows_open_excluded"], 1)
        self.assertEqual(summary["events_dropped_post_cutoff"], 1)

    def test_churn_block_measures_stability_against_previous_snapshot(self) -> None:
        events = [
            event(realized_net_bps=9.0, exit_at=f"2026-07-01T00:{index + 10:02d}:00Z")
            for index in range(5)
        ]
        previous = {
            "generated_at": "2026-07-01T00:00:00Z",
            "selected": [
                {
                    "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                    "timeframe": "1m",
                    "selected_variant": "ROBUST_Z",
                    "direction": "SHORT_SPREAD",
                },
                {
                    "pair_id": "PF_TAOUSD__PF_HYPEUSD",
                    "timeframe": "1m",
                    "selected_variant": "COINTEGRATION_Z",
                    "direction": "SHORT_SPREAD",
                },
            ],
        }

        snapshot = shadow.build_snapshot(
            events=events,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=5),
            generated_at="2026-07-02T00:10:00Z",
            previous_snapshot=previous,
        )

        churn = snapshot["churn"]
        self.assertEqual(churn["previous_selected_count"], 2)
        self.assertEqual(churn["selected_added"], [])
        self.assertEqual(len(churn["selected_removed"]), 1)
        self.assertEqual(
            churn["selected_removed"][0]["pair_id"], "PF_TAOUSD__PF_HYPEUSD"
        )
        self.assertEqual(churn["selected_retained_count"], 1)
        self.assertEqual(churn["churn_count"], 1)
        self.assertEqual(churn["stability_ratio"], 0.5)

    def test_churn_is_null_without_previous_snapshot(self) -> None:
        events = [
            event(realized_net_bps=9.0, exit_at=f"2026-07-01T00:{index + 10:02d}:00Z")
            for index in range(5)
        ]

        snapshot = shadow.build_snapshot(
            events=events,
            source_cutoff_at="2026-07-02T00:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=5),
            generated_at="2026-07-02T00:10:00Z",
        )

        self.assertIsNone(snapshot["churn"])

    def test_script_has_no_execution_post_surface(self) -> None:
        source = inspect.getsource(shadow)

        forbidden = [
            "order-intent",
            "/dispatch",
            "urlopen",
            "requests.",
            "http://127.0.0.1:8082",
            "subprocess",
            "os.system",
            "socket",
            "httpx",
            "urllib",
            "os.environ",
        ]
        for needle in forbidden:
            self.assertNotIn(needle, source)


if __name__ == "__main__":
    unittest.main()
