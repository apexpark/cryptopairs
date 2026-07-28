# Inner Review Summary — AG-20260728-017

Verdict: `CLEAN`

## Scope reviewed

Reviewed the exact local diff from authorized base
`670bba2e5c31374f5d09018ec86355ec352bd15f` for:

- the separate v2 governor CLI;
- its deterministic synthetic fixture and focused tests;
- the C-d Operator runbook;
- compatibility and CHANGELOG records;
- PR #261 landing reconciliation; and
- append-only run/decision governance.

The unchanged v1 governor, v2 contracts/examples, B2-c, and paper surfaces were
checked by exact SHA-256. No host, real artifact, second v2 window,
configuration, eligibility, AUTO-2D, trading, service, deployment, secret,
CI-1, OBS-1, OBS-3, AUTO-3, or unattended-loop action occurred.

## Review angles

### Contract and deterministic-policy angle

- The output validates against the unchanged v2 schema and passes the merged
  independent v2 semantic auditor.
- Policy hash, prior-set hash, and decision ID use the ratified canonical
  formulas.
- Qualification keeps realized and selector evidence as separate
  set-membership streams.
- Realized-supported candidates must be present in the static baseline for
  this first-transition implementation. Evidence-qualified additions use the
  selector-exploration lane.
- Ranking, exact-key tie-breaks, reserved exploration, concentration
  skip-and-continue, overflow truncation, additions/removals, churn, and
  validity match the merged policy.
- The future previous-accepted-v2-universe source refuses fail closed.

### Fail-closed input and output angle

- Inputs bind absolute normalized paths, exact raw-byte SHA-256 values, and
  producer Git attestations; regular/non-symlink/open-no-follow/stable-read and
  pre/post-output checks are active.
- Duplicate keys, non-finite JSON, malformed bytes, unknown directions,
  realized `NONE`/null, schema-v1/partial selector evidence, reused inputs,
  policy mismatch, and fractional snapshot timing reject without a valid
  artifact.
- Trusted separation, freshness, qualification, and transition failure emit
  schema-valid blocked-empty output only.
- Output uses one exclusive fresh directory, exclusive files, fsync, post-write
  hash/byte verification, no overwrite/repair/reuse, and retained residue on
  failure.
- Concurrent invocations permit exactly one successful output root.

### Authority and operations angle

- Default invocation is bounded, disabled, and performs no file I/O.
- `--enabled` creates only deterministic advisory JSON and Markdown.
- `--verify-only` is strictly read-only and rechecks existing output identity
  through reconstruction; it is explicitly not the independent AUTO-2D
  verifier.
- Every concrete authority field is false. No paper config writer, controller,
  trial start, execution, exchange, service, deployment, or live path is
  imported or exposed.
- The runbook requires exact bindings, one-shot use, retained transcript and
  hashes, no automatic retry, no fallback, partial-root preservation, and
  separate authorization for E3, AUTO-2D, evidence, configuration, and trial
  start.

### Governance and scope angle

- PR #261 is reconciled as landing
  `670bba2e5c31374f5d09018ec86355ec352bd15f`.
- The decisions register has two appended rows and zero deletions.
- CI-1, OBS-1, and OBS-3 remain separately scoped.
- The authorized-path allowlist contains exactly the 12 expected paths once
  this review record is included.

## Findings repaired during inner review

1. Synthetic selected rows were initially passed whole to an exact-key-only
   helper, and blocked decisions initially derived baseline removals despite
   the contract's blocked-empty requirement. The extractor now isolates exact
   identity fields and blocked output clears every outcome/transition set.
2. Verification-only initially lacked a final output identity recheck.
   Existing outputs are now re-read after reconstruction; enabled output is
   also re-read and hash/byte checked, followed by a second input-preservation
   check.
3. Whole-second calculation fields could otherwise round a fractional source
   age open. V2 snapshots now require canonical whole-second generated/cutoff
   timestamps before artifact creation.
4. The first allocation pass could reserve the highest-ranked exploration
   candidate even when its concentration effects made that transition unsafe
   while the next candidate was safe. A deterministic reservation simulation
   now records the candidate-specific concentration skip and continues to the
   next ranked exploration candidate.
5. The final transition check now independently rechecks pair,
   pair/variant/direction, full-instrument, and new-addition instrument caps
   rather than relying only on incremental selection checks.

All repaired behavior is covered by passing focused tests.

## Verification evidence

- Focused v2 governor/runbook suite: **30 passed**, no skips, xfails, or
  placeholders.
- Full canonical `tools/scripts` suite: **327 passed plus 70 subtests**, with
  one pre-existing third-party `dateutil` deprecation warning.
- Draft 2020-12 schema validation with active RFC 3339 format checking passes
  on generated eligible and blocked decisions.
- The merged independent v2 contract auditor passes against generated
  production-shaped synthetic output.
- Ruff passes on both changed Python files.
- Python compilation, 122-file JSON parsing, `git diff --check`, exact
  base/ancestry, 12-path scope allowlist, append-only decision audit, runbook
  config/flag checks, and protected SHA-256 checks pass.
- Bounded E4 covers disabled no-I/O, unsupported-prior refusal,
  malformed/hash/symlink/non-regular/mutation refusal, `NONE`/null/unknown
  direction boundaries, deterministic repeat output, read-only
  reconstruction, collision/concurrency, partial-root retention, transition
  safety, and input preservation.
- Genuine E3: **NOT RUN — separately gated**. No real host file or second
  comparable v2 window was accessed, captured, or represented as E3.

## Residual boundaries

- Producer Git SHA is an Operator attestation whose format is validated and
  recorded; the raw-byte SHA-256 is the offline content binding.
- The stable-file controls match the merged v1 production primitive: the final
  path component is non-symlink/open-no-follow guarded, while a redirected
  ancestor still cannot substitute different accepted content without
  matching the exact raw hash.
- First transition supports only `STATIC_PAPER_ALLOWLIST`. Later accepted-v2
  universe input requires AUTO-2D provenance and a separate reviewed slice.
- A policy-eligible governor decision remains non-actuating and confers no
  paper eligibility. AUTO-2D must be independently implemented and reviewed.

## Next gate

Commit and push one exact head, then open a Tier 3 draft PR. Claude must review
that exact SHA independently and read-only. Any repair push voids the verdict.
Merge remains Operator-only after a CLEAN exact-SHA review, passing required
checks, zero unresolved threads, and mergeability. Genuine E3, AUTO-2D, a
second comparable v2 window, production replay, configuration mutation, and a
bounded paper trial each remain separate Operator gates.
