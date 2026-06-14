from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools/scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_observe_report as report  # noqa: E402


def observe_record(
    *,
    observed_at: str = "2026-06-13T05:30:00Z",
    decision: str = "OBSERVED_ENTRY_CANDIDATE",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    timeframe: str = "1m",
    selected_variant: str = "ROBUST_Z",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "observe_only",
        "run_id": "2026-06-13T05:30:00Z-1m",
        "observed_at": observed_at,
        "source_generated_at": "2026-06-13T05:29:57Z",
        "timeframe": timeframe,
        "pair_id": pair_id,
        "selected_variant": selected_variant,
        "approval_source": "LEARNING_SELECTION",
        "decision_reason_code": "LEARNING_SELECTED_AND_LIVE_GATES_PASS",
        "setup_gate_pass": True,
        "cost_gate_pass": True,
        "trade_gate_pass": True,
        "spread_z": 2.12,
        "entry_distance_z": 0.31,
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
        "decision": decision,
        "reason_codes": [
            "TRADE_NOW_LIVE_GATES_PASS",
            "ALLOWLIST_PAIR_VARIANT",
            "QUALITY_GATE_PASS",
        ],
        "observe_key": f"observe-only:v1:{timeframe}:{pair_id}:{selected_variant}:SHORT_SPREAD:{observed_at}",
        "evidence": {
            "data_health_status": "ok",
            "strategy_health_status": "ok",
            "trade_now_status": "ok",
            "trade_now_observability_status": "ok",
            "dispatch_mode_status": "ok",
            "kill_switch_status": "ok",
            "open_trades_status": "ok",
            "source_urls": [],
        },
    }


def opportunity_row(
    *,
    evaluated_at: str,
    actionable: bool,
    cost_gate_pass: bool = True,
    direction_hint: str = "SHORT_SPREAD",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    timeframe: str = "1m",
    selected_variant: str = "ROBUST_Z",
) -> dict[str, object]:
    return {
        "pair_id": pair_id,
        "left_instrument": "PF_DOGEUSD",
        "right_instrument": "PF_PEPEUSD",
        "timeframe": timeframe,
        "selected_variant": selected_variant,
        "regime": "CALM",
        "direction_hint": direction_hint,
        "spread_z": 2.12,
        "opportunity_score": 35.9,
        "net_edge_bps": 19.5,
        "cost_gate_pass": cost_gate_pass,
        "actionable": actionable,
        "rationale_codes": ["COST_PASS"],
        "cost_gate_rationale_codes": ["EDGE_CLEAR"],
        "evaluated_at": evaluated_at,
    }


def paper_trade_row(
    *,
    entry_ts: str,
    exit_ts: str = "2026-06-13T05:47:00Z",
    net_bps: float = 12.5,
    direction: str = "SHORT_SPREAD",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    timeframe: str = "1m",
    selected_variant: str = "ROBUST_Z",
) -> dict[str, object]:
    return {
        "pair_id": pair_id,
        "timeframe": timeframe,
        "exit_mode": "mean_revert",
        "left_instrument": "PF_DOGEUSD",
        "right_instrument": "PF_PEPEUSD",
        "selected_variant": selected_variant,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "bars_held": 12,
        "direction": direction,
        "exit_kind": "exit",
        "entry_z": 2.12,
        "exit_z": 0.1,
        "net_bps": net_bps,
        "created_at": "2026-06-13T06:00:00Z",
        "updated_at": "2026-06-13T06:00:00Z",
    }


class AutopilotObserveReportTests(unittest.TestCase):
    def test_report_matches_candidate_to_later_ready_window_and_paper_trade(self) -> None:
        result = report.build_report(
            observe_records=[observe_record()],
            opportunity_rows=[
                opportunity_row(evaluated_at="2026-06-13T05:29:00Z", actionable=False),
                opportunity_row(evaluated_at="2026-06-13T05:31:00Z", actionable=True),
                opportunity_row(evaluated_at="2026-06-13T05:32:00Z", actionable=True),
            ],
            paper_trade_rows=[
                paper_trade_row(entry_ts="2026-06-13T05:35:00Z", net_bps=12.5),
            ],
            generated_at="2026-06-13T06:00:00Z",
            lookahead_minutes=60,
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["scope"]["timeframe"], "1m")
        self.assertEqual(result["summary"]["observed_candidate_records"], 1)
        self.assertEqual(result["summary"]["observed_candidates_with_later_ready_window"], 1)
        self.assertEqual(result["summary"]["observed_candidates_with_later_paper_trade"], 1)
        self.assertEqual(result["summary"]["unique_later_ready_windows"], 1)
        self.assertEqual(result["summary"]["unique_later_paper_trades"], 1)
        self.assertEqual(result["summary"]["profitable_unique_later_paper_trades"], 1)
        self.assertEqual(result["summary"]["sum_unique_later_paper_net_bps"], 12.5)

        pair_row = result["by_pair_variant"][0]
        self.assertEqual(pair_row["pair_id"], "PF_DOGEUSD__PF_PEPEUSD")
        self.assertEqual(pair_row["later_ready_windows"], 1)
        self.assertEqual(pair_row["later_ready_rows"], 2)
        self.assertEqual(pair_row["unique_later_paper_trades"], 1)

        candidate_row = result["observed_candidates"][0]
        self.assertEqual(candidate_row["first_later_ready_at"], "2026-06-13T05:31:00Z")
        self.assertEqual(candidate_row["later_paper_trade_count"], 1)
        self.assertEqual(candidate_row["sum_later_paper_net_bps"], 12.5)

    def test_blocked_records_are_not_counted_as_observed_candidates(self) -> None:
        result = report.build_report(
            observe_records=[
                observe_record(decision="BLOCKED_QUALITY_GATE"),
            ],
            opportunity_rows=[
                opportunity_row(evaluated_at="2026-06-13T05:31:00Z", actionable=True),
            ],
            paper_trade_rows=[
                paper_trade_row(entry_ts="2026-06-13T05:35:00Z", net_bps=12.5),
            ],
            generated_at="2026-06-13T06:00:00Z",
            lookahead_minutes=60,
        )

        self.assertEqual(result["summary"]["observed_candidate_records"], 0)
        self.assertEqual(result["summary"]["observed_candidates_with_later_ready_window"], 0)
        self.assertEqual(result["summary"]["unique_later_paper_trades"], 0)
        self.assertEqual(result["observed_candidates"], [])
        self.assertEqual(result["by_pair_variant"], [])

    def test_repeated_observations_do_not_multiply_aggregate_paper_trade_counts(self) -> None:
        result = report.build_report(
            observe_records=[
                observe_record(observed_at="2026-06-13T05:30:00Z"),
                observe_record(observed_at="2026-06-13T05:31:00Z"),
            ],
            opportunity_rows=[],
            paper_trade_rows=[
                paper_trade_row(entry_ts="2026-06-13T05:35:00Z", net_bps=8.0),
            ],
            generated_at="2026-06-13T06:00:00Z",
            lookahead_minutes=60,
        )

        self.assertEqual(result["summary"]["observed_candidate_records"], 2)
        self.assertEqual(result["summary"]["observed_candidates_with_later_paper_trade"], 2)
        self.assertEqual(result["summary"]["unique_later_paper_trades"], 1)
        self.assertEqual(result["summary"]["sum_unique_later_paper_net_bps"], 8.0)
        self.assertEqual(result["by_pair_variant"][0]["observed_candidate_records"], 2)
        self.assertEqual(result["by_pair_variant"][0]["unique_later_paper_trades"], 1)

    def test_opposite_direction_rows_are_not_attributed_to_candidate(self) -> None:
        result = report.build_report(
            observe_records=[
                observe_record(),
            ],
            opportunity_rows=[
                opportunity_row(
                    evaluated_at="2026-06-13T05:31:00Z",
                    actionable=True,
                    direction_hint="LONG_SPREAD",
                ),
            ],
            paper_trade_rows=[
                paper_trade_row(
                    entry_ts="2026-06-13T05:35:00Z",
                    direction="LONG_SPREAD",
                    net_bps=12.5,
                ),
            ],
            generated_at="2026-06-13T06:00:00Z",
            lookahead_minutes=60,
        )

        self.assertEqual(result["summary"]["observed_candidate_records"], 1)
        self.assertEqual(result["summary"]["observed_candidates_with_later_ready_window"], 0)
        self.assertEqual(result["summary"]["observed_candidates_with_later_paper_trade"], 0)
        self.assertEqual(result["summary"]["unique_later_ready_windows"], 0)
        self.assertEqual(result["summary"]["unique_later_paper_trades"], 0)

    def test_non_1m_observe_record_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "AUTO-1C only accepts 1m observe records"):
            report.build_report(
                observe_records=[
                    observe_record(timeframe="15m"),
                ],
                opportunity_rows=[],
                paper_trade_rows=[],
                generated_at="2026-06-13T06:00:00Z",
                lookahead_minutes=60,
            )

    def test_cli_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            records_dir = root / "records" / "20260613"
            records_dir.mkdir(parents=True)
            observe_path = records_dir / "autopilot_observe_20260613.jsonl"
            observe_path.write_text(json.dumps(observe_record()) + "\n", encoding="utf-8")
            opportunity_path = root / "opportunity_history_1m.json"
            opportunity_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            opportunity_row(evaluated_at="2026-06-13T05:31:00Z", actionable=True),
                        ]
                    }
                ),
                encoding="utf-8",
            )
            paper_path = root / "paper_trades_1m.json"
            paper_path.write_text(
                json.dumps(
                    {
                        "rows": [
                            paper_trade_row(entry_ts="2026-06-13T05:35:00Z", net_bps=12.5),
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output_json = root / "report.json"
            output_markdown = root / "report.md"

            exit_code = report.main(
                [
                    "--observe-dir",
                    str(root / "records"),
                    "--opportunity-history-json",
                    str(opportunity_path),
                    "--paper-trades-json",
                    str(paper_path),
                    "--generated-at",
                    "2026-06-13T06:00:00Z",
                    "--lookahead-minutes",
                    "60",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_markdown),
                ]
            )

            self.assertEqual(exit_code, 0)
            output = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(output["summary"]["unique_later_paper_trades"], 1)
            self.assertIn(
                "AUTO-1C Observe-Only Attribution Report",
                output_markdown.read_text(encoding="utf-8"),
            )


class AutopilotObserveReportContractTests(unittest.TestCase):
    def validator(self) -> Draft202012Validator:
        schema_path = REPO_ROOT / "specs/contracts/autopilot_observe_report.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_report_example_matches_schema(self) -> None:
        example_path = REPO_ROOT / "specs/examples/autopilot_observe_report.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))

        errors = sorted(self.validator().iter_errors(example), key=str)

        self.assertEqual(errors, [])

    def test_generated_report_matches_schema(self) -> None:
        generated = report.build_report(
            observe_records=[observe_record()],
            opportunity_rows=[
                opportunity_row(evaluated_at="2026-06-13T05:31:00Z", actionable=True),
            ],
            paper_trade_rows=[
                paper_trade_row(entry_ts="2026-06-13T05:35:00Z", net_bps=12.5),
            ],
            generated_at="2026-06-13T06:00:00Z",
            lookahead_minutes=60,
        )

        errors = sorted(self.validator().iter_errors(generated), key=str)

        self.assertEqual(errors, [])
