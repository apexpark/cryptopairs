from __future__ import annotations

import datetime as dt
import json
import os
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


class _StopLoop(Exception):
    """Sentinel to break out of an otherwise-unbounded loop under test."""


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
        "rationale_codes": ["LEARNING_SELECTED"],
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
        tick_example = json.loads(
            (repo_root / "specs/examples/autopilot_observe_record.selector_view_tick.example.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(sorted(validator.iter_errors(entry_example), key=str), [])
        self.assertEqual(
            sorted(validator.iter_errors(selector_view_example), key=str), []
        )
        self.assertEqual(selector_view_example["capture_profile"], "selector_view")
        self.assertEqual(selector_view_example["decision"], "SELECTOR_VIEW_OBSERVED")

        # The tick manifest is its own record type. Validating it against the
        # whole schema (a oneOf) also proves the branches stay mutually
        # exclusive: a manifest must match the manifest branch and no other.
        self.assertEqual(sorted(validator.iter_errors(tick_example), key=str), [])
        self.assertEqual(tick_example["capture_profile"], "selector_view_tick")
        self.assertEqual(tick_example["decision"], "SELECTOR_VIEW_TICK_CAPTURED")
        self.assertEqual(
            tick_example["recorded_rows"], sum(tick_example["rows_per_bucket"].values())
        )
        # A live manifest built by the tool validates too, empty universe included.
        for rows_per_bucket in (
            {"TRADE_NOW": 0, "WATCHLIST": 0, "EXCLUDED": 0},
            {"TRADE_NOW": 2, "WATCHLIST": 1, "EXCLUDED": 7},
        ):
            built = observe.selector_view_tick_record(
                observed_at=OBSERVED_AT,
                source_generated="2026-06-13T05:29:57Z",
                rows_per_bucket=rows_per_bucket,
            )
            self.assertEqual(sorted(validator.iter_errors(built), key=str), [])
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
            schema["oneOf"][2],  # the tick manifest is a selector-view surface too
            snapshot_schema["properties"]["selector_view"],
            snapshot_schema["properties"]["universe"],
            snapshot_schema["properties"]["churn"]["oneOf"][1]["properties"]["selector_view"],
        ]
        forbidden_tokens = ("realized", "pnl", "outcome", "fill", "estimated", "simulated")
        for node in guarded_nodes:
            for field_name in property_names(node):
                for forbidden in forbidden_tokens:
                    self.assertNotIn(forbidden, field_name.lower())

    def test_tick_manifest_contract_rejects_out_of_contract_identity(self) -> None:
        """The manifest branch must reject a tick that misstates its own identity.

        The manifest is the sole positive marker that a tick was captured, so a
        consumer keys off its run_id/observed_at/timeframe. Left loose, the
        branch would accept an empty run_id, a timestamp that is not a
        timestamp, or a non-1m tick — each of which reads as a valid capture
        downstream. These are the adversarial cases the tightened contract must
        refuse.
        """
        from jsonschema import Draft202012Validator

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        schema = json.loads(
            (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
            .read_text(encoding="utf-8")
        )
        format_checker = Draft202012Validator.FORMAT_CHECKER
        # `format` is annotation-only unless a checker is passed, and the
        # date-time checker itself no-ops unless its backing dependency is
        # installed. Without this guard every assertion below would pass
        # vacuously in an environment that cannot check date-time at all, and
        # the contract would look enforced while enforcing nothing.
        self.assertFalse(
            format_checker.conforms("not-a-timestamp", "date-time"),
            "date-time format checking is inactive (rfc3339-validator missing); "
            "these assertions would pass vacuously",
        )
        validator = Draft202012Validator(schema, format_checker=format_checker)

        valid = json.loads(
            (repo_root / "specs/examples/autopilot_observe_record.selector_view_tick.example.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(sorted(validator.iter_errors(valid), key=str), [])

        # Each case mutates exactly one field of an otherwise-valid manifest, so
        # a rejection can only be attributed to that field.
        for field, bad_value, case in (
            ("run_id", "", "empty run_id"),
            ("run_id", "   ", "blank run_id"),
            ("run_id", "not-a-timestamp", "run_id that is not a date-time"),
            ("observed_at", "", "empty observed_at"),
            ("observed_at", "2026-07-16", "date-only observed_at"),
            ("observed_at", "16/07/2026 00:05", "non-ISO observed_at"),
            ("source_generated_at", "", "empty source_generated_at"),
            ("source_generated_at", "not-a-timestamp", "invalid source_generated_at"),
            ("timeframe", "5m", "non-1m timeframe"),
            ("timeframe", "1h", "non-1m timeframe"),
            ("timeframe", "", "empty timeframe"),
        ):
            with self.subTest(case=case, field=field):
                record = deepcopy(valid)
                record[field] = bad_value
                self.assertNotEqual(
                    sorted(validator.iter_errors(record), key=str),
                    [],
                    f"schema accepted {case}",
                )

        # A null in either required timestamp is rejected too: the manifest
        # declares both non-nullable, unlike the entry row's nullable
        # source_generated_at.
        for field in ("observed_at", "source_generated_at", "run_id"):
            with self.subTest(case="null", field=field):
                record = deepcopy(valid)
                record[field] = None
                self.assertNotEqual(
                    sorted(validator.iter_errors(record), key=str), [], f"schema accepted null {field}"
                )

        # The tool's own manifests satisfy the tightened contract under the same
        # format checker — the constraints describe what it actually emits.
        built = observe.selector_view_tick_record(
            observed_at=OBSERVED_AT,
            source_generated="2026-06-13T05:29:57Z",
            rows_per_bucket={"TRADE_NOW": 0, "WATCHLIST": 0, "EXCLUDED": 0},
        )
        self.assertEqual(sorted(validator.iter_errors(built), key=str), [])
        self.assertEqual(built["run_id"], built["observed_at"])
        self.assertEqual(built["timeframe"], "1m")

    def test_emitted_records_are_rfc3339_even_when_the_cue_timestamp_is_not(self) -> None:
        """A tightened contract is only real if the tool cannot violate it.

        The freshness gate's predicate is `datetime.fromisoformat`, which is
        strictly wider than the RFC 3339 `format: date-time` the manifest branch
        declares: a naive timestamp with no offset, ISO basic form, or a
        one-digit fraction all parse fine and would previously be recorded raw —
        emitting a manifest that fails its own schema branch while the tick
        looked captured. Drives the real capture path, not a hand-built record.
        """
        from jsonschema import Draft202012Validator

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        schema = json.loads(
            (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
            .read_text(encoding="utf-8")
        )
        format_checker = Draft202012Validator.FORMAT_CHECKER
        self.assertFalse(
            format_checker.conforms("not-a-timestamp", "date-time"),
            "date-time format checking is inactive; this test would pass vacuously",
        )
        validator = Draft202012Validator(schema, format_checker=format_checker)

        for raw, case in (
            ("2026-06-13T05:29:57Z", "already RFC 3339"),
            ("2026-06-13T05:29:57", "naive, no offset"),
            ("2026-06-13T05:29:57.5", "one-digit fraction"),
            ("2026-06-13T07:29:57+02:00", "non-UTC offset"),
        ):
            with self.subTest(case=case):
                cue_url = "http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"
                routes = base_routes()
                routes[cue_url] = {**routes[cue_url], "generated_at": raw}
                records = observe.run_once(
                    config(capture_selector_view=True),
                    client=RecordingGetClient(routes),
                    observed_at=OBSERVED_AT,
                )

                self.assertTrue(records, f"{case}: tick produced no records")
                # The whole tick must be in contract, manifest and rows alike.
                for record in records:
                    self.assertEqual(
                        sorted(validator.iter_errors(record), key=str),
                        [],
                        f"{case}: emitted record violates its own schema branch",
                    )
                manifest = records[0]
                self.assertEqual(manifest["capture_profile"], "selector_view_tick")
                # Same instant as the source, restated in the declared form.
                # Compared at whole-second resolution because iso() truncates
                # sub-second precision — the same canonical form every other
                # timestamp the tool records already uses, and immaterial at the
                # 1m timeframe this capture is scoped to.
                self.assertEqual(
                    observe.parse_iso(manifest["source_generated_at"]),
                    observe.parse_iso(raw).replace(microsecond=0),
                    f"{case}: normalization moved the instant by more than the "
                    f"sub-second truncation iso() is defined to apply",
                )

    def test_selector_view_mode_captures_all_buckets_and_is_schema_valid(self) -> None:
        from jsonschema import Draft202012Validator

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        schema = json.loads(
            (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)

        routes = base_routes()
        payload = routes["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"]
        watch = deepcopy(candidate())
        watch["pair_id"] = "PF_SOLUSD__PF_AVAXUSD"
        watch["decision_bucket"] = "WATCHLIST"
        watch["watch_reason_code"] = "WATCH_ENTRY_DISTANCE"
        excluded = deepcopy(candidate())
        excluded["pair_id"] = "PF_XBTUSD__PF_BNBUSD"
        excluded["decision_bucket"] = "EXCLUDED"
        excluded["blocked_reason_code"] = "COST_GATE_FAIL"
        payload["watchlist"] = [watch]
        payload["excluded"] = [excluded]
        client = RecordingGetClient(routes)

        records = observe.run_once(
            config(capture_selector_view=True), client=client, observed_at=OBSERVED_AT
        )

        # A captured tick is one manifest followed by every candidate across all
        # three buckets. (A malformed row would refuse the whole tick instead —
        # see the refusal tests below; this response is deliberately all-valid.)
        manifest, rows = records[0], records[1:]
        self.assertEqual(manifest["capture_profile"], "selector_view_tick")
        self.assertEqual(manifest["decision"], "SELECTOR_VIEW_TICK_CAPTURED")
        self.assertEqual(manifest["recorded_rows"], 3)
        self.assertEqual(
            manifest["rows_per_bucket"], {"TRADE_NOW": 1, "WATCHLIST": 1, "EXCLUDED": 1}
        )
        self.assertEqual(sorted(validator.iter_errors(manifest), key=str), [])

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            sorted(r["cue_bucket"] for r in rows),
            ["EXCLUDED", "TRADE_NOW", "WATCHLIST"],
        )
        for record in rows:
            self.assertEqual(record["decision"], "SELECTOR_VIEW_OBSERVED")
            self.assertEqual(record["capture_profile"], "selector_view")
            self.assertEqual(sorted(validator.iter_errors(record), key=str), [])
            self.assertNotIn("realized_net_bps", record)
            self.assertTrue(record["observe_key"].startswith("selector-view:v2:"))

    def test_selector_view_loop_requires_positive_max_runtime(self) -> None:
        # Codex finding 2: an unbounded selector-view loop is both an unattended
        # loop and unbounded disk growth. Startup must be refused unless a
        # positive runtime bound is configured. Each case returns before any
        # network client is constructed.
        import contextlib, io
        from unittest import mock

        base = {
            "AUTOPILOT_OBSERVE_ENABLED": "true",
            "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true",
            "AUTOPILOT_OBSERVE_LOOP": "true",
        }
        for label, extra in (
            ("absent", {}),
            ("empty", {"AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": ""}),
            ("zero", {"AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": "0"}),
            ("negative", {"AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": "-300"}),
        ):
            with self.subTest(max_runtime=label):
                buf = io.StringIO()
                with mock.patch.dict(os.environ, {**base, **extra}, clear=True):
                    with contextlib.redirect_stderr(buf):
                        rc = observe.main([])
                self.assertEqual(rc, 2, label)
                payload = json.loads(buf.getvalue().strip().splitlines()[-1])
                self.assertEqual(payload["error"], "SELECTOR_VIEW_LOOP_REQUIRES_MAX_RUNTIME")

    def test_selector_view_loop_with_positive_max_runtime_starts(self) -> None:
        # The guard must not block a properly bounded selector-view loop.
        # run_once is stubbed so no network is touched; a single tick then exits
        # because elapsed + interval >= max_runtime.
        from unittest import mock

        env = {
            "AUTOPILOT_OBSERVE_ENABLED": "true",
            "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true",
            "AUTOPILOT_OBSERVE_LOOP": "true",
            "AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": "1",
            "AUTOPILOT_OBSERVE_INTERVAL_SECONDS": "300",
        }
        with tempfile.TemporaryDirectory() as tmp:
            env["AUTOPILOT_OBSERVE_OUTPUT_DIR"] = tmp
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.object(observe, "run_once", return_value=[]) as ran:
                    with mock.patch.object(observe, "JsonGetClient"):
                        rc = observe.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(ran.call_count, 1)  # started, ticked once, exited on bound

    def test_selector_view_argv_identity_is_exact_not_any_observe_process(self) -> None:
        # Codex round-6 finding 2: the stop procedure must identify the *exact*
        # selector-view process. Both the narrow paper-feeding run and the
        # selector-view run are launched as `python3 .../autopilot_observe.py`
        # with everything else supplied by the environment, so matching on the
        # script name alone matches BOTH — and would stop the narrow run if the
        # selector-view PID file were stale and its PID reused. Only the
        # explicit flag in argv distinguishes them.
        for argv, expected, why in (
            (["python3", "tools/scripts/autopilot_observe.py"], False,
             "narrow paper-feeding run: same script, no flag"),
            (["python3", "tools/scripts/autopilot_observe.py", "--capture-selector-view"],
             True, "the selector-view run"),
            (["python3", "/opt/cryptopairs/tools/scripts/autopilot_observe.py",
              "--capture-selector-view", "--once"], True, "absolute path, extra flags"),
            (["python3", "autopilot_observe.py", "--capture-selector-view"], True,
             "bare script name"),
            (["python3", "-u", "tools/scripts/autopilot_observe.py",
              "--capture-selector-view"], True, "interpreter flags before the script"),
            (["/usr/bin/python3.11", "tools/scripts/autopilot_observe.py",
              "--capture-selector-view"], True, "versioned absolute interpreter"),
            (["./tools/scripts/autopilot_observe.py", "--capture-selector-view"], True,
             "executed directly via its shebang"),
            ([], False, "no argv at all"),
            (["python3", "some_other_tool.py", "--capture-selector-view"], False,
             "the flag alone is not enough: must be this script"),
            (["python3", "tools/scripts/autopilot_observe.py",
              "--capture-selector-view-typo"], False,
             "token-exact: a lookalike flag is not the flag"),
            (["grep", "--capture-selector-view", "autopilot_observe.py"], False,
             "a process merely mentioning both tokens is not the capture"),
            (["python3", "other.py", "autopilot_observe.py", "--capture-selector-view"],
             False, "script name as a later argument is not the program being run"),
            # The false positive that matters most: a narrow run whose ARGUMENT
            # VALUE contains the flag text. With exact argv the value stays one
            # token and cannot masquerade as the flag.
            (["python3", "tools/scripts/autopilot_observe.py", "--output-dir",
              "/tmp/out --capture-selector-view"], False,
             "flag text inside an argument value is not the flag"),
        ):
            with self.subTest(command=why):
                self.assertIs(observe.selector_view_argv_matches(argv), expected, why)

    def test_verify_refuses_when_argv_cannot_be_read_exactly(self) -> None:
        # `ps` renders argv space-joined and unquoted, so it cannot be split
        # back into argv: an argument value containing the flag text would
        # re-split into a token that looks like the flag, and the probe would
        # green-light killing the narrow run. When argv is not exact the probe
        # refuses rather than trusting it.
        from unittest import mock

        looks_like_capture = [
            "python3", "tools/scripts/autopilot_observe.py", "--capture-selector-view",
        ]
        with mock.patch.object(observe, "process_argv", return_value=(looks_like_capture, False)):
            safe, verdict = observe.verify_selector_view_pid(4242)
        self.assertFalse(safe)
        self.assertEqual(verdict["verdict"], "IDENTITY_NOT_VERIFIABLE")

        with mock.patch.object(observe, "process_argv", return_value=(looks_like_capture, True)):
            safe, verdict = observe.verify_selector_view_pid(4242)
        self.assertTrue(safe)
        self.assertEqual(verdict["verdict"], "SELECTOR_VIEW_CAPTURE")

    def test_verify_selector_view_pid_refuses_wrong_or_stale_pid(self) -> None:
        # The verdict gates a signal, so every non-confirming case must be
        # unsafe-to-signal (exit 2) rather than a guess.
        import contextlib, io
        from unittest import mock

        cases = (
            ("narrow run", (["python3", "tools/scripts/autopilot_observe.py"], True),
             2, "NOT_SELECTOR_VIEW_CAPTURE"),
            ("stale pid", (None, False), 2, "NO_SUCH_PROCESS"),
            ("selector-view run",
             (["python3", "tools/scripts/autopilot_observe.py", "--capture-selector-view"], True),
             0, "SELECTOR_VIEW_CAPTURE"),
        )
        for label, argv_result, expected_rc, verdict in cases:
            with self.subTest(case=label):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(observe, "process_argv", return_value=argv_result):
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        rc = observe.main(["--verify-selector-view-pid", "4242"])
                self.assertEqual(rc, expected_rc, label)
                payload = json.loads((out.getvalue() or err.getvalue()).strip())
                self.assertEqual(payload["verdict"], verdict)
                self.assertIs(payload["safe_to_signal"], expected_rc == 0)

    def test_verify_selector_view_pid_signals_nothing_and_ignores_env(self) -> None:
        # The probe is a pure question: it must not kill anything, and must
        # answer even when the observer is disabled by default in the env.
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(observe, "process_argv", return_value=(None, False)):
                with mock.patch.object(observe, "os") as fake_os:
                    with mock.patch("sys.stderr"):
                        rc = observe.main(["--verify-selector-view-pid", "4242"])
        self.assertEqual(rc, 2)
        fake_os.kill.assert_not_called()

    def test_sigterm_lets_the_in_flight_tick_finish_its_append(self) -> None:
        # Codex round-6 finding 2: the runbook then claimed SIGTERM "lets the
        # current tick finish its write", but with no handler the default
        # disposition terminates the process immediately and can cut a JSONL
        # append in half. (Round 7 narrowed that claim — a stop only finishes the
        # tick once it is past abandoning, which is exactly the mid-append case
        # pinned here — and scoped the handler to selector-view loops, which is
        # why this test sets the capture flag.)
        # Deliver a real SIGTERM to this process from inside write_records —
        # i.e. mid-append — and assert the tick still lands complete and the
        # loop then exits on its own.
        import signal as signal_mod
        from unittest import mock

        real_write = observe.write_records
        state = {"ticks": 0}

        def write_and_get_signalled(records, output_dir, observed_at):
            state["ticks"] += 1
            os.kill(os.getpid(), signal_mod.SIGTERM)  # arrives mid-tick
            return real_write(records, output_dir, observed_at)

        env = {
            "AUTOPILOT_OBSERVE_ENABLED": "true",
            "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true",
            "AUTOPILOT_OBSERVE_LOOP": "true",
            "AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": "86400",  # would run all day
            "AUTOPILOT_OBSERVE_INTERVAL_SECONDS": "300",       # would sleep 5 min
            # Point at the in-test fake services so the tick is a real capture
            # with rows to append, not a source-unavailable system record.
            "DATA_SERVICE_URL": "http://data",
            "STRATEGY_SERVICE_URL": "http://strategy",
            "EXECUTION_SERVICE_URL": "http://execution",
        }
        routes = base_routes()
        previous = signal_mod.getsignal(signal_mod.SIGTERM)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env["AUTOPILOT_OBSERVE_OUTPUT_DIR"] = tmp
                with mock.patch.dict(os.environ, env, clear=True):
                    with mock.patch.object(
                        observe, "JsonGetClient", lambda: RecordingGetClient(routes)
                    ):
                        with mock.patch.object(observe, "utc_now", return_value=OBSERVED_AT):
                            with mock.patch.object(
                                observe, "write_records", write_and_get_signalled
                            ):
                                rc = observe.main([])

                written = sorted(pathlib.Path(tmp).rglob("autopilot_observe_*.jsonl"))
                self.assertEqual(len(written), 1)
                lines = [
                    line for line in
                    written[0].read_text(encoding="utf-8").splitlines() if line.strip()
                ]
        finally:
            signal_mod.signal(signal_mod.SIGTERM, previous)

        self.assertEqual(rc, 0)                 # clean exit, not a kill
        self.assertEqual(state["ticks"], 1)     # stopped; did not start another tick
        # The in-flight append completed: every line is whole, parseable JSON,
        # and the tick's manifest and rows are all present.
        records = [json.loads(line) for line in lines]
        manifests = [r for r in records if r.get("capture_profile") == "selector_view_tick"]
        rows = [r for r in records if r.get("capture_profile") == "selector_view"]
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]["recorded_rows"], len(rows))

    def test_stop_while_polling_abandons_the_tick_instead_of_waiting_out_every_fetch(
        self,
    ) -> None:
        # A tick makes 7 sequential fetches, each able to burn the full timeout
        # against an unresponsive endpoint. If a stop only took effect after the
        # whole tick, exit could take ~7x the timeout — past the runbook's ~30s
        # escalation gate, and precisely in the degraded case where an operator
        # most wants to stop. Worse, it would steer them to the `kill -9` this
        # handling exists to avoid. A stop while polling must abandon the tick.
        stop = observe.StopSignal()
        fetched: list[str] = []

        def fetch_then_stop(_client, url, _timeout):
            fetched.append(url)
            stop.request(15)  # a stop lands during the very first fetch
            return {"status": "ok"}, "OK", None

        with unittest.mock.patch.object(observe, "fetch_source", fetch_then_stop):
            records = observe.run_once(
                config(capture_selector_view=True),
                client=object(),
                observed_at=OBSERVED_AT,
                stop=stop,
            )

        # Abandoned: nothing is recorded, so nothing partial reaches the
        # artifact and the tick reads downstream as missing — which it is.
        self.assertIsNone(records)
        # It stopped at the next fetch boundary rather than completing all 7.
        self.assertEqual(len(fetched), 1)

    def test_run_once_without_stop_is_unchanged(self) -> None:
        # The stop parameter is opt-in: every existing caller (and --once) must
        # keep getting a list, never None.
        records = observe.run_once(
            config(capture_selector_view=True),
            client=RecordingGetClient(base_routes()),
            observed_at=OBSERVED_AT,
        )
        self.assertIsInstance(records, list)
        self.assertTrue(records)

    def test_sigterm_during_sleep_stops_without_waiting_out_the_interval(self) -> None:
        # PEP 475 resumes an interrupted time.sleep for its full remaining
        # duration, so a flag alone would leave a stop unnoticed for up to a
        # whole interval (300s in the runbook). The sleep must poll the flag.
        stop = observe.StopSignal()

        def request_stop_partway(_seconds):
            stop.request(15)  # as the handler would, from another context

        with unittest.mock.patch.object(observe.time, "sleep", request_stop_partway):
            started = observe.time.monotonic()
            observe.sleep_until_interval_or_stop(300, stop)
            elapsed = observe.time.monotonic() - started

        self.assertTrue(stop.requested)
        self.assertLess(elapsed, 5)  # returned promptly, not after 300s

    def test_install_does_not_re_arm_a_signal_the_launcher_ignored(self) -> None:
        # `nohup ... &` hands a background run an ignored SIGINT on purpose.
        # Re-arming it here would make the run newly killable by a signal its
        # launcher meant it to survive, so an existing SIG_IGN is left alone.
        import signal as signal_mod

        previous = signal_mod.getsignal(signal_mod.SIGINT)
        try:
            signal_mod.signal(signal_mod.SIGINT, signal_mod.SIG_IGN)
            observe.StopSignal().install()
            self.assertIs(signal_mod.getsignal(signal_mod.SIGINT), signal_mod.SIG_IGN)
        finally:
            signal_mod.signal(signal_mod.SIGINT, previous)

        # SIGTERM, which is not ignored, is still armed.
        previous_term = signal_mod.getsignal(signal_mod.SIGTERM)
        try:
            stop = observe.StopSignal()
            stop.install()
            # Bound methods are equal, not identical, across attribute lookups.
            self.assertEqual(signal_mod.getsignal(signal_mod.SIGTERM), stop.request)
        finally:
            signal_mod.signal(signal_mod.SIGTERM, previous_term)

    def test_stop_signal_records_only_the_first_request(self) -> None:
        stop = observe.StopSignal()
        self.assertFalse(stop.requested)
        stop.request(15)
        stop.request(2)  # a later signal must not overwrite the original cause
        self.assertTrue(stop.requested)
        self.assertEqual(stop.signum, 15)

    def test_max_runtime_guard_does_not_affect_narrow_loop_or_once(self) -> None:
        # Scoped strictly to selector-view loops: the narrow paper-feeding loop
        # keeps its existing operator-authorized behaviour, and a bounded-by-
        # construction --once selector-view run is exempt.
        from unittest import mock

        cases = (
            ("narrow loop, no max runtime",
             {"AUTOPILOT_OBSERVE_ENABLED": "true", "AUTOPILOT_OBSERVE_LOOP": "true"}, []),
            ("selector-view --once, no max runtime",
             {"AUTOPILOT_OBSERVE_ENABLED": "true",
              "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true"}, ["--once"]),
        )
        for label, env, argv in cases:
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as tmp:
                    env = {**env, "AUTOPILOT_OBSERVE_OUTPUT_DIR": tmp}
                    with mock.patch.dict(os.environ, env, clear=True):
                        with mock.patch.object(observe, "run_once", return_value=[]) as ran:
                            with mock.patch.object(observe, "JsonGetClient"):
                                with mock.patch.object(observe.time, "sleep",
                                                       side_effect=_StopLoop):
                                    try:
                                        rc = observe.main(argv)
                                    except _StopLoop:
                                        rc = 0  # narrow loop ran past the guard
                self.assertEqual(rc, 0, label)
                self.assertGreaterEqual(ran.call_count, 1, label)

    def test_stop_handling_is_scoped_to_selector_view_loops_only(self) -> None:
        """The narrow paper-feeding loop must keep its pre-slice stop behaviour.

        This slice's work order (AG-20260713-009) requires the narrow run to be
        byte-identical when the selector-view flag is false, and installing a
        SIGTERM handler changes how that run dies — an operator-visible change to
        a loop this slice was never authorized to touch. Pinned here because
        nothing else fails if the install is quietly re-broadened to every loop.
        """
        import signal as signal_mod
        from unittest import mock

        cases = (
            ("narrow loop installs no handler", {}, False),
            (
                "selector-view loop installs a handler",
                {
                    "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true",
                    "AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS": "600",
                },
                True,
            ),
        )
        for label, extra_env, expect_install in cases:
            with self.subTest(case=label):
                installed: list[int] = []

                # Record what the loop arms without actually arming it, so the
                # test process keeps its own dispositions.
                def record_install(signum, handler, _installed=installed):
                    _installed.append(signum)
                    return signal_mod.SIG_DFL

                with tempfile.TemporaryDirectory() as tmp:
                    env = {
                        "AUTOPILOT_OBSERVE_ENABLED": "true",
                        "AUTOPILOT_OBSERVE_LOOP": "true",
                        "AUTOPILOT_OBSERVE_OUTPUT_DIR": tmp,
                        **extra_env,
                    }
                    with mock.patch.dict(os.environ, env, clear=True):
                        with mock.patch.object(observe.signal, "signal", record_install):
                            with mock.patch.object(
                                observe.signal, "getsignal", return_value=signal_mod.SIG_DFL
                            ):
                                with mock.patch.object(observe, "run_once", return_value=[]):
                                    with mock.patch.object(observe, "JsonGetClient"):
                                        # Both sleep paths raise, so the loop
                                        # exits after exactly one tick either way.
                                        with mock.patch.object(
                                            observe.time, "sleep", side_effect=_StopLoop
                                        ):
                                            with self.assertRaises(_StopLoop):
                                                observe.main([])

                if expect_install:
                    self.assertEqual(
                        sorted(installed),
                        sorted([signal_mod.SIGTERM, signal_mod.SIGINT]),
                        label,
                    )
                else:
                    self.assertEqual(installed, [], label)

    def test_narrow_loop_sleeps_with_plain_sleep_not_the_stop_aware_sleep(self) -> None:
        # The stop-aware sleep wakes every 0.5s to poll the flag. The narrow loop
        # has no flag to poll, so it keeps the single plain sleep it has always
        # made — same one call, same full interval.
        from unittest import mock

        slept: list[float] = []

        def record_sleep(seconds):
            slept.append(seconds)
            raise _StopLoop

        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AUTOPILOT_OBSERVE_ENABLED": "true",
                "AUTOPILOT_OBSERVE_LOOP": "true",
                "AUTOPILOT_OBSERVE_INTERVAL_SECONDS": "300",
                "AUTOPILOT_OBSERVE_OUTPUT_DIR": tmp,
            }
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.object(observe, "run_once", return_value=[]):
                    with mock.patch.object(observe, "JsonGetClient"):
                        with mock.patch.object(observe.time, "sleep", record_sleep):
                            with self.assertRaises(_StopLoop):
                                observe.main([])

        self.assertEqual(slept, [300.0])

    def test_disabled_selector_view_loop_probe_is_unaffected_by_max_runtime_guard(self) -> None:
        # The guard sits AFTER the disabled-default early return, so a disabled
        # probe still prints the disabled payload and exits 0 even with a loop +
        # selector-view + no max runtime configured. Disabled-default behaviour
        # stays byte-identical.
        import contextlib, io
        from unittest import mock

        env = {
            "AUTOPILOT_OBSERVE_ENABLED": "false",
            "AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW": "true",
            "AUTOPILOT_OBSERVE_LOOP": "true",
        }
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = observe.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(err.getvalue(), "")  # guard did not fire
        self.assertEqual(
            json.loads(out.getvalue()),
            {"enabled": False,
             "recommended_action": "SET_AUTOPILOT_OBSERVE_ENABLED_TRUE_TO_RUN"},
        )

    def test_selector_view_disabled_by_default_leaves_behavior_unchanged(self) -> None:
        routes = base_routes()
        payload = routes["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"]
        payload["watchlist"] = [deepcopy(candidate())]
        payload["excluded"] = [deepcopy(candidate())]

        default_records = observe.run_once(
            config(), client=RecordingGetClient(routes), observed_at=OBSERVED_AT, seen_keys=set()
        )

        # Default (capture_selector_view=False): only the tradable_now entry row
        # is evaluated; watchlist/excluded are ignored exactly as before.
        self.assertEqual(len(default_records), 1)
        self.assertEqual(default_records[0]["decision"], "OBSERVED_ENTRY_CANDIDATE")
        self.assertNotIn("capture_profile", default_records[0])

    def test_selector_view_malformed_inputs_refuse_whole_tick(self) -> None:
        from jsonschema import Draft202012Validator

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        validator = Draft202012Validator(
            json.loads(
                (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
                .read_text(encoding="utf-8")
            )
        )
        evidence = observe.blocked_before_poll_evidence()

        def variant(pair: str, **overrides: Any) -> dict[str, Any]:
            base = deepcopy(candidate())
            base["pair_id"] = pair
            base.update(overrides)
            return base

        huge = int("9" * 400)
        absent_codes = variant("PF_ABSENT__PF_CODES", rationale_codes=None)
        absent_codes.pop("rationale_codes")  # key genuinely absent
        absent_tf = {k: v for k, v in candidate().items() if k != "timeframe"}
        absent_tf["pair_id"] = "PF_NO__PF_TF"
        rows = [
            candidate(),                                            # the one good row
            variant("PF_HUGE__PF_NUM", spread_z=huge),             # big int: preserved, not rounded
            variant("PF_NAN__PF_NUM", net_edge_bps=float("nan")),   # non-finite -> omit
            variant("PF_INF__PF_NUM", opportunity_score=float("inf")),  # -> omit
            variant("PF_STR__PF_BOOL", setup_gate_pass="false"),    # bool-as-string -> omit
            variant("PF_STR__PF_CODES", rationale_codes="COST_PASS"),  # str not list -> omit
            variant("PF_BAD__PF_BUCKET", decision_bucket="GARBAGE"),  # bad enum -> omit
            absent_codes,                                           # absent codes -> omit
            variant("PF_BAD__PF_TF", timeframe="5m"),               # wrong timeframe -> omit
            absent_tf,                                              # absent timeframe -> omit
            variant("PF_MISS__PF_NUM", opportunity_score=None),     # null required number -> omit
        ]
        trade_now = {
            "generated_at": "2026-06-13T05:29:57Z",
            "tradable_now": rows,
            "watchlist": [],
            "excluded": [],
        }

        records = observe.selector_view_records(
            config=config(),
            trade_now=trade_now,
            observed_at=OBSERVED_AT,
            dispatch_mode=None,
            kill_switch=None,
            evidence=evidence,
            source_reasons=[],
        )

        # Codex finding 1: a malformed candidate must NOT be silently dropped
        # while its neighbours are emitted. Because this response contains rows
        # that cannot be faithfully transcribed, the whole tick is refused: no
        # selector rows at all, just one machine-readable refusal record.
        self.assertEqual([r.get("capture_profile") for r in records], [None])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertIn("SELECTOR_VIEW_ROW_MALFORMED:tradable_now", records[0]["reason_codes"])
        # The good row and the big-int row are NOT emitted — a partial universe
        # can never reach B2-c as though it were complete.
        self.assertNotIn("PF_DOGEUSD__PF_PEPEUSD", json.dumps(records))
        self.assertNotIn("PF_HUGE__PF_NUM", json.dumps(records))
        # Reason codes stay bounded and never leak row-supplied pair_ids.
        for code in records[0]["reason_codes"]:
            self.assertRegex(
                code,
                r"^SELECTOR_VIEW_ROW_(NOT_OBJECT|IDENTITY_INVALID|MALFORMED):"
                r"(tradable_now|watchlist|excluded)$",
            )
        # Everything written is schema-valid (no NaN/inf, no fabricated fields).
        serialized = json.dumps(records, allow_nan=False)  # raises if any NaN/inf slipped through
        self.assertNotIn("NaN", serialized)
        self.assertNotIn("Infinity", serialized)
        for record in records:
            self.assertEqual(sorted(validator.iter_errors(record), key=str), [])

    def test_selector_view_strict_transcription_preserves_valid_rows(self) -> None:
        # Complement to the refusal test: on a fully-valid tick every candidate
        # is emitted, and a huge int is preserved exactly rather than rounded.
        # This keeps the strict-transcription coverage the refusal path removed.
        huge = int("9" * 400)
        good = deepcopy(candidate())
        big = deepcopy(candidate())
        big["pair_id"] = "PF_HUGE__PF_NUM"
        big["spread_z"] = huge
        records = observe.selector_view_records(
            config=config(),
            trade_now={
                "generated_at": "2026-06-13T05:29:57Z",
                "tradable_now": [good, big], "watchlist": [], "excluded": [],
            },
            observed_at=OBSERVED_AT, dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        selector_rows = [r for r in records if r.get("capture_profile") == "selector_view"]
        self.assertEqual({r["pair_id"] for r in selector_rows},
                         {"PF_DOGEUSD__PF_PEPEUSD", "PF_HUGE__PF_NUM"})
        huge_row = next(r for r in selector_rows if r["pair_id"] == "PF_HUGE__PF_NUM")
        self.assertEqual(huge_row["spread_z"], huge)  # exact, no float rounding

    def test_selector_view_refuses_tick_on_non_object_or_identity_invalid_row(self) -> None:
        # Codex finding 1: non-object and identity-invalid rows previously
        # vanished without even incrementing the omission counter. Each must now
        # refuse the whole tick with its own bounded reason code.
        for bad_row, expected in (
            ("not-an-object", "SELECTOR_VIEW_ROW_NOT_OBJECT:watchlist"),
            (None, "SELECTOR_VIEW_ROW_NOT_OBJECT:watchlist"),
            ([1, 2], "SELECTOR_VIEW_ROW_NOT_OBJECT:watchlist"),
            ({"selected_variant": "ROBUST_Z", "timeframe": "1m"},
             "SELECTOR_VIEW_ROW_IDENTITY_INVALID:watchlist"),   # pair_id absent
            ({"pair_id": "   ", "selected_variant": "ROBUST_Z", "timeframe": "1m"},
             "SELECTOR_VIEW_ROW_IDENTITY_INVALID:watchlist"),   # blank pair_id
            ({"pair_id": "PF_A__PF_B", "timeframe": "1m"},
             "SELECTOR_VIEW_ROW_IDENTITY_INVALID:watchlist"),   # variant absent
        ):
            records = observe.selector_view_records(
                config=config(),
                trade_now={
                    "generated_at": "2026-06-13T05:29:57Z",
                    "tradable_now": [candidate()],   # a perfectly good row
                    "watchlist": [bad_row],
                    "excluded": [],
                },
                observed_at=OBSERVED_AT, dispatch_mode=None, kill_switch=None,
                evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
            )
            self.assertEqual(len(records), 1, f"{bad_row!r} should refuse the tick")
            self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
            self.assertIn(expected, records[0]["reason_codes"])
            # the good tradable_now row must NOT be emitted alongside the refusal
            self.assertNotIn("selector_view", [r.get("capture_profile") for r in records])
            self.assertNotIn("PF_DOGEUSD__PF_PEPEUSD", json.dumps(records))

    def test_selector_view_refusal_reason_codes_are_bounded_and_deduped(self) -> None:
        # Many bad rows in one bucket collapse to a single code; codes never
        # interpolate pair_id (which would be unbounded and attacker-supplied).
        bad = deepcopy(candidate())
        bad["pair_id"] = "PF_EVIL__PF_INJECT"
        bad["setup_gate_pass"] = "false"          # bool-as-string -> malformed
        other = deepcopy(bad)
        other["pair_id"] = "PF_OTHER__PF_BAD"
        records = observe.selector_view_records(
            config=config(),
            trade_now={
                "generated_at": "2026-06-13T05:29:57Z",
                "tradable_now": [bad, other, "not-an-object"],
                "watchlist": [], "excluded": [],
            },
            observed_at=OBSERVED_AT, dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        codes = records[0]["reason_codes"]
        self.assertEqual(sorted(codes), [
            "SELECTOR_VIEW_ROW_MALFORMED:tradable_now",
            "SELECTOR_VIEW_ROW_NOT_OBJECT:tradable_now",
        ])
        self.assertNotIn("PF_EVIL__PF_INJECT", json.dumps(records))
        self.assertNotIn("PF_OTHER__PF_BAD", json.dumps(records))

    def test_selector_view_empty_buckets_are_complete_not_incomplete(self) -> None:
        # An empty bucket is a complete view of an empty bucket; only candidates
        # the endpoint actually returned can make a tick incomplete.
        records = observe.selector_view_records(
            config=config(),
            trade_now={
                "generated_at": "2026-06-13T05:29:57Z",
                "tradable_now": [], "watchlist": [], "excluded": [],
            },
            observed_at=OBSERVED_AT, dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        # No candidate rows, and crucially no refusal record: the tick is
        # complete. It is represented by the manifest alone.
        self.assertEqual([r["capture_profile"] for r in records], ["selector_view_tick"])
        self.assertEqual(records[0]["recorded_rows"], 0)
        self.assertEqual(
            records[0]["rows_per_bucket"], {"TRADE_NOW": 0, "WATCHLIST": 0, "EXCLUDED": 0}
        )

    def test_artifact_distinguishes_empty_captured_tick_from_missing_tick(self) -> None:
        # Codex round-6 finding 1: an all-empty selector universe is a valid,
        # successfully captured observation, but it writes no candidate rows —
        # so without a positive per-tick marker it is byte-for-byte
        # indistinguishable on disk from a tick that never ran (host down, loop
        # stopped). B2-c must be able to tell "the selector saw nothing" from
        # "we did not look". This asserts that at the artifact level, through
        # the real writer, because that file is B2-c's only input.
        def read_ticks(path: pathlib.Path) -> dict[str, dict[str, Any]]:
            """A B2-c-style reader: a tick counts as captured only on a manifest."""
            ticks: dict[str, dict[str, Any]] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)  # every line must be complete JSON
                run = record["run_id"]
                tick = ticks.setdefault(run, {"captured": False, "stated": 0, "rows": 0})
                if record.get("capture_profile") == "selector_view_tick":
                    tick["captured"] = True
                    tick["stated"] = record["recorded_rows"]
                elif record.get("capture_profile") == "selector_view":
                    tick["rows"] += 1
            return ticks

        routes = base_routes()
        payload = routes["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"]
        empty_at = dt.datetime(2026, 6, 13, 5, 30, tzinfo=dt.timezone.utc)
        populated_at = dt.datetime(2026, 6, 13, 5, 35, tzinfo=dt.timezone.utc)
        missing_at = dt.datetime(2026, 6, 13, 5, 40, tzinfo=dt.timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            # Each tick's cue response must be fresh for its own observed_at, or
            # the staleness gate would refuse it and this would not be testing
            # capture at all.
            payload["generated_at"] = "2026-06-13T05:29:57Z"
            payload["tradable_now"] = []  # the selector legitimately returns nothing
            empty_records = observe.run_once(
                config(capture_selector_view=True),
                client=RecordingGetClient(routes),
                observed_at=empty_at,
            )
            path = observe.write_records(empty_records, out, empty_at)

            payload["generated_at"] = "2026-06-13T05:34:57Z"
            payload["tradable_now"] = [candidate()]  # a later tick sees one pair
            populated_records = observe.run_once(
                config(capture_selector_view=True),
                client=RecordingGetClient(routes),
                observed_at=populated_at,
            )
            observe.write_records(populated_records, out, populated_at)
            # The 05:40 tick never ran: nothing is written for it at all.

            ticks = read_ticks(path)

        empty_key = observe.iso(empty_at)
        populated_key = observe.iso(populated_at)
        missing_key = observe.iso(missing_at)

        # The empty tick is present and positively marked as captured, with a
        # stated row count of zero that its zero rows satisfy.
        self.assertIn(empty_key, ticks)
        self.assertTrue(ticks[empty_key]["captured"])
        self.assertEqual(ticks[empty_key]["stated"], 0)
        self.assertEqual(ticks[empty_key]["rows"], 0)

        # The missing tick is absent entirely — the distinction the finding is
        # about, and the assertion that fails on the pre-fix behaviour where an
        # empty tick also wrote nothing.
        self.assertNotIn(missing_key, ticks)
        self.assertNotEqual(ticks.get(empty_key), ticks.get(missing_key))

        # A populated tick still reconciles: stated count == rows that follow.
        self.assertTrue(ticks[populated_key]["captured"])
        self.assertEqual(ticks[populated_key]["stated"], 1)
        self.assertEqual(ticks[populated_key]["rows"], 1)

    def test_refused_tick_emits_no_manifest_so_it_never_reads_as_captured(self) -> None:
        # "Captured" and "refused" must stay mutually exclusive: a refused tick
        # must not carry a manifest, or B2-c would read an untrustworthy view as
        # a good one.
        records = observe.selector_view_records(
            config=config(),
            trade_now={
                "generated_at": "2026-06-13T05:29:57Z",
                "tradable_now": [candidate()], "watchlist": "not-a-list", "excluded": [],
            },
            observed_at=OBSERVED_AT, dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertNotIn(
            "selector_view_tick", [r.get("capture_profile") for r in records]
        )

    def test_selector_view_refuses_whole_tick_on_bad_or_missing_bucket(self) -> None:
        # A non-list bucket refuses the whole tick (no partial universe).
        for trade_now, reason in (
            ({"generated_at": "2026-06-13T05:29:57Z", "tradable_now": [candidate()],
              "watchlist": "not-a-list", "excluded": []}, "CUE_BUCKET_NOT_LIST:watchlist"),
            ({"generated_at": "2026-06-13T05:29:57Z", "tradable_now": [candidate()],
              "excluded": []}, "CUE_BUCKET_MISSING:watchlist"),
        ):
            records = observe.selector_view_records(
                config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
                dispatch_mode=None, kill_switch=None,
                evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
            self.assertIn(reason, records[0]["reason_codes"])
            self.assertNotIn("selector_view", [r.get("capture_profile") for r in records])

    def test_selector_view_degraded_source_record_is_nan_free(self) -> None:
        # A degraded response carrying a non-finite learning_overlay_age_seconds
        # must still serialize as valid JSON (nullable_number rejects NaN/inf).
        trade_now = {
            "generated_at": "2026-06-13T05:29:57Z",
            "learning_overlay_age_seconds": float("nan"),
            "tradable_now": [candidate()], "watchlist": [], "excluded": [],
        }
        records = observe.selector_view_records(
            config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(),
            source_reasons=["DATA_HEALTH_DEGRADED"],
        )
        json.dumps(records, allow_nan=False)  # raises if any record carries NaN/inf
        self.assertEqual(records[0]["decision"], "BLOCKED_SOURCE_UNAVAILABLE")

    def test_huge_number_does_not_crash_entry_or_system_paths(self) -> None:
        self.assertIsNone(observe.nullable_number(float("nan")))
        self.assertIsNone(observe.nullable_number(float("inf")))
        huge = int("9" * 400)
        self.assertEqual(observe.nullable_number(huge), huge)  # preserved, no overflow
        routes = base_routes()
        routes["http://strategy/v1/strategy/pairs/trade-now?timeframe=1m"][
            "learning_overlay_age_seconds"
        ] = huge
        records = observe.run_once(
            config(), client=RecordingGetClient(routes), observed_at=OBSERVED_AT, seen_keys=set()
        )
        json.dumps([observe.json_safe(r) for r in records], allow_nan=False)

    def test_date_only_generated_at_is_not_fresh(self) -> None:
        trade_now = {"generated_at": "2026-06-13", "tradable_now": [candidate()],
                     "watchlist": [], "excluded": []}
        records = observe.selector_view_records(
            config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertIn("TRADE_NOW_GENERATED_AT_INVALID", records[0]["reason_codes"])

    def test_writer_finite_records_byte_identical(self) -> None:
        # json_safe + allow_nan=False must not change the bytes written for a
        # finite record (guards disabled-default byte-identity).
        record = {"b": 2.5, "a": "x", "n": 7, "nested": {"z": 1.0, "y": [3, "q"]}}
        direct = json.dumps(record, sort_keys=True, separators=(",", ":"))
        guarded = json.dumps(observe.json_safe(record), sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        self.assertEqual(direct, guarded)

    def test_writer_sanitizes_nested_non_finite(self) -> None:
        record = {"a": float("nan"), "b": [1.0, float("inf"), {"c": float("-inf")}], "d": "ok"}
        safe = observe.json_safe(record)
        json.dumps(safe, allow_nan=False)
        self.assertIsNone(safe["a"])
        self.assertIsNone(safe["b"][1])
        self.assertIsNone(safe["b"][2]["c"])
        self.assertEqual(safe["d"], "ok")

    def test_round4_decision_bucket_list_omits_not_crashes(self) -> None:
        row = deepcopy(candidate())
        row["decision_bucket"] = ["not", "hashable"]   # would TypeError on `in frozenset`
        trade_now = {"generated_at": "2026-06-13T05:29:57Z",
                     "tradable_now": [row], "watchlist": [], "excluded": []}
        records = observe.selector_view_records(
            config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual([r for r in records if r.get("capture_profile") == "selector_view"], [])

    def test_round4_decision_bucket_mismatch_is_recorded_faithfully(self) -> None:
        # The v2 schema does not require decision_bucket == cue_bucket; a valid
        # enum value that differs is faithful evidence, recorded not dropped.
        row = deepcopy(candidate())
        row["decision_bucket"] = "TRADE_NOW"  # while in the watchlist bucket
        trade_now = {"generated_at": "2026-06-13T05:29:57Z",
                     "tradable_now": [], "watchlist": [row], "excluded": []}
        records = observe.selector_view_records(
            config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        sel = [r for r in records if r.get("capture_profile") == "selector_view"]
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["cue_bucket"], "WATCHLIST")
        self.assertEqual(sel[0]["decision_bucket"], "TRADE_NOW")
        # But a garbage (non-enum) decision_bucket still omits the row.
        bad = deepcopy(candidate()); bad["decision_bucket"] = "GARBAGE"
        tn2 = {"generated_at": "2026-06-13T05:29:57Z",
               "tradable_now": [bad], "watchlist": [], "excluded": []}
        r2 = observe.selector_view_records(
            config=config(), trade_now=tn2, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual([r for r in r2 if r.get("capture_profile") == "selector_view"], [])

    def test_refused_tick_is_surfaced_on_stderr_with_per_bucket_counts(self) -> None:
        import contextlib, io
        bad = deepcopy(candidate()); bad["net_edge_bps"] = float("nan")  # malformed
        trade_now = {"generated_at": "2026-06-13T05:29:57Z",
                     "tradable_now": [bad], "watchlist": ["not-an-object"],
                     "excluded": []}
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            records = observe.selector_view_records(
                config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
                dispatch_mode=None, kill_switch=None,
                evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
            )
        diag = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(diag["selector_view_tick_refused"], "INCOMPLETE_UNIVERSE")
        self.assertEqual(diag["omitted_per_bucket"], {"tradable_now": 1, "watchlist": 1})
        self.assertEqual(diag["would_have_recorded"], 0)
        self.assertEqual(sorted(diag["reason_codes"]), [
            "SELECTOR_VIEW_ROW_MALFORMED:tradable_now",
            "SELECTOR_VIEW_ROW_NOT_OBJECT:watchlist",
        ])
        # and the artifact itself carries the refusal, not a partial universe
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")

    def test_round4_timeless_timestamps_are_invalid(self) -> None:
        for bad in ("2026-06-13", "2026-06-13+00:00", "2026-06-13:05:29:57"):
            trade_now = {"generated_at": bad, "tradable_now": [candidate()],
                         "watchlist": [], "excluded": []}
            records = observe.selector_view_records(
                config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
                dispatch_mode=None, kill_switch=None,
                evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
            )
            self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE", bad)

    def test_round4_system_record_is_schema_valid_on_garbage_upstream(self) -> None:
        from jsonschema import Draft202012Validator
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        validator = Draft202012Validator(json.loads(
            (repo_root / "specs/contracts/autopilot_observe_record.schema.json")
            .read_text(encoding="utf-8")))
        trade_now = {"generated_at": "2026-06-13T05:29:57Z",
                     "learning_overlay_age_seconds": -1,
                     "tradable_now": [candidate()], "watchlist": [], "excluded": []}
        records = observe.selector_view_records(
            config=config(), trade_now=trade_now, observed_at=OBSERVED_AT,
            dispatch_mode={"mode": "GARBAGE"}, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(),
            source_reasons=["DATA_HEALTH_DEGRADED"],
        )
        self.assertEqual(records[0]["decision"], "BLOCKED_SOURCE_UNAVAILABLE")
        self.assertIsNone(records[0]["dispatch_mode"])              # garbage -> null
        self.assertIsNone(records[0]["learning_overlay_age_seconds"])  # negative -> null
        self.assertEqual(sorted(validator.iter_errors(records[0]), key=str), [])

    def test_round4_v1_invalid_source_generated_at_is_null(self) -> None:
        # An entry/system record must not carry a non-timestamp generated_at.
        self.assertIsNone(observe.source_generated_at({"generated_at": "hello"}))
        self.assertIsNone(observe.source_generated_at({"generated_at": "2026-06-13"}))
        self.assertEqual(
            observe.source_generated_at({"generated_at": "2026-06-13T05:29:57Z"}),
            "2026-06-13T05:29:57Z",
        )

    def test_round4_quality_window_range_and_finiteness(self) -> None:
        import tempfile, os
        def load(row: dict[str, Any]) -> None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump([{"pair_id": "P", "timeframe": "1m", "selected_variant": "V", **row}], fh)
                name = fh.name
            try:
                observe.load_quality_windows(name)
            finally:
                os.unlink(name)
        base = {"rows": 10, "profitable_rate": 0.9, "avg_net_bps": 5.0}
        load(base)  # valid
        for bad in ({"avg_net_bps": float("nan")}, {"rows": -1}, {"rows": 3.9},
                    {"rows": True}, {"profitable_rate": 1.5}, {"profitable_rate": -0.1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                load({**base, **bad})

    def test_round4_min_ready_env_validated(self) -> None:
        with self.assertRaises(ValueError):
            observe.load_config({"AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS": "-1"})
        with self.assertRaises(ValueError):
            observe.load_config({"AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS": "inf"})

    def test_selector_view_refuses_future_timestamp(self) -> None:
        # A future generated_at (negative age beyond tolerance) is not "fresh".
        future = {"generated_at": "2026-06-13T06:00:00Z",  # 30 min ahead of OBSERVED_AT
                  "tradable_now": [candidate()], "watchlist": [], "excluded": []}
        records = observe.selector_view_records(
            config=config(), trade_now=future, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_STALE_INPUT")
        self.assertIn("TRADE_NOW_SIGNAL_FUTURE", records[0]["reason_codes"])

    def test_selector_view_invalid_generated_at_marks_malformed_response(self) -> None:
        trade_now = {"tradable_now": [candidate()], "watchlist": [], "excluded": []}
        records = observe.selector_view_records(
            config=config(),
            trade_now=trade_now,
            observed_at=OBSERVED_AT,
            dispatch_mode=None,
            kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(),
            source_reasons=[],
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "BLOCKED_MALFORMED_RESPONSE")
        self.assertIn("TRADE_NOW_GENERATED_AT_INVALID", records[0]["reason_codes"])

    def test_selector_view_refuses_stale_or_degraded_source(self) -> None:
        cfg = config()
        # Stale: generated_at older than max_signal_age_seconds (120s default).
        stale = {"generated_at": "2026-06-13T05:20:00Z",
                 "tradable_now": [candidate()], "watchlist": [], "excluded": []}
        stale_records = observe.selector_view_records(
            config=cfg, trade_now=stale, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(), source_reasons=[],
        )
        self.assertEqual(len(stale_records), 1)
        self.assertEqual(stale_records[0]["decision"], "BLOCKED_STALE_INPUT")
        self.assertNotIn("SELECTOR_VIEW_OBSERVED",
                         [r["decision"] for r in stale_records])

        # Degraded source: non-empty source_reasons blocks the whole tick.
        fresh = {"generated_at": "2026-06-13T05:29:57Z",
                 "tradable_now": [candidate()], "watchlist": [], "excluded": []}
        degraded = observe.selector_view_records(
            config=cfg, trade_now=fresh, observed_at=OBSERVED_AT,
            dispatch_mode=None, kill_switch=None,
            evidence=observe.blocked_before_poll_evidence(),
            source_reasons=["DATA_HEALTH_DEGRADED"],
        )
        self.assertEqual(len(degraded), 1)
        self.assertEqual(degraded[0]["decision"], "BLOCKED_SOURCE_UNAVAILABLE")
        self.assertIn("DATA_HEALTH_DEGRADED", degraded[0]["reason_codes"])

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
