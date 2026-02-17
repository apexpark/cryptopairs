# Secrets And Security Policy

## Purpose

Define secure handling of credentials, privileged actions, and operational access.

## Hard Rules

1. `MUST NOT` store API keys/secrets in source control.
2. `MUST` encrypt secrets at rest and restrict access by least privilege.
3. `MUST` separate read-only and trading credentials where possible.
4. `MUST` rotate compromised credentials immediately.
5. `MUST` audit all privileged actions (orders, cancellations, config changes).
6. `MUST` use TLS for all remote service communication.
7. `MUST` redact secrets from logs and error payloads.

## Local Development Requirements

1. Use environment files excluded from git for local-only secrets.
2. Use local secret manager abstraction for service access.
3. Maintain separate profiles for `dev`, `paper`, and `live`.

## Access Control

1. Operator roles:
- `viewer`: read-only dashboards and logs.
- `operator`: strategy toggles and paper controls.
- `admin`: live mode, risk overrides, credential management.

2. Live mode requires explicit elevated role and confirmation workflow.

## Incident Response

1. Credential leak suspected:
- Revoke keys.
- Rotate keys.
- Audit recent actions and access logs.

2. Unauthorized action detected:
- Activate kill switch.
- Pause affected services.
- Start incident runbook.

## Acceptance Checks

1. Secret scanning passes in CI.
2. Log output contains no raw credentials.
3. Unauthorized action attempts are denied and audited.

## Out Of Scope

1. End-user IAM for external customers in MVP.
2. Hardware security module integration in initial local phase.
