# Proposal: X3 reporting alignment diagnostics

> **Status**: design proposal. No implementation in this PR.
>
> **Author**: codex, 2026-05-08.
>
> **Branch**: `codex/x3-reporting-alignment-diagnostics`. Sprint base:
> `codex/fix-clippy-run-24549051096`.
>
> **Item addressed**: X3 in `docs/AGENT_STATE.md` §"Cross-cutting".

---

## 1. Context and verified facts

X3 is deferred until after Slice C neutral champion selection lands and is
observed. This proposal does not implement Slice C, change public contracts, or
change runtime behavior.

Verified repo facts:

- `docs/AGENT_STATE.md` marks X3 open and deferred until after Slice C lands
  and legacy-row behavior is observed.
- `docs/26-champion-selection-integrity-fix-spec.md` requires clear separation
  between evaluated-best variant, stored champion variant, and transition
  decision.
- `docs/proposals/SLICE-C-host-lineage-and-implementation.md` says Slice C must
  preserve Slice A `selection_state` semantics and must not collapse
  `selection_state.best_variant` and `selection_state.stored_champion_variant`
  back into one ambiguous `selected_variant`.
- `docs/03-contracts-and-compatibility.md` allows additive optional fields
  without a breaking bump and treats field-meaning changes as breaking.
- `docs/02-versioning-and-releases.md` classifies optional schema fields and
  new metrics/log fields as backward-compatible MINOR-class changes.
- `specs/contracts/strategy_pairs_backtest_response.schema.json` requires
  top-level `selected_variant`.
- `specs/contracts/strategy_pairs_live_z_response.schema.json` requires
  top-level `selected_variant`.
- `specs/contracts/strategy_pairs_paper_trades_response.schema.json` requires
  `rows[].selected_variant`.
- `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`
  requires `rows[].selected_variant`.

## 2. Problem

Backtest, live-z, paper-trades, and opportunity-history responses still expose
only legacy `selected_variant` as their selected strategy-variant identity.
After Slice C, operators need diagnostics that explain whether that value
represents:

1. the neutral evaluated-best variant;
2. a stored champion presentation/projection;
3. a historical row written before diagnostics existed; or
4. an unavailable or inconsistent state that must not be treated as selection
   proof.

Redefining `selected_variant` would break compatibility and would make old
payloads ambiguous. X3 should add diagnostics beside the existing field.

## 3. Scope and non-goals

In scope for the later X3 implementation PR:

- additive response diagnostics for backtest;
- additive response diagnostics for live-z;
- additive per-row diagnostics for paper-trades history;
- additive per-row diagnostics for opportunity history;
- schema/example updates and validation for those four response contracts.

Out of scope:

- removing, renaming, replacing, or redefining `selected_variant`;
- changing Slice C neutral-selection behavior;
- recanonicalizing `LEGACY_ROW_FALLBACK` rows;
- making reporting diagnostics trade-eligibility proof;
- adding new dependencies;
- broad UI redesign.

## 4. Compatibility rules

The implementation PR must follow these rules:

1. Keep every existing `selected_variant` field in place and required exactly
   where it is required today.
2. Do not change the existing enum on backtest/live-z `selected_variant`.
3. Do not tighten paper-trades or opportunity-history `selected_variant` from
   string to enum in the same change, because that could reject previously valid
   persisted rows.
4. Add diagnostics as optional properties only.
5. When diagnostics are unavailable, report unavailability explicitly rather
   than inferring from current selected rows at read time.
6. Treat diagnostic inconsistency as research-visible only and fail closed for
   any downstream trading interpretation.

## 5. Recommended diagnostic shape

**PROPOSAL:** add one optional object named `selection_diagnostics` wherever the
legacy `selected_variant` currently appears as the main variant identity for
the surface.

Recommended field set when the object is present:

| Field | Type | Meaning |
|---|---|---|
| `status` | enum | `AVAILABLE`, `UNAVAILABLE`, or `INCONSISTENT`. |
| `unavailable_reason` | string or null | Machine-readable reason when `status != AVAILABLE`. |
| `selected_variant_role` | enum | Relationship between sibling `selected_variant` and diagnostic state: `EVALUATED_BEST`, `STORED_CHAMPION_PROJECTION`, or `UNKNOWN`. |
| `best_variant` | string or null | Neutral evaluated-best variant from Slice A/Slice C selection state. |
| `best_opportunity_score` | number or null | Score for `best_variant` when available. |
| `stored_champion_variant` | string or null | Stored champion variant at evaluation/write time. |
| `stored_champion_score` | number or null | Stored champion score when available. |
| `transition_decision` | enum or null | `INITIALIZE`, `UNCHANGED`, `KEEP_CHAMPION`, or `PROMOTE_CHALLENGER`. |
| `score_delta_to_champion` | number or null | Best-minus-champion score delta when available. |
| `drift_active` | boolean or null | Whether best variant and stored champion differ. |
| `source` | enum or null | Mirror of cue selection source when available. |
| `validation_state` | enum or null | Mirror of cue validation state when available. |

Recommended enum values should match
`specs/contracts/strategy_pairs_cues_response.schema.json` where the same
concept already exists. New enum values must be additive and documented in the
contract description.

## 6. Surface-specific recommendation

### Backtest response

Future contract:

- `specs/contracts/strategy_pairs_backtest_response.schema.json`

Future example:

- `specs/examples/strategy_pairs_backtest_response.example.json`

Add optional top-level `selection_diagnostics`.

Source of truth:

- Use the same request-time selection state used to build the backtest inputs.
- Do not recompute diagnostics independently from the returned series after the
  fact.

Acceptance criteria:

- existing clients that read `selected_variant`, `points`, `markers`, and
  `rationale_codes` continue to validate;
- a drift case can show `selected_variant` as the presented/stored champion
  while `selection_diagnostics.best_variant` shows the neutral evaluated best.

### Live-z response

Future contract:

- `specs/contracts/strategy_pairs_live_z_response.schema.json`

Future example:

- `specs/examples/strategy_pairs_live_z_response.example.json`

Add optional top-level `selection_diagnostics`.

Source of truth:

- Use the same request-time selection state used to build the live-z response.
- Do not infer from current z-series markers alone.

Acceptance criteria:

- existing clients that read the live z-series continue to validate;
- diagnostics can distinguish projected champion display from evaluated-best
  state during Slice C observation.

### Paper-trades response

Future contract:

- `specs/contracts/strategy_pairs_paper_trades_response.schema.json`

Future example:

- `specs/examples/strategy_pairs_paper_trades_response.example.json`

Add optional `rows[].selection_diagnostics`.

Source of truth:

- Persist a diagnostic snapshot when paper-trade rows are generated.
- For rows written before diagnostics exist, either omit the object for legacy
  compatibility or emit `status: "UNAVAILABLE"` with
  `unavailable_reason: "HISTORICAL_ROW_WITHOUT_DIAGNOSTICS"`.
- Do not decorate old rows by reading the current selected champion at response
  time; that would mix current state into historical trades.

Acceptance criteria:

- existing clients that read paper-trade rows continue to validate;
- row diagnostics are stable over time and audit the selection state that
  existed when the paper-trade row was derived.

### Opportunity-history response

Future contract:

- `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`

Future example:

- `specs/examples/strategy_pairs_opportunity_history_response.example.json`

Add optional `rows[].selection_diagnostics`.

Source of truth:

- Persist a diagnostic snapshot with each opportunity-history row at
  `evaluated_at`.
- For rows written before diagnostics exist, either omit the object for legacy
  compatibility or emit `status: "UNAVAILABLE"` with
  `unavailable_reason: "HISTORICAL_ROW_WITHOUT_DIAGNOSTICS"`.
- Do not make `actionable: true` imply diagnostic trust. Actionability and
  selection-integrity diagnostics remain separate.

Acceptance criteria:

- existing opportunity-history downloads continue to validate;
- operators can filter rows where evaluated best differs from stored champion
  without treating old rows as silently safe.

## 7. Contract and example requirements for implementation

The later implementation PR must update exactly these response contracts for
X3's first slice:

1. `specs/contracts/strategy_pairs_backtest_response.schema.json`
2. `specs/contracts/strategy_pairs_live_z_response.schema.json`
3. `specs/contracts/strategy_pairs_paper_trades_response.schema.json`
4. `specs/contracts/strategy_pairs_opportunity_history_response.schema.json`

It must update exactly these matching examples:

1. `specs/examples/strategy_pairs_backtest_response.example.json`
2. `specs/examples/strategy_pairs_live_z_response.example.json`
3. `specs/examples/strategy_pairs_paper_trades_response.example.json`
4. `specs/examples/strategy_pairs_opportunity_history_response.example.json`

Schema requirements:

- Add `selection_diagnostics` to `properties`, not `required`.
- Use `additionalProperties: false` for the diagnostic object.
- Where the parent schema already uses `additionalProperties: false`, explicitly
  declare the new property there.
- Keep diagnostic enum values bounded.
- Keep nullable fields nullable where diagnostics can be unavailable for
  historical rows.

Example requirements:

- Each target example should include `selection_diagnostics` so the additive
  field is documented.
- Persisted-history surfaces should have test coverage for a legacy row with no
  diagnostics or explicit unavailable diagnostics, even if the public example
  shows the available path.

Validation requirements:

```bash
python3 - <<'PY'
import json
from jsonschema import Draft202012Validator

pairs = [
    (
        "specs/contracts/strategy_pairs_backtest_response.schema.json",
        "specs/examples/strategy_pairs_backtest_response.example.json",
    ),
    (
        "specs/contracts/strategy_pairs_live_z_response.schema.json",
        "specs/examples/strategy_pairs_live_z_response.example.json",
    ),
    (
        "specs/contracts/strategy_pairs_paper_trades_response.schema.json",
        "specs/examples/strategy_pairs_paper_trades_response.example.json",
    ),
    (
        "specs/contracts/strategy_pairs_opportunity_history_response.schema.json",
        "specs/examples/strategy_pairs_opportunity_history_response.example.json",
    ),
]

for schema_path, example_path in pairs:
    with open(schema_path) as fh:
        schema = json.load(fh)
    with open(example_path) as fh:
        example = json.load(fh)
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert not errors, (schema_path, example_path, errors)
    print(f"OK {schema_path} validates {example_path}")
PY
```

Also run JSON syntax validation for touched schema/example files, matching the
bootstrap playbook's contract check.

## 8. Testing requirements for implementation

Minimum implementation coverage:

1. Serialization test proving each new diagnostic object is optional and the
   old payload shape remains valid.
2. Schema/example validation for all four target response contracts.
3. Backtest/live-z regression test where `selected_variant_role` is
   `EVALUATED_BEST`.
4. Backtest/live-z regression test where drift exists and
   `selected_variant_role` is `STORED_CHAMPION_PROJECTION`.
5. Postgres-backed integration test for opportunity-history diagnostics using
   the existing `strategy-service` repository integration harness.
6. Postgres-backed integration test for paper-trade diagnostics, including a
   historical/unavailable row path.
7. Replay or fixture-based test, if Slice C fixture candles are available,
   proving repeated evaluation yields stable best variant, stored champion
   relation, transition decision, and diagnostics.

If deterministic Slice C fixture candles are not available, the implementation
PR must state that gap and keep the Postgres-backed tests as the minimum
acceptance bar for persisted surfaces.

## 9. Observability requirements

No metric or alert changes are required for this proposal.

**PROPOSAL for later implementation:** first rely on existing Slice C canary
metrics and audits:

- `pairs_cue_projection_total{outcome}`;
- `strategy_selection_transition_total{decision,timeframe}`;
- `strategy_selection_rows_updated_without_transition_total{timeframe}`;
- the `cue.selection_state` audit in
  `docs/27-champion-selection-independent-review-brief.md`.

If rollout visibility for the four reporting surfaces proves necessary, add a
bounded metric:

- `strategy_reporting_selection_diagnostics_total{surface,status}`

Allowed `surface` labels should be bounded to:

- `backtest`
- `live_z`
- `paper_trades`
- `opportunity_history`

Allowed `status` labels should be bounded to:

- `AVAILABLE`
- `UNAVAILABLE`
- `INCONSISTENT`

Do not use `pair_id` as a metric label. Pair-level detail belongs in structured
logs and response payloads.

Structured logs for future implementation should include:

- `request_id` when available;
- `surface`;
- `pair_id`;
- `timeframe`;
- `selected_variant_role`;
- `diagnostics_status`;
- `validation_state`;
- `transition_decision`;
- `drift_active`.

Alerts should continue to follow `docs/playbooks/observability-slo-runbook.md`.
X3 diagnostics must not create a new route to enable live `ENTRY` or `EXIT`.

## 10. Risk and failure modes

1. **Breaking contract compatibility.** Making diagnostics required or changing
   `selected_variant` meaning would break consumers. Mitigation: optional
   diagnostics only; no semantic redefinition.
2. **Historical state contamination.** Recomputing diagnostics for persisted
   paper/opportunity rows at read time would make old rows look more certain
   than they are. Mitigation: persist snapshots for new rows; mark old rows
   unavailable.
3. **Operator overtrust.** A visible diagnostic object can look like a trading
   approval. Mitigation: diagnostics are reporting-only; risk/execution gates
   stay fail-closed.
4. **Slice C not yet proven.** X3 depends on neutral-selection behavior and
   observation data. Mitigation: implementation waits until operator-captured
   Slice C evidence exists.
5. **Metric cardinality.** Reporting metrics could explode if pair labels are
   added. Mitigation: bounded `surface,status` labels only.

## 11. Versioning and changelog

This proposal is docs-only. It does not change behavior, schemas, examples,
metrics, alerts, or public contracts. No version bump is required and
`CHANGELOG.md` should not change for this proposal alone.

Future implementation:

- optional diagnostics in the four target contracts are MINOR-class additive
  changes;
- any new metrics are also MINOR-class contract additions because metrics are
  contracts under `docs/03-contracts-and-compatibility.md`;
- `CHANGELOG.md` must document the implementation when schemas, examples,
  runtime behavior, or metrics change;
- changing `selected_variant` meaning, removing it, or making replacements
  required is breaking and requires MAJOR handling.

## 12. Acceptance criteria for implementation PR

The later X3 implementation PR is ready for local review only when:

1. Slice C has landed and the operator has captured the observation evidence
   required by `docs/playbooks/observability-slo-runbook.md`.
2. All four target contracts and examples are updated.
3. Legacy `selected_variant` compatibility is preserved.
4. Diagnostics are optional/additive only.
5. Draft 2020-12 schema validation passes for each changed contract/example
   pair.
6. JSON syntax validation passes for touched contract/example files.
7. Persisted paper/opportunity rows do not infer diagnostics from current
   selected state at read time.
8. Integration/replay tests cover available and unavailable diagnostics.
9. The implementation PR documents any operator-only host verification that
   remains.

## 13. Recommendation

Approve X3 as a contract-additive reporting alignment slice after Slice C
observation. Use `selection_diagnostics` as the common optional object across
the four reporting surfaces, preserve legacy `selected_variant`, and require
schema/example validation plus persisted-history integration coverage before
implementation is considered done.
