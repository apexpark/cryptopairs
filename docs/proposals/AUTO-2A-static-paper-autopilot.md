# Proposal: AUTO-2A focused static paper autopilot

> **Status**: design proposal. No runtime implementation in this slice.
>
> **Author**: codex, 2026-06-23.
>
> **Branch**: `codex/auto2a-static-paper-design`. Base: `main` at
> `598a7e62534f84c5ae25da96cbd434321ed363cd`.
>
> **Item addressed**: define the first paper-only automation design gate after
> AUTO-1 observe-only evidence and AUTO-2 governance.

---

## 1. Context and sources consulted

Verified repo artifacts:

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/proposals/AUTO-1-1m-autopilot-observe-only.md`
- `docs/playbooks/autopilot-observe-only-runbook.md`
- `docs/proposals/AUTO-2-1m-paper-autopilot-governance.md`
- `docs/superpowers/plans/2026-06-22-auto2-paper-autopilot-sequence.md`
- `docs/12-risk-and-execution-policy.md`
- `docs/14-testing-standards.md`
- `docs/15-observability-and-alerting.md`
- `specs/contracts/autopilot_observe_record.schema.json`
- `specs/contracts/autopilot_observe_report.schema.json`
- `tools/scripts/autopilot_observe.py`
- `tools/scripts/autopilot_observe_report.py`

Operator-approved design input:

- AUTO-2A paper exits use a fixed holding window plus exit on the next
  available paper outcome or mark.

## 2. Slice Loop Check

- **New input consumed**: the operator selected fixed holding window plus next
  available paper outcome/mark as the first paper-exit model.
- **New state transition**: moves from observe-only attribution into a designed
  paper-only position lifecycle with entry, open-position, exit, and report
  concepts.
- **New artifact/runtime/user value**: defines how a `1m` would-entry becomes
  at most one auditable paper position with deterministic exit evidence.
- **Why this is not repeating the prior slice**: AUTO-1 recorded candidates
  and attribution. AUTO-2A defines the paper ledger mechanics that will later
  decide entry, duplicate suppression, cooldown, stale-input blocks, and exits.
- **Stop/defer condition**: stop if the design or later implementation requires
  live `ENTRY` or `EXIT`, execution-service `POST` endpoints, exchange/Kraken
  calls, dynamic allowlist control, service restarts, or unbounded hosted loops.

## 3. Problem

AUTO-1 proved that the system can observe `1m` Trade Now candidates without
execution. AUTO-2 established that the next step is not live automation and not
dynamic champion/challenger control. The next missing boundary is paper-only
position lifecycle behavior.

Without a focused static paper trial, an apparent result can be ambiguous. A
bad outcome could be caused by poor candidate quality, duplicated polling,
open-position conflicts, cooldown churn, stale inputs, exit logic, reporting
bugs, or dynamic allowlist churn. AUTO-2A isolates the paper mechanics first.

## 4. Scope

AUTO-2A is a design gate for a later static paper implementation.

In scope:

- a static `1m` pair/variant allowlist;
- disabled-by-default paper-only mode;
- append-only paper decision records;
- append-only paper position lifecycle records;
- duplicate suppression for repeated observed candidates;
- cooldown after paper exit or blocked re-entry;
- fixed holding-window exit simulation;
- stale and malformed input fail-closed behavior;
- report requirements for a 24-72 hour paper trial;
- explicit no-execution-service-POST acceptance tests.

Out of scope:

- live order intents;
- execution-service dispatch;
- exchange or Kraken API calls;
- dynamic champion/challenger output controlling entries;
- stop-loss, take-profit, trailing-stop, or strategy-specific exits;
- hosted service restarts;
- unbounded background loops;
- changing execution-service risk controls.

## 5. Mandatory AUTO-2A decisions

- Mode is paper-only and disabled by default.
- Active allowlist is static for the first paper trial.
- A repeated observed candidate cannot create a second open paper position for
  the same pair, variant, timeframe, and direction.
- Entry, block, duplicate-suppression, cooldown, exit, and stale-input
  decisions are append-only records.
- Live execution-service `POST` endpoints are out of scope and must be guarded
  by tests.
- Exit simulation must be deterministic and documented before any Hetzner loop
  is run.
- The first exit model is fixed holding window plus exit on the next available
  paper outcome or mark.
- If holding-window configuration is absent, invalid, or outside documented
  bounds, new paper entries fail closed.

## 6. Proposed paper lifecycle

The later implementation should treat an observe-like candidate as input, not
as an order intent.

1. Load configuration.
2. If `AUTOPILOT_PAPER_ENABLED` is not explicitly true, emit disabled status
   and do not read or write paper decisions.
3. Load a non-empty static allowlist of `pair_id:selected_variant` entries.
4. Load one or more observe-like candidate records or poll an already approved
   read-only candidate source.
5. Reject all non-`1m` candidates.
6. Reject any candidate outside the static allowlist.
7. Reject stale, malformed, or incomplete candidates.
8. Reject candidates while kill switch, dispatch mode, or open-position safety
   source is unavailable or malformed.
9. Reject candidates when a matching paper position is already open.
10. Reject candidates inside the configured cooldown window.
11. Write an append-only entry decision.
12. Open one append-only paper position record.
13. Keep the position open until its configured holding window expires.
14. At or after expiry, close the position at the next available paper outcome
    or mark.
15. If no valid paper outcome or mark is available, write an append-only
    `EXIT_DEFERRED_MARK_UNAVAILABLE` decision and leave the paper position open.

An open paper position blocks new entries for the same pair, timeframe,
selected variant, and direction. This is the core idempotency rule for the
static paper trial.

## 7. Exit model

AUTO-2A uses only one exit model:

```text
exit_eligible_at = entry_observed_at + hold_window_bars * 60 seconds
exit_at = first valid paper outcome or mark timestamp >= exit_eligible_at
```

Design constraints:

- `hold_window_bars` is required and positive.
- The first implementation should bound `hold_window_bars` to a documented
  range, for example 1 to 240 bars, before allowing entries.
- The mark/outcome source must be read-only and explicitly verified from repo
  artifacts in the implementation slice. This proposal does not assume a new
  service API.
- The exit decision records the source timestamp, source type, realized paper
  net bps when available, and whether the value came from a paper-trade outcome
  or a mark adapter.
- The later implementation must not add stop-loss, take-profit, trailing-stop,
  or strategy-specific exits in AUTO-2A.

This keeps the first paper trial focused on whether entries, dedupe, cooldown,
and reporting work. Richer trade management belongs in a later design after
the static paper ledger has evidence.

## 8. Static allowlist

The static allowlist should be explicit and bounded. The AUTO-2 governance
proposal names these seed candidates from operator-provided observe evidence,
to be reconfirmed from fresh evidence before implementation:

- `PF_SUIUSD__PF_ARBUSD:ROBUST_Z`
- `PF_XBTUSD__PF_BNBUSD:COINTEGRATION_Z`
- `PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z`

These are not permanent selections. They are controlled inputs for proving the
paper lifecycle. The later implementation should block empty allowlists and
should reject allowlist entries that do not parse as exactly one
`pair_id:selected_variant` pair.

Dynamic champion/challenger output remains advisory until AUTO-2B and AUTO-2C
are complete. It must not mutate this allowlist during AUTO-2A.

## 9. Future contracts

This design slice does not add schemas. The implementation slice should add
these contracts before or with paper tooling:

- `specs/contracts/autopilot_paper_decision_record.schema.json`
- `specs/contracts/autopilot_paper_position.schema.json`
- `specs/contracts/autopilot_paper_report.schema.json`

Required contract properties:

- `mode` must be explicit and paper-only.
- Paper records must not reuse execution order-intent schemas.
- Decision records must represent allows, blocks, duplicate suppression,
  cooldown blocks, entries, exit attempts, completed exits, and deferred exits.
- Position records must include lifecycle status, entry metadata, exit metadata,
  hold-window configuration, source timestamps, and realized paper result.
- Report records must aggregate a bounded run window and include methodology
  caveats that the output is paper simulation, not live PnL.

## 10. Failure modes and fail-closed behavior

The later implementation must block new paper entries when:

- the tool is disabled;
- the static allowlist is empty or malformed;
- candidate timeframe is not `1m`;
- candidate pair/variant is not allowlisted;
- candidate direction is missing when direction is part of the paper key;
- candidate source is stale or malformed;
- Trade Now response is unavailable or malformed;
- safety-source reads are unavailable or malformed;
- execution-service reports `FAIL_CLOSED` dispatch mode;
- kill switch payload is unavailable, malformed, or active;
- open-trade/open-position safety source is unavailable or malformed;
- a matching paper position is already open;
- cooldown is active for the key;
- hold-window configuration is missing or invalid;
- paper outcome/mark source is unavailable when attempting exit.

Existing open paper positions may continue to emit exit-deferred records when
marks are unavailable, but the tool must not open replacement positions until
the prior paper position reaches a terminal state and cooldown has elapsed.

## 11. Observability and reporting

The implementation should emit append-only artifacts that let the operator
reconstruct the run without relying on hidden process state.

Minimum report fields:

- run id;
- run start and end timestamps;
- configured static allowlist;
- hold-window bars;
- observed candidates;
- entry decisions;
- open paper positions;
- exited paper positions;
- duplicate-suppressed count;
- cooldown-block count;
- stale-source-block count;
- malformed-source-block count;
- exit-deferred count;
- realized paper net bps by pair/variant/direction;
- caveat that the report is paper-only and not live PnL.

The runbook in the later slice must include run, monitor, stop, and evidence
capture commands before any hosted loop is started.

## 12. Test plan for implementation

The later implementation must use TDD and include focused tests for:

- disabled-by-default behavior;
- empty or malformed static allowlist blocks all candidates;
- non-`1m` candidate blocks;
- stale candidate blocks;
- malformed source blocks;
- duplicate candidate suppression across repeated polls;
- duplicate candidate suppression across process restarts from persisted
  artifacts;
- open-position conflict blocks a second matching paper entry;
- cooldown blocks immediate re-entry after exit;
- invalid hold-window configuration blocks entries;
- expired hold-window closes at the next available paper outcome or mark;
- missing mark/outcome emits an exit-deferred decision rather than fabricating
  PnL;
- generated decision, position, and report examples validate against schemas;
- no execution-service order-intent or dispatch `POST` URL is imported,
  constructed, or called.

Replay tests should prove that the same input artifacts produce the same
decision and position sequence.

## 13. Acceptance criteria

- Focused static allowlist is explicit and bounded.
- Paper entries and exits are represented by contracts, not execution order
  intents.
- Tests prove no live execution URL is called.
- Tests prove duplicates and cooldowns suppress repeated entries.
- Tests prove stale or malformed source data blocks new entries.
- Runbook includes run, monitor, stop, and report commands.
- Operator-only deployment steps are separated from repo merge.
- The first hosted run is 24-72 hours, paper-only, and records evidence before
  any dynamic allowlist control is considered.

## 14. Versioning

This proposal changes no runtime behavior and adds no contract schema. It
requires a `CHANGELOG.md` entry under `Unreleased` / `Operator Tooling`, but no
version bump.

The later implementation slice will require new contract/example entries and
schema validation.

## 15. Next slice

After this design is reviewed and merged, AUTO-2A should continue with the
contracts and paper ledger slice:

1. Add decision, position, and report schemas/examples.
2. Add failing contract and ledger tests.
3. Implement disabled-by-default static paper tooling.
4. Add report tooling and a paper-only runbook.
5. Run exact-SHA review before any hosted execution.

No Hetzner deployment or runtime enablement is part of this design PR.
