# Alpha Delivery Control

## Purpose

Keep the remaining alpha scope on-track with low cognitive overhead, especially when interruptions or side requests occur.

Primary control artifacts:
- `plans/alpha_plan.json` (single source of truth)
- `tools/scripts/alpha_tracker.py` (status/checkpoint utility)

## Hard Control Rules

1. One active focus item only (`active_focus_id` in `plans/alpha_plan.json`).
2. Work-in-progress limit: one `IN_PROGRESS` item at a time unless explicitly approved.
3. Every completion claim must include evidence path(s) in the tracker item.
4. Any non-priority request is parked in `sidetrack_queue` before context switching.
5. Resume path after interruption is always:
   - run tracker `summary`
   - review active focus and dependencies
   - execute next action from latest checkpoint

## Daily/Session Cadence

At session start:
1. `python3 tools/scripts/alpha_tracker.py summary`
2. Confirm active focus aligns with highest `NOW` priority and dependency readiness.
3. If not aligned, set focus:
   - `python3 tools/scripts/alpha_tracker.py set-focus --id <n>`

During execution:
1. Keep one item `IN_PROGRESS`.
2. Add evidence incrementally as files/tests are completed.
3. If interrupted by another idea/request, park it:
   - `python3 tools/scripts/alpha_tracker.py park --title "<sidetrack summary>" --return-after-id <focus_id>`

At checkpoint (every major step or context switch):
1. Record delta and next action:
   - `python3 tools/scripts/alpha_tracker.py checkpoint --delta "<what changed>" --next-action "<next concrete step>"`
2. Add blockers if present:
   - `--blocker "<blocker>"`

At completion of an item:
1. Mark done with evidence:
   - `python3 tools/scripts/alpha_tracker.py set-status --id <n> --status DONE --evidence "<path>" --note "<result>"`
2. Move focus to next ready item.

## Status Definitions

- `PENDING`: not started.
- `IN_PROGRESS`: current focus item.
- `BLOCKED`: cannot proceed due to dependency/unknown/safety blocker.
- `DONE`: complete with evidence.

## Side-Track Recovery Protocol

When side-tracked:
1. Park the detour in `sidetrack_queue`.
2. Keep current focus unchanged unless explicitly re-prioritized.
3. Add a checkpoint stating the interruption.

When returning:
1. Run `summary`.
2. Read latest checkpoint.
3. Execute only the recorded `next_action`.

## Evidence Standards

Each DONE item should include at least one of:
- Code path(s) updated
- Test command + pass result
- Schema/example paths
- Runbook/doc updates

This aligns with `docs/17-verification-protocol.md`.

## Example Commands

```bash
python3 tools/scripts/alpha_tracker.py summary
python3 tools/scripts/alpha_tracker.py set-status --id 1 --status IN_PROGRESS --note "Started backend analytics endpoint"
python3 tools/scripts/alpha_tracker.py checkpoint --delta "Added endpoint contract + tests" --next-action "Wire endpoint into web analytics page"
python3 tools/scripts/alpha_tracker.py park --title "Evaluate alternate chart library" --return-after-id 2
python3 tools/scripts/alpha_tracker.py set-status --id 1 --status DONE --evidence "services/strategy-service/src/main.rs" --note "Backtest endpoint merged"
```
