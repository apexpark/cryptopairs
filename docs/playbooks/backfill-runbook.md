# Backfill Runbook

## Purpose

Operational procedure for diagnosing and repairing missing market data.

## Triggers

1. Data query returns `PARTIAL_BACKFILLED`, `INCOMPLETE`, or `FAILED`.
2. Integrity alert fired for active symbol/timeframe.
3. Manual operator request.

## Inputs

1. `instrument`
2. `timeframe`
3. `requested_start`
4. `requested_end`
5. `missing_ranges`

## Procedure

1. Confirm active exchange connectivity and auth health.
2. Verify local data range currently present.
3. Execute targeted backfill for each missing range.
4. Re-run gap detection and integrity calculation.
5. If still incomplete, retry per policy limits.
6. If unresolved after max retries, mark interval unresolved with reason code.
7. Raise incident when unresolved ranges affect strategy-required windows.

## Validation

1. No duplicate timestamp collisions after merge/upsert.
2. Range continuity matches timeframe granularity.
3. Integrity status updated and persisted.

## User Communication Requirements

1. Report integrity status and coverage percentage.
2. List unresolved intervals and reason codes.
3. State whether strategy/live execution is blocked by policy.

## Escalation

1. Exchange API limitations or outages.
2. Persistent schema/parsing failures.
3. Repeated unresolved gaps on core trading pairs.
