# Async Reoptimization Runner Runbook

## Purpose

Operate the bounded async reoptimization runner without weakening fail-closed
strategy behavior.

This runbook covers status inspection, disable/rollback, cancellation handling,
stuck lease recovery, budget exhaustion, missing telemetry, artifact evidence,
and the operator-only readiness checklist for the future production canary.

## Scope And Current Status

Implemented by the merged Slice A-D work and this Slice E branch:

1. durable async run state and single-flight lease state in
   `services/strategy-service/src/main.rs`;
2. disabled-by-default bounded runner controlled by
   `STRATEGY_REOPT_WORKER_ENABLED`;
3. read/enqueue-only async run endpoints:
   `POST /v1/strategy/reoptimize/runs`,
   `GET /v1/strategy/reoptimize/runs/latest`, and
   `GET /v1/strategy/reoptimize/runs/{run_id}`;
4. opt-in script modes for `tools/scripts/strategy_tuning_report.py` and
   `tools/scripts/strategy_maintenance_cycle.py`;
5. bounded async reoptimization metrics and structured runner/API logs;
6. async contracts and examples under
   `specs/contracts/strategy_reoptimize_run_*` and
   `specs/examples/strategy_reoptimize_run_*`.

Not implemented by these slices:

1. production scheduler enablement;
2. public mutating cancellation route;
3. artifact download route;
4. automatic `PROMOTE` or `REVERT`;
5. live `ENTRY` or `EXIT` enablement;
6. host verification.

Do not enable the runner or scheduler in production until Slice F is explicitly
approved by the operator.

## Hard Safety Rules

1. Host verification is operator-only. Agents must not SSH into `cryptopairs`
   or claim runtime state unless the operator provides evidence.
2. Unknown, stale, schema-invalid, expired, canceled, degraded, failed, or
   contradictory run state maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
3. Missing telemetry fails closed. Do not treat missing metrics, unreadable
   status, or missing artifacts as healthy.
4. Lease loss, lease expiry, budget exhaustion, artifact failure, and
   cancellation fail closed.
5. `PROMOTION_CANDIDATE_AVAILABLE` is evidence only. It must never enqueue or
   execute `PROMOTE`.
6. Repair-only provenance such as `RECANONICALIZED_LEGACY_ROW` remains
   fail-closed until an explicit operator-approved transition exists.
7. Live `ENTRY` and `EXIT` remain disabled unless approved through the risk and
   execution policy.
8. The synchronous route `POST /v1/strategy/pairs/reoptimize` remains
   compatible until a separate versioned migration is approved.

## Status Inspection

Use the status endpoints and persisted run state as evidence, not authority to
promote:

1. read `GET /v1/strategy/reoptimize/runs/latest` or the exact
   `GET /v1/strategy/reoptimize/runs/{run_id}` payload;
2. validate `status`, `trigger_source`, `recommendation`,
   `fail_closed_reasons`, progress, and budget fields against the async run
   contracts;
3. confirm the payload is fresh enough for the consuming workflow;
4. confirm the run is request-compatible before using it as maintenance report
   evidence;
5. treat null `request_fingerprint` or null `service_version` as unavailable
   compatibility evidence for workflows that require those fields;
6. compare status payloads, logs, metrics, and artifacts when artifacts are
   implemented.

Safe terminal handling:

| Status | Operator treatment |
|---|---|
| `SUCCEEDED` | Review evidence only if request-compatible, fresh, telemetry-backed, and artifact-backed when artifacts are required. |
| `DEGRADED` | `HOLD` or `OPERATOR_REVIEW_REQUIRED`; inspect budget/errors/artifacts. |
| `FAILED` | `HOLD`; inspect critical errors. |
| `EXPIRED` | `HOLD`; recover stale lease/run state before more work. |
| `CANCELED` | `HOLD`; cancellation is not success. |

Non-terminal states (`QUEUED`, `LEASED`, `RUNNING`,
`CANCEL_REQUESTED`) are not promotion evidence.

## Disable And Rollback

1. Set `STRATEGY_REOPT_WORKER_ENABLED=false`.
2. Restart only required services.
3. Verify no new scheduled mutation-producing run is enqueued after disable.
4. If an active run exists, let it reach terminal state under existing budgets
   or use an approved cancellation path when one exists.
5. Keep run rows, logs, and artifacts readable.
6. Keep maintenance/report recommendations fail-closed until a fresh approved
   successful run exists after re-enable.

Rollback must not delete run history or artifact evidence.

## Cancellation Handling

Cancellation is a state transition, not a process kill.

1. Inspect latest status and identify the exact `run_id`.
2. Confirm status is cancelable: `QUEUED`, `LEASED`, `RUNNING`, or
   `CANCEL_REQUESTED`.
3. Until an operator-approved mutating cancel route exists, do not invent a
   manual database mutation procedure.
4. If a future cancel route is approved, submit cancellation only for the exact
   run and then wait for terminal `CANCELED`, `FAILED`, or `EXPIRED`.
5. Confirm no new pair/timeframe work starts after cancellation is observed.
6. Inspect logs, progress, and artifacts for completed, skipped, canceled, and
   failed work.

`CANCELED` keeps recommendation at `HOLD` and must not produce
`PROMOTION_CANDIDATE_AVAILABLE`.

## Stuck Lease Or Expired Run Recovery

Symptoms:

1. `LEASED` or `RUNNING` persists past the configured lease TTL plus the
   operator-approved grace window;
2. `heartbeat_at` is missing or stale;
3. the same active run blocks new single-flight work;
4. status cannot prove the current owner and lease generation.

Response:

1. Do not enqueue a new mutation-producing run.
2. Keep scheduler enablement blocked.
3. Inspect status, `lease_owner`, `lease_generation`, `lease_expires_at`,
   `heartbeat_at`, progress, and errors.
4. If the service has already marked the run `EXPIRED`, keep recommendation at
   `HOLD` and inspect logs/artifacts.
5. If the run is still active but the lease is stale, use only the approved
   recovery path or let service recovery expire it.
6. Restart the service only if required for service health; restart is not
   proof that the run is safe.
7. Re-enable only after a fresh known state and complete telemetry are
   available.

Never delete run history to clear a stuck lease.

## Budget Exhaustion Response

Budget exhaustion is always fail-closed.

Signals:

1. status has an exhausted budget state;
2. `strategy_reoptimize_budget_exhausted_total{budget}` increases;
3. terminal status is `DEGRADED` or `FAILED`;
4. recommendation is `HOLD` or `OPERATOR_REVIEW_REQUIRED`.

Response:

1. Do not manually promote from partial run evidence.
2. Inspect progress, logs, and artifacts to identify the stopped work unit.
3. Compare host CPU and hot endpoint latency with the operator-captured
   baseline during Slice F.
4. Adjust budgets only through an operator-approved config change and canary.
5. Preserve the exhausted run as audit evidence.

## Missing Telemetry Or Unknown Status

Missing telemetry includes absent metrics, unreadable status rows, schema
validation failure, stale `heartbeat_at`, missing artifacts, unavailable logs,
or a status enum outside the contract.

Response:

1. Treat the runner state as unknown.
2. Do not enqueue scheduled mutation-producing work.
3. Keep latest maintenance/report decision at `HOLD`.
4. Emit or record `MISSING_TELEMETRY`, `UNKNOWN_STATUS`, or `STALE_STATUS` on
   the approved status/alert surface.
5. Restore observability first: status, logs, run rows, metrics, and artifacts.
6. Re-run status inspection before considering enablement or promotion review.

Unknown status is not a warning-only condition.

## Metrics And Alerts

Dashboards must render missing data as blocked, not green.

Use only bounded labels documented in
`docs/15-observability-and-alerting.md`. Do not use `run_id`, `pair_id`,
`operator_id`, `lease_owner`, hostnames, container ids, artifact paths, request
URLs, or free-form error text as metric labels. Put those values in structured
logs, status payloads, or artifacts.

Alert on:

1. stuck lease;
2. repeated `FAILED` or `DEGRADED` runs;
3. missed schedule while enabled;
4. budget exhaustion;
5. artifact failure or containment rejection;
6. cancellation failure or timeout;
7. unsafe promotion attempt;
8. missing telemetry;
9. unknown status.

Alert payloads may include the latest `run_id` as context, not as a metric
label.

## Artifact Evidence

Artifact evidence is required only when the consuming workflow declares it
required. Until artifact writing and download routes are implemented, missing
artifacts must stay fail-closed for workflows that require them.

When artifacts exist:

1. validate the manifest against
   `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`;
2. require paths to be relative to the artifact root;
3. reject parent traversal, absolute paths, unreadable files, partial
   manifests, and mismatched byte/count summaries;
4. compare artifact counts with status progress;
5. preserve artifacts as audit evidence.

Artifact inspection never substitutes for operator-only host verification.

## Slice F Readiness Checklist

Before asking the operator to approve Slice F, verify:

1. Slice D and Slice E are merged.
2. Async endpoints validate against the async contracts.
3. Async metrics are implemented with bounded labels only.
4. Status, logs, run rows, metrics, and artifacts agree for a completed
   non-production run, or artifact absence is explicitly fail-closed where
   artifacts are not implemented.
5. Missing telemetry and unknown status render as blocked.
6. Cancel behavior is authorized, audited, idempotent, and fail-closed before
   any mutating cancel route is exposed.
7. Stuck lease recovery preserves history and maps to `EXPIRED` or another
   bounded terminal state.
8. Budget exhaustion maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`.
9. `PROMOTION_CANDIDATE_AVAILABLE` is shown as review evidence only.
10. `RECANONICALIZED_LEGACY_ROW` remains repair-only and blocked from trade
    eligibility.
11. Host verification steps are assigned to the operator only.
12. A Slice F evidence manifest validates against
    `specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json`
    and passes `tools/scripts/slice_f_evidence_check.py`.

Readiness is not enablement. A passing readiness manifest can support an
operator review, but it does not authorize `STRATEGY_REOPT_WORKER_ENABLED`,
scheduler enablement, live `ENTRY` / `EXIT`, automatic `PROMOTE`, automatic
`REVERT`, or repair-provenance graduation.

## Operator-Only Host Capture For Slice F

For any future enablement or canary, the operator captures a bundle with a
root `slice_f_manifest.json` matching
`specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json`.
The bundle is evidence only.

1. host branch, commit, and dirty status;
2. deployed image or service identity;
3. runner and scheduler flag values before and after the window;
4. all budget env values;
5. proof live `ENTRY` and `EXIT` remain disabled;
6. proof promotion and revert remain manual and confirmation-gated;
7. operator-approved CPU threshold source/query/window/value;
8. operator-approved hot endpoint list, latency source/query/stat/window/value;
9. pre-run CPU and hot endpoint latency baseline;
10. current status endpoint payload;
11. status progression for the exact canary run if one is authorized;
12. artifact manifest and required artifacts when implemented;
13. `/metrics` output for implemented metrics only;
14. active alert configuration and active alerts before and after the run;
15. strategy logs before, during, and after the run, or disabled-state logs for
    readiness-only bundles;
16. selected-row inventory and Trade Now evidence proving every
    `RECANONICALIZED_LEGACY_ROW` remains blocked with
    `RECANONICALIZED_LEGACY_ROW_ACTIVE`;
17. post-run CPU and hot endpoint latency comparison if a canary ran.

The required strategy log evidence must show useful async reoptimization event
names such as `reoptimize_run_enqueue_attempted`,
`reoptimize_run_enqueued`, `reoptimize_lease_acquired`,
`reoptimize_lease_heartbeat`, `reoptimize_budget_exhausted`,
`reoptimize_recommendation_finalized`, or `reoptimize_fail_closed`. Generic
service logs are not sufficient.

Validate the captured manifest from the repository root:

```bash
python3 tools/scripts/slice_f_evidence_check.py path/to/slice_f_manifest.json
```

If the bundle includes referenced artifact files, verify file containment and
hashes:

```bash
python3 tools/scripts/slice_f_evidence_check.py \
  path/to/slice_f_manifest.json \
  --bundle-root path/to/bundle-root \
  --verify-files
```

If host evidence is missing, stale, or contradictory, keep the runner disabled
and keep recommendations at `HOLD`.

Hard stop conditions include missing alert routing, missing CPU or hot endpoint
threshold approval, weak strategy logs, unknown or schema-invalid status,
nonzero active async gauges before approval, live `ENTRY` / `EXIT` evidence
missing, automatic `PROMOTE` / `REVERT` evidence, or any
`RECANONICALIZED_LEGACY_ROW` becoming trade eligible.

## Related Sources

- `docs/proposals/reoptimise-background-runner-redesign.md`
- `docs/proposals/reoptimise-api-script-migration-plan.md`
- `docs/proposals/reoptimise-observability-runbook-plan.md`
- `docs/proposals/reoptimise-slice-f-canary-hardening.md`
- `docs/15-observability-and-alerting.md`
- `docs/playbooks/hosted-deployment-runbook.md`
- `docs/playbooks/observability-slo-runbook.md`
- `docs/playbooks/strategy-maintenance-automation-runbook.md`
- `specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json`
- `specs/contracts/strategy_reoptimize_run_enqueue_response.schema.json`
- `specs/contracts/strategy_reoptimize_run_status_response.schema.json`
- `specs/contracts/strategy_reoptimize_run_cancel_response.schema.json`
- `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`
