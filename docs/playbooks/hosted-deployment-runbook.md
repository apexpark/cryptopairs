# Hosted Deployment Runbook (Hetzner + Timescale + Vercel)

## Purpose

Provide a controlled, step-by-step rollout path for public browser access with always-on backend services.

## Scope

1. Hetzner CPX32 VM for backend services.
2. Timescale Performance plan for managed database.
3. Vercel Pro for frontend hosting.

## Step Sequence

1. Track status in `plans/hosted_deployment_plan.json`.
2. Complete provider setup and billing.
3. Establish DNS and TLS routing.
4. Wire production environment configuration and secrets.
5. Deploy immutable backend services with persistent startup.
6. Deploy web app and connect hosted API base URLs.
7. Validate fail-closed readiness and data pipeline health.
8. Enable demo sharing with manual-only controls.

## Preflight Checklist

1. All provider accounts active with billing enabled.
2. Domain available for subdomains (example: `app.<domain>`, `api.<domain>`).
3. Repo access and deploy permissions confirmed.
4. Secrets storage approach chosen (mounted files or provider secret manager).

## Control Commands

```bash
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json summary
python3 tools/scripts/alpha_tracker.py --plan plans/hosted_deployment_plan.json checkpoint --delta "<delta>" --next-action "<next>"
```

```bash
cd /opt/cryptopairs
bash scripts/deploy.sh
```

Optional targeted deploy:

```bash
cd /opt/cryptopairs
bash scripts/deploy.sh --services data-service,strategy-service
```

Slow-start services (for example strategy-service after recreate) may require a larger health
window:

```bash
bash scripts/deploy.sh --services strategy-service --health-retries 30 --health-sleep-secs 2
```

## One-Click Maintenance Actions (Promote / Revert)

The strategy-service maintenance action endpoint can execute promote/revert deploys from the
Analytics UI. This requires strategy-service to control Docker on the host.

Required runtime capabilities:
1. Docker socket mounted into strategy-service:
- `/var/run/docker.sock:/var/run/docker.sock`
2. Docker CLI available in strategy-service container (`docker` + compose support).

Validation command:
```bash
curl -i -s -X POST "http://127.0.0.1:8083/v1/strategy/maintenance/action" \
  -H "Content-Type: application/json" \
  --data '{"action":"PROMOTE","operator_id":"diag","confirm":false}'
```

Expected result:
1. `400` with `confirm=true is required ...` means the endpoint is present.
2. `404` means the running strategy-service build is missing maintenance action support.

Security note:
1. Docker socket access is privileged and should be limited to trusted single-tenant hosts.
2. Keep API access restricted and monitor maintenance action artifacts for operator/audit review.

## Validation Commands

```bash
python3 tools/scripts/fail_closed_readiness_check.py \
  --exchange kraken_futures \
  --account-id primary \
  --data-service-url https://api.<domain>/data \
  --account-service-url https://api.<domain>/account \
  --execution-service-url https://api.<domain>/execution \
  --strategy-service-url https://api.<domain>/strategy \
  --output-json artifacts/fail_closed_readiness_report_hosted.json
```

```bash
python3 tools/scripts/data_pipeline_e2e_check.py \
  --data-service-url https://api.<domain>/data \
  --instrument PI_XBTUSD \
  --timeframe 1m \
  --output-json artifacts/data_pipeline_e2e_report_hosted.json
```

## Rollback Rules

1. If health checks fail after deploy, revert to previous image tag and restart services.
2. Keep `EXECUTION_DISPATCH_MODE=fail_closed` until all hosted checks pass.
3. If data integrity drops below threshold, block entries and run backfill repair first.

## User Required Actions

1. Purchase plans and enable billing.
2. Create/assign DNS records.
3. Provide secrets via secure channel or provider secret manager.
4. Approve first public URL go-live.

## Notes

Use this runbook with:
- `docs/21-hosted-deployment-control.md`
- `docs/playbooks/execution-operations-runbook.md`
- `docs/playbooks/secrets-lifecycle-runbook.md`

Bootstrap metadata:
- Hetzner VM public IPv4 (initial): `46.224.220.150`
- This IP is for first-connection/bootstrap only; production routing should use DNS hostnames.
