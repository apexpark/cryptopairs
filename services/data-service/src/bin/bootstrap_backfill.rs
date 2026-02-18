use anyhow::Result;
use chrono::{DateTime, Duration, Utc};
use common_types::{DataQueryRequest, Timeframe};
use data_service::{
    config::Settings,
    gap_detector::build_integrity_report,
    repository::{MarketDataRepository, PostgresMarketDataRepository},
};
use kraken_adapter::{KrakenFuturesRestClient, MarketDataAdapter};
use std::sync::Arc;
use tracing::{info, warn};

const DEFAULT_BOOTSTRAP_START: &str = "2020-02-26T00:00:00Z";
const PAGE_CANDLE_LIMIT: i64 = 2000;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let settings = Settings::from_env();
    let start =
        std::env::var("BOOTSTRAP_START_TS").unwrap_or_else(|_| DEFAULT_BOOTSTRAP_START.to_string());
    let bootstrap_start = DateTime::parse_from_rfc3339(&start)?.with_timezone(&Utc);
    let now = Utc::now();

    let repository: Arc<dyn MarketDataRepository> =
        Arc::new(PostgresMarketDataRepository::connect(&settings.postgres_url).await?);
    let adapter: Arc<dyn MarketDataAdapter> = Arc::new(KrakenFuturesRestClient::new(
        settings.kraken_base_url.clone(),
    ));

    for symbol in &settings.symbols {
        for timeframe in [
            Timeframe::OneMinute,
            Timeframe::FifteenMinutes,
            Timeframe::OneHour,
        ] {
            backfill_symbol_timeframe(
                symbol,
                timeframe,
                bootstrap_start,
                now,
                &repository,
                &adapter,
                settings.integrity_threshold_pct,
            )
            .await?;
        }
    }

    Ok(())
}

async fn backfill_symbol_timeframe(
    symbol: &str,
    timeframe: Timeframe,
    mut cursor: DateTime<Utc>,
    end: DateTime<Utc>,
    repository: &Arc<dyn MarketDataRepository>,
    adapter: &Arc<dyn MarketDataAdapter>,
    integrity_threshold_pct: f64,
) -> Result<()> {
    let step = timeframe.step_seconds();
    let chunk_seconds = step * (PAGE_CANDLE_LIMIT - 1);

    while cursor <= end {
        let window_end = std::cmp::min(cursor + Duration::seconds(chunk_seconds), end);
        let request = DataQueryRequest {
            instrument: symbol.to_string(),
            timeframe,
            start_ts: cursor,
            end_ts: window_end,
        };

        let fetched = match adapter.fetch_candles(&request).await {
            Ok(candles) => candles,
            Err(error) => {
                warn!(
                    instrument = symbol,
                    timeframe = ?timeframe,
                    start_ts = %cursor,
                    end_ts = %window_end,
                    error = %error,
                    "bootstrap fetch failed"
                );
                cursor = window_end + Duration::seconds(step);
                continue;
            }
        };

        if !fetched.is_empty() {
            let written = repository
                .upsert_candles(symbol, timeframe, &fetched)
                .await?;
            info!(
                instrument = symbol,
                timeframe = ?timeframe,
                start_ts = %cursor,
                end_ts = %window_end,
                fetched = fetched.len(),
                written,
                "bootstrap chunk persisted"
            );
        }

        let local = repository.fetch_candles(&request).await?;
        let report = build_integrity_report(&request, &local, integrity_threshold_pct);
        repository
            .record_quality_interval(&request, &report)
            .await?;

        if report.coverage_pct < integrity_threshold_pct {
            warn!(
                instrument = symbol,
                timeframe = ?timeframe,
                start_ts = %cursor,
                end_ts = %window_end,
                coverage_pct = report.coverage_pct,
                status = report.status.as_str(),
                "bootstrap chunk below integrity threshold"
            );
        }

        cursor = window_end + Duration::seconds(step);
    }

    Ok(())
}
