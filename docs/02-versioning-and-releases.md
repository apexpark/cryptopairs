# Versioning and Releases

This repository uses **SemVer** with additional rules for **contracts/specs** and **operational behavior**.

## What Is Versioned

We version:
1) **System behavior** (execution, risk decisions, integrity gating)
2) **Contracts** (schemas, message formats, API shapes, config keys)
3) **Release artifacts** (container images, packages, deploy bundles) — when code exists

Even before code exists, we still version:
- `specs/contracts/*`
- public docs that define externally visible behavior

## Semantic Versioning Rules

### Version Format
`MAJOR.MINOR.PATCH`

### MAJOR Bump (Breaking)
Any change that breaks compatibility for:
- contract consumers/producers
- config keys/meaning
- required operational procedures
- order lifecycle semantics
- integrity status meanings

Examples:
- removing a required field from an event schema
- changing a status enum meaning
- changing risk policy defaults in a way that alters behavior without opt-in

### MINOR Bump (Backward Compatible Feature)
Additive and backward compatible:
- adding optional fields to schemas
- adding new contract/event types without breaking old ones
- new features behind flags with safe defaults
- new metrics/log fields

### PATCH Bump (Fix)
- bug fixes
- doc fixes that do not change defined behavior
- internal refactors (once code exists) with no contract change

## Contracts vs Implementation Versioning

### Contract Versioning
Contracts live in `specs/contracts/`.
- The repository version applies to the entire system.
- Additionally, each contract file SHOULD include a `version` field (or `$id` with versioning).

### Compatibility Rule Of Thumb
Default is **additive only**.
Breaking changes require:
- MAJOR bump
- migration/deprecation notes in `docs/03-contracts-and-compatibility.md`
- `CHANGELOG.md` entry

## Release Artifacts (When Code Exists)

A release SHOULD include:
- tagged git commit
- changelog entry
- published artifacts (containers/packages)
- migration notes (if any)
- updated runbooks (if ops changed)

Recommended tagging: `vMAJOR.MINOR.PATCH`

## Release Checklist (Use Even Pre-Code)

Before cutting a release/tag:
- [ ] `CHANGELOG.md` updated
- [ ] Contract changes documented + compatibility reviewed
- [ ] Threat model impact considered for security-sensitive changes
- [ ] DoR/DoD satisfied per `docs/README.md`
- [ ] Any new operational requirement reflected in playbooks
- [ ] Version bump is correct per SemVer rules
