# Repo Structure and Ownership

This document prevents sprawl and ensures agents place work in predictable locations.

## Current State
At minimum, this repo contains:
- `docs/` policy + playbooks + ADRs
- `specs/` machine-readable contracts + examples
- `.github/` templates + ownership configuration
- `AGENTS.md`, `CHANGELOG.md`, `README.md`
- `services/` Rust service scaffolding
- `crates/` shared Rust types
- `research/` Python strategy scaffolding
- `apps/` frontend app directory scaffold
- `infra/` local stack and SQL bootstrap
- `tools/` utility scripts directory scaffold

## Future Golden Layout (When Code Arrives)

Recommended top-level layout:
- `services/` — production services (Rust-first for critical paths)
- `apps/` — UI and dashboards (React)
- `research/` — Python research/backtesting
- `specs/` — contracts + examples (source of truth)
- `tools/` — local tooling, linters, generators
- `infra/` — deployment manifests (later)

## Ownership (Role-Based Until Teams Exist)

Define these owners (CODEOWNERS can enforce later):
- **Data Integrity Owner**: ingestion/backfill/integrity gating
- **Execution Owner**: order lifecycle, idempotency, reconciliation
- **Risk Owner**: risk engine, limits, kill switch
- **Security Owner**: auth, secrets, key handling, threat model
- **Observability Owner**: metrics/logs/alerts/SLOs
- **UI Owner**: dashboards, styling, operator UX
- **Contracts Owner**: schemas, compatibility, versioning

If a change touches a domain, it requires that owner review.

## Placement Rules
- Machine-readable schemas MUST go in `specs/contracts/`
- Example payloads MUST go in `specs/examples/`
- Operational runbooks MUST go in `docs/playbooks/`
- Architecture decisions MUST go in `docs/adr/`
- Policies belong in `docs/` and MUST be referenced by the change
- GitHub governance files (`CODEOWNERS`, PR templates) MUST live in `.github/`
