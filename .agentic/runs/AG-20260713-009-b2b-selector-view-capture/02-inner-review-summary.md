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
