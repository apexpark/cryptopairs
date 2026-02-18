use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IntegrityStatus {
    Complete,
    PartialBackfilled,
    Incomplete,
    Stale,
    Failed,
}

impl IntegrityStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Complete => "COMPLETE",
            Self::PartialBackfilled => "PARTIAL_BACKFILLED",
            Self::Incomplete => "INCOMPLETE",
            Self::Stale => "STALE",
            Self::Failed => "FAILED",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum Timeframe {
    #[serde(rename = "1m")]
    OneMinute,
    #[serde(rename = "15m")]
    FifteenMinutes,
    #[serde(rename = "1h")]
    OneHour,
}

impl Timeframe {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::OneMinute => "1m",
            Self::FifteenMinutes => "15m",
            Self::OneHour => "1h",
        }
    }

    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "1m" => Some(Self::OneMinute),
            "15m" => Some(Self::FifteenMinutes),
            "1h" => Some(Self::OneHour),
            _ => None,
        }
    }

    pub fn step_seconds(self) -> i64 {
        match self {
            Self::OneMinute => 60,
            Self::FifteenMinutes => 15 * 60,
            Self::OneHour => 60 * 60,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Candle {
    pub ts: DateTime<Utc>,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MissingRange {
    pub start_ts: DateTime<Utc>,
    pub end_ts: DateTime<Utc>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DataIntegrityReport {
    pub status: IntegrityStatus,
    pub coverage_pct: f64,
    pub missing_ranges: Vec<MissingRange>,
    pub last_verified_at: DateTime<Utc>,
    pub warnings: Vec<String>,
}

impl DataIntegrityReport {
    pub fn is_live_eligible(&self, min_coverage_pct: f64) -> bool {
        self.coverage_pct >= min_coverage_pct
            && matches!(
                self.status,
                IntegrityStatus::Complete | IntegrityStatus::PartialBackfilled
            )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DataQueryRequest {
    pub instrument: String,
    pub timeframe: Timeframe,
    pub start_ts: DateTime<Utc>,
    pub end_ts: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DataQueryResponse {
    pub instrument: String,
    pub timeframe: Timeframe,
    pub start_ts: DateTime<Utc>,
    pub end_ts: DateTime<Utc>,
    pub candles: Vec<Candle>,
    pub integrity: DataIntegrityReport,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TradeTick {
    pub instrument: String,
    pub seq: i64,
    pub ts: DateTime<Utc>,
    pub side: String,
    pub price: f64,
    pub qty: f64,
    pub uid: String,
}

#[cfg(test)]
mod tests {
    use super::{DataIntegrityReport, IntegrityStatus, Timeframe};
    use chrono::Utc;

    #[test]
    fn timeframe_step_seconds_are_correct() {
        assert_eq!(Timeframe::OneMinute.step_seconds(), 60);
        assert_eq!(Timeframe::FifteenMinutes.step_seconds(), 900);
        assert_eq!(Timeframe::OneHour.step_seconds(), 3600);
    }

    #[test]
    fn live_eligibility_respects_threshold_and_status() {
        let report = DataIntegrityReport {
            status: IntegrityStatus::PartialBackfilled,
            coverage_pct: 99.5,
            missing_ranges: vec![],
            last_verified_at: Utc::now(),
            warnings: vec![],
        };
        assert!(report.is_live_eligible(99.5));
        assert!(!report.is_live_eligible(99.9));
    }
}
