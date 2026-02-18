use anyhow::{anyhow, Result};
use async_trait::async_trait;
use common_types::{Candle, DataIntegrityReport, DataQueryRequest, Timeframe};
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
        Ok(Self { client })
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
}

fn timeframe_string(timeframe: Timeframe) -> &'static str {
    match timeframe {
        Timeframe::OneMinute => "1m",
        Timeframe::FifteenMinutes => "15m",
        Timeframe::OneHour => "1h",
    }
}
