use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct InstrumentTradingConstraints {
    pub min_lot: f64,
    pub tick_size: f64,
}

pub fn normalize_kraken_perp_symbol(raw: &str) -> String {
    let upper = raw.trim().to_ascii_uppercase();
    let without_suffix = upper.trim_end_matches('*');
    if let Some(symbol) = without_suffix.strip_prefix("PI_") {
        format!("PF_{symbol}")
    } else {
        without_suffix.to_string()
    }
}

pub fn kraken_perp_constraints(raw_instrument: &str) -> Option<InstrumentTradingConstraints> {
    match normalize_kraken_perp_symbol(raw_instrument).as_str() {
        "PF_ADAUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1.0,
            tick_size: 0.00001,
        }),
        "PF_ARBUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1.0,
            tick_size: 0.0001,
        }),
        "PF_AVAXUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.01,
            tick_size: 0.001,
        }),
        "PF_BNBUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.01,
            tick_size: 0.01,
        }),
        "PF_DOGEUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1.0,
            tick_size: 0.000001,
        }),
        "PF_ETHUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.001,
            tick_size: 0.1,
        }),
        "PF_HYPEUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.1,
            tick_size: 0.001,
        }),
        "PF_LINKUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.1,
            tick_size: 0.001,
        }),
        "PF_PEPEUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1000.0,
            tick_size: 0.0000000001,
        }),
        "PF_SOLUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.01,
            tick_size: 0.01,
        }),
        "PF_SUIUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1.0,
            tick_size: 0.0001,
        }),
        "PF_TAOUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.01,
            tick_size: 0.01,
        }),
        "PF_XBTUSD" => Some(InstrumentTradingConstraints {
            min_lot: 0.0001,
            tick_size: 1.0,
        }),
        "PF_XRPUSD" => Some(InstrumentTradingConstraints {
            min_lot: 1.0,
            tick_size: 0.00001,
        }),
        _ => None,
    }
}

pub fn quantize_to_step(value: f64, step: f64) -> Option<f64> {
    if !value.is_finite() || !step.is_finite() || value <= 0.0 || step <= 0.0 {
        return None;
    }
    let units = (value / step).round();
    if !units.is_finite() || units <= 0.0 {
        return None;
    }
    Some(units * step)
}

pub fn is_aligned_to_step(value: f64, step: f64, unit_tolerance: f64) -> bool {
    if !value.is_finite() || !step.is_finite() || value <= 0.0 || step <= 0.0 {
        return false;
    }
    let units = value / step;
    if !units.is_finite() {
        return false;
    }
    let tolerance = unit_tolerance.max(1e-9);
    (units - units.round()).abs() <= tolerance
}

pub fn quantize_price_to_tick(price: f64, tick_size: f64) -> Option<f64> {
    quantize_to_step(price, tick_size).filter(|value| *value > 0.0)
}

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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
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
    use super::{
        is_aligned_to_step, kraken_perp_constraints, normalize_kraken_perp_symbol,
        quantize_price_to_tick, quantize_to_step, DataIntegrityReport, IntegrityStatus, Timeframe,
    };
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

    #[test]
    fn kraken_symbol_normalization_handles_aliases_and_suffixes() {
        assert_eq!(normalize_kraken_perp_symbol("PF_XBTUSD"), "PF_XBTUSD");
        assert_eq!(normalize_kraken_perp_symbol("PI_XBTUSD"), "PF_XBTUSD");
        assert_eq!(normalize_kraken_perp_symbol("PF_XBTUSD*"), "PF_XBTUSD");
    }

    #[test]
    fn kraken_constraints_lookup_resolves_known_symbols() {
        let pepe = kraken_perp_constraints("PF_PEPEUSD").expect("pepe constraints");
        assert!((pepe.min_lot - 1000.0).abs() < 1e-9);
        assert!((pepe.tick_size - 0.0000000001).abs() < 1e-15);

        let xbt = kraken_perp_constraints("PI_XBTUSD").expect("xbt constraints");
        assert!((xbt.min_lot - 0.0001).abs() < 1e-9);
        assert!((xbt.tick_size - 1.0).abs() < 1e-9);

        assert!(kraken_perp_constraints("PF_UNKNOWN").is_none());
    }

    #[test]
    fn step_helpers_align_and_quantize_values() {
        assert!(is_aligned_to_step(1.0, 0.01, 1e-6));
        assert!(!is_aligned_to_step(0.015, 0.01, 1e-6));
        assert_eq!(quantize_to_step(0.015, 0.01), Some(0.02));
        assert_eq!(quantize_price_to_tick(2021.749, 0.1), Some(2021.7));
    }
}
