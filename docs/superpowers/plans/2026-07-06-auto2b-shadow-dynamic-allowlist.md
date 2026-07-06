# AUTO-2B Shadow Dynamic Allowlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` for review loops or
> `superpowers:executing-plans` for task execution. `AGENTS.md` remains highest
> precedence.

**Goal:** Convert AUTO-2A static paper evidence into a shadow-only dynamic
selection artifact that can score the `1m` pair/variant/direction universe
without controlling paper or live entries.

**Architecture:** AUTO-2B is an artifact-only bridge between static paper
evidence and the later AUTO-2C governor. It reads closed paper evidence, applies
deterministic scoring and fail-closed gates, and emits a schema-backed snapshot.
It does not write runtime config or call services.

**Tech Stack:** Python tooling under `tools/scripts/`, JSON Schema contracts
under `specs/contracts/`, examples under `specs/examples/`, docs under
`docs/proposals/` and `docs/playbooks/`, and Apex review workflow under
`docs/ops/ai_workflow.md`.

---

## File Structure

- Create `docs/proposals/AUTO-2B-shadow-dynamic-allowlist.md`.
- Create `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`.
- Create `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`.
- Create `tools/scripts/autopilot_shadow_allowlist.py`.
- Create `tools/scripts/tests/test_autopilot_shadow_allowlist.py`.
- Create `docs/playbooks/autopilot-shadow-allowlist-runbook.md`.
- Modify `tools/scripts/README.md`.
- Modify `specs/contracts/README.md`.
- Modify `specs/examples/README.md`.
- Modify `docs/AGENT_STATE.md`.
- Modify `CHANGELOG.md`.

---

## Task 1: Design and Contract

**Files:**
- `docs/proposals/AUTO-2B-shadow-dynamic-allowlist.md`
- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`

- [ ] **Step 1: Record the Slice Loop Check**

Include new input, state transition, artifact value, non-repetition, and
stop/defer boundaries.

- [ ] **Step 2: Define shadow-only contract**

The contract must require:

```text
schema_version, mode, generated_at, source_cutoff_at, selector_config,
summary, selected, rejected, quarantined, static_allowlist_comparison,
methodology
```

The mode must be `shadow_dynamic_allowlist_snapshot`.

- [ ] **Step 3: Validate schema/example**

Run:

```bash
python3 -m unittest tools.scripts.tests.test_autopilot_shadow_allowlist.AutopilotShadowAllowlistTests.test_example_matches_schema_and_is_shadow_only
```

Expected: pass.

---

## Task 2: Shadow Selector Tool

**Files:**
- `tools/scripts/autopilot_shadow_allowlist.py`
- `tools/scripts/tests/test_autopilot_shadow_allowlist.py`

- [ ] **Step 1: Implement evidence loaders**

Support:

```text
--paper-trades-json
--positions-jsonl
--paper-dir
--run-config-json
--static-allowlist
```

- [ ] **Step 2: Implement no-lookahead scoring**

Only score events whose exit timestamp is at or before `--source-cutoff-at`.

- [ ] **Step 3: Implement gates**

Required gates:

```text
min_closed_positions
min_avg_net_bps
max_tail_loss_bps
max_avg_exit_lag_seconds
min_score
max_selected
```

- [ ] **Step 4: Write tests**

Cover:

```text
positive leg selects
tail-loss leg quarantines
source cutoff prevents lookahead
low sample rejects
position JSONL latest state and exit lag reduce correctly
CLI emits JSON and Markdown
no execution POST/dispatch/HTTP client surface
```

- [ ] **Step 5: Verify**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_shadow_allowlist.py tools/scripts/tests
python3 -m unittest tools.scripts.tests.test_autopilot_shadow_allowlist
```

Expected: pass.

---

## Task 3: Operator Runbook and State

**Files:**
- `docs/playbooks/autopilot-shadow-allowlist-runbook.md`
- `tools/scripts/README.md`
- `docs/AGENT_STATE.md`
- `CHANGELOG.md`

- [ ] **Step 1: Add runbook**

Include preflight, command, report paths, static comparison, and explicit
non-control caveats.

- [ ] **Step 2: Update state and changelog**

Record AUTO-2B in review and keep AUTO-2C as the next governed dynamic slice.

- [ ] **Step 3: Full verification**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_shadow_allowlist.py tools/scripts/tests
python3 -m unittest tools.scripts.tests.test_autopilot_shadow_allowlist
for f in specs/contracts/*.json specs/examples/*.json; do python3 -m json.tool "$f" >/dev/null || exit 1; done
git diff --check
```

Expected: all pass.
