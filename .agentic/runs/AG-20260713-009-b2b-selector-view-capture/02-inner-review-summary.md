# Inner Review Summary — AG-20260713-009

Two independent read-only reviewers on commit f4573ec; repairs in the
follow-up commit. 143 tools/scripts tests green.

## Reviewer A — tool correctness / fail-closed / contract conformance

- P2: `rationale_codes` iterated without a list guard → an identity-valid
  row with a non-list `rationale_codes` crashed the whole capture tick;
  a string value silently exploded into per-character garbage. **Fix:**
  `str_list()` guard mirroring `learning_reason_codes`; plus the whole
  per-row build is now wrapped so ANY unexpected shape fails closed to
  omission (the docstring's claim is now literally true), proven by a new
  test.
- P3: `spread_z`/`net_edge_bps`/`opportunity_score` `or 0.0` fabricated a
  stated figure from an absent one. **Fix:** a missing/non-numeric required
  stated figure now omits the row (fail closed) instead of fabricating 0.0.
- P3: stdout summary gained `selector_view_records: 0` even when disabled.
  **Fix:** the key is emitted only in capture mode; disabled runs' summary
  is unchanged.
- P3: source_generated_at fallback / disabled-default test proxy — noted;
  the disabled-default path is byte-identical (records) and now also
  summary-identical.
- Verified: max_runtime bound math correct; `--once` unaffected; boundary
  observation-only; scope confined.

## Reviewer B — proposal fidelity / boundary / faithfulness

- P3: "additionally" vs pure-mode wording — defensible and well-reasoned;
  B2-c consumes selector-view rows separately (§4.2) so nothing downstream
  needs both. **Fix:** ratified in the decisions register (wording-closure
  note).
- P3: inaccurate inline comment about malformed-response coverage. **Fix:**
  comment corrected; malformed non-list buckets now emit a diagnostic
  marker record instead of silent omission.
- P3: unused execution-service GETs in pure mode — informational, left as
  read-only harmless fetches to keep the diff surgical.
- Verified: observe_key does not collide with entry rows; field mapping
  faithful to decisionRowBase; no outcome fields; records/state/changelog
  do not overclaim (capture start is B2-d, operator).

Verdict after repairs: P2 closed with a regression test; all actioned P3s
fixed; one P3 (execution GETs) consciously left with rationale.

## Codex Tier 3 review round (PR #252) — two P1s the inner review missed

Codex's adversarial probing found two P1s the inner review did not:
- P1: a 400-digit number raised `OverflowError` in `float()` (escaping the
  narrow sentinel catch) and crashed the capture tick; NaN/inf passed and
  would serialize as invalid JSON.
- P1: lenient coercion FABRICATED rows — `setup_gate_pass: "false"` became
  `True`, a string `rationale_codes` became `[]` — producing schema-valid
  but semantically false selector evidence.

Fix: `selector_view_record` rewritten to strict all-or-nothing transcription
(finite numbers only, real bools only, string-lists only, timeframe==1m;
any wrong-typed field omits the row). Malformed responses (bad
`generated_at`) and non-list buckets now emit an honest
`BLOCKED_MALFORMED_RESPONSE` system record, not a fake selector observation.
Comprehensive malformed-input tests added (huge/NaN/inf/bool-as-string/
str-as-list/wrong-timeframe/missing-number/non-list-bucket/invalid-
generated-at); `json.dumps(allow_nan=False)` guards the artifact. P2s:
runbook disk figure corrected to a measured ~1.4–1.7 KB/row (was 0.6–1.0).
the tools/scripts suite green.

Lesson recorded: the inner-review claim "every unexpected shape is omitted,
proven by a regression test" was an overclaim — adversarial numeric/type
probing (huge/NaN/coercion) is now part of the fail-closed review checklist
for capture tools.

## Codex Tier 3 review round 3 (PR #252) — five more numeric/serialization P1s

Codex's third pass found five deeper correctness holes, all now fixed:
- `nullable_number` OverflowError on a huge int (entry + system paths) —
  `math.isfinite` on a large int raises. **Fix:** `is_finite_number`
  short-circuits ints (always finite, never overflow) before any float
  conversion; used by both `nullable_number` and `_finite_number`.
- lossy `float()` rounding of ints above 2**53. **Fix:** `_finite_number`
  preserves the value as-is (int stays int) — exact, tested.
- unvalidated `decision_bucket` could emit a v2-enum-invalid record.
  **Fix:** `_nullable_cue_bucket` validates against {TRADE_NOW, WATCHLIST,
  EXCLUDED} or null; bad value omits the row.
- date-only `generated_at` ("2026-06-13") parsed as fresh. **Fix:** the
  freshness gate requires a real time component (rejects strings without
  ":") → BLOCKED_MALFORMED_RESPONSE.
- the writer itself permitted nested non-finite JSON. **Fix:** `json_safe`
  recursively replaces NaN/inf with None on every record before
  `json.dumps(..., allow_nan=False)` — an invalid write is now impossible
  without any crash risk; a byte-identity test proves finite records are
  unchanged.

Meta-note: three Codex rounds on one capture tool, all on
numeric/serialization faithfulness that inner review under-probed. The
fail-closed review checklist for capture tools now mandates explicit
huge-int / non-finite / lossy-conversion / enum / timestamp-precision /
nested-serialization probes. the full tools/scripts suite green (count grows each round as cases are added).

## Codex round 4 + proactive convergence audit (PR #252)

Codex round 4 found four more: (1) an unhashable list/dict `decision_bucket`
crashed the tick — isinstance-guarded; (2) the ":" timestamp heuristic
accepted timeless strings — now requires a real "T" ISO datetime; (3) a
NaN quality-window value passed the gate then wrote a fabricated pass:true —
rejected at load; (4) system records could be schema-invalid on garbage
upstream (dispatch mode / negative age) — `schema_dispatch_mode` and
`nonneg_number` now coerce to schema-valid values.

To stop trading rounds, a **proactive convergence audit** then traced every
schema-constrained field across the entry, system, and selector record
paths. It confirmed no remaining crash or invalid-JSON path, and surfaced:
- A self-correction: my round-4 `decision_bucket == cue_bucket` requirement
  was OVER-strict (the v2 schema permits them to differ) and dropped
  schema-valid rows, under-recording the universe. **Relaxed** — a valid
  differing enum value is now recorded faithfully; a non-enum value still
  omits the row.
- Universe under-recording was invisible: omitted malformed rows now emit a
  per-bucket stderr diagnostic (`selector_view_omitted_malformed`) so B2-d
  evidence reveals a silently-dropped bucket instead of it looking empty.
- The v1 `source_generated_at` copied a raw non-timestamp string onto a
  BLOCKED_STALE_INPUT record — now nulled unless it is a valid "T" datetime.
- Pre-existing entry-path quality-window/config range holes (rows/min_rows
  `minimum 0`, profitable_rate `[0,1]`, non-finite thresholds, huge-int
  overflow, float/bool coercion of `rows`) — all validated/rejected at load,
  even though selector-view capture does not use quality windows, so no
  schema-invalid record can be produced from any config.

Every finding has a regression test. The fail-closed review checklist for
capture tools now mandates an exhaustive per-schema-field trace across all
record-building paths before first external review.

## Codex Tier 3 review round at `93efb4d` (post-merge-repair) — FINDINGS

Codex reviewed the conflict-repaired head `93efb4d1bdc87c88467182a03fcaad29d681b06a`
and returned FINDINGS. All four are repaired below; the prior verdict is void.

### F1 — incomplete ticks were silently under-recorded (fail-closed gap)

`selector_view_records` dropped a non-object row, an identity-invalid row, or
an unfaithfully-transcribable row and **emitted the remaining rows anyway**. Two
of those three paths did not even increment the omission counter, so they left
no trace at all; the third produced only a stderr line. The JSONL artifact —
the sole B2-c input — carried no signal, so B2-c could not distinguish a
complete universe from a silently shrunken one. A shrunken universe reads
downstream as false churn, and an under-recorded bucket as false stability:
exactly the measurement B2-b exists to make trustworthy.

**Repair — refuse the whole tick** (the finding's first branch), chosen over a
completeness marker because:
- it matches the fail-closed posture already in this function (a missing or
  non-list bucket already refuses the whole tick);
- it needs no contract change — B2-a's v2 contracts are merged and binding, and
  a marker "B2-c is explicitly required to reject" would need both a schema
  change and a downstream obligation that does not yet exist;
- it makes the guarantee unconditional and self-enforcing: any selector row
  present in the artifact belongs to a complete, faithfully-transcribed tick.

Any returned candidate that is not an object, fails identity, or raises
`_SelectorViewRowMalformed` now refuses the tick with a single
`BLOCKED_MALFORMED_RESPONSE` record and **no** selector rows. Reason codes are
bounded (3 causes x 3 buckets = 9 max) and never interpolate row-supplied
values such as `pair_id`. An empty bucket remains complete and valid — only
candidates the endpoint actually returned can make a tick incomplete.

Accepted trade-off: a persistently malformed upstream row refuses every tick.
That is the correct fail-closed direction and is loudly visible (per-tick
`INCOMPLETE_UNIVERSE` stderr diagnostic with per-bucket counts, plus a refusal
record per tick), rather than silently banking a corrupt churn baseline for 72h.
The runbook now tells the Operator to grep for it and escalate.

### F2 — unbounded selector-view loop could be started

`AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS` was optional, so `--loop` +
`--capture-selector-view` with no bound ran forever: an unattended loop
(Autonomy Doctrine) capturing the whole universe every tick (unbounded disk).
**Repair:** selector-view loop startup is refused unless a positive bound is
configured — `SELECTOR_VIEW_LOOP_REQUIRES_MAX_RUNTIME`, exit 2, before any
network client is constructed. Placed after the disabled-default early return
so the disabled probe stays byte-identical, and scoped to selector-view loops
so the narrow paper-feeding loop's operator-authorized behaviour is unchanged.
A `--once` selector-view run is bounded by construction and exempt.

### F3 — no selector-view stop procedure

The selector-view run writes its own `autopilot_observe_selector_view.pid`, but
the runbook's only stop procedure used the narrow run's `autopilot_observe.pid`
— an operator stopping early had no exact procedure and could signal the wrong
process. **Repair:** a dedicated "Stop the selector-view run" section that
identifies the correct PID file, verifies the PID really is the selector-view
capture via `ps` before signalling, uses SIGTERM (letting the in-flight tick
finish its write), verifies the stop, and escalates before any `kill -9`
(a hard kill mid-append can truncate the final JSONL record).

### F4 — PR description and evidence refreshed

Refreshed to the exact repaired head with the actual verification counts below.

### Multi-angle inner review of these repairs

- **Completeness (adversarial):** traced every path by which a selector row can
  fail to reach the artifact. Three row-level causes → all now refuse. Verified
  no *other* silent-drop path survives: `apply_persisted_duplicate_blocks` only
  relabels `OBSERVED_ENTRY_CANDIDATE` records (never drops, never matches
  `SELECTOR_VIEW_OBSERVED`), and `existing_observed_candidate_keys` only
  collects entry keys — so selector rows never dedupe away.
- **Exception surface:** confirmed every strict helper raises only
  `_SelectorViewRowMalformed` (`_finite_number` preserves ints so no
  `OverflowError`; `selector_view_observe_key` is total), so no exception
  escapes to crash a tick instead of refusing it. `row["pair_id"]` /
  `row["selected_variant"]` direct access stays safe because
  `candidate_identity_reason` gates it — and now refuses rather than skips.
- **Blast radius:** guard is scoped to `loop and capture_selector_view`;
  disabled-probe byte-identity and the narrow entry path are regression-tested.
- **Cardinality / injection:** refusal reason codes and the stderr diagnostic
  are built only from the `CUE_BUCKETS` constant and fixed cause strings; a
  regression test asserts no row-supplied `pair_id` reaches either.
- **Contract:** the refusal reuses the existing `BLOCKED_MALFORMED_RESPONSE`
  system record; no schema change. Refusal records are schema-validated in test.
- **Test-honesty finding (self-caught):** the pre-existing happy-path test
  `test_selector_view_mode_captures_all_buckets_and_is_schema_valid` had a
  `"not-an-object"` row baked into its `excluded` bucket and asserted the other
  three rows were still emitted — i.e. the test *enshrined* the F1 bug as
  intended behaviour. It now uses an all-valid response; the non-object case is
  covered by a dedicated refusal test.

### Verification (actual counts at this head)

- `tests.test_autopilot_observe` + `tests.test_autopilot_observe_contract` +
  `tests.test_autopilot_observe_report`: **Ran 54 tests — OK** (was 46 before
  this round; 8 net new). Includes jsonschema validation of both selector-view
  rows and the refusal records.
- Regression tests added this round: whole-tick refusal on malformed rows;
  refusal on non-object and identity-invalid rows (6 sub-cases); bounded/deduped
  reason codes with no `pair_id` leakage; empty buckets are complete (no false
  refusal); strict transcription preserves valid rows incl. exact 400-digit int;
  stderr refusal diagnostic with per-bucket counts; max-runtime guard rejects
  absent/empty/zero/negative (4 sub-cases); bounded loop still starts; guard does
  not affect narrow loop or `--once`; disabled probe unaffected by the guard.
- No Rust surface touched; GitHub Actions `ci.yml` on `claude/**` is the
  canonical Rust gate.
- No host action, deploy, capture, or merge performed by this session.
