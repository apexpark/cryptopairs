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
