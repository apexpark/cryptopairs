# AUTO-2 Paper Autopilot Sequence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe 1m paper-autopilot path without allowing champion/challenger selection or live execution to outrun proven paper controls.

**Architecture:** AUTO-2 is split into static paper automation, shadow dynamic selection, governed dynamic selection, dynamic paper automation, and a later live-design gate. The paper ledger is the actuation boundary; champion/challenger output remains advisory until a separate governor proves stability and fail-closed behavior.

**Tech Stack:** Python tooling under `tools/scripts/`, JSON Schema contracts under `specs/contracts/`, examples under `specs/examples/`, operator playbooks under `docs/playbooks/`, and Apex review workflow under `docs/ops/ai_workflow.md`.

---

## File Structure

- Create `docs/proposals/AUTO-2A-static-paper-autopilot.md` for the paper-only design before implementation.
- Create `specs/contracts/autopilot_paper_decision_record.schema.json` for allow/block/entry/exit decisions.
- Create `specs/contracts/autopilot_paper_position.schema.json` for paper position lifecycle records.
- Create `specs/contracts/autopilot_paper_report.schema.json` for aggregate trial output.
- Create matching examples under `specs/examples/`.
- Create `tools/scripts/autopilot_paper.py` for disabled-by-default paper-only operation.
- Create `tools/scripts/autopilot_paper_report.py` for evidence summaries.
- Create tests under `tools/scripts/tests/test_autopilot_paper.py` and `tools/scripts/tests/test_autopilot_paper_contract.py`.
- Modify `docs/playbooks/autopilot-observe-only-runbook.md` only if the observe runbook needs to hand off to the paper runbook.
- Create `docs/playbooks/autopilot-paper-only-runbook.md` for Hetzner run, monitor, stop, and evidence-capture commands.
- Modify `docs/AGENT_STATE.md` at each slice boundary.
- Modify `CHANGELOG.md` for each merged operator-tooling slice.

## Task 1: AUTO-2A Design Gate

**Files:**
- Create: `docs/proposals/AUTO-2A-static-paper-autopilot.md`
- Modify: `docs/AGENT_STATE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the design proposal**

Include these mandatory decisions in `docs/proposals/AUTO-2A-static-paper-autopilot.md`:

```markdown
## Mandatory AUTO-2A Decisions

- Mode is paper-only and disabled by default.
- Active allowlist is static for the first paper trial.
- A repeated observed candidate cannot create a second open paper position for the same pair, variant, timeframe, and direction.
- Entry, block, duplicate-suppression, cooldown, exit, and stale-input decisions are append-only records.
- Live execution-service `POST` endpoints are out of scope and must be guarded by tests.
- Exit simulation must be deterministic and documented before any Hetzner loop is run.
```

- [ ] **Step 2: Add acceptance criteria**

Add this acceptance checklist to the proposal:

```markdown
## Acceptance Criteria

- Focused static allowlist is explicit and bounded.
- Paper entries and exits are represented by contracts, not execution order intents.
- Tests prove no live execution URL is called.
- Tests prove duplicates and cooldowns suppress repeated entries.
- Tests prove stale or malformed source data blocks new entries.
- Runbook includes run, monitor, stop, and report commands.
- Operator-only deployment steps are separated from repo merge.
```

- [ ] **Step 3: Verify docs-only slice**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Open review**

Open a PR with a Reviewer prompt using exact base/head SHAs. Do not merge without Operator approval.

## Task 2: AUTO-2A Contracts And Paper Ledger

**Files:**
- Create: `specs/contracts/autopilot_paper_decision_record.schema.json`
- Create: `specs/contracts/autopilot_paper_position.schema.json`
- Create: `specs/examples/autopilot_paper_decision_record.example.json`
- Create: `specs/examples/autopilot_paper_position.example.json`
- Create: `tools/scripts/autopilot_paper.py`
- Create: `tools/scripts/tests/test_autopilot_paper.py`
- Create: `tools/scripts/tests/test_autopilot_paper_contract.py`
- Modify: `tools/scripts/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing contract tests**

Create tests that validate the examples against the schemas and assert the mode is exactly `paper_only`.

```bash
python3 -m unittest tools/scripts/tests/test_autopilot_paper_contract.py
```

Expected before implementation: fails because schemas/examples do not exist.

- [ ] **Step 2: Create schemas and examples**

The decision schema must include these required fields:

```text
schema_version, mode, run_id, observed_at, decision_type, decision_reason,
pair_id, timeframe, selected_variant, direction, source_generated_at
```

The position schema must include these required fields:

```text
schema_version, mode, paper_position_id, pair_id, timeframe, selected_variant,
direction, status, entry_observed_at, entry_score_z, entry_net_edge_bps,
exit_observed_at, exit_reason, realized_net_bps
```

- [ ] **Step 3: Write failing paper-ledger tests**

Cover:

```text
disabled_by_default
static_allowlist_required
non_1m_blocks
duplicate_candidate_suppressed
cooldown_blocks_reentry
stale_trade_now_blocks
malformed_trade_now_blocks
no_execution_order_intent_url_used
```

- [ ] **Step 4: Implement minimal paper ledger**

Implement `tools/scripts/autopilot_paper.py` so it reads observe-like candidate input, writes append-only paper decisions and positions, and never imports or calls execution `POST` paths.

- [ ] **Step 5: Verify focused Python checks**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_paper.py tools/scripts/tests
python3 -m unittest tools/scripts/tests/test_autopilot_paper.py
python3 -m unittest tools/scripts/tests/test_autopilot_paper_contract.py
git diff --check
```

Expected: all commands pass.

## Task 3: AUTO-2A Runbook And Report

**Files:**
- Create: `specs/contracts/autopilot_paper_report.schema.json`
- Create: `specs/examples/autopilot_paper_report.example.json`
- Create: `tools/scripts/autopilot_paper_report.py`
- Create: `tools/scripts/tests/test_autopilot_paper_report.py`
- Create: `docs/playbooks/autopilot-paper-only-runbook.md`
- Modify: `tools/scripts/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write report tests**

Tests must cover aggregate counts, profitable paper exits, duplicate-suppressed counts, cooldown-block counts, stale-source blocks, and per-pair/direction breakdowns.

- [ ] **Step 2: Implement report**

The report must produce JSON and Markdown outputs from paper decision/position artifacts without requiring direct database access.

- [ ] **Step 3: Add runbook**

The runbook must include:

```text
preflight command
one-shot disabled probe
run loop command
monitor command
stop command
report command
artifact paths
operator-only deployment note
```

- [ ] **Step 4: Verify**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_paper_report.py tools/scripts/tests
python3 -m unittest tools/scripts/tests/test_autopilot_paper_report.py
git diff --check
```

Expected: all commands pass.

## Task 4: AUTO-2B Shadow Dynamic Allowlist

**Files:**
- Create: `docs/proposals/AUTO-2B-shadow-dynamic-allowlist.md`
- Create: `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`
- Create: `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`
- Create: `tools/scripts/autopilot_shadow_allowlist.py`
- Create: `tools/scripts/tests/test_autopilot_shadow_allowlist.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Design shadow selector capture**

The proposal must state that shadow output is read-only and cannot control entries.

- [ ] **Step 2: Implement snapshot capture**

Capture champion/challenger candidate output, static allowlist disagreement, selector churn, sample sufficiency, and freshness.

- [ ] **Step 3: Verify**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_shadow_allowlist.py tools/scripts/tests
python3 -m unittest tools/scripts/tests/test_autopilot_shadow_allowlist.py
git diff --check
```

Expected: all commands pass.

## Task 5: AUTO-2C Governed Dynamic Allowlist

**Files:**
- Create: `docs/proposals/AUTO-2C-governed-dynamic-allowlist.md`
- Create: `specs/contracts/autopilot_dynamic_allowlist_decision.schema.json`
- Create: `specs/examples/autopilot_dynamic_allowlist_decision.example.json`
- Create: `tools/scripts/autopilot_dynamic_allowlist.py`
- Create: `tools/scripts/tests/test_autopilot_dynamic_allowlist.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add governor design**

The proposal must define sample, dwell, churn, concentration, direction, quarantine, and stale-selector gates.

- [ ] **Step 2: Write fail-closed tests**

Tests must prove stale selector, malformed selector, excessive churn, insufficient sample, drawdown quarantine, and concentration breach all block new eligibility.

- [ ] **Step 3: Implement governor**

The governor emits allowlist decisions only; it does not create paper positions or live intents.

- [ ] **Step 4: Verify**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_dynamic_allowlist.py tools/scripts/tests
python3 -m unittest tools/scripts/tests/test_autopilot_dynamic_allowlist.py
git diff --check
```

Expected: all commands pass.

## Task 6: AUTO-2D Dynamic Paper Trial

**Files:**
- Create: `docs/proposals/AUTO-2D-dynamic-paper-trial.md`
- Modify: `tools/scripts/autopilot_paper.py`
- Modify: `tools/scripts/autopilot_paper_report.py`
- Modify: `tools/scripts/tests/test_autopilot_paper.py`
- Modify: `tools/scripts/tests/test_autopilot_paper_report.py`
- Modify: `docs/playbooks/autopilot-paper-only-runbook.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Design dynamic paper enablement**

The proposal must require an explicit config flag that switches from static allowlist to governed dynamic allowlist for paper-only entries.

- [ ] **Step 2: Add tests**

Tests must prove the dynamic paper mode refuses raw champion/challenger output and accepts only governed allowlist decisions.

- [ ] **Step 3: Implement dynamic paper mode**

Reuse the AUTO-2A paper ledger and exits. Do not add any live execution path.

- [ ] **Step 4: Verify**

Run:

```bash
python3 -m compileall -q tools/scripts/autopilot_paper.py tools/scripts/autopilot_paper_report.py tools/scripts/tests
python3 -m unittest tools/scripts/tests/test_autopilot_paper.py
python3 -m unittest tools/scripts/tests/test_autopilot_paper_report.py
git diff --check
```

Expected: all commands pass.

## Task 7: AUTO-3 Live Automation Design Gate

**Files:**
- Create: `docs/proposals/AUTO-3-live-automation-design.md`
- Modify: `docs/AGENT_STATE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Confirm evidence prerequisites**

Require links or artifact paths for:

```text
AUTO-2A static paper report
AUTO-2B shadow dynamic selector report
AUTO-2C governor test evidence
AUTO-2D dynamic paper report
```

- [ ] **Step 2: Write live design proposal only**

The first AUTO-3 slice must be design-only and must not modify runtime code.

- [ ] **Step 3: Apply Apex review gate**

Use exact base/head SHAs, independent Reviewer signoff, and explicit Operator approval before merge.

## Self-Review

- Spec coverage: this plan covers the agreed sequence from focused static paper trial through live-design gate.
- Placeholder scan: no unresolved placeholder markers or open-ended "appropriate handling" language is present.
- Type consistency: paper-only terms are consistently separated from execution order-intent terms.
