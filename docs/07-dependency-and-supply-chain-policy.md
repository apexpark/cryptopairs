# Dependency and Supply Chain Policy

## Purpose

Define controls for adding, updating, and auditing third-party dependencies across Rust, Python, and frontend tooling.

## Hard Rules

1. `MUST` pin dependency versions through lockfiles or exact versions.
2. `MUST` document why each new dependency is needed.
3. `MUST` prefer mature, maintained packages with clear license terms.
4. `MUST` run vulnerability and license checks before merge.
5. `MUST` avoid unreviewed transitive dependency sprawl.
6. `MUST` record externally relevant dependency changes in `CHANGELOG.md`.
7. `MUST` remove unused dependencies promptly.

## Approval Requirements

Any new dependency must include:

1. Package name and version.
2. Use case and affected modules.
3. Security/maintenance assessment summary.
4. Rollback/removal plan.

## Ecosystem Controls

1. Rust:
- Commit `Cargo.lock` for application crates.
- Use exact/compatible constraints with review.

2. Python:
- Use pinned requirements or lock tooling.
- Separate runtime vs dev dependencies.

3. Frontend:
- Use lockfile-enforced installs.
- Avoid overlapping UI frameworks unless justified by `docs/16-ui-styling-guide.md`.

## Update Policy

1. Security patches: prioritize and fast-track.
2. Routine updates: batch in small reviewable changes.
3. Breaking upgrades: require compatibility review and migration notes.

## Verification

Before merge:

1. Dependency scan results reviewed.
2. Lockfile changes inspected.
3. Affected tests executed.
4. Changelog updated when behavior/external surface changes.

## Out Of Scope

1. Private package registry setup details.
2. Enterprise SBOM tooling mandates in local MVP phase.
