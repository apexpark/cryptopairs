# Secrets Lifecycle Runbook

## Purpose

Define operator-safe credential handling for hosted trading deployments.

## Source of Truth

1. Rotation policy:
- `infra/config/hosted_secrets_rotation_policy.json`

2. Hosted environment template:
- `infra/env/hosted-mode.env.example`

3. Audit script:
- `tools/scripts/secrets_lifecycle_audit.py`

## Operator Settings (Friendly -> Technical Key)

1. Kraken API Key Secret Reference (`KRAKEN_FUTURES_API_KEY_REF`)
2. Kraken API Secret Reference (`KRAKEN_FUTURES_API_SECRET_REF`)
3. Kraken API Key Mounted File (`KRAKEN_FUTURES_API_KEY_FILE`)
4. Kraken API Secret Mounted File (`KRAKEN_FUTURES_API_SECRET_FILE`)

Hosted rule:
- Keep inline secret values empty for `KRAKEN_FUTURES_API_KEY` and `KRAKEN_FUTURES_API_SECRET`.

## Pre-Live Validation

1. Run lifecycle audit:

```bash
python3 tools/scripts/secrets_lifecycle_audit.py \
  --policy-json infra/config/hosted_secrets_rotation_policy.json \
  --env-file infra/env/hosted-mode.env.example \
  --output-json artifacts/secrets_lifecycle_audit_report.json
```

2. In deployment environments with mounted files, enforce file presence/age:

```bash
python3 tools/scripts/secrets_lifecycle_audit.py \
  --policy-json infra/config/hosted_secrets_rotation_policy.json \
  --env-file /path/to/runtime.env \
  --enforce-mounted-files \
  --output-json artifacts/secrets_lifecycle_audit_report.json
```

3. Confirm report contains `"pass": true`.

## Rotation Procedure

1. Create new secret version in vault/KMS.
2. Update mounted secret material or secret reference pointer.
3. Restart only affected services (minimum: `execution-service`).
4. Run secrets lifecycle audit and verify pass.
5. Run manual trade E2E check in paper mode before restoring live traffic.

## Incident Procedure (Suspected Leak)

1. Activate kill switch immediately.
2. Revoke compromised keys in exchange console.
3. Rotate to new secret versions and redeploy.
4. Run audit + manual flow E2E checks.
5. Record incident timeline in:
- `docs/playbooks/incident-runbook.md`

## Fail-Closed Expectations

1. If key/secret values are missing in live mode, dispatch fails closed.
2. If secret files are unreadable or empty, dispatch fails closed.
3. Do not bypass by committing inline secrets to source control.
