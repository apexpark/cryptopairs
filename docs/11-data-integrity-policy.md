# Data Integrity Policy

## Purpose

Define strict rules for local-first market data retrieval, gap detection, backfill, and user integrity reporting.

## Integrity Status Values

1. `COMPLETE`: no gaps detected for requested window.
2. `PARTIAL_BACKFILLED`: gaps found and some repaired.
3. `INCOMPLETE`: unresolved gaps remain.
4. `STALE`: data older than freshness threshold.
5. `FAILED`: ingestion or backfill operation failed.

## Hard Rules

1. `MUST` query local storage first for all data requests.
2. `MUST` run gap detection before returning data to strategy/execution consumers.
3. `MUST` attempt targeted backfill for missing intervals.
4. `MUST` avoid full-window backfill when only partial intervals are missing.
5. `MUST` return integrity metadata with each response.
6. `MUST NOT` silently downgrade integrity status.
7. `MUST` persist integrity checks in a quality table for audit/replay.
8. `MUST` block live execution when integrity threshold fails.

## Required Response Fields

1. `status`
2. `coverage_pct`
3. `missing_ranges`
4. `last_verified_at`
5. `warnings`

## Gap Detection Rules

1. Validate expected timestamp continuity by timeframe and instrument.
2. Detect duplicates and out-of-order records.
3. Detect stale windows using per-timeframe freshness thresholds.

## Backfill Rules

1. Use bounded targeted ranges only.
2. Retry with exponential backoff and capped attempts.
3. Mark unresolved ranges with reason codes.
4. Emit alert when unresolved ranges affect strategy-required windows.

## Strategy And Execution Gating

1. Strategy backtest may proceed with `INCOMPLETE` only if explicitly allowed and recorded.
2. Paper trading may proceed with warning when within configured tolerance.
3. Live trading `MUST` be blocked when below policy threshold.

## Acceptance Checks

1. Data query returns integrity metadata in all cases.
2. Known synthetic gaps are detected and reported.
3. Backfill worker repairs recoverable gaps and updates status.
4. Non-recoverable gaps produce user-visible integrity warnings.

## Failure Handling

1. On repeated backfill failure, escalate incident and link affected symbols/timeframes.
2. Preserve raw error context for diagnostics.
3. Continue serving available data with explicit degraded status.

## Out Of Scope

1. Vendor-level correction of historical exchange anomalies.
2. Perfect tick-level reconstruction when source data is unavailable.
