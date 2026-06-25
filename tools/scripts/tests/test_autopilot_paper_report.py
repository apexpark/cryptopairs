from __future__ import annotations

import inspect
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

import autopilot_paper_report as report  # noqa: E402


def run_config(
    *,
    run_id: str = "20260618T064500Z",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    selected_variant: str = "ROBUST_Z",
    timeframe: str = "1m",
    hold_window_bars: int = 5,
    max_runtime_seconds: int = 86400,
    max_observe_candidate_age_seconds: int = 120,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "timeframe": timeframe,
        "static_allowlist": [
            {
                "pair_id": pair_id,
                "selected_variant": selected_variant,
            }
        ],
        "hold_window_bars": hold_window_bars,
        "max_runtime_seconds": max_runtime_seconds,
        "max_observe_candidate_age_seconds": max_observe_candidate_age_seconds,
    }


def decision_record(
    *,
    decision_type: str = "PAPER_ENTRY_OPENED",
    observed_at: str = "2026-06-18T06:45:00Z",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    timeframe: str = "1m",
    selected_variant: str = "ROBUST_Z",
    direction: str = "SHORT_SPREAD",
    paper_position_id: str = (
        "paper-position:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
        "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:45:00Z"
    ),
    realized_net_bps: float | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "paper_only",
        "run_id": f"{observed_at}-paper-1m",
        "observed_at": observed_at,
        "decision_type": decision_type,
        "decision_reason": "test decision",
        "reason_codes": ["TEST_REASON"],
        "pair_id": pair_id,
        "timeframe": timeframe,
        "selected_variant": selected_variant,
        "direction": direction,
        "source_generated_at": "2026-06-18T06:44:52Z",
        "observe_key": (
            f"observe-only:v1:{timeframe}:{pair_id}:{selected_variant}:"
            f"{direction}:2026-06-18T06:45:00Z"
        ),
        "paper_position_id": paper_position_id,
        "hold_window_bars": 5,
        "cooldown_seconds": 300,
        "exit_eligible_at": "2026-06-18T06:50:00Z",
        "exit_source_type": "paper_trade_outcome"
        if decision_type == "PAPER_EXIT_COMPLETED"
        else None,
        "exit_source_at": "2026-06-18T06:50:15Z"
        if decision_type == "PAPER_EXIT_COMPLETED"
        else None,
        "realized_net_bps": realized_net_bps,
        "evidence": {
            "static_allowlist_size": 1,
            "candidate_timeframe": timeframe,
            "candidate_source": "observe_record",
            "mark_source": "paper_trade_outcome"
            if decision_type == "PAPER_EXIT_COMPLETED"
            else None,
            "existing_open_position": False,
            "cooldown_until": None,
        },
    }


def position_record(
    *,
    status: str = "OPEN",
    pair_id: str = "PF_DOGEUSD__PF_PEPEUSD",
    timeframe: str = "1m",
    selected_variant: str = "ROBUST_Z",
    direction: str = "SHORT_SPREAD",
    paper_position_id: str = (
        "paper-position:v1:1m:PF_DOGEUSD__PF_PEPEUSD:"
        "ROBUST_Z:SHORT_SPREAD:2026-06-18T06:45:00Z"
    ),
    realized_net_bps: float | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "paper_only",
        "paper_position_id": paper_position_id,
        "pair_id": pair_id,
        "timeframe": timeframe,
        "selected_variant": selected_variant,
        "direction": direction,
        "status": status,
        "entry_observed_at": "2026-06-18T06:45:00Z",
        "entry_score_z": 2.12,
        "entry_net_edge_bps": 19.5,
        "source_generated_at": "2026-06-18T06:44:52Z",
        "entry_observe_key": (
            f"observe-only:v1:{timeframe}:{pair_id}:{selected_variant}:"
            f"{direction}:2026-06-18T06:45:00Z"
        ),
        "hold_window_bars": 5,
        "exit_eligible_at": "2026-06-18T06:50:00Z",
        "exit_observed_at": "2026-06-18T06:50:15Z" if status == "CLOSED" else None,
        "exit_reason": "HOLD_WINDOW_MARK" if status == "CLOSED" else None,
        "exit_source_type": "paper_trade_outcome" if status == "CLOSED" else None,
        "realized_net_bps": realized_net_bps if status == "CLOSED" else None,
    }


class AutopilotPaperReportTests(unittest.TestCase):
    def test_report_summarizes_latest_position_state_and_realized_pnl(self) -> None:
        generated = report.build_report(
            run_config=run_config(),
            paper_decisions=[
                decision_record(),
                decision_record(
                    decision_type="PAPER_EXIT_COMPLETED",
                    observed_at="2026-06-18T06:51:00Z",
                    realized_net_bps=7.25,
                ),
                decision_record(
                    decision_type="PAPER_EXIT_DEFERRED_MARK_UNAVAILABLE",
                    observed_at="2026-06-18T06:52:00Z",
                ),
            ],
            paper_positions=[
                position_record(status="OPEN"),
                position_record(status="CLOSED", realized_net_bps=7.25),
            ],
            generated_at="2026-06-18T07:00:00Z",
        )

        self.assertEqual(generated["schema_version"], 1)
        self.assertEqual(generated["mode"], "paper_only_report")
        self.assertEqual(generated["run_config"]["run_id"], "20260618T064500Z")
        self.assertEqual(generated["run_config"]["timeframe"], "1m")
        self.assertEqual(generated["run_config"]["hold_window_bars"], 5)
        self.assertEqual(generated["run_config"]["max_runtime_seconds"], 86400)
        self.assertEqual(generated["run_config"]["max_observe_candidate_age_seconds"], 120)
        self.assertEqual(
            generated["run_config"]["static_allowlist"],
            [
                {
                    "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
                    "selected_variant": "ROBUST_Z",
                }
            ],
        )
        self.assertEqual(generated["scope"]["timeframe"], "1m")
        self.assertEqual(generated["summary"]["decision_records"], 3)
        self.assertEqual(generated["summary"]["entry_opened_decisions"], 1)
        self.assertEqual(generated["summary"]["exit_completed_decisions"], 1)
        self.assertEqual(generated["summary"]["exit_deferred_decisions"], 1)
        self.assertEqual(generated["summary"]["unique_positions"], 1)
        self.assertEqual(generated["summary"]["open_positions"], 0)
        self.assertEqual(generated["summary"]["closed_positions"], 1)
        self.assertEqual(generated["summary"]["profitable_closed_positions"], 1)
        self.assertEqual(generated["summary"]["sum_realized_net_bps"], 7.25)
        self.assertEqual(generated["summary"]["avg_realized_net_bps"], 7.25)

        pair_row = generated["by_pair_variant"][0]
        self.assertEqual(pair_row["pair_id"], "PF_DOGEUSD__PF_PEPEUSD")
        self.assertEqual(pair_row["closed_positions"], 1)
        self.assertEqual(pair_row["sum_realized_net_bps"], 7.25)
        self.assertEqual(generated["closed_positions"][0]["realized_net_bps"], 7.25)
        self.assertEqual(generated["open_positions"], [])

    def test_report_includes_blocked_decision_breakdown(self) -> None:
        generated = report.build_report(
            run_config=run_config(),
            paper_decisions=[
                decision_record(decision_type="BLOCKED_DUPLICATE_CANDIDATE"),
                decision_record(decision_type="BLOCKED_COOLDOWN"),
                decision_record(decision_type="BLOCKED_COOLDOWN"),
                decision_record(decision_type="BLOCKED_STALE_INPUT"),
            ],
            paper_positions=[],
            generated_at="2026-06-18T07:00:00Z",
        )

        self.assertEqual(generated["summary"]["blocked_decisions"], 4)
        self.assertEqual(
            generated["summary"]["block_breakdown"],
            {
                "BLOCKED_COOLDOWN": 2,
                "BLOCKED_DUPLICATE_CANDIDATE": 1,
                "BLOCKED_STALE_INPUT": 1,
            },
        )

    def test_non_1m_paper_artifacts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "AUTO-2A paper report only accepts 1m"):
            report.build_report(
                run_config=run_config(),
                paper_decisions=[decision_record(timeframe="15m")],
                paper_positions=[],
                generated_at="2026-06-18T07:00:00Z",
            )

    def test_non_1m_run_config_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "AUTO-2A paper report only accepts 1m"):
            report.build_report(
                run_config=run_config(timeframe="15m"),
                paper_decisions=[],
                paper_positions=[],
                generated_at="2026-06-18T07:00:00Z",
            )

    def test_cli_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            day_dir = root / "records" / "20260618"
            day_dir.mkdir(parents=True)
            decisions_path = day_dir / "autopilot_paper_decisions_20260618.jsonl"
            positions_path = day_dir / "autopilot_paper_positions_20260618.jsonl"
            decisions_path.write_text(
                json.dumps(decision_record()) + "\n"
                + json.dumps(
                    decision_record(
                        decision_type="PAPER_EXIT_COMPLETED",
                        observed_at="2026-06-18T06:51:00Z",
                        realized_net_bps=7.25,
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            positions_path.write_text(
                json.dumps(position_record(status="OPEN")) + "\n"
                + json.dumps(position_record(status="CLOSED", realized_net_bps=7.25))
                + "\n",
                encoding="utf-8",
            )
            run_config_path = root / "run_config.json"
            run_config_path.write_text(json.dumps(run_config()) + "\n", encoding="utf-8")
            output_json = root / "paper_report.json"
            output_markdown = root / "paper_report.md"

            exit_code = report.main(
                [
                    "--paper-dir",
                    str(root / "records"),
                    "--run-config-json",
                    str(run_config_path),
                    "--generated-at",
                    "2026-06-18T07:00:00Z",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_markdown),
                ]
            )

            self.assertEqual(exit_code, 0)
            output = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(output["summary"]["closed_positions"], 1)
            self.assertEqual(output["run_config"]["hold_window_bars"], 5)
            self.assertIn(
                "AUTO-2A Paper Report",
                output_markdown.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z",
                output_markdown.read_text(encoding="utf-8"),
            )

    def test_report_tool_has_no_execution_http_surface(self) -> None:
        source = inspect.getsource(report)

        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("order-intent", source)
        self.assertNotIn("dispatch", source)


class AutopilotPaperReportContractTests(unittest.TestCase):
    def validator(self) -> Draft202012Validator:
        schema_path = REPO_ROOT / "specs/contracts/autopilot_paper_report.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_report_example_matches_schema(self) -> None:
        example_path = REPO_ROOT / "specs/examples/autopilot_paper_report.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))

        errors = sorted(self.validator().iter_errors(example), key=str)

        self.assertEqual(errors, [])

    def test_generated_report_matches_schema(self) -> None:
        generated = report.build_report(
            run_config=run_config(),
            paper_decisions=[decision_record()],
            paper_positions=[position_record(status="OPEN")],
            generated_at="2026-06-18T07:00:00Z",
        )

        errors = sorted(self.validator().iter_errors(generated), key=str)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
