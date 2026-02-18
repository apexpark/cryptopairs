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
