# AUTO-2C v2-a Inner Review Summary

Date: 2026-07-28
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after four contract/test/documentation repairs; fresh
independent Claude exact-SHA review required**

## Context and scope

- Hydrated `AGENTS.md`, `docs/AGENT_STATE.md`, and
  `docs/playbooks/remote-agent-bootstrap.md` in the mandatory order.
- Fetched only `origin/main` without tags and proved the branch started at,
  and the live remote still equals, exact authorized base
  `c1b65389ebf0ead41146df12ca49a07f3889cfc9`.
- Inspected the merged AUTO-2C proposal; C-a, C-b, and C-c work orders and
  inner-review records; v1 decision contract/example/tests and governor;
  B2-c snapshot and existing paper contracts/code; compatibility,
  architecture, integrity, risk, testing, observability, versioning, and
  evidence policies; and current governance.
- Changed paths are limited to the separately versioned v2 policy record,
  decision/provenance contracts, five canonical synthetic examples, one
  focused independent test module, compatibility/changelog, C-c completion,
  and AG-20260728-016 governance/audit records.
- No v1/B2-c/paper contract or runtime code, dependency, runbook, CI, host,
  real artifact, capture, paper configuration, eligibility, service,
  deployment, secret, paper/live trading, AUTO-2D implementation, AUTO-3,
  OBS-1, OBS-3, CI-1, merge, or unattended loop changed.

## Contract and policy review

- The v2 decision is a separate schema-version-2 type. It does not relax v1
  in place, and the future v2 AUTO-2D route explicitly rejects v1 decisions
  and raw snapshots.
- Exact identity remains pair ID + `1m` + selected variant + long/short
  direction. Selector `NONE` and null remain separately counted but
  non-actionable. Unknown selector direction and realized-paper `NONE`, null,
  or unknown direction cannot form a valid decision.
- Current and previous evidence references bind raw SHA-256 and producer Git
  SHA, the paper configuration binds the same, governor configuration binds
  raw SHA-256, the canonical policy and prior active set have their own hashes,
  and explicit evaluation time participates in decision identity.
- An eligible decision requires two distinct comparable schema-v2 references
  with present selector evidence and available selector churn, identical
  selector configuration, at least 86,400 seconds of cutoff separation, no
  more than 1,800 seconds of source age, and the ratified per-candidate minima.
- Realized-paper and selector-view evidence remain separate and can interact
  only by exact-key membership. `REALIZED_AND_SELECTOR` and
  `SELECTOR_EXPLORATION` are explicit classes.
- Both ranking lanes use worst-of-two-snapshot components, descending evidence
  strength, and exact-key ascending final tie-break. Allocation reserves the
  best safe exploration addition, fills realized candidates, permits a second
  safe exploration addition, skips concentration failures and continues, and
  records capacity truncation.
- Selection, additions, removals, exploration, pair, instrument, direction,
  churn, validity, paper exposure, cooldown, age, entry, exit-grace, and hard
  runtime limits are fixed constants. Churn is prior/proposed symmetric
  difference divided by `max(4, prior active count)`. No fallback is permitted.
- `POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` remains non-actuating. The governor
  cannot approve or consume itself. Every AUTO-2D verification requirement is
  explicit and every governor authority boundary is false.
- The additive paper-provenance companion binds an immutable synthetic trial
  universe and paper decision/position records to one independently verified
  v2 decision. It replaces no existing paper contract and keeps all
  live/exchange/execution/deployment/service authority false.

## Inner-review findings and repairs

### IR-1 — lifecycle duration values were only derivable

The first provenance draft recorded timestamps and some paper caps but omitted
explicit fields for the 300-second automatic-start age, 86,400-second entry
window, 3,600-second exit grace, and 90,000-second hard runtime. A later audit
would have had to infer policy by reading a separate decision.

Repair: add all four constants to every provenance record and schema, assert
deadline arithmetic, and mutation-test every value.

### IR-2 — eligible status did not force complete comparable selector history

Snapshot references required schema version 2, but the eligible conditional
initially allowed `selector_view_present` or
`selector_view_churn_available` to be false.

Repair: eligible decisions now require both flags true for both snapshots, with
focused mutations proving each false value is rejected.

### IR-3 — blocked-evidence wording discarded useful audit facts

The first documentation pass said a blocked decision must erase candidate
evidence. That was stricter than the safe boundary and would hide candidates
when qualification completed before a later transition/churn gate blocked.

Repair: blocked decisions require empty selection steps, selected,
truncated/skipped outcomes, additions, removals, and retained transition
state. Already-qualified candidate evidence may remain for audit after a
later global block; the canonical early-stale example has none. No fallback or
authority is introduced.

### IR-4 — boundary mutations did not directly cover every output family

The first focused suite proved the canonical paths but did not explicitly
mutate output cardinality, comparable-history flags, every direction/authority
boundary, and every provenance lifecycle constant.

Repair: expand the focused suite to 36 passing tests with explicit max-item,
history, direction, independent-verification, authority, and lifecycle
mutations.

## Governance and versioning review

- The decisions-register change is append-only: two rows added, zero deleted.
- PR #260 CLEAN head/landing, C-c completion, the Operator's accelerated queue
  reset, exact v2 policy, this BUILD authorization, and the later-slice stops
  are consistent across the policy record, work orders, decisions,
  agent-runs, living state, compatibility, and changelog.
- V2 is an additive MINOR-level contract family. V1, B2-c, paper contracts,
  runtime code, package versions, dependencies, release, and tags are
  unchanged.
- CI-1 remains open and separately scoped. The system Python diagnostic still
  reproduces its known missing RFC 3339 validator: 295 tests pass and two
  pre-existing observe guards fail loudly. The canonical local environment
  has active format validation and passes fully.

## Verification evidence

- Focused v2 contract suite: **36 passed**, no skips, xfails, or placeholders.
- Full canonical `tools/scripts` suite from `tools/scripts` under the
  repository's format-capable environment: **297 passed plus 70 subtests**,
  with one pre-existing third-party deprecation warning.
- Both Draft 2020-12 schemas and all five canonical examples validate with an
  active self-contained RFC 3339 checker.
- All 120 contract/example JSON files parse.
- Independent tests recompute policy hash, prior-set hash, decision ID,
  ranking, selection/truncation, transition sets, concentration, churn,
  cutoff/freshness/validity, and provenance deadline arithmetic.
- Ruff, Python compilation, `git diff --check`, authorized-path allowlist,
  exact-base/branch/ancestry checks, and append-only decision audit pass.
- V1 decision contract/example/focused test, B2-c/v1 governor, paper decision
  and position contracts, and paper tool match their exact base SHA-256
  values.
- No production Python or Rust code changed; E3/E4 are not claimed or needed
  for this contract-only slice.

E2 is achieved. The result remains synthetic and non-actuating.

## Next gate

Commit and push one exact head, then open a Tier 3 draft PR. Claude must review
that exact SHA independently and read-only. Any repair push voids the verdict.
Merge remains Operator-only after a CLEAN exact-SHA review, passing required
checks, zero unresolved threads, and mergeability. V2 governor/runbook work
cannot begin without a separate later authorization.
