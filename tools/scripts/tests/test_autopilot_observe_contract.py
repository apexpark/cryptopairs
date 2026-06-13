from __future__ import annotations

import json
import pathlib
import unittest

from jsonschema import Draft202012Validator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class AutopilotObserveContractTests(unittest.TestCase):
    def test_autopilot_observe_example_matches_schema(self) -> None:
        schema_path = REPO_ROOT / "specs/contracts/autopilot_observe_record.schema.json"
        example_path = REPO_ROOT / "specs/examples/autopilot_observe_record.example.json"

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_path.read_text(encoding="utf-8"))

        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(example), key=str)

        self.assertEqual(errors, [])
