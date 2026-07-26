# Proposal: AUTO-2C Governed Dynamic Allowlist

> **Status**: PROPOSAL — design only.
>
> **Authority**: this document does not implement a governor, create an
> allowlist decision, alter paper eligibility, authorize AUTO-2D, or grant any
> runtime, host, deployment, secret, paper-trading, or live-trading action.
>
> **Item addressed**: Operator decision OP-45(d/e), using the accepted
> AUTO-2B.2 B2-d capture and corrected B2-cR preserved-evidence replay.

## 1. Context & Sources Consulted

Verified repository sources:

- `AGENTS.md`
- `CODEX.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `.agentic/registers/decisions.md`
- `.agentic/policies/evidence.md`
- `docs/proposals/AUTO-2-1m-paper-autopilot-governance.md`
- `docs/proposals/AUTO-2B-shadow-dynamic-allowlist.md`
- `docs/proposals/AUTO-2B2-full-universe-shadow.md`
- `docs/superpowers/plans/2026-06-22-auto2-paper-autopilot-sequence.md`
- `.agentic/runs/AG-20260717-010-b2c-shadow-scorer-selector-view-input/00-work-order.md`
- `.agentic/runs/AG-20260724-011-b2cr-direction-sentinel-consumer-repair/00-work-order.md`
- `docs/playbooks/autopilot-shadow-allowlist-runbook.md`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/contracts/autopilot_paper_decision_record.schema.json`
- `specs/contracts/autopilot_paper_position.schema.json`
- `tools/scripts/autopilot_shadow_allowlist.py`
- `tools/scripts/autopilot_paper.py`
- `docs/02-versioning-and-releases.md`
- `docs/03-contracts-and-compatibility.md`
- `docs/10-architecture.md`
- `docs/11-data-integrity-policy.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`

Accepted Operator evidence:

- B2-d run `20260720T000558Z` completed naturally at Git SHA
  `88f12eab5ec29c19b91a27497c1658c6cf109002`.
- Its four selector-view shards remained unchanged and structurally complete:
  849 manifests and 13,584 rows, with no malformed line, incomplete manifest,
  duplicate tick, duplicate candidate, orphan row, or trailing partial.
- B2-cR landed on `main` as
  `29de6028b564869298bc0be7e581ed28df78bbf2`.
- The corrected offline replay at that landing SHA consumed 46 latest closed
  paper positions, excluded two latest open positions without estimating or
  changing them, and represented all 13,584 selector rows.
- The schema-valid output kept 11,418 `direction_hint="NONE"` rows distinct
  from null; every `NONE` identity was marginal and none was prominent.
- The replay selected one realized-paper identity, rejected three, quarantined
  none, and found zero unknown directions.
- Realized-paper churn was computed against a schema-v1 previous snapshot.
  `churn.selector_view` is null because that previous snapshot has no
  selector-view block.
- The accepted replay bound these exact inputs:
  - paper run:
    `/opt/cryptopairs/artifacts/autopilot_paper/runs/20260713T060641Z`;
  - selector-view run:
    `/opt/cryptopairs/artifacts/autopilot_observe_selector_view/runs/20260720T000558Z`;
  - source cutoff: `2026-07-23T00:02:25Z`;
  - previous snapshot:
    `/opt/cryptopairs/artifacts/autopilot_shadow_allowlist/runs/20260713T043227Z/autopilot_shadow_allowlist_snapshot.json`,
    SHA-256
    `d26267fefa68ee5dc9929fa7c2b0e8964d76face655377382c5550b1c579b853`;
  - thresholds: minimum closed positions `5`, minimum average net bps `0`,
    maximum tail loss bps `-60`, maximum average exit lag `1800` seconds,
    maximum selected `8`, and minimum score `0`.
- The accepted output is
  `/opt/cryptopairs/artifacts/autopilot_shadow_allowlist/runs/b2d-20260720T000558Z-b2cr-29de6028/autopilot_shadow_allowlist_snapshot.json`,
  SHA-256
  `97275666f9f07af9ea5ce2942838dda3bf53dcf20cced063af83d01e576a547b`.
  These are accepted historical transcript facts, not a claim about current
  host state.
- The output remained advisory and changed no paper or live eligibility,
  service, process, or trading state.

## 2. Problem

AUTO-2B/B2-c produces advisory evidence. Its `selected` array is not an active
allowlist, and `selector_view_prominent` means only that an exact selector key
appeared in `TRADE_NOW` at least once during the captured window. Neither fact
proves dwell, cross-window stability, acceptable transition churn,
concentration, current freshness, or Operator approval.

The accepted replay also has no comparable selector-view predecessor:
`churn.selector_view=null`. It therefore cannot prove selector dwell or
stability and must not produce actionable eligibility.

AUTO-2C needs a governor between the advisory snapshot and any later
paper-entry consumer. The smallest safe boundary is a deterministic,
offline, one-shot artifact reducer. It can say that a candidate set is
eligible for Operator review or that the evidence is blocked; it cannot
activate the set.

## 3. Slice Loop Check

- **New input consumed**: accepted production-shaped B2-d capture and corrected
  B2-cR replay evidence.
- **New state transition**: advisory shadow evidence becomes design input for a
  future governed decision artifact; no candidate becomes eligible.
- **New artifact/runtime/user value**: a proposed, testable boundary for
  freshness, history, churn, concentration, quarantine, deterministic
  reduction, expiry, and approval.
- **Why this is not repeating B2-c**: B2-c validates and summarizes evidence;
  AUTO-2C will decide whether multiple trusted summaries satisfy governance
  gates.
- **Stop/defer condition**: any coupling to `autopilot_paper.py`, eligibility
  activation, service code, host action, scheduler, deployment, secrets,
  OBS-1, OBS-3, CI-1, AUTO-2D, AUTO-3, or live execution stops and requires a
  new Operator decision.

## 4. Plan

This proposal recommends four future Tier 3 implementation slices. OP-45(e)
requires the queue to be rebuilt before any of them starts.

1. **C-a — contracts and examples**: add a new governed-decision contract and
   example without changing B2-c or paper contracts.
2. **C-b — tests and scaffolding**: add deterministic fixtures, fail-closed
   tests, mutation checkpoints, and a disabled/no-output CLI scaffold.
3. **C-c — offline governor**: implement the one-shot reducer behind exact
   inputs and exclusive output creation; do not integrate it with paper.
4. **C-d — runbook and hardening**: document Operator-run input binding,
   validation, output review, expiry, and exact-hash approval. This remains
   offline and cannot begin AUTO-2D.

Each slice needs a separate work order, Codex inner review, fresh Claude
exact-SHA review, green required checks, and explicit Operator merge
authorization. This proposal does not authorize those slices.

## 5. Interfaces / Contracts

### 5.1 Existing input contract

The future governor consumes complete
`autopilot_shadow_allowlist_snapshot` schema-v2 artifacts. It must not rescore
paper events or reinterpret selector rows. It validates and uses the streams
as already separated:

- realized-paper evidence: `selected`, `rejected`, `quarantined`, realized
  churn, and their metrics;
- selector-view evidence: `selector_view_prominent`,
  `selector_view_marginal`, selector churn, and universe membership;
- set-membership comparisons only between the two streams.

The governor also needs the exact paper-run configuration that defines the
static baseline. It must bind all input files by SHA-256 in its output.

### 5.2 Proposed output contract

**PROPOSAL**: add
`specs/contracts/autopilot_dynamic_allowlist_decision.schema.json` with
schema version `1` and a matching example. Proposed required fields:

- `schema_version`, `mode`, `decision_id`, `status`;
- `evaluated_at`, `valid_until`;
- current and previous snapshot paths, SHA-256 hashes, generated timestamps,
  and source cutoffs;
- paper-run-config path and SHA-256 hash;
- exact B2-c selector configuration and governor configuration;
- baseline entries, proposed entries, additions, removals, and retained
  entries;
- per-gate verdicts and bounded reason codes;
- dwell, freshness, churn, and concentration calculations;
- counts of selector `NONE`, null, actionable, and unknown identities;
- `operator_approval_required: true`;
- `authority: "advisory_pending_operator_approval"`;
- explicit no-paper/no-live/no-execution caveats.

Proposed top-level statuses:

- `ELIGIBLE_FOR_OPERATOR_REVIEW`: every trusted-input and policy gate passes;
  the artifact remains non-authoritative.
- `GOVERNOR_BLOCKED`: inputs are structurally trusted but policy evidence is
  stale, insufficient, unstable, over-concentrated, or over the churn limit;
  proposed entries are empty.

Malformed, ambiguous, or internally inconsistent input is not a valid
decision. It must exit nonzero and create no artifact.

### 5.3 Exact identity and direction boundary

The only actionable key is:

```text
pair_id + timeframe=1m + selected_variant + direction
```

Actionable directions remain exactly `LONG_SPREAD` and `SHORT_SPREAD`.

`NONE` is the strategy service's explicit non-actionable sentinel. JSON null
means direction was not supplied. They remain distinct identities in evidence,
but neither is actionable, neither is a wildcard, and neither may match
directional realized-paper evidence or a direction-specific baseline entry.
Every other direction string is unknown and fails the entire input closed.

### 5.4 Proposed exact inputs

**PROPOSAL**: the future CLI requires explicit paths and never scans for
"latest":

- `--current-snapshot-json`
- `--previous-snapshot-json`
- `--paper-run-config-json`
- `--governor-config-json`
- `--evaluated-at`
- optional `--previous-decision-json`
- `--output-json`
- `--output-markdown`

No wall-clock default may affect the decision. The explicit evaluation time is
part of the deterministic decision identity.

## 6. Proposed Governor Rules

All numeric values and policy choices in this section are **PROPOSAL**, not
approved implementation policy.

### 6.1 Trusted-input gates

Before any output:

1. Both snapshots validate as schema version 2.
2. Snapshot identities, arrays, counts, timestamps, and finite numbers are
   internally consistent and contain no duplicate exact keys.
3. Snapshot selector configurations match exactly.
4. Current and previous SHA-256 hashes differ.
5. Source cutoffs increase strictly and the current cutoff is not in the
   future.
6. The current snapshot's realized and selector sections remain segregated.
7. Direction values are only null, `LONG_SPREAD`, `NONE`, or `SHORT_SPREAD`;
   realized-paper candidates remain long/short only.
8. The paper-run configuration is structurally valid and reconstructs the
   static baseline used for the transition comparison.

Any failure exits nonzero before output creation.

### 6.2 Candidate qualification

**PROPOSAL**: an exact long/short key qualifies for Operator review only when
it:

1. is `SHADOW_SELECTED` in both snapshots;
2. is `selector_view_prominent` in both snapshots;
3. is absent from both snapshots' rejected and quarantined arrays;
4. overlaps the exact static baseline;
5. satisfies every global history, freshness, churn, concentration, and
   expiry gate.

`selector_view_only` and marginal identities never qualify. Selector-view
metrics are not PnL and are never merged numerically with realized metrics.

### 6.3 First-policy defaults

**PROPOSAL**:

- transition posture: demotion-only; output is a subset of the static
  baseline;
- comparable history: two consecutive schema-v2 snapshots with identical
  B2-c thresholds;
- minimum source-cutoff separation: 24 hours;
- maximum current source age at evaluation: 30 minutes;
- maximum governed entries: 4;
- maximum directions per pair/variant: 2;
- maximum entries containing the same full instrument identifier: 2;
- maximum changed entries per decision: 1;
- maximum churn ratio: 25%;
- validity: 24 hours from explicit evaluation;
- any global gate failure: `GOVERNOR_BLOCKED` with an empty proposed set;
- no automatic reuse, fallback, overwrite, activation, or rollback.

For concentration, a pair ID must split into exactly two non-empty instrument
identifiers around one `__`. The governor counts the full identifiers; it must
not guess or normalize base assets.

### 6.4 Current evidence disposition

The accepted replay cannot pass the proposed comparable-history gate:
`churn.selector_view=null` proves the supplied previous snapshot has no
selector-view block. The replay remains valid evidence, but it cannot yield
actionable eligibility. Under this design it produces
`GOVERNOR_BLOCKED` with an empty proposed set.

A future second comparable v2 evidence window, replay, or host action requires
separate Operator authorization. This proposal authorizes none.

### 6.5 Freshness and expiry

Freshness is measured from `source_cutoff_at`, not `generated_at`. Replaying
old source data cannot make it fresh by generating a new artifact.

After `valid_until`, the artifact grants no new-entry eligibility. A future
consumer must fail closed rather than silently fall back to a previous
decision.

### 6.6 Operator approval and AUTO-2D boundary

`ELIGIBLE_FOR_OPERATOR_REVIEW` is not approval. A future AUTO-2D run requires:

1. an implemented and reviewed AUTO-2C governor;
2. a separately approved AUTO-2D design and consumer;
3. an unexpired governed-decision path and exact SHA-256;
4. explicit Operator authorization naming that exact hash and bounded paper
   run;
5. the existing AUTO-2A paper ledger, risk, duplicate, cooldown, and exit
   controls unchanged.

**PROPOSAL**: record the Operator decision append-only with the exact governed
JSON path and SHA-256, `decision_id`, governor-config hash, `valid_until`, and
the bounded AUTO-2D paper run it may feed. The later consumer must require an
exact match to that recorded approval and fail closed on a missing,
conflicting, expired, or differently hashed decision.

AUTO-2C never writes `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`, `.env`, runtime
configuration, positions, orders, or service state.

## 7. Idempotency, Concurrency, and Rollback

**PROPOSAL**:

- Canonicalize and sort every key before hashing or serialization.
- Derive `decision_id` from the current/previous snapshot hashes, paper config
  hash, governor config, and explicit evaluation time.
- Identical inputs must produce byte-identical JSON and Markdown.
- Open output paths exclusively and refuse any existing path; never overwrite
  or repair partial output.
- Never mutate input files.
- A previous decision is comparison evidence only; it is not implicit
  authority.
- A blocked or expired decision never falls back to an older decision.
- Rollback means the Operator explicitly chooses a reviewed static baseline or
  separately authorizes a still-valid prior artifact in a later AUTO-2D
  procedure. The governor performs no rollback action itself.
- A future paper consumer must accept exactly one Operator-approved decision
  hash and reject concurrent or conflicting approvals.

## 8. Risk & Failure Modes

| Risk | Fail-closed response |
|---|---|
| Replay-generated time masks stale source evidence | Measure age from `source_cutoff_at` |
| Same window replayed as new dwell evidence | Require distinct hashes and strictly increasing cutoffs |
| Config drift makes churn incomparable | Require exact selector-config equality |
| `NONE` or null treated as a directional wildcard | Preserve identity but exclude from action |
| Unknown direction reaches output | Abort before artifact |
| Excessive additions/removals | Emit blocked empty decision |
| Concentration cannot be derived safely | Reject malformed pair identity or emit blocked decision |
| Quarantined key would remain eligible | Exclude it; if transition gates fail, block all new entries |
| Partial/concurrent output | Exclusive new paths; no overwrite or repair |
| Prior decision silently reused | No fallback; expired/blocked means no new entries |
| Advisory artifact treated as authority | Exact-hash Operator approval and later AUTO-2D consumer remain mandatory |
| Existing paper position needs an exit | AUTO-2C does nothing; existing paper-exit rules remain separate |

## 9. Test Plan

Future implementation must provide at least E3 integrated evidence and E4 proof
for the fail-closed controls. **PROPOSAL** test coverage:

1. New contract and example validate.
2. A production-shaped accepted-replay fixture with
   `churn.selector_view=null` emits a blocked empty decision.
3. Two comparable v2 snapshots can produce a review-eligible decision only
   when the exact long/short key is realized-selected, selector-prominent, and
   static-overlapping in both.
4. `NONE` and null remain distinct, appear in evidence counts, and never enter
   proposed entries.
5. Unknown selector directions and realized-paper `NONE` abort before output.
6. Schema version, selector config, hash identity, timestamp ordering,
   freshness, duplicate-key, count/list, and finite-number mutations fail.
7. Insufficient dwell, stale evidence, excessive churn, quarantine, maximum
   count, pair concentration, and instrument concentration block with bounded
   reasons.
8. Reversing input arrays and repeated identical invocation produce
   byte-identical output.
9. Existing output paths fail without overwrite; input hashes remain
   unchanged.
10. Static-overlap tests prove the first governor is demotion-only.
11. Source scans prove no HTTP, execution POST, service, `.env`, paper
    position, or runtime-config write surface.
12. Mutation checkpoints remove or invert every safety gate and prove the
    focused tests fail.
13. Focused and full canonical `tools/scripts` suites pass in a clean detached
    worktree.
14. A real accepted snapshot replay reaches E3 only from an
    Operator-supplied read-only copy or a separately authorized Operator-run
    host validation; no agent assumes host access.

CI-1 remains open: current GitHub CI does not run the `tools/scripts` suite.
AUTO-2C must disclose that limitation and must not silently absorb or claim to
resolve CI-1 without a separately approved scope.

## 10. Observability

The future offline JSON and Markdown artifacts should report:

- input paths, SHA-256 hashes, versions, cutoffs, and evaluation time;
- producer repository SHAs and paper-run configuration hash, so provenance is
  explicit and replayable;
- every gate verdict and bounded reason code;
- freshness and snapshot-separation seconds;
- candidate dwell across snapshots;
- baseline/proposed/retained/addition/removal sets;
- churn count and ratio;
- pair/variant and full-instrument concentration counts;
- `NONE`, null, actionable, and unknown-direction counts;
- status, expiry, and `operator_approval_required=true`;
- explicit advisory, no-eligibility, no-paper, and no-live caveats.

**PROPOSAL**: retain the bound input snapshots, paper configuration, governed
decision JSON, human-readable report, and validation transcript under one
immutable run identity. Record hashes for every retained file. Refuse
symlinks, path reuse, overwrite, or partial-output repair.

No service metric, alert, daemon, scheduler, or hosted loop is part of this
proposal. A later runbook may define Operator-visible artifact checks only
after the implementation queue is rebuilt.

## 11. Versioning

This proposal changes no system, contract, configuration, or runtime behavior.
It requires no version bump.

**PROPOSAL for a future C-a slice**: a new governed-decision contract is an
additive contract type and therefore a MINOR-level feature under
`docs/02-versioning-and-releases.md`, beginning at its own schema version `1`.
That slice must add an example, validation tests, compatibility notes, and a
`CHANGELOG.md` entry. Existing B2-c snapshot and paper contracts stay
unchanged unless a separately reviewed design proves they cannot express a
required invariant.

No dependency is proposed.

## 12. Operator Decisions Required Before Implementation

Before any C-a/C-b/C-c/C-d BUILD, the Operator must explicitly decide:

1. demotion-only versus evidence-backed additions — recommendation:
   demotion-only;
2. two-window history, 24-hour separation, and 30-minute freshness values —
   recommendation: adopt the proposed values;
3. four-entry, per-pair/per-instrument, one-change, and 25% churn caps —
   recommendation: adopt the proposed values;
4. 24-hour expiry and no-fallback behavior — recommendation: adopt;
5. E3 real-evidence route — supply a read-only snapshot copy or separately
   authorize Operator-run validation after implementation merge;
6. CI-1 treatment — recommendation: keep it as a separate work order.

## 13. Stop and Queue Rebuild

This proposal is the final step in the OP-45 queue. After it is accepted and
merged:

1. stop;
2. reconcile the accepted design and any Operator answers;
3. rebuild and approve the implementation queue;
4. do not auto-start C-a, AUTO-2D, AUTO-3, OBS-1, OBS-3, CI-1, host work,
   capture, deployment, secrets, services, paper trading, or live trading.
