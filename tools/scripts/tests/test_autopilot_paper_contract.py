from __future__ import annotations

import json
import pathlib
import unittest

from jsonschema import Draft202012Validator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def validate_example(schema_name: str, example_name: str) -> dict:
    schema_path = REPO_ROOT / "specs/contracts" / schema_name
    example_path = REPO_ROOT / "specs/examples" / example_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    example = json.loads(example_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(example), key=str)
    if errors:
        raise AssertionError(errors)
    return example


class AutopilotPaperContractTests(unittest.TestCase):
    def validator(self, schema_name: str) -> Draft202012Validator:
        schema_path = REPO_ROOT / "specs/contracts" / schema_name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_decision_record_example_matches_schema_and_is_paper_only(self) -> None:
        example = validate_example(
            "autopilot_paper_decision_record.schema.json",
            "autopilot_paper_decision_record.example.json",
        )

        self.assertEqual(example["mode"], "paper_only")
        self.assertEqual(example["timeframe"], "1m")
        self.assertNotIn("order_intent", json.dumps(example))

    def test_position_example_matches_schema_and_is_paper_only(self) -> None:
        example = validate_example(
            "autopilot_paper_position.schema.json",
            "autopilot_paper_position.example.json",
        )

        self.assertEqual(example["mode"], "paper_only")
        self.assertEqual(example["timeframe"], "1m")
        self.assertIn(example["status"], {"OPEN", "CLOSED"})
        self.assertNotIn("order_intent", json.dumps(example))

    def test_exit_completed_decision_requires_realized_result_fields(self) -> None:
        example = validate_example(
            "autopilot_paper_decision_record.schema.json",
            "autopilot_paper_decision_record.example.json",
        )
        invalid = dict(example)
        invalid.update(
            {
                "decision_type": "PAPER_EXIT_COMPLETED",
                "exit_source_type": None,
                "exit_source_at": None,
                "realized_net_bps": None,
            }
        )

        errors = sorted(
            self.validator("autopilot_paper_decision_record.schema.json").iter_errors(
                invalid
            ),
            key=str,
        )

        self.assertNotEqual(errors, [])

    def test_closed_position_requires_realized_result_fields(self) -> None:
        example = validate_example(
            "autopilot_paper_position.schema.json",
            "autopilot_paper_position.example.json",
        )
        invalid = dict(example)
        invalid.update({"status": "CLOSED"})

        errors = sorted(
            self.validator("autopilot_paper_position.schema.json").iter_errors(invalid),
            key=str,
        )

        self.assertNotEqual(errors, [])

    def test_closed_position_requires_entry_observe_key(self) -> None:
        example = validate_example(
            "autopilot_paper_position.schema.json",
            "autopilot_paper_position.example.json",
        )
        invalid = dict(example)
        invalid.update(
            {
                "status": "CLOSED",
                "entry_observe_key": None,
                "exit_observed_at": "2026-06-18T06:50:15Z",
                "exit_reason": "HOLD_WINDOW_MARK",
                "exit_source_type": "paper_trade_outcome",
                "realized_net_bps": 7.25,
            }
        )

        errors = sorted(
            self.validator("autopilot_paper_position.schema.json").iter_errors(invalid),
            key=str,
        )

        self.assertNotEqual(errors, [])

    def test_open_position_requires_entry_observe_key(self) -> None:
        example = validate_example(
            "autopilot_paper_position.schema.json",
            "autopilot_paper_position.example.json",
        )
        invalid = dict(example)
        invalid.update({"status": "OPEN", "entry_observe_key": None})

        errors = sorted(
            self.validator("autopilot_paper_position.schema.json").iter_errors(invalid),
            key=str,
        )

        self.assertNotEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
