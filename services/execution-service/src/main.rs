use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use common_types::Timeframe;
use execution_service::{evaluate_integrity_gate_from_store, GateDecision};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::net::TcpListener;
use tracing::info;

#[derive(Clone)]
struct AppState {
    postgres_url: Arc<String>,
    default_min_coverage_pct: f64,
}

#[derive(Debug, Deserialize)]
struct DecisionQuery {
    instrument: String,
    timeframe: String,
    min_coverage_pct: Option<f64>,
}

#[derive(Debug, Serialize)]
struct DecisionResponse {
    instrument: String,
    timeframe: String,
    decision: &'static str,
    reason: Option<String>,
    min_coverage_pct: f64,
    evaluated_at: chrono::DateTime<chrono::Utc>,
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
    BadRequest(String),
    Upstream(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self {
            Self::BadRequest(message) => (
                StatusCode::BAD_REQUEST,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
            Self::Upstream(message) => (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
        "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
    });
    let port = std::env::var("EXECUTION_SERVICE_PORT").unwrap_or_else(|_| "8082".to_string());
    let default_min_coverage_pct = std::env::var("INTEGRITY_MIN_COVERAGE_PCT")
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(99.5);
    let bind_addr = format!("0.0.0.0:{port}");

    let app_state = AppState {
        postgres_url: Arc::new(postgres_url.clone()),
        default_min_coverage_pct,
    };
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/execution/decision", get(decision))
        .with_state(app_state);

    let listener = TcpListener::bind(&bind_addr).await?;
    info!(
        bind_addr = %bind_addr,
        postgres_url = %postgres_url,
        default_min_coverage_pct,
        "execution-service started"
    );
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn decision(
    State(state): State<AppState>,
    Query(query): Query<DecisionQuery>,
) -> Result<Json<DecisionResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected one of 1m, 15m, 1h".to_string())
    })?;
    let min_coverage_pct = query
        .min_coverage_pct
        .unwrap_or(state.default_min_coverage_pct);
    let gate_decision = evaluate_integrity_gate_from_store(
        &state.postgres_url,
        &query.instrument,
        timeframe,
        min_coverage_pct,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (decision, reason) = match gate_decision {
        GateDecision::Allowed => ("ALLOWED", None),
        GateDecision::Blocked(reason) => ("BLOCKED", Some(reason)),
    };

    Ok(Json(DecisionResponse {
        instrument: query.instrument,
        timeframe: timeframe.as_str().to_string(),
        decision,
        reason,
        min_coverage_pct,
        evaluated_at: chrono::Utc::now(),
    }))
}
