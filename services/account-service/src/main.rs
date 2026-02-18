use account_service::{
    build_router, run_reconciliation_once, AccountRepository, AppState, ReconcileJobConfig,
};
use std::sync::Arc;
use tokio::net::TcpListener;
use tracing::info;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
        "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
    });
    let port = std::env::var("ACCOUNT_SERVICE_PORT").unwrap_or_else(|_| "8081".to_string());
    let reconcile_interval_secs = std::env::var("ACCOUNT_RECONCILE_INTERVAL_SECS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(60);
    let max_snapshot_age_secs = std::env::var("ACCOUNT_RECONCILE_MAX_SNAPSHOT_AGE_SECS")
        .ok()
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(120);
    let max_drift_notional = std::env::var("ACCOUNT_RECONCILE_MAX_DRIFT_NOTIONAL")
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(25.0);
    let bind_addr = format!("0.0.0.0:{port}");

    let repository = Arc::new(AccountRepository::connect(&postgres_url).await?);
    let reconcile_repo = repository.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(
            reconcile_interval_secs.max(1),
        ));
        loop {
            interval.tick().await;
            let config = ReconcileJobConfig {
                max_snapshot_age_secs,
                max_drift_notional,
            };
            match run_reconciliation_once(reconcile_repo.as_ref(), config).await {
                Ok(summary) => {
                    info!(
                        total_accounts = summary.total_accounts,
                        ok = summary.ok,
                        stale_snapshot = summary.stale_snapshot,
                        drift_exceeded = summary.drift_exceeded,
                        "account reconciliation tick complete"
                    );
                }
                Err(error) => {
                    tracing::error!(error = %error, "account reconciliation tick failed");
                }
            }
        }
    });

    let app = build_router(AppState { repository });
    let listener = TcpListener::bind(&bind_addr).await?;

    info!(
        bind_addr = %bind_addr,
        reconcile_interval_secs,
        max_snapshot_age_secs,
        max_drift_notional,
        "account-service started"
    );
    axum::serve(listener, app).await?;
    Ok(())
}
