use crate::AppState;
use chrono::{Duration, Utc};
use common_types::{DataQueryRequest, Timeframe};
use tokio::time::{sleep, Duration as TokioDuration};
use tracing::{info, warn};

pub fn spawn_backfill_worker(
    state: AppState,
    symbols: Vec<String>,
    interval_seconds: u64,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        loop {
            for symbol in &symbols {
                for timeframe in [
                    Timeframe::OneMinute,
                    Timeframe::FifteenMinutes,
                    Timeframe::OneHour,
                ] {
                    let now = Utc::now();
                    let window_start = match timeframe {
                        Timeframe::OneMinute => now - Duration::hours(24),
                        Timeframe::FifteenMinutes => now - Duration::days(30),
                        Timeframe::OneHour => now - Duration::days(120),
                    };
                    let request = DataQueryRequest {
                        instrument: symbol.clone(),
                        timeframe,
                        start_ts: window_start,
                        end_ts: now,
                    };

                    if let Err(error) = backfill_window(&state, &request).await {
                        warn!(
                            instrument = %symbol,
                            timeframe = ?timeframe,
                            error = %error,
                            "backfill worker failed for window"
                        );
                    }
                }
            }

            sleep(TokioDuration::from_secs(interval_seconds)).await;
        }
    })
}

async fn backfill_window(state: &AppState, request: &DataQueryRequest) -> anyhow::Result<()> {
    let local = state.repository.fetch_candles(request).await?;
    let report =
        crate::gap_detector::build_integrity_report(request, &local, state.integrity_threshold_pct);
    if report.missing_ranges.is_empty() {
        return Ok(());
    }

    let mut total_written = 0usize;
    for range in report.missing_ranges {
        let segment = DataQueryRequest {
            instrument: request.instrument.clone(),
            timeframe: request.timeframe,
            start_ts: range.start_ts,
            end_ts: range.end_ts,
        };
        let fetched = match state.adapter.fetch_candles(&segment).await {
            Ok(candles) => candles,
            Err(error) => {
                warn!(
                    instrument = %request.instrument,
                    timeframe = ?request.timeframe,
                    start_ts = %segment.start_ts,
                    end_ts = %segment.end_ts,
                    error = %error,
                    "backfill segment request failed"
                );
                continue;
            }
        };
        if fetched.is_empty() {
            continue;
        }
        total_written += state
            .repository
            .upsert_candles(&request.instrument, request.timeframe, &fetched)
            .await?;
    }

    info!(
        instrument = %request.instrument,
        timeframe = ?request.timeframe,
        total_written,
        "backfill worker persisted candles"
    );

    let refreshed = state.repository.fetch_candles(request).await?;
    let refreshed_report = crate::gap_detector::build_integrity_report(
        request,
        &refreshed,
        state.integrity_threshold_pct,
    );
    state
        .repository
        .record_quality_interval(request, &refreshed_report)
        .await?;
    Ok(())
}
