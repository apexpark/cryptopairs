# AUTO-2B Shadow Dynamic Allowlist Runbook

## Purpose

Build an AUTO-2B shadow dynamic allowlist snapshot from closed `1m` paper
evidence. The snapshot records what a dynamic selector would choose, reject, or
quarantine. It does not control paper entries or live entries.

## Safety Invariants

1. Do not feed this output into `AUTOPILOT_PAPER_ALLOWED_PAIR_VARIANTS`.
2. Do not start services, hosted loops, live `ENTRY` / `EXIT`, or exchange
   calls from this runbook.
3. Use a fixed `SOURCE_CUTOFF_AT` so selector scoring cannot look ahead.
4. Keep outputs under ignored `artifacts/autopilot_shadow_allowlist/`.
5. Treat the output as advisory evidence for AUTO-2C, not as an active
   allowlist.

## Build From AUTO-2A Paper Evidence

Run on Hetzner from `/opt/cryptopairs` after a paper run has completed.

```bash
cd /opt/cryptopairs

PAPER_RUN_ROOT="${PAPER_RUN_ROOT:-$(ls -1dt artifacts/autopilot_paper/runs/* | head -1)}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SHADOW_ROOT="artifacts/autopilot_shadow_allowlist/runs/$RUN_ID"
SOURCE_CUTOFF_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$SHADOW_ROOT"

git status --short --branch | tee "$SHADOW_ROOT/git_status.txt"
git rev-parse HEAD | tee "$SHADOW_ROOT/git_head.txt"
python3 --version | tee "$SHADOW_ROOT/python_version.txt"

python3 tools/scripts/autopilot_shadow_allowlist.py \
  --paper-dir "$PAPER_RUN_ROOT/records" \
  --run-config-json "$PAPER_RUN_ROOT/run_config.json" \
  --source-cutoff-at "$SOURCE_CUTOFF_AT" \
  --min-closed-positions 5 \
  --min-avg-net-bps 0 \
  --max-tail-loss-bps -60 \
  --max-avg-exit-lag-seconds 1800 \
  --max-selected 8 \
  --output-json "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json" \
  --output-markdown "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"

jq '.summary' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
jq '.static_allowlist_comparison' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
sed -n '1,180p' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"
```

The static comparison is direction-equivalent. Pair-level static allowlist
entries from the paper run config are expanded only across directions observed
in the shadow evidence for the same pair/variant.

## Build From Captured Strategy Paper Trades

Use this when a broader universe paper-trades capture exists.

```bash
PAPER_TRADES_JSON="artifacts/autopilot_observe/runs/<run-id>/paper_trades_1m.json"
SOURCE_CUTOFF_AT="2026-07-02T00:00:00Z"
SHADOW_ROOT="artifacts/autopilot_shadow_allowlist/runs/<run-id>"
mkdir -p "$SHADOW_ROOT"

python3 tools/scripts/autopilot_shadow_allowlist.py \
  --paper-trades-json "$PAPER_TRADES_JSON" \
  --source-cutoff-at "$SOURCE_CUTOFF_AT" \
  --min-closed-positions 10 \
  --min-avg-net-bps 0 \
  --max-tail-loss-bps -60 \
  --max-avg-exit-lag-seconds 1800 \
  --max-selected 8 \
  --output-json "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json" \
  --output-markdown "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"
```

## Build From B2-b Selector-View Evidence (B2-c)

This procedure consumes a **completed** B2-b selector-view capture. It does not
start, stop, or signal a capture. B2-d capture remains an Operator-only step
with its own authorization and evidence window.

Set all three roots/cutoffs explicitly so the snapshot cannot silently select
the wrong run. `SOURCE_CUTOFF_AT` is the reviewed end of the evidence window,
not the current wall clock. `PREVIOUS_SNAPSHOT` is optional; set it only when
the prior snapshot used the same realized-selector thresholds.

```bash
cd /opt/cryptopairs

: "${PAPER_RUN_ROOT:?set PAPER_RUN_ROOT to the completed paper run root}"
: "${SELECTOR_VIEW_ROOT:?set SELECTOR_VIEW_ROOT to the completed B2-b capture root}"
: "${SOURCE_CUTOFF_AT:?set SOURCE_CUTOFF_AT to the reviewed RFC 3339 window end}"
[[ -d "$PAPER_RUN_ROOT/records" ]] || {
  echo "paper records directory not found: $PAPER_RUN_ROOT/records" >&2
  exit 1
}
[[ -d "$SELECTOR_VIEW_ROOT/records" ]] || {
  echo "selector-view records directory not found: $SELECTOR_VIEW_ROOT/records" >&2
  exit 1
}

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SHADOW_ROOT="artifacts/autopilot_shadow_allowlist/runs/$RUN_ID"
mkdir -p "$SHADOW_ROOT"

selector_view_args=()
while IFS= read -r -d '' selector_path; do
  selector_view_args+=(--selector-view-jsonl "$selector_path")
done < <(
  find "$SELECTOR_VIEW_ROOT/records" -type f \
    -name 'autopilot_observe_*.jsonl' -print0
)
if (( ${#selector_view_args[@]} == 0 )); then
  echo "no selector-view JSONL files found under $SELECTOR_VIEW_ROOT/records" >&2
  exit 1
fi

previous_snapshot_args=()
if [[ -n "${PREVIOUS_SNAPSHOT:-}" ]]; then
  [[ -f "$PREVIOUS_SNAPSHOT" ]] || {
    echo "previous snapshot not found: $PREVIOUS_SNAPSHOT" >&2
    exit 1
  }
  previous_snapshot_args+=(--previous-snapshot-json "$PREVIOUS_SNAPSHOT")
fi

git status --short --branch | tee "$SHADOW_ROOT/git_status.txt"
git rev-parse HEAD | tee "$SHADOW_ROOT/git_head.txt"
python3 --version | tee "$SHADOW_ROOT/python_version.txt"

python3 tools/scripts/autopilot_shadow_allowlist.py \
  --paper-dir "$PAPER_RUN_ROOT/records" \
  --run-config-json "$PAPER_RUN_ROOT/run_config.json" \
  "${selector_view_args[@]}" \
  --source-cutoff-at "$SOURCE_CUTOFF_AT" \
  --min-closed-positions 5 \
  --min-avg-net-bps 0 \
  --max-tail-loss-bps -60 \
  --max-avg-exit-lag-seconds 1800 \
  --max-selected 8 \
  "${previous_snapshot_args[@]}" \
  --output-json "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json" \
  --output-markdown "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"

jq '.selector_view' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
jq '.universe' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
jq '.churn' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
sed -n '1,260p' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"
```

The tool re-checks every B2-b tick manifest before aggregation. A manifest must
be followed by exactly its declared number of rows with matching per-bucket
counts and tick identity; a truncated, duplicated, interrupted, or malformed
tick aborts the whole snapshot before output is written. An all-empty tick is
valid because its zero-row manifest proves the observation occurred.

Interpretation is deliberately narrow:

- `selector_view_prominent` means observed in `TRADE_NOW` at least once during
  the window; every other observed candidate is `selector_view_marginal`.
- `rows_observed` and `time_in_tradable_now_ratio` describe selector
  membership, not fills or outcomes. `stated_net_edge_bps_summary` restates the
  selector's own view and is not realized PnL.
- `bucket_universe_counts` counts distinct pair/variant/direction keys observed
  in each bucket. A key may count in more than one bucket when it moves during
  the window.
- `direction: "NONE"` is the strategy service's explicit non-actionable
  direction sentinel. It remains distinct from a missing/null direction, does
  not match `LONG_SPREAD` or `SHORT_SPREAD` paper evidence or
  direction-specific static entries, and does not itself grant eligibility.
  It is accepted only as a selector-view direction; the realized paper-event
  direction set remains `LONG_SPREAD` / `SHORT_SPREAD`. Any other unknown
  selector direction string still fails closed.
- `selector_view_only` is the advisory discovery list: prominent in the
  selector view and absent from the static paper allowlist. It is not
  permission to alter eligibility.
- `churn.selector_view` compares prominent selector-view sets only;
  top-level realized-paper churn is calculated independently.

## Evidence Checklist

Keep these files together for review:

- `$SHADOW_ROOT/git_status.txt`
- `$SHADOW_ROOT/git_head.txt`
- `$SHADOW_ROOT/python_version.txt`
- `$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json`
- `$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md`
- source paper evidence used for the snapshot
- source B2-b selector-view JSONL used for a v2 snapshot

Do not merge host evidence into the repository.

## Measure Churn And Stability Across Snapshots

Churn and selector stability (AUTO-2 §3 exit criteria for AUTO-2B) are
cross-snapshot quantities: they require at least two snapshots over the same
selector config. After the first snapshot exists, build later snapshots with
`--previous-snapshot-json` pointing at the most recent prior snapshot:

```bash
cd /opt/cryptopairs

PREVIOUS_SNAPSHOT="$(ls -1dt artifacts/autopilot_shadow_allowlist/runs/*/autopilot_shadow_allowlist_snapshot.json | head -1)"
PAPER_RUN_ROOT="${PAPER_RUN_ROOT:-$(ls -1dt artifacts/autopilot_paper/runs/* | head -1)}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SHADOW_ROOT="artifacts/autopilot_shadow_allowlist/runs/$RUN_ID"
SOURCE_CUTOFF_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$SHADOW_ROOT"

python3 tools/scripts/autopilot_shadow_allowlist.py \
  --paper-dir "$PAPER_RUN_ROOT/records" \
  --run-config-json "$PAPER_RUN_ROOT/run_config.json" \
  --source-cutoff-at "$SOURCE_CUTOFF_AT" \
  --previous-snapshot-json "$PREVIOUS_SNAPSHOT" \
  --output-json "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json" \
  --output-markdown "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md"

jq '.churn' "$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json"
```

Interpretation: `stability_ratio` is retained-selected divided by the
previous selected count; `churn_count` is additions plus removals. Keep the
selector config identical between compared snapshots — comparing snapshots
built with different thresholds measures config change, not selector churn.

## Failure Handling

1. If the tool reports no closed paper events and no selector-view input was
   supplied, stop and capture paper evidence first. A selector-only v2 snapshot
   is valid but its realized-paper sections and paper-evidenced subset are
   empty; do not describe it as outcome evidence.
2. If selector-view ingestion reports a missing manifest, truncated tick,
   count mismatch, duplicate tick/candidate, invalid identity/value, or an
   outcome/PnL/fill field, stop. Do not hand-edit the capture or keep a partial
   snapshot; fix or recapture under a separately authorized B2-d window.
3. The tool is deliberately crash-hard on malformed evidence: one bad row
   that passes the skip filters aborts the whole snapshot rather than
   emitting partial output. Treat a traceback as a data-quality signal;
   capture it in the evidence bundle and do not hand-edit evidence files.
4. If all candidates reject for insufficient sample, keep AUTO-2B as evidence
   and do not loosen thresholds inside the same run.
5. If tail-loss quarantine removes a leg, treat it as a selector diagnostic,
   not as permission to manually edit runtime allowlists.
6. If the snapshot suggests a dynamic allowlist, wait for AUTO-2C governor
   implementation before allowing dynamic output to drive paper entries.
