# Verification Protocol (Anti-Hallucination)

This repository enforces proof-based development.

## Purpose

Define evidence requirements so claims are grounded in repository artifacts, tests, or operational signals.

## Rule: Every Claim Must Be Verifiable
If you state that something exists or works, you must provide one of:
- exact file path + (when applicable) symbol name
- an example payload (specs/examples) + schema reference
- a test that proves it (when code exists)
- a runtime signal definition (metric/log/alert) that would prove it in operation

If none of the above exist, label it as **PROPOSAL**.

## Evidence Types
- **Repo evidence**: `path/to/file`
- **Schema evidence**: explicit schema path under `specs/contracts/` plus version identifier
- **Example evidence**: explicit example path under `specs/examples/` linked to its schema
- **Operational evidence**: metric name + meaning, alert threshold

## Unknowns Must Stop Work
If a safety-critical unknown exists (risk, execution, integrity), you must:
- stop
- summarize unknowns
- propose a minimal safe next step
- request the missing information

## No Assumed Architecture
Until code exists, architecture is what’s described in:
- `docs/10-architecture.md`
- ADRs in `docs/adr/`

Any deviation requires a new ADR.
