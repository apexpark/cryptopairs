#!/usr/bin/env python3
"""Run a reproducible E2E check for data capture/backfill/storage integrity."""

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


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_get_json(url: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_report(
    data_service_url: str,
    instrument: str,
    timeframe: str,
    lookback_minutes: int,
    history_limit: int,
    min_coverage_pct: float,
    timeout: int,
) -> dict[str, Any]:
    end_ts = utc_now()
    start_ts = end_ts - dt.timedelta(minutes=lookback_minutes)

    health_url = f"{data_service_url}/health"
    health = http_get_json(health_url, timeout)

    query_url = f"{data_service_url}/v1/data/query"
    query_payload = {
        "instrument": instrument,
        "timeframe": timeframe,
        "start_ts": iso(start_ts),
        "end_ts": iso(end_ts),
    }
    query_response = http_post_json(query_url, query_payload, timeout)

    history_query = urllib.parse.urlencode(
        {
            "instrument": instrument,
            "timeframe": timeframe,
            "limit": history_limit,
        }
    )
    history_url = f"{data_service_url}/v1/integrity/history?{history_query}"
    history_response = http_get_json(history_url, timeout)

    integrity = query_response.get("integrity", {})
    status = integrity.get("status")
    coverage_pct = float(integrity.get("coverage_pct", 0.0))
    candles = query_response.get("candles", [])
    history_rows = history_response.get("rows", [])

    checks = {
        "health_ok": health.get("status") == "ok",
        "candles_non_empty": len(candles) > 0,
        "integrity_status_present": bool(status),
        "integrity_history_present": len(history_rows) > 0,
        "coverage_threshold_met": coverage_pct >= min_coverage_pct,
    }

    pass_all = all(checks.values()) and status in {"COMPLETE", "PARTIAL_BACKFILLED"}

    return {
        "generated_at": iso(utc_now()),
        "data_service_url": data_service_url,
        "request": query_payload,
        "health": health,
        "integrity": {
            "status": status,
            "coverage_pct": coverage_pct,
            "missing_ranges": integrity.get("missing_ranges", []),
            "warnings": integrity.get("warnings", []),
            "last_verified_at": integrity.get("last_verified_at"),
        },
        "counts": {
            "candles": len(candles),
            "history_rows": len(history_rows),
        },
        "checks": checks,
        "pass": pass_all,
        "latest_history_row": history_rows[0] if history_rows else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--instrument", default="PI_XBTUSD")
    parser.add_argument("--timeframe", choices=["1m", "15m", "1h"], default="1m")
    parser.add_argument("--lookback-minutes", type=int, default=240)
    parser.add_argument("--history-limit", type=int, default=20)
    parser.add_argument("--min-coverage-pct", type=float, default=99.5)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--output-json",
        default="artifacts/data_pipeline_e2e_report.json",
        help="Report output path",
    )
    args = parser.parse_args()

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = build_report(
            data_service_url=args.data_service_url,
            instrument=args.instrument,
            timeframe=args.timeframe,
            lookback_minutes=max(10, args.lookback_minutes),
            history_limit=max(1, min(500, args.history_limit)),
            min_coverage_pct=max(0.0, min(100.0, args.min_coverage_pct)),
            timeout=max(3, args.timeout_seconds),
        )
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        failure = {
            "generated_at": iso(utc_now()),
            "pass": False,
            "error": f"request failed: {error}",
        }
        output_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1

    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 2


if __name__ == "__main__":
    sys.exit(main())
