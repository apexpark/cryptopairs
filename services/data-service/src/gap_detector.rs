use chrono::{TimeZone, Utc};
use common_types::{Candle, DataIntegrityReport, DataQueryRequest, IntegrityStatus, MissingRange};
use std::collections::HashSet;

pub fn build_integrity_report(
    request: &DataQueryRequest,
    candles: &[Candle],
    threshold_pct: f64,
) -> DataIntegrityReport {
    if request.end_ts < request.start_ts {
        return DataIntegrityReport {
            status: IntegrityStatus::Failed,
            coverage_pct: 0.0,
            missing_ranges: vec![],
            last_verified_at: Utc::now(),
            warnings: vec!["request end_ts is earlier than start_ts".to_string()],
        };
    }

    let step = request.timeframe.step_seconds();
    let expected_timestamps = enumerate_expected_timestamps(
        request.start_ts.timestamp(),
        request.end_ts.timestamp(),
        step,
    );

    if expected_timestamps.is_empty() {
        return DataIntegrityReport {
            status: IntegrityStatus::Failed,
            coverage_pct: 0.0,
            missing_ranges: vec![],
            last_verified_at: Utc::now(),
            warnings: vec!["no expected timestamps for requested range".to_string()],
        };
    }

    let observed: HashSet<i64> = candles
        .iter()
        .map(|candle| candle.ts.timestamp())
        .filter(|ts| *ts >= request.start_ts.timestamp() && *ts <= request.end_ts.timestamp())
        .collect();

    let present = expected_timestamps
        .iter()
        .filter(|ts| observed.contains(ts))
        .count();
    let expected = expected_timestamps.len();
    let coverage_pct = (present as f64 / expected as f64) * 100.0;
    let missing_ranges = build_missing_ranges(&expected_timestamps, &observed, step);

    let status = if missing_ranges.is_empty() {
        IntegrityStatus::Complete
    } else if coverage_pct >= threshold_pct {
        IntegrityStatus::PartialBackfilled
    } else {
        IntegrityStatus::Incomplete
    };

    let warnings = if missing_ranges.is_empty() {
        vec![]
    } else {
        vec![format!(
            "detected {} missing interval(s) in requested range",
            missing_ranges.len()
        )]
    };

    DataIntegrityReport {
        status,
        coverage_pct,
        missing_ranges,
        last_verified_at: Utc::now(),
        warnings,
    }
}

fn enumerate_expected_timestamps(start: i64, end: i64, step: i64) -> Vec<i64> {
    let mut result = Vec::new();
    let mut cursor = start;
    while cursor <= end {
        result.push(cursor);
        cursor += step;
    }
    result
}

fn build_missing_ranges(
    expected_timestamps: &[i64],
    observed: &HashSet<i64>,
    step: i64,
) -> Vec<MissingRange> {
    let mut ranges = Vec::new();
    let mut current_start: Option<i64> = None;
    let mut current_end: Option<i64> = None;

    for ts in expected_timestamps {
        if observed.contains(ts) {
            if let (Some(start), Some(end)) = (current_start.take(), current_end.take()) {
                ranges.push(MissingRange {
                    start_ts: Utc
                        .timestamp_opt(start, 0)
                        .single()
                        .expect("valid timestamp"),
                    end_ts: Utc.timestamp_opt(end, 0).single().expect("valid timestamp"),
                    reason: "missing_candle".to_string(),
                });
            }
            continue;
        }

        if current_start.is_none() {
            current_start = Some(*ts);
            current_end = Some(*ts);
        } else {
            current_end = Some(*ts);
        }
    }

    if let (Some(start), Some(end)) = (current_start, current_end) {
        ranges.push(MissingRange {
            start_ts: Utc
                .timestamp_opt(start, 0)
                .single()
                .expect("valid timestamp"),
            end_ts: Utc.timestamp_opt(end, 0).single().expect("valid timestamp"),
            reason: "missing_candle".to_string(),
        });
    }

    let _ = step;
    ranges
}

#[cfg(test)]
mod tests {
    use super::build_integrity_report;
    use chrono::{TimeZone, Utc};
    use common_types::{Candle, DataQueryRequest, IntegrityStatus, Timeframe};

    fn request() -> DataQueryRequest {
        DataQueryRequest {
            instrument: "PI_XBTUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            start_ts: Utc
                .timestamp_opt(1_700_000_000, 0)
                .single()
                .expect("valid timestamp"),
            end_ts: Utc
                .timestamp_opt(1_700_000_120, 0)
                .single()
                .expect("valid timestamp"),
        }
    }

    #[test]
    fn complete_window_is_marked_complete() {
        let req = request();
        let candles = vec![
            Candle {
                ts: req.start_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
            Candle {
                ts: Utc
                    .timestamp_opt(1_700_000_060, 0)
                    .single()
                    .expect("valid timestamp"),
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
            Candle {
                ts: req.end_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
        ];
        let report = build_integrity_report(&req, &candles, 99.5);
        assert_eq!(report.status, IntegrityStatus::Complete);
        assert!(report.missing_ranges.is_empty());
        assert_eq!(report.coverage_pct, 100.0);
    }

    #[test]
    fn missing_candle_below_threshold_is_incomplete() {
        let req = request();
        let candles = vec![
            Candle {
                ts: req.start_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
            Candle {
                ts: req.end_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
        ];
        let report = build_integrity_report(&req, &candles, 99.5);
        assert_eq!(report.status, IntegrityStatus::Incomplete);
        assert_eq!(report.missing_ranges.len(), 1);
        assert!(report.coverage_pct < 99.5);
    }

    #[test]
    fn missing_candle_above_relaxed_threshold_is_partial_backfilled() {
        let req = request();
        let candles = vec![
            Candle {
                ts: req.start_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
            Candle {
                ts: req.end_ts,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
        ];
        let report = build_integrity_report(&req, &candles, 60.0);
        assert_eq!(report.status, IntegrityStatus::PartialBackfilled);
        assert!(report.coverage_pct >= 60.0);
    }
}
