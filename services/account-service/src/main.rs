use account_service::{build_router, AccountRepository, AppState};
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
    let bind_addr = format!("0.0.0.0:{port}");

    let repository = Arc::new(AccountRepository::connect(&postgres_url).await?);
    let app = build_router(AppState { repository });
    let listener = TcpListener::bind(&bind_addr).await?;

    info!(bind_addr = %bind_addr, "account-service started");
    axum::serve(listener, app).await?;
    Ok(())
}
