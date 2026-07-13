# Inner Review Summary — AG-20260713-005

Cross-model dual review of the AUTO-2B slice: two Claude reviewers on the
Codex-authored content (commits 3aa00b1/63e1610/fa8b216) plus the Claude
curation commits (042f917/8f11774). Repairs applied in the follow-up
commit. Codex performs the Tier 3 exact-SHA review of the final head.

## Reviewer A — shadow tool safety + correctness

- Advisory-only boundary: **CLEAN** — stdlib-only imports, no HTTP/
  subprocess/env surface, writes only its own snapshot artifacts;
  tail-loss sign, lookahead cutoff, division guards, schema/example match
  all verified.
- P2: `RANK_OUTSIDE_MAX_SELECTED` demotion and three threshold gates
  untested. **Fix:** tests added for overflow demotion,
  `AVG_EXIT_LAG_LIMIT_BREACHED`, `AVG_NET_BPS_BELOW_THRESHOLD`,
  `SCORE_BELOW_THRESHOLD`.
- P2: snapshot silently dropped rows with no tally. **Fix:** summary now
  counts non-1m, incomplete, deduplicated, open-position, and post-cutoff
  exclusions (schema/example updated; tested).
- P3s fixed: negative exit lag no longer becomes a score bonus (clamped,
  tested); dedupe last-wins documented in the docstring; the
  no-execution-surface test broadened (subprocess/os.system/socket/httpx/
  urllib/os.environ); crash-hard fail-closed behavior documented in the
  runbook. P3 left as-is with rationale: `max_loss_bps` naming (scoring
  unaffected; cosmetic).

## Reviewer B — governance fit + curation

- Governance fit: boundary respected everywhere; runbook operator-invoked,
  loop-free, artifacts gitignored; curation merge verified lossless, all
  SHAs and pin checks pass.
- P2: AUTO-2 §3 requires churn and selector stability to be measurable;
  a single snapshot cannot express them. **Fix:** optional
  `--previous-snapshot-json` produces a `churn` block (added/removed/
  retained/stability ratio vs prior snapshot); schema, example, tests,
  runbook procedure, and proposal acceptance criteria updated.
- P3: AG-20260712-004 register row stale. **Fix:** closed with PR #248
  outcome.

Test suite after repairs: 19 passed (13 original + 6 added).
Verdict after repairs: all P2s closed; one P3 consciously waived with
rationale (cosmetic metric naming); none silently dropped.
