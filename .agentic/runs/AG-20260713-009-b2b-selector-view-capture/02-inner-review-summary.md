# Inner Review Summary — AG-20260713-009

> **Post-merge Operator ruling — 2026-07-17 (OBS-2, Option 1):** the
> malformed-input/config divergence described below is ratified as fail-closed
> hardening. Historical statements that OBS-2 was open remain as the record of
> each review round and are superseded for current status by this ruling and the
> append-only decisions register. OBS-1, OBS-3, B2-c scope, capture, host,
> deploy, secrets, live trading, and unattended loops remain unauthorized.

Two independent read-only reviewers on commit f4573ec; repairs in the
follow-up commit. 143 tools/scripts tests green at that commit.

> **Round 12 (current head) is the latest round; totals are unchanged from round
> 9**, which supersedes the 143 above and the round-6/7 totals. The authoritative
> counts are under "Round 9 — Codex exact-SHA review of `f9b3e63`" →
> "Verification" (rounds 10, 11 and 12 are documentation-only and change no
> count). Five earlier claims are **withdrawn**: that the probe establishes
> process *identity* — it establishes *kind* only, per OBS-3 (round 10); that any
> procedural rule in the runbook closes the resulting gap — a sequential PID
> recycle defeats them all, so an early stop needs Operator authorization
> (round 11); that verify-then-signal in one process would close it either — that
> is still TOCTOU on a raw PID, and OBS-3 now requires a pidfd (round 12); the
> round-6 claim that
> the narrow paper-feeding loop "does now finish its tick on SIGTERM — an
> improvement" (an unauthorized scope expansion, reverted in round 7), and every
> unqualified "byte-identical" statement about the narrow run or the disabled
> probe (true only on well-formed input; malformed input diverges — open under
> OBS-2). Individual sections below carry dated round-7/round-9 corrections
> inline rather than being rewritten.

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
  summary-identical. (**Round-9 correction:** "byte-identical" is true only on
  well-formed input. The slice's fail-closed hardening also lands on the narrow
  path, so malformed input diverges — open under OBS-2.)
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
network client is constructed. Placed after the disabled-default early return,
so the guard itself never fires on a disabled probe, and scoped to selector-view
loops so the narrow paper-feeding loop's operator-authorized behaviour is
unchanged. (**Round-9 correction:** this originally read "so the disabled probe
stays byte-identical". That is false and was verified so — `load_config` runs
*before* the disabled-default early return, so a malformed quality-windows file
makes even a disabled probe raise where `origin/main` exits 0. The guard's own
placement is still correct; only the byte-identity claim was wrong. Open under
OBS-2.)
A `--once` selector-view run is bounded by construction and exempt.

### F3 — no selector-view stop procedure

The selector-view run writes its own `autopilot_observe_selector_view.pid`, but
the runbook's only stop procedure used the narrow run's `autopilot_observe.pid`
— an operator stopping early had no exact procedure and could signal the wrong
process. **Repair:** a dedicated "Stop the selector-view run" section that
identifies the correct PID file, verifies the PID really is ~~the~~ **a**
selector-view capture (**corrected in round 10:** the check establishes the
process's *kind*, not its *identity* — a concurrent capture or a recycled PID
passes it too; see OBS-3) via `ps` before signalling, uses SIGTERM (~~letting the in-flight tick
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

---

## Round 7 — Codex exact-SHA review of `177cd0e` (4 findings, all repaired)

### F1 — the tick manifest declared no identity

The manifest is the sole positive marker that a tick was captured, so a consumer
keys off its `run_id` / `observed_at` / `timeframe`. The branch constrained none
of them: `run_id` had no `minLength`, both timestamps no `format`, `timeframe` no
`const`. An empty `run_id`, an `observed_at` of `"not-a-timestamp"`, or a `5m`
tick all validated as a captured 1m tick. **Fix:** `run_id` non-empty +
`date-time`; `observed_at` / `source_generated_at` `date-time` (both already
required and non-nullable); `timeframe` `const: "1m"`. Scoped to the *new* branch
only — the entry and selector-view branches are merged contracts from B2-a and
are out of this slice's scope.

**Tests:** `test_tick_manifest_contract_rejects_out_of_contract_identity` — 14
sub-cases, each mutating exactly one field of an otherwise-valid manifest so a
rejection can only be attributed to that field. `format` is annotation-only
unless a validator is handed a `FormatChecker`, and the `date-time` checker
itself silently no-ops without `rfc3339-validator`, so the test asserts the
checker is live before asserting anything else — otherwise every case would pass
vacuously while enforcing nothing. Verified adversarially: against the pre-repair
schema the test fails with exactly the reviewer's cases (`schema accepted empty
run_id`, `schema accepted non-ISO observed_at`, …).

### F2 — the narrow paper-feeding loop had been changed, out of scope

`StopSignal` was installed for `if config.loop:` — every loop. The work order
(AG-20260713-009) requires the narrow run to be byte-identical with the capture
flag false, and names "any change to the entry-candidate emission when the flag
is false" a stop condition. **Fix:** the install, the polling stop (`run_once`'s
`stop=` argument), and the stop-aware sleep are scoped to
`config.loop and config.capture_selector_view`. The narrow loop keeps `stop =
None`, its default signal disposition, and its plain
`time.sleep(config.interval_seconds)` — which also leaves `run_once` on its
always-returns-a-list path, making the abandoned-tick branch dead there.

Round 6 *noticed* this divergence and documented it as "an improvement". That
was the wrong call and is withdrawn: an improvement outside the work order is
still a scope expansion. Shared graceful stopping for the narrow loop is recorded
as **OBS-1** for an Operator scope decision rather than taken here.

**Tests:** `test_stop_handling_is_scoped_to_selector_view_loops_only` and
`test_narrow_loop_sleeps_with_plain_sleep_not_the_stop_aware_sleep` pin the
boundary — nothing else failed when the scoping changed, which is exactly why it
could regress unnoticed. Verified adversarially: re-broadening the install to
`if config.loop:` fails both, reporting the handler armed on the narrow path and
the sleep shortened to `[0.5]` from `[300.0]` — concrete proof the pre-repair
code really did change narrow-loop behaviour.

### F3 — the wording claimed every in-flight tick finishes

Worst instance: the abandoned path printed `"status": "tick_abandoned_on_stop"`
and then, from a shared `stopped_exit()`, `"detail": "…finished the in-flight
tick and exited"` — the log contradicted itself in adjacent lines. **Fix:**
`stopped_exit(detail)` takes the case, and each of the three exits names its own:
abandoned while polling / past abandoning (append completed) / stopped between
ticks. The guarantee is now stated as what it actually is — *no tick is ever left
half-written* — rather than as every tick finishing. Corrected in the docstring,
the loop comments, the runbook (both loops' sections), `CHANGELOG.md`, and
`docs/AGENT_STATE.md`; a repo-wide grep for the stale phrasings returns nothing.

### F4 — audit surfaces refreshed

The 0.2.0 → 0.3.0 contract change and the new manifest example are now declared
in `CHANGELOG.md` (the PR body had said "Schema/examples updated (n/a)", which
was false). Round-6 totals are marked superseded, `docs/AGENT_STATE.md`'s B2-b
row carries the round-7 behaviour and counts, and the PR body's Head SHA and
fresh-review line are refreshed to the pushed head.

### Multi-angle inner review of the round-7 repairs

Three independent read-only reviewers (work-order scope boundary; JSON Schema
contract + test rigour; documentation accuracy). **Both of the following are
defects the repairs themselves introduced or missed, found by that review and
fixed before pushing.**

- **The tightening was unenforceable as written.** The manifest branch declared
  `format: date-time` (RFC 3339), but the freshness gate's predicate is
  `datetime.fromisoformat`, which is strictly *wider*, and `source_generated_at()`
  returns the **raw** string. So a cue response with a naive
  `"2026-06-13T05:29:57"` (no offset), ISO basic `"20260613T052957"`, or a
  one-digit fraction passed the gate and produced a manifest that **failed the
  branch it had just been given** — the tick looked captured while its record
  violated its own contract. Reproduced end-to-end before fixing. **Fix:**
  normalize via `iso(parse_iso(...))` at the selector-view call site, restating
  the instant `parse_iso` already resolved in the form the contract declares.
  Deliberately *not* fixed inside the shared `source_generated_at()`, which also
  feeds entry rows on the narrow path this slice must not touch. Note `iso()`
  truncates to whole seconds — immaterial at 1m, and the canonical form every
  other timestamp here already uses. **Test:**
  `test_emitted_records_are_rfc3339_even_when_the_cue_timestamp_is_not` drives
  the real capture path (not a hand-built record) across four timestamp forms and
  validates every emitted record, manifest and rows alike, under the format
  checker. Verified adversarially: reverting to raw passthrough fails exactly the
  two non-RFC-3339 cases.
- **The F3 fix itself over-claimed, in the same class F3 asked to remove.** "A
  signal during polling abandons the unwritten tick" is not unconditional: the
  flag is tested only at the *top* of each of the seven fetches, so a signal
  during the last one has no boundary left to be honoured at and the tick
  completes and is appended. Verified by experiment — stop during fetch #1 →
  `records=None` (abandoned); stop during fetch #7 → 2 records written. That is
  the *right* behaviour (the tick's data is whole by then), so the code stands
  and the wording was corrected everywhere instead.

Also fixed from the review: the `CHANGELOG` implied the schema constrains
`run_id == observed_at` (it constrains `run_id`'s shape; the equality is a tool
property asserted in tests); the runbook's stop taxonomy omitted the
idle-between-ticks case, which is the common one; and stale "lets the in-flight
tick finish its write" phrasings survived inside this file's own round-6 sections.

Recorded, not fixed:

- **OBS-2 (new, medium)** — the scope reviewer found that B2-b's fail-closed
  hardening *also* changed the narrow run's entry emission, which the work order
  excluded. Independently reproduced by executing `origin/main`'s module against
  the branch's with the flag false: a non-ISO `generated_at`, a NaN `spread_z`, a
  negative `learning_overlay_age_seconds`, and an out-of-enum `dispatch_mode` now
  record `null` instead of passing through; `_optional_int(5.0)` now raises where
  it returned `5`, which is reachable at startup because the narrow run is
  launched with `AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON`. Every one is a
  *hardening*, so "restoring byte-identical" would mean weakening a safety
  property — an Operator call, not this session's. Full options in the follow-up
  row.
- **CI-1** — unchanged and still open: CI never runs `tools/scripts/tests`, so
  this contract and its examples are enforced only when run locally. The round-7
  tests are the repo's only `FormatChecker` users, and `rfc3339-validator` is an
  undeclared dependency — on a plain-`jsonschema` environment the new guard fails
  the suite loudly rather than passing silently, which is the intended direction,
  but it underlines CI-1.

### Verification (clean detached checkout of the pushed commit)

Measured in a clean detached worktree (`git worktree add --detach <sha>`;
`git status --porcelain` empty) — **not** the working tree, which still carries
the untracked macOS " 2.py" duplicates that caused the round-6 F3 miscount.

Canonical command (from `tools/scripts/`):
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -q --import-mode=importlib`

- Full `tools/scripts` suite: **185 passed, 42 subtests passed** (0 failures).
- Focused observe suites (`test_autopilot_observe.py`, `..._contract.py`,
  `..._report.py`): **70 passed, 42 subtests**; `test_autopilot_observe.py` alone
  is **59**.
- Reconciliation: round-6 clean-tree total **181** + **4** new tests → **185**;
  subtests 22 → 42 (+20, from the new sub-case tests). The same command in the
  dirty working tree still reports **196** = 185 + the 11 untracked duplicates,
  reproducing the F3 arithmetic exactly.
- All `specs/contracts/*.json` + `specs/examples/*.json` valid (**111** files,
  `python -m json.tool` — the `contracts` CI job's check), in the clean tree.
  The observe schema is also `check_schema`-valid draft 2020-12, `version` 0.3.0,
  3 `oneOf` branches.
- No Rust surface touched (no `.rs` / `Cargo*` / `rust-toolchain` in the branch
  diff), so the Rust preflight is not implicated this round.
- No host action, deploy, capture, or merge performed by this session.

---

## Round 9 — Codex exact-SHA review of `f9b3e63` (4 P2 findings; 3 repaired, 1 Operator-deferred)

All four reproduced. The Operator scoped the round (2026-07-17): repair 1, 3 and
4; defer 2 to its own work order.

### P2-1 — the runtime bound was measured on a steerable clock

`main()` computed `elapsed` from `utc_now()` (i.e. `datetime.now()`) while
`sleep_until_interval_or_stop` already used `time.monotonic()` — two clocks in
one loop. This bound is the control that keeps a selector-view capture from
running unattended (Autonomy Doctrine; a selector-view loop refuses to start
without a positive `MAX_RUNTIME_SECONDS`), so an NTP correction could steer the
authorized window: a backward step subtracts itself from every later `elapsed`
and the run keeps capturing far past its window; a forward step ends it early.
**Fix:** both ends now read `time.monotonic()`, which cannot be stepped.

**Test:** `test_max_runtime_bound_is_immune_to_wall_clock_steps` advances both
clocks together at 400s/tick and steps only the wall clock. Verified
adversarially by reverting to wall-clock: the control case still passes while
both step cases fail (`10 != 1` — a 6.7x overrun of the authorized window — and
`1 != 5` — an early exit), so the test isolates the clock choice rather than the
harness, and it is the only test in the suite that does.

### P2-3 — the manifest's count consistency was claimed but unenforced

`recorded_rows`' description asserted it "equals the sum of rows_per_bucket",
which the schema does not enforce — the same "text claims more than it enforces"
class as round 7's `run_id` description. The inner review confirmed the gap is
**unclosable in principle here**: draft 2020-12 has no keyword relating two
instance locations arithmetically (`multipleOf` compares to a literal; `$data` is
a non-standard Ajv extension and does substitution, not arithmetic), and the one
real loophole — enumerating the domain via `anyOf`/`const` — needs a finite
domain, while `recorded_rows` and each bucket are unbounded (`minimum: 0`, no
`maximum`). **Fix:** the description now states it as a producer invariant that
is explicitly NOT schema-enforced and that a consumer must re-check, and the
enforcement the schema cannot carry moved into a test.

**Test:** `test_manifest_row_count_invariant_holds_and_is_not_schema_enforced`
first asserts a lying manifest (`recorded_rows: 99` over buckets summing to 3) is
schema-*valid* — pinning the gap so nobody reverts the description to the false
claim — then proves the writer upholds the invariant across empty, lopsided and
populated universes, and end-to-end that the manifest's counts match the rows
actually emitted after it.

### P2-4 — the byte-identity audit was incomplete

Round 8 was scoped to three surfaces; `.agentic/registers/decisions.md:32` still
carried "the narrow paper-feeding run (flag default false) is byte-identical".
**Fix, per the Operator's ruling:** row 32 is left byte-for-byte intact — its
*decision* (pure observational mode) is still valid and only a factual claim in
its rationale is wrong — and a dated correction row is **appended**, per the
register's own "append-only" rule. The diff on that file is one insertion, zero
deletions. A full sweep also corrected `.agentic/registers/agent-runs.md` and two
claims in this file.

### P2-2 — deferred by the Operator

The stop probe proves a process's *kind* (it is *a* selector-view capture), not
its *identity* (it is *the* run you meant to stop). Recorded as **OBS-3** with
the two candidate designs; the Operator deferred it so the redesign gets its own
work order rather than being improvised at the end of this PR. Definite-article
over-claims ("confirms a PID really is **the** selector-view capture") were
corrected in `CHANGELOG.md` and `docs/AGENT_STATE.md` to match what the probe
actually establishes.

### Multi-angle inner review of the round-9 repairs

Three independent read-only reviewers (clock correctness; schema contract + test
rigour; audit completeness + register governance). The schema reviewer found no
defects and independently confirmed the unenforceability premise. The other two
found four defects **in the round-9 repairs themselves**, all fixed before push:

- **The sweep that fixed the incompleteness finding was itself incomplete.** It
  excluded `tools/scripts/tests/` and missed a code comment, leaving the exact
  claim round 9 declares false alive in `autopilot_observe.py` ("so the disabled
  probe stays byte-identical") and in its own test. Both corrected; the
  AGENT_STATE line claiming the audit was "completed" was itself an over-claim
  and now says what was actually swept.
- **The recorded counts were wrong** — 186/45 written before the last test was
  added; the measured clean-tree total is **187/49**. This is the round-6 F3
  error class exactly, caught pre-push this time.
- **Two comment-accuracy defects in the new clock test**, and they are the F3
  sin repeated in the repair for P2-1: the comments said a wall-clock bound
  "never fires" and "would run forever". False — a one-time step still leaves
  `elapsed` growing, so the bound fires late (tick 10), and the real defect is a
  6.7x overrun, not a hang. Reworded to the measured behaviour; the runaway cap
  is now honestly described as a harness guard, not a modelled scenario.
- **A non-conforming register status** (`active — superseded by the eventual
  OBS-2 ruling`) invented a value outside the register's vocabulary and
  pre-announced a supersession that has not happened. Now plain `active`.

Raised and not actioned: the decisions register has no correction mechanism, so a
reader of row 32 alone still sees the false claim with status `active` and no
forward pointer — a register-design gap for the Operator, not a defect in this
repair. `docs/AGENT_STATE.md:48` has a pre-existing unescaped `|` rendering that
row as 5 columns (not introduced here, left alone).

### Verification (clean detached checkout of the pushed commit)

Canonical command (from `tools/scripts/`):
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -q --import-mode=importlib`

- Full `tools/scripts` suite: **187 passed, 49 subtests passed** (0 failures) —
  185 at round 7 plus round 9's 2 tests.
- Focused observe suites: **72 passed, 49 subtests**.
- All `specs/contracts/*.json` + `specs/examples/*.json` valid (**111** files);
  the observe schema is `check_schema`-valid draft 2020-12, `version` 0.3.0, 3
  `oneOf` branches, each example matching exactly one.
- Schema `version` stays **0.3.0**: the only schema edit is a description, so the
  set of records the contract accepts is unchanged — no wire-visible change to
  bump for.
- Narrow paper-feeding run unaffected **by this round's clock change**:
  `max_runtime_seconds` defaults to `None`, the whole `elapsed` block is skipped
  there, and the only narrow-path change is a never-read local, so round 9 alters
  none of its stdout. (This says nothing about the slice's overall byte-identity
  on that path — that remains open under OBS-2.)
- No Rust surface touched; no host action, deploy, capture, or merge performed.

---

## Round 10 — Codex exact-SHA review of `8cbd563` (1 P2, repaired)

Documentation and wording only — **no behaviour, contract or test change** (the
suite is unchanged at 187/49, and the diff touches no logic).

### P2 — OBS-3 was disclosed in the registers but still overclaimed where it counts

Round 9 recorded the kind-vs-identity gap as OBS-3 and corrected the definite
article in `CHANGELOG.md` / `docs/AGENT_STATE.md` — but never audited the
**runbook**, which is the surface an Operator actually acts on. It still said the
probe confirms "**this** selector-view capture", that exit 0 means "it is **safe
to signal**", and then gated the `kill` on that exit code alone. Worse, it framed
the check as the answer to "a PID file can go stale and PIDs get reused" — which
is exactly the case it does *not* cover when the recycled PID belongs to another
capture. A disclosure in a register the Operator does not read during the
procedure is not a disclosure. The finding is correct and was the most
operationally serious of the wording defects: it told a human it was safe to kill
a process on a guarantee the code does not make.

**Repair.** The stop procedure now reads *what the check verifies → the verdict
table → what it does **not** prove → the kill gate*:

- Exit 0 is stated as establishing the process's **kind** (it is *a* selector-view
  capture, decisively not the narrow run), explicitly **not** its **identity**,
  with the two passing cases named (a concurrent capture; a recycled PID held by
  a different capture).
- Two procedural rules stand in until OBS-3: run one capture at a time, and use
  the PID file from the run root you just started (each run writes its PID into
  its own timestamped root, so a PID file you did not just create *is* the stale
  case).
- The kill gate now requires **all three** conditions, not just exit 0.
- `selector_view_argv_matches`' docstring, which claimed "*this* script run in
  selector-view", now states kind-not-identity at the top.

**A mitigation was drafted and then withdrawn on test evidence.** The first draft
told the Operator to cross-check with `pgrep -laf -- "--capture-selector-view"`
and expect exactly one line. Executed against a fake capture it returned **two**
PIDs — the capture and the shell wrapper whose own command line contained the
flag — and BSD `pgrep` silently ignored `-a`, printing bare PIDs. A check that
routinely cries wolf either causes needless escalation or trains the Operator to
ignore it, so it was replaced with the procedural rules above and the runbook now
explicitly warns against that pattern. Recorded because the near-miss is the
lesson: a command in a step card is only a mitigation if it has been run.

**Deliberately not changed, recorded on OBS-3 instead:** the probe emits a field
literally named `safe_to_signal: true` and its `--help` says "exit 0 only if it
is safe to signal". Both assert the safety the check does not establish, but
renaming them changes the tool's output contract — a behaviour change, out of
scope for an audit-wording repair, and any consumer of that JSON would need
updating in step. OBS-3 now carries both, with the resolution depending on its
own outcome: bind the probe to a run and `safe_to_signal` becomes true as named;
leave it unbound and it should be renamed (e.g. `is_selector_view_capture`).

The runbook's procedural rules are honestly a stopgap, not a fix: they rely on
the Operator remembering them, which is precisely what OBS-3 exists to remove.
Stated as such in the row rather than presented as closure.

### Verification (clean detached checkout of the pushed commit)

- Full `tools/scripts` suite: **187 passed, 49 subtests** — unchanged from round
  9, as a wording-only round should be.
- `git diff` vs `8cbd563` touches no executable logic: one docstring, one state
  row, one register row, the runbook, and this file.
- OBS-2, OBS-3 and CI-1 all remain open and unreverted; none is claimed repaired.
- No host action, deploy, capture, or merge performed.

---

## Round 11 — Codex exact-SHA review of `94dec9f` (1 P2, repaired)

Documentation only — no behaviour, contract or test change; suite unchanged at
187/49.

### P2 — the round-10 repair admitted the gap and then closed it with rules that don't

Round 10 correctly stopped the runbook claiming the probe proves identity. Then,
in the next paragraph, it claimed two procedural rules "close the gap": run one
capture at a time, and use the PID file from the run root you started. **They do
not**, and the review's counterexample is exact:

> Capture A writes PID 1234 into A's run root and exits at `MAX_RUNTIME_SECONDS`.
> Capture B later starts and the kernel recycles PID 1234. At kill time only B is
> running — so "one capture at a time" holds. The PID file is the one the
> Operator created, from their own run root — so rule 2 holds. The probe exits 0,
> because B genuinely *is* a selector-view capture. Every condition passes and
> the kill lands on B.

The two captures never coexist, so no "one at a time" rule can exclude the case.
Round 10's rule 1 rested on "the two cases above only arise when a second capture
exists", which is false for a *sequential* recycle. Round 10 had literally named
the recycled-PID case two paragraphs earlier and then asserted rules that don't
cover it — the same self-contradiction class this PR keeps producing, one layer
deeper each time: round 8 fixed the claim in three surfaces and missed a fourth;
round 9 fixed the wording and missed the runbook; round 10 fixed the runbook's
claim and then re-introduced sufficiency underneath it.

Also false and now removed: "**Identity comes from the PID file**, not from this
check." A PID file records a *PID* — precisely the thing that gets recycled. It
identifies a run only while that process is known to have been alive
continuously, which is exactly what is unknown at the moment you ask whether to
signal it.

**Repair.** The runbook no longer presents any set of conditions as sufficient:

- The two habits are kept but demoted to **screening** — they can prove you must
  *not* signal, never that you may — with the sequential-recycle sequence written
  out so the limit is concrete rather than asserted.
- An early stop is **not self-authorizing**: it now requires explicit Operator
  authorization, stating that identity is unverified. There is no procedural
  substitute until OBS-3 lands, and the runbook says so.
- Two pieces of context so escalation is a real decision rather than a shrug:
  the loop **exits by itself** at `MAX_RUNTIME_SECONDS`, so early stops should be
  rare; and the blast radius is *likely* small — at probe time the check does
  reliably exclude the narrow paper-feeding run, so if that still holds at signal
  time the worst case is a graceful SIGTERM to a different selector-view capture
  (observation-only, no trading or eligibility path, no half-written record, at
  most one in-flight tick lost). It is deliberately **not** stated as a bound:
  the probe and the `kill` are separate commands, so a recycle in that window can
  land the signal on a process the probe never saw — including the narrow run,
  which has no handler (OBS-1). Unlikely, not excluded. The inner review of this
  round flagged the first draft of this very sentence for asserting a bound.

**No new mitigation was invented.** Round 10's lesson was that an untested
command in a step card is not a mitigation; round 11's is that an untested
*argument* is not one either. The two mechanisms that would genuinely establish
identity — comparing process start time against the PID file's mtime, and
`readlink /proc/<pid>/fd/1` resolving to this run root's log — are `/proc`-based
and **cannot be tested from this session's macOS host** (a third candidate,
carrying the run id in argv, is recorded alongside them). They are
recorded as OBS-3 candidates, explicitly marked untested, to be validated on the
capture host inside that slice. Prescribing either here would repeat the exact
error being repaired.

OBS-3's row records the withdrawal of the round-10 stopgap and notes the raised
practical priority: until it lands, every early stop costs an Operator decision.

### Inner review of the round-11 repair

One adversarial reviewer, briefed on this PR's documented pattern (each round
fixes an over-claim and reintroduces a subtler one underneath) and told to hunt
for exactly that. It confirmed the runbook repair itself is sound — no residual
sufficiency claim, the sequential-recycle example traced and correct against the
Step 2 launch and the tool's self-exit, and the "no half-written record" clause
CONFIRMED for a wrongly-signalled capture B (B matches argv only because it *is*
a capture, so it installs `StopSignal` before its first tick). It then found the
pattern repeating anyway, in the surfaces the repair did not audit:

- **The withdrawn claims were left standing in the records** — "the PID file
  supplies identity" survived in the OBS-3 row's own opening (the same table cell
  whose round-11 addition says it "is gone"), in the B2-b row, in `CHANGELOG.md`,
  and in `selector_view_argv_matches`' docstring, which still told the reader the
  runbook "carries the procedural rules that stand in until then" while the
  runbook now says there is no procedural substitute. This is round 8's miss
  reproduced exactly: qualified in one surface, unqualified in the records that
  outlive the PR. All corrected.
- **The blast-radius claim was re-asserted as a bound** in both the OBS-3 row and
  this file, unqualified by the TOCTOU window the runbook states two files away.
  The concrete cost: an OBS-3 designer reads the row, budgets against a bounded
  observation-only radius, and never designs for the recycle-between-probe-and-
  kill window — which can land SIGTERM on the narrow paper-feeding run, which has
  no handler (OBS-1). Both now say likelihood, not bound.
- **The OBS-3 candidates carried the round-10 error latently.** Start-time-vs-mtime
  and `readlink /proc/<pid>/fd/1` are both sound in principle (independently
  confirmed), but performed as an Operator eyeball *between* probe and kill they
  are still TOCTOU-exposed — i.e. not fixes at all. The row now states the binding
  constraint: whichever candidate wins must run **inside the signalling tool**.
  (**Corrected in round 12:** that constraint was first written as "atomically
  with the signal — verify-then-signal in one process", which is itself not
  atomic. Reading `/proc` and calling `kill(pid)` are separate syscalls and the
  PID can be recycled between them, so a single process racing on a raw PID
  reproduces the TOCTOU it was meant to close — the same error one layer deeper,
  in the very constraint written to prevent it. The requirement is a stable
  kernel handle: acquire a pidfd, verify, then signal through the pidfd, so a
  recycle fails `ESRCH` instead of hitting a stranger. Recorded on the OBS-3
  row.) Two further holes recorded against candidate (b):
  a capture restarted into an existing `$SV_ROOT` resolves to the same log and
  passes for the wrong run, and a rotated/removed log yields a `(deleted)` path
  that must fail closed.

Found independently and fixed before that review reported: the blast-radius
sentence in the runbook had the same defect, asserting the narrow run was excluded
when the probe only excludes it *at probe time*. The probe and the `kill` are
separate commands with nothing holding the PID between them, so the guarantee does
not survive to the signal. Now stated as a likelihood with the window named.

The meta-lesson, recorded because it is now four rounds old: the failure is not
carelessness in any one sentence, it is **fixing the surface that was cited and
not the class**. Round 8 fixed three surfaces of four; round 9 fixed wording but
not the runbook; round 10 fixed the runbook's claim and re-introduced sufficiency
beneath it; round 11 fixed the runbook and left the records. Every one of these
was caught only because someone swept for the *claim*, not the *citation*.

### Verification

- Full `tools/scripts` suite: **187 passed, 49 subtests** — unchanged, as a
  documentation round should be.
- Diff vs `94dec9f` changes **five** files: `docs/playbooks/autopilot-observe-only-runbook.md`,
  `docs/AGENT_STATE.md`, `CHANGELOG.md`, `tools/scripts/autopilot_observe.py`
  (docstring only) and this record. It touches **no executable Python logic** —
  the normalized AST is unchanged — and no contract or test file.
  (**Round-12 correction:** this line originally read "touches no Python … the
  runbook, the state file, and this record". That was true when written and went
  stale the moment the round-11 inner review added the docstring and CHANGELOG
  repairs; it was never re-checked. A verification record that is not re-derived
  after the last edit is not a verification record.)
- OBS-2, OBS-3 and CI-1 remain open and unreverted; none is claimed repaired.
- No host action, deploy, capture, or merge performed.

---

## Round 12 — Codex exact-SHA review of `713536f` (3 P2s, all repaired)

Documentation only. All three findings were correct; the first is the sharpest
result of this whole sequence.

### P2-1 — "verify-then-signal in one process" is not atomic

Round 11's own OBS-3 constraint — written specifically to stop a racy
identity check — was itself racy. Reading `/proc` and calling `kill(pid)` are
separate syscalls; the target can exit and its PID be recycled between them. A
single process racing on a raw PID reproduces exactly the TOCTOU it was written
to close. Round 11 rejected the Operator-eyeball check for being TOCTOU-exposed
and then prescribed a tool-side check with the same defect, one layer down.

**Repair:** the requirement is now a **stable kernel handle, not a PID**. Acquire
a pidfd (`os.pidfd_open`, Linux 5.3+/Python 3.9+) and signal through it
(`signal.pidfd_send_signal`, Linux 5.1+/Python 3.9+) — a pidfd refers to one
specific process and is never recycled, which is the property
`pidfd_send_signal(2)` exists to provide. **Order is load-bearing and is recorded
as such:** open the pidfd *first*, then verify, then signal through it, so a
recycle in any window leaves the pidfd on the original (dead) process and the
signal fails `ESRCH` — fail closed. Verify-then-open is wrong and must not be
built: a recycle in *that* window is precisely what gets signalled. Fail closed
where the APIs are unavailable, matching the existing `IDENTITY_NOT_VERIFIABLE`
posture. Both APIs confirmed **absent on this macOS host**, so recorded untested,
like OBS-3's other candidates.

### P2-2 — the kill block's guarantees were unconditional

The runbook admitted the PID may change between probe and signal, then told the
Operator SIGTERM "never leaves a half-written record" and described the graceful
stop unconditionally. Authorization does not restore identity — it records that
the Operator accepted an unverified one. If the PID now belongs to the narrow
paper-feeding run (no handler, OBS-1) or anything else, none of those guarantees
hold. **Repair:** the whole section is now explicitly conditional on `$SV_PID`
still referring to a capture, with the narrow-run consequence named; the guarantee
is stated as a property of the capture's *handler* — travelling with the process,
not the PID — and the log tail is framed as the post-signal check that you hit
what you meant to.

### P2-3 — the verification record was false

It claimed the round-11 delta touched "no Python" and listed three files; the
delta is five, including `tools/scripts/autopilot_observe.py` and `CHANGELOG.md`.
The line was true when written and went stale the moment round 11's *own inner
review* added the docstring and CHANGELOG repairs — and was never re-derived.
**Repair:** it now says "no executable Python logic" (AST unchanged), lists all
five files, and carries the correction. The lesson is narrow and worth stating: a
verification record written before the last edit is not a verification record.

### Pattern note

Five consecutive rounds of the same failure, and round 12 sharpens the diagnosis
past round 11's. It is not only "fix the class, not the citation" — P2-1 shows the
fix itself can carry the defect it names, and P2-3 shows the *evidence* can go
stale under the repair that produced it. Both are the same root: a claim asserted
at one moment and never re-checked against the artifact as it finally stands. The
three habits that actually caught things this round were mechanical, not clever:
re-derive every count and file list *after* the last edit; test the primitive
before prescribing it (pidfd's absence here is why it is marked untested); and
grep for the claim across every surface, not the one cited.

### Verification

- Full `tools/scripts` suite: **187 passed, 49 subtests** — unchanged.
- Diff vs `713536f` changes **three** files, re-derived from `git status` after
  the last edit rather than asserted from memory:
  `docs/playbooks/autopilot-observe-only-runbook.md`, `docs/AGENT_STATE.md`, and
  this record. **No `.py` file is in the delta at all** this round, so the
  executable-logic question does not arise. (The first draft of this very line
  said "four files" and then listed three — caught by re-deriving it, which is
  the whole point of P2-3 above.)
- OBS-2, OBS-3 and CI-1 remain open and unreverted; none is claimed repaired.
- No host action, deploy, capture, or merge performed.
