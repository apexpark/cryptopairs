# AUTO-2D bounded dynamic paper controller runbook

## Status and authority

This runbook covers the disabled-by-default AUTO-2D paper-only controller at
`tools/scripts/autopilot_dynamic_paper_controller_v2.py`.

The controller may automatically accept only an exact AUTO-2C v2 decision with
status `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` after independently
reconstructing the whole decision from its raw, exact-hash inputs. It is not
the governor approving itself: the controller does not import or invoke the v2
governor or the test auditor.

The controller has no live-order, exchange-routing, execution-service POST,
deployment, service-configuration or automatic-restart authority. A successful
read-only verification is not start authority. Starting one paper trial
requires a separate exact Operator authorization after genuine E3, independent
review, merge and fresh host preflight.

The controller independently supports two exact policy versions. The
historical `auto2c-v2-paper-automatic-acceptance-1` route retains its static
removal and churn gates. The explicit
`auto2c-v2-first-bounded-paper-experiment-1` route accepts static overlap only
as bound reference evidence: removal and churn are recomputed and reported but
do not gate the isolated experiment. Every other qualification, ranking,
addition, exploration, concentration, freshness and integrity rule remains
enforced independently.

## Fixed policy envelope

- Paper only; no live orders or exchange routing.
- 60-second monotonic cadence.
- At most four immutable exact pair/variant/direction keys.
- At most two open positions globally.
- At most one open position per exact key, pair and full instrument.
- At most one open selector-exploration position.
- Five one-minute bars per holding window.
- 300-second exact-key cooldown.
- 120-second maximum candidate age.
- The decision must be no more than 300 seconds old at controller start.
- 86,400-second entry window followed by 3,600 seconds of exit-only grace.
- 90,000-second hard runtime.
- No fallback, root reuse, restart, repair, cleanup or alternate universe.
- The first-experiment universe exists only in the newly created
  controller-owned root and never mutates shared paper configuration.
- Trial evidence grants no subsequent paper or live promotion; a separate
  policy decision is required.

`direction_hint: "NONE"` and a missing/null direction remain distinct and
non-actionable. Neither can enter the immutable universe. Any other unknown
selector direction refuses the input. Realized-paper `NONE`, null or unknown
directions also refuse.

## Inputs

Every path below must be absolute and normalized. Bound files must be regular,
non-symlink files. Hashes bind the raw bytes, not normalized JSON.

Required read-only bindings:

1. repository root and exact checked-out Git SHA;
2. eligible v2 decision path and raw SHA-256;
3. current schema-v2 snapshot path, raw SHA-256 and producer Git SHA;
4. previous schema-v2 snapshot path, raw SHA-256 and producer Git SHA;
5. paper run-config path, raw SHA-256 and producer Git SHA;
6. v2 governor-config path and raw SHA-256;
7. exact RFC 3339 `EVALUATED_AT` used by the decision;
8. `PRIOR_ACTIVE_SET_SOURCE=STATIC_PAPER_ALLOWLIST`;
9. exact RFC 3339 proposed controller start time, which must be no more than
   60 seconds behind the controller's actual UTC wall clock and cannot be in
   the future;
10. one exact regular-file observe JSONL source;
11. one exact HTTP loopback strategy paper-trades URL with an explicit port;
    the controller's read-only adapter converts only completed `exit_ts` /
    finite `net_bps` rows into the existing paper-ledger mark shape; and
12. one existing real directory that does not contain the deterministic trial
    root.

The repository must be at the exact supplied SHA with a clean tracked
worktree. Untracked files are not read or modified by the controller.

## Disabled-default proof

The default command performs no file, process or network I/O:

```bash
python3 tools/scripts/autopilot_dynamic_paper_controller_v2.py
```

Expected result:

```json
{"artifact_created":false,"files_read":false,"mode":"auto2d_bounded_paper_controller","network_accessed":false,"start_invoked":false,"status":"DISABLED"}
```

`--start` without `--enabled` refuses before inspecting any input.

## Genuine E3 input manifest

Genuine E3 is separately gated. It requires Operator-controlled, read-only
copies from two distinct comparable production schema-v2 selector windows. Do
not capture a window, access a host, copy files or run E3 without explicit
authorization.

```text
REPOSITORY_ROOT=<absolute clean local checkout>
REPOSITORY_GIT_SHA=<40 lowercase hex exact reviewed PR head>

DECISION_PATH=<absolute regular non-symlink eligible v2 decision JSON>
DECISION_SHA256=<64 lowercase hex raw-byte hash>

CURRENT_SNAPSHOT_PATH=<absolute regular non-symlink schema-v2 JSON>
CURRENT_SNAPSHOT_SHA256=<64 lowercase hex raw-byte hash>
CURRENT_SNAPSHOT_PRODUCER_GIT_SHA=<40 lowercase hex>

PREVIOUS_SNAPSHOT_PATH=<absolute regular non-symlink schema-v2 JSON>
PREVIOUS_SNAPSHOT_SHA256=<64 lowercase hex raw-byte hash>
PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA=<40 lowercase hex>

PAPER_RUN_CONFIG_PATH=<absolute regular non-symlink JSON>
PAPER_RUN_CONFIG_SHA256=<64 lowercase hex raw-byte hash>
PAPER_RUN_CONFIG_PRODUCER_GIT_SHA=<40 lowercase hex>

GOVERNOR_CONFIG_PATH=<absolute regular non-symlink JSON>
GOVERNOR_CONFIG_SHA256=<64 lowercase hex raw-byte hash>

EVALUATED_AT=<exact canonical RFC 3339 decision time>
CONTROLLER_STARTED_AT=<canonical RFC 3339 time, 0..300 seconds after EVALUATED_AT and within 60 seconds of actual invocation>
PRIOR_ACTIVE_SET_SOURCE=STATIC_PAPER_ALLOWLIST

OBSERVE_SOURCE_JSONL=<absolute regular non-symlink observe JSONL>
MARKS_URL=<exact http://127.0.0.1:PORT/path or http://[::1]:PORT/path>
TRIAL_ROOT_PARENT=<absolute existing real directory>
```

The proposed deterministic root is:

```text
${TRIAL_ROOT_PARENT}/auto2d-paper-v2-${DECISION_ID}
```

It must be absent. A prior or partial root is a hard no-restart condition.

## Strictly read-only E3 verification

Populate the manifest variables in one Operator-controlled shell. The
following command reads and verifies but creates nothing and performs no
network request:

```bash
python3 tools/scripts/autopilot_dynamic_paper_controller_v2.py \
  --verify-only \
  --repository-root "$REPOSITORY_ROOT" \
  --repository-git-sha "$REPOSITORY_GIT_SHA" \
  --decision-json "$DECISION_PATH" \
  --decision-sha256 "$DECISION_SHA256" \
  --current-snapshot-json "$CURRENT_SNAPSHOT_PATH" \
  --current-snapshot-sha256 "$CURRENT_SNAPSHOT_SHA256" \
  --current-snapshot-producer-git-sha "$CURRENT_SNAPSHOT_PRODUCER_GIT_SHA" \
  --previous-snapshot-json "$PREVIOUS_SNAPSHOT_PATH" \
  --previous-snapshot-sha256 "$PREVIOUS_SNAPSHOT_SHA256" \
  --previous-snapshot-producer-git-sha "$PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA" \
  --paper-run-config-json "$PAPER_RUN_CONFIG_PATH" \
  --paper-run-config-sha256 "$PAPER_RUN_CONFIG_SHA256" \
  --paper-run-config-producer-git-sha "$PAPER_RUN_CONFIG_PRODUCER_GIT_SHA" \
  --governor-config-json "$GOVERNOR_CONFIG_PATH" \
  --governor-config-sha256 "$GOVERNOR_CONFIG_SHA256" \
  --evaluated-at "$EVALUATED_AT" \
  --prior-active-set-source "$PRIOR_ACTIVE_SET_SOURCE" \
  --controller-started-at "$CONTROLLER_STARTED_AT" \
  --observe-source-jsonl "$OBSERVE_SOURCE_JSONL" \
  --marks-url "$MARKS_URL" \
  --trial-root-parent "$TRIAL_ROOT_PARENT"
```

Required result:

- exit code zero;
- `status=VERIFIED_NOT_STARTED`;
- `verification=PASS`;
- `artifact_created=false`;
- `network_accessed=false`;
- `start_invoked=false`;
- exact decision, policy, repository and proposed-root bindings; and
- actual wall-clock decision age at most 300 seconds and the supplied start
  binding no more than 60 seconds old; and
- the proposed root remains absent.

Any other result is `NO-GO`. Do not retry, repair, substitute an input, create
an output, or start a trial.

## What independent verification recomputes

The controller re-reads raw bytes and independently verifies:

- exact paths, SHA-256 hashes and producer-Git-SHA attestations;
- strict JSON, schema-v2 completeness, timestamps and selector configuration;
- realized-paper and selector-view stream segregation;
- actionable direction domains and non-actionable `NONE`/null handling;
- the exact static direction-level baseline;
- two-snapshot identity, separation, freshness and churn consistency;
- candidate qualification and both deterministic ranking lanes;
- exploration reservation, concentration skips and deterministic truncation;
- selected, added, removed and retained exact keys;
- selection, addition and concentration limits;
- for the historical route, removal and 50% churn limits;
- for `FIRST_BOUNDED_PAPER_EXPERIMENT`, exact static-overlap calculations and
  an explicit report-only removal/churn posture;
- policy-envelope hash, prior-active-set hash and decision ID;
- every calculation, gate, reason, methodology and authority field; and
- exact equality of the complete reconstructed decision.

It accepts no schema-v1 decision, blocked decision, raw snapshot in place of a
decision, governor self-approval, fallback universe or per-output override.
It also rejects a policy-version/config mismatch, an experiment decision that
omits the no-promotion boundary, or any attempt to apply experiment semantics
to the historical policy version.

## Separately authorized start command

Do not run this block merely because E3 or review is clean. It requires a new
Operator authorization bound to the exact merged repository SHA, decision
hash, input hashes, proposed start time, observe source, marks URL and absent
root.

That authorization must follow a fresh read-only host preflight proving that
no other AUTO-2D controller or static/dynamic paper loop is running and that
no unresolved paper position exists outside the proposed trial. If exclusive
paper ownership and zero prior open exposure cannot be proved, the start is
`NO-GO`; the controller's in-process exposure ledger must not be treated as a
cross-process inventory.

The only operational difference from the E3 command is replacing
`--verify-only` with both `--enabled --start`:

```bash
python3 tools/scripts/autopilot_dynamic_paper_controller_v2.py \
  --enabled --start \
  --repository-root "$REPOSITORY_ROOT" \
  --repository-git-sha "$REPOSITORY_GIT_SHA" \
  --decision-json "$DECISION_PATH" \
  --decision-sha256 "$DECISION_SHA256" \
  --current-snapshot-json "$CURRENT_SNAPSHOT_PATH" \
  --current-snapshot-sha256 "$CURRENT_SNAPSHOT_SHA256" \
  --current-snapshot-producer-git-sha "$CURRENT_SNAPSHOT_PRODUCER_GIT_SHA" \
  --previous-snapshot-json "$PREVIOUS_SNAPSHOT_PATH" \
  --previous-snapshot-sha256 "$PREVIOUS_SNAPSHOT_SHA256" \
  --previous-snapshot-producer-git-sha "$PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA" \
  --paper-run-config-json "$PAPER_RUN_CONFIG_PATH" \
  --paper-run-config-sha256 "$PAPER_RUN_CONFIG_SHA256" \
  --paper-run-config-producer-git-sha "$PAPER_RUN_CONFIG_PRODUCER_GIT_SHA" \
  --governor-config-json "$GOVERNOR_CONFIG_PATH" \
  --governor-config-sha256 "$GOVERNOR_CONFIG_SHA256" \
  --evaluated-at "$EVALUATED_AT" \
  --prior-active-set-source "$PRIOR_ACTIVE_SET_SOURCE" \
  --controller-started-at "$CONTROLLER_STARTED_AT" \
  --observe-source-jsonl "$OBSERVE_SOURCE_JSONL" \
  --marks-url "$MARKS_URL" \
  --trial-root-parent "$TRIAL_ROOT_PARENT"
```

The command runs one foreground controller. Do not daemonize it, wrap it in an
unattended retry loop, start a second copy, or use a service manager.

## Start and lifecycle controls

Before root creation the controller repeats repository and raw-input checks,
locks the existing parent directory without waiting, and requires the
deterministic root to remain absent. Root creation is exclusive.

After root creation:

- `controller_binding.json` freezes all bindings and the immutable universe;
- `autopilot_dynamic_paper_provenance_v2.jsonl` is append-only;
- `controller_events.jsonl` retains tick hashes and controller refusals;
- `paper/` contains the existing paper decision/position JSONL formats;
- the controller rechecks repository and immutable bound inputs each tick;
- the observe source is stable-read by exact device/inode identity;
- completed paper-trade rows are adapted in memory to existing paper marks;
  marks use GET only, with proxies disabled and redirects refused;
- exits are processed before entries;
- controller-owned portfolio caps are applied before the paper ledger; and
- every paper decision and position receives an append-only provenance binding.

For `FIRST_BOUNDED_PAPER_EXPERIMENT`, `controller_binding.json` additionally
records that static overlap is report-only, shared configuration was not
mutated, the dynamic universe is root-local and immutable, and neither the
decision nor the trial evidence has later-promotion authority.

At 86,400 seconds the controller appends `EXIT_ONLY` and opens no further
positions. It completes naturally when no position remains. At 90,000 seconds,
any unresolved position produces `NO_GO/HARD_RUNTIME_REACHED`; the partial root
is retained.

## Fail-closed and partial-root handling

Before root creation, any mismatch produces no artifact.

After root creation, any immutable-input change, repository change, malformed
state, source identity change, loopback GET failure, clock reversal or output
failure stops new entries and retains the root. The controller never
overwrites, repairs, cleans or reuses it. A retained partial root is audit
evidence and blocks automatic restart for that decision.

Do not remove a partial root. Do not edit JSONL records. Do not create a
replacement root for the same decision. Escalate with:

- complete terminal output;
- exact repository and decision SHA;
- root path and read-only file hashes;
- last provenance and controller-event records; and
- unresolved paper-position count.

There is no runbook-authorized early-stop signal. OBS-3 process-identity work
remains separately scoped. If a controller appears stuck, gather read-only
evidence and request exact Operator direction; do not signal a PID from this
runbook.

## Post-run validation

A later separately authorized read-only validator must:

1. require natural process exit or report that it is still running without
   signalling it;
2. validate every provenance record against
   `specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json`;
3. recompute the decision, policy, input and record hashes;
4. require one immutable trial ID and universe across every record;
5. reconcile every paper record to exactly one provenance binding;
6. prove controller exposure caps and lifecycle deadlines were respected;
7. report malformed, duplicate, orphan, incomplete and trailing-partial counts;
8. report `COMPLETE/NATURAL_COMPLETION` or the exact `NO_GO` reason;
9. prove all bound inputs were preserved; and
10. report output file paths, sizes, timestamps and SHA-256 hashes.

No paper result, clean validation or provenance record grants live eligibility,
deployment, service mutation or AUTO-3 authority.

## Rollback

The controller writes no shared paper configuration and changes no service.
Rollback is therefore documentary and operational:

- retain the complete trial root;
- do not use its immutable universe for another run;
- do not restart or fall back;
- keep existing static paper configuration unchanged; and
- record the decision, reason and exact retained hashes append-only.

CI-1, OBS-1 and OBS-3 remain separately scoped.
