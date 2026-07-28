# AUTO-2C v2 Automatic Paper Policy

> **Status**: Operator-ratified contract design.
>
> **Authority**: non-actuating. This record and its contracts do not implement
> the v2 governor, alter paper configuration, approve a concrete decision,
> start a paper trial, route an order, access a host, deploy a service, or grant
> live-trading authority.
>
> **Supersedes narrowly**: the schema-version-1 demotion-only, zero-addition,
> block-on-overflow, one-change, 25%-churn, 24-hour-validity, and per-output
> Operator-approval policy for the future accelerated paper-only route. The
> schema-version-1 contract and implementation remain valid historical
> advisory interfaces and are not accepted by the v2 paper route.

## 1. Context & Sources Consulted

Verified repository sources:

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- the C-a, C-b, and C-c work orders and inner-review summaries under
  `.agentic/runs/`
- `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- `tools/scripts/autopilot_dynamic_allowlist.py`
- `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/contracts/autopilot_paper_decision_record.schema.json`
- `specs/contracts/autopilot_paper_position.schema.json`
- `tools/scripts/autopilot_paper.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `.agentic/policies/evidence.md`

Verified governance facts:

- PR #260 landed AUTO-2C C-c on `main` as
  `c1b65389ebf0ead41146df12ca49a07f3889cfc9`.
- C-c is a deterministic, one-shot, advisory schema-version-1 governor. It is
  demotion-only, blocks candidate overflow, requires per-output exact-hash
  Operator approval, and has no paper or live authority.
- The accepted C-c E3 was a schema-valid blocked-empty advisory result against
  a schema-version-1 predecessor. It did not create eligibility.
- No second comparable schema-v2 selector window has been accepted.
- CI-1, OBS-1, and OBS-3 remain separately scoped.

Operator-ratified policy inputs:

- the accelerated target is one later, separately authorized, bounded
  paper-only PairsTrader trial;
- qualified selector-discovered exact keys may be added even when absent from
  the static baseline;
- overflow is deterministically ranked and truncated instead of blocking
  solely because too many candidates qualify;
- automatic acceptance means a future AUTO-2D controller independently
  verifies a v2 decision inside this fixed policy envelope;
- the governor never approves itself and cannot start a trial; and
- the protected sequence remains PLAN → BUILD → INNER → Tier 3 draft PR →
  Claude exact-SHA REVIEW → Operator MERGE authorization for every slice.

All host, process, evidence, and artifact state is potentially stale. No
current runtime claim is made here.

## 2. Problem and Target

The v1 governor deliberately cannot add a selector-discovered key outside the
static baseline, rank and truncate an oversized candidate set, or support
automatic acceptance. Those limits were safe for the first advisory governor,
but they cannot reach the Operator's paper-only automatic-selection target.

The smallest compatible progression is a separate v2 contract family:

1. AUTO-2C v2 produces a deterministic, non-actuating decision that may contain
   bounded additions and records every rank, selection, truncation, skip, and
   transition calculation.
2. A later AUTO-2D controller independently re-reads and recomputes the
   decision. It may automatically accept it only when every fixed contract,
   hash, freshness, policy, configuration, concurrency, and paper-only gate
   passes.
3. Only that later controller may construct an immutable dynamic paper
   universe and start exactly one bounded paper trial, and only after its own
   implementation, production-evidence, and trial-start gates are separately
   authorized.

This slice defines contracts and synthetic validation only. It does not perform
steps 1–3 at runtime.

## 3. Slice Loop Check

- **New input**: the Operator-ratified addition, ranking, automatic-acceptance,
  exposure, lifecycle, and transition envelope.
- **New state transition**: the v1 demotion-only interface gains a separately
  versioned v2 successor capable of representing a bounded addition and a
  deterministic truncated candidate set.
- **Concrete value**: the next governor slice and later AUTO-2D controller can
  target one machine-readable policy without inventing selection or authority
  semantics.
- **Non-repetition**: v1 remains preserved; v2 explicitly changes the
  previously blocking policies needed for the paper-trial target.
- **Stop/defer**: governor code, runbooks, host/evidence actions, paper
  configuration, controller behavior, paper start, live trading, services,
  deployment, secrets, CI-1, OBS-1, OBS-3, AUTO-3, or an unattended loop
  remains outside this slice.

## 4. Plan and Dependency-Ordered Queue

1. **V2-a — this slice**: v2 decision and paper-provenance contracts,
   canonical eligible/blocked and provenance examples, independent semantic
   and mutation tests, compatibility, versioning, and governance.
2. **V2-b + C-d — later**: implement the one-shot v2 governor and its
   Operator-run runbook/hardening. Preserve v1 behavior as a separate route.
3. **AUTO-2D — later**: implement the isolated bounded paper controller,
   independent v2 verification, immutable dynamic universe, provenance
   records, one-shot start/stop lifecycle, and no-live boundary.
4. **Production evidence and one trial — later**: obtain two separately
   authorized comparable schema-v2 windows, run one separately authorized
   v2 decision, validate it, then request a distinct exact trial-start
   authorization.

Each later slice requires its own PLAN, BUILD authorization, inner review,
Tier 3 draft PR, Claude exact-SHA review, and Operator merge authorization.
This record grants none of them.

## 5. Interfaces / Contracts

### 5.1 AUTO-2C v2 decision

`specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json` is a new
schema-version-2 decision type. Required identity inputs are:

- exact raw SHA-256 and producer Git SHA for current and previous B2-c
  snapshots;
- exact raw SHA-256 and producer Git SHA for the paper-run configuration;
- exact raw SHA-256 for the governor configuration;
- a policy-envelope SHA-256 over canonical `policy_version + policy`;
- a prior-active-set SHA-256 over canonical exact keys; and
- an explicit RFC 3339 evaluation time.

The deterministic `decision_id` is SHA-256 over minified key-sorted UTF-8 JSON
containing those four raw input hashes, the policy-envelope hash, the
prior-active-set hash, and the evaluation time, with no trailing newline.

The contract has two statuses:

- `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION`: trusted inputs and every policy
  gate pass. This is not eligibility authority.
- `GOVERNOR_BLOCKED`: trusted inputs cannot pass policy. Candidate, selected,
  selection-step, truncation, skip, addition, removal, and retained outcome
  sets are empty. Candidate evidence may remain when qualification completed
  before a later global transition gate blocked; an early input-policy block
  may have no candidates.

Malformed, untrusted, unknown-direction, incomplete, duplicate, or internally
inconsistent inputs remain outside the valid decision contract and must later
create no artifact.

### 5.2 Exact actionable identity and direction

The only actionable identity is:

```text
pair_id + timeframe=1m + selected_variant + direction
```

Actionable direction is exactly `LONG_SPREAD` or `SHORT_SPREAD`.

Selector `NONE` is an explicit non-actionable sentinel. JSON null is missing
direction. They remain distinct evidence counts and identities, but neither
may enter a candidate, selected universe, transition set, or paper provenance
key. Every other selector direction is unknown and rejects the input before
output. Realized-paper direction remains long/short only; realized `NONE`,
null, or unknown direction also rejects before output.

### 5.3 Evidence segregation

Realized-paper and selector-view evidence remain separate streams:

- realized qualification is exact set membership in selected and absence from
  rejected/quarantined sets in both snapshots;
- selector qualification is exact set membership in prominent and absence
  from marginal/non-actionable sets in both snapshots; and
- metrics are never numerically merged between streams.

Two candidate classes are permitted:

- `REALIZED_AND_SELECTOR`: selected by realized-paper evidence in both
  snapshots and selector-prominent in both.
- `SELECTOR_EXPLORATION`: absent from realized selected, rejected, and
  quarantined sets in both snapshots, but selector-prominent in both.

### 5.4 AUTO-2D provenance companion

`specs/contracts/autopilot_dynamic_paper_provenance_v2.schema.json` is an
append-only companion interface for a later controller. It does not alter the
existing paper-decision or paper-position contracts.

It defines synthetic shapes for:

- one trial manifest binding the exact v2 decision, immutable universe, and
  fixed lifecycle bounds;
- one paper-decision binding; and
- one paper-position binding.

Each record requires successful independent recomputation, exact decision and
policy hashes, append-only storage, no fallback, no automatic restart, and
paper-only authority. All live-order, exchange-routing, execution-service,
deployment, and service-configuration authority fields are false.

## 6. Ratified Policy Envelope

### 6.1 Comparable evidence and qualification

- exactly two distinct schema-v2 B2-c snapshots;
- identical B2-c selector configuration;
- current and previous raw snapshot hashes must differ;
- source cutoffs strictly ordered and separated by at least 86,400 seconds;
- current source age at evaluation no more than 1,800 seconds;
- selector evidence present and complete in both snapshots;
- for every candidate in each snapshot:
  - selector rows at least 12;
  - `TRADE_NOW` rows at least 3;
  - `TRADE_NOW` ratio at least 0.01; and
  - finite positive selector-stated mean net edge.

No fallback is permitted for missing, stale, malformed, incomplete,
inconsistent, or insufficient evidence.

### 6.2 Deterministic ranking

Exact-key final tie-break order is lexicographic:

```text
(pair_id, timeframe, selected_variant, direction)
```

The realized-supported lane ranks by:

1. minimum total B2-c score across the two snapshots, descending;
2. minimum closed-position count, descending;
3. minimum `TRADE_NOW` ratio, descending; and
4. exact key, ascending.

The selector-exploration lane ranks by:

1. minimum `TRADE_NOW` ratio, descending;
2. minimum `TRADE_NOW` count, descending;
3. minimum selector-stated mean net edge, descending; and
4. exact key, ascending.

Allocation is deterministic:

1. reserve the best qualifying, transition-safe exploration addition;
2. fill from the realized-supported lane;
3. allow a second qualifying exploration addition when capacity and every
   transition/concentration gate permit; and
4. record candidates rejected by concentration as skipped and continue;
   record otherwise qualifying candidates beyond capacity as truncated.

An excess candidate count alone is not a blocking condition.

### 6.3 Selection, concentration, transition, and expiry

- maximum selected entries: 4;
- maximum additions: 2;
- maximum selector-exploration entries: 2;
- minimum selector-exploration entries: 1 when at least one qualifies and the
  transition remains safe;
- maximum removals: 2;
- maximum directions per pair/timeframe/variant: 2;
- maximum entries per pair ID: 2;
- maximum entries containing one full instrument: 2;
- maximum new additions containing one full instrument: 1;
- maximum churn: 50%;
- churn numerator: prior/proposed symmetric-difference count;
- churn denominator: `max(4, prior_active_entry_count)`;
- decision validity: 108,000 seconds (30 hours);
- fallback: none.

For the first transition, the prior active set is the exact static paper
allowlist. Later transitions use the immediately preceding independently
accepted v2 paper universe. A v1 decision or raw B2-c snapshot is never an
accepted prior v2 decision.

### 6.4 Paper-only exploration and lifecycle caps

- maximum simultaneous open paper positions: 2;
- maximum open position per pair ID: 1;
- maximum open position per full instrument: 1;
- maximum open selector-exploration position: 1;
- maximum open position per exact key: 1;
- holding window: 5 bars;
- cooldown: 300 seconds;
- maximum candidate age: 120 seconds;
- maximum decision age at automatic start: 300 seconds;
- entry window: 86,400 seconds;
- exit-only grace: 3,600 seconds;
- controller hard runtime: 90,000 seconds;
- no automatic restart and no fallback.

The later controller must stop new entries at the entry deadline, move to
exit-only handling, and stop no later than the hard deadline. Unresolved paper
positions must be reported, not reinterpreted as closed.

## 7. Automatic Acceptance and Authority Boundary

The governor cannot approve or consume its own output. A later AUTO-2D
controller may automatically accept one decision only by independently:

1. validating schema version 2 and policy version;
2. re-reading regular, non-symlink, stable inputs;
3. rechecking every raw input hash and producer attestation;
4. recomputing policy hash, prior-set hash, decision ID, qualification,
   ranking, truncation, concentration, transition, freshness, and expiry;
5. requiring status `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION`;
6. proving the decision and paper configuration are unchanged and the
   decision is within the 300-second automatic-start age;
7. creating one exclusive, previously absent trial root; and
8. freezing the exact selected universe for the entire bounded trial.

Per-output Operator approval is not required inside the ratified envelope.
That is a policy-level authorization design, not authority in this contract
slice. The later controller, production evidence run, and the first paper
trial each remain separate Operator gates.

The governor and contracts have no paper-configuration-write, paper-start,
paper-eligibility, live-eligibility, order, exchange, execution, deployment,
service, secret, or self-approval authority.

## 8. Risk & Failure Modes

- **Untrusted bytes or provenance**: reject before artifact creation.
- **Schema/version/config mismatch**: reject before artifact creation.
- **Stale, missing, incomplete, duplicate, or inconsistent evidence**: reject
  before artifact creation or produce blocked-empty only when the input is
  trusted but policy-insufficient.
- **Unknown/non-actionable direction entering an actionable set**: reject
  before artifact creation.
- **Ranking ambiguity**: canonical rank components and exact-key tie-breaks
  are recorded; any mismatch is fail-closed.
- **Overflow**: truncate deterministically and record; never silently drop.
- **Concentration failure**: skip that candidate and continue; never weaken a
  concentration cap.
- **Transition/churn failure**: valid blocked-empty decision, no fallback.
- **Expired decision**: no new entry and no fallback.
- **Concurrent or repeated invocation**: one exclusive output/trial root may
  win; collisions refuse without overwrite, repair, cleanup, or reuse.
- **Partial root**: retain for diagnosis; never treat as accepted output.
- **Controller mismatch**: independent recomputation failure prevents trial
  creation/start.
- **Authority leakage**: all actuation fields remain false and all concrete
  paper actions stay in later separately reviewed code.

## 9. Test Plan

This contract slice requires:

- Draft 2020-12 schema validation with active RFC 3339 format checking;
- canonical eligible and blocked decisions;
- canonical trial, paper-decision, and paper-position provenance records;
- independent policy-hash, prior-set-hash, and decision-ID recomputation;
- exact two-snapshot, selector-config, cutoff separation, freshness, and
  validity arithmetic;
- deterministic lane ranking, final tie-breaks, reserved exploration,
  skip-and-continue concentration, truncation, and transition sets;
- maximum-selection, additions, removals, exploration, pair, instrument,
  direction, and churn boundaries;
- distinct non-actionable `NONE` and null plus unknown-direction refusal;
- realized/selector segregation;
- blocked-empty and no-fallback behavior;
- independent-verification and all-false actuation authority;
- companion record binding to exact v2 decision bytes;
- mutation checkpoints for identity, ranking, set equality, freshness,
  concentration, churn, authority, and v1 incompatibility; and
- byte-identical preservation of the v1 decision contract/example/tests,
  existing governor, and paper contracts/code.

No real host artifact or runtime paper behavior is required or permitted for
this contract slice.

## 10. Observability and Audit

The v2 decision records:

- exact inputs, producer attestations, policy and prior-set hashes;
- explicit evaluation/expiry and source cutoffs;
- candidate rank components and lane ranks;
- every selected, skipped, and truncated candidate;
- additions, removals, retained entries, concentration, churn, and gate
  outcomes;
- separate selector/realized direction counts;
- deterministic methodology; and
- explicit AUTO-2D verification and no-authority boundaries.

The provenance companion records immutable trial bounds and exact selection
origin for later paper decision/position records. It adds no service metric,
alert, process, scheduler, output root, or runtime log in this slice.

## 11. Versioning and Compatibility

This is an additive MINOR-level contract family:

- schema version 2 is a new decision type, not an in-place v1 relaxation;
- schema-v1 artifacts remain valid for the v1 advisory governor;
- schema-v1 decisions and raw snapshots are explicitly unacceptable to the
  future v2 AUTO-2D route;
- existing B2-c snapshot and AUTO-2A paper contracts/code remain unchanged;
- the provenance companion is additive and does not replace paper records;
- no package version, dependency, release, or tag changes here; and
- `CHANGELOG.md`, compatibility, and governance record the supersession and
  continued no-actuation boundary.

## 12. Stop Conditions

Stop and request a new decision if implementation requires changing v1,
B2-c, or existing paper contracts/code; accessing a host or real artifact;
capturing a second window; writing paper configuration; implementing or
starting AUTO-2D; trading; routing an order; deploying; accessing secrets;
changing services; addressing CI-1/OBS-1/OBS-3; beginning AUTO-3; or running an
unattended loop.

## 13. Current Gate

V2-a ends at a Tier 3 draft PR. A different reviewer must assess its exact
head. A CLEAN verdict is not merge authority. After a CLEAN exact-SHA review,
passing required checks, no unresolved threads, and mergeability, the Operator
must separately authorize merge. V2-b + C-d cannot begin before that merge and
a separate BUILD authorization.
