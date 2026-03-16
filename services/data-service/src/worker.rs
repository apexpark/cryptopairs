use crate::{config::TimeframeDays, normalize_request_window, AppState};
use chrono::{DateTime, Duration, Utc};
use common_types::{DataQueryRequest, Timeframe};
use std::collections::HashMap;
use tokio::time::{sleep, Duration as TokioDuration};
use tracing::{info, warn};

const KRAKEN_MAX_CANDLES_PER_REQUEST: i64 = 2000;
const BACKFILL_FULL_SWEEP_BOOTSTRAP_SECONDS: u64 = 300;

#[derive(Debug, Clone, Hash, PartialEq, Eq)]
struct BackfillKey {
    instrument: String,
    timeframe: Timeframe,
}

#[derive(Debug, Clone, Copy)]
enum BackfillMode {
    Incremental,
    FullSweep,
    Bootstrap,
}

impl BackfillMode {
    fn as_str(self) -> &'static str {
        match self {
            Self::Incremental => "incremental",
            Self::FullSweep => "full_sweep",
            Self::Bootstrap => "bootstrap",
        }
    }
}

#[derive(Debug, Clone, Default)]
struct BackfillWindowResult {
    total_written: usize,
    latest_ts: Option<DateTime<Utc>>,
}

pub fn spawn_backfill_worker(
    state: AppState,
    symbols: Vec<String>,
    interval_seconds: u64,
    overlap_steps: i64,
    full_sweep_interval_seconds: u64,
    backfill_window_days: TimeframeDays,
    candles_retention_days: TimeframeDays,
    prune_interval_seconds: u64,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut last_prune_at: Option<DateTime<Utc>> = None;
        let mut last_full_sweep_at: Option<DateTime<Utc>> = None;
        let mut latest_cursors: HashMap<BackfillKey, DateTime<Utc>> = HashMap::new();
        loop {
            let cycle_started_at = Utc::now();
            let run_full_sweep = should_run_full_sweep(
                last_full_sweep_at,
                cycle_started_at,
                full_sweep_interval_seconds,
            );
            let mut cycle_written = 0usize;
            for symbol in &symbols {
                for timeframe in [
                    Timeframe::OneMinute,
                    Timeframe::FifteenMinutes,
                    Timeframe::OneHour,
                ] {
                    let now = Utc::now();
                    let window_start = backfill_window_start(now, timeframe, backfill_window_days);
                    let key = BackfillKey {
                        instrument: symbol.clone(),
                        timeframe,
                    };
                    let (start_ts, mode) = if run_full_sweep {
                        (window_start, BackfillMode::FullSweep)
                    } else {
                        let latest_ts = match latest_cursors.get(&key).copied() {
                            Some(ts) => Some(ts),
                            None => match state
                                .repository
                                .fetch_latest_candle_ts(symbol, timeframe)
                                .await
                            {
                                Ok(ts) => {
                                    if let Some(latest) = ts {
                                        latest_cursors.insert(key.clone(), latest);
                                    }
                                    ts
                                }
                                Err(error) => {
                                    warn!(
                                        instrument = %symbol,
                                        timeframe = %timeframe.as_str(),
                                        error = %error,
                                        "backfill worker failed to load latest candle cursor"
                                    );
                                    None
                                }
                            },
                        };

                        match latest_ts {
                            Some(last_ts) => (
                                incremental_window_start(
                                    last_ts,
                                    timeframe,
                                    overlap_steps,
                                    window_start,
                                    now,
                                ),
                                BackfillMode::Incremental,
                            ),
                            None => (window_start, BackfillMode::Bootstrap),
                        }
                    };
                    let request = DataQueryRequest {
                        instrument: symbol.clone(),
                        timeframe,
                        start_ts,
                        end_ts: now,
                    };

                    match backfill_window(&state, &request).await {
                        Ok(result) => {
                            cycle_written = cycle_written.saturating_add(result.total_written);
                            if let Some(latest_ts) = result.latest_ts {
                                latest_cursors.insert(key, latest_ts);
                            }
                            if result.total_written > 0 {
                                info!(
                                    instrument = %symbol,
                                    timeframe = %timeframe.as_str(),
                                    mode = %mode.as_str(),
                                    start_ts = %request.start_ts,
                                    end_ts = %request.end_ts,
                                    total_written = result.total_written,
                                    "backfill worker persisted candles"
                                );
                            }
                        }
                        Err(error) => {
                            warn!(
                                instrument = %symbol,
                                timeframe = ?timeframe,
                                mode = %mode.as_str(),
                                start_ts = %request.start_ts,
                                end_ts = %request.end_ts,
                                error = %error,
                                "backfill worker failed for window"
                            );
                        }
                    }
                }
            }
            if run_full_sweep {
                last_full_sweep_at = Some(cycle_started_at);
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

            let cycle_elapsed_seconds = now.signed_duration_since(cycle_started_at).num_seconds();
            info!(
                run_full_sweep,
                cycle_elapsed_seconds,
                cycle_written,
                tracked_cursors = latest_cursors.len(),
                "backfill worker cycle completed"
            );

            sleep(TokioDuration::from_secs(interval_seconds)).await;
        }
    })
}

async fn backfill_window(
    state: &AppState,
    request: &DataQueryRequest,
) -> anyhow::Result<BackfillWindowResult> {
    let normalized_request = normalize_request_window(request);
    let local = state.repository.fetch_candles(&normalized_request).await?;
    let report = crate::gap_detector::build_integrity_report(
        &normalized_request,
        &local,
        state.integrity_threshold_pct,
    );
    if report.missing_ranges.is_empty() {
        return Ok(BackfillWindowResult {
            total_written: 0,
            latest_ts: local.last().map(|candle| candle.ts),
        });
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
    Ok(BackfillWindowResult {
        total_written,
        latest_ts: refreshed.last().map(|candle| candle.ts),
    })
}

fn backfill_window_start(
    now: DateTime<Utc>,
    timeframe: Timeframe,
    backfill_window_days: TimeframeDays,
) -> DateTime<Utc> {
    now - Duration::days(backfill_window_days.days_for(timeframe))
}

fn incremental_window_start(
    last_seen_ts: DateTime<Utc>,
    timeframe: Timeframe,
    overlap_steps: i64,
    lower_bound: DateTime<Utc>,
    upper_bound: DateTime<Utc>,
) -> DateTime<Utc> {
    let step_seconds = timeframe.step_seconds().max(1);
    let overlap = Duration::seconds(step_seconds.saturating_mul(overlap_steps.max(1)));
    let with_overlap = last_seen_ts - overlap;
    let clamped = std::cmp::max(with_overlap, lower_bound);
    std::cmp::min(clamped, upper_bound)
}

fn should_run_full_sweep(
    last_full_sweep_at: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
    full_sweep_interval_seconds: u64,
) -> bool {
    match last_full_sweep_at {
        None => true,
        Some(last) => {
            now.signed_duration_since(last).num_seconds()
                >= full_sweep_interval_seconds.max(BACKFILL_FULL_SWEEP_BOOTSTRAP_SECONDS) as i64
        }
    }
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
    use super::{
        backfill_window_start, incremental_window_start, should_run_full_sweep,
        should_run_retention_prune, split_range_into_segments,
    };
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

    #[test]
    fn incremental_window_start_applies_overlap_and_bounds() {
        let lower = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        let last = lower + chrono::Duration::minutes(10);
        let upper = lower + chrono::Duration::minutes(12);

        let start = incremental_window_start(last, Timeframe::OneMinute, 2, lower, upper);
        assert_eq!(start, lower + chrono::Duration::minutes(8));

        let clamped_lower = incremental_window_start(
            lower + chrono::Duration::minutes(1),
            Timeframe::OneMinute,
            4,
            lower,
            upper,
        );
        assert_eq!(clamped_lower, lower);

        let clamped_upper = incremental_window_start(
            upper + chrono::Duration::minutes(5),
            Timeframe::OneMinute,
            2,
            lower,
            upper,
        );
        assert_eq!(clamped_upper, upper);
    }

    #[test]
    fn full_sweep_interval_respected() {
        let now = Utc
            .timestamp_opt(1_700_000_000, 0)
            .single()
            .expect("valid timestamp");
        assert!(should_run_full_sweep(None, now, 10_800));
        assert!(!should_run_full_sweep(
            Some(now - chrono::Duration::seconds(120)),
            now,
            10_800
        ));
        assert!(should_run_full_sweep(
            Some(now - chrono::Duration::seconds(10_900)),
            now,
            10_800
        ));
    }
}
