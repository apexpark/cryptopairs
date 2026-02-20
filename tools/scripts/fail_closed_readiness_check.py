#!/usr/bin/env python3
"""Operator-facing fail-closed readiness check for manual trading sessions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_get_json(url: str, timeout: int, query: dict[str, Any] | None = None) -> dict[str, Any]:
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def alert_counts(alerts: list[dict[str, Any]]) -> tuple[int, int]:
    p1 = 0
    p2 = 0
    for alert in alerts:
        if not alert.get("triggered"):
            continue
        severity = str(alert.get("severity", "")).upper()
        if severity == "P1":
            p1 += 1
        elif severity == "P2":
            p2 += 1
    return p1, p2


def build_report(args: argparse.Namespace) -> dict[str, Any]:
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

    kill_switch = http_get_json(
        f"{args.execution_service_url}/v1/execution/kill-switch", args.timeout_seconds
    )
    execution_summary = http_get_json(
        f"{args.execution_service_url}/v1/execution/observability/summary",
        args.timeout_seconds,
        {
            "exchange": args.exchange,
            "account_id": args.account_id,
            "window_minutes": args.window_minutes,
        },
    )
    account_summary = http_get_json(
        f"{args.account_service_url}/v1/account/observability/summary",
        args.timeout_seconds,
        {
            "exchange": args.exchange,
            "account_id": args.account_id,
            "window_minutes": args.window_minutes,
        },
    )
    reconcile = http_get_json(
        f"{args.account_service_url}/v1/account/reconcile",
        args.timeout_seconds,
        {
            "exchange": args.exchange,
            "account_id": args.account_id,
        },
    )

    exec_p1, exec_p2 = alert_counts(execution_summary.get("alerts", []))
    acct_p1, acct_p2 = alert_counts(account_summary.get("alerts", []))
    total_p1 = exec_p1 + acct_p1
    total_p2 = exec_p2 + acct_p2

    checks = {
        "services_healthy": all(item.get("status") == "ok" for item in health.values()),
        "kill_switch_endpoint_readable": "active" in kill_switch,
        "reconcile_status_ok": reconcile.get("reconcile", {}).get("status") == "OK",
        "no_p1_alerts": total_p1 == 0,
    }

    if args.require_no_p2:
        checks["no_p2_alerts"] = total_p2 == 0

    ready_for_manual_entries = all(bool(value) for value in checks.values())

    return {
        "generated_at": iso(utc_now()),
        "request": {
            "exchange": args.exchange,
            "account_id": args.account_id,
            "window_minutes": args.window_minutes,
            "require_no_p2": args.require_no_p2,
        },
        "health": health,
        "kill_switch": kill_switch,
        "reconcile": reconcile,
        "execution_observability": execution_summary,
        "account_observability": account_summary,
        "alert_counts": {
            "execution": {"p1": exec_p1, "p2": exec_p2},
            "account": {"p1": acct_p1, "p2": acct_p2},
            "total": {"p1": total_p1, "p2": total_p2},
        },
        "checks": checks,
        "ready_for_manual_entries": ready_for_manual_entries,
        "recommended_action": (
            "ENABLE_MANUAL_ENTRY" if ready_for_manual_entries else "KEEP_FAIL_CLOSED"
        ),
        "pass": ready_for_manual_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--account-service-url", default="http://127.0.0.1:8081")
    parser.add_argument("--execution-service-url", default="http://127.0.0.1:8082")
    parser.add_argument("--strategy-service-url", default="http://127.0.0.1:8083")
    parser.add_argument("--exchange", default="kraken_futures")
    parser.add_argument("--account-id", default="primary")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--require-no-p2", action="store_true")
    parser.add_argument(
        "--output-json",
        default="artifacts/fail_closed_readiness_report.json",
    )
    args = parser.parse_args()

    args.window_minutes = max(1, min(args.window_minutes, 24 * 60))
    args.timeout_seconds = max(3, args.timeout_seconds)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": str(error),
            "recommended_action": "KEEP_FAIL_CLOSED",
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 2


if __name__ == "__main__":
    sys.exit(main())
