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
  `tools/scripts/autopilot_observe_report.py` (attribution of real paper
  trades to observe candidates — not a simulator; verified in inner
  review), `tools/scripts/autopilot_shadow_allowlist.py`
  (realized-evidence scorer, PR #244).

## 2. Slice Loop Check

- **New input consumed**: Operator decision OP-24; the session finding that
  the observe layer's allowlist bounds the discoverable universe.
- **New state transition**: shadow selection moves from "re-rank the static
  shortlist" to "select over the observed universe" — the last structural
  gap between AUTO-2B evidence and a genuinely dynamic AUTO-2C governor.
- **New artifact/runtime/user value**: universe-wide selector-view
  evidence, clearly segregated from realized paper evidence; churn and
  stability measured over the real candidate universe; a discovery list
  with a documented promotion path.
- **Why this is not repeating the prior slice**: PR #244 cannot discover
  any pair outside the paper allowlist by construction; this proposal adds
  the discovery layer it explicitly deferred.
- **Stop/defer condition**: any coupling of selector-view output to
  paper eligibility or execution → out of scope here,
  AUTO-2C+ territory; any host sizing concern (record volume) → stop and
  re-scope with the Operator.

## 3. Problem

The merged AUTO-2B scorer only sees legs that produced closed paper
positions, and paper positions only exist for the static allowlist. The
observe sidecar is doubly narrowed: it is gated by
`AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS`, and — more fundamentally — it
reads only the cue endpoint's `tradable_now` bucket, which is the
selector's already-approved set. The `watchlist` and `excluded` buckets,
where the rest of the universe and the selector's reasoning live, are
never recorded. Consequently:

1. The shadow selector can demote shortlist legs but can never surface a
   new pair: `shadow_only_count` is structurally 0.
2. Churn/stability metrics (§3 exit criteria) are measured over a 4-leg
   universe, which understates real selector churn.
3. "What the champion/challenger would have selected" is answered only
   within the shortlist, which is not what §3 intends.

## 4. Design

Two additive, advisory-only changes. Neither grants any new authority; all
default-deny boundaries hold. **No simulation layer**: this design claims
no outcomes for pairs that have never paper-traded; discovered pairs earn
outcome evidence only via the promotion path in §4.3.

### 4.1 Selector-view capture (observe layer)

The cue endpoint (`strategy_pairs_trade_now_response`) reports three
buckets — `tradable_now`, `watchlist`, `excluded` — and
`tools/scripts/autopilot_observe.py` currently reads only `tradable_now`
(the already-selected set). The change:

- New env `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW` (default **false**,
  fail closed; unset ⇒ behavior identical to today, proven by test). When
  `true`, the tool additionally records one **selector-view row per
  candidate in every bucket** — pair/variant/direction, bucket name, the
  selector's own reason/gate fields as reported by the endpoint, and
  `score_z`/edge fields where present. These rows are observations of the
  champion/challenger's stated view, not entry candidates.
- Selector-view rows carry `"capture_profile": "selector_view"` and a
  `"cue_bucket"` field. This is a **versioned** update to the
  `autopilot_observe_record` contract, and a larger one than a plain field
  addition: the current schema's closed `decision` enum and required
  entry-candidate fields (`quality_window`, `conflicting_live_trade`,
  `dispatch_mode`, `kill_switch_active`, …) fit entry rows only, so the
  bump either adds a `SELECTOR_VIEW_OBSERVED` decision member with a
  conditional (`if/then`) relaxation of entry-only required fields, or
  splits selector-view rows into their own row type within the versioned
  contract. B2-a decides between those two shapes; either way the example
  updates and existing consumers of version-1 records are unaffected.
- Quality windows: selector-view capture bypasses the entry-candidate
  quality gate entirely (it observes the selector, it does not nominate
  entries), so the wide run needs no per-pair windows. The existing
  entry-candidate path and its gates are untouched.
- The capture runs as a **separate, bounded, operator-started run root**
  alongside (not replacing) the trial-supporting narrow capture, with a
  `MAX_RUNTIME_SECONDS`-style bound like the paper loop; the paper loop's
  input stays exactly as reviewed.
- Sizing guard: the runbook budgets record volume (universe size × cadence
  × buckets) and instructs the Operator to confirm disk headroom; the tool
  logs a per-tick row count so growth is visible.

### 4.2 Selector-view input (shadow scorer)

Extend `tools/scripts/autopilot_shadow_allowlist.py`:

- New optional input `--selector-view-jsonl <path...>` consuming
  selector-view rows from a capture window. From these the tool computes
  **selector-view metrics only** — per pair/variant/direction: bucket
  membership over time, time-in-`tradable_now` ratio, candidate frequency,
  score distribution summary, gate-failure reasons — and emits them in a
  new `selector_view` section with its own lists
  (`selector_view_prominent`, `selector_view_marginal`), every row carrying
  `"evidence_kind": "selector_view"`.
- **No outcome claims**: selector-view metrics carry no realized-outcome
  bps and no tool-produced outcome estimate. (Selector-view rows may
  record the selector's own stated `net_edge_bps` as an observation of
  the selector's view — that figure is never treated as an outcome.) The
  realized gates (tail loss, avg net bps) do not apply to selector-view
  rows and no aggregate combines the two evidence kinds. The methodology block
  states selector-view evidence is not PnL, not fill evidence, and not
  permission for any eligibility change.
- Discovery report: a new `universe` block — selector-view universe size
  per bucket, paper-evidenced subset size, `selector_view_only` candidates
  (the discovery list: prominent in the selector's view but absent from
  the static allowlist), overlap with the static allowlist — plus churn
  measured **per evidence stream** when `--previous-snapshot-json` is
  supplied (selector-view churn is the §3 "selector stability/churn"
  quantity measured over the real universe).
- Contract: additive, versioned update to
  `autopilot_shadow_allowlist_snapshot` (new optional fields; existing
  consumers unaffected; example updated; schema version bumped per
  `docs/03-contracts-and-compatibility.md`).

### 4.3 Promotion path and explicit out-of-scope

How a discovered pair earns outcome evidence (the only honest way): the
Operator reads the discovery report, chooses candidates, and adds them to
the **static allowlist of the next operator-started paper window**;
realized paper evidence then accrues and the existing realized scorer
covers them. That decision is per-window, Operator-only, and outside this
tooling.

No change to `autopilot_paper.py`, its allowlist, or any eligibility path.
No scheduler; the selector-view capture is bounded and operator-started.
No service code. Selector-view output feeds human review and later AUTO-2C
design only.

## 5. Safety boundaries

- Selector-view capture is observe-only: the observe tool has no execution
  surface (regression-tested in PR #244's pattern; same test extended to
  the new env handling), and the capture loop is bounded like the paper
  loop — no unbounded background loops (AUTO-2 §8).
- `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW=false` default preserves
  current behavior byte-for-byte when unset (proven by test).
- Shadow output remains advisory; the §3 "not allowed: acting on dynamic
  selector output" boundary is restated in every new artifact section.
- The AUTO-2 §8 stop gates apply unchanged; nothing here touches dispatch
  mode, kill switch, live `ENTRY`/`EXIT`, or promotion.

## 6. Slices (each Tier 3: contracts + autopilot files are protected)

| Slice | Content | Evidence |
|---|---|---|
| B2-a | Versioned contract updates + examples (observe record: `capture_profile`/`cue_bucket`, version bump; snapshot: `selector_view`/`universe` blocks, version bump) | E2: schema validation + example tests |
| B2-b | `autopilot_observe.py` selector-view capture (all cue buckets) + tests; runbook sizing guidance | E3 min (autopilot tooling floor per `.agentic/policies/evidence.md`); E4 for the fail-closed default (test proves unset ⇒ unchanged behavior) |
| B2-c | `autopilot_shadow_allowlist.py` selector-view input + universe/per-stream churn + tests; runbook update | E3 min; E4 for stream segregation (test proves no aggregate mixes evidence kinds) |
| B2-d | Operator evidence pass: bounded selector-view window on host, first universe snapshot, evidence bundle | E5 (operator-run) |

## 7. Acceptance criteria (proposal level)

- All four §3 AUTO-2B exit-criteria quantities measurable **over the
  selector's real universe** (all cue buckets), not only the static
  shortlist.
- Selector-view and realized evidence never combined in any emitted
  number; selector-view rows carry no outcome claims.
- Unset new env ⇒ behavior identical to merged AUTO-2B (proven by test).
- Discovery output (`selector_view_only`) exists, is labeled advisory, and
  the promotion path to real evidence is documented.

## 8. Open questions for the Operator (to answer before B2-b)

1. Bucket scope: capture all three cue buckets (`tradable_now`,
   `watchlist`, `excluded`), or only `tradable_now` + `watchlist`?
   (Default proposal: all three; `excluded` rows carry the gate-failure
   reasons that explain selector churn.)
2. Capture cadence: 60s like the narrow capture, or slower (e.g. 300s) to
   bound record volume for the first window? (Default proposal: 300s —
   selector membership changes slowly relative to entry signals.)
3. Disk budget: acceptable artifact growth per 72h selector-view window
   (estimate provided in B2-b's runbook before any start).
