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

## Evidence Checklist

Keep these files together for review:

- `$SHADOW_ROOT/git_status.txt`
- `$SHADOW_ROOT/git_head.txt`
- `$SHADOW_ROOT/python_version.txt`
- `$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.json`
- `$SHADOW_ROOT/autopilot_shadow_allowlist_snapshot.md`
- source paper evidence used for the snapshot

Do not merge host evidence into the repository.

## Failure Handling

1. If the tool reports no closed paper events, stop and capture paper evidence
   first.
2. If all candidates reject for insufficient sample, keep AUTO-2B as evidence
   and do not loosen thresholds inside the same run.
3. If tail-loss quarantine removes a leg, treat it as a selector diagnostic,
   not as permission to manually edit runtime allowlists.
4. If the snapshot suggests a dynamic allowlist, wait for AUTO-2C governor
   implementation before allowing dynamic output to drive paper entries.
