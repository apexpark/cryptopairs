# Proposal: Slice F reoptimization canary hardening

> **Status**: docs-only hardening proposal. No code, config, schema, script,
> scheduler, runner, live execution, promotion, revert, or host-runtime change.
>
> **Item addressed**: Slice F follow-up after local evidence review found
> missing alerting surface, unapproved CPU/hot endpoint thresholds, weak
> strategy log evidence, and missing repair-provenance evidence.

---

## 1. Scope

This proposal defines the evidence gate for a future operator-only Slice F
production canary of the bounded async reoptimization runner.

It does not:

1. enable `STRATEGY_REOPT_WORKER_ENABLED`;
2. enable any production scheduler;
3. enable live `ENTRY` or `EXIT`;
4. create automatic `PROMOTE`;
5. create automatic `REVERT`;
6. expose new cancellation, artifact download, or UI controls;
7. graduate `RECANONICALIZED_LEGACY_ROW` or other repair-only provenance;
8. authorize host SSH or host verification by agents;
9. define numeric CPU or latency thresholds.

If this document conflicts with `AGENTS.md`, `AGENTS.md` wins.

## 2. Verified Sources

Repository sources consulted before writing:

1. `AGENTS.md`;
2. `docs/AGENT_STATE.md`;
3. `docs/playbooks/remote-agent-bootstrap.md`;
4. `docs/playbooks/reoptimise-runner-agent-brief.md`;
5. `docs/playbooks/async-reoptimization-runner-runbook.md`;
6. `docs/proposals/reoptimise-background-runner-redesign.md`;
7. `docs/proposals/reoptimise-observability-runbook-plan.md`;
8. `docs/proposals/reoptimise-api-script-migration-plan.md`;
9. `docs/proposals/SLICE-D-recanonicalize-legacy-rows.md`;
10. `docs/03-contracts-and-compatibility.md`;
11. `docs/12-risk-and-execution-policy.md`;
12. `docs/14-testing-standards.md`;
13. `docs/15-observability-and-alerting.md`;
14. `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`;
15. `specs/contracts/strategy_reoptimize_run_cancel_response.schema.json`;
16. `specs/contracts/strategy_reoptimize_run_enqueue_response.schema.json`;
17. `specs/contracts/strategy_reoptimize_run_status_response.schema.json`;
18. `specs/examples/strategy_reoptimize_run_artifact_manifest.example.json`;
19. `specs/examples/strategy_reoptimize_run_cancel_response.example.json`;
20. `specs/examples/strategy_reoptimize_run_enqueue_response.example.json`;
21. `specs/examples/strategy_reoptimize_run_status_response.example.json`;
22. `services/strategy-service/src/main.rs` for implemented async
    reoptimization metric/log names and `RECANONICALIZED_LEGACY_ROW_ACTIVE`
    Trade Now blocking behavior.

## 3. Pre-Canary Readiness Gate

Slice F must not start unless every readiness gate is `PASS` in the evidence
manifest described in section 8.

Required readiness gates:

1. operator approval identifies the exact canary scope, target timeframe,
   start window, abort owner, rollback owner, and host evidence owner;
2. host identity capture is assigned to the operator and not claimed by an
   agent;
3. runner and scheduler state are captured before any canary and prove no
   unapproved mutation-producing async run is active;
4. alerting surface is configured, routed, and captures missing data as
   blocked rather than green;
5. CPU and hot endpoint latency thresholds are operator-approved before the
   canary starts;
6. strategy log capture has useful async reoptimization events or explicit
   disabled-state evidence;
7. status endpoint payloads validate against the async run contracts;
8. `/metrics` contains the implemented async reoptimization metrics with
   bounded labels only;
9. live `ENTRY` and `EXIT` remain disabled under
   `docs/12-risk-and-execution-policy.md`;
10. promotion and revert remain manual and confirmation-gated;
11. repair-only provenance remains blocked from trade eligibility.

Any `FAIL`, missing value, stale value, contradictory value, or unchecked
operator approval keeps the runner disabled and keeps downstream
recommendations at `HOLD`.

## 4. Alerting Readiness Requirements

Before any canary, the evidence bundle must prove an alerting surface exists.
Raw metric output alone is not alerting readiness.

The manifest must capture:

1. alert rules or equivalent alert queries for the implemented async
   reoptimization metrics in `docs/15-observability-and-alerting.md`;
2. routing destination or operator notification path;
3. dashboard or alert inspection path;
4. pre-canary active alert state;
5. post-canary active alert state;
6. proof that missing series, unreadable status, stale status, and unknown
   status render as blocked;
7. proof that alert payloads can include latest `run_id` as context without
   using it as a metric label.

Minimum alert coverage:

| Gate | Required signal |
|---|---|
| Stuck lease | `strategy_reoptimize_active_runs{status}` plus lease heartbeat/status evidence |
| Repeated failed/degraded runs | `strategy_reoptimize_run_total{trigger,status}` terminal `FAILED` or `DEGRADED` |
| Schedule missed while enabled | `strategy_reoptimize_scheduler_enqueue_total{trigger,result}` or documented missed-schedule counter if later added |
| Budget exhaustion | `strategy_reoptimize_budget_exhausted_total{budget}` |
| Cancellation failure or timeout | `strategy_reoptimize_cancel_total{result}` with `FAILED` or `TIMED_OUT` |
| Missing telemetry | `strategy_reoptimize_telemetry_missing_total{reason}` |
| Unknown status | `strategy_reoptimize_status_unknown_total{reason}` |
| Unsafe promotion attempt | `strategy_reoptimize_fail_closed_total{reason="UNSAFE_PROMOTION_ATTEMPT"}` and any implemented unsafe-promotion metric |
| Repair provenance active | `strategy_reoptimize_fail_closed_total{reason="REPAIR_PROVENANCE_ACTIVE"}` or the Trade Now blocked evidence in section 7 |

Pass semantics:

1. `PASS`: every required alert is configured, routable, and has a captured
   before/after state.
2. `FAIL`: any required alert is missing, unrouted, unqueryable, stale,
   contradictory, or treats missing data as healthy.
3. `NOT_APPLICABLE`: allowed only for a metric surface explicitly not
   implemented in the current code, and only if the canary does not rely on
   that surface. `NOT_APPLICABLE` on missing telemetry, unknown status, stuck
   lease, budget exhaustion, live execution, promotion, revert, or repair
   provenance is a canary stop.

## 5. CPU And Hot Endpoint Threshold Approval

This document does not choose numeric thresholds. Numeric thresholds are
operator decisions.

Before any canary, the manifest must capture operator-approved thresholds:

1. CPU metric source and query;
2. CPU aggregation window;
3. CPU baseline window;
4. CPU maximum absolute threshold or maximum relative increase;
5. hot endpoint list with method and path;
6. latency metric source and query for every hot endpoint;
7. latency statistic for each endpoint, such as p95 or p99;
8. latency baseline window;
9. latency maximum absolute threshold or maximum relative increase;
10. abort rule when any threshold is exceeded.

The hot endpoint list must be explicit in the manifest. It must not rely on
phrases such as "all important endpoints" or "normal strategy endpoints."

Pass semantics:

1. `PASS`: thresholds were approved before canary start, baseline samples are
   present, post-run samples are present, and every measured value is within
   the approved threshold.
2. `FAIL`: thresholds are missing, approved after the run, missing baseline,
   missing post-run sample, use an unnamed endpoint, or breach any approved
   threshold.

If CPU or latency threshold evidence is `FAIL`, keep the runner disabled and
keep maintenance/report recommendations at `HOLD`.

## 6. Strategy Log Evidence Requirements

`strategy_logs_before`, `strategy_logs_during`, and `strategy_logs_after`
must be useful enough to reconstruct the async reoptimization timeline.
Presence of generic service logs is not sufficient.

Every log file must include:

1. log source name;
2. capture command or query;
3. capture start and end timestamps;
4. service/container identity if available;
5. timezone or UTC statement;
6. a statement of whether debug-level records were included.

Required useful log content:

| Evidence file | Required content |
|---|---|
| `strategy_logs_before` | Explicit disabled-state evidence such as `strategy reoptimize worker disabled`, or a statement that no service restart occurred in the capture window plus status/metrics evidence proving disabled state. Absence of reoptimize logs alone is `FAIL`. |
| `strategy_logs_during` | For any canary run, a coherent sequence using implemented event names: enqueue attempt/result, lease acquisition, heartbeat or status heartbeat evidence, pair/timeframe progress or budget stop, terminal recommendation, and any fail-closed event. |
| `strategy_logs_after` | Terminal or disabled-state evidence after the canary, including no unexpected follow-up enqueue and no automatic promotion/revert action. |

Implemented async reoptimization event names that may satisfy the timeline:

1. `reoptimize_run_enqueue_attempted`;
2. `reoptimize_run_enqueued`;
3. `reoptimize_run_enqueue_rejected`;
4. `reoptimize_lease_acquired`;
5. `reoptimize_lease_heartbeat`;
6. `reoptimize_lease_lost`;
7. `reoptimize_budget_exhausted`;
8. `reoptimize_cancel_observed`;
9. `reoptimize_recommendation_finalized`;
10. `reoptimize_fail_closed`.

Required fields when an event is present:

| Event | Required fields |
|---|---|
| `reoptimize_run_enqueue_attempted` | `trigger_source` |
| `reoptimize_run_enqueued` | `run_id`, `trigger_source`, `status_after` |
| `reoptimize_run_enqueue_rejected` | `trigger_source`, `status_after`, `fail_closed_reason` when present |
| `reoptimize_lease_acquired` | `run_id`, `lease_owner`, `lease_generation`, `lease_expires_at`, `status_after` |
| `reoptimize_lease_heartbeat` | `run_id`, `lease_owner`, `lease_generation`, `heartbeat_at`, `status_after`, `phase` |
| `reoptimize_lease_lost` | `run_id`, `reason`; include `lease_owner` and `lease_generation` when present |
| `reoptimize_budget_exhausted` | `run_id`, `budget_name`, `context`; include `timeframe` when present |
| `reoptimize_cancel_observed` | `run_id`, `status_after` |
| `reoptimize_recommendation_finalized` | `run_id`, `status_after`, `recommendation`, `fail_closed_reasons`, pair/error counts |
| `reoptimize_fail_closed` | `fail_closed_reason`; include `run_id` when present |

Pass semantics:

1. `PASS`: logs show the required timeline for the approved canary scope, or
   for a disabled/no-canary bundle they prove disabled state with matching
   status/metrics evidence.
2. `FAIL`: logs are absent, unrelated, outside the window, lack implemented
   event names, lack required fields, contradict status/metrics, or omit
   fail-closed events when status/metrics indicate fail-closed behavior.

If log evidence is `FAIL`, keep the runner disabled and keep recommendations
at `HOLD`.

## 7. Repair-Provenance Evidence Requirements

Slice F evidence must prove that `RECANONICALIZED_LEGACY_ROW` remains
repair-only and blocked from trade eligibility.

Required evidence:

1. selected-row inventory grouped by `source` and `timeframe`, including any
   `RECANONICALIZED_LEGACY_ROW` rows;
2. Trade Now response or equivalent operator-captured surface showing every
   recanonicalized row is outside `tradable_now`;
3. for every recanonicalized row, `decision_bucket` is `EXCLUDED` or an
   equivalent non-tradable bucket;
4. for every recanonicalized row, `decision_reason_code` is
   `PROVENANCE_POLICY_BLOCKED`;
5. for every recanonicalized row, `blocked_reason_code` is
   `RECANONICALIZED_LEGACY_ROW_ACTIVE`;
6. for every recanonicalized row, `rationale_codes` includes
   `RECANONICALIZED_LEGACY_ROW_ACTIVE`;
7. no row with selected config source `RECANONICALIZED_LEGACY_ROW` appears as
   live trade eligible;
8. no async reoptimization recommendation, report, artifact, or log states
   that repair-only provenance was graduated to `AUTO_CHAMPION` or another
   non-repair source;
9. any async runner fail-closed reason related to repair provenance remains
   `REPAIR_PROVENANCE_ACTIVE` and maps to `HOLD` or
   `OPERATOR_REVIEW_REQUIRED`;
10. live `ENTRY` and `EXIT` disabled evidence remains present.

Pass semantics:

1. `PASS`: every recanonicalized row is present in evidence and blocked as
   repair-only with the exact reason codes above.
   If the current inventory has zero `RECANONICALIZED_LEGACY_ROW` rows, `PASS`
   is allowed only when the bundle explicitly captures a selected-row inventory
   with count `0` plus Trade Now or equivalent evidence showing no
   recanonicalized row is trade eligible. Missing inventory is not the same as
   a zero-row inventory.
2. `FAIL`: repair-provenance evidence is missing; any recanonicalized row is
   absent from the audit; any recanonicalized row is tradable, watchlisted as
   execution-ready, promoted, or graduated; reason codes are missing or
   contradictory; or live execution evidence is missing.

If repair-provenance evidence is `FAIL`, keep the runner disabled and keep
recommendations at `HOLD`.

## 8. Machine-Checkable Evidence Bundle Manifest

Every Slice F evidence bundle includes a root `slice_f_manifest.json` plus
referenced artifacts. The manifest validates against
`specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json` and
then must pass the semantic checker in
`tools/scripts/slice_f_evidence_check.py`.

If an operator bundle contains raw artifacts but no manifest, normalize it
locally with:

```bash
python3 tools/scripts/slice_f_evidence_manifest_from_bundle.py \
  path/to/operator-captured-bundle
```

The generator only reads local operator-captured files. It does not contact the
host and does not claim host verification. It emits fail-closed stop conditions
for dirty repo identity, missing alerting, missing thresholds, weak logs,
unknown or non-success status, nonzero fail-closed metric deltas, missing
safety proof, missing repair-provenance proof, and missing required artifacts.

Required top-level fields:

```json
{
  "schema_version": "1.0.0",
  "bundle_id": "slice-f-<timestamp>",
  "generated_at": "<UTC timestamp>",
  "canary_authorized": false,
  "overall_pass": false,
  "recommended_action": "KEEP_DISABLED_KEEP_HOLD",
  "operator_approval": {
    "present": false,
    "reference": null,
    "host_evidence_owner": "operator"
  },
  "repo_identity": {
    "branch": "<operator-captured>",
    "commit": "<operator-captured>",
    "dirty_status": "<operator-captured>",
    "captured_by": "operator"
  },
  "canary_scope": {
    "timeframes": [],
    "trigger_source": null,
    "runner_enabled_before": false,
    "scheduler_enabled_before": false,
    "runner_enabled_after": false,
    "scheduler_enabled_after": false
  },
  "alerting": {},
  "thresholds": {
    "approved_before_canary": false,
    "cpu": {},
    "hot_endpoints": []
  },
  "logs": {},
  "status_payloads": [],
  "metrics": {},
  "safety": {},
  "repair_provenance": {},
  "artifacts": [],
  "checks": [],
  "stop_conditions": []
}
```

Required `artifacts[]` fields:

```json
{
  "id": "strategy_logs_before",
  "path": "relative/path/inside/bundle",
  "kind": "LOG",
  "required": true,
  "sha256": "<64 hex chars>",
  "captured_at": "<UTC timestamp>"
}
```

Required artifact ids:

| Artifact id | Required for |
|---|---|
| `repo_identity` | every bundle |
| `operator_approval` | any canary bundle |
| `runner_flags_before` | every bundle |
| `runner_flags_after` | any canary bundle |
| `budget_values` | any canary bundle |
| `status_before` | every bundle |
| `status_progression` | any canary bundle |
| `status_after` | any canary bundle |
| `metrics_before` | every bundle |
| `metrics_during` | any canary bundle |
| `metrics_after` | any canary bundle |
| `alerts_config` | every readiness or canary bundle |
| `alerts_before` | every readiness or canary bundle |
| `alerts_after` | any canary bundle |
| `strategy_logs_before` | every bundle |
| `strategy_logs_during` | any canary bundle |
| `strategy_logs_after` | any canary bundle |
| `cpu_baseline` | every readiness or canary bundle |
| `cpu_during_after` | any canary bundle |
| `hot_endpoint_latency_baseline` | every readiness or canary bundle |
| `hot_endpoint_latency_after` | any canary bundle |
| `artifact_manifest` | any canary bundle that claims run artifacts |
| `repair_provenance_inventory` | every Slice F readiness or canary bundle |
| `trade_now_repair_provenance_block` | every Slice F readiness or canary bundle |
| `entry_exit_disabled` | every bundle |
| `promotion_revert_gating` | every bundle |

Required `checks[]` fields:

```json
{
  "id": "alerting_ready",
  "status": "PASS",
  "evidence_artifact_ids": ["alerts_config", "alerts_before"],
  "failure_reason": null
}
```

Allowed check statuses:

1. `PASS`;
2. `FAIL`;
3. `NOT_APPLICABLE`.

`NOT_APPLICABLE` is not allowed for these checks:

1. `operator_approval_present` for any canary bundle;
2. `alerting_ready`;
3. `thresholds_approved`;
4. `strategy_logs_useful`;
5. `status_contract_valid`;
6. `metrics_bounded_and_present`;
7. `entry_exit_disabled`;
8. `promotion_revert_confirm_gated`;
9. `repair_provenance_blocked`;
10. `stop_conditions_absent`.

Required checks:

| Check id | Pass condition |
|---|---|
| `operator_approval_present` | Operator approval exists before any canary and names scope, thresholds, owners, and abort rule. |
| `alerting_ready` | Section 4 passes. |
| `thresholds_approved` | Section 5 passes. |
| `strategy_logs_useful` | Section 6 passes. |
| `status_contract_valid` | Status/enqueue/cancel/artifact payloads validate against the relevant `strategy_reoptimize_run_*` contract when present. |
| `metrics_bounded_and_present` | Implemented async metrics are present with bounded labels only. |
| `active_async_gauges_zero_before` | Before approval, active async gauges are zero or the active state is explicitly fail-closed and operator-approved for recovery. |
| `status_progression_known` | Any run progression uses only contract statuses: `QUEUED`, `LEASED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELED`, `SUCCEEDED`, `DEGRADED`, `FAILED`, `EXPIRED`. |
| `recommendation_safe` | Recommendations use only contract values and any non-success, unknown, stale, invalid, or contradictory state maps to `HOLD` or `OPERATOR_REVIEW_REQUIRED`. |
| `entry_exit_disabled` | Live `ENTRY` and `EXIT` disabled evidence exists. |
| `promotion_revert_confirm_gated` | No automatic `PROMOTE` or `REVERT`; any action path requires explicit confirmation. |
| `repair_provenance_blocked` | Section 7 passes. |
| `cpu_within_threshold` | Approved CPU threshold evidence passes. |
| `hot_endpoint_latency_within_threshold` | Approved hot endpoint latency evidence passes. |
| `artifact_evidence_valid` | Artifact manifest is present, path-contained, complete, and consistent when artifacts are claimed or required. |
| `stop_conditions_absent` | No stop condition in section 9 is present. |

Bundle-level pass/fail:

1. A readiness bundle can pass only if all readiness checks are `PASS` and
   `canary_authorized` is `false`.
2. A canary bundle can pass only if all required checks are `PASS` and
   `canary_authorized` is `true`.
3. Any `FAIL` means the bundle fails.
4. Any missing required artifact means the related check is `FAIL`.
5. Any stale or contradictory artifact means the related check is `FAIL`.
6. Any unknown status or schema-invalid payload means the related check is
   `FAIL` and recommendation must be `HOLD`.

## 9. Explicit Stop Conditions

The runner stays disabled and recommendations stay `HOLD` when any condition
below is true:

1. operator approval for Slice F is missing, stale, or narrower than the
   attempted canary;
2. alerting readiness is `FAIL`;
3. CPU threshold approval or evidence is `FAIL`;
4. hot endpoint latency threshold approval or evidence is `FAIL`;
5. strategy logs are missing, generic-only, outside the window, or
   contradictory;
6. status payload is schema-invalid or has an unknown status;
7. status is `QUEUED`, `LEASED`, `RUNNING`, or `CANCEL_REQUESTED` after the
   allowed window;
8. terminal status is `CANCELED`, `DEGRADED`, `FAILED`, or `EXPIRED`;
9. budget state is `UNKNOWN` or `EXHAUSTED`;
10. lease ownership, generation, or heartbeat cannot be proven;
11. `strategy_reoptimize_telemetry_missing_total` or
    `strategy_reoptimize_status_unknown_total` increases for the canary
    window;
12. any required artifact manifest is missing, partial, unreadable, or path-
    containment rejected;
13. active async run gauges are nonzero before approval without an explicit
    operator recovery plan;
14. live `ENTRY` or `EXIT` disabled evidence is missing;
15. any automatic `PROMOTE` or `REVERT` path is observed or cannot be ruled
    out;
16. any `RECANONICALIZED_LEGACY_ROW` is trade eligible, promoted, graduated,
    missing from the repair-provenance audit, or not blocked with
    `RECANONICALIZED_LEGACY_ROW_ACTIVE`;
17. repair-provenance evidence is missing;
18. host identity is missing, dirty state is unknown, or deployed identity is
    contradictory;
19. evidence bundle manifest is missing, not parseable, or has any required
    check at `FAIL`;
20. an agent, rather than the operator, is the source of host verification.

Stop-condition handling:

1. keep `STRATEGY_REOPT_WORKER_ENABLED=false`;
2. keep scheduler enablement disabled;
3. keep live `ENTRY` and `EXIT` disabled;
4. preserve existing run rows, metrics, logs, and artifacts;
5. mark maintenance/report output as `HOLD` or
   `OPERATOR_REVIEW_REQUIRED`;
6. require a fresh operator-approved evidence bundle before reconsidering.

Validate a captured bundle:

```bash
python3 tools/scripts/slice_f_evidence_check.py path/to/slice_f_manifest.json
```

Validate referenced files and hashes when the bundle is available on disk:

```bash
python3 tools/scripts/slice_f_evidence_check.py \
  path/to/slice_f_manifest.json \
  --bundle-root path/to/bundle-root \
  --verify-files
```

## 10. Test Plan

This follow-up requires:

1. `git diff --check`;
2. JSON syntax validation for the new manifest contract and examples;
3. schema validation for the pass/fail/zero-row manifest examples;
4. semantic validation proving the pass and zero-row examples exit `0` and the
   fail example exits nonzero;
5. unit coverage for dirty repo identity, unknown status, runner enablement,
   alert template coverage, and raw-bundle fail-closed manifest generation.

Future extensions to the manifest contract should add:

1. additional pass and fail examples under `specs/examples/`;
2. schema validation for every example;
3. fixture tests covering missing alerting, missing thresholds, weak logs,
   missing repair-provenance evidence, unknown status, and repair-provenance
   graduation attempts.

## 11. Versioning

This follow-up changes docs, adds a machine-readable evidence manifest
contract, adds pass/fail examples, and adds a local validation script. It does
not change public service behavior, metric names, metric labels, config keys,
runtime defaults, or operator enablement procedure.

Because a contract and operator-facing checker are added, record the change in
`CHANGELOG.md`. No runtime version bump is required unless release metadata is
updated for docs/spec additions elsewhere in the release process.
