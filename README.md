# Crypto Pairs Trader

This repo is currently **docs-first**: policies, contracts, and operational playbooks come before implementation.

## Start Here
- `AGENTS.md` (highest precedence; mandatory for agents)
- `docs/README.md` (documentation map + precedence)
- `docs/00-guardrails.md` and `docs/01-product-scope.md`
- `docs/05-agent-build-workflow.md` and `docs/17-verification-protocol.md`

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

## Onboarding Flow

1. Read scope and guardrails (`docs/00-guardrails.md`, `docs/01-product-scope.md`).
2. Read governance workflow/policies (`docs/02-05`, `docs/07`, `docs/17`).
3. Review architecture and domain policies (`docs/10-architecture.md` plus relevant `11-16` docs).
4. Use runbooks and ADRs for operations and design decisions.

## Contracts
Machine-readable contracts should live in:
- `specs/contracts/`
with examples in:
- `specs/examples/`

## Versioning
See `docs/02-versioning-and-releases.md` and `CHANGELOG.md`.
