use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    response::Response,
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio_postgres::{types::ToSql, Client, NoTls};

#[derive(Clone)]
pub struct AppState {
    pub repository: Arc<AccountRepository>,
}

#[derive(Clone)]
pub struct AccountRepository {
    client: Arc<Client>,
}

impl AccountRepository {
    pub async fn connect(connection_string: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(connection_string, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                tracing::error!(error = %error, "account-service postgres connection ended");
            }
        });
        let repo = Self {
            client: Arc::new(client),
        };
        repo.ensure_schema().await?;
        Ok(repo)
    }

    async fn ensure_schema(&self) -> anyhow::Result<()> {
        self.client
            .batch_execute(
                "CREATE TABLE IF NOT EXISTS account_snapshots (
                    exchange TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    equity DOUBLE PRECISION NOT NULL,
                    balance DOUBLE PRECISION NOT NULL,
                    margin_used DOUBLE PRECISION NOT NULL,
                    unrealized_pnl DOUBLE PRECISION NOT NULL,
                    realized_pnl DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (exchange, account_id, ts)
                 );
                 CREATE TABLE IF NOT EXISTS reconciliation_events (
                    exchange TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL,
                    drift_notional DOUBLE PRECISION NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (exchange, account_id, ts)
                 );",
            )
            .await?;
        Ok(())
    }

    pub async fn insert_snapshot(&self, snapshot: &AccountSnapshotWrite) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO account_snapshots
                  (exchange, account_id, ts, equity, balance, margin_used, unrealized_pnl, realized_pnl)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                 ON CONFLICT (exchange, account_id, ts) DO UPDATE SET
                  equity = EXCLUDED.equity,
                  balance = EXCLUDED.balance,
                  margin_used = EXCLUDED.margin_used,
                  unrealized_pnl = EXCLUDED.unrealized_pnl,
                  realized_pnl = EXCLUDED.realized_pnl",
                &[
                    &snapshot.exchange as &(dyn ToSql + Sync),
                    &snapshot.account_id,
                    &snapshot.ts,
                    &snapshot.equity,
                    &snapshot.balance,
                    &snapshot.margin_used,
                    &snapshot.unrealized_pnl,
                    &snapshot.realized_pnl,
                ],
            )
            .await?;
        Ok(())
    }

    pub async fn latest_snapshot(
        &self,
        exchange: &str,
        account_id: &str,
    ) -> anyhow::Result<Option<AccountSnapshotRead>> {
        let row = self
            .client
            .query_opt(
                "SELECT exchange, account_id, ts, equity, balance, margin_used, unrealized_pnl, realized_pnl
                 FROM account_snapshots
                 WHERE exchange=$1 AND account_id=$2
                 ORDER BY ts DESC LIMIT 1",
                &[&exchange, &account_id],
            )
            .await?;

        Ok(row.map(|r| AccountSnapshotRead {
            exchange: r.get(0),
            account_id: r.get(1),
            ts: r.get(2),
            equity: r.get(3),
            balance: r.get(4),
            margin_used: r.get(5),
            unrealized_pnl: r.get(6),
            realized_pnl: r.get(7),
        }))
    }

    pub async fn latest_reconcile(
        &self,
        exchange: &str,
        account_id: &str,
    ) -> anyhow::Result<Option<ReconcileRead>> {
        let row = self
            .client
            .query_opt(
                "SELECT exchange, account_id, ts, status, drift_notional, notes
                 FROM reconciliation_events
                 WHERE exchange=$1 AND account_id=$2
                 ORDER BY ts DESC LIMIT 1",
                &[&exchange, &account_id],
            )
            .await?;
        Ok(row.map(|r| ReconcileRead {
            exchange: r.get(0),
            account_id: r.get(1),
            ts: r.get(2),
            status: r.get(3),
            drift_notional: r.get(4),
            notes: r.get(5),
        }))
    }

    pub async fn record_reconcile(&self, event: &ReconcileWrite) -> anyhow::Result<()> {
        self.client
            .execute(
                "INSERT INTO reconciliation_events
                 (exchange, account_id, ts, status, drift_notional, notes)
                 VALUES ($1,$2,$3,$4,$5,$6)
                 ON CONFLICT (exchange, account_id, ts) DO UPDATE SET
                  status=EXCLUDED.status,
                  drift_notional=EXCLUDED.drift_notional,
                  notes=EXCLUDED.notes",
                &[
                    &event.exchange as &(dyn ToSql + Sync),
                    &event.account_id,
                    &event.ts,
                    &event.status,
                    &event.drift_notional,
                    &event.notes,
                ],
            )
            .await?;
        Ok(())
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AccountSnapshotWrite {
    pub exchange: String,
    pub account_id: String,
    pub ts: DateTime<Utc>,
    pub equity: f64,
    pub balance: f64,
    pub margin_used: f64,
    pub unrealized_pnl: f64,
    pub realized_pnl: f64,
}

#[derive(Debug, Serialize)]
pub struct AccountSnapshotRead {
    pub exchange: String,
    pub account_id: String,
    pub ts: DateTime<Utc>,
    pub equity: f64,
    pub balance: f64,
    pub margin_used: f64,
    pub unrealized_pnl: f64,
    pub realized_pnl: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ReconcileWrite {
    pub exchange: String,
    pub account_id: String,
    pub ts: DateTime<Utc>,
    pub status: String,
    pub drift_notional: f64,
    pub notes: String,
}

#[derive(Debug, Serialize)]
pub struct ReconcileRead {
    pub exchange: String,
    pub account_id: String,
    pub ts: DateTime<Utc>,
    pub status: String,
    pub drift_notional: f64,
    pub notes: String,
}

#[derive(Debug, Deserialize)]
struct AccountQuery {
    exchange: String,
    account_id: String,
}

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route(
            "/v1/account/snapshot",
            post(write_snapshot).get(read_snapshot),
        )
        .route(
            "/v1/account/reconcile",
            post(write_reconcile).get(read_reconcile),
        )
        .with_state(state)
}

#[derive(Debug)]
struct ApiError(String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({ "error": self.0 })),
        )
            .into_response()
    }
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status":"ok" }))
}

async fn write_snapshot(
    State(state): State<AppState>,
    Json(payload): Json<AccountSnapshotWrite>,
) -> Result<impl IntoResponse, ApiError> {
    state
        .repository
        .insert_snapshot(&payload)
        .await
        .map_err(|error| ApiError(error.to_string()))?;
    Ok(Json(serde_json::json!({"written": true})))
}

async fn read_snapshot(
    State(state): State<AppState>,
    axum::extract::Query(query): axum::extract::Query<AccountQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let snapshot = state
        .repository
        .latest_snapshot(&query.exchange, &query.account_id)
        .await
        .map_err(|error| ApiError(error.to_string()))?;
    Ok(Json(serde_json::json!({ "snapshot": snapshot })))
}

async fn write_reconcile(
    State(state): State<AppState>,
    Json(payload): Json<ReconcileWrite>,
) -> Result<impl IntoResponse, ApiError> {
    state
        .repository
        .record_reconcile(&payload)
        .await
        .map_err(|error| ApiError(error.to_string()))?;
    Ok(Json(serde_json::json!({"written": true})))
}

async fn read_reconcile(
    State(state): State<AppState>,
    axum::extract::Query(query): axum::extract::Query<AccountQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let event = state
        .repository
        .latest_reconcile(&query.exchange, &query.account_id)
        .await
        .map_err(|error| ApiError(error.to_string()))?;
    Ok(Json(serde_json::json!({ "reconcile": event })))
}
