pub mod config;
pub mod gap_detector;
pub mod repository;
pub mod worker;
pub mod ws_worker;

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{TimeZone, Utc};
use common_types::{DataQueryRequest, DataQueryResponse, Timeframe};
use kraken_adapter::MarketDataAdapter;
use repository::{IntegrityHistoryEntry, MarketDataRepository};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, sync::Arc};
use tower_http::cors::{Any, CorsLayer};
use tracing::{info, warn};

#[derive(Clone)]
pub struct AppState {
    pub repository: Arc<dyn MarketDataRepository>,
    pub adapter: Arc<dyn MarketDataAdapter>,
    pub integrity_threshold_pct: f64,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug)]
enum ApiError {
    SourceUnavailable(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self {
            Self::SourceUnavailable(message) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
        }
    }
}

pub fn build_router(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    Router::new()
        .route("/health", get(health))
        .route("/v1/data/query", post(query_data))
        .route("/v1/integrity/history", get(integrity_history))
        .route("/v1/market/metrics", get(market_metrics))
        .route("/v1/market/metrics/batch", get(market_metrics_batch))
        .layer(cors)
        .with_state(state)
}

async fn health(State(state): State<AppState>) -> Result<Json<HealthResponse>, ApiError> {
    state.repository.health_check().await.map_err(|error| {
        warn!(error = %error, "data-service health repository check failed");
        ApiError::SourceUnavailable(error.to_string())
    })?;
    Ok(Json(HealthResponse { status: "ok" }))
}

async fn query_data(
    State(state): State<AppState>,
    Json(request): Json<DataQueryRequest>,
) -> Result<Json<DataQueryResponse>, ApiError> {
    let normalized_request = normalize_request_window(&request);
    let normalization_warning = normalization_warning_code(&request, &normalized_request);

    let initial_candles = state
        .repository
        .fetch_candles(&normalized_request)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    let mut integrity = gap_detector::build_integrity_report(
        &normalized_request,
        &initial_candles,
        state.integrity_threshold_pct,
    );
    let mut unresolved_backfill_codes: Vec<String> = vec![];
    if !integrity.missing_ranges.is_empty() {
        info!(
            instrument = %normalized_request.instrument,
            missing_ranges = integrity.missing_ranges.len(),
            "local gap detected; attempting targeted backfill"
        );

        for range in &integrity.missing_ranges {
            let backfill_request = DataQueryRequest {
                instrument: normalized_request.instrument.clone(),
                timeframe: normalized_request.timeframe,
                start_ts: range.start_ts,
                end_ts: range.end_ts,
            };
            match state.adapter.fetch_candles(&backfill_request).await {
                Ok(candles) if !candles.is_empty() => {
                    let written = state
                        .repository
                        .upsert_candles(
                            &normalized_request.instrument,
                            normalized_request.timeframe,
                            &candles,
                        )
                        .await
                        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;
                    info!(
                        instrument = %normalized_request.instrument,
                        timeframe = ?normalized_request.timeframe,
                        written,
                        "backfill range persisted"
                    );
                }
                Ok(_) => {
                    unresolved_backfill_codes.push(format!(
                        "UNRESOLVED_BACKFILL_EMPTY:{}:{}",
                        range.start_ts.to_rfc3339(),
                        range.end_ts.to_rfc3339()
                    ));
                    warn!(
                        instrument = %normalized_request.instrument,
                        start_ts = %range.start_ts,
                        end_ts = %range.end_ts,
                        "backfill returned no candles"
                    );
                }
                Err(error) => {
                    unresolved_backfill_codes.push(format!(
                        "UNRESOLVED_BACKFILL_ERROR:{}:{}:{}",
                        range.start_ts.to_rfc3339(),
                        range.end_ts.to_rfc3339(),
                        error
                    ));
                    warn!(
                        instrument = %normalized_request.instrument,
                        start_ts = %range.start_ts,
                        end_ts = %range.end_ts,
                        error = %error,
                        "backfill request failed"
                    );
                }
            }
        }
    }

    let candles = state
        .repository
        .fetch_candles(&normalized_request)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;
    integrity = gap_detector::build_integrity_report(
        &normalized_request,
        &candles,
        state.integrity_threshold_pct,
    );
    if let Some(code) = normalization_warning {
        integrity.warnings.push(code);
    }
    if !integrity.missing_ranges.is_empty() && !unresolved_backfill_codes.is_empty() {
        integrity.warnings.extend(unresolved_backfill_codes);
    }
    state
        .repository
        .record_quality_interval(&normalized_request, &integrity)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    Ok(Json(DataQueryResponse {
        instrument: normalized_request.instrument,
        timeframe: normalized_request.timeframe,
        start_ts: normalized_request.start_ts,
        end_ts: normalized_request.end_ts,
        candles,
        integrity,
    }))
}

#[derive(Debug, serde::Deserialize)]
struct IntegrityHistoryQuery {
    instrument: String,
    timeframe: String,
    limit: Option<i64>,
}

#[derive(Debug, Serialize)]
struct IntegrityHistoryResponse {
    instrument: String,
    timeframe: String,
    rows: Vec<IntegrityHistoryRow>,
}

#[derive(Debug, Serialize)]
struct IntegrityHistoryRow {
    start_ts: chrono::DateTime<chrono::Utc>,
    end_ts: chrono::DateTime<chrono::Utc>,
    status: String,
    coverage_pct: f64,
    reason: String,
    checked_at: chrono::DateTime<chrono::Utc>,
}

async fn integrity_history(
    State(state): State<AppState>,
    Query(query): Query<IntegrityHistoryQuery>,
) -> Result<Json<IntegrityHistoryResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::SourceUnavailable("invalid timeframe; expected one of 1m, 15m, 1h".to_string())
    })?;
    let limit = query.limit.unwrap_or(100).clamp(1, 500);
    let rows = state
        .repository
        .fetch_integrity_history(&query.instrument, timeframe, limit)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    Ok(Json(IntegrityHistoryResponse {
        instrument: query.instrument,
        timeframe: timeframe.as_str().to_string(),
        rows: rows.into_iter().map(map_history_row).collect(),
    }))
}

#[derive(Debug, serde::Deserialize)]
struct MarketMetricsQuery {
    instrument: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct MarketMetricsResponse {
    instrument: String,
    server_time: chrono::DateTime<chrono::Utc>,
    bid: f64,
    ask: f64,
    mark: f64,
    index: f64,
    change_24h_pct: f64,
    funding_rate: f64,
    open_interest: f64,
}

#[derive(Debug, Deserialize)]
struct MarketMetricsBatchQuery {
    instruments: String,
}

#[derive(Debug, Serialize)]
struct MarketMetricsBatchResponse {
    generated_at: chrono::DateTime<chrono::Utc>,
    metrics: Vec<MarketMetricsResponse>,
}

async fn market_metrics(
    State(state): State<AppState>,
    Query(query): Query<MarketMetricsQuery>,
) -> Result<Json<MarketMetricsResponse>, ApiError> {
    let instrument = query.instrument.trim();
    if instrument.is_empty() {
        return Err(ApiError::SourceUnavailable(
            "instrument query parameter is required".to_string(),
        ));
    }

    let metrics = state
        .adapter
        .fetch_market_metrics(instrument)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    Ok(Json(MarketMetricsResponse {
        instrument: metrics.instrument,
        server_time: metrics.server_time,
        bid: metrics.bid,
        ask: metrics.ask,
        mark: metrics.mark,
        index: metrics.index,
        change_24h_pct: metrics.change_24h_pct,
        funding_rate: metrics.funding_rate,
        open_interest: metrics.open_interest,
    }))
}

async fn market_metrics_batch(
    State(state): State<AppState>,
    Query(query): Query<MarketMetricsBatchQuery>,
) -> Result<Json<MarketMetricsBatchResponse>, ApiError> {
    let instruments = query
        .instruments
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .collect::<Vec<_>>();
    if instruments.is_empty() {
        return Err(ApiError::SourceUnavailable(
            "instruments query parameter is required".to_string(),
        ));
    }

    let mut dedupe = HashSet::new();
    let mut normalized = Vec::with_capacity(instruments.len());
    for instrument in instruments {
        let key = instrument.to_uppercase();
        if dedupe.insert(key) {
            normalized.push(instrument);
        }
    }

    let metrics = state
        .adapter
        .fetch_market_metrics_batch(&normalized)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    Ok(Json(MarketMetricsBatchResponse {
        generated_at: Utc::now(),
        metrics: metrics
            .into_iter()
            .map(|entry| MarketMetricsResponse {
                instrument: entry.instrument,
                server_time: entry.server_time,
                bid: entry.bid,
                ask: entry.ask,
                mark: entry.mark,
                index: entry.index,
                change_24h_pct: entry.change_24h_pct,
                funding_rate: entry.funding_rate,
                open_interest: entry.open_interest,
            })
            .collect(),
    }))
}

fn map_history_row(value: IntegrityHistoryEntry) -> IntegrityHistoryRow {
    IntegrityHistoryRow {
        start_ts: value.start_ts,
        end_ts: value.end_ts,
        status: value.status,
        coverage_pct: value.coverage_pct,
        reason: value.reason,
        checked_at: value.checked_at,
    }
}

pub(crate) fn normalize_request_window(request: &DataQueryRequest) -> DataQueryRequest {
    let step = request.timeframe.step_seconds();
    let (start, end) = align_bounds_to_step(
        request.start_ts.timestamp(),
        request.end_ts.timestamp(),
        step,
    );
    if start > end {
        return request.clone();
    }
    let start_ts = Utc
        .timestamp_opt(start, 0)
        .single()
        .unwrap_or(request.start_ts);
    let end_ts = Utc.timestamp_opt(end, 0).single().unwrap_or(request.end_ts);
    DataQueryRequest {
        instrument: request.instrument.clone(),
        timeframe: request.timeframe,
        start_ts,
        end_ts,
    }
}

pub(crate) fn align_bounds_to_step(start: i64, end: i64, step: i64) -> (i64, i64) {
    if step <= 0 {
        return (start, end);
    }
    let start_offset = start.rem_euclid(step);
    let aligned_start = if start_offset == 0 {
        start
    } else {
        start + (step - start_offset)
    };
    let aligned_end = end - end.rem_euclid(step);
    (aligned_start, aligned_end)
}

fn normalization_warning_code(
    original: &DataQueryRequest,
    normalized: &DataQueryRequest,
) -> Option<String> {
    if original.start_ts == normalized.start_ts && original.end_ts == normalized.end_ts {
        return None;
    }
    Some(format!(
        "REQUEST_WINDOW_NORMALIZED:{}:{}:{}:{}",
        original.start_ts.to_rfc3339(),
        original.end_ts.to_rfc3339(),
        normalized.start_ts.to_rfc3339(),
        normalized.end_ts.to_rfc3339()
    ))
}

#[cfg(test)]
mod tests {
    use super::{align_bounds_to_step, health, normalize_request_window, AppState};
    use crate::repository::{MarketDataRepository, UnconfiguredRepository};
    use axum::{extract::State, http::StatusCode, response::IntoResponse};
    use chrono::{TimeZone, Utc};
    use common_types::{DataQueryRequest, Timeframe};
    use kraken_adapter::{KrakenFuturesRestClient, MarketDataAdapter};
    use std::sync::Arc;

    #[tokio::test]
    async fn health_returns_503_when_repository_check_fails() {
        let status = request_health_status(Arc::new(UnconfiguredRepository)).await;
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    }

    async fn request_health_status(repository: Arc<dyn MarketDataRepository>) -> StatusCode {
        let state = AppState {
            repository,
            adapter: Arc::new(KrakenFuturesRestClient::new("http://127.0.0.1"))
                as Arc<dyn MarketDataAdapter>,
            integrity_threshold_pct: 0.95,
        };
        health(State(state)).await.into_response().status()
    }

    #[test]
    fn align_bounds_ceil_start_and_floor_end() {
        let (start, end) = align_bounds_to_step(1_700_000_005, 1_700_000_125, 60);
        assert_eq!(start, 1_700_000_040);
        assert_eq!(end, 1_700_000_100);
    }

    #[test]
    fn normalize_request_window_preserves_usable_range() {
        let request = DataQueryRequest {
            instrument: "PI_XBTUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            start_ts: Utc
                .timestamp_opt(1_700_000_005, 0)
                .single()
                .expect("valid timestamp"),
            end_ts: Utc
                .timestamp_opt(1_700_000_125, 0)
                .single()
                .expect("valid timestamp"),
        };
        let normalized = normalize_request_window(&request);
        assert_eq!(normalized.start_ts.timestamp(), 1_700_000_040);
        assert_eq!(normalized.end_ts.timestamp(), 1_700_000_100);
    }

    #[test]
    fn normalize_request_window_falls_back_when_alignment_inverts_window() {
        let request = DataQueryRequest {
            instrument: "PI_XBTUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            start_ts: Utc
                .timestamp_opt(1_700_000_005, 0)
                .single()
                .expect("valid timestamp"),
            end_ts: Utc
                .timestamp_opt(1_700_000_039, 0)
                .single()
                .expect("valid timestamp"),
        };
        let normalized = normalize_request_window(&request);
        assert_eq!(normalized.start_ts, request.start_ts);
        assert_eq!(normalized.end_ts, request.end_ts);
    }
}
