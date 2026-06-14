from __future__ import annotations

import json
import pathlib
import sys
import unittest

from jsonschema import Draft202012Validator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "tools/scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import autopilot_observe as observe  # noqa: E402
from tests.test_autopilot_observe import OBSERVED_AT, RecordingGetClient, base_routes, config  # noqa: E402


class AutopilotObserveContractTests(unittest.TestCase):
    def validator(self) -> Draft202012Validator:
        schema_path = REPO_ROOT / "specs/contracts/autopilot_observe_record.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def test_autopilot_observe_example_matches_schema(self) -> None:
        example_path = REPO_ROOT / "specs/examples/autopilot_observe_record.example.json"

        example = json.loads(example_path.read_text(encoding="utf-8"))

        errors = sorted(self.validator().iter_errors(example), key=str)

        self.assertEqual(errors, [])

    def test_observed_candidate_example_does_not_use_fail_closed_dispatch(self) -> None:
        example_path = REPO_ROOT / "specs/examples/autopilot_observe_record.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))

        if example["decision"] == "OBSERVED_ENTRY_CANDIDATE":
            self.assertNotEqual(example["dispatch_mode"], "FAIL_CLOSED")

    def test_generated_allowed_and_blocked_records_match_schema(self) -> None:
        validator = self.validator()
        routes = base_routes()
        allowed = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )[0]
        routes["http://execution/v1/execution/dispatch-mode"]["mode"] = "FAIL_CLOSED"
        blocked = observe.run_once(
            config(),
            client=RecordingGetClient(routes),
            observed_at=OBSERVED_AT,
            seen_keys=set(),
        )[0]

        for record in (allowed, blocked):
            errors = sorted(validator.iter_errors(record), key=str)
            self.assertEqual(errors, [])
