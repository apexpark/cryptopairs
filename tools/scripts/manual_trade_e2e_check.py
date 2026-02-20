#!/usr/bin/env python3
"""Run a deterministic end-to-end manual trade flow check."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TIMEFRAME_TO_LOOKBACK_MINUTES = {
    "1m": 360,
    "15m": 2880,
    "1h": 10080,
}


class CheckFailure(Exception):
    """Raised when a required validation fails."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_start_utc() -> dt.datetime:
    now = utc_now()
    return dt.datetime(now.year, now.month, now.day, tzinfo=dt.timezone.utc)


def http_get_json(url: str, timeout: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
    if query:
        encoded = urllib.parse.urlencode(query)
        url = f"{url}?{encoded}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def long_entry_legs(left_instrument: str, right_instrument: str) -> list[dict[str, str]]:
    return [
        {"instrument": left_instrument, "side": "BUY"},
        {"instrument": right_instrument, "side": "SELL"},
    ]


def long_close_legs(left_instrument: str, right_instrument: str) -> list[dict[str, str]]:
    return [
        {"instrument": left_instrument, "side": "SELL"},
        {"instrument": right_instrument, "side": "BUY"},
    ]


def warm_integrity(
    data_service_url: str,
    instrument: str,
    timeframe: str,
    timeout: int,
) -> dict[str, Any]:
    end_ts = utc_now()
    lookback_minutes = TIMEFRAME_TO_LOOKBACK_MINUTES[timeframe]
    start_ts = end_ts - dt.timedelta(minutes=lookback_minutes)
    payload = {
        "instrument": instrument,
        "timeframe": timeframe,
        "start_ts": iso(start_ts),
        "end_ts": iso(end_ts),
    }
    return http_post_json(f"{data_service_url}/v1/data/query", payload, timeout)


def seed_account_state(
    account_service_url: str,
    exchange: str,
    account_id: str,
    timeout: int,
) -> dict[str, Any]:
    now = utc_now()
    day_start = today_start_utc()

    day_start_snapshot = {
        "exchange": exchange,
        "account_id": account_id,
        "ts": iso(day_start + dt.timedelta(minutes=1)),
        "equity": 10000.0,
        "balance": 9950.0,
        "margin_used": 500.0,
        "unrealized_pnl": 50.0,
        "realized_pnl": 0.0,
    }
    now_snapshot = {
        "exchange": exchange,
        "account_id": account_id,
        "ts": iso(now),
        "equity": 10020.0,
        "balance": 9970.0,
        "margin_used": 480.0,
        "unrealized_pnl": 50.0,
        "realized_pnl": 0.0,
    }

    write_day_start = http_post_json(
        f"{account_service_url}/v1/account/snapshot", day_start_snapshot, timeout
    )
    write_now = http_post_json(
        f"{account_service_url}/v1/account/snapshot", now_snapshot, timeout
    )

    reconcile_event = {
        "exchange": exchange,
        "account_id": account_id,
        "ts": iso(now),
        "status": "OK",
        "drift_notional": 0.0,
        "notes": "manual_trade_e2e seed",
    }
    write_reconcile = http_post_json(
        f"{account_service_url}/v1/account/reconcile", reconcile_event, timeout
    )

    snapshot_read = http_get_json(
        f"{account_service_url}/v1/account/snapshot",
        timeout,
        {"exchange": exchange, "account_id": account_id},
    )
    day_start_read = http_get_json(
        f"{account_service_url}/v1/account/snapshot/day-start",
        timeout,
        {
            "exchange": exchange,
            "account_id": account_id,
            "day_start_utc": iso(day_start),
        },
    )
    reconcile_read = http_get_json(
        f"{account_service_url}/v1/account/reconcile",
        timeout,
        {"exchange": exchange, "account_id": account_id},
    )

    assert_true(write_day_start.get("written") is True, "failed to write day-start snapshot")
    assert_true(write_now.get("written") is True, "failed to write latest snapshot")
    assert_true(write_reconcile.get("written") is True, "failed to write reconcile seed")
    assert_true(snapshot_read.get("snapshot") is not None, "snapshot read returned null")
    assert_true(day_start_read.get("snapshot") is not None, "day-start snapshot read returned null")
    assert_true(
        reconcile_read.get("reconcile", {}).get("status") == "OK",
        "reconcile gate seed is not OK",
    )

    return {
        "snapshot": snapshot_read,
        "day_start_snapshot": day_start_read,
        "reconcile": reconcile_read,
    }


def enforce_kill_switch_off(execution_service_url: str, timeout: int) -> dict[str, Any]:
    update = http_post_json(
        f"{execution_service_url}/v1/execution/kill-switch",
        {
            "active": False,
            "reason": "manual_trade_e2e preflight",
            "actor": "manual_trade_e2e_check",
        },
        timeout,
    )
    state = http_get_json(f"{execution_service_url}/v1/execution/kill-switch", timeout)
    assert_true(state.get("active") is False, "kill switch is still active")
    return {"update": update, "state": state}


def run_intent_lifecycle(
    execution_service_url: str,
    exchange: str,
    account_id: str,
    operator_id: str,
    timeframe: str,
    pair_id: str,
    spread_direction: str,
    spread_z: float | None,
    qty: float,
    action: str,
    legs: list[dict[str, str]],
    timeout: int,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for index, leg in enumerate(legs):
        idempotency_key = (
            f"manuale2e-{action.lower()}-{pair_id}-{leg['instrument']}-{int(utc_now().timestamp())}-{index}"
        )
        submit_payload = {
            "idempotency_key": idempotency_key,
            "exchange": exchange,
            "account_id": account_id,
            "pair_id": pair_id,
            "instrument": leg["instrument"],
            "timeframe": timeframe,
            "action": action,
            "spread_direction": spread_direction,
            "spread_z": spread_z,
            "side": leg["side"],
            "qty": qty,
            "operator_confirmed": action != "EMERGENCY_STOP_CLOSE",
            "operator_id": operator_id if action != "EMERGENCY_STOP_CLOSE" else None,
            "min_coverage_pct": 99.5,
        }

        intent = http_post_json(
            f"{execution_service_url}/v1/execution/order-intent", submit_payload, timeout
        )
        dispatch = None
        history = None
        if intent.get("decision") == "ACCEPTED":
            dispatch = http_post_json(
                f"{execution_service_url}/v1/execution/order-intent/dispatch",
                {"idempotency_key": idempotency_key, "actor": operator_id},
                timeout,
            )
            history = http_get_json(
                f"{execution_service_url}/v1/execution/order-intent/history",
                timeout,
                {"idempotency_key": idempotency_key},
            )
        outcomes.append(
            {
                "idempotency_key": idempotency_key,
                "submit_payload": submit_payload,
                "intent": intent,
                "dispatch": dispatch,
                "history": history,
            }
        )
    return outcomes


def validate_outcomes(
    outcomes: list[dict[str, Any]],
    require_dispatch_ack: bool,
) -> dict[str, Any]:
    accepted = [item for item in outcomes if item["intent"].get("decision") == "ACCEPTED"]
    blocked = [item for item in outcomes if item["intent"].get("decision") != "ACCEPTED"]

    assert_true(len(accepted) > 0, "all intents were blocked")

    lifecycle_checks: list[dict[str, Any]] = []
    for item in accepted:
        history = item.get("history") or {}
        state_events = history.get("state_events", [])
        states = [event.get("state") for event in state_events]
        dispatch_result = (item.get("dispatch") or {}).get("result")

        has_submit_chain = (
            "NEW" in states and "APPROVED" in states and "PENDING_SUBMIT" in states
        )
        has_ack = "ACKNOWLEDGED" in states

        if require_dispatch_ack:
            assert_true(
                dispatch_result == "ACKNOWLEDGED" and has_ack,
                f"dispatch not acknowledged for {item['idempotency_key']}",
            )

        lifecycle_checks.append(
            {
                "idempotency_key": item["idempotency_key"],
                "dispatch_result": dispatch_result,
                "states": states,
                "has_submit_chain": has_submit_chain,
                "has_ack": has_ack,
            }
        )
        assert_true(
            has_submit_chain,
            f"state transition chain missing for {item['idempotency_key']}",
        )

    return {
        "accepted_count": len(accepted),
        "blocked_count": len(blocked),
        "blocked_reasons": [item["intent"].get("reason") for item in blocked],
        "lifecycle_checks": lifecycle_checks,
    }


def find_position(
    execution_service_url: str,
    exchange: str,
    account_id: str,
    pair_id: str,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    positions_payload = http_get_json(
        f"{execution_service_url}/v1/execution/portfolio/positions",
        timeout,
        {"exchange": exchange, "account_id": account_id},
    )
    position = None
    for row in positions_payload.get("positions", []):
        if row.get("pair_id") == pair_id:
            position = row
            break
    return positions_payload, position


def run_report(args: argparse.Namespace) -> dict[str, Any]:
    health = {
        "data_service": http_get_json(f"{args.data_service_url}/health", args.timeout_seconds),
        "account_service": http_get_json(
            f"{args.account_service_url}/health", args.timeout_seconds
        ),
        "execution_service": http_get_json(
            f"{args.execution_service_url}/health", args.timeout_seconds
        ),
        "strategy_service": http_get_json(
            f"{args.strategy_service_url}/health", args.timeout_seconds
        ),
    }
    assert_true(
        all(item.get("status") == "ok" for item in health.values()),
        "one or more service health checks failed",
    )

    cues = http_get_json(
        f"{args.strategy_service_url}/v1/strategy/pairs/cues",
        args.timeout_seconds,
        {"timeframe": args.timeframe, "limit": 20},
    )
    cue_rows = cues.get("cues", [])
    assert_true(len(cue_rows) > 0, "no strategy cues available")

    cue_row = next((row for row in cue_rows if row.get("cue", {}).get("actionable")), cue_rows[0])
    cue = cue_row.get("cue", {})
    pair_id = cue.get("pair_id")
    left = cue.get("left_instrument")
    right = cue.get("right_instrument")
    spread_z = cue.get("spread_z")

    assert_true(bool(pair_id), "selected cue is missing pair_id")
    assert_true(bool(left) and bool(right), "selected cue is missing instruments")

    left_warm = warm_integrity(
        args.data_service_url,
        str(left),
        args.timeframe,
        args.timeout_seconds,
    )
    right_warm = warm_integrity(
        args.data_service_url,
        str(right),
        args.timeframe,
        args.timeout_seconds,
    )

    account_seed = seed_account_state(
        args.account_service_url,
        args.exchange,
        args.account_id,
        args.timeout_seconds,
    )
    kill_switch = enforce_kill_switch_off(args.execution_service_url, args.timeout_seconds)

    entry_outcomes = run_intent_lifecycle(
        execution_service_url=args.execution_service_url,
        exchange=args.exchange,
        account_id=args.account_id,
        operator_id=args.operator_id,
        timeframe=args.timeframe,
        pair_id=str(pair_id),
        spread_direction="LONG_SPREAD",
        spread_z=float(spread_z) if spread_z is not None else None,
        qty=args.spread_qty,
        action="ENTRY",
        legs=long_entry_legs(str(left), str(right)),
        timeout=args.timeout_seconds,
    )
    entry_validation = validate_outcomes(entry_outcomes, args.require_dispatch_ack)

    positions_after_entry, pair_position_after_entry = find_position(
        args.execution_service_url,
        args.exchange,
        args.account_id,
        str(pair_id),
        args.timeout_seconds,
    )
    assert_true(
        pair_position_after_entry is not None,
        "spread position did not appear after entry flow",
    )

    close_outcomes: list[dict[str, Any]] = []
    close_validation: dict[str, Any] | None = None
    positions_after_close: dict[str, Any] | None = None
    pair_position_after_close: dict[str, Any] | None = None

    if args.include_close:
        close_outcomes = run_intent_lifecycle(
            execution_service_url=args.execution_service_url,
            exchange=args.exchange,
            account_id=args.account_id,
            operator_id=args.operator_id,
            timeframe=args.timeframe,
            pair_id=str(pair_id),
            spread_direction="LONG_SPREAD",
            spread_z=None,
            qty=float(pair_position_after_entry.get("total_size", args.spread_qty)),
            action="EMERGENCY_STOP_CLOSE",
            legs=long_close_legs(str(left), str(right)),
            timeout=args.timeout_seconds,
        )
        close_validation = validate_outcomes(close_outcomes, args.require_dispatch_ack)
        positions_after_close, pair_position_after_close = find_position(
            args.execution_service_url,
            args.exchange,
            args.account_id,
            str(pair_id),
            args.timeout_seconds,
        )

    reconcile_run = http_post_json(
        f"{args.account_service_url}/v1/account/reconcile/run",
        {},
        args.timeout_seconds,
    )
    reconcile_after = http_get_json(
        f"{args.account_service_url}/v1/account/reconcile",
        args.timeout_seconds,
        {"exchange": args.exchange, "account_id": args.account_id},
    )

    checks = {
        "services_healthy": True,
        "strategy_cue_available": True,
        "entry_accepted": entry_validation["accepted_count"] >= 2,
        "entry_dispatch_acknowledged_or_allowed": (
            all(item["dispatch_result"] == "ACKNOWLEDGED" for item in entry_validation["lifecycle_checks"])
            if args.require_dispatch_ack
            else True
        ),
        "position_updated_after_entry": pair_position_after_entry is not None,
        "reconcile_status_ok": reconcile_after.get("reconcile", {}).get("status") == "OK",
    }

    if args.include_close:
        checks["close_accepted"] = (close_validation or {}).get("accepted_count", 0) >= 2
        if args.require_flat_after_close:
            checks["position_flat_after_close"] = pair_position_after_close is None

    report = {
        "generated_at": iso(utc_now()),
        "request": {
            "exchange": args.exchange,
            "account_id": args.account_id,
            "timeframe": args.timeframe,
            "spread_qty": args.spread_qty,
            "operator_id": args.operator_id,
            "include_close": args.include_close,
            "require_dispatch_ack": args.require_dispatch_ack,
            "require_flat_after_close": args.require_flat_after_close,
        },
        "selected_pair": {
            "pair_id": pair_id,
            "left_instrument": left,
            "right_instrument": right,
            "spread_z": spread_z,
        },
        "health": health,
        "integrity_warmup": {
            str(left): left_warm.get("integrity"),
            str(right): right_warm.get("integrity"),
        },
        "account_seed": account_seed,
        "kill_switch": kill_switch,
        "entry": {
            "validation": entry_validation,
            "outcomes": entry_outcomes,
            "positions_after_entry": positions_after_entry,
            "pair_position_after_entry": pair_position_after_entry,
        },
        "close": {
            "validation": close_validation,
            "outcomes": close_outcomes,
            "positions_after_close": positions_after_close,
            "pair_position_after_close": pair_position_after_close,
        }
        if args.include_close
        else None,
        "reconcile": {
            "run": reconcile_run,
            "after": reconcile_after,
        },
        "checks": checks,
    }

    report["pass"] = all(bool(value) for value in checks.values())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--account-service-url", default="http://127.0.0.1:8081")
    parser.add_argument("--execution-service-url", default="http://127.0.0.1:8082")
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:8083")
    parser.add_argument("--exchange", default="kraken_futures")
    parser.add_argument("--account-id", default="primary")
    parser.add_argument("--operator-id", default="operator-e2e")
    parser.add_argument("--timeframe", choices=["1m", "15m", "1h"], default="1m")
    parser.add_argument("--spread-qty", type=float, default=1.25)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--include-close",
        action="store_true",
        help="also execute emergency-stop-close legs after entry",
    )
    parser.add_argument(
        "--require-flat-after-close",
        action="store_true",
        help="mark failure if pair position remains open after close flow",
    )
    parser.add_argument(
        "--allow-non-ack-dispatch",
        action="store_true",
        help="do not require ACKNOWLEDGED dispatch results",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/manual_trade_e2e_report.json",
        help="report output path",
    )
    args = parser.parse_args()

    args.spread_qty = max(0.001, args.spread_qty)
    args.timeout_seconds = max(3, args.timeout_seconds)
    args.require_dispatch_ack = not args.allow_non_ack_dispatch

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = run_report(args)
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": f"request failed: {error}",
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1
    except CheckFailure as error:
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": str(error),
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 2

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 3


if __name__ == "__main__":
    sys.exit(main())
