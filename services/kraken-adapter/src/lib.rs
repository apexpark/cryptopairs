use async_trait::async_trait;
use chrono::{DateTime, TimeZone, Utc};
use common_types::{Candle, DataQueryRequest, Timeframe};
use serde::Deserialize;
use std::{collections::HashMap, path::Path};
use thiserror::Error;
use tracing::warn;

#[derive(Debug, Error)]
pub enum AdapterError {
    #[error("http request failed: {0}")]
    Request(String),
    #[error("unexpected http status {status}: {body}")]
    HttpStatus { status: u16, body: String },
    #[error("response decode failed: {0}")]
    Decode(String),
    #[error("invalid candle timestamp from kraken: {0}")]
    InvalidTimestamp(i64),
    #[error("invalid server time from kraken tickers: {0}")]
    InvalidServerTime(String),
    #[error("history bounds config error: {0}")]
    HistoryBounds(String),
    #[error("missing history bounds for symbol={symbol} timeframe={timeframe}")]
    MissingHistoryBounds { symbol: String, timeframe: String },
    #[error("ticker not found for instrument={instrument}")]
    TickerNotFound { instrument: String },
    #[error("ticker missing required field for instrument={instrument}: {field}")]
    MissingTickerField {
        instrument: String,
        field: &'static str,
    },
    #[error(
        "request outside history bounds for symbol={symbol} timeframe={timeframe} requested=[{requested_start},{requested_end}] earliest={earliest_start}"
    )]
    RequestOutsideHistoryBounds {
        symbol: String,
        timeframe: String,
        requested_start: i64,
        requested_end: i64,
        earliest_start: i64,
    },
}

#[async_trait]
pub trait MarketDataAdapter: Send + Sync {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>, AdapterError>;
    async fn fetch_market_metrics(&self, instrument: &str) -> Result<MarketMetrics, AdapterError>;
}

#[derive(Debug, Clone)]
pub struct MarketMetrics {
    pub instrument: String,
    pub server_time: DateTime<Utc>,
    pub mark: f64,
    pub index: f64,
    pub change_24h_pct: f64,
    pub funding_rate: f64,
    pub open_interest: f64,
}

#[derive(Debug, Clone)]
struct HistoryBound {
    earliest_start_sec: i64,
    max_candles_per_request: usize,
}

#[derive(Debug, Clone)]
pub struct KrakenHistoryBounds {
    by_symbol: HashMap<String, HashMap<String, HistoryBound>>,
}

impl KrakenHistoryBounds {
    pub fn from_file(path: impl AsRef<Path>) -> Result<Self, AdapterError> {
        let path_ref = path.as_ref();
        let body = std::fs::read_to_string(path_ref).map_err(|error| {
            AdapterError::HistoryBounds(format!("failed reading {}: {}", path_ref.display(), error))
        })?;
        Self::from_json_str(&body)
    }

    pub fn from_json_str(value: &str) -> Result<Self, AdapterError> {
        let parsed: KrakenHistoryBoundsFile = serde_json::from_str(value)
            .map_err(|error| AdapterError::HistoryBounds(error.to_string()))?;
        let mut by_symbol: HashMap<String, HashMap<String, HistoryBound>> = HashMap::new();

        for symbol_entry in parsed.symbols {
            let symbol_key = symbol_entry.symbol.to_uppercase();
            let mut timeframe_map: HashMap<String, HistoryBound> = HashMap::new();
            for (timeframe, bounds) in symbol_entry.timeframes {
                if Timeframe::parse(&timeframe).is_none() {
                    return Err(AdapterError::HistoryBounds(format!(
                        "unsupported timeframe '{}' in bounds file",
                        timeframe
                    )));
                }
                if bounds.max_candles_per_request == 0 {
                    return Err(AdapterError::HistoryBounds(format!(
                        "max_candles_per_request must be > 0 for symbol={} timeframe={}",
                        symbol_key, timeframe
                    )));
                }
                timeframe_map.insert(
                    timeframe,
                    HistoryBound {
                        earliest_start_sec: bounds.earliest_start_sec,
                        max_candles_per_request: bounds.max_candles_per_request,
                    },
                );
            }
            by_symbol.insert(symbol_key, timeframe_map);
        }

        Ok(Self { by_symbol })
    }

    fn lookup(&self, symbol: &str, timeframe: Timeframe) -> Option<HistoryBound> {
        let symbol_key = symbol.to_uppercase();
        self.by_symbol
            .get(&symbol_key)
            .and_then(|timeframes| timeframes.get(timeframe.as_str()))
            .cloned()
    }
}

impl Default for KrakenHistoryBounds {
    fn default() -> Self {
        let mut by_symbol: HashMap<String, HashMap<String, HistoryBound>> = HashMap::new();
        for symbol in ["PI_XBTUSD", "PI_ETHUSD"] {
            let mut timeframes = HashMap::new();
            timeframes.insert(
                "1m".to_string(),
                HistoryBound {
                    earliest_start_sec: 1_582_719_360,
                    max_candles_per_request: 2_000,
                },
            );
            timeframes.insert(
                "15m".to_string(),
                HistoryBound {
                    earliest_start_sec: 1_582_719_300,
                    max_candles_per_request: 2_000,
                },
            );
            timeframes.insert(
                "1h".to_string(),
                HistoryBound {
                    earliest_start_sec: 1_582_718_400,
                    max_candles_per_request: 2_000,
                },
            );
            by_symbol.insert(symbol.to_string(), timeframes);
        }
        Self { by_symbol }
    }
}

#[derive(Debug, Clone)]
pub struct KrakenFuturesRestClient {
    pub base_url: String,
    client: reqwest::Client,
    history_bounds: KrakenHistoryBounds,
}

impl KrakenFuturesRestClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            client: reqwest::Client::new(),
            history_bounds: KrakenHistoryBounds::default(),
        }
    }

    pub fn with_history_bounds(mut self, history_bounds: KrakenHistoryBounds) -> Self {
        self.history_bounds = history_bounds;
        self
    }

    fn bounded_request_range(
        &self,
        request: &DataQueryRequest,
    ) -> Result<(i64, i64), AdapterError> {
        let timeframe = request.timeframe.as_str().to_string();
        let bounds = self
            .history_bounds
            .lookup(&request.instrument, request.timeframe)
            .ok_or_else(|| AdapterError::MissingHistoryBounds {
                symbol: request.instrument.clone(),
                timeframe: timeframe.clone(),
            })?;

        let requested_start = request.start_ts.timestamp();
        let requested_end = request.end_ts.timestamp();
        let bounded_start = requested_start.max(bounds.earliest_start_sec);

        if bounded_start > requested_end {
            return Err(AdapterError::RequestOutsideHistoryBounds {
                symbol: request.instrument.clone(),
                timeframe,
                requested_start,
                requested_end,
                earliest_start: bounds.earliest_start_sec,
            });
        }

        if bounded_start != requested_start {
            warn!(
                symbol = %request.instrument,
                timeframe = %request.timeframe.as_str(),
                requested_start,
                bounded_start,
                earliest_start = bounds.earliest_start_sec,
                "kraken history request start clamped to configured earliest bound"
            );
        }

        let max_window_seconds = request.timeframe.step_seconds()
            * (bounds.max_candles_per_request.saturating_sub(1) as i64);
        let mut bounded_end = requested_end;
        if max_window_seconds > 0 && (bounded_end - bounded_start) > max_window_seconds {
            bounded_end = bounded_start + max_window_seconds;
            warn!(
                symbol = %request.instrument,
                timeframe = %request.timeframe.as_str(),
                requested_end,
                bounded_end,
                max_candles = bounds.max_candles_per_request,
                "kraken history request end clamped to max page depth"
            );
        }

        Ok((bounded_start, bounded_end))
    }
}

impl Default for KrakenFuturesRestClient {
    fn default() -> Self {
        Self::new("https://futures.kraken.com")
    }
}

#[async_trait]
impl MarketDataAdapter for KrakenFuturesRestClient {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>, AdapterError> {
        let resolution = match request.timeframe {
            Timeframe::OneMinute => "1m",
            Timeframe::FifteenMinutes => "15m",
            Timeframe::OneHour => "1h",
        };
        let (from, to) = self.bounded_request_range(request)?;
        let url = format!(
            "{}/api/charts/v1/trade/{}/{}?from={from}&to={to}",
            self.base_url, request.instrument, resolution
        );

        let response = self
            .client
            .get(url)
            .send()
            .await
            .map_err(|err| AdapterError::Request(err.to_string()))?;
        let status = response.status().as_u16();
        let body = response
            .text()
            .await
            .map_err(|err| AdapterError::Decode(err.to_string()))?;
        if status != 200 {
            return Err(AdapterError::HttpStatus { status, body });
        }

        let payload: KrakenChartsResponse =
            serde_json::from_str(&body).map_err(|err| AdapterError::Decode(err.to_string()))?;
        payload
            .candles
            .into_iter()
            .map(|raw| {
                let ts = Utc
                    .timestamp_millis_opt(raw.time)
                    .single()
                    .ok_or(AdapterError::InvalidTimestamp(raw.time))?;
                Ok(Candle {
                    ts,
                    open: parse_number(&raw.open)?,
                    high: parse_number(&raw.high)?,
                    low: parse_number(&raw.low)?,
                    close: parse_number(&raw.close)?,
                    volume: parse_number(&raw.volume)?,
                })
            })
            .collect()
    }

    async fn fetch_market_metrics(&self, instrument: &str) -> Result<MarketMetrics, AdapterError> {
        let url = format!("{}/derivatives/api/v3/tickers", self.base_url);
        let response = self
            .client
            .get(url)
            .send()
            .await
            .map_err(|err| AdapterError::Request(err.to_string()))?;
        let status = response.status().as_u16();
        let body = response
            .text()
            .await
            .map_err(|err| AdapterError::Decode(err.to_string()))?;
        if status != 200 {
            return Err(AdapterError::HttpStatus { status, body });
        }

        let payload: KrakenTickersResponse =
            serde_json::from_str(&body).map_err(|err| AdapterError::Decode(err.to_string()))?;
        let server_time = payload
            .server_time
            .parse::<DateTime<Utc>>()
            .map_err(|_| AdapterError::InvalidServerTime(payload.server_time.clone()))?;

        let ticker = payload
            .tickers
            .into_iter()
            .find(|item| item.symbol.eq_ignore_ascii_case(instrument))
            .ok_or_else(|| AdapterError::TickerNotFound {
                instrument: instrument.to_string(),
            })?;

        let mark = ticker
            .mark_price
            .ok_or_else(|| AdapterError::MissingTickerField {
                instrument: ticker.symbol.clone(),
                field: "markPrice",
            })?;
        let index = ticker
            .index_price
            .ok_or_else(|| AdapterError::MissingTickerField {
                instrument: ticker.symbol.clone(),
                field: "indexPrice",
            })?;
        let change_24h_pct = ticker
            .change_24h
            .ok_or_else(|| AdapterError::MissingTickerField {
                instrument: ticker.symbol.clone(),
                field: "change24h",
            })?;
        let funding_rate = ticker
            .funding_rate
            .ok_or_else(|| AdapterError::MissingTickerField {
                instrument: ticker.symbol.clone(),
                field: "fundingRate",
            })?;
        let open_interest =
            ticker
                .open_interest
                .ok_or_else(|| AdapterError::MissingTickerField {
                    instrument: ticker.symbol.clone(),
                    field: "openInterest",
                })?;

        Ok(MarketMetrics {
            instrument: ticker.symbol,
            server_time,
            mark,
            index,
            change_24h_pct,
            funding_rate,
            open_interest,
        })
    }
}

#[derive(Debug, Deserialize)]
struct KrakenChartsResponse {
    candles: Vec<KrakenRawCandle>,
}

#[derive(Debug, Deserialize)]
struct KrakenTickersResponse {
    #[serde(rename = "serverTime")]
    server_time: String,
    tickers: Vec<KrakenTicker>,
}

#[derive(Debug, Deserialize)]
struct KrakenTicker {
    symbol: String,
    #[serde(rename = "markPrice")]
    mark_price: Option<f64>,
    #[serde(rename = "indexPrice")]
    index_price: Option<f64>,
    #[serde(rename = "change24h")]
    change_24h: Option<f64>,
    #[serde(rename = "fundingRate")]
    funding_rate: Option<f64>,
    #[serde(rename = "openInterest")]
    open_interest: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct KrakenRawCandle {
    time: i64,
    open: String,
    high: String,
    low: String,
    close: String,
    volume: String,
}

#[derive(Debug, Deserialize)]
struct KrakenHistoryBoundsFile {
    symbols: Vec<KrakenSymbolBoundsFile>,
}

#[derive(Debug, Deserialize)]
struct KrakenSymbolBoundsFile {
    symbol: String,
    timeframes: HashMap<String, KrakenTimeframeBoundsFile>,
}

#[derive(Debug, Deserialize)]
struct KrakenTimeframeBoundsFile {
    earliest_start_sec: i64,
    max_candles_per_request: usize,
}

fn parse_number(value: &str) -> Result<f64, AdapterError> {
    value
        .parse::<f64>()
        .map_err(|err| AdapterError::Decode(err.to_string()))
}

#[cfg(test)]
mod tests {
    use super::{
        parse_number, KrakenFuturesRestClient, KrakenHistoryBounds, KrakenTicker,
        KrakenTickersResponse,
    };
    use chrono::{TimeZone, Utc};
    use common_types::{DataQueryRequest, Timeframe};

    fn request(start: i64, end: i64) -> DataQueryRequest {
        DataQueryRequest {
            instrument: "PI_XBTUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            start_ts: Utc
                .timestamp_opt(start, 0)
                .single()
                .expect("valid timestamp"),
            end_ts: Utc.timestamp_opt(end, 0).single().expect("valid timestamp"),
        }
    }

    #[test]
    fn default_base_url_is_https() {
        let client = KrakenFuturesRestClient::default();
        assert!(client.base_url.starts_with("https://"));
    }

    #[test]
    fn parse_number_handles_numeric_strings() {
        assert_eq!(parse_number("123.5").expect("valid numeric string"), 123.5);
    }

    #[test]
    fn bounds_from_json_parses_supported_timeframes() {
        let json = r#"{
          "symbols": [
            {
              "symbol": "PI_XBTUSD",
              "timeframes": {
                "1m": { "earliest_start_sec": 100, "max_candles_per_request": 2000 },
                "15m": { "earliest_start_sec": 200, "max_candles_per_request": 1500 },
                "1h": { "earliest_start_sec": 300, "max_candles_per_request": 1200 }
              }
            }
          ]
        }"#;
        let bounds = KrakenHistoryBounds::from_json_str(json).expect("bounds parse should pass");
        assert!(bounds.lookup("PI_XBTUSD", Timeframe::OneMinute).is_some());
        assert!(bounds
            .lookup("PI_XBTUSD", Timeframe::FifteenMinutes)
            .is_some());
        assert!(bounds.lookup("PI_XBTUSD", Timeframe::OneHour).is_some());
    }

    #[test]
    fn bounded_request_range_clamps_start_and_max_window() {
        let client = KrakenFuturesRestClient::new("https://futures.kraken.com");
        let req = request(1_582_000_000, 1_700_000_000);
        let (start, end) = client
            .bounded_request_range(&req)
            .expect("range should be bounded");
        assert_eq!(start, 1_582_719_360);
        assert_eq!(end, 1_582_719_360 + (60 * 1_999));
    }

    #[test]
    fn bounded_request_range_rejects_pre_history_window() {
        let client = KrakenFuturesRestClient::new("https://futures.kraken.com");
        let req = request(1_580_000_000, 1_580_000_100);
        let error = client
            .bounded_request_range(&req)
            .expect_err("pre-history request should fail");
        assert!(error
            .to_string()
            .contains("request outside history bounds for symbol=PI_XBTUSD"));
    }

    #[test]
    fn tickers_payload_parses_required_fields() {
        let raw = r#"{
          "result": "success",
          "serverTime": "2026-02-20T05:24:16.241Z",
          "tickers": [
            {
              "symbol": "PI_XBTUSD",
              "markPrice": 67324.30,
              "indexPrice": 67317.80,
              "change24h": 0.84,
              "fundingRate": 0.0000021,
              "openInterest": 5278812.0
            }
          ]
        }"#;
        let payload: KrakenTickersResponse =
            serde_json::from_str(raw).expect("tickers response should parse");
        assert_eq!(payload.server_time, "2026-02-20T05:24:16.241Z");
        let ticker: &KrakenTicker = payload
            .tickers
            .iter()
            .find(|value| value.symbol == "PI_XBTUSD")
            .expect("PI_XBTUSD ticker should be present");
        assert_eq!(ticker.mark_price, Some(67324.30));
        assert_eq!(ticker.index_price, Some(67317.80));
        assert_eq!(ticker.change_24h, Some(0.84));
        assert_eq!(ticker.funding_rate, Some(0.0000021));
        assert_eq!(ticker.open_interest, Some(5_278_812.0));
    }
}
