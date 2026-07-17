from __future__ import annotations

import contextlib
import datetime as dt
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
import autopilot_observe as observe  # noqa: E402


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


def selector_row(
    *,
    observed_at: str,
    pair_id: str = "PF_SOLUSD__PF_AVAXUSD",
    selected_variant: str = "COINTEGRATION_Z",
    direction_hint: str | None = "LONG_SPREAD",
    cue_bucket: str = "WATCHLIST",
    selected_score_z: float | None = 1.5,
    net_edge_bps: float = 7.0,
    decision_reason_code: str | None = None,
    blocked_reason_code: str | None = None,
    watch_reason_code: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "mode": "observe_only",
        "capture_profile": "selector_view",
        "run_id": observed_at,
        "observed_at": observed_at,
        "source_generated_at": observed_at,
        "timeframe": "1m",
        "pair_id": pair_id,
        "selected_variant": selected_variant,
        "cue_bucket": cue_bucket,
        "direction_hint": direction_hint,
        "decision": "SELECTOR_VIEW_OBSERVED",
        "decision_reason_code": decision_reason_code,
        "blocked_reason_code": blocked_reason_code,
        "watch_reason_code": watch_reason_code,
        "rationale_codes": ["COST_GATE_OK"],
        "setup_gate_pass": cue_bucket == "TRADE_NOW",
        "cost_gate_pass": blocked_reason_code != "COST_GATE_FAIL",
        "trade_gate_pass": cue_bucket == "TRADE_NOW",
        "spread_z": 1.25,
        "selected_score_z": selected_score_z,
        "net_edge_bps": net_edge_bps,
        "opportunity_score": 0.5,
        "observe_key": (
            f"selector-view:v2:1m:{pair_id}:{selected_variant}:"
            f"{direction_hint or 'NO_DIRECTION'}:{cue_bucket}:{observed_at}"
        ),
    }


def selector_manifest(
    *, observed_at: str, rows: list[dict[str, object]]
) -> dict[str, object]:
    counts = {"TRADE_NOW": 0, "WATCHLIST": 0, "EXCLUDED": 0}
    for row in rows:
        counts[str(row["cue_bucket"])] += 1
    return {
        "schema_version": 2,
        "mode": "observe_only",
        "capture_profile": "selector_view_tick",
        "run_id": observed_at,
        "observed_at": observed_at,
        "source_generated_at": observed_at,
        "timeframe": "1m",
        "decision": "SELECTOR_VIEW_TICK_CAPTURED",
        "recorded_rows": len(rows),
        "rows_per_bucket": counts,
    }


def write_jsonl(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, allow_nan=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_selector_capture(
    path: pathlib.Path,
    ticks: list[tuple[str, list[dict[str, object]]]],
) -> None:
    records: list[dict[str, object]] = []
    for observed_at, rows in ticks:
        records.append(selector_manifest(observed_at=observed_at, rows=rows))
        records.extend(rows)
    write_jsonl(path, records)


def forbidden_outcome_keys(value: object) -> set[str]:
    forbidden: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ("realized", "outcome", "pnl", "fill")):
                forbidden.add(key)
            forbidden.update(forbidden_outcome_keys(child))
    elif isinstance(value, list):
        for child in value:
            forbidden.update(forbidden_outcome_keys(child))
    return forbidden


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

    def test_selector_view_builds_schema_valid_segregated_v2_snapshot(self) -> None:
        first_at = "2026-07-16T00:05:00Z"
        second_at = "2026-07-16T00:10:00Z"
        after_cutoff_at = "2026-07-16T01:05:00Z"
        pair_a = "PF_SOLUSD__PF_AVAXUSD"
        pair_b = "PF_DOGEUSD__PF_PEPEUSD"
        pair_c = "PF_XBTUSD__PF_LINKUSD"

        first_rows = [
            selector_row(
                observed_at=first_at,
                pair_id=pair_a,
                cue_bucket="WATCHLIST",
                selected_score_z=1.0,
                net_edge_bps=5.0,
                watch_reason_code="WATCH_ENTRY_DISTANCE",
            ),
            selector_row(
                observed_at=first_at,
                pair_id=pair_b,
                selected_variant="ROBUST_Z",
                direction_hint="SHORT_SPREAD",
                cue_bucket="TRADE_NOW",
                selected_score_z=2.0,
                net_edge_bps=7.0,
            ),
        ]
        second_rows = [
            selector_row(
                observed_at=second_at,
                pair_id=pair_a,
                cue_bucket="TRADE_NOW",
                selected_score_z=3.0,
                net_edge_bps=9.0,
            ),
            selector_row(
                observed_at=second_at,
                pair_id=pair_b,
                selected_variant="ROBUST_Z",
                direction_hint="SHORT_SPREAD",
                cue_bucket="EXCLUDED",
                selected_score_z=None,
                net_edge_bps=-1.0,
                blocked_reason_code="COST_GATE_FAIL",
            ),
            selector_row(
                observed_at=second_at,
                pair_id=pair_c,
                selected_variant="ROBUST_Z",
                direction_hint=None,
                cue_bucket="WATCHLIST",
                selected_score_z=0.5,
                net_edge_bps=2.0,
                decision_reason_code="LOW_SELECTOR_CONFIDENCE",
            ),
        ]
        late_rows = [
            selector_row(
                observed_at=after_cutoff_at,
                pair_id="PF_LATEUSD__PF_DROPUSD",
                cue_bucket="TRADE_NOW",
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            capture_path = pathlib.Path(tmp) / "selector_view.jsonl"
            write_selector_capture(
                capture_path,
                [
                    (first_at, first_rows),
                    (second_at, second_rows),
                    (after_cutoff_at, late_rows),
                ],
            )
            ticks = shadow.read_selector_view_ticks([capture_path])

        snapshot = shadow.build_snapshot(
            events=[
                event(
                    pair_id=pair_b,
                    selected_variant="ROBUST_Z",
                    direction="SHORT_SPREAD",
                )
            ],
            source_cutoff_at="2026-07-16T01:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=1),
            static_allowlist={(pair_b, "1m", "ROBUST_Z", "SHORT_SPREAD")},
            generated_at="2026-07-16T01:01:00Z",
            selector_ticks=ticks,
        )

        schema = json.loads(
            (REPO_ROOT / "specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json")
            .read_text(encoding="utf-8")
        )
        errors = sorted(Draft202012Validator(schema).iter_errors(snapshot), key=str)
        self.assertEqual(errors, [])
        self.assertEqual(snapshot["schema_version"], 2)

        prominent = {
            row["pair_id"]: row for row in snapshot["selector_view"]["selector_view_prominent"]
        }
        marginal = {
            row["pair_id"]: row for row in snapshot["selector_view"]["selector_view_marginal"]
        }
        self.assertEqual(set(prominent), {pair_a, pair_b})
        self.assertEqual(set(marginal), {pair_c})
        self.assertNotIn("PF_LATEUSD__PF_DROPUSD", prominent)

        a_metrics = prominent[pair_a]["metrics"]
        self.assertEqual(a_metrics["rows_observed"], 2)
        self.assertEqual(a_metrics["time_in_tradable_now_ratio"], 0.5)
        self.assertEqual(
            a_metrics["bucket_counts"],
            {"TRADE_NOW": 1, "WATCHLIST": 1, "EXCLUDED": 0},
        )
        self.assertEqual(
            a_metrics["score_z_summary"], {"min": 1.0, "max": 3.0, "mean": 2.0}
        )
        self.assertEqual(
            a_metrics["stated_net_edge_bps_summary"],
            {"min": 5.0, "max": 9.0, "mean": 7.0},
        )
        self.assertEqual(
            a_metrics["top_gate_failure_reasons"], ["WATCH_ENTRY_DISTANCE"]
        )
        self.assertEqual(
            prominent[pair_b]["metrics"]["top_gate_failure_reasons"],
            ["COST_GATE_FAIL"],
        )

        self.assertEqual(
            snapshot["universe"]["bucket_universe_counts"],
            {"TRADE_NOW": 2, "WATCHLIST": 2, "EXCLUDED": 1},
        )
        self.assertEqual(snapshot["universe"]["paper_evidenced_count"], 1)
        self.assertEqual(snapshot["universe"]["static_allowlist_overlap_count"], 1)
        self.assertEqual(
            [row["pair_id"] for row in snapshot["universe"]["selector_view_only"]],
            [pair_a],
        )
        self.assertEqual(forbidden_outcome_keys(snapshot["selector_view"]), set())
        self.assertIn("not PnL", snapshot["methodology"]["execution_caveat"])
        self.assertIn("not fill evidence", snapshot["methodology"]["execution_caveat"])
        markdown = shadow.render_markdown(snapshot)
        self.assertIn("Score z (min/mean/max)", markdown)
        self.assertIn("COST_GATE_FAIL", markdown)
        self.assertIn("Selector-View Discovery", markdown)
        self.assertIn(pair_a, markdown)

    def test_selector_view_replay_is_input_order_deterministic(self) -> None:
        first_at = "2026-07-16T00:05:00Z"
        second_at = "2026-07-16T00:10:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            first_path = root / "a.jsonl"
            second_path = root / "b.jsonl"
            write_selector_capture(
                first_path,
                [(first_at, [selector_row(observed_at=first_at)])],
            )
            write_selector_capture(
                second_path,
                [
                    (
                        second_at,
                        [
                            selector_row(
                                observed_at=second_at,
                                cue_bucket="TRADE_NOW",
                                selected_score_z=2.5,
                            )
                        ],
                    )
                ],
            )
            forward_ticks = shadow.read_selector_view_ticks([first_path, second_path])
            reverse_ticks = shadow.read_selector_view_ticks([second_path, first_path])

        kwargs = {
            "events": [],
            "source_cutoff_at": "2026-07-16T01:00:00Z",
            "selector_config": shadow.SelectorConfig(),
            "generated_at": "2026-07-16T01:01:00Z",
        }
        forward = shadow.build_snapshot(selector_ticks=forward_ticks, **kwargs)
        reverse = shadow.build_snapshot(selector_ticks=reverse_ticks, **kwargs)

        self.assertEqual(forward_ticks, reverse_ticks)
        self.assertEqual(forward, reverse)

    def test_b2b_producer_records_integrate_with_b2c_consumer(self) -> None:
        observed_at = dt.datetime(2026, 7, 16, 0, 5, tzinfo=dt.timezone.utc)
        observed_at_text = "2026-07-16T00:05:00Z"
        huge_spread = int("9" * 400)
        exact_large_score = 2**53 + 1
        records = observe.selector_view_records(
            config=observe.Config(
                enabled=True,
                capture_selector_view=True,
                max_signal_age_seconds=120,
            ),
            trade_now={
                "generated_at": "2026-07-16T00:04:57Z",
                "tradable_now": [
                    {
                        "pair_id": "PF_SOLUSD__PF_AVAXUSD",
                        "timeframe": "1m",
                        "selected_variant": "COINTEGRATION_Z",
                        "direction_hint": "LONG_SPREAD",
                        "decision_reason_code": "LEARNING_SELECTED_AND_LIVE_GATES_PASS",
                        "blocked_reason_code": None,
                        "watch_reason_code": None,
                        "rationale_codes": ["LEARNING_SELECTED"],
                        "setup_gate_pass": True,
                        "cost_gate_pass": True,
                        "trade_gate_pass": True,
                        "spread_z": huge_spread,
                        "selected_score_z": exact_large_score,
                        "net_edge_bps": 11.2,
                        "opportunity_score": 0.61,
                    }
                ],
                "watchlist": [],
                "excluded": [],
            },
            observed_at=observed_at,
            dispatch_mode=None,
            kill_switch=None,
            evidence={},
            source_reasons=[],
        )
        self.assertEqual(
            [record["capture_profile"] for record in records],
            ["selector_view_tick", "selector_view"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            capture_path = pathlib.Path(tmp) / "b2b_output.jsonl"
            write_jsonl(
                capture_path,
                [
                    {
                        "pair_id": "__SYSTEM__",
                        "decision": "BLOCKED_MALFORMED_RESPONSE",
                    },
                    *records,
                ],
            )
            ticks = shadow.read_selector_view_ticks([capture_path])

        snapshot = shadow.build_snapshot(
            events=[],
            source_cutoff_at="2026-07-16T00:10:00Z",
            selector_config=shadow.SelectorConfig(),
            generated_at="2026-07-16T00:11:00Z",
            selector_ticks=ticks,
        )

        self.assertEqual(ticks[0].run_id, observed_at_text)
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(
            snapshot["selector_view"]["selector_view_prominent"][0]["pair_id"],
            "PF_SOLUSD__PF_AVAXUSD",
        )
        self.assertEqual(
            snapshot["selector_view"]["selector_view_prominent"][0]["metrics"][
                "score_z_summary"
            ],
            {
                "min": exact_large_score,
                "max": exact_large_score,
                "mean": exact_large_score,
            },
        )
        self.assertEqual(snapshot["universe"]["paper_evidenced_count"], 0)
        self.assertEqual(forbidden_outcome_keys(snapshot["selector_view"]), set())

    def test_selector_view_churn_is_separate_from_realized_churn(self) -> None:
        pair_a = "PF_SOLUSD__PF_AVAXUSD"
        pair_b = "PF_DOGEUSD__PF_PEPEUSD"
        pair_c = "PF_XBTUSD__PF_LINKUSD"
        prior_at = "2026-07-16T00:05:00Z"
        current_at = "2026-07-16T00:10:00Z"

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prior_path = root / "prior.jsonl"
            current_path = root / "current.jsonl"
            write_selector_capture(
                prior_path,
                [
                    (
                        prior_at,
                        [
                            selector_row(
                                observed_at=prior_at,
                                pair_id=pair_a,
                                cue_bucket="TRADE_NOW",
                            ),
                            selector_row(
                                observed_at=prior_at,
                                pair_id=pair_c,
                                selected_variant="ROBUST_Z",
                                direction_hint=None,
                                cue_bucket="TRADE_NOW",
                            ),
                        ],
                    )
                ],
            )
            write_selector_capture(
                current_path,
                [
                    (
                        current_at,
                        [
                            selector_row(
                                observed_at=current_at,
                                pair_id=pair_a,
                                cue_bucket="TRADE_NOW",
                            ),
                            selector_row(
                                observed_at=current_at,
                                pair_id=pair_b,
                                selected_variant="ROBUST_Z",
                                direction_hint="SHORT_SPREAD",
                                cue_bucket="TRADE_NOW",
                            ),
                        ],
                    )
                ],
            )
            prior_ticks = shadow.read_selector_view_ticks([prior_path])
            current_ticks = shadow.read_selector_view_ticks([current_path])

        realized_events = [event()]
        prior = shadow.build_snapshot(
            events=realized_events,
            source_cutoff_at="2026-07-16T01:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=1),
            generated_at="2026-07-16T01:01:00Z",
            selector_ticks=prior_ticks,
        )
        current = shadow.build_snapshot(
            events=realized_events,
            source_cutoff_at="2026-07-16T01:00:00Z",
            selector_config=shadow.SelectorConfig(min_closed_positions=1),
            generated_at="2026-07-16T01:02:00Z",
            previous_snapshot=prior,
            selector_ticks=current_ticks,
        )

        realized_churn = current["churn"]
        self.assertEqual(realized_churn["churn_count"], 0)
        self.assertEqual(realized_churn["selected_added"], [])
        self.assertEqual(realized_churn["selected_removed"], [])
        selector_churn = realized_churn["selector_view"]
        self.assertEqual(selector_churn["previous_prominent_count"], 2)
        self.assertEqual(
            [row["pair_id"] for row in selector_churn["prominent_added"]], [pair_b]
        )
        self.assertEqual(
            [row["pair_id"] for row in selector_churn["prominent_removed"]], [pair_c]
        )
        self.assertEqual(selector_churn["prominent_retained_count"], 1)
        self.assertEqual(selector_churn["churn_count"], 2)
        self.assertEqual(selector_churn["stability_ratio"], 0.5)
        schema = json.loads(
            (REPO_ROOT / "specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            sorted(Draft202012Validator(schema).iter_errors(current), key=str), []
        )
        duplicate_previous = json.loads(json.dumps(prior))
        duplicate_previous["selector_view"]["selector_view_prominent"].append(
            duplicate_previous["selector_view"]["selector_view_prominent"][0]
        )
        with self.assertRaisesRegex(ValueError, "duplicate prominent selector key"):
            shadow.build_snapshot(
                events=realized_events,
                source_cutoff_at="2026-07-16T01:00:00Z",
                selector_config=shadow.SelectorConfig(min_closed_positions=1),
                generated_at="2026-07-16T01:03:00Z",
                previous_snapshot=duplicate_previous,
                selector_ticks=current_ticks,
            )

    def test_selector_view_empty_tick_supports_selector_only_snapshot_and_cli(self) -> None:
        observed_at = "2026-07-16T00:05:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            capture_path = root / "selector_view.jsonl"
            output_json = root / "snapshot.json"
            output_markdown = root / "snapshot.md"
            write_selector_capture(capture_path, [(observed_at, [])])

            exit_code = shadow.main(
                [
                    "--selector-view-jsonl",
                    str(capture_path),
                    "--source-cutoff-at",
                    "2026-07-16T01:00:00Z",
                    "--generated-at",
                    "2026-07-16T01:01:00Z",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_markdown),
                ]
            )

            snapshot = json.loads(output_json.read_text(encoding="utf-8"))
            markdown = output_markdown.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(snapshot["summary"]["source_event_count"], 0)
        self.assertEqual(snapshot["selector_view"]["selector_view_prominent"], [])
        self.assertEqual(snapshot["selector_view"]["selector_view_marginal"], [])
        self.assertEqual(
            snapshot["universe"]["bucket_universe_counts"],
            {"TRADE_NOW": 0, "WATCHLIST": 0, "EXCLUDED": 0},
        )
        self.assertIn("Selector-View", markdown)
        self.assertIn("advisory", markdown)

    def test_selector_view_ingest_rejects_incomplete_or_ambiguous_ticks(self) -> None:
        observed_at = "2026-07-16T00:05:00Z"
        row = selector_row(observed_at=observed_at)
        valid_manifest = selector_manifest(observed_at=observed_at, rows=[row])
        two_row_manifest = selector_manifest(observed_at=observed_at, rows=[row, row])
        wrong_bucket_manifest = {**valid_manifest}
        wrong_bucket_manifest["rows_per_bucket"] = {
            "TRADE_NOW": 1,
            "WATCHLIST": 0,
            "EXCLUDED": 0,
        }
        mismatched_time_row = {**row, "observed_at": "2026-07-16T00:06:00Z"}
        duplicate_bucket_row = {**row, "cue_bucket": "TRADE_NOW"}
        lexical_manifest = {
            **valid_manifest,
            "run_id": "2026-07-16T00:05:00+00:00",
        }
        extra_field_manifest = {**valid_manifest, "unexpected_manifest_field": True}
        equivalent_at = "2026-07-16T00:05:00+00:00"
        equivalent_row = selector_row(observed_at=equivalent_at)
        equivalent_manifest = selector_manifest(
            observed_at=equivalent_at, rows=[equivalent_row]
        )
        cases = {
            "truncated": [two_row_manifest, row],
            "bucket_count_mismatch": [wrong_bucket_manifest, row],
            "unmanifested": [row],
            "duplicate_tick": [valid_manifest, row, valid_manifest, row],
            "equivalent_duplicate_tick": [
                valid_manifest,
                row,
                equivalent_manifest,
                equivalent_row,
            ],
            "mismatched_tick_identity": [valid_manifest, mismatched_time_row],
            "duplicate_candidate": [two_row_manifest, row, duplicate_bucket_row],
            "lexical_manifest_identity": [lexical_manifest, row],
            "extra_manifest_field": [extra_field_manifest, row],
            "mixed_entry_record": [
                {
                    "capture_profile": "entry",
                    "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                    "decision": "OBSERVED_ENTRY_CANDIDATE",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name, records in cases.items():
                with self.subTest(name=name):
                    path = root / f"{name}.jsonl"
                    write_jsonl(path, records)
                    with self.assertRaises(ValueError):
                        shadow.read_selector_view_ticks([path])

            unterminated_path = root / "unterminated_final_record.jsonl"
            write_jsonl(unterminated_path, [valid_manifest, row])
            unterminated_path.write_text(
                unterminated_path.read_text(encoding="utf-8").removesuffix("\n"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "terminating newline"):
                shadow.read_selector_view_ticks([unterminated_path])

    def test_selector_view_ingest_rejects_outcomes_and_invalid_values(self) -> None:
        observed_at = "2026-07-16T00:05:00Z"
        base = selector_row(observed_at=observed_at)
        cases = {
            "outcome_field": {**base, "realized_net_bps": 99.0},
            "non_finite_score": {**base, "selected_score_z": math.nan},
            "unsupported_direction": {**base, "direction_hint": "SIDEWAYS"},
            "unexpected_field": {**base, "unexpected_selector_field": True},
            "missing_required_field": {
                key: value for key, value in base.items() if key != "decision_reason_code"
            },
            "invalid_optional_field": {**base, "expected_hold_bars": True},
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name, invalid_row in cases.items():
                with self.subTest(name=name):
                    path = root / f"{name}.jsonl"
                    write_jsonl(
                        path,
                        [
                            selector_manifest(observed_at=observed_at, rows=[invalid_row]),
                            invalid_row,
                        ],
                    )
                    with self.assertRaises(ValueError):
                        shadow.read_selector_view_ticks([path])

            outcome_path = root / "outcome_for_cli.jsonl"
            output_path = root / "must_not_exist.json"
            outcome_row = cases["outcome_field"]
            write_jsonl(
                outcome_path,
                [
                    selector_manifest(observed_at=observed_at, rows=[outcome_row]),
                    outcome_row,
                ],
            )
            with self.assertRaises(ValueError):
                shadow.main(
                    [
                        "--selector-view-jsonl",
                        str(outcome_path),
                        "--source-cutoff-at",
                        "2026-07-16T01:00:00Z",
                        "--output-json",
                        str(output_path),
                    ]
                )
            self.assertFalse(output_path.exists())

    def test_explicit_no_selector_input_preserves_legacy_v1_output(self) -> None:
        kwargs = {
            "events": [event()],
            "source_cutoff_at": "2026-07-02T00:00:00Z",
            "selector_config": shadow.SelectorConfig(min_closed_positions=1),
            "generated_at": "2026-07-02T00:10:00Z",
        }
        baseline = shadow.build_snapshot(**kwargs)
        explicit_none = shadow.build_snapshot(**kwargs, selector_ticks=None)

        self.assertEqual(explicit_none, baseline)
        self.assertEqual(explicit_none["schema_version"], 1)
        self.assertNotIn("selector_view", explicit_none)
        self.assertNotIn("universe", explicit_none)

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
