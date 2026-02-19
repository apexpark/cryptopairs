use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use common_types::Timeframe;
use execution_service::{
    evaluate_integrity_gate_from_store, evaluate_order_intent, normalize_side, GateDecision,
    OrderIntentAction, OrderIntentDecision, OrderLifecycleState, ReconcileDecision,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio_postgres::{types::ToSql, Client, NoTls};
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

#[derive(Clone)]
struct AppState {
    repository: Arc<ExecutionRepository>,
    postgres_url: Arc<String>,
    default_min_coverage_pct: f64,
}

#[derive(Clone)]
struct ExecutionRepository {
    client: Arc<Client>,
}

impl ExecutionRepository {
    async fn connect(connection_string: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(connection_string, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                tracing::error!(error = %error, "execution-service postgres connection ended");
            }
        });

        let repository = Self {
            client: Arc::new(client),
        };
        repository.ensure_schema().await?;
        Ok(repository)
    }

    async fn ensure_schema(&self) -> anyhow::Result<()> {
        self.client
            .batch_execute(
                "CREATE TABLE IF NOT EXISTS execution_control (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    kill_switch_active BOOLEAN NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (id = 1)
                 );
                 CREATE TABLE IF NOT EXISTS execution_control_events (
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    kill_switch_active BOOLEAN NOT NULL,
                    reason TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'system'
                 );
                 CREATE TABLE IF NOT EXISTS execution_order_intents (
                    idempotency_key TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL DEFAULT 'kraken_futures',
                    account_id TEXT NOT NULL DEFAULT 'default',
                    instrument TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    action TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty DOUBLE PRECISION NOT NULL,
                    operator_confirmed BOOLEAN NOT NULL,
                    operator_id TEXT,
                    min_coverage_pct DOUBLE PRECISION NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                 );
                 CREATE TABLE IF NOT EXISTS execution_order_state_events (
                    idempotency_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT 'system',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (idempotency_key, state, created_at)
                 );
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS exchange TEXT NOT NULL DEFAULT 'kraken_futures';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS account_id TEXT NOT NULL DEFAULT 'default';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'ENTRY';
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS operator_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
                 ALTER TABLE execution_order_intents
                 ADD COLUMN IF NOT EXISTS operator_id TEXT;",
            )
            .await?;
        Ok(())
    }

    async fn get_kill_switch_state(&self) -> anyhow::Result<KillSwitchState> {
        let row = self
            .client
            .query_opt(
                "SELECT kill_switch_active, reason, updated_at
                 FROM execution_control
                 WHERE id = 1",
                &[],
            )
            .await?;

        if let Some(row) = row {
            Ok(KillSwitchState {
                active: row.get(0),
                reason: row.get(1),
                updated_at: row.get(2),
            })
        } else {
            Ok(KillSwitchState {
                active: true,
                reason: "unknown kill switch state; defaulting to blocked".to_string(),
                updated_at: Utc::now(),
            })
        }
    }

    async fn set_kill_switch_state(
        &self,
        active: bool,
        reason: &str,
        actor: &str,
    ) -> anyhow::Result<KillSwitchState> {
        let now = Utc::now();
        self.client
            .execute(
                "INSERT INTO execution_control (id, kill_switch_active, reason, updated_at)
                 VALUES (1, $1, $2, $3)
                 ON CONFLICT (id) DO UPDATE SET
                   kill_switch_active = EXCLUDED.kill_switch_active,
                   reason = EXCLUDED.reason,
                   updated_at = EXCLUDED.updated_at",
                &[&active, &reason, &now],
            )
            .await?;

        self.client
            .execute(
                "INSERT INTO execution_control_events (ts, kill_switch_active, reason, actor)
                 VALUES ($1, $2, $3, $4)",
                &[&now as &(dyn ToSql + Sync), &active, &reason, &actor],
            )
            .await?;

        Ok(KillSwitchState {
            active,
            reason: reason.to_string(),
            updated_at: now,
        })
    }

    async fn fetch_order_intent(
        &self,
        idempotency_key: &str,
    ) -> anyhow::Result<Option<OrderIntentRecord>> {
        let row = self
            .client
            .query_opt(
                "SELECT idempotency_key, instrument, timeframe, action, side, qty,
                        operator_confirmed, operator_id, min_coverage_pct, exchange, account_id,
                        decision, reason, created_at
                 FROM execution_order_intents
                 WHERE idempotency_key = $1",
                &[&idempotency_key],
            )
            .await?;

        Ok(row.map(|row| OrderIntentRecord {
            idempotency_key: row.get(0),
            instrument: row.get(1),
            timeframe: row.get(2),
            action: row.get(3),
            side: row.get(4),
            qty: row.get(5),
            operator_confirmed: row.get(6),
            operator_id: row.get(7),
            min_coverage_pct: row.get(8),
            exchange: row.get(9),
            account_id: row.get(10),
            decision: row.get(11),
            reason: row.get(12),
            created_at: row.get(13),
        }))
    }

    async fn insert_order_intent(&self, record: &OrderIntentRecord) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO execution_order_intents
                 (idempotency_key, instrument, timeframe, action, side, qty,
                  operator_confirmed, operator_id, min_coverage_pct, exchange, account_id,
                  decision, reason, created_at)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                 ON CONFLICT (idempotency_key) DO NOTHING",
                &[
                    &record.idempotency_key as &(dyn ToSql + Sync),
                    &record.instrument,
                    &record.timeframe,
                    &record.action,
                    &record.side,
                    &record.qty,
                    &record.operator_confirmed,
                    &record.operator_id,
                    &record.min_coverage_pct,
                    &record.exchange,
                    &record.account_id,
                    &record.decision,
                    &record.reason,
                    &record.created_at,
                ],
            )
            .await?;
        self.record_state_event(
            &record.idempotency_key,
            OrderLifecycleState::New,
            "intent persisted",
            "execution-service",
        )
        .await?;

        let follow_up_state = if record.decision == "ACCEPTED" {
            OrderLifecycleState::Approved
        } else {
            OrderLifecycleState::Rejected
        };
        self.record_state_event(
            &record.idempotency_key,
            follow_up_state,
            &record.reason,
            "execution-service",
        )
        .await?;
        Ok(())
    }

    async fn fetch_latest_reconcile_decision(
        &self,
        exchange: &str,
        account_id: &str,
    ) -> anyhow::Result<ReconcileDecision> {
        let row = self
            .client
            .query_opt(
                "SELECT status, drift_notional, notes
                 FROM reconciliation_events
                 WHERE exchange=$1 AND account_id=$2
                 ORDER BY ts DESC
                 LIMIT 1",
                &[&exchange, &account_id],
            )
            .await?;
        let Some(row) = row else {
            return Ok(ReconcileDecision::Blocked(format!(
                "reconcile gate blocked signal: no reconcile history for exchange={exchange} account_id={account_id}"
            )));
        };
        let status: String = row.get(0);
        let drift_notional: f64 = row.get(1);
        let notes: String = row.get(2);
        if status == "OK" {
            Ok(ReconcileDecision::Allowed)
        } else {
            Ok(ReconcileDecision::Blocked(format!(
                "reconcile gate blocked signal: status={status} drift_notional={drift_notional:.4} notes={notes}"
            )))
        }
    }

    async fn record_state_event(
        &self,
        idempotency_key: &str,
        state: OrderLifecycleState,
        reason: &str,
        actor: &str,
    ) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO execution_order_state_events
                 (idempotency_key, state, reason, actor, created_at)
                 VALUES ($1,$2,$3,$4,NOW())",
                &[&idempotency_key, &state.as_str(), &reason, &actor],
            )
            .await?;
        Ok(())
    }
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
    evaluated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct UpdateKillSwitchRequest {
    active: bool,
    reason: String,
    actor: Option<String>,
}

#[derive(Debug, Serialize)]
struct KillSwitchState {
    active: bool,
    reason: String,
    updated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
struct OrderIntentRequest {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    instrument: String,
    timeframe: String,
    action: String,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: Option<f64>,
}

#[derive(Debug, Serialize)]
struct OrderIntentResponse {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    instrument: String,
    timeframe: String,
    action: String,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: f64,
    decision: String,
    reason: Option<String>,
    evaluated_at: DateTime<Utc>,
}

#[derive(Debug)]
struct OrderIntentRecord {
    idempotency_key: String,
    exchange: String,
    account_id: String,
    instrument: String,
    timeframe: String,
    action: String,
    side: String,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<String>,
    min_coverage_pct: f64,
    decision: String,
    reason: String,
    created_at: DateTime<Utc>,
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

    let repository = Arc::new(ExecutionRepository::connect(&postgres_url).await?);
    let app_state = AppState {
        repository,
        postgres_url: Arc::new(postgres_url.clone()),
        default_min_coverage_pct,
    };
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);
    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/execution/decision", get(decision))
        .route(
            "/v1/execution/kill-switch",
            get(kill_switch).post(update_kill_switch),
        )
        .route("/v1/execution/order-intent", post(order_intent))
        .layer(cors)
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
        evaluated_at: Utc::now(),
    }))
}

async fn kill_switch(State(state): State<AppState>) -> Result<Json<KillSwitchState>, ApiError> {
    let current = state
        .repository
        .get_kill_switch_state()
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    Ok(Json(current))
}

async fn update_kill_switch(
    State(state): State<AppState>,
    Json(payload): Json<UpdateKillSwitchRequest>,
) -> Result<Json<KillSwitchState>, ApiError> {
    if payload.active && payload.reason.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "reason is required when enabling kill switch".to_string(),
        ));
    }
    let actor = payload.actor.unwrap_or_else(|| "operator".to_string());
    let reason = if payload.reason.trim().is_empty() {
        "manual update".to_string()
    } else {
        payload.reason
    };

    let updated = state
        .repository
        .set_kill_switch_state(payload.active, &reason, &actor)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    info!(
        active = updated.active,
        reason = %updated.reason,
        actor = %actor,
        "execution kill switch updated"
    );

    Ok(Json(updated))
}

async fn order_intent(
    State(state): State<AppState>,
    Json(payload): Json<OrderIntentRequest>,
) -> Result<Json<OrderIntentResponse>, ApiError> {
    if payload.idempotency_key.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "idempotency_key is required".to_string(),
        ));
    }
    if payload.exchange.trim().is_empty() || payload.account_id.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "exchange and account_id are required".to_string(),
        ));
    }
    if payload.qty <= 0.0 {
        return Err(ApiError::BadRequest("qty must be > 0".to_string()));
    }
    let timeframe = Timeframe::parse(&payload.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected one of 1m, 15m, 1h".to_string())
    })?;
    let action = OrderIntentAction::parse(&payload.action).ok_or_else(|| {
        ApiError::BadRequest("action must be one of ENTRY, EXIT, EMERGENCY_STOP_CLOSE".to_string())
    })?;
    let side = normalize_side(&payload.side)
        .ok_or_else(|| ApiError::BadRequest("side must be BUY or SELL".to_string()))?;
    let normalized_operator_id = payload
        .operator_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string);
    validate_manual_controls(
        action,
        payload.operator_confirmed,
        normalized_operator_id.as_deref(),
    )?;

    let min_coverage_pct = payload
        .min_coverage_pct
        .unwrap_or(state.default_min_coverage_pct);

    if let Some(existing) = state
        .repository
        .fetch_order_intent(&payload.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
    {
        if !is_same_intent(
            &existing,
            &payload.exchange,
            &payload.account_id,
            &payload.instrument,
            timeframe,
            action,
            side,
            payload.qty,
            payload.operator_confirmed,
            normalized_operator_id.as_deref(),
            min_coverage_pct,
        ) {
            return Err(ApiError::BadRequest(
                "idempotency_key already used with different payload".to_string(),
            ));
        }
        return Ok(Json(map_order_intent(existing)));
    }

    let kill_switch = state
        .repository
        .get_kill_switch_state()
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let gate_decision = if matches!(action, OrderIntentAction::EmergencyStopClose) {
        GateDecision::Allowed
    } else {
        evaluate_integrity_gate_from_store(
            &state.postgres_url,
            &payload.instrument,
            timeframe,
            min_coverage_pct,
        )
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
    };

    let reconcile_decision = if matches!(action, OrderIntentAction::EmergencyStopClose) {
        ReconcileDecision::Allowed
    } else {
        state
            .repository
            .fetch_latest_reconcile_decision(&payload.exchange, &payload.account_id)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?
    };

    let intent_decision = evaluate_order_intent(
        action,
        kill_switch.active,
        gate_decision,
        reconcile_decision,
    );
    let (decision, reason) = match intent_decision {
        OrderIntentDecision::Accepted => ("ACCEPTED".to_string(), String::new()),
        OrderIntentDecision::Blocked(reason) => ("BLOCKED".to_string(), reason),
    };

    let record = OrderIntentRecord {
        idempotency_key: payload.idempotency_key,
        exchange: payload.exchange,
        account_id: payload.account_id,
        instrument: payload.instrument,
        timeframe: timeframe.as_str().to_string(),
        action: action.as_str().to_string(),
        side: side.to_string(),
        qty: payload.qty,
        operator_confirmed: payload.operator_confirmed,
        operator_id: normalized_operator_id,
        min_coverage_pct,
        decision,
        reason,
        created_at: Utc::now(),
    };

    state
        .repository
        .insert_order_intent(&record)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let stored = state
        .repository
        .fetch_order_intent(&record.idempotency_key)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?
        .ok_or_else(|| ApiError::Upstream("order intent persistence failed".to_string()))?;

    info!(
        idempotency_key = %stored.idempotency_key,
        action = %stored.action,
        operator_confirmed = stored.operator_confirmed,
        decision = %stored.decision,
        reason = %stored.reason,
        "execution order intent evaluated"
    );

    Ok(Json(map_order_intent(stored)))
}

fn validate_manual_controls(
    action: OrderIntentAction,
    operator_confirmed: bool,
    operator_id: Option<&str>,
) -> Result<(), ApiError> {
    if matches!(action, OrderIntentAction::Entry | OrderIntentAction::Exit) {
        if !operator_confirmed {
            return Err(ApiError::BadRequest(
                "manual ENTRY/EXIT requires operator_confirmed=true".to_string(),
            ));
        }
        if operator_id.is_none() {
            return Err(ApiError::BadRequest(
                "manual ENTRY/EXIT requires operator_id".to_string(),
            ));
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn is_same_intent(
    existing: &OrderIntentRecord,
    exchange: &str,
    account_id: &str,
    instrument: &str,
    timeframe: Timeframe,
    action: OrderIntentAction,
    side: &str,
    qty: f64,
    operator_confirmed: bool,
    operator_id: Option<&str>,
    min_coverage_pct: f64,
) -> bool {
    existing.exchange == exchange
        && existing.account_id == account_id
        && existing.instrument == instrument
        && existing.timeframe == timeframe.as_str()
        && existing.action == action.as_str()
        && existing.side == side
        && (existing.qty - qty).abs() < f64::EPSILON
        && existing.operator_confirmed == operator_confirmed
        && existing.operator_id.as_deref() == operator_id
        && (existing.min_coverage_pct - min_coverage_pct).abs() < f64::EPSILON
}

fn map_order_intent(record: OrderIntentRecord) -> OrderIntentResponse {
    OrderIntentResponse {
        idempotency_key: record.idempotency_key,
        exchange: record.exchange,
        account_id: record.account_id,
        instrument: record.instrument,
        timeframe: record.timeframe,
        action: record.action,
        side: record.side,
        qty: record.qty,
        operator_confirmed: record.operator_confirmed,
        operator_id: record.operator_id,
        min_coverage_pct: record.min_coverage_pct,
        decision: record.decision,
        reason: if record.reason.is_empty() {
            None
        } else {
            Some(record.reason)
        },
        evaluated_at: record.created_at,
    }
}

#[cfg(test)]
mod tests {
    use super::{validate_manual_controls, ApiError};
    use execution_service::OrderIntentAction;

    #[test]
    fn manual_entry_requires_operator_confirmation() {
        let result = validate_manual_controls(OrderIntentAction::Entry, false, Some("ops-1"));
        assert!(matches!(result, Err(ApiError::BadRequest(_))));
    }

    #[test]
    fn manual_exit_requires_operator_id() {
        let result = validate_manual_controls(OrderIntentAction::Exit, true, None);
        assert!(matches!(result, Err(ApiError::BadRequest(_))));
    }

    #[test]
    fn emergency_stop_can_run_without_operator_confirmation() {
        let result = validate_manual_controls(OrderIntentAction::EmergencyStopClose, false, None);
        assert!(result.is_ok());
    }
}
