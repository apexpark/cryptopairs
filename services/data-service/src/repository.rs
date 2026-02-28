use anyhow::{anyhow, Result};
use async_trait::async_trait;
use chrono::{DateTime, Utc};
use common_types::{Candle, DataIntegrityReport, DataQueryRequest, Timeframe, TradeTick};
use tokio_postgres::Row;
use tokio_postgres::{types::ToSql, Client, NoTls};

#[async_trait]
pub trait MarketDataRepository: Send + Sync {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>>;
    async fn upsert_candles(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        candles: &[Candle],
    ) -> Result<usize>;
    async fn record_quality_interval(
        &self,
        request: &DataQueryRequest,
        report: &DataIntegrityReport,
    ) -> Result<()>;
    async fn insert_trades(&self, trades: &[TradeTick]) -> Result<usize>;
    async fn fetch_integrity_history(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        limit: i64,
    ) -> Result<Vec<IntegrityHistoryEntry>>;
    async fn delete_candles_older_than(
        &self,
        timeframe: Timeframe,
        cutoff_ts: DateTime<Utc>,
    ) -> Result<u64>;
}

#[derive(Debug, Clone)]
pub struct IntegrityHistoryEntry {
    pub instrument: String,
    pub timeframe: Timeframe,
    pub start_ts: chrono::DateTime<chrono::Utc>,
    pub end_ts: chrono::DateTime<chrono::Utc>,
    pub status: String,
    pub coverage_pct: f64,
    pub reason: String,
    pub checked_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Default)]
pub struct UnconfiguredRepository;

#[async_trait]
impl MarketDataRepository for UnconfiguredRepository {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>> {
        let _ = request;
        Err(anyhow!(
            "market data repository is not configured; wire TimescaleDB + Kraken backfill first"
        ))
    }

    async fn upsert_candles(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        candles: &[Candle],
    ) -> Result<usize> {
        let _ = (instrument, timeframe, candles);
        Err(anyhow!(
            "market data repository is not configured; upsert unavailable"
        ))
    }

    async fn record_quality_interval(
        &self,
        request: &DataQueryRequest,
        report: &DataIntegrityReport,
    ) -> Result<()> {
        let _ = (request, report);
        Err(anyhow!(
            "market data repository is not configured; quality interval recording unavailable"
        ))
    }

    async fn insert_trades(&self, trades: &[TradeTick]) -> Result<usize> {
        let _ = trades;
        Err(anyhow!(
            "market data repository is not configured; trade insert unavailable"
        ))
    }

    async fn fetch_integrity_history(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        limit: i64,
    ) -> Result<Vec<IntegrityHistoryEntry>> {
        let _ = (instrument, timeframe, limit);
        Err(anyhow!(
            "market data repository is not configured; integrity history unavailable"
        ))
    }

    async fn delete_candles_older_than(
        &self,
        timeframe: Timeframe,
        cutoff_ts: DateTime<Utc>,
    ) -> Result<u64> {
        let _ = (timeframe, cutoff_ts);
        Err(anyhow!(
            "market data repository is not configured; candle retention prune unavailable"
        ))
    }
}

pub struct PostgresMarketDataRepository {
    client: Client,
}

impl PostgresMarketDataRepository {
    pub async fn connect(connection_string: &str) -> Result<Self> {
        let (client, connection) = tokio_postgres::connect(connection_string, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                tracing::error!(error = %error, "postgres connection task ended");
            }
        });
        let repo = Self { client };
        repo.ensure_schema().await?;
        Ok(repo)
    }

    async fn ensure_schema(&self) -> Result<()> {
        self.client
            .batch_execute(
                "CREATE TABLE IF NOT EXISTS trades (
                    instrument TEXT NOT NULL,
                    seq BIGINT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    side TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    qty DOUBLE PRECISION NOT NULL,
                    uid TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (instrument, seq)
                 );",
            )
            .await?;
        Ok(())
    }
}

#[async_trait]
impl MarketDataRepository for PostgresMarketDataRepository {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>> {
        let rows = self
            .client
            .query(
                "SELECT ts, open, high, low, close, volume
                 FROM candles
                 WHERE instrument = $1
                   AND timeframe = $2
                   AND ts >= $3
                   AND ts <= $4
                 ORDER BY ts ASC",
                &[
                    &request.instrument as &(dyn ToSql + Sync),
                    &timeframe_string(request.timeframe),
                    &request.start_ts,
                    &request.end_ts,
                ],
            )
            .await?;

        Ok(rows
            .into_iter()
            .map(|row| Candle {
                ts: row.get(0),
                open: row.get(1),
                high: row.get(2),
                low: row.get(3),
                close: row.get(4),
                volume: row.get(5),
            })
            .collect())
    }

    async fn upsert_candles(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        candles: &[Candle],
    ) -> Result<usize> {
        let mut written = 0usize;
        let timeframe_value = timeframe_string(timeframe);
        for candle in candles {
            self.client
                .execute(
                    "INSERT INTO candles (instrument, timeframe, ts, open, high, low, close, volume)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                     ON CONFLICT (instrument, timeframe, ts)
                     DO UPDATE SET
                       open = EXCLUDED.open,
                       high = EXCLUDED.high,
                       low = EXCLUDED.low,
                       close = EXCLUDED.close,
                       volume = EXCLUDED.volume",
                    &[
                        &instrument as &(dyn ToSql + Sync),
                        &timeframe_value,
                        &candle.ts,
                        &candle.open,
                        &candle.high,
                        &candle.low,
                        &candle.close,
                        &candle.volume,
                    ],
                )
                .await?;
            written += 1;
        }
        Ok(written)
    }

    async fn record_quality_interval(
        &self,
        request: &DataQueryRequest,
        report: &DataIntegrityReport,
    ) -> Result<()> {
        let reason = report.warnings.join(" | ");
        self.client
            .execute(
                "INSERT INTO data_quality_intervals
                    (instrument, timeframe, start_ts, end_ts, status, coverage_pct, reason, checked_at)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                &[
                    &request.instrument as &(dyn ToSql + Sync),
                    &timeframe_string(request.timeframe),
                    &request.start_ts,
                    &request.end_ts,
                    &report.status.as_str(),
                    &report.coverage_pct,
                    &reason,
                    &report.last_verified_at,
                ],
            )
            .await?;
        Ok(())
    }

    async fn insert_trades(&self, trades: &[TradeTick]) -> Result<usize> {
        let mut inserted = 0usize;
        for trade in trades {
            let written = self
                .client
                .execute(
                    "INSERT INTO trades (instrument, seq, ts, side, price, qty, uid)
                     VALUES ($1, $2, $3, $4, $5, $6, $7)
                     ON CONFLICT (instrument, seq) DO NOTHING",
                    &[
                        &trade.instrument as &(dyn ToSql + Sync),
                        &trade.seq,
                        &trade.ts,
                        &trade.side,
                        &trade.price,
                        &trade.qty,
                        &trade.uid,
                    ],
                )
                .await?;
            inserted += written as usize;
        }
        Ok(inserted)
    }

    async fn fetch_integrity_history(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        limit: i64,
    ) -> Result<Vec<IntegrityHistoryEntry>> {
        let rows = self
            .client
            .query(
                "SELECT instrument, timeframe, start_ts, end_ts, status, coverage_pct, reason, checked_at
                 FROM data_quality_intervals
                 WHERE instrument = $1 AND timeframe = $2
                 ORDER BY checked_at DESC
                 LIMIT $3",
                &[&instrument, &timeframe_string(timeframe), &limit],
            )
            .await?;
        Ok(rows.into_iter().map(map_integrity_history_row).collect())
    }

    async fn delete_candles_older_than(
        &self,
        timeframe: Timeframe,
        cutoff_ts: DateTime<Utc>,
    ) -> Result<u64> {
        let deleted = self
            .client
            .execute(
                "DELETE FROM candles
                 WHERE timeframe = $1
                   AND ts < $2",
                &[&timeframe_string(timeframe), &cutoff_ts],
            )
            .await?;
        Ok(deleted)
    }
}

fn timeframe_string(timeframe: Timeframe) -> &'static str {
    timeframe.as_str()
}

fn map_integrity_history_row(row: Row) -> IntegrityHistoryEntry {
    let timeframe_raw: String = row.get(1);
    IntegrityHistoryEntry {
        instrument: row.get(0),
        timeframe: Timeframe::parse(&timeframe_raw).unwrap_or(Timeframe::OneMinute),
        start_ts: row.get(2),
        end_ts: row.get(3),
        status: row.get(4),
        coverage_pct: row.get(5),
        reason: row.get(6),
        checked_at: row.get(7),
    }
}
