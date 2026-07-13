# Code Review — PR #<N> at head SHA <SHA>

Reviewer: <model/agent> · Conduct: read-only · Tree verified clean before and
after.

**SHA discipline: this review is valid only for the head SHA above. If the
branch moves, this verdict is void and a fresh review is required.**

## Checked against

- Project invariants (kill switch never bypassed; fail-closed on stale/unknown
  state; no execution-service order-intent paths from tooling; promotions
  operator-triggered; emergency stop-close always automated once a position
  exists, while discretionary live `EXIT` intents require operator
  confirmation per `docs/12` rules 8–9)
- Correctness of the diff; behavior-asserting tests present
- Protected-path contract compliance (`specs/contracts/**`)
- Slice Loop Check satisfied (PR template)

## Findings

| # | File:line | Severity (P1 block / P2 should-fix / P3 nit) | Confidence | Finding |
|---|---|---|---|---|
| | | | | |

## Verdict

CLEAN | FINDINGS — at SHA <SHA>.
