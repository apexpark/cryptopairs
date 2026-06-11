# Signal Learning Runbook (Experimental Branch)

## Purpose

Run a deterministic overnight monitoring loop that:
1. Samples live strategy outputs by pair/timeframe.
2. Builds rolling evidence of expectancy and realized paper-trade quality.
3. Updates a **recommendation-only** signal logic artifact with strict confidence gates.

This runbook does **not** auto-apply strategy changes.

## Scope And Safety

1. Branch scope: experimental worktree only.
2. Runtime scope: read-only against strategy API endpoints.
3. Output scope:
   - cycle artifacts in `artifacts/signal_learning/runs/`
   - rolling state in `artifacts/signal_learning/state.json`
   - recursive logic recommendations in `artifacts/signal_learning/signal_logic.json`
4. No writes to runtime selected-signal config or deploy settings.
5. Hosted cadence runs must execute one cycle per timer tick. Do not use an
   unmanaged long-running shell loop on the hosted machine.

## Inputs

- Policy: `infra/config/signal_learning_policy.json`
- Strategy endpoints:
  - `GET /v1/strategy/pairs/cues`
  - `GET /v1/strategy/pairs/expectancy`
  - `GET /v1/strategy/pairs/paper-trades`

## Overnight Local Run

From experimental repo root:

```bash
cd /Users/kevinsaunders/Documents/Crypto_PairsTrader-signal-redesign
bash scripts/run_signal_learning_overnight.sh \
  --strategy-url http://127.0.0.1:18083 \
  --cycles 48 \
  --sleep-seconds 900
```

Example above: 48 cycles at 15-minute intervals (~12 hours).

Background mode:

```bash
cd /Users/kevinsaunders/Documents/Crypto_PairsTrader-signal-redesign
nohup bash scripts/run_signal_learning_overnight.sh --strategy-url http://127.0.0.1:18083 > /tmp/signal-learning.log 2>&1 &
tail -f /tmp/signal-learning.log
```

## Hosted Trade Now Overlay Cadence

`GET /v1/strategy/pairs/trade-now` treats the latest signal-learning cycle
artifact as the approved-universe overlay. The strategy service reads the newest
`*signal-learning-cycle.json` file from `/workspace/artifacts/signal_learning/runs`;
on the hosted machine this maps to `/opt/cryptopairs/artifacts/signal_learning/runs`
because `docker-compose.yml` mounts the repo at `/workspace`.

The overlay TTL is 24 hours. If no fresh artifact exists, Trade Now fails closed
by downgrading learning-selected rows to Watchlist or Excluded. Keep the overlay
fresh with a timer that runs one read-only learning cycle per tick.

Install or update the hosted systemd timer:

```bash
cd /opt/cryptopairs
sudo bash scripts/install_signal_learning_cadence_systemd.sh \
  --repo-root /opt/cryptopairs \
  --strategy-url http://127.0.0.1:8083 \
  --interval-seconds 900
```

Show timer status:

```bash
sudo bash scripts/install_signal_learning_cadence_systemd.sh --show
systemctl list-timers cryptopairs-signal-learning-cadence.timer --all
```

Run one foreground refresh without installing the timer:

```bash
cd /opt/cryptopairs
bash scripts/run_signal_learning_overnight.sh \
  --strategy-url http://127.0.0.1:8083 \
  --cycles 1 \
  --sleep-seconds 0 \
  --timeframes 1m,15m,1h
```

Verify that artifacts are current and Trade Now sees a fresh overlay:

```bash
cd /opt/cryptopairs
ls -lt artifacts/signal_learning/runs | head
tail -n 100 artifacts/signal_learning/cadence.log

latest_cycle="$(find artifacts/signal_learning/runs -maxdepth 1 \
  -name '*-signal-learning-cycle.json' -type f -print | sort | tail -n 1)"
test -n "${latest_cycle}"
jq '{
    generated_at,
    degraded_timeframes: .summary.degraded_timeframes,
    timeframe_statuses: [
      .timeframe_reports[] | {
        timeframe,
        status,
        error_count: (.errors | length),
        errors
      }
    ]
  }' "${latest_cycle}"
jq -e '.summary.degraded_timeframes == 0' "${latest_cycle}"

for tf in 1m 15m 1h; do
  echo "=== $tf ==="
  curl -fsS "http://127.0.0.1:8083/v1/strategy/pairs/trade-now?timeframe=$tf" \
    | jq '{
        learning_overlay_fresh,
        learning_overlay_age_seconds,
        tradable_now_count: (.tradable_now | length),
        watchlist_count: (.watchlist | length),
        excluded_count: (.excluded | length)
      }'
done
```

Treat any non-zero `summary.degraded_timeframes` as a failed refresh even if the
artifact timestamp is fresh. The cycle script records partial API failures as
`DEGRADED` in the artifact so operators can inspect the timeframe-level errors
without starting a live trading path.

Pause or remove the timer:

```bash
sudo systemctl stop cryptopairs-signal-learning-cadence.timer
sudo systemctl stop cryptopairs-signal-learning-cadence.service
sudo bash scripts/install_signal_learning_cadence_systemd.sh --remove
```

Failure mode: if the timer fails, the previous artifact ages out and Trade Now
fails closed when the overlay becomes stale. Inspect
`artifacts/signal_learning/cadence.log` and `journalctl -u
cryptopairs-signal-learning-cadence.service` before restarting the timer.

## Artifact Review

1. Latest cycle files:

```bash
ls -lah artifacts/signal_learning/runs | tail -n 10
```

2. Current recursive logic recommendations:

```bash
cat artifacts/signal_learning/signal_logic.json | head -n 80
```

3. Rolling state sample:

```bash
cat artifacts/signal_learning/state.json | head -n 80
```

## Promotion Discipline (No Aberration Upgrades)

Use these minimum evidence rules before integrating recommendation output into strategy runtime:

1. At least `min_cycles_for_confidence` cycles met (policy).
2. At least `min_combined_trades` combined expectancy + paper trades (policy).
3. Recommendation confidence at or above 0.70.
4. Recommendation direction stable for at least 2 consecutive review windows.
5. No degraded cycle spike dominating the decision period.

If any of the above are not satisfied, keep recommendation as `HOLD`.

## Operational Notes

1. If API fetch fails for a timeframe, that cycle is marked `DEGRADED`.
2. Mutation cooldown is enforced in cycle counts (`cooldown_cycles_between_mutations`).
3. Severe, stable negative evidence can disable a pair in the recommendation artifact, but runtime remains unchanged until operator chooses to implement.
4. Universe selection applies a minimum paper-trade depth gate (`selection.min_paper_trades_for_selection`) before top-k ranking.
5. Optional low-sample backfill (`selection.allow_low_sample_backfill`) can fill remaining slots when the paper-depth-gated set is too small.

## Next Step After Overnight Run

1. Compare recommendation deltas against baseline logic file and current runtime metrics.
2. Prepare a bounded implementation PR that only applies high-confidence, repeated recommendations.
3. Validate via:
   - `tools/scripts/signal_gate_pnl_audit.py`
   - `scripts/benchmark_signal_engines.sh`
   - side-by-side EXP vs MAIN checks before merge decision.

## Tuesday-Style One-Command Review

After a monitoring run started with `scripts/start_weekend_signal_monitoring.sh`, run:

```bash
bash scripts/report_signal_monitoring_pass_fail.sh --repo-root /Users/kevinsaunders/Documents/Crypto_PairsTrader-signal-redesign
```

This report:
1. Loads the latest monitoring metadata (`artifacts/runtime/weekend-monitoring-latest.json`).
2. Evaluates the exact acceptance checks:
   - low-sample selection must be zero
   - degraded timeframes must be zero
   - compare pair-set mismatch must be zero and transient compare errors must be within threshold
   - benchmark EXP win rate must be at least MAIN win rate
   - selector stability must pass (top-k overlap + top-k member dwell)
   - 48-pair coverage ratio must exceed threshold
3. Exits `0` on pass and non-zero on fail for automation compatibility.

Optional threshold overrides:

```bash
bash scripts/report_signal_monitoring_pass_fail.sh \
  --repo-root /Users/kevinsaunders/Documents/Crypto_PairsTrader-signal-redesign \
  --selector-topk-overlap-min 0.60 \
  --selector-dwell-mean-min 2.0 \
  --max-compare-errors 1 \
  --max-pairset-mismatch 0
```

Notes:
1. Selector stability is derived from cycle artifacts in-window:
   - adjacent top-k overlap mean
   - top-k member dwell mean across consecutive cycles
2. Window-local top1 turnover is still reported as an audit metric, but is not used as the acceptance gate.
3. Pairset stability supports a bounded transient compare error budget while still requiring zero pair-set mismatch warnings by default.
