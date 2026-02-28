use common_types::Timeframe;

#[derive(Debug, Clone, Copy)]
pub struct TimeframeDays {
    pub one_minute: u64,
    pub fifteen_minutes: u64,
    pub one_hour: u64,
}

impl TimeframeDays {
    pub fn days_for(self, timeframe: Timeframe) -> i64 {
        match timeframe {
            Timeframe::OneMinute => self.one_minute.max(1) as i64,
            Timeframe::FifteenMinutes => self.fifteen_minutes.max(1) as i64,
            Timeframe::OneHour => self.one_hour.max(1) as i64,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Settings {
    pub bind_addr: String,
    pub integrity_threshold_pct: f64,
    pub postgres_url: String,
    pub kraken_base_url: String,
    pub kraken_history_bounds_path: String,
    pub symbols: Vec<String>,
    pub backfill_interval_seconds: u64,
    pub backfill_window_days: TimeframeDays,
    pub candles_retention_days: TimeframeDays,
    pub candles_prune_interval_seconds: u64,
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
            .unwrap_or_else(|_| {
                "PF_XBTUSD,PF_ETHUSD,PF_SOLUSD,PF_XRPUSD,PF_ZECUSD,PF_DOGEUSD,PF_ADAUSD,PF_PEPEUSD,PF_SUIUSD,PF_AVAXUSD,PF_XAUTUSD,PF_TAOUSD,PF_LINKUSD,PF_BNBUSD,PF_HYPEUSD,PF_ARBUSD".to_string()
            })
            .split(',')
            .map(str::trim)
            .filter(|symbol| !symbol.is_empty())
            .map(ToString::to_string)
            .collect::<Vec<_>>();
        let backfill_interval_seconds = std::env::var("BACKFILL_INTERVAL_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(60);
        let backfill_window_days = TimeframeDays {
            one_minute: parse_env_u64("BACKFILL_WINDOW_DAYS_1M", 120).max(1),
            fifteen_minutes: parse_env_u64("BACKFILL_WINDOW_DAYS_15M", 540).max(1),
            one_hour: parse_env_u64("BACKFILL_WINDOW_DAYS_1H", 1_095).max(1),
        };
        let candles_retention_days = TimeframeDays {
            one_minute: parse_env_u64("CANDLES_RETENTION_DAYS_1M", 120).max(1),
            fifteen_minutes: parse_env_u64("CANDLES_RETENTION_DAYS_15M", 540).max(1),
            one_hour: parse_env_u64("CANDLES_RETENTION_DAYS_1H", 1_095).max(1),
        };
        let candles_prune_interval_seconds =
            parse_env_u64("CANDLES_PRUNE_INTERVAL_SECONDS", 3_600).max(60);

        Self {
            bind_addr: format!("0.0.0.0:{port}"),
            integrity_threshold_pct,
            postgres_url,
            kraken_base_url,
            kraken_history_bounds_path,
            symbols,
            backfill_interval_seconds,
            backfill_window_days,
            candles_retention_days,
            candles_prune_interval_seconds,
        }
    }
}

fn parse_env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}
