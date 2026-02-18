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

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'ENTRY';

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS operator_confirmed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE execution_order_intents
ADD COLUMN IF NOT EXISTS operator_id TEXT;
