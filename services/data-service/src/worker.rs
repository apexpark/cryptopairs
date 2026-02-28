use crate::{config::TimeframeDays, normalize_request_window, AppState};
use chrono::{DateTime, Duration, Utc};
use common_types::{DataQueryRequest, Timeframe};
use tokio::time::{sleep, Duration as TokioDuration};
use tracing::{info, warn};

const KRAKEN_MAX_CANDLES_PER_REQUEST: i64 = 2000;

pub fn spawn_backfill_worker(
    state: AppState,
    symbols: Vec<String>,
    interval_seconds: u64,
    backfill_window_days: TimeframeDays,
    candles_retention_days: TimeframeDays,
    prune_interval_seconds: u64,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut last_prune_at: Option<DateTime<Utc>> = None;
        loop {
            for symbol in &symbols {
                for timeframe in [
                    Timeframe::OneMinute,
                    Timeframe::FifteenMinutes,
                    Timeframe::OneHour,
                ] {
                    let now = Utc::now();
                    let window_start = backfill_window_start(now, timeframe, backfill_window_days);
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

            let now = Utc::now();
            if should_run_retention_prune(last_prune_at, now, prune_interval_seconds) {
                match prune_expired_candles(&state, now, candles_retention_days).await {
                    Ok(_) => {
                        last_prune_at = Some(now);
                    }
                    Err(error) => {
                        warn!(
                            error = %error,
                            "candle retention prune failed"
                        );
                    }
                }
            }

            sleep(TokioDuration::from_secs(interval_seconds)).await;
        }
    })
}

async fn backfill_window(state: &AppState, request: &DataQueryRequest) -> anyhow::Result<()> {
    let normalized_request = normalize_request_window(request);
    let local = state.repository.fetch_candles(&normalized_request).await?;
    let report = crate::gap_detector::build_integrity_report(
        &normalized_request,
        &local,
        state.integrity_threshold_pct,
    );
    if report.missing_ranges.is_empty() {
        return Ok(());
    }

    let mut total_written = 0usize;
    let step_seconds = normalized_request.timeframe.step_seconds();

    for range in report.missing_ranges {
        for (segment_start, segment_end) in split_range_into_segments(
            range.start_ts,
            range.end_ts,
            step_seconds,
            KRAKEN_MAX_CANDLES_PER_REQUEST,
        ) {
            let segment = DataQueryRequest {
                instrument: normalized_request.instrument.clone(),
                timeframe: normalized_request.timeframe,
                start_ts: segment_start,
                end_ts: segment_end,
            };
            let fetched = match state.adapter.fetch_candles(&segment).await {
                Ok(candles) => candles,
                Err(error) => {
                    warn!(
                        instrument = %normalized_request.instrument,
                        timeframe = ?normalized_request.timeframe,
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
                .upsert_candles(
                    &normalized_request.instrument,
                    normalized_request.timeframe,
                    &fetched,
                )
                .await?;
        }
    }

    info!(
        instrument = %normalized_request.instrument,
        timeframe = ?normalized_request.timeframe,
        total_written,
        "backfill worker persisted candles"
    );

    let refreshed = state.repository.fetch_candles(&normalized_request).await?;
    let refreshed_report = crate::gap_detector::build_integrity_report(
        &normalized_request,
        &refreshed,
        state.integrity_threshold_pct,
    );
    state
        .repository
        .record_quality_interval(&normalized_request, &refreshed_report)
        .await?;
    Ok(())
}

fn backfill_window_start(
    now: DateTime<Utc>,
    timeframe: Timeframe,
    backfill_window_days: TimeframeDays,
) -> DateTime<Utc> {
    now - Duration::days(backfill_window_days.days_for(timeframe))
}

fn should_run_retention_prune(
    last_prune_at: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
    prune_interval_seconds: u64,
) -> bool {
    match last_prune_at {
        None => true,
        Some(last) => {
            now.signed_duration_since(last).num_seconds() >= prune_interval_seconds.max(60) as i64
        }
    }
}

async fn prune_expired_candles(
    state: &AppState,
    now: DateTime<Utc>,
    retention_days: TimeframeDays,
) -> anyhow::Result<()> {
    for timeframe in [
        Timeframe::OneMinute,
        Timeframe::FifteenMinutes,
        Timeframe::OneHour,
    ] {
        let days = retention_days.days_for(timeframe);
        let cutoff_ts = now - Duration::days(days);
        let deleted = state
            .repository
            .delete_candles_older_than(timeframe, cutoff_ts)
            .await?;
        info!(
            timeframe = ?timeframe,
            retention_days = days,
            cutoff_ts = %cutoff_ts,
            rows_deleted = deleted,
            "candle retention prune completed"
        );
    }
    Ok(())
}

fn split_range_into_segments(
    start_ts: DateTime<Utc>,
    end_ts: DateTime<Utc>,
    step_seconds: i64,
    max_candles_per_request: i64,
) -> Vec<(DateTime<Utc>, DateTime<Utc>)> {
    if step_seconds <= 0 || max_candles_per_request <= 1 || end_ts < start_ts {
        return vec![];
    }

    let chunk_seconds = step_seconds * (max_candles_per_request - 1);
    let mut segments = Vec::new();
    let mut cursor = start_ts;
    while cursor <= end_ts {
        let segment_end = std::cmp::min(cursor + Duration::seconds(chunk_seconds), end_ts);
        segments.push((cursor, segment_end));
        cursor = segment_end + Duration::seconds(step_seconds);
    }
    segments
}

#[cfg(test)]
mod tests {
    use super::{backfill_window_start, should_run_retention_prune, split_range_into_segments};
    use crate::config::TimeframeDays;
    use chrono::{TimeZone, Utc};
    use common_types::Timeframe;

    #[test]
    fn split_range_respects_page_depth_limit() {
        let start = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        let end = Utc
            .timestamp_opt(1_700_172_740, 0)
            .single()
            .expect("valid timestamp");
        let segments = split_range_into_segments(start, end, 60, 2_000);
        assert_eq!(segments.len(), 2);
        assert_eq!(
            segments[0].1.timestamp() - segments[0].0.timestamp(),
            60 * 1_999
        );
        assert!(segments[1].1 <= end);
    }

    #[test]
    fn split_range_returns_empty_for_invalid_inputs() {
        let start = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        let end = Utc
            .timestamp_opt(1_699_999_940, 0)
            .single()
            .expect("valid timestamp");
        assert!(split_range_into_segments(start, end, 60, 2_000).is_empty());
        assert!(split_range_into_segments(start, start, 0, 2_000).is_empty());
        assert!(split_range_into_segments(start, start, 60, 1).is_empty());
    }

    #[test]
    fn backfill_window_start_uses_timeframe_day_config() {
        let now = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        let days = TimeframeDays {
            one_minute: 120,
            fifteen_minutes: 540,
            one_hour: 1_095,
        };

        let one_minute_start = backfill_window_start(now, Timeframe::OneMinute, days);
        let fifteen_minute_start = backfill_window_start(now, Timeframe::FifteenMinutes, days);
        let one_hour_start = backfill_window_start(now, Timeframe::OneHour, days);

        assert_eq!(now.signed_duration_since(one_minute_start).num_days(), 120);
        assert_eq!(
            now.signed_duration_since(fifteen_minute_start).num_days(),
            540
        );
        assert_eq!(now.signed_duration_since(one_hour_start).num_days(), 1_095);
    }

    #[test]
    fn retention_prune_interval_respected() {
        let now = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        let last = now - chrono::Duration::seconds(1_000);

        assert!(should_run_retention_prune(None, now, 3_600));
        assert!(!should_run_retention_prune(Some(last), now, 3_600));
        assert!(should_run_retention_prune(Some(last), now, 900));
    }
}
