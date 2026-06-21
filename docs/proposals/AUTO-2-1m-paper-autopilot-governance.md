# Proposal: AUTO-2 1m paper-autopilot governance sequence

> **Status**: design and governance proposal. No runtime implementation in this
> slice.
>
> **Author**: codex, 2026-06-22.
>
> **Branch**: `codex/auto2-roadmap-governance`. Base: `main` at
> `94b15b215e00cd1da92d2f6adc651dbc421124ac`.
>
> **Item addressed**: memorialize the operator-approved sequence from
> observe-only evidence to 1m paper automation, while keeping
> champion/challenger selection governed and audit-first.

---

## 1. Context and sources consulted

Verified repo artifacts:

- `AGENTS.md`
- `docs/AGENT_STATE.md`
- `docs/playbooks/remote-agent-bootstrap.md`
- `docs/ops/README.md`
- `docs/ops/ai_workflow.md`
- `docs/ops/codex_prompt_pack.md`
- `docs/proposals/AUTO-1-1m-autopilot-observe-only.md`
- `docs/playbooks/autopilot-observe-only-runbook.md`
- `specs/contracts/autopilot_observe_record.schema.json`
- `specs/contracts/autopilot_observe_report.schema.json`
- `tools/scripts/autopilot_observe.py`
- `tools/scripts/autopilot_observe_report.py`

Operator-provided, non-repo runtime context:

- AUTO-1 observe-only evidence ran on Hetzner for roughly 87 hours.
- The operator-provided attribution report showed positive simulated paper-trade
  attribution across multiple 1m pair/variant/direction keys.
- That evidence supports designing a paper-only automation slice. It is not
  live PnL and does not authorize live order automation.

## 2. Problem

The champion/challenger system can surface candidate pairs and variants, but
candidate selection is not the same control surface as automated actuation.

If a continuously changing champion/challenger allowlist controls an autopilot
before the paper ledger, duplicate suppression, cooldowns, exits, stale-input
handling, and audit trail are proven, bad results become hard to attribute. The
failure could be selection quality, allowlist churn, position lifecycle logic,
exit logic, stale data, or execution gating.

AUTO-2 therefore separates these concerns:

1. prove the paper-autopilot mechanics with a focused static allowlist;
2. shadow the continuous champion/challenger selector without acting on it;
3. add governance rules before dynamic selection can drive paper entries;
4. run a governed dynamic paper trial;
5. consider live automation only after explicit operator approval and a fresh
   design/review cycle.

## 3. Non-negotiable sequence

The following sequence is the project guardrail. Later slices may refine names
or implementation details, but they must not skip the ordering without an
explicit Apex governance exception recorded in the PR.

| Stage | Purpose | Allowed | Not allowed | Exit criteria |
|---|---|---|---|---|
| AUTO-2A - Focused static paper trial | Prove paper-autopilot mechanics with a small static 1m allowlist. | Paper-only entries, paper exits, append-only ledger, deterministic reports. | Dynamic allowlist control, execution-service order intents, live dispatch, exchange calls. | 24-72h paper ledger evidence, duplicate/cooldown/exits verified, no live path reachable. |
| AUTO-2B - Shadow dynamic allowlist | Record what champion/challenger would have selected while static paper trial continues. | Read-only selector snapshots, churn metrics, comparison reports. | Acting on dynamic selector output. | Evidence that selector stability, churn, sample quality, and disagreement with static allowlist are measurable. |
| AUTO-2C - Governed dynamic allowlist | Add safety governor between champion/challenger output and paper eligibility. | Dwell-time, sample-size, churn, concentration, quarantine, and stale-selector gates. | Direct best-candidate-to-entry control. | Tests and reports prove stale or unstable selector state fails closed. |
| AUTO-2D - Dynamic paper trial | Let the governed dynamic allowlist control paper-only eligibility. | Paper-only entries from governed allowlist, with same ledger/risk/exits as AUTO-2A. | Live order intents, live dispatch, exchange calls. | 24-72h dynamic paper evidence and attribution against static/shadow baselines. |
| AUTO-3 - Live automation proposal | Decide whether to design live execution. | Design-only PR, risk model, kill switch, rollout/rollback plan, operator approvals. | Runtime live automation implementation in the same slice. | Separate operator-approved proposal and exact-SHA independent review. |

## 4. Initial AUTO-2A focus

AUTO-2A should use a deliberately small static allowlist so the first trial
isolates the paper-autopilot mechanics.

Current seed candidates from operator-provided observe attribution, to be
re-confirmed from fresh evidence before implementation:

- `PF_SUIUSD__PF_ARBUSD:ROBUST_Z`
- `PF_XBTUSD__PF_BNBUSD:COINTEGRATION_Z`
- `PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z`

These are not a permanent universe. They are a controlled input for proving:

- one candidate becomes at most one paper position in the relevant ready window;
- repeated polling does not create duplicate entries;
- cooldowns suppress immediate re-entry churn;
- exits are deterministic and auditable;
- stale data, stale selector state, malformed responses, kill-switch state, or
  open-position conflicts fail closed;
- every allow/block/exit decision is recorded in an append-only artifact or
  table.

## 5. Dynamic champion/challenger role

The champion/challenger system should become the continuous selector only after
it is governed.

Before AUTO-2C, champion/challenger output is advisory evidence only. It may be
recorded, compared, and analyzed, but it must not directly expand or mutate the
active paper-entry allowlist.

The governor introduced in AUTO-2C must control at least:

- minimum recent sample count;
- minimum recent average net bps or utility score;
- minimum dwell time before addition;
- cooldown after removal or drawdown quarantine;
- maximum additions/removals per hour and per day;
- maximum open paper positions by pair, base asset, and total portfolio;
- direction-specific eligibility where the evidence supports one side but not
  the other;
- selector freshness and schema validity;
- deterministic explanation for every allowlist change.

If the dynamic selector is unavailable, stale, malformed, internally
inconsistent, or too volatile, the governed dynamic allowlist must fail closed
to no new dynamic entries. Existing paper positions may still follow their
configured paper-exit rules.

## 6. Apex harness controls

AUTO-2 work must use the repository's Apex harness workflow:

- `AGENTS.md` remains highest precedence.
- Coder work must be split into small PRs.
- Every PR must include exact files touched, verification, and an exact-SHA
  Reviewer prompt.
- Independent Reviewer signoff is required for the exact head SHA.
- Operator approval is required before merge.
- Host deployment, background loops, and any runtime enablement are
  operator-only unless the Operator explicitly delegates a bounded command.
- Same-chat sub-agent review is advisory only unless the Operator records an
  explicit exception.

Deployment control rule:

- Docs/contracts/tests can merge without host deployment.
- Any host update must have commands that preserve disabled-by-default behavior
  and avoid service restarts unless a runtime implementation slice explicitly
  requires and documents them.
- Any runtime enablement must have a stop command and evidence-capture command
  in the same PR or runbook.

## 7. Contract direction for later slices

AUTO-2A should introduce contracts only when implementation begins. Expected
contracts are:

- `autopilot_paper_decision_record`: one append-only allow/block/entry/exit
  decision at paper-autopilot grain;
- `autopilot_paper_position`: one paper position lifecycle with entry, exit,
  fees/slippage assumptions, and realized net bps;
- `autopilot_paper_report`: aggregate trial evidence over a bounded window.

The contracts must make the mode explicit as paper-only. They must not reuse an
execution-service order-intent schema for paper entries.

## 8. Stop gates

Stop and request operator approval before proceeding if any slice requires:

- live `ENTRY` or `EXIT` intents;
- `POST /v1/execution/order-intent`;
- `POST /v1/execution/order-intent/dispatch`;
- exchange credentials or Kraken API behavior;
- relaxation of dispatch mode, kill switch, or operator-confirmation rules;
- unbounded background loops on Hetzner;
- dynamic selector output controlling eligibility before AUTO-2C is complete;
- bypassing independent Reviewer signoff.

## 9. Acceptance criteria

This governance proposal is acceptable if it:

- prevents project drift from observe-only evidence directly into live
  automation;
- records the focused paper-only trial as the next automation step;
- preserves champion/challenger as the future continuous selector, but only
  through a shadow phase and a governed dynamic allowlist;
- keeps all execution paths disabled and operator-controlled until a later,
  separately approved live proposal;
- ties future deployment work to the Apex harness, exact-SHA review, and
  operator-only host controls.
