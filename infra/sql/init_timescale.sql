CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS candles (
  instrument TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION NOT NULL,
  source TEXT NOT NULL DEFAULT 'kraken_futures',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (instrument, timeframe, ts)
);

SELECT create_hypertable('candles', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS data_quality_intervals (
  instrument TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  coverage_pct DOUBLE PRECISION NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (instrument, timeframe, start_ts, end_ts, checked_at)
);

SELECT create_hypertable('data_quality_intervals', 'checked_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS trades (
  instrument TEXT NOT NULL,
  seq BIGINT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  side TEXT NOT NULL,
  price DOUBLE PRECISION NOT NULL,
  qty DOUBLE PRECISION NOT NULL,
  uid TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (instrument, seq)
);

CREATE TABLE IF NOT EXISTS account_snapshots (
  exchange TEXT NOT NULL,
  account_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  equity DOUBLE PRECISION NOT NULL,
  balance DOUBLE PRECISION NOT NULL,
  margin_used DOUBLE PRECISION NOT NULL,
  unrealized_pnl DOUBLE PRECISION NOT NULL,
  realized_pnl DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (exchange, account_id, ts)
);

CREATE TABLE IF NOT EXISTS reconciliation_events (
  exchange TEXT NOT NULL,
  account_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  drift_notional DOUBLE PRECISION NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (exchange, account_id, ts)
);

CREATE TABLE IF NOT EXISTS execution_control (
  id SMALLINT PRIMARY KEY DEFAULT 1,
  kill_switch_active BOOLEAN NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS execution_control_events (
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  kill_switch_active BOOLEAN NOT NULL,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS execution_order_intents (
  idempotency_key TEXT PRIMARY KEY,
  exchange TEXT NOT NULL DEFAULT 'kraken_futures',
  account_id TEXT NOT NULL DEFAULT 'default',
  instrument TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  action TEXT NOT NULL,
  side TEXT NOT NULL,
  qty DOUBLE PRECISION NOT NULL,
  operator_confirmed BOOLEAN NOT NULL,
  operator_id TEXT,
  min_coverage_pct DOUBLE PRECISION NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_order_state_events (
  idempotency_key TEXT NOT NULL,
  state TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL DEFAULT 'system',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (idempotency_key, state, created_at)
);

CREATE TABLE IF NOT EXISTS execution_dispatch_attempts (
  idempotency_key TEXT NOT NULL,
  attempt_no INTEGER NOT NULL,
  result_state TEXT NOT NULL,
  exchange_order_id TEXT,
  reason TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL DEFAULT 'execution-service',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (idempotency_key, attempt_no)
);

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS exchange TEXT NOT NULL DEFAULT 'kraken_futures';

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS account_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'ENTRY';

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS operator_confirmed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS operator_id TEXT;

CREATE TABLE IF NOT EXISTS strategy_signal_performance (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  signal_variant TEXT NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  score_last DOUBLE PRECISION NOT NULL,
  sample_count INTEGER NOT NULL,
  win_rate DOUBLE PRECISION NOT NULL,
  edge_bps DOUBLE PRECISION NOT NULL,
  reliability DOUBLE PRECISION NOT NULL,
  regime TEXT NOT NULL,
  opportunity_score DOUBLE PRECISION NOT NULL,
  rationale TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe, signal_variant, window_end)
);

ALTER TABLE strategy_signal_performance
ADD COLUMN IF NOT EXISTS score_last DOUBLE PRECISION NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS strategy_selected_signal (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  signal_variant TEXT NOT NULL,
  opportunity_score DOUBLE PRECISION NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe)
);

CREATE TABLE IF NOT EXISTS strategy_shadow_model_runs (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  run_at TIMESTAMPTZ NOT NULL,
  model_name TEXT NOT NULL,
  status TEXT NOT NULL,
  training_rows INTEGER NOT NULL,
  positive_rate DOUBLE PRECISION NOT NULL,
  precision DOUBLE PRECISION NOT NULL,
  brier_score DOUBLE PRECISION NOT NULL,
  recommended_variant TEXT NOT NULL,
  recommended_probability DOUBLE PRECISION NOT NULL,
  agrees_with_selected BOOLEAN NOT NULL,
  rationale TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe, run_at)
);

CREATE TABLE IF NOT EXISTS strategy_champion_drift_events (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  event_at TIMESTAMPTZ NOT NULL,
  champion_variant TEXT NOT NULL,
  challenger_variant TEXT NOT NULL,
  champion_score DOUBLE PRECISION NOT NULL,
  challenger_score DOUBLE PRECISION NOT NULL,
  score_delta DOUBLE PRECISION NOT NULL,
  decision TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe, event_at)
);

CREATE TABLE IF NOT EXISTS strategy_opportunity_history (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  evaluated_at TIMESTAMPTZ NOT NULL,
  left_instrument TEXT NOT NULL,
  right_instrument TEXT NOT NULL,
  selected_variant TEXT NOT NULL,
  regime TEXT NOT NULL,
  direction_hint TEXT NOT NULL,
  spread_z DOUBLE PRECISION NOT NULL,
  opportunity_score DOUBLE PRECISION NOT NULL,
  net_edge_bps DOUBLE PRECISION NOT NULL,
  cost_gate_pass BOOLEAN NOT NULL,
  actionable BOOLEAN NOT NULL,
  rationale_codes TEXT NOT NULL DEFAULT '',
  cost_gate_rationale_codes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe, evaluated_at)
);

CREATE TABLE IF NOT EXISTS strategy_paper_trades (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  exit_mode TEXT NOT NULL,
  left_instrument TEXT NOT NULL,
  right_instrument TEXT NOT NULL,
  selected_variant TEXT NOT NULL,
  entry_ts TIMESTAMPTZ NOT NULL,
  exit_ts TIMESTAMPTZ NOT NULL,
  bars_held INTEGER NOT NULL,
  direction TEXT NOT NULL,
  exit_kind TEXT NOT NULL,
  entry_z DOUBLE PRECISION NOT NULL,
  exit_z DOUBLE PRECISION NOT NULL,
  entry_index INTEGER NOT NULL,
  exit_index INTEGER NOT NULL,
  left_entry DOUBLE PRECISION NOT NULL,
  left_exit DOUBLE PRECISION NOT NULL,
  right_entry DOUBLE PRECISION NOT NULL,
  right_exit DOUBLE PRECISION NOT NULL,
  left_leg_bps DOUBLE PRECISION NOT NULL,
  right_leg_bps DOUBLE PRECISION NOT NULL,
  gross_bps DOUBLE PRECISION NOT NULL,
  round_trip_cost_bps DOUBLE PRECISION NOT NULL,
  net_bps DOUBLE PRECISION NOT NULL,
  equity_pre_entry DOUBLE PRECISION NOT NULL,
  equity_exit DOUBLE PRECISION NOT NULL,
  equity_trade_bps DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pair_id, timeframe, exit_mode, entry_ts, exit_ts, exit_kind)
);

CREATE TABLE IF NOT EXISTS strategy_candidate_runs (
  candidate_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  rank INTEGER NOT NULL,
  candidate_variant TEXT NOT NULL,
  status TEXT NOT NULL,
  decision_state TEXT NOT NULL,
  primary_reason_code TEXT NOT NULL,
  objective_score DOUBLE PRECISION NOT NULL,
  objective_delta DOUBLE PRECISION NOT NULL,
  config_json TEXT NOT NULL,
  metrics_json TEXT,
  walk_forward_json TEXT NOT NULL,
  rationale_codes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_candidate_runs_pair_timeframe_created
ON strategy_candidate_runs (pair_id, timeframe, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_candidate_runs_request
ON strategy_candidate_runs (request_id);

CREATE TABLE IF NOT EXISTS strategy_candidate_probation (
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  candidate_id TEXT NOT NULL REFERENCES strategy_candidate_runs(candidate_id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  eligible_after TIMESTAMPTZ NOT NULL,
  probation_samples INTEGER NOT NULL DEFAULT 0,
  promotable BOOLEAN NOT NULL DEFAULT FALSE,
  last_reason TEXT NOT NULL DEFAULT '',
  last_candidate_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_champion_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_objective_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
  PRIMARY KEY (pair_id, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_strategy_candidate_probation_state
ON strategy_candidate_probation (state, promotable, updated_at DESC);

CREATE TABLE IF NOT EXISTS strategy_candidate_actions (
  id BIGSERIAL PRIMARY KEY,
  pair_id TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  action TEXT NOT NULL,
  state_before TEXT NOT NULL,
  state_after TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  operator_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
