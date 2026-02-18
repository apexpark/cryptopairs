use async_trait::async_trait;
use chrono::{TimeZone, Utc};
use common_types::{Candle, DataQueryRequest};
use serde::Deserialize;
use thiserror::Error;

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
}

#[async_trait]
pub trait MarketDataAdapter: Send + Sync {
    async fn fetch_candles(&self, request: &DataQueryRequest) -> Result<Vec<Candle>, AdapterError>;
}

#[derive(Debug, Clone)]
pub struct KrakenFuturesRestClient {
    pub base_url: String,
    client: reqwest::Client,
}

impl KrakenFuturesRestClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            client: reqwest::Client::new(),
        }
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
            common_types::Timeframe::OneMinute => "1m",
            common_types::Timeframe::FifteenMinutes => "15m",
            common_types::Timeframe::OneHour => "1h",
        };
        let from = request.start_ts.timestamp();
        let to = request.end_ts.timestamp();
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
}

#[derive(Debug, Deserialize)]
struct KrakenChartsResponse {
    candles: Vec<KrakenRawCandle>,
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

fn parse_number(value: &str) -> Result<f64, AdapterError> {
    value
        .parse::<f64>()
        .map_err(|err| AdapterError::Decode(err.to_string()))
}

#[cfg(test)]
mod tests {
    use super::{parse_number, KrakenFuturesRestClient};

    #[test]
    fn default_base_url_is_https() {
        let client = KrakenFuturesRestClient::default();
        assert!(client.base_url.starts_with("https://"));
    }

    #[test]
    fn parse_number_handles_numeric_strings() {
        assert_eq!(parse_number("123.5").expect("valid numeric string"), 123.5);
    }
}
