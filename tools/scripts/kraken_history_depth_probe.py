#!/usr/bin/env python3
"""
Probe Kraken Futures chart history depth and basic continuity for selected timeframes.

This script uses live Kraken responses and does not fabricate data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List

BASE_URL = "https://futures.kraken.com/api/charts/v1"
SUPPORTED_TIMEFRAMES = ("1m", "15m", "1h")
STEP_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000}


def fetch_candles(symbol: str, timeframe: str, start_sec: int, end_sec: int) -> Dict[str, Any]:
    query = urllib.parse.urlencode({"from": start_sec, "to": end_sec})
    url = f"{BASE_URL}/trade/{symbol}/{timeframe}?{query}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if "candles" not in data:
        raise RuntimeError(f"unexpected payload structure for {timeframe}: {data}")
    return data


def continuity_issues(candles: List[Dict[str, Any]], step_ms: int) -> int:
    if len(candles) < 2:
        return 0
    issues = 0
    previous = candles[0]["time"]
    for candle in candles[1:]:
        current = candle["time"]
        if current - previous != step_ms:
            issues += 1
        previous = current
    return issues


def iso(ms: int) -> str:
    return dt.datetime.utcfromtimestamp(ms / 1000).replace(tzinfo=dt.timezone.utc).isoformat()


def probe(symbol: str, timeframe: str) -> Dict[str, Any]:
    now_sec = int(time.time())
    data = fetch_candles(symbol, timeframe, 0, now_sec)
    candles = data["candles"]
    if not candles:
        return {
            "timeframe": timeframe,
            "symbol": symbol,
            "candles_returned": 0,
            "more_candles": bool(data.get("more_candles", False)),
            "earliest_candle_ms": None,
            "earliest_candle_iso": None,
            "latest_candle_ms": None,
            "latest_candle_iso": None,
            "continuity_issues_in_page": 0,
        }

    earliest = candles[0]["time"]
    latest = candles[-1]["time"]
    issues = continuity_issues(candles, STEP_MS[timeframe])

    return {
        "timeframe": timeframe,
        "symbol": symbol,
        "candles_returned": len(candles),
        "more_candles": bool(data.get("more_candles", False)),
        "earliest_candle_ms": earliest,
        "earliest_candle_iso": iso(earliest),
        "latest_candle_ms": latest,
        "latest_candle_iso": iso(latest),
        "continuity_issues_in_page": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PI_XBTUSD", help="Kraken Futures instrument symbol")
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=list(SUPPORTED_TIMEFRAMES),
        choices=SUPPORTED_TIMEFRAMES,
        help="Timeframes to probe",
    )
    parser.add_argument(
        "--output-json",
        default="specs/examples/kraken_history_depth_probe.json",
        help="Output path for probe report",
    )
    args = parser.parse_args()

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": f"{BASE_URL}/trade/:symbol/:timeframe?from=<sec>&to=<sec>",
        "symbol": args.symbol,
        "results": [probe(args.symbol, tf) for tf in args.timeframes],
    }

    with open(args.output_json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
