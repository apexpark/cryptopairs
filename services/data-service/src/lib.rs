pub mod config;
pub mod gap_detector;
pub mod repository;
pub mod worker;

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use common_types::{DataQueryRequest, DataQueryResponse};
use kraken_adapter::MarketDataAdapter;
use repository::MarketDataRepository;
use serde::Serialize;
use std::sync::Arc;
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
    Router::new()
        .route("/health", get(health))
        .route("/v1/data/query", post(query_data))
        .with_state(state)
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn query_data(
    State(state): State<AppState>,
    Json(request): Json<DataQueryRequest>,
) -> Result<Json<DataQueryResponse>, ApiError> {
    let initial_candles = state
        .repository
        .fetch_candles(&request)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    let mut integrity = gap_detector::build_integrity_report(
        &request,
        &initial_candles,
        state.integrity_threshold_pct,
    );
    if !integrity.missing_ranges.is_empty() {
        info!(
            instrument = %request.instrument,
            missing_ranges = integrity.missing_ranges.len(),
            "local gap detected; attempting targeted backfill"
        );

        for range in &integrity.missing_ranges {
            let backfill_request = DataQueryRequest {
                instrument: request.instrument.clone(),
                timeframe: request.timeframe,
                start_ts: range.start_ts,
                end_ts: range.end_ts,
            };
            match state.adapter.fetch_candles(&backfill_request).await {
                Ok(candles) if !candles.is_empty() => {
                    let written = state
                        .repository
                        .upsert_candles(&request.instrument, request.timeframe, &candles)
                        .await
                        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;
                    info!(
                        instrument = %request.instrument,
                        timeframe = ?request.timeframe,
                        written,
                        "backfill range persisted"
                    );
                }
                Ok(_) => {
                    warn!(
                        instrument = %request.instrument,
                        start_ts = %range.start_ts,
                        end_ts = %range.end_ts,
                        "backfill returned no candles"
                    );
                }
                Err(error) => {
                    warn!(
                        instrument = %request.instrument,
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
        .fetch_candles(&request)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;
    integrity =
        gap_detector::build_integrity_report(&request, &candles, state.integrity_threshold_pct);
    state
        .repository
        .record_quality_interval(&request, &integrity)
        .await
        .map_err(|error| ApiError::SourceUnavailable(error.to_string()))?;

    Ok(Json(DataQueryResponse {
        instrument: request.instrument,
        timeframe: request.timeframe,
        start_ts: request.start_ts,
        end_ts: request.end_ts,
        candles,
        integrity,
    }))
}
