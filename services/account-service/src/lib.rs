use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    response::Response,
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio_postgres::{types::ToSql, Client, NoTls};
use tower_http::cors::{Any, CorsLayer};

#[derive(Clone)]
pub struct AppState {
    pub repository: Arc<AccountRepository>,
}

#[derive(Debug, Clone, Copy)]
pub struct ReconcileJobConfig {
    pub max_snapshot_age_secs: i64,
    pub max_drift_notional: f64,
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

    pub async fn latest_snapshots_all(&self) -> anyhow::Result<Vec<AccountSnapshotRead>> {
        let rows = self
            .client
            .query(
                "SELECT DISTINCT ON (exchange, account_id)
                    exchange, account_id, ts, equity, balance, margin_used, unrealized_pnl, realized_pnl
                 FROM account_snapshots
                 ORDER BY exchange, account_id, ts DESC",
                &[],
            )
            .await?;
        Ok(rows
            .into_iter()
            .map(|r| AccountSnapshotRead {
                exchange: r.get(0),
                account_id: r.get(1),
                ts: r.get(2),
                equity: r.get(3),
                balance: r.get(4),
                margin_used: r.get(5),
                unrealized_pnl: r.get(6),
                realized_pnl: r.get(7),
            })
            .collect())
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

pub async fn run_reconciliation_once(
    repository: &AccountRepository,
    config: ReconcileJobConfig,
) -> anyhow::Result<ReconcileRunSummary> {
    let now = Utc::now();
    let snapshots = repository.latest_snapshots_all().await?;
    let mut summary = ReconcileRunSummary {
        total_accounts: snapshots.len(),
        ok: 0,
        stale_snapshot: 0,
        drift_exceeded: 0,
    };

    for snapshot in snapshots {
        let event = evaluate_snapshot(snapshot, now, config);
        match event.status.as_str() {
            "OK" => summary.ok += 1,
            "STALE_SNAPSHOT" => summary.stale_snapshot += 1,
            "DRIFT_EXCEEDED" => summary.drift_exceeded += 1,
            _ => {}
        }
        repository.record_reconcile(&event).await?;
    }

    Ok(summary)
}

fn evaluate_snapshot(
    snapshot: AccountSnapshotRead,
    now: DateTime<Utc>,
    config: ReconcileJobConfig,
) -> ReconcileWrite {
    let staleness_cutoff = now - Duration::seconds(config.max_snapshot_age_secs.max(0));
    if snapshot.ts < staleness_cutoff {
        return ReconcileWrite {
            exchange: snapshot.exchange,
            account_id: snapshot.account_id,
            ts: now,
            status: "STALE_SNAPSHOT".to_string(),
            drift_notional: 0.0,
            notes: format!(
                "latest snapshot is older than {} seconds",
                config.max_snapshot_age_secs.max(0)
            ),
        };
    }

    let expected_equity = snapshot.balance + snapshot.unrealized_pnl + snapshot.realized_pnl;
    let drift_notional = (snapshot.equity - expected_equity).abs();
    if drift_notional > config.max_drift_notional {
        return ReconcileWrite {
            exchange: snapshot.exchange,
            account_id: snapshot.account_id,
            ts: now,
            status: "DRIFT_EXCEEDED".to_string(),
            drift_notional,
            notes: format!(
                "equity mismatch above threshold {:.4}",
                config.max_drift_notional
            ),
        };
    }

    ReconcileWrite {
        exchange: snapshot.exchange,
        account_id: snapshot.account_id,
        ts: now,
        status: "OK".to_string(),
        drift_notional,
        notes: "reconciliation passed".to_string(),
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

#[derive(Debug, Clone, Serialize)]
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

#[derive(Debug, Clone, Serialize)]
pub struct ReconcileRead {
    pub exchange: String,
    pub account_id: String,
    pub ts: DateTime<Utc>,
    pub status: String,
    pub drift_notional: f64,
    pub notes: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReconcileRunSummary {
    pub total_accounts: usize,
    pub ok: usize,
    pub stale_snapshot: usize,
    pub drift_exceeded: usize,
}

#[derive(Debug, Deserialize)]
struct AccountQuery {
    exchange: String,
    account_id: String,
}

pub fn build_router(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);
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
        .route("/v1/account/reconcile/run", post(run_reconcile_now))
        .layer(cors)
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

async fn run_reconcile_now(State(state): State<AppState>) -> Result<impl IntoResponse, ApiError> {
    let summary = run_reconciliation_once(
        state.repository.as_ref(),
        ReconcileJobConfig {
            max_snapshot_age_secs: 120,
            max_drift_notional: 25.0,
        },
    )
    .await
    .map_err(|error| ApiError(error.to_string()))?;
    Ok(Json(serde_json::json!({ "summary": summary })))
}

#[cfg(test)]
mod tests {
    use super::{evaluate_snapshot, AccountSnapshotRead, ReconcileJobConfig};
    use chrono::{Duration, Utc};

    #[test]
    fn evaluate_snapshot_marks_stale() {
        let now = Utc::now();
        let snapshot = AccountSnapshotRead {
            exchange: "kraken_futures".to_string(),
            account_id: "acct1".to_string(),
            ts: now - Duration::seconds(300),
            equity: 1000.0,
            balance: 900.0,
            margin_used: 100.0,
            unrealized_pnl: 100.0,
            realized_pnl: 0.0,
        };
        let event = evaluate_snapshot(
            snapshot,
            now,
            ReconcileJobConfig {
                max_snapshot_age_secs: 120,
                max_drift_notional: 25.0,
            },
        );
        assert_eq!(event.status, "STALE_SNAPSHOT");
    }

    #[test]
    fn evaluate_snapshot_marks_drift_exceeded() {
        let now = Utc::now();
        let snapshot = AccountSnapshotRead {
            exchange: "kraken_futures".to_string(),
            account_id: "acct1".to_string(),
            ts: now,
            equity: 1100.0,
            balance: 900.0,
            margin_used: 100.0,
            unrealized_pnl: 50.0,
            realized_pnl: 0.0,
        };
        let event = evaluate_snapshot(
            snapshot,
            now,
            ReconcileJobConfig {
                max_snapshot_age_secs: 120,
                max_drift_notional: 25.0,
            },
        );
        assert_eq!(event.status, "DRIFT_EXCEEDED");
    }
}
