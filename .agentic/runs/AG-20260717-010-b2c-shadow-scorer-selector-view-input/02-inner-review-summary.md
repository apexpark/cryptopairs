# B2-c Inner Review Summary

Date: 2026-07-17
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after repairs; ready for independent Claude review**

## Scope and authority angle

- The changed implementation surface is the artifact-only
  `tools/scripts/autopilot_shadow_allowlist.py`, its tests, the shadow runbook,
  changelog, and the required agent-state/run records.
- No observe/capture producer, service, order-intent, dispatch, exchange,
  runtime allowlist, host, deploy, secret, live-trading, scheduler, OBS-1, or
  OBS-3 surface changed.
- A source search found no network/process/environment execution surface in
  the scorer. The sole paper-allowlist name is in methodology text explicitly
  stating that the advisory artifact cannot control it.
- No capture or host command was executed. The runbook only describes a later
  Operator-authorized B2-d consumption step over completed evidence.

## Contract and data-integrity angle

The reader revalidates the binding B2-a/B2-b shape before aggregation: exact
manifest and row fields, constants, timezone-bearing tick identities, required
and optional value types, complete row and bucket counts, candidate uniqueness,
and a terminating JSONL newline. All complete input ticks validate before the
cutoff is applied, so malformed future rows cannot be hidden by the cutoff.

Finding IR-1: the first implementation checked every value used by the scorer
but accepted unrelated extra fields, some missing nullable required fields, and
an otherwise complete final JSON object without B2-b's terminating newline. It
also keyed duplicate ticks by both raw `run_id` and parsed time, allowing two
lexically different timestamps for the same instant.

Repair: require the exact merged manifest field set and the merged selector-row
required/optional field sets, validate every optional field type, require the
producer's newline terminator, and deduplicate on normalized tick time. Added
adversarial cases for unknown/missing fields, invalid optional values,
unterminated tails, and semantically duplicate timestamps.

The selector path remains structurally separate from realized-paper scoring.
Only set-membership comparisons feed `universe`; selector-stated score and
edge values remain labeled observations, and recursive outcome/PnL/fill fields
are rejected before output.

## Determinism, replay, and operator-reporting angle

- Input paths, eligible ticks, output keys, discovery rows, churn rows, and
  equally ranked failure reasons have explicit stable ordering.
- A forward/reverse input-path replay produces identical ticks and snapshots.
  Large integer observations remain exact rather than being rounded through a
  float conversion.
- Prominent means observed in `TRADE_NOW` at least once; marginal means never
  observed there. This rule is recorded in the work order and runbook.

Finding IR-2: the JSON artifact carried all contracted score, stated-edge,
bucket, gate-reason, and discovery details, but the initial Markdown report
showed only row counts and trade-now ratios.

Repair: render the full score/edge summaries, per-bucket counts, ranked gate
reasons, and advisory selector-only discovery identities in Markdown.

Finding IR-3: the B2-c runbook required paper and selector roots but only the
selector-file discovery failed when its records directory was absent. A typo in
the paper root could silently produce a selector-only snapshot.

Repair: fail before artifact creation unless both explicitly supplied records
directories exist. Selector-only CLI operation remains valid when intentionally
invoked without a paper directory and is explicitly labeled as non-outcome
evidence.

## Evidence

- Test-only mutation checkpoint:
  `8c042948427e8df8e3afc16b4acf80b695de1f6f`. In a clean detached worktree,
  the pre-fix scorer produced **24 failed, 19 passed, 1 warning**. This proves
  the added B2-c tests do not pass against the old implementation.
- Repaired focused suite: **27 passed, 16 subtests passed, 1 warning**.
- Repaired full `tools/scripts` suite: **195 passed, 65 subtests passed,
  1 warning** using `/opt/anaconda3/bin/python3` with external pytest plugin
  autoload disabled.
- `ruff check` and Python byte-compilation: pass.
- Binding snapshot, entry, selector-row, and selector-tick examples: pass
  Draft 2020-12 validation with `FormatChecker`.
- New B2-c runbook shell block: `bash -n` pass.
- `git diff --check origin/main`: pass.
- The one warning is the existing third-party `dateutil` UTC deprecation. The
  system-Python RFC 3339 checker gap remains the separately tracked CI-1 and is
  not represented as passing evidence here.

E3 is met by replaying records from the real B2-b producer helper through the
B2-c reader and scorer into the v2 artifact. E4 is met by the mutation proof,
strict complete-tick failures with no output artifact, recursive outcome-field
rejection, and a regression proving selector and realized aggregates/churn do
not mix.
