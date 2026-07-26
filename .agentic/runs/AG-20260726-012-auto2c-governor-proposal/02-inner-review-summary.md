# AUTO-2C Proposal Inner Review Summary

Date: 2026-07-26
Author/reviewer: Codex (Lead Coder, same-agent multi-angle review)
Result: **CLEAN after two documentation repairs; fresh independent Claude
review required**

## Context and sources

- Mandatory governance hydration:
  `AGENTS.md`, `docs/AGENT_STATE.md`, and
  `docs/playbooks/remote-agent-bootstrap.md`.
- Accepted B2-d/B2-cR replay transcript supplied by the Operator.
- Merged B2-c/B2-cR work orders, contracts, implementation, and runbook.
- AUTO-2, AUTO-2B, and AUTO-2B.2 proposals and current governance queue.
- Versioning, compatibility, architecture, data-integrity, risk, testing, and
  observability policies listed in the proposal.

## Scope and authority angle

- Changed paths are limited to the authorized proposal and governance/audit
  surfaces.
- No contract, example, Python/Rust code, test, runbook, CI, dependency,
  service, configuration, artifact, or eligibility input changed.
- The proposal is explicitly non-actuating and does not authorize host work,
  replay, capture, paper/live trading, AUTO-2D/AUTO-3, OBS-1/OBS-3/CI-1, or
  an unattended loop.
- Every unratified numeric or policy default is marked **PROPOSAL**.
- OP-45(e) stops the queue after proposal authoring for an Operator-led
  rebuild.

## Evidence and factual-accuracy angle

- PR #256 exact review head and landing SHA are recorded consistently.
- The accepted replay facts are preserved: 46 closed positions scored, two
  open positions excluded, 849 manifests, 13,584 selector rows, 11,418
  `NONE` rows, one realized-paper identity selected, three rejected, zero
  quarantined, and zero unknown directions.
- `churn.selector_view=null` is described as the absence of a comparable
  prior v2 selector-view block, not as a passing stability signal.
- The proposal binds the accepted paper run, selector run, source cutoff,
  previous snapshot hash, threshold configuration, output path, output hash,
  and exact repository SHA. Those are labelled accepted historical transcript
  facts rather than current host claims.

Finding IR-1: the first proposal draft recorded the aggregate replay counts but
did not bind the accepted replay by its exact paths, cutoff, thresholds, and
snapshot hash.

Repair: add the complete accepted binding facts and explicitly distinguish
them from current host state.

Finding IR-2: the living state still described paper run
`20260713T060641Z` as running and the AUTO-2B.2 implementation as awaiting an
Operator go.

Repair: record the paper run as naturally complete with the accepted
46-closed/two-open treatment and reconcile the merged/evidence-complete
AUTO-2B.2 state.

## Contract and fail-closed angle

- The proposed actionable identity exactly matches the merged selector key:
  pair ID, fixed `1m` timeframe, selected variant, and direction.
- `NONE` remains distinct from null, while both remain non-actionable and
  cannot act as wildcards.
- Realized-paper candidates remain long/short only; unknown selector direction
  values abort before output.
- Realized-paper and selector-view evidence are retained and evaluated as
  separate streams.
- Missing, stale, malformed, incomplete, inconsistent, duplicated, or
  provenance-mismatched inputs fail before artifact creation.
- The current accepted snapshot cannot pass the proposed comparable-history
  gate and therefore cannot confer eligibility.

## Determinism, concurrency, expiry, and audit angle

- Explicit inputs and evaluation time replace latest-file and wall-clock
  discovery.
- Canonical sorting, content-bound decision identity, exclusive output
  creation, no overwrite/repair, and exact-hash input recording are required.
- Expired or blocked decisions never fall back to older decisions.
- A later AUTO-2D consumer must bind one append-only Operator approval to the
  exact decision hash and reject missing, conflicting, expired, or different
  approvals.
- Existing paper exits remain governed by the paper ledger; AUTO-2C performs
  no position or rollback action.

## Governance and versioning angle

- The decisions register change is append-only: three inserted rows and zero
  deletions.
- `docs/AGENT_STATE.md`, the agent-runs register, and the Unreleased
  Governance changelog section agree that B2-d validation is complete,
  AUTO-2C proposal authoring is the final OP-45 step, and implementation is
  unauthorized.
- Proposal-only documentation changes require no version bump.
- The future contract is explicitly proposed as a separately reviewed,
  additive MINOR feature with its own schema version.

## Verification

- `git diff --check`: pass.
- Exact changed/untracked path allowlist: pass.
- Decisions-register append-only check: 3 insertions, 0 deletions.
- Mandatory AGENTS.md planning-section search: pass.
- Exact evidence-binding search: pass.
- Producer/consumer direction boundary inspection: selector directions are
  `LONG_SPREAD`, `NONE`, and `SHORT_SPREAD`; realized-paper directions remain
  `LONG_SPREAD` and `SHORT_SPREAD`.
- Placeholder-marker search: clean.
- No runtime tests were run because this slice changes only proposal and
  governance Markdown; the separately scoped future test plan is recorded.
