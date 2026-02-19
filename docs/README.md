# Crypto Pairs Trader Docs

This documentation defines design intent, engineering guardrails, and operational procedures for the local-first then hosted build of the crypto perpetual futures trading system.

Repository entrypoint for onboarding is `README.md`.

## Precedence

If instructions conflict, use this order:

1. `AGENTS.md`
2. `docs/00-guardrails.md`
3. `docs/01-product-scope.md`
4. Governance docs in `docs/` (`02-05`, `07`, and `17`)
5. Module policy docs in `docs/` (`10-16` series)
6. Playbooks in `docs/playbooks/`
7. ADRs in `docs/adr/`
8. Temporary notes and ad hoc plans

## How To Use This Folder

1. Read `docs/00-guardrails.md` before designing or coding.
2. Read governance docs relevant to your change (`docs/02-05`, `docs/07`, and `docs/17`).
3. Read module policy docs relevant to your change (`docs/10-16`).
4. Follow the runbooks for incidents or data repairs.
5. Record architectural decisions as ADRs.

## Documents

- `docs/00-guardrails.md`
- `docs/01-product-scope.md`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/04-repo-structure-and-ownership.md`
- `docs/05-agent-build-workflow.md`
- `docs/07-dependency-and-supply-chain-policy.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/13-secrets-and-security.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `docs/16-ui-styling-guide.md`
- `docs/17-verification-protocol.md`
- `docs/18-strategy-module-implementation-spec.md`
- `docs/19-manual-trading-operator-ui-session.md`
- `docs/playbooks/backfill-runbook.md`
- `docs/playbooks/incident-runbook.md`
- `docs/adr/ADR-0001-hybrid-rust-python.md`

## Definition Of Ready

A task is ready when:

- Goal and module owner are identified.
- Affected interfaces and data contracts are listed.
- Risk and rollback path are defined.
- Test plan is defined (unit/integration/replay).

## Definition Of Done

A task is done when:

- Code matches guardrails and module policy docs.
- Tests pass at the required level.
- Metrics/logging/alerts are updated if behavior changed.
- Relevant docs and ADRs are updated.
