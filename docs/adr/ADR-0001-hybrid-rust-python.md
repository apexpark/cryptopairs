# ADR-0001: Hybrid Rust + Python Architecture

## Status

Accepted

## Date

2026-02-17

## Context

The platform must support:

1. High-reliability exchange connectivity and execution.
2. Fast iteration for quantitative strategy research.
3. Local-first operation with a clean path to hosted deployment.
4. Strong data integrity guarantees for downstream strategy safety.

A single-language implementation creates tradeoffs:

1. All Python: faster research, weaker systems-level guarantees in critical paths.
2. All Rust: stronger safety/performance, slower strategy prototyping and experimentation.

## Decision

Adopt a hybrid architecture:

1. Rust for safety-critical and latency-sensitive services:
- Kraken adapter
- Data ingestion/backfill/integrity services
- Execution and risk controls
- Account reconciliation core

2. Python for strategy R&D:
- Pairs trading model prototyping
- Backtesting and parameter exploration
- Transition validated logic to Rust when entering live-critical paths

3. Use explicit contracts between Rust and Python layers:
- Versioned schemas
- Deterministic event formats
- Integrity metadata attached to all market data responses

## Consequences

### Positive

1. Better reliability and operational safety in live execution.
2. Faster strategy iteration and research throughput.
3. Clear migration path from prototype to productionized strategy logic.

### Negative

1. Higher system complexity across two language ecosystems.
2. Additional integration and contract testing burden.
3. Team must maintain Rust and Python proficiency.

## Guardrails

1. No direct strategy-to-exchange order path bypassing Rust risk/execution services.
2. Live strategy runs require integrity and risk gates.
3. Contract changes require versioning and compatibility tests.
