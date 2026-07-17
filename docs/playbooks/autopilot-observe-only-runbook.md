# 1m Autopilot Observe-Only Runbook

## Purpose

Run the AUTO-1 observe-only sidecar on Hetzner, capture evidence for 24-72
hours, and build an offline AUTO-1C attribution report.

This runbook is observe-only. It must not create execution order intents,
dispatch orders, restart services, or change runtime trading mode.

## Safety Invariants

1. Keep the observer disabled unless the command explicitly sets
   `AUTOPILOT_OBSERVE_ENABLED=true`.
2. Use only `AUTOPILOT_OBSERVE_TIMEFRAMES=1m` or omit the timeframe variable.
3. Provide an explicit `pair_id:selected_variant` allowlist.
4. Keep `EXECUTION_DISPATCH_MODE` unchanged. The observer reads dispatch mode
   and blocks candidates when execution-service reports `FAIL_CLOSED`.
5. Keep the evidence directory under `artifacts/autopilot_observe/`.
6. Treat report paper-trade outcomes as simulated attribution, not live PnL.

## Host Preflight

Run on Hetzner from `/opt/cryptopairs`.

```bash
cd /opt/cryptopairs

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="artifacts/autopilot_observe/runs/$RUN_ID"
mkdir -p "$RUN_ROOT"

git status --short --branch | tee "$RUN_ROOT/git_status.txt"
git rev-parse HEAD | tee "$RUN_ROOT/git_head.txt"
python3 --version | tee "$RUN_ROOT/python_version.txt"

curl -fsS http://127.0.0.1:8080/health | tee "$RUN_ROOT/data_health.json"
curl -fsS http://127.0.0.1:8083/health | tee "$RUN_ROOT/strategy_health.json"
curl -fsS http://127.0.0.1:8082/v1/execution/dispatch-mode | tee "$RUN_ROOT/dispatch_mode.json"
curl -fsS http://127.0.0.1:8082/v1/execution/kill-switch | tee "$RUN_ROOT/kill_switch.json"

AUTOPILOT_OBSERVE_ENABLED=false \
python3 tools/scripts/autopilot_observe.py --once | tee "$RUN_ROOT/disabled_probe.json"
```

Expected disabled probe:

```json
{
  "enabled": false,
  "recommended_action": "SET_AUTOPILOT_OBSERVE_ENABLED_TRUE_TO_RUN"
}
```

## Configure Allowlist And Quality Window

Replace the pair/variant and quality numbers with the operator-approved trial
set. Keep the allowlist small for the first 24-hour capture.

```bash
cat > "$RUN_ROOT/quality_windows.json" <<'JSON'
[
  {
    "pair_id": "PF_DOGEUSD__PF_PEPEUSD",
    "timeframe": "1m",
    "selected_variant": "ROBUST_Z",
    "rows": 64,
    "profitable_rate": 0.73,
    "avg_net_bps": 7.4
  }
]
JSON

ALLOWLIST="PF_DOGEUSD__PF_PEPEUSD:ROBUST_Z"
```

## One-Shot Trial Tick

Run one enabled tick before starting a long capture.

```bash
AUTOPILOT_OBSERVE_ENABLED=true \
AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON="$RUN_ROOT/quality_windows.json" \
AUTOPILOT_OBSERVE_OUTPUT_DIR="$RUN_ROOT/records" \
AUTOPILOT_OBSERVE_INTERVAL_SECONDS=60 \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=20 \
AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS=0 \
python3 tools/scripts/autopilot_observe.py --once | tee "$RUN_ROOT/one_shot_stdout.json"
```

Review the stdout and generated JSONL before starting the loop:

```bash
find "$RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print
tail -n 20 "$RUN_ROOT"/records/*/autopilot_observe_*.jsonl
```

## 24-72 Hour Capture Loop

Start the observer as a background process. The observer appends JSONL records
under `$RUN_ROOT/records`.

```bash
nohup env \
  AUTOPILOT_OBSERVE_ENABLED=true \
  AUTOPILOT_OBSERVE_ALLOWED_PAIR_VARIANTS="$ALLOWLIST" \
  AUTOPILOT_OBSERVE_QUALITY_WINDOWS_JSON="$RUN_ROOT/quality_windows.json" \
  AUTOPILOT_OBSERVE_OUTPUT_DIR="$RUN_ROOT/records" \
  AUTOPILOT_OBSERVE_LOOP=true \
  AUTOPILOT_OBSERVE_INTERVAL_SECONDS=60 \
  AUTOPILOT_OBSERVE_MIN_READY_WINDOW_ROWS=20 \
  AUTOPILOT_OBSERVE_MIN_READY_WINDOW_AVG_NET_BPS=0 \
  python3 tools/scripts/autopilot_observe.py \
  > "$RUN_ROOT/autopilot_observe.log" 2>&1 &
echo "$!" | tee "$RUN_ROOT/autopilot_observe.pid"
```

Monitor without changing runtime state:

```bash
cat "$RUN_ROOT/autopilot_observe.pid"
tail -n 100 "$RUN_ROOT/autopilot_observe.log"
find "$RUN_ROOT/records" -type f -name 'autopilot_observe_*.jsonl' -print -exec wc -l {} \;
tail -n 5 "$RUN_ROOT"/records/*/autopilot_observe_*.jsonl
```

Stop after the chosen observation window:

```bash
kill "$(cat "$RUN_ROOT/autopilot_observe.pid")"
sleep 2
tail -n 100 "$RUN_ROOT/autopilot_observe.log"
```

This loop stops on SIGTERM's default disposition — it is not signal-handled, so
a stop can land mid-append and truncate the final record. Stop it between ticks
where you can, and treat a truncated last line as expected rather than as data
loss. (The graceful stop described under "Stop the selector-view run" belongs to
the selector-view loop only; extending it to this loop is a tracked follow-up.)

## Selector-View Capture (AUTO-2B.2, wide universe)

Selector-view capture records the cue endpoint's full view across all three
buckets (`tradable_now`, `watchlist`, `excluded`) as observation-only rows —
never entry candidates, never outcomes. It is disabled by default; the
narrow paper-feeding capture is unaffected. Run it as a **separate, bounded,
operator-started run root**.

### Step 1 — Estimate disk before starting (required)

Selector-view volume ≈ (candidates across all buckets) × (ticks over the
window). Read the current universe size, then project. This is read-only:

```bash
cd /opt/cryptopairs
curl -fsS "http://127.0.0.1:8083/v1/strategy/pairs/trade-now?timeframe=1m" \
  | jq '{tradable_now: (.tradable_now|length), watchlist: (.watchlist|length), excluded: (.excluded|length), total: ((.tradable_now|length)+(.watchlist|length)+(.excluded|length))}'
```

Projection at 300s cadence (12 ticks/hour): `rows_per_window = total × 12 ×
hours`. A fully-populated selector-view row serializes to roughly 1.4–1.7 KB
(use 1.8 KB per row for a safety-margin estimate). Confirm free
space with `df -h /opt/cryptopairs` before starting; do not start if the
projected artifact would exceed available headroom — re-scope the cadence or
window with the Operator instead.

### Step 2 — Bounded selector-view run

```bash
cd /opt/cryptopairs

SV_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SV_ROOT="artifacts/autopilot_observe_selector_view/runs/$SV_ID"
mkdir -p "$SV_ROOT/records"
git rev-parse HEAD | tee "$SV_ROOT/git_head.txt"

nohup env \
  AUTOPILOT_OBSERVE_ENABLED=true \
  AUTOPILOT_OBSERVE_OUTPUT_DIR="$SV_ROOT/records" \
  AUTOPILOT_OBSERVE_LOOP=true \
  AUTOPILOT_OBSERVE_INTERVAL_SECONDS=300 \
  AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS=259200 \
  python3 tools/scripts/autopilot_observe.py --capture-selector-view \
  > "$SV_ROOT/autopilot_observe_selector_view.log" 2>&1 &
echo "$!" | tee "$SV_ROOT/autopilot_observe_selector_view.pid"
echo "SV_ROOT=$SV_ROOT"
```

Selector-view capture is switched on by the explicit `--capture-selector-view`
**flag**, not by the equivalent `AUTOPILOT_OBSERVE_CAPTURE_SELECTOR_VIEW`
environment variable, and this matters for stopping the run safely. Both this
run and the narrow paper-feeding run above execute the same
`python3 tools/scripts/autopilot_observe.py`; everything else about them comes
from the environment, which `ps` does not show. The flag is what puts a
distinguishing token in this process's own visible command line, so the stop
procedure below can tell the two runs apart. Start it any other way and that
procedure will — by design — refuse to confirm the PID.

The loop exits itself at `MAX_RUNTIME_SECONDS` — whatever value the command
above sets, here 259200s (72h). The tool enforces only that the bound is a
positive integer, not any particular ceiling: it will not clamp a larger value
for you, so the 72h window is this command's choice and re-scoping it is an
Operator decision. Each tick
logs a `selector_view_records` count so growth is visible. No allowlist and
no quality windows are needed — selector-view capture bypasses the
entry-candidate gates entirely and drives no eligibility or execution path.

`AUTOPILOT_OBSERVE_MAX_RUNTIME_SECONDS` is **mandatory and must be a positive
integer** for a selector-view loop: the tool refuses to start
(`SELECTOR_VIEW_LOOP_REQUIRES_MAX_RUNTIME`, exit 2) if it is missing, zero, or
negative, so an unbounded wide capture cannot be started by accident.

### Monitor

```bash
tail -n 20 "$SV_ROOT/autopilot_observe_selector_view.log"
find "$SV_ROOT/records" -name 'autopilot_observe_*.jsonl' -exec wc -l {} \;
du -sh "$SV_ROOT"
```

If a tick logs `"selector_view_tick_refused": "INCOMPLETE_UNIVERSE"`, the cue
endpoint returned a candidate that could not be faithfully transcribed. That
tick is recorded as a single `BLOCKED_MALFORMED_RESPONSE` record and emits **no**
selector rows — by design, so a partial universe never reaches B2-c. Repeated
refusals mean the source needs fixing; capture, do not ignore them:

```bash
grep -c 'INCOMPLETE_UNIVERSE' "$SV_ROOT/autopilot_observe_selector_view.log" || true
grep 'INCOMPLETE_UNIVERSE' "$SV_ROOT/autopilot_observe_selector_view.log" | tail -n 5
```

### Tick manifests: what "no rows" means

Every captured tick writes one manifest record
(`"capture_profile": "selector_view_tick"`, `"decision":
"SELECTOR_VIEW_TICK_CAPTURED"`) immediately before that tick's rows, stating
`recorded_rows` and the per-bucket counts that follow.

It is there because "no rows" is otherwise ambiguous. If the selector
legitimately returns an empty universe, the tick writes no candidate rows — and
without the manifest that is indistinguishable on disk from a tick that never
ran at all (host down, loop stopped, run never started). The manifest is the
positive marker: **manifest present = the tick was captured**, and a manifest
with `recorded_rows: 0` is a real observation that the selector saw nothing. No
manifest and no refusal record for a timestamp means that tick is missing, not
empty. A refused tick emits its `BLOCKED_*` record and **no** manifest, so
captured and refused never overlap.

Because the manifest is written first, it also makes truncation visible: if the
rows that follow are fewer than `recorded_rows`, the tail was cut (e.g. a
`kill -9` mid-append) rather than the universe being smaller.

The records are sharded one file per calendar day, so a multi-day run always
spans several files. `-h` suppresses the per-file name prefix, which is what
makes these a single total rather than a count per file:

```bash
# Ticks captured, and how many of them saw an empty universe:
grep -hc '"SELECTOR_VIEW_TICK_CAPTURED"' "$SV_ROOT"/records/*/autopilot_observe_*.jsonl \
  | paste -sd+ - | bc
grep -h '"SELECTOR_VIEW_TICK_CAPTURED"' "$SV_ROOT"/records/*/autopilot_observe_*.jsonl \
  | grep -c '"recorded_rows":0'
```

### Stop the selector-view run

The selector-view run has its **own** PID file
(`autopilot_observe_selector_view.pid`), separate from the narrow
paper-feeding run's `$RUN_ROOT/autopilot_observe.pid`. Stop only the
selector-view loop; do not touch the narrow run.

The loop normally exits on its own at `MAX_RUNTIME_SECONDS`. To stop it early,
or to confirm it has ended:

```bash
SV_PID="$(cat "$SV_ROOT/autopilot_observe_selector_view.pid")"

# Confirm the PID is a selector-view capture before signalling it.
# Prints the verdict either way; signals nothing itself.
python3 tools/scripts/autopilot_observe.py --verify-selector-view-pid "$SV_PID"
```

This check exists because matching on `autopilot_observe.py` alone would match
the **narrow paper-feeding run too**, and stop the wrong capture. It reads the
PID's exact argv from `/proc/<pid>/cmdline` and confirms the
`--capture-selector-view` flag.

Run it **on the capture host**, where the run actually is. It fails closed —
each verdict below exits 2 and means **do not signal**:

| Verdict | Meaning |
|---|---|
| `NO_SUCH_PROCESS` | Stale PID file; nothing is running under this PID. |
| `NOT_SELECTOR_VIEW_CAPTURE` | Some other process holds this PID — possibly the narrow run. |
| `IDENTITY_NOT_VERIFIABLE` | No `/proc` (e.g. run from a Mac). `ps` renders argv space-joined and unquoted, so an argument *value* could masquerade as the flag; the check will not guess. Re-run it on the host. |

If it does not exit 0, stop and escalate to the Operator; do not kill the PID.

**Read the exit code for exactly what it means.** Exit 0 establishes the
process's **kind** — this PID is *a* selector-view capture, so it is not the
narrow run and not some unrelated process. It does **not** establish the
process's **identity**: it cannot tell you this PID is *the* capture you started.
Two cases still pass:

- **Two captures running at once** — both match, and the check cannot say which
  is yours.
- **A stale PID file whose PID has been recycled by a different selector-view
  capture** — the check passes and you would stop the wrong one.

Identity comes from the PID file, not from this check — so keep the PID file
trustworthy. Two rules close the gap, and they are procedural, not automated:

1. **Run one selector-view capture at a time.** The two cases above only arise
   when a second capture exists. If you cannot account for every capture running
   on the host, do not signal — escalate to the Operator.
2. **Use the PID file from the run root you started** (`$SV_ROOT`, the timestamped
   directory from Step 2 of this session). Each run writes its PID into its own
   run root, so a PID file you did not just create is the stale case — do not
   signal from it.

Binding the check to one specific run, so neither rule has to be remembered, is
tracked as follow-up **OBS-3**.

> Do not substitute a `pgrep -f --capture-selector-view` style count for rule 1.
> That pattern is matched against whole command lines as text, so it also matches
> any shell or wrapper whose own command line happens to contain the flag —
> verified to return spurious extra PIDs. A check that cries wolf is worse than
> no check, because it teaches you to ignore it.

If, and only if, **all** hold — the check exited 0, `$SV_PID` came from the run
root you started, and you can account for every selector-view capture on the
host:

```bash
kill "$SV_PID"          # SIGTERM; never leaves a half-written record
sleep 5
ps -p "$SV_PID" > /dev/null && echo "still running" || echo "stopped"
tail -n 20 "$SV_ROOT/autopilot_observe_selector_view.log"
```

The tool handles SIGTERM (and SIGINT) and exits at its next checkpoint, always
logging `"status": "stopped_by_signal"` last. It does not wait out the remaining
sleep interval. What happens to the tick in progress depends on where the signal
lands, and the `detail` in that final log line tells you which case you got:

- **Idle between ticks** (the common case) — nothing is in flight. Detail:
  `stop signal received between ticks; no tick was in flight`.
- **While polling, with a fetch still ahead** — the tick is abandoned and
  nothing is written. An extra line logs `"status": "tick_abandoned_on_stop"`
  first, then the detail `stop signal received while polling; the unwritten tick
  was abandoned`. That timestamp has no manifest and no rows, so it reads
  downstream as a tick that never ran, which is what it is.
- **Too late to abandon** — during record construction, during the append, or
  during the tick's *final* fetch (the stop is only tested at each fetch
  boundary, and the last fetch has none after it). The append completes and the
  file is closed. Detail: `stop signal received once the tick was past
  abandoning; its append completed`.

So a stop guarantees neither that the in-flight tick finishes nor that it is
abandoned — which you get depends on timing. What it does guarantee is that no
tick is ever left half-written: every record on disk is whole, and a stopped run
ends either with a complete final record or with no record for that tick.

Expected time to exit:

- Idle between ticks (the common case): well under a second.
- Mid-tick: up to one HTTP timeout (`AUTOPILOT_OBSERVE_TIMEOUT_SECONDS`,
  default 10s). A tick makes seven sequential fetches, but a stop is honoured at
  the next fetch boundary — it does not wait out all seven. If a boundary
  remains, the tick is abandoned rather than half-recorded and the log says
  `"status": "tick_abandoned_on_stop"`; nothing is written, so that timestamp is
  simply a missing tick, which is what it is. If the stop lands during the
  seventh fetch there is no boundary left, so that tick completes and is
  appended — see the case list above.
- If an endpoint is not merely slow but dribbles bytes indefinitely, the socket
  timeout never fires and the fetch can outlast the estimate above. That is the
  case for the `kill -9` escalation below.

If it is still running after ~30s, escalate to the Operator before using
`kill -9`: SIGKILL cannot be handled, so a hard kill during a JSONL append can
still truncate the final record. The capture is append-only and
observation-only, so a stopped run loses no committed evidence: every completed
tick is already durable on disk. A truncated tail is detectable rather than
silent — see "Tick manifests" above.

## Capture Attribution Inputs

Capture strategy-service history after the observation window. The service caps
each response at 20,000 rows; for exact multi-day attribution, prefer shorter
report windows or repeat this capture/report step daily.

`only_pass=false` is important for ready-window boundaries because the report
uses non-ready rows to split contiguous ready windows.

```bash
ATTRIBUTION_HOURS=24

curl -fsS \
  "http://127.0.0.1:8083/v1/strategy/pairs/opportunity-history?timeframe=1m&hours=$ATTRIBUTION_HOURS&only_pass=false&limit=20000" \
  -o "$RUN_ROOT/opportunity_history_1m.json"

curl -fsS \
  "http://127.0.0.1:8083/v1/strategy/pairs/paper-trades?timeframe=1m&hours=$ATTRIBUTION_HOURS&limit=20000" \
  -o "$RUN_ROOT/paper_trades_1m.json"

python3 -m json.tool "$RUN_ROOT/opportunity_history_1m.json" >/dev/null
python3 -m json.tool "$RUN_ROOT/paper_trades_1m.json" >/dev/null
```

## Build The AUTO-1C Report

Use a lookahead window that matches the attribution question. For the first
trial, `240` minutes is a useful bounded default for "did this observation lead
to a near-term simulated paper entry?"

```bash
python3 tools/scripts/autopilot_observe_report.py \
  --observe-dir "$RUN_ROOT/records" \
  --opportunity-history-json "$RUN_ROOT/opportunity_history_1m.json" \
  --paper-trades-json "$RUN_ROOT/paper_trades_1m.json" \
  --lookahead-minutes 240 \
  --output-json "$RUN_ROOT/autopilot_observe_report.json" \
  --output-markdown "$RUN_ROOT/autopilot_observe_report.md"

jq '.summary' "$RUN_ROOT/autopilot_observe_report.json"
sed -n '1,120p' "$RUN_ROOT/autopilot_observe_report.md"
```

## Evidence Bundle Checklist

Keep these files together for review:

- `$RUN_ROOT/git_status.txt`
- `$RUN_ROOT/git_head.txt`
- `$RUN_ROOT/data_health.json`
- `$RUN_ROOT/strategy_health.json`
- `$RUN_ROOT/dispatch_mode.json`
- `$RUN_ROOT/kill_switch.json`
- `$RUN_ROOT/disabled_probe.json`
- `$RUN_ROOT/quality_windows.json`
- `$RUN_ROOT/autopilot_observe.log`
- `$RUN_ROOT/records/**/autopilot_observe_*.jsonl`
- `$RUN_ROOT/opportunity_history_1m.json`
- `$RUN_ROOT/paper_trades_1m.json`
- `$RUN_ROOT/autopilot_observe_report.json`
- `$RUN_ROOT/autopilot_observe_report.md`

Do not merge this evidence into the repository. It is host/runtime evidence and
should stay under ignored `artifacts/`.

## Failure Handling

1. If the disabled probe is not disabled, stop and inspect environment leakage.
2. If data-service or strategy-service health fails, stop the observe run and
   investigate service health before collecting candidate evidence.
3. If execution-service reports malformed dispatch mode, active kill switch
   payload shape errors, or open-trades source errors, the observer should emit
   blocked records. Treat this as valid safety evidence, not as a reason to
   bypass guards.
4. If report generation fails on non-`1m` input, discard that evidence set for
   AUTO-1 and recapture with 1m-only inputs.
5. If endpoint row caps truncate the attribution input, lower
   `ATTRIBUTION_HOURS` or split analysis into daily evidence bundles.
