# AUTO-2C v2 Offline Governor Runbook

## Purpose and authority

This runbook operates the separate AUTO-2C v2 offline governor:

```text
tools/scripts/autopilot_dynamic_allowlist_v2.py
```

Its output is advisory and non-actuating. The governor cannot alter paper
configuration, grant paper eligibility, start a paper trial, route an order,
approve itself, deploy, or confer live authority. A later AUTO-2D controller
must independently re-read the source files and recompute the complete
decision before it may consume a policy-eligible output. AUTO-2D is not
implemented or authorized by this runbook.

Default invocation is disabled and performs no file input/output:

```bash
python3 tools/scripts/autopilot_dynamic_allowlist_v2.py
```

Expected bounded result:

```json
{"artifact_created":false,"mode":"auto2c_v2_governor","status":"DISABLED"}
```

## Required authorization and evidence

Do not run `--enabled` without a separate Operator authorization naming:

- the exact repository Git SHA;
- two distinct, complete, comparable schema-v2 B2-c snapshots;
- each snapshot's absolute path, raw-byte SHA-256, and producer Git SHA;
- the paper-run config's absolute path, raw-byte SHA-256, and producer Git SHA;
- an exact v2 governor-config absolute path and raw-byte SHA-256;
- an explicit RFC 3339 evaluation time at whole-second precision;
- `prior_active_set_source=STATIC_PAPER_ALLOWLIST`;
- one new Operator evidence root and one absent decision subdirectory; and
- the permitted transcript and output files.

Genuine E3 additionally requires Operator-supplied, read-only, exact-hash
copies of two real comparable v2 snapshots. Synthetic fixtures, a schema-v1
predecessor, or a single v2 window must never be called E3.

The first-transition route reconstructs the prior active set only from the
paper config's exact direction-level `pair_variant_direction` static
allowlist. The future
`PREVIOUS_ACCEPTED_V2_PAPER_UNIVERSE` route is not implemented and fails
closed.

## Fail-closed preflight

Before creating an evidence root, verify and record:

1. repository branch and exact Git SHA;
2. complete tracked and untracked worktree state;
3. all four inputs are absolute, normalized, regular, non-symlink files;
4. every supplied SHA-256 is the hash of the exact raw bytes;
5. every producer Git SHA is a 40-character lowercase hexadecimal Operator
   attestation;
6. the snapshots are distinct schema-v2 files with identical selector config,
   complete selector evidence, available selector churn, ordered cutoffs, and
   at least 86,400 seconds of cutoff separation;
7. current snapshot age at `EVALUATED_AT` is no more than 1,800 seconds;
8. the paper config uses a non-empty direction-level static allowlist;
9. the governor config exactly equals the ratified policy envelope; and
10. the decision subdirectory and both fixed output paths are absent.

The CLI repeats the file, hash, structure, consistency, direction, provenance,
time, and collision checks. It rejects duplicate JSON keys and non-finite
numbers. `NONE` and null remain distinct selector evidence but are
non-actionable; any unknown selector direction or any realized-paper
`NONE`/null/unknown direction rejects the input before output.

## Exact policy configuration

The bound governor-config JSON must contain exactly:

```json
{
  "policy": {
    "candidate_overflow_behavior": "DETERMINISTIC_TRUNCATE_AND_RECORD",
    "churn_denominator": "MAX_POLICY_CAPACITY_PRIOR_ACTIVE_COUNT",
    "churn_floor_capacity": 4,
    "churn_measure": "PRIOR_SELECTED_SYMMETRIC_DIFFERENCE",
    "concentration_overflow_behavior": "SKIP_AND_CONTINUE",
    "controller_hard_runtime_seconds": 90000,
    "cooldown_seconds": 300,
    "decision_validity_seconds": 108000,
    "entry_window_seconds": 86400,
    "exit_only_grace_seconds": 3600,
    "exploration_lane_ranking": "MIN_TRADE_NOW_RATIO_DESC_MIN_TRADE_NOW_COUNT_DESC_MIN_SELECTOR_EDGE_DESC_EXACT_KEY_ASC",
    "fallback_behavior": "NO_FALLBACK",
    "hold_window_bars": 5,
    "max_additions": 2,
    "max_automatic_start_decision_age_seconds": 300,
    "max_candidate_age_seconds": 120,
    "max_churn_ratio": 0.5,
    "max_current_source_age_seconds": 1800,
    "max_directions_per_pair_variant": 2,
    "max_entries_per_full_instrument": 2,
    "max_entries_per_pair_id": 2,
    "max_new_additions_per_full_instrument": 1,
    "max_open_paper_positions_per_full_instrument": 1,
    "max_open_paper_positions_per_pair_id": 1,
    "max_open_positions_per_exact_key": 1,
    "max_open_selector_exploration_positions": 1,
    "max_removals": 2,
    "max_selected_entries": 4,
    "max_selector_exploration_entries": 2,
    "max_simultaneously_open_paper_positions": 2,
    "min_selector_exploration_entries_when_qualified_and_transition_safe": 1,
    "min_selector_rows_each_snapshot": 12,
    "min_source_cutoff_separation_seconds": 86400,
    "min_trade_now_count_each_snapshot": 3,
    "min_trade_now_ratio_each_snapshot": 0.01,
    "realized_lane_ranking": "MIN_TOTAL_B2C_SCORE_DESC_MIN_CLOSED_COUNT_DESC_MIN_TRADE_NOW_RATIO_DESC_EXACT_KEY_ASC",
    "require_positive_finite_selector_mean_net_edge": true,
    "required_comparable_v2_snapshots": 2,
    "selection_allocation": "RESERVE_BEST_EXPLORATION_ADDITION_FILL_REALIZED_ALLOW_SECOND_ADDITION"
  },
  "policy_version": "auto2c-v2-paper-automatic-acceptance-1"
}
```

Create this file only through a separately authorized Operator procedure. Do
not hand-edit any evidence or reuse a config with a different raw hash.

## One-shot invocation

The Operator wrapper may create one timestamped evidence root and persist one
transcript when explicitly authorized. The governor itself creates only the
previously absent decision subdirectory and these fixed files:

```text
autopilot_dynamic_allowlist_decision_v2.json
autopilot_dynamic_allowlist_decision_v2.md
```

Bind the approved values, then invoke exactly once:

```bash
python3 tools/scripts/autopilot_dynamic_allowlist_v2.py \
  --enabled \
  --current-snapshot-json "$CURRENT_SNAPSHOT_PATH" \
  --current-snapshot-sha256 "$CURRENT_SNAPSHOT_SHA256" \
  --current-snapshot-producer-git-sha "$CURRENT_SNAPSHOT_PRODUCER_GIT_SHA" \
  --previous-snapshot-json "$PREVIOUS_SNAPSHOT_PATH" \
  --previous-snapshot-sha256 "$PREVIOUS_SNAPSHOT_SHA256" \
  --previous-snapshot-producer-git-sha "$PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA" \
  --paper-run-config-json "$PAPER_RUN_CONFIG_PATH" \
  --paper-run-config-sha256 "$PAPER_RUN_CONFIG_SHA256" \
  --paper-run-config-producer-git-sha "$PAPER_RUN_CONFIG_PRODUCER_GIT_SHA" \
  --governor-config-json "$GOVERNOR_CONFIG_PATH" \
  --governor-config-sha256 "$GOVERNOR_CONFIG_SHA256" \
  --evaluated-at "$EVALUATED_AT" \
  --prior-active-set-source STATIC_PAPER_ALLOWLIST \
  --output-json "$DECISION_ROOT/autopilot_dynamic_allowlist_decision_v2.json" \
  --output-markdown "$DECISION_ROOT/autopilot_dynamic_allowlist_decision_v2.md"
```

Do not retry automatically. Do not repair, clean up, overwrite, or reuse a
partial decision root.

## Result handling

`INPUT_REJECTED` means no valid decision exists. If the decision root is
absent, retain the transcript. If a partial root exists, retain it unchanged
for diagnosis and use a newly authorized root for any later attempt.

`GOVERNOR_BLOCKED` is a valid, schema-version-2, non-actuating policy result.
Its proposed/selected/addition/removal/retained and outcome sets are empty.
There is no fallback. A blocked result is never eligible for AUTO-2D.

`POLICY_ELIGIBLE_FOR_AUTO2D_VERIFICATION` means only that the offline governor
found a deterministic result inside the ratified envelope. It grants no
eligibility or start authority. The output expires after 108,000 seconds, and
a future AUTO-2D start must also satisfy the stricter 300-second decision-age
gate.

Candidate overflow alone never blocks. Candidates are ranked by the contracted
realized and exploration lanes, concentration failures are skipped with a
recorded reason, and otherwise qualifying excess candidates are truncated and
recorded. Realized-paper and selector-view evidence remain separate
set-membership streams and are never numerically merged.

## Post-run validation

Before accepting the result as evidence:

1. validate the JSON against
   `specs/contracts/autopilot_dynamic_allowlist_decision_v2.schema.json` with
   RFC 3339 format checking;
2. recompute the policy-envelope hash from canonical
   `policy_version + policy`;
3. recompute the prior-active-set hash from sorted exact keys;
4. recompute `decision_id` from the four raw input hashes, policy hash,
   prior-set hash, and canonical `evaluated_at`;
5. verify every candidate metric, lane rank, exact-key tie-break,
   selection/skip/truncation step, concentration, transition, churn, freshness,
   cutoff, validity, and direction count;
6. require all authority-boundary fields false;
7. hash the JSON, Markdown, and transcript;
8. re-hash every input and verify bytes and file metadata remain unchanged;
9. retain the repository SHA, exact command, stdout/stderr, exit status, input
   manifest, output hashes, and validation report append-only; and
10. stop for Codex validation and a later independent AUTO-2D gate.

## Strictly read-only reconstruction

Given existing exact output hashes, `--verify-only` re-reads the bound inputs,
reconstructs both outputs byte-for-byte, and creates or modifies nothing:

```bash
python3 tools/scripts/autopilot_dynamic_allowlist_v2.py \
  --verify-only \
  --current-snapshot-json "$CURRENT_SNAPSHOT_PATH" \
  --current-snapshot-sha256 "$CURRENT_SNAPSHOT_SHA256" \
  --current-snapshot-producer-git-sha "$CURRENT_SNAPSHOT_PRODUCER_GIT_SHA" \
  --previous-snapshot-json "$PREVIOUS_SNAPSHOT_PATH" \
  --previous-snapshot-sha256 "$PREVIOUS_SNAPSHOT_SHA256" \
  --previous-snapshot-producer-git-sha "$PREVIOUS_SNAPSHOT_PRODUCER_GIT_SHA" \
  --paper-run-config-json "$PAPER_RUN_CONFIG_PATH" \
  --paper-run-config-sha256 "$PAPER_RUN_CONFIG_SHA256" \
  --paper-run-config-producer-git-sha "$PAPER_RUN_CONFIG_PRODUCER_GIT_SHA" \
  --governor-config-json "$GOVERNOR_CONFIG_PATH" \
  --governor-config-sha256 "$GOVERNOR_CONFIG_SHA256" \
  --evaluated-at "$EVALUATED_AT" \
  --prior-active-set-source STATIC_PAPER_ALLOWLIST \
  --output-json "$DECISION_ROOT/autopilot_dynamic_allowlist_decision_v2.json" \
  --output-markdown "$DECISION_ROOT/autopilot_dynamic_allowlist_decision_v2.md" \
  --expected-output-json-sha256 "$OUTPUT_JSON_SHA256" \
  --expected-output-markdown-sha256 "$OUTPUT_MARKDOWN_SHA256"
```

This is a same-implementation operational reconstruction. It does not replace
the independently implemented AUTO-2D verifier.

## Concurrency, repeat invocation, rollback, and retention

- Only one exclusive decision root may win. Any collision refuses.
- Repeating the same inputs requires a distinct, explicitly authorized absent
  decision root; deterministic outputs should be byte-identical.
- A partial root is diagnostic residue, not a valid result. Preserve it.
- There is no eligibility rollback because this governor cannot actuate. If a
  later consumer rejects or expires a decision, the safe state is no new paper
  trial and no fallback.
- Retain the complete Operator evidence root append-only according to
  `.agentic/policies/evidence.md`.
- Any second comparable v2 evidence window, E3 run, AUTO-2D implementation,
  paper configuration, or paper-trial start requires a separate explicit
  Operator authorization.
