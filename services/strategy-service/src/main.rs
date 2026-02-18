use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use common_types::Timeframe;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use strategy_service::{evaluate_pair, PairCue, PairEvaluationInput, PairEvaluationOutput};
use tokio::net::TcpListener;
use tokio_postgres::{types::ToSql, Client, NoTls};
use tracing::info;

#[derive(Clone)]
struct AppState {
    repository: Arc<StrategyRepository>,
    settings: Arc<StrategySettings>,
}

#[derive(Debug, Clone)]
struct PairSpec {
    left: String,
    right: String,
}

impl PairSpec {
    fn pair_id(&self) -> String {
        format!("{}__{}", self.left, self.right)
    }
}

#[derive(Debug, Clone)]
struct StrategySettings {
    bind_addr: String,
    postgres_url: String,
    pairs: Vec<PairSpec>,
    timeframes: Vec<Timeframe>,
    entry_band: f64,
    exit_band: f64,
    stop_band: f64,
    lookback_bars_1m: usize,
    lookback_bars_15m: usize,
    lookback_bars_1h: usize,
    hold_bars_1m: usize,
    hold_bars_15m: usize,
    hold_bars_1h: usize,
    max_half_life_bars_1m: f64,
    max_half_life_bars_15m: f64,
    max_half_life_bars_1h: f64,
    funding_drag_bps: f64,
    min_samples_target: usize,
    reopt_interval_secs: u64,
}

impl StrategySettings {
    fn from_env() -> Self {
        let port = std::env::var("STRATEGY_SERVICE_PORT").unwrap_or_else(|_| "8083".to_string());
        let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
            "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
        });

        let pairs_raw =
            std::env::var("STRATEGY_PAIRS").unwrap_or_else(|_| "PI_XBTUSD:PI_ETHUSD".to_string());
        let pairs = parse_pairs(&pairs_raw);
        let timeframes_raw =
            std::env::var("STRATEGY_TIMEFRAMES").unwrap_or_else(|_| "1m,15m,1h".to_string());
        let timeframes = parse_timeframes(&timeframes_raw);

        let entry_band = parse_env_f64("STRATEGY_ENTRY_BAND", 1.8);
        let exit_band = parse_env_f64("STRATEGY_EXIT_BAND", 0.6);
        let stop_band = parse_env_f64("STRATEGY_STOP_BAND", 3.2);
        let funding_drag_bps = parse_env_f64("STRATEGY_FUNDING_DRAG_BPS", 0.6);
        let min_samples_target = parse_env_usize("STRATEGY_MIN_SAMPLES_TARGET", 8);
        let reopt_interval_secs = parse_env_u64("STRATEGY_REOPT_INTERVAL_SECS", 3600);

        Self {
            bind_addr: format!("0.0.0.0:{port}"),
            postgres_url,
            pairs,
            timeframes,
            entry_band,
            exit_band,
            stop_band,
            lookback_bars_1m: parse_env_usize("STRATEGY_LOOKBACK_BARS_1M", 520),
            lookback_bars_15m: parse_env_usize("STRATEGY_LOOKBACK_BARS_15M", 720),
            lookback_bars_1h: parse_env_usize("STRATEGY_LOOKBACK_BARS_1H", 900),
            hold_bars_1m: parse_env_usize("STRATEGY_HOLD_BARS_1M", 20),
            hold_bars_15m: parse_env_usize("STRATEGY_HOLD_BARS_15M", 14),
            hold_bars_1h: parse_env_usize("STRATEGY_HOLD_BARS_1H", 10),
            max_half_life_bars_1m: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_1M", 120.0),
            max_half_life_bars_15m: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_15M", 90.0),
            max_half_life_bars_1h: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_1H", 72.0),
            funding_drag_bps,
            min_samples_target,
            reopt_interval_secs,
        }
    }

    fn lookback_bars(&self, timeframe: Timeframe) -> usize {
        match timeframe {
            Timeframe::OneMinute => self.lookback_bars_1m,
            Timeframe::FifteenMinutes => self.lookback_bars_15m,
            Timeframe::OneHour => self.lookback_bars_1h,
        }
    }

    fn hold_bars(&self, timeframe: Timeframe) -> usize {
        match timeframe {
            Timeframe::OneMinute => self.hold_bars_1m,
            Timeframe::FifteenMinutes => self.hold_bars_15m,
            Timeframe::OneHour => self.hold_bars_1h,
        }
    }

    fn max_half_life_bars(&self, timeframe: Timeframe) -> f64 {
        match timeframe {
            Timeframe::OneMinute => self.max_half_life_bars_1m,
            Timeframe::FifteenMinutes => self.max_half_life_bars_15m,
            Timeframe::OneHour => self.max_half_life_bars_1h,
        }
    }
}

#[derive(Clone)]
struct StrategyRepository {
    client: Arc<Client>,
}

#[derive(Debug, Clone)]
struct ClosePoint {
    ts: DateTime<Utc>,
    close: f64,
}

#[derive(Debug)]
struct PersistSummary {
    performance_rows_written: usize,
    selected_rows_written: usize,
}

impl StrategyRepository {
    async fn connect(connection_string: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(connection_string, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                tracing::error!(error = %error, "strategy-service postgres connection ended");
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
                "CREATE TABLE IF NOT EXISTS strategy_signal_performance (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal_variant TEXT NOT NULL,
                    window_end TIMESTAMPTZ NOT NULL,
                    sample_count INTEGER NOT NULL,
                    win_rate DOUBLE PRECISION NOT NULL,
                    edge_bps DOUBLE PRECISION NOT NULL,
                    reliability DOUBLE PRECISION NOT NULL,
                    regime TEXT NOT NULL,
                    opportunity_score DOUBLE PRECISION NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe, signal_variant, window_end)
                 );
                 CREATE TABLE IF NOT EXISTS strategy_selected_signal (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal_variant TEXT NOT NULL,
                    opportunity_score DOUBLE PRECISION NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe)
                 );",
            )
            .await?;
        Ok(())
    }

    async fn fetch_recent_closes(
        &self,
        instrument: &str,
        timeframe: Timeframe,
        limit: i64,
    ) -> anyhow::Result<Vec<ClosePoint>> {
        let mut rows = self
            .client
            .query(
                "SELECT ts, close
                 FROM candles
                 WHERE instrument=$1 AND timeframe=$2
                 ORDER BY ts DESC
                 LIMIT $3",
                &[&instrument, &timeframe.as_str(), &limit],
            )
            .await?
            .into_iter()
            .map(|row| ClosePoint {
                ts: row.get(0),
                close: row.get(1),
            })
            .collect::<Vec<_>>();
        rows.reverse();
        Ok(rows)
    }

    async fn record_evaluation(
        &self,
        timeframe: Timeframe,
        evaluation: &PairEvaluationOutput,
    ) -> anyhow::Result<PersistSummary> {
        let mut summary = PersistSummary {
            performance_rows_written: 0,
            selected_rows_written: 0,
        };

        for variant in &evaluation.variants {
            let rationale = variant.rationale_codes.join("|");
            let written = self
                .client
                .execute(
                    "INSERT INTO strategy_signal_performance
                     (pair_id, timeframe, signal_variant, window_end, sample_count, win_rate,
                      edge_bps, reliability, regime, opportunity_score, rationale)
                     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                     ON CONFLICT (pair_id, timeframe, signal_variant, window_end)
                     DO UPDATE SET
                       sample_count = EXCLUDED.sample_count,
                       win_rate = EXCLUDED.win_rate,
                       edge_bps = EXCLUDED.edge_bps,
                       reliability = EXCLUDED.reliability,
                       regime = EXCLUDED.regime,
                       opportunity_score = EXCLUDED.opportunity_score,
                       rationale = EXCLUDED.rationale",
                    &[
                        &evaluation.cue.pair_id as &(dyn ToSql + Sync),
                        &timeframe.as_str(),
                        &variant.variant,
                        &evaluation.cue.evaluated_at,
                        &(variant.sample_count as i32),
                        &variant.win_rate,
                        &variant.edge_bps,
                        &variant.reliability,
                        &evaluation.cue.regime,
                        &variant.opportunity_score,
                        &rationale,
                    ],
                )
                .await?;
            summary.performance_rows_written += written as usize;
        }

        let selected_written = self
            .client
            .execute(
                "INSERT INTO strategy_selected_signal
                 (pair_id, timeframe, signal_variant, opportunity_score, updated_at)
                 VALUES ($1,$2,$3,$4,$5)
                 ON CONFLICT (pair_id, timeframe)
                 DO UPDATE SET
                   signal_variant = EXCLUDED.signal_variant,
                   opportunity_score = EXCLUDED.opportunity_score,
                   updated_at = EXCLUDED.updated_at",
                &[
                    &evaluation.cue.pair_id as &(dyn ToSql + Sync),
                    &timeframe.as_str(),
                    &evaluation.cue.selected_variant,
                    &evaluation.cue.opportunity_score,
                    &evaluation.cue.evaluated_at,
                ],
            )
            .await?;
        summary.selected_rows_written += selected_written as usize;

        Ok(summary)
    }

    async fn fetch_selected_variant(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
    ) -> anyhow::Result<Option<String>> {
        let row = self
            .client
            .query_opt(
                "SELECT signal_variant
                 FROM strategy_selected_signal
                 WHERE pair_id=$1 AND timeframe=$2",
                &[&pair_id, &timeframe.as_str()],
            )
            .await?;
        Ok(row.map(|row| row.get(0)))
    }
}

#[derive(Debug, Deserialize)]
struct CuesQuery {
    timeframe: String,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct ReoptimizeRequest {
    timeframes: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug, Serialize)]
struct CueWithDiagnostics {
    cue: PairCue,
    variants: Vec<strategy_service::VariantEvaluation>,
    half_life_bars: f64,
    hedge_ratio: f64,
    hedge_ratio_stability: f64,
}

#[derive(Debug, Serialize)]
struct CuesResponse {
    timeframe: String,
    generated_at: DateTime<Utc>,
    cues: Vec<CueWithDiagnostics>,
    skipped: Vec<SkippedPair>,
}

#[derive(Debug, Serialize)]
struct SkippedPair {
    pair_id: String,
    reason: String,
}

#[derive(Debug, Serialize)]
struct ReoptimizeResponse {
    generated_at: DateTime<Utc>,
    timeframes: Vec<String>,
    pairs_processed: usize,
    cues_generated: usize,
    performance_rows_written: usize,
    selected_rows_written: usize,
    errors: Vec<ReoptError>,
}

#[derive(Debug, Serialize)]
struct ReoptError {
    pair_id: String,
    timeframe: String,
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

    let settings = Arc::new(StrategySettings::from_env());
    let repository = Arc::new(StrategyRepository::connect(&settings.postgres_url).await?);
    let state = AppState {
        repository,
        settings: settings.clone(),
    };

    let _worker = spawn_reoptimize_worker(state.clone());

    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/strategy/pairs/cues", get(pairs_cues))
        .route("/v1/strategy/pairs/reoptimize", post(reoptimize))
        .with_state(state);

    let listener = TcpListener::bind(&settings.bind_addr).await?;
    info!(
        bind_addr = %settings.bind_addr,
        pairs = ?settings.pairs.iter().map(|p| p.pair_id()).collect::<Vec<_>>(),
        timeframes = ?settings.timeframes.iter().map(|t| t.as_str()).collect::<Vec<_>>(),
        entry_band = settings.entry_band,
        exit_band = settings.exit_band,
        stop_band = settings.stop_band,
        reopt_interval_secs = settings.reopt_interval_secs,
        "strategy-service started"
    );

    axum::serve(listener, app).await?;
    Ok(())
}

fn spawn_reoptimize_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let interval_secs = state.settings.reopt_interval_secs.max(60);
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(interval_secs));
        loop {
            interval.tick().await;
            let mut pairs_processed = 0usize;
            let mut cues_generated = 0usize;
            let mut performance_rows_written = 0usize;
            let mut selected_rows_written = 0usize;

            for timeframe in &state.settings.timeframes {
                for pair in &state.settings.pairs {
                    pairs_processed += 1;
                    match evaluate_pair_for_timeframe(&state, pair, *timeframe).await {
                        Ok(output) => {
                            cues_generated += usize::from(output.cue.actionable);
                            match state
                                .repository
                                .record_evaluation(*timeframe, &output)
                                .await
                            {
                                Ok(summary) => {
                                    performance_rows_written += summary.performance_rows_written;
                                    selected_rows_written += summary.selected_rows_written;
                                }
                                Err(error) => {
                                    tracing::warn!(
                                        pair_id = %pair.pair_id(),
                                        timeframe = %timeframe.as_str(),
                                        error = %error,
                                        "failed to persist strategy evaluation"
                                    );
                                }
                            }
                        }
                        Err(error) => {
                            tracing::warn!(
                                pair_id = %pair.pair_id(),
                                timeframe = %timeframe.as_str(),
                                error = %error,
                                "strategy evaluation skipped"
                            );
                        }
                    }
                }
            }

            info!(
                pairs_processed,
                cues_generated,
                performance_rows_written,
                selected_rows_written,
                "strategy reoptimize tick complete"
            );
        }
    })
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn pairs_cues(
    State(state): State<AppState>,
    Query(query): Query<CuesQuery>,
) -> Result<Json<CuesResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let limit = query.limit.unwrap_or(20).clamp(1, 100);

    let mut cues = vec![];
    let mut skipped = vec![];

    for pair in &state.settings.pairs {
        match evaluate_pair_for_timeframe(&state, pair, timeframe).await {
            Ok(output) => {
                let preferred_variant = state
                    .repository
                    .fetch_selected_variant(&pair.pair_id(), timeframe)
                    .await
                    .map_err(|error| ApiError::Upstream(error.to_string()))?;

                let selected_matches = preferred_variant
                    .as_deref()
                    .map(|preferred| preferred == output.cue.selected_variant)
                    .unwrap_or(true);

                let mut cue = output.cue.clone();
                if !selected_matches {
                    cue.rationale_codes.push("CHAMPION_DRIFT".to_string());
                }

                cues.push(CueWithDiagnostics {
                    cue,
                    variants: output.variants,
                    half_life_bars: output.half_life_bars,
                    hedge_ratio: output.hedge_ratio,
                    hedge_ratio_stability: output.hedge_ratio_stability,
                });
            }
            Err(error) => skipped.push(SkippedPair {
                pair_id: pair.pair_id(),
                reason: error.to_string(),
            }),
        }
    }

    cues.sort_by(|left, right| {
        right
            .cue
            .opportunity_score
            .partial_cmp(&left.cue.opportunity_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    cues.truncate(limit);

    Ok(Json(CuesResponse {
        timeframe: timeframe.as_str().to_string(),
        generated_at: Utc::now(),
        cues,
        skipped,
    }))
}

async fn reoptimize(
    State(state): State<AppState>,
    Json(payload): Json<ReoptimizeRequest>,
) -> Result<Json<ReoptimizeResponse>, ApiError> {
    let requested_timeframes = if let Some(values) = payload.timeframes {
        let mut parsed = vec![];
        for value in values {
            if let Some(timeframe) = Timeframe::parse(&value) {
                parsed.push(timeframe);
            } else {
                return Err(ApiError::BadRequest(format!(
                    "invalid timeframe '{}' in reoptimize request",
                    value
                )));
            }
        }
        if parsed.is_empty() {
            state.settings.timeframes.clone()
        } else {
            parsed
        }
    } else {
        state.settings.timeframes.clone()
    };

    let mut pairs_processed = 0usize;
    let mut cues_generated = 0usize;
    let mut performance_rows_written = 0usize;
    let mut selected_rows_written = 0usize;
    let mut errors = vec![];

    for timeframe in &requested_timeframes {
        for pair in &state.settings.pairs {
            pairs_processed += 1;
            match evaluate_pair_for_timeframe(&state, pair, *timeframe).await {
                Ok(output) => {
                    cues_generated += usize::from(output.cue.actionable);
                    match state
                        .repository
                        .record_evaluation(*timeframe, &output)
                        .await
                    {
                        Ok(summary) => {
                            performance_rows_written += summary.performance_rows_written;
                            selected_rows_written += summary.selected_rows_written;
                        }
                        Err(error) => errors.push(ReoptError {
                            pair_id: pair.pair_id(),
                            timeframe: timeframe.as_str().to_string(),
                            error: error.to_string(),
                        }),
                    }
                }
                Err(error) => errors.push(ReoptError {
                    pair_id: pair.pair_id(),
                    timeframe: timeframe.as_str().to_string(),
                    error: error.to_string(),
                }),
            }
        }
    }

    Ok(Json(ReoptimizeResponse {
        generated_at: Utc::now(),
        timeframes: requested_timeframes
            .iter()
            .map(|timeframe| timeframe.as_str().to_string())
            .collect(),
        pairs_processed,
        cues_generated,
        performance_rows_written,
        selected_rows_written,
        errors,
    }))
}

async fn evaluate_pair_for_timeframe(
    state: &AppState,
    pair: &PairSpec,
    timeframe: Timeframe,
) -> anyhow::Result<PairEvaluationOutput> {
    let lookback = state.settings.lookback_bars(timeframe) as i64;
    let left = state
        .repository
        .fetch_recent_closes(&pair.left, timeframe, lookback)
        .await?;
    let right = state
        .repository
        .fetch_recent_closes(&pair.right, timeframe, lookback)
        .await?;

    let (timestamps, left_closes, right_closes) = align_closes(left, right);
    if timestamps.len() < 120 {
        return Err(anyhow::anyhow!(
            "insufficient aligned candles for pair={} timeframe={} bars={}",
            pair.pair_id(),
            timeframe.as_str(),
            timestamps.len()
        ));
    }

    evaluate_pair(PairEvaluationInput {
        pair_id: pair.pair_id(),
        left_instrument: pair.left.clone(),
        right_instrument: pair.right.clone(),
        timeframe,
        timestamps,
        left_closes,
        right_closes,
        entry_band: state.settings.entry_band,
        exit_band: state.settings.exit_band,
        stop_band: state.settings.stop_band,
        hold_bars: state.settings.hold_bars(timeframe),
        max_half_life_bars: state.settings.max_half_life_bars(timeframe),
        funding_drag_bps: state.settings.funding_drag_bps,
        min_samples_target: state.settings.min_samples_target,
    })
}

fn align_closes(
    left: Vec<ClosePoint>,
    right: Vec<ClosePoint>,
) -> (Vec<DateTime<Utc>>, Vec<f64>, Vec<f64>) {
    if left.is_empty() || right.is_empty() {
        return (vec![], vec![], vec![]);
    }

    let right_map = right
        .into_iter()
        .map(|point| (point.ts, point.close))
        .collect::<HashMap<_, _>>();

    let mut timestamps = vec![];
    let mut left_closes = vec![];
    let mut right_closes = vec![];
    for point in left {
        if let Some(right_close) = right_map.get(&point.ts) {
            timestamps.push(point.ts);
            left_closes.push(point.close);
            right_closes.push(*right_close);
        }
    }

    (timestamps, left_closes, right_closes)
}

fn parse_pairs(raw: &str) -> Vec<PairSpec> {
    let mut pairs = raw
        .split(',')
        .filter_map(|value| {
            let parts = value.split(':').map(str::trim).collect::<Vec<_>>();
            if parts.len() != 2 || parts[0].is_empty() || parts[1].is_empty() {
                return None;
            }
            Some(PairSpec {
                left: parts[0].to_string(),
                right: parts[1].to_string(),
            })
        })
        .collect::<Vec<_>>();

    if pairs.is_empty() {
        pairs.push(PairSpec {
            left: "PI_XBTUSD".to_string(),
            right: "PI_ETHUSD".to_string(),
        });
    }
    pairs
}

fn parse_timeframes(raw: &str) -> Vec<Timeframe> {
    let mut values = raw
        .split(',')
        .filter_map(|value| Timeframe::parse(value.trim()))
        .collect::<Vec<_>>();
    if values.is_empty() {
        values = vec![
            Timeframe::OneMinute,
            Timeframe::FifteenMinutes,
            Timeframe::OneHour,
        ];
    }
    values
}

fn parse_env_f64(key: &str, default: f64) -> f64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(default)
}

fn parse_env_usize(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(default)
}

fn parse_env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}
