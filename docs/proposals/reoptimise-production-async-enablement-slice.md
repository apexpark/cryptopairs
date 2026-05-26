# Proposal: Production async reoptimization enablement slice

> **Status**: proposed follow-up slice after completed Slice F evidence
> acceptance. This document does not enable worker drain, scheduled enqueue,
> live `ENTRY` / `EXIT`, automatic `PROMOTE` / `REVERT`, or repair-provenance
> graduation.
>
> **Item addressed**: create the production async enablement slice without
> treating the accepted Slice F bounded manual evidence packet as authorization
> for unattended scheduled production operation.

---

## 1. Scope

Slice F proved that a bounded, operator-approved manual async reoptimization
window can be captured and validated while runtime returns to disabled state.
Production async enablement is a separate slice because it introduces a new
risk surface: unattended scheduled enqueue.

This slice defines the work required before any production scheduler window:

1. evidence contract/tooling for an explicitly enabled scheduler window;
2. operator approval inputs for scope, budgets, abort rules, rollback owner,
   and evidence owner;
3. a first scheduled-canary procedure that proves scheduler lifecycle,
   artifacts, logs, metrics, alerts, and rollback;
4. steady-state ramp criteria after the first scheduled canary passes.

It does not authorize:

1. setting `STRATEGY_REOPT_WORKER_ENABLED=true` in production;
2. setting `STRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED=true` in production;
3. enabling live `ENTRY` or `EXIT`;
4. creating automatic `PROMOTE` or automatic `REVERT`;
5. exposing public mutating cancellation or artifact download routes;
6. graduating `RECANONICALIZED_LEGACY_ROW` or other repair-only provenance;
7. host SSH or host verification by agents.

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
8. `docs/proposals/reoptimise-slice-f-canary-hardening.md`;
9. `docs/12-risk-and-execution-policy.md`;
10. `docs/15-observability-and-alerting.md`;
11. `specs/contracts/slice_f_reoptimize_canary_evidence_manifest.schema.json`;
12. `specs/contracts/strategy_reoptimize_run_artifact_manifest.schema.json`;
13. `specs/contracts/strategy_reoptimize_run_enqueue_response.schema.json`;
14. `specs/contracts/strategy_reoptimize_run_status_response.schema.json`;
15. `tools/scripts/slice_f_evidence_manifest_from_bundle.py`;
16. `tools/scripts/slice_f_evidence_check.py`;
17. `services/strategy-service/src/main.rs`.

## 3. Slice Boundaries

### PAE-A: Production enablement evidence contract and checker

Create a separate production async enablement evidence packet, or a clearly
versioned checker mode, that models three phases:

1. `before`: worker and scheduler disabled, active gauges zero, safety gates
   captured;
2. `during`: worker and scheduler enabled only inside the approved window,
   exactly one expected scheduled lifecycle is observed unless the approval
   names a different count;
3. `after`: worker and scheduler disabled again, active gauges zero, no new
   scheduled enqueue after rollback.

Do not relax the Slice F checker to pass an enabled scheduler. Slice F remains
the completed bounded manual evidence gate; production enablement needs its own
evidence semantics.

Acceptance criteria:

1. schema-valid pass and fail examples cover before/during/after evidence;
2. missing or contradictory evidence returns `KEEP_DISABLED_KEEP_HOLD`;
3. `artifact_manifest` validation is mandatory for enabled-window success;
4. status, request artifact, summary artifact, and artifact manifest agree on
   `trigger_source=SCHEDULED` and the approved `requested_timeframes`;
5. generator/checker tests reject manual/scheduled contamination, enabled
   flags outside the approved window, nonzero after gauges, missing logs,
   missing alerts, missing artifacts, and any non-success terminal state.

### PAE-B: Request/config fingerprint and service-version evidence

Graduate nullable evidence fields that are currently compatibility placeholders
into deterministic scheduler evidence before steady-state production use:

1. request/config fingerprint for the reoptimization request, budget snapshot,
   timeframe scope, and pair universe;
2. service version or build identity for status payloads and artifacts;
3. reconciliation between status payload, DB run row, request artifact, summary
   artifact, and artifact manifest.

Acceptance criteria:

1. fingerprints are deterministic and exclude volatile fields;
2. missing or mismatched fingerprints fail closed for production enablement;
3. `latest-successful` consumers can distinguish compatible evidence from a
   stale or incompatible run without trusting null identity fields.

### PAE-C: First scheduled canary procedure

After PAE-A is merged and explicitly approved by the operator, run one bounded
scheduled canary window.

Required approval fields:

1. exact timeframe scope;
2. exact pair set or approved pair filter;
3. scheduler cadence and start window;
4. run wall-clock and timeframe wall-clock budgets;
5. pair count, pair concurrency, DB batch, artifact byte, cooldown, lease TTL,
   and heartbeat budgets;
6. success threshold;
7. abort rule;
8. rollback owner;
9. host evidence owner;
10. alert/threshold evidence owner.

The canary must begin disabled, enable only the approved flags for the
approved window, then return to disabled state before the evidence packet can
pass.

Acceptance criteria:

1. exactly the approved scheduled run count is enqueued;
2. no manual run contaminates scheduled evidence;
3. lifecycle progresses through queued/leased or running/terminal states with
   no stuck lease;
4. terminal status is `SUCCEEDED`, `WITHIN_BUDGET`, and has no fail-closed
   reasons;
5. required artifacts exist, are path-contained, and hash-verify;
6. logs include scheduler enqueue, lease acquire, heartbeat or progress, and
   final recommendation events;
7. metrics show bounded active-run lifecycle and zero active gauges after
   rollback;
8. alerting is deployed, routed, queryable, captures before/during/after
   state, and treats missing data as blocked;
9. live `ENTRY` / `EXIT`, automatic `PROMOTE` / `REVERT`, and repair
   provenance graduation remain blocked.

### PAE-D: Steady-state ramp criteria

Only after PAE-C passes may a separate operator decision consider steady-state
scheduling.

Ramp criteria:

1. at least one passing scheduled canary bundle validates with the production
   enablement checker;
2. no unresolved alert, missing telemetry, stale status, budget exhaustion,
   lease anomaly, artifact failure, or scope mismatch remains open;
3. rollback has been proven from enabled state back to disabled state;
4. retention and artifact access policy are explicit;
5. ongoing scheduler cadence, budgets, and alert ownership are named.

Steady-state enablement is not automatic. It remains an operator decision.

## 4. Fail-Closed Rules

Any of these outcomes keeps `STRATEGY_REOPT_WORKER_ENABLED=false`,
`STRATEGY_REOPT_SCHEDULER_ENQUEUE_ENABLED=false`, and downstream
recommendations at `HOLD` or `OPERATOR_REVIEW_REQUIRED`:

1. operator approval is missing, stale, or narrower than observed behavior;
2. host identity, service identity, flags, budgets, metrics, alerts, logs,
   status, run rows, or artifacts are missing or contradictory;
3. live `ENTRY` or `EXIT` is enabled;
4. automatic `PROMOTE` or automatic `REVERT` is enabled;
5. repair-only provenance becomes trade-eligible;
6. scheduled enqueue occurs outside the approved window;
7. manual and scheduled evidence are mixed in one canary verdict;
8. final run status is `DEGRADED`, `FAILED`, `EXPIRED`, `CANCELED`,
   `CANCEL_REQUESTED`, `LEASED`, `RUNNING`, `QUEUED`, stale, or unknown;
9. budget state is not `WITHIN_BUDGET`;
10. artifact manifest is missing, schema-invalid, hash-invalid, path-escaping,
    partial, or scope-mismatched;
11. active gauges are nonzero after rollback;
12. scheduler continues enqueuing after rollback;
13. CPU or hot endpoint latency exceeds approved thresholds;
14. alerting is missing, unrouted, unqueryable, or treats missing data as
    healthy.

## 5. Evidence Packet Requirements

A production enablement evidence packet must include distinct artifacts for
the before, during, and after phases. At minimum:

1. host repository identity and dirty status;
2. deployed service identity;
3. strategy-service flags and budgets before, during, and after;
4. execution-service live `ENTRY` / `EXIT` disable proof;
5. promotion and revert confirmation-gating probes;
6. repair-provenance inventory and Trade Now block evidence;
7. operator threshold approval artifact;
8. CPU and hot endpoint baseline/during/after captures;
9. alert configuration, routing, active-state, and missing-data behavior
   before/during/after;
10. status progression for the exact scheduled run;
11. DB run row evidence for trigger source, requested timeframes, terminal
    status, budgets, and artifact manifest persistence;
12. strategy logs before/during/after with useful async event names;
13. Prometheus metrics before/during/after;
14. artifact manifest plus required artifact files;
15. post-rollback proof that worker and scheduler are disabled, active gauges
    are zero, and no new scheduled run was enqueued.

Host capture remains operator-only. Repo agents validate operator-provided
bundles locally; they do not SSH to `cryptopairs` and do not claim runtime
state from repo artifacts alone.

## 6. Observability Requirements

The enabled-window packet must prove these bounded-label metric and log
surfaces are usable:

1. scheduler enqueue attempts and results;
2. active runs by bounded status;
3. run lifecycle terminal counts by bounded trigger/status labels;
4. lease acquire, heartbeat, loss, and expiry;
5. budget exhaustion by bounded budget label;
6. missing telemetry and unknown status reasons;
7. artifact write/manifest failures;
8. terminal recommendation decisions;
9. alert state for stuck lease, failed/degraded runs, missed schedule, budget
   exhaustion, cancellation failure, missing telemetry, unknown status, unsafe
   promotion, and repair provenance active.

`run_id`, hostnames, container ids, artifact paths, URLs, pair ids, lease
owners, and free-form error messages remain in logs, status payloads, DB rows,
or artifacts only. They must not become metric labels.

## 7. Test Plan

PAE-A must ship with tests before any operator scheduled canary:

1. schema validation for new or versioned evidence manifest examples;
2. checker tests for passing before/during/after evidence;
3. checker tests rejecting missing during lifecycle, enabled-before evidence,
   scheduler-after-disable evidence, nonzero after gauges, missing artifact
   manifest, manual/scheduled scope mismatch, and weak logs;
4. generator fixture tests for raw bundles with distinct before/during/after
   artifacts;
5. focused Rust tests for scheduler gate behavior, worker-drain separation,
   trigger/timeframe persistence, and artifact/status scope agreement;
6. Postgres-backed repository integration coverage where
   `STRATEGY_TEST_DATABASE_URL` is available, with local self-skip reported
   exactly when it is unset.

## 8. Versioning

This proposal is docs-only and does not change runtime behavior, public API
schemas, env defaults, metric labels, or compatibility guarantees.

Future PAE-A contract or checker work must update `CHANGELOG.md`, add or bump
the relevant evidence schema/examples, and document migration semantics. Any
runtime env/default change requires a separate versioning assessment and
operator approval.

## 9. Open Decisions

Operator decisions still required before any scheduled production window:

1. first scheduled timeframe scope;
2. first scheduled pair scope;
3. scheduler cadence and enabled-window duration;
4. pass threshold: one clean scheduled run or multiple clean runs;
5. abort threshold for repeated non-success runs;
6. artifact retention and access/download policy;
7. cancellation authority and audit boundary;
8. steady-state alert owner and escalation route;
9. whether request/config fingerprint graduation blocks the first scheduled
   canary or only steady-state enablement.
