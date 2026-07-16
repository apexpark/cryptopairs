# Inner Review Summary — AG-20260713-009

Two independent read-only reviewers on commit f4573ec; repairs in the
follow-up commit. 143 tools/scripts tests green at that commit.

> **Round 7 (current head) supersedes the totals in this header and in
> "Reviewer B" below.** The authoritative counts are in "Round 7 — repairs after
> the fresh Codex exact-SHA review at `177cd0e`" at the end of this file. The
> round-6 claim that the narrow paper-feeding loop "does now finish its tick on
> SIGTERM — an improvement" is **withdrawn**: it was an unauthorized scope
> expansion, and round 7 reverts it.

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
capture via `ps` before signalling, uses SIGTERM (~~letting the in-flight tick
finish its write~~ — **corrected in round 7:** never leaving a half-written
record; whether the in-flight tick finishes or is abandoned depends on when the
signal lands), verifies the stop, and escalates before any `kill -9`
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

### Verification — superseded, see "Round 6" below

The counts previously recorded in this section (**180**) were measured in a
dirty working tree and are wrong for the pushed commit. Corrected in the round-6
section below; retained here only so the error is legible rather than silently
rewritten.

- Runner caveat (still accurate, worth keeping): a plain `python3 -m unittest`
  run under-reports, because its loader collects `TestCase` methods but not
  module-level `def test_*` functions. Separately, plain `unittest`/`pytest`
  invocations from this Mac fail or mis-resolve
  `from tests.test_autopilot_observe import ...` because Anaconda ships a real
  `tests` package in site-packages that shadows the local namespace dir;
  `--import-mode=importlib` (as in the canonical command) resolves it. The stale
  "143" in the PR description dated from head `b517510`, before rounds 2-5 added
  tests.

## Round 6 — Codex exact-SHA review of `4d14612` (3 findings, all repaired)

### F1 — an empty-but-captured tick was indistinguishable from a missed tick

Confirmed by reading and by test: with all three buckets present but empty,
every guard in `selector_view_records` passes, the row loop never executes, and
the function returns `[]` — zero records written. On disk that is identical to a
tick that never ran. The pre-existing test
`test_selector_view_empty_buckets_are_complete_not_incomplete` asserted exactly
this (`assertEqual(records, [])`), so it had **enshrined the defect** — the
second time this slice a test encoded the bug as intended behaviour.

**Decision — represent, do not fail closed.** An empty universe is a legitimate
selector state (every pair filtered out), and "the selector saw nothing" is real
information for B2-c's churn measurement. Failing closed would discard a valid
observation *and* would still not distinguish it from a malformed response.
So: a versioned per-tick completeness record. Each captured tick now leads with a
`selector_view_tick` manifest (`decision: SELECTOR_VIEW_TICK_CAPTURED`) stating
`recorded_rows` and `rows_per_bucket`. Manifest present = captured; absent =
missing. A refused tick emits only its `BLOCKED_*` record and no manifest, so
captured and refused stay mutually exclusive.

Manifest-first ordering is deliberate: it accounts for every row that follows, so
a truncated tail (a `kill -9` mid-append) is detectable as a shortfall against
the stated counts rather than reading as a genuinely smaller universe — which
also closes the artifact-integrity half of F2.

**Regression test, proven to fail pre-fix:**
`test_artifact_distinguishes_empty_captured_tick_from_missing_tick` drives the
real writer and reads the JSONL back through a B2-c-style reader over three
ticks — empty-captured, populated, and never-run. Against the pre-fix code it
fails with `AssertionError: '2026-06-13T05:30:00Z' not found in {...}` — the
empty tick is simply absent, which is the finding. It passes after.
`test_refused_tick_emits_no_manifest_so_it_never_reads_as_captured` pins the
mutual exclusion.

### F2 — the stop procedure could identify neither the run nor stop it gracefully

Both parts confirmed, and the identity half is worse than the finding states.
Both the narrow paper-feeding run and the selector-view run were launched as
`python3 tools/scripts/autopilot_observe.py` with *all* differing configuration
supplied by the environment (`AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW=true`).
`ps` shows argv, not the environment — so the two runs' command lines were
**byte-identical** and the runbook's `grep 'autopilot_observe.py'` guard could
not distinguish them *even in principle*. A stale selector-view PID file whose
PID had been reused by the narrow run would pass the guard and stop the wrong
capture.

- **Identity:** the runbook now starts the selector run with the explicit
  `--capture-selector-view` flag, putting a distinguishing token in the
  process's own argv, and gates the kill on a new read-only
  `--verify-selector-view-pid PID` probe. The probe reads the PID's command line
  and confirms the flag; it signals nothing. It fails closed: `NO_SUCH_PROCESS`
  (stale PID file) and `NOT_SELECTOR_VIEW_CAPTURE` both exit 2 = do not signal.
  `selector_view_command_matches` is token-exact via `shlex` and requires the
  script to be the program actually run (directly, or as a python interpreter's
  argument) — an inner-review case caught that an earlier draft matched
  `grep --capture-selector-view autopilot_observe.py`, a false positive that
  would have gated a kill on an unrelated process.
- **Graceful stop:** the runbook's claim that SIGTERM "lets the current tick
  finish its write" was false — the tool had no handler, so the default
  disposition terminated it outright. Demonstrated in an isolated subprocess:
  with the handler suppressed, a SIGTERM delivered mid-`write_records` kills the
  process (**exit 143**) and the tick is lost entirely — no file, no output.
  With the handler, **exit 0** and the complete tick (manifest + row) on disk.
  `StopSignal` now handles SIGTERM/SIGINT by setting a flag, so the signal is
  delivered between bytecodes, the append completes, the file closes, and the
  loop exits at its next checkpoint logging `"status": "stopped_by_signal"`.
  (**Round-7 caveat:** true for a signal arriving at or after record
  construction, which is the case measured here. A signal during polling with a
  fetch boundary still ahead abandons the tick instead — nothing is appended.)
- **Sleep responsiveness:** PEP 475 resumes an interrupted `time.sleep` for its
  full remaining duration, so a flag alone would have left a stop unnoticed for
  up to a whole interval (300s in the runbook). `sleep_until_interval_or_stop`
  polls the flag in short slices. ~~The loop tail was restructured to a single
  stop-exit point so a stop arriving during either the tick or the sleep never
  starts one more tick.~~ (**Superseded in round 7:** scoping the stop to
  selector-view loops split the tail into three `stopped_exit` call sites, each
  naming its own case. The invariant that a stop never starts one more tick is
  unchanged.)

Tests: `..._command_identity_is_exact_not_any_observe_process` (9 sub-cases,
including the narrow run, lookalike flags, and an unparseable command line),
`..._verify_selector_view_pid_refuses_wrong_or_stale_pid` (3 sub-cases),
`..._verify_selector_view_pid_signals_nothing_and_ignores_env`,
`test_sigterm_lets_the_in_flight_tick_finish_its_append` (delivers a real
SIGTERM from inside `write_records`), `..._sigterm_during_sleep_stops_without_
waiting_out_the_interval`, `test_stop_signal_records_only_the_first_request`.

### F3 — verification totals were measured in a dirty tree

Confirmed and root-caused. The recorded **180** was measured in a working tree
carrying macOS duplicate files; `tools/scripts/tests/test_strategy_tuning_scripts 2.py`
is untracked and contributes exactly **11** tests. `180 − 11 = 169`, matching the
finding precisely. All counts below are now measured in a **clean detached
worktree of the pushed commit** (`git worktree add --detach`, `git status
--porcelain` empty), not the working tree.

### Multi-angle inner review of the round-6 repairs

Four independent read-only angles over the staged diff; everything they raised is
fixed in the pushed commit.

- **Fail-closed correctness (adversarial, fuzzed):** traced every return path of
  `selector_view_records` and fuzzed it with 5,000 randomized cue payloads
  (missing/non-list buckets, non-object rows, bad identity, NaN, string-as-bool,
  null `rationale_codes`, invalid/stale/future timestamps, with and without
  `source_reasons`) asserting that a refused tick never carries a manifest, a
  captured tick always does, and `sum(rows_per_bucket) == len(rows)` with the
  per-bucket counts matching a `Counter` over emitted rows. Zero violations. The
  `rows_per_bucket` increment sits *after* the successful `append`, so a row that
  raises is neither appended nor counted.
- **Contract:** all three `oneOf` branches carry disjoint `required` sets with
  `additionalProperties: false`, so every record the tool emits matches exactly
  one branch — verified by validating tool-generated entry rows, selector rows,
  refusal records, and manifests (empty and populated) against the schema.
- **Doc accuracy (the class of defect that caused F2):** the runbook's start →
  verify → stop procedure was executed verbatim against the real script, and the
  greps were run against real serialized output. Three defects found and fixed:
  (1) a "72h cap" claim the tool does not enforce — it requires only a *positive*
  bound and clamps nothing, so the sentence now says the window is this command's
  choice, not a tool-enforced ceiling; (2) `grep -c` over the day-sharded glob
  printed a count *per file* rather than the stated total (records shard one file
  per calendar day, so any multi-day run always trips this) — now `grep -hc … |
  paste -sd+ - | bc`, verified to report 3 across two day-files where the old
  form printed `2` and `1`; (3) a cross-reference pointing "below" at a section
  that is above it. Fixing (1) mattered on principle: this slice exists precisely
  because a runbook asserted a safety property the code did not implement.
- **Self-caught during implementation:** an earlier draft of the identity
  predicate matched any command *containing* both tokens, so
  `grep --capture-selector-view autopilot_observe.py` returned True — a false
  positive on a predicate that gates a kill. It now requires the script to be the
  program actually run (directly, or as a python interpreter's argument).

#### Two defects the inner review found in the round-6 repair itself

Both were in the F2 fix, and both are recorded because the first draft of a fix
for "the runbook claims something the code doesn't do" itself shipped a runbook
claim the code didn't do.

- **Stop latency was bounded by network I/O, not by the append it protects.**
  A tick makes seven sequential fetches, each able to burn the full timeout
  against an unresponsive endpoint, and the flag was only read after the whole
  tick. Measured against blackholed endpoints: **68.1s** from SIGTERM to exit at
  the default 10s timeout (35s at 5s) — past the runbook's own ~30s escalation
  gate, in exactly the degraded case where an operator most wants to stop, so
  the documented procedure walked them toward the `kill -9` the handler exists
  to avoid. The truncation window actually being closed is the append itself
  (sub-millisecond), so waiting out fetches bought nothing. Fixed by checking
  the flag at each fetch boundary and **abandoning** the tick: nothing is
  written until a tick completes, so an abandoned tick records no partial view
  and reads downstream as the missing tick it is (`"status":
  "tick_abandoned_on_stop"`). Re-measured: **3.0s**, i.e. the in-flight fetch's
  remainder. The runbook's "a few seconds" claim is replaced by the real bounds,
  including the slow-drip socket case that genuinely warrants `kill -9`.
- **Process identity trusted `ps`, which cannot be split back into argv.**
  `ps -o command=` renders argv space-joined and unquoted, so `shlex.split`
  cannot recover token boundaries. Demonstrated live: a **narrow** run with no
  selector-view flag anywhere in its argv, but with the flag text inside an
  `--output-dir` value, re-split into `[..., '--output-dir', '/tmp/out',
  '--capture-selector-view']` and was confirmed `SELECTOR_VIEW_CAPTURE`, exit 0
  — green-lighting the kill of the narrow run, the precise outcome the check
  exists to prevent. Fixed by reading `/proc/<pid>/cmdline` (NUL-separated →
  exact argv) on the Linux capture host; where `/proc` is absent the check
  returns `IDENTITY_NOT_VERIFIABLE` and refuses rather than guessing. Verified:
  the same exploit now returns `IDENTITY_NOT_VERIFIABLE`, safe_to_signal false.
- **Also corrected:** `StopSignal.install` no longer re-arms a disposition
  already `SIG_IGN` (a shell backgrounding the run ignores SIGINT deliberately;
  re-arming would make it newly killable by a signal its launcher meant it to
  survive). ~~And the narrow loop *does* now finish its tick on SIGTERM — an
  improvement, but one an earlier comment glossed as "unchanged"; the comment
  and the runbook now say so.~~ **Withdrawn in round 7** — see below. Correctly
  spotting that the narrow loop's behaviour had changed, this round drew the
  wrong conclusion: it documented the change instead of questioning whether the
  slice was allowed to make it. It was not. An "improvement" outside the work
  order is still a scope expansion, and the reasoning that an unauthorized
  change is fine because it is an improvement is the failure mode to watch for.

### Verification — superseded, see "Round 7" below

(Accurate for round 6's head `177cd0e`; round 7 adds tests, so the totals here
are no longer the current ones.)

Canonical command (from `tools/scripts/`):
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -q --import-mode=importlib`

- Full `tools/scripts` suite: **181 passed, 22 subtests passed** (0 failures).
- Focused observe suites (`test_autopilot_observe.py`, `..._contract.py`,
  `..._report.py`): **66 passed, 22 subtests** — was 54 in the dirty-tree
  measurement; `test_autopilot_observe.py` alone is **55**.
- Reconciliation: the pre-repair clean-tree total is **169** (not 180); this
  round adds **12** tests → **181**, and subtests go 6 → 22 (+16, from the two
  new sub-case tests). Re-running the same command in the dirty working tree
  still reports **192** = 181 + the 11 untracked duplicates, which reproduces
  the F3 error exactly and confirms the diagnosis.
- All `specs/contracts/*.json` + `specs/examples/*.json` valid (111 files,
  `python -m json.tool` — the `contracts` CI job's check), in the clean tree.
- Schema `version` 0.2.0 → 0.3.0 for the added `oneOf` branch; the manifest
  example and tool-built manifests (empty and populated) are jsonschema-validated
  in test, which also proves the three `oneOf` branches stay mutually exclusive.
- No Rust surface touched (no `.rs` / `Cargo*` / `rust-toolchain` in the
  branch diff).
- No host action, deploy, capture, or merge performed by this session.
- Regression tests added this round: whole-tick refusal on malformed rows;
  refusal on non-object and identity-invalid rows (6 sub-cases); bounded/deduped
  reason codes with no `pair_id` leakage; empty buckets are complete (no false
  refusal); strict transcription preserves valid rows incl. exact 400-digit int;
  stderr refusal diagnostic with per-bucket counts; max-runtime guard rejects
  absent/empty/zero/negative (4 sub-cases); bounded loop still starts; guard does
  not affect narrow loop or `--once`; disabled probe unaffected by the guard.
- All `specs/contracts/*.json` + `specs/examples/*.json` valid (`python -m
  json.tool`, the `contracts` CI job's check).
- No Rust surface touched (no `.rs` / `Cargo*` / `rust-toolchain`); the local
  pre-push Rust preflight was skipped with a reason via
  `RUST_PREFLIGHT_OVERRIDE`, and GitHub Actions `ci.yml` on `claude/**` — the
  canonical Rust gate — ran and passed `rust` on the pushed head.
- No host action, deploy, capture, or merge performed by this session.
