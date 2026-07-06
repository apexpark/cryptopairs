# Proposal: AUTO-2B Shadow Dynamic Allowlist

> **Status**: implementation slice proposal.
>
> **Mode**: shadow-only, artifact-only, paper-autopilot advisory evidence.
>
> **Boundary**: this slice must not control `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`,
> submit execution order intents, dispatch orders, call exchanges, change live
> `ENTRY` / `EXIT`, or start hosted loops.

## 1. Context and sources consulted

Verified repo artifacts:

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/ops/ai_workflow.md`
- `docs/ops/codex_prompt_pack.md`
- `docs/proposals/AUTO-2-1m-paper-autopilot-governance.md`
- `docs/superpowers/plans/2026-06-22-auto2-paper-autopilot-sequence.md`
- `tools/scripts/autopilot_observe.py`
- `tools/scripts/autopilot_observe_report.py`
- `tools/scripts/autopilot_paper.py`
- `tools/scripts/autopilot_paper_report.py`
- `specs/contracts/autopilot_paper_report.schema.json`

Operator-provided runtime evidence:

- AUTO-2A direction-gated paper trial `20260628T061640Z`.
- 83 closed paper positions, 57 profitable, +288.9911 realized net bps.
- `PF_TAOUSD__PF_HYPEUSD:COINTEGRATION_Z:SHORT_SPREAD` was negative overall
  because one -118.0464 bps tail loss dominated four small winners.
- Exit-lag buckets showed the best evidence in `<=5m`, `5-15m`, and `>30m`,
  while `15-30m` was negative.

## 2. Slice Loop Check

- **New input consumed**: AUTO-2A static paper evidence plus the explicit
  overfitting concern that manually culling losing legs is not a robust
  universe selector.
- **New state transition**: static paper allowlist review moves to shadow
  dynamic selector evidence over pair/variant/direction candidates.
- **New artifact/runtime/user value**: a schema-backed shadow snapshot records
  selected, rejected, and quarantined candidates with sample, tail, exit-lag,
  score, and static-allowlist disagreement evidence.
- **Why this is not repeating AUTO-2A**: AUTO-2A proved paper ledger mechanics
  for a fixed allowlist; AUTO-2B measures what a dynamic selector would choose
  without acting on that output.
- **Stop/defer condition**: stop if selector output needs to control paper
  entries, mutate runtime config, start a hosted loop, call execution `POST`
  endpoints, use exchange credentials, or relax live safety gates.

## 3. Problem

Manual post-run culling can overfit to one 72-hour window. It is useful for
smoke-test interpretation, but it does not prove the system can robustly select
from the wider `1m` universe.

AUTO-2B therefore introduces a shadow selector that can score and compare
candidate legs without controlling paper entries. This creates the evidence
needed for AUTO-2C's governed dynamic allowlist.

## 4. Design

The selector unit is:

```text
pair_id + timeframe=1m + selected_variant + direction
```

The snapshot consumes closed paper evidence from either:

- strategy paper-trade JSON rows, or
- AUTO-2A paper position JSONL artifacts.

The selector only scores events whose exit timestamp is at or before
`source_cutoff_at`. That boundary is required so replay tests can prove there is
no lookahead into later outcomes.

## 5. Scoring and gates

AUTO-2B uses simple, deterministic scoring so the first shadow selector is
auditable:

```text
score =
  avg_net_bps
  + win_rate_bonus
  + sample_size_bonus
  + tail_loss_penalty
  + exit_lag_penalty
```

Required gates:

- minimum closed positions;
- minimum average realized net bps;
- maximum tail loss;
- maximum average exit lag when exit-lag evidence exists;
- minimum score;
- maximum selected candidate count.

Failure handling:

- insufficient sample -> `SHADOW_REJECTED`;
- negative/low average -> `SHADOW_REJECTED`;
- excessive tail loss -> `SHADOW_QUARANTINED`;
- excessive average exit lag -> `SHADOW_REJECTED`;
- score below threshold -> `SHADOW_REJECTED`.

## 6. Contracts and artifacts

This slice adds:

- `specs/contracts/autopilot_shadow_allowlist_snapshot.schema.json`;
- `specs/examples/autopilot_shadow_allowlist_snapshot.example.json`;
- `tools/scripts/autopilot_shadow_allowlist.py`.

Snapshot output includes:

- selector configuration;
- selected candidates;
- rejected candidates;
- quarantined candidates;
- score components;
- static allowlist comparison, with pair-level static entries expanded across
  observed directions for the same pair/variant;
- methodology and caveat text.

## 7. Safety boundaries

AUTO-2B must not:

- write `.env` or runtime config;
- alter `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`;
- call `POST /v1/execution/order-intent`;
- call dispatch endpoints;
- call exchange APIs;
- create live or paper positions;
- start services or hosted loops.

AUTO-2B output may be reviewed by humans and later consumed by AUTO-2C tests,
but it is not an allowlist for paper entries.

## 8. Acceptance criteria

- Schema and example validate.
- Replay test proves `source_cutoff_at` prevents lookahead.
- Tests prove low sample rejects, tail loss quarantines, and positive evidence
  can shadow-select.
- Tests prove pair-level and direction-level static allowlists compare against
  direction-equivalent shadow selector units.
- Tests prove AUTO-2A position JSONL can be reduced without full decision-row
  loading.
- Tests scan for execution order-intent/dispatch/HTTP client surfaces.
- README/runbook docs show artifact-only usage.
- `CHANGELOG.md` and `docs/AGENT_STATE.md` record the slice state.

## 9. Follow-up boundary

AUTO-2C must add the governor between shadow output and paper eligibility. Only
after AUTO-2C is reviewed can AUTO-2D use governed dynamic output to control
paper entries. Live automation remains a separate AUTO-3 design gate.
