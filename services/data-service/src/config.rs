#[derive(Debug, Clone)]
pub struct Settings {
    pub bind_addr: String,
    pub integrity_threshold_pct: f64,
    pub postgres_url: String,
    pub kraken_base_url: String,
    pub kraken_history_bounds_path: String,
    pub symbols: Vec<String>,
    pub backfill_interval_seconds: u64,
}

impl Settings {
    pub fn from_env() -> Self {
        let port = std::env::var("DATA_SERVICE_PORT").unwrap_or_else(|_| "8080".to_string());
        let integrity_threshold_pct = std::env::var("DATA_INTEGRITY_THRESHOLD_PCT")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(99.5);
        let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
            "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
        });
        let kraken_base_url = std::env::var("KRAKEN_BASE_URL")
            .unwrap_or_else(|_| "https://futures.kraken.com".to_string());
        let kraken_history_bounds_path = std::env::var("KRAKEN_HISTORY_BOUNDS_PATH")
            .unwrap_or_else(|_| "infra/config/kraken_history_bounds.json".to_string());
        let symbols = std::env::var("KRAKEN_SYMBOLS")
            .unwrap_or_else(|_| "PI_XBTUSD,PI_ETHUSD".to_string())
            .split(',')
            .map(str::trim)
            .filter(|symbol| !symbol.is_empty())
            .map(ToString::to_string)
            .collect::<Vec<_>>();
        let backfill_interval_seconds = std::env::var("BACKFILL_INTERVAL_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(60);

        Self {
            bind_addr: format!("0.0.0.0:{port}"),
            integrity_threshold_pct,
            postgres_url,
            kraken_base_url,
            kraken_history_bounds_path,
            symbols,
            backfill_interval_seconds,
        }
    }
}
