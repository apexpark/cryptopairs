# Proposal: AUTO-2B.2 Full-Universe Shadow Selection

> **Status**: PROPOSAL — design only. No implementation in this document's
> PR. Implementation slices require this proposal merged, then the normal
> Tier 3 flow per slice.
> **Item addressed**: Operator decision OP-24 (2026-07-13): extend AUTO-2B
> so the shadow selector runs over all available pairs, not the static
> shortlist.

## 1. Context and sources consulted

- `docs/proposals/AUTO-2-1m-paper-autopilot-governance.md` §3 (AUTO-2B row:
  "Record what champion/challenger **would have selected** while static
  paper trial continues") and §8 stop gates.
- `docs/proposals/AUTO-2B-shadow-dynamic-allowlist.md` (merged slice, PR
  #244): shadow selector scores **closed paper positions** only.
- Operator-provided host evidence (2026-07-13 session): the AUTO-2A run's
  decision ledger shows 167,065 `BLOCKED_NOT_ALLOWLISTED` paper decisions,
  and the observe loop's own log shows `BLOCKED_NOT_ALLOWLISTED` at the
  observe layer — **both funnel layers are allowlisted**.
- `tools/scripts/autopilot_observe.py` (`AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS`),
  `tools/scripts/autopilot_observe_report.py` (attribution over observe
  records with simulated outcomes), `tools/scripts/autopilot_shadow_allowlist.py`
  (realized-evidence scorer, PR #244).

## 2. Slice Loop Check

- **New input consumed**: Operator decision OP-24; the session finding that
  the observe layer's allowlist bounds the discoverable universe.
- **New state transition**: shadow selection moves from "re-rank the static
  shortlist" to "select over the observed universe" — the last structural
  gap between AUTO-2B evidence and a genuinely dynamic AUTO-2C governor.
- **New artifact/runtime/user value**: universe-wide simulated selection
  evidence, clearly segregated from realized paper evidence; churn and
  stability measured over the real candidate universe.
- **Why this is not repeating the prior slice**: PR #244 cannot discover
  any pair outside the paper allowlist by construction; this proposal adds
  the discovery layer it explicitly deferred.
- **Stop/defer condition**: any coupling of wide-observe or simulated
  selection output to paper eligibility or execution → out of scope here,
  AUTO-2C+ territory; any host sizing concern (record volume) → stop and
  re-scope with the Operator.

## 3. Problem

The merged AUTO-2B scorer only sees legs that produced closed paper
positions, and paper positions only exist for the static allowlist. The
observe sidecar — the layer that could see everything — is itself gated by
`AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS`. Consequently:

1. The shadow selector can demote shortlist legs but can never surface a
   new pair: `shadow_only_count` is structurally 0.
2. Churn/stability metrics (§3 exit criteria) are measured over a 4-leg
   universe, which understates real selector churn.
3. "What the champion/challenger would have selected" is answered only
   within the shortlist, which is not what §3 intends.

## 4. Design

Two additive, advisory-only changes. Neither grants any new authority; all
default-deny boundaries hold.

### 4.1 Wide observe capture (observe layer)

Add an explicit opt-in to `tools/scripts/autopilot_observe.py`:

- New env `AUTOPILOT_OBSERVE_ALLOW_ALL_PAIR_VARIANTS` (default **false**,
  fail closed). When `true`, the allowlist gate admits every
  pair/variant/direction the strategy service's cue endpoint reports for
  the `1m` timeframe; all other gates (quality windows optional per pair,
  staleness, schema validation, 1m-only) unchanged.
- Records written by a wide capture carry `"capture_profile": "wide"` (new
  optional field, additive schema change to `autopilot_observe_record`).
- The wide capture runs as a **separate operator-started observe run root**
  alongside (not replacing) the trial-supporting narrow capture, so the
  paper loop's input stays exactly as reviewed.
- Sizing guard: the runbook budgets record volume (universe size × cadence)
  and instructs the Operator to confirm disk headroom; the tool logs a
  per-tick record count so growth is visible.

### 4.2 Simulated-evidence input (shadow scorer)

Extend `tools/scripts/autopilot_shadow_allowlist.py`:

- New optional input `--observe-attribution-json <path>` consuming the
  attribution artifact produced by `autopilot_observe_report.py` over a
  wide-capture window (simulated outcomes per pair/variant/direction).
- Simulated evidence is scored by the **same gates** (min sample, min avg
  net bps, tail loss, score threshold) but into **separate output lists**:
  `simulated_selected`, `simulated_rejected`, `simulated_quarantined`,
  each row carrying `"evidence_kind": "simulated"`. Realized paper rows
  keep the existing lists untouched.
- **Never mixed**: no aggregate combines simulated and realized numbers; a
  candidate present in both streams appears in both, each scored from its
  own evidence. The methodology block states that simulated selection is
  not PnL, not fill evidence, and not permission for any eligibility
  change.
- Discovery report: a new `universe` block — observed universe size,
  paper-evidenced subset size, `simulated_only` candidates (the discovery
  list), overlap with static allowlist — plus churn measured per stream
  when `--previous-snapshot-json` is supplied.
- Contract: additive, versioned update to
  `autopilot_shadow_allowlist_snapshot` (new optional fields; existing
  consumers unaffected; example updated; schema version bumped per
  `docs/03-contracts-and-compatibility.md`).

### 4.3 Explicitly out of scope

No change to `autopilot_paper.py`, its allowlist, or any eligibility path.
No scheduler. No service code. Wide-observe output and simulated selection
feed human review and later AUTO-2C design only.

## 5. Safety boundaries

- Wide capture is observe-only: the observe tool has no execution surface
  (regression-tested in PR #244's pattern; same test extended to the new
  env handling).
- `AUTOPILOT_OBSERVE_ALLOW_ALL_PAIR_VARIANTS=false` default preserves
  current behavior byte-for-byte when unset.
- Shadow output remains advisory; the §3 "not allowed: acting on dynamic
  selector output" boundary is restated in every new artifact section.
- The AUTO-2 §8 stop gates apply unchanged; nothing here touches dispatch
  mode, kill switch, live `ENTRY`/`EXIT`, or promotion.

## 6. Slices (each Tier 3: contracts + autopilot files are protected)

| Slice | Content | Evidence |
|---|---|---|
| B2-a | Contract/schema updates + examples (observe record `capture_profile`, snapshot `simulated_*`/`universe` blocks) | E2: schema validation + example tests |
| B2-b | `autopilot_observe.py` allow-all env + tests; runbook sizing guidance | E2 min; E4 for the fail-closed default (test proves unset ⇒ unchanged behavior) |
| B2-c | `autopilot_shadow_allowlist.py` simulated input + universe/churn blocks + tests; runbook update | E2; E4 for stream segregation (test proves no aggregate mixes kinds) |
| B2-d | Operator evidence pass: wide capture window on host, first universe snapshot, evidence bundle | E5 (operator-run) |

## 7. Acceptance criteria (proposal level)

- All four §3 AUTO-2B exit-criteria quantities measurable **over the
  observed universe**, not only the static shortlist.
- Simulated and realized evidence never combined in any emitted number.
- Unset new env ⇒ behavior identical to merged AUTO-2B (proven by test).
- Discovery output (`simulated_only`) exists and is labeled advisory.

## 8. Open questions for the Operator (to answer before B2-b)

1. Universe source: the strategy cue endpoint's full `1m` pair set, or an
   operator-curated broad list? (Default proposal: cue endpoint set.)
2. Wide-capture cadence: 60s like the narrow capture, or slower (e.g.
   300s) to bound record volume for the first window?
3. Disk budget: acceptable artifact growth per 72h wide window (estimate
   provided in B2-b's runbook before any start).
