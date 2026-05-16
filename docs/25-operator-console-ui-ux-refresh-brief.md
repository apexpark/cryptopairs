# Operator Console UI/UX Refresh Brief

## Purpose

Refresh the web operator console so it answers three operator questions immediately and safely:

1. Is there a signal?
2. Is that signal approved for trading now?
3. Is the system actually ready to send a live order?

The refresh must preserve fail-closed behavior and make runtime provenance explicit.

## Confirmed Runtime Findings

These findings are facts verified from the current hosted environment on 2026-05-02:

1. The hosted runtime is not a clean GitHub branch deployment. Hetzner is running local branch `rc/live-trial` with host-only changes and a dirty worktree.
2. Strategy cues are being generated continuously across configured pairs and timeframes.
3. Trade-ready cues do not automatically mean operator-approved or executable trades.
4. `trade-now` can exclude a cue even when setup, cost, and trade gates pass.
5. Execution readiness depends on separate fail-closed gates:
   - dispatch mode
   - live credential/config presence
   - kill switch state
   - integrity state per leg
   - account reconcile freshness
6. The current UI exposes parts of this state, but the operator must infer too much from multiple cards and disabled buttons.

## Problem Statement

The current console is informative but not decisive. It mixes:

- research evidence
- policy approval state
- live execution readiness
- host/runtime provenance

This creates a high-risk UX failure mode: the operator can see a strong signal and still not understand why it is not tradable, or whether the blocker is strategic, operational, or deployment-related.

## Goals

1. Make "why can I or can I not trade this now?" answerable in under 5 seconds.
2. Separate research-positive signals from policy-approved opportunities.
3. Separate policy-approved opportunities from execution-ready opportunities.
4. Show runtime provenance and deployment trust state in the UI.
5. Preserve explicit confirmation and fail-closed controls for live actions.

## Non-Goals

1. Autonomous execution changes.
2. Strategy logic changes.
3. Hosted auth redesign.
4. Full design-system migration in the same slice.

## Design Principles

1. Never use a green "ready" state unless policy and execution are both clear.
2. Never hide a blocker behind a disabled button alone.
3. Prefer one canonical status ladder over multiple loosely related badges.
4. Use plain language first. Raw backend terms belong in secondary details, not primary operator copy.
5. Treat provenance as an operator safety input, not a backend detail.
6. Keep research depth available without forcing it into the critical execution path.

## Recommended Information Architecture

### 1. Top Runtime Bar

Add a persistent top bar with:

- environment name
- runtime branch and commit
- dirty/clean runtime state
- dispatch mode
- live credential/config presence
- last reconcile status and age
- kill switch state

This bar answers "what system am I operating?" before the user evaluates any pair.

### 2. Opportunity Table: Four-State Model

Replace the current implicit readiness model with explicit columns:

- `Signal`
- `Approved Now`
- `Ready to Trade`
- `Position`

Recommended meanings:

1. `Signal`
   - research engine sees a current setup
2. `Approved Now`
   - the system currently allows this setup to be considered for trading
3. `Ready to Trade`
   - the system gates currently allow a live submission path
4. `Position`
   - live spread position exists for this pair

This allows the same row to show:

- signal yes
- approved no
- ready to trade no
- position no

without ambiguity.

### 3. Selected Pair Readiness Ladder

For the selected pair, add a single ladder/card stack that shows ordered blockers:

1. Signal setup
2. Cost economics
3. Trading approval
4. Live trading mode
5. Exchange connection ready
6. Left leg market data health
7. Right leg market data health
8. Account freshness
9. Final operator confirmation

Each step must show:

- `PASS`, `WARN`, or `BLOCK`
- one plain-English reason
- optional secondary details with raw source codes or status strings when useful

Examples:

- `BLOCK: This setup is not approved for trading yet.`
  Details: `Approval is paused because the review data is out of date.`
- `BLOCK: Live trading is turned off right now.`
  Details: `Dispatch mode: FAIL_CLOSED.`
- `BLOCK: Account data is too old to trade safely right now.`
  Details: `Reconcile status: STALE_SNAPSHOT.`
- `WARN: This signal is using fallback settings, so treat it with extra caution.`
  Details: `Signal source: LEGACY_ROW_FALLBACK.`

### 4. Trade Action Panel

Keep the manual-first panel, but change the copy to reflect real modes:

1. If dispatch mode is `FAIL_CLOSED`
   - label panel `Simulation / Intent Review`
   - do not imply live arming is sufficient
2. If dispatch mode is `SIMULATE_ACK`
   - label panel `Paper Dispatch`
3. If dispatch mode is `LIVE_KRAKEN`
   - label panel `Live Dispatch`
   - require explicit live arm and operator ID

Buttons should remain disabled when blocked, but every disabled state must have one primary reason and optional secondary reasons.

### 4A. User-Facing Copy Rules

All operator-facing copy should follow this pattern:

1. Lead with the practical meaning.
2. Explain the consequence.
3. Put raw system language in an optional detail, tooltip, or expandable row.

Good:

- `Live trading is turned off right now.`
- `This pair is not approved for trading yet.`
- `We cannot place an order because the account snapshot is out of date.`

Avoid as primary copy:

- `FAIL_CLOSED`
- `STALE_SNAPSHOT`
- `LEGACY_ROW_FALLBACK`
- `PROVENANCE_POLICY_BLOCKED`

### 5. Research Separation

Keep analytics and deep diagnostics, but demote them from the decision path:

- pair rationale codes
- z-score charts
- replay charts
- expectancy sweeps
- candidate inbox

These belong in a `Research` or `Diagnostics` drawer/tab, not mixed into the first-screen trading decision.

### 6. Empty-State Discipline

Do not show empty candidate/optimizer surfaces as if they are active workflows. If inbox/action data is empty or stale:

- state that directly
- explain whether it is expected, unavailable, or failed

## Proposed Visual States

Use one shared token set for all risk-critical states:

1. `PASS`
   - green
2. `WARN`
   - amber
3. `BLOCK`
   - red
4. `INFO`
   - neutral blue/gray
5. `UNKNOWN`
   - muted gray with fail-closed copy

Do not reuse green for "interesting signal" if execution is blocked.

## Copy Changes

Replace vague phrases with causal language:

- `SIM ONLY` -> `Live trading is turned off in the current mode`
- `Trade Now 0` -> `No opportunities are approved for trading right now`
- `Excluded 16` -> `16 signals are currently blocked from trading`
- `No live cues available` -> `No current signals matched this view`

## Implementation Slices

### Slice A: Status Model And Copy

Use existing endpoints only:

- strategy cues
- `trade-now`
- dispatch mode
- kill switch
- integrity decisions
- reconcile
- open trades

Deliverables:

- unified row state model
- readiness ladder
- clearer disabled-state copy

### Slice B: Provenance And Runtime Trust

Expose:

- branch
- commit
- dirty state
- build stamp
- selected config provenance

If runtime metadata is not currently available through an endpoint, this is a PROPOSAL for a minimal read-only status contract.

### Slice C: Layout Cleanup

Refactor Trade page into:

- top runtime bar
- left opportunity table
- center decision card
- right safety rail

Keep charts below the fold or in a diagnostics area.

### Slice D: Shared UI Primitives

Create or standardize shared primitives for:

- status badge
- blocker list
- provenance chip
- action-disabled reason
- risky-action confirmation

## Acceptance Criteria

1. Operator can distinguish `signal present` from `tradable now` without opening diagnostics.
2. Operator can identify the first blocking reason for any pair in one screen.
3. Live actions are impossible when dispatch mode, reconcile, or integrity state is unsafe.
4. Runtime provenance is visible from the Trade page.
5. Layout remains legible at desktop and tablet widths.

## Contract Impact

No contract change is required for the first UI slice if the client composes existing endpoints.

PROPOSAL:

If client-side composition becomes too fragile, add a read-only `trade-readiness summary` contract that returns:

- runtime provenance
- dispatch mode
- credential/config readiness
- pair policy state
- execution gate breakdown

## Testing Guidance For Implementation

When this brief is implemented, minimum verification should include:

1. frontend integration test for each primary blocker state
2. replayable fixture for reconcile stale vs OK
3. integration test for mode-specific panel copy
4. accessibility pass on focus order, contrast, and disabled-state messaging

## Rollout Recommendation

Ship this as a UI-only slice first. Do not combine it with strategy, execution, or hosted auth changes in the same release.
