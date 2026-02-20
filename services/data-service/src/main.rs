use data_service::{
    build_router,
    config::Settings,
    repository::{MarketDataRepository, PostgresMarketDataRepository},
    worker::spawn_backfill_worker,
    ws_worker::spawn_trade_ingest_worker,
    AppState,
};
use kraken_adapter::{KrakenFuturesRestClient, KrakenHistoryBounds, MarketDataAdapter};
use std::sync::Arc;
use tokio::net::TcpListener;
use tracing::{info, warn};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();

    let settings = Settings::from_env();
    let repository: Arc<dyn MarketDataRepository> =
        Arc::new(PostgresMarketDataRepository::connect(&settings.postgres_url).await?);
    let history_bounds = KrakenHistoryBounds::from_file(&settings.kraken_history_bounds_path)
        .unwrap_or_else(|error| {
            warn!(
                path = %settings.kraken_history_bounds_path,
                error = %error,
                "failed loading configured history bounds; falling back to built-in defaults"
            );
            KrakenHistoryBounds::default()
        });
    let adapter: Arc<dyn MarketDataAdapter> = Arc::new(
        KrakenFuturesRestClient::new(settings.kraken_base_url.clone())
            .with_history_bounds(history_bounds),
    );
    let state = AppState {
        repository,
        adapter,
        integrity_threshold_pct: settings.integrity_threshold_pct,
    };
    let _backfill_worker = spawn_backfill_worker(
        state.clone(),
        settings.symbols.clone(),
        settings.backfill_interval_seconds,
    );
    let _trade_ingest_worker = spawn_trade_ingest_worker(state.clone(), settings.symbols.clone());

    let app = build_router(state);

    let listener = TcpListener::bind(&settings.bind_addr).await?;
    info!(
        bind_addr = %settings.bind_addr,
        postgres_url = %settings.postgres_url,
        kraken_base_url = %settings.kraken_base_url,
        kraken_history_bounds_path = %settings.kraken_history_bounds_path,
        symbols = ?settings.symbols,
        backfill_interval_seconds = settings.backfill_interval_seconds,
        integrity_threshold_pct = settings.integrity_threshold_pct,
        "data-service started"
    );

    axum::serve(listener, app).await?;
    Ok(())
}
