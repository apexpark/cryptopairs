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

## Storage Retention Controls (Self-Hosted Timescale)

To keep hosted storage bounded, set retention env keys in `/opt/cryptopairs/.env.hosted`:

```bash
BACKFILL_INTERVAL_SECONDS=60
BACKFILL_WINDOW_DAYS_1M=90
BACKFILL_WINDOW_DAYS_15M=365
BACKFILL_WINDOW_DAYS_1H=730
CANDLES_RETENTION_DAYS_1M=90
CANDLES_RETENTION_DAYS_15M=365
CANDLES_RETENTION_DAYS_1H=730
TRADES_RETENTION_DAYS=120
CANDLES_PRUNE_INTERVAL_SECONDS=3600
STRATEGY_OPPORTUNITY_HISTORY_RETENTION_DAYS=180
STRATEGY_PAPER_TRADES_HISTORY_RETENTION_DAYS=180
STRATEGY_HISTORY_PRUNE_INTERVAL_SECONDS=3600
```

Apply updated settings:

```bash
cd /opt/cryptopairs
bash scripts/deploy.sh --skip-pull --services data-service,strategy-service
```

Verify bounded-growth settings are live:

```bash
docker exec cryptopairs-data-service printenv | rg 'TRADES_RETENTION_DAYS|CANDLES_PRUNE_INTERVAL_SECONDS'
docker exec cryptopairs-strategy-service printenv | rg 'STRATEGY_OPPORTUNITY_HISTORY_RETENTION_DAYS|STRATEGY_PAPER_TRADES_HISTORY_RETENTION_DAYS|STRATEGY_HISTORY_PRUNE_INTERVAL_SECONDS'
```

## Web Password Gate (UI Login Box)

The web app can require a password before loading any dashboard content.
This is controlled by strategy-service env var `STRATEGY_UI_ACCESS_PASSWORD`.

Set or rotate password on the server:

```bash
cd /opt/cryptopairs
sed -i '/^STRATEGY_UI_ACCESS_PASSWORD=/d' .env.hosted
echo 'STRATEGY_UI_ACCESS_PASSWORD=REPLACE_WITH_STRONG_PASSWORD' >> .env.hosted
bash scripts/deploy.sh --skip-pull --services strategy-service
```

Validate endpoints:

```bash
curl -s http://127.0.0.1:8083/v1/strategy/ui-auth/status
curl -i -s -X POST http://127.0.0.1:8083/v1/strategy/ui-auth/verify \
  -H 'Content-Type: application/json' \
  --data '{"password":"wrong"}'
```

Expected:
1. Status returns `{"enabled":true}` when password is configured.
2. Verify returns `401` for wrong password and `200 {"ok":true}` for correct password.

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

## Optimizer Candidate Inbox Actions

Candidate lifecycle control is exposed via strategy-service:
1. `GET /v1/strategy/pairs/candidate-inbox` for active challengers/promotable candidates.
2. `POST /v1/strategy/pairs/candidate-action` for manual `PROMOTE`, `HOLD`, `REJECT`.

Validation command:

```bash
curl -s "http://127.0.0.1:8083/v1/strategy/pairs/candidate-inbox?limit=3" | jq '.rows | length'
curl -i -s -X POST "http://127.0.0.1:8083/v1/strategy/pairs/candidate-action" \
  -H "Content-Type: application/json" \
  --data '{"pair_id":"PF_TAOUSD__PF_HYPEUSD","timeframe":"1h","action":"HOLD","operator_id":"diag","confirm":false}'
```

Expected result:
1. Inbox endpoint returns `200` with rows array (possibly empty).
2. Action endpoint returns `400` with `confirm=true is required ...` when confirmation is omitted.

## Async Reoptimization Runner Host Boundary (Future Gated)

Do not enable the async reoptimization scheduler during ordinary hosted
deployment. Enablement requires a separately approved implementation, bounded
metrics, conservative budgets, and operator-captured canary evidence.

Before any future scheduler enablement, the operator must capture:
1. host branch, commit, and dirty status;
2. deployed image or service identity;
3. scheduler, lease, budget, cache, and worker flag values;
4. proof live `ENTRY` and `EXIT` remain disabled;
5. proof promotion remains manual;
6. pre-enable CPU and hot endpoint latency baseline;
7. `/metrics` output for async runner metrics;
8. status endpoint output for the canary run;
9. artifact manifest and artifacts;
10. post-run CPU and hot endpoint latency comparison;
11. active alerts before and after the run.

If any host evidence is missing, stale, or contradictory, keep the scheduler
disabled and keep recommendations at `HOLD`.

Operator flows for enable, disable, cancel, artifact inspection, and rollback
are in `docs/playbooks/async-reoptimization-runner-runbook.md`.

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
