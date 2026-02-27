use axum::{
    extract::{Query, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use common_types::{
    kraken_perp_constraints, quantize_price_to_tick, InstrumentTradingConstraints, Timeframe,
};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use strategy_service::{
    annotate_with_shadow_model, apply_portfolio_plan_to_cues, build_portfolio_plan,
    compute_backtest_series, evaluate_cost_gate, evaluate_pair, train_shadow_model, BacktestConfig,
    BacktestExitMode, CandidateSetDiagnostics, CostGateInput, FundingModel, PairCue,
    PairEvaluationInput, PairEvaluationOutput, PortfolioPlan, Regime, ShadowModelTrainingRow,
    SignalVariant,
};
use tokio::net::TcpListener;
use tokio::sync::RwLock;
use tokio_postgres::{types::ToSql, Client, NoTls};
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

#[derive(Clone)]
struct AppState {
    repository: Arc<StrategyRepository>,
    settings: Arc<StrategySettings>,
    http_client: reqwest::Client,
    sampled_slippage: Arc<SampledSlippageStore>,
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
    data_service_url: String,
    pairs: Vec<PairSpec>,
    timeframes: Vec<Timeframe>,
    entry_band: f64,
    exit_band: f64,
    stop_band: f64,
    lookback_bars_1m: usize,
    lookback_bars_15m: usize,
    lookback_bars_1h: usize,
    paper_trade_persist_bars: usize,
    hold_bars_1m: usize,
    hold_bars_15m: usize,
    hold_bars_1h: usize,
    max_half_life_bars_1m: f64,
    max_half_life_bars_15m: f64,
    max_half_life_bars_1h: f64,
    funding_drag_bps: f64,
    min_samples_target: usize,
    reopt_interval_secs: u64,
    shadow_ml_min_rows: usize,
    shadow_ml_training_limit: usize,
    trading_fee_bps: f64,
    slippage_base_bps: f64,
    slippage_vol_multiplier: f64,
    slippage_z_multiplier: f64,
    sampled_slippage_interval_ms: u64,
    sampled_slippage_warmup_secs: u64,
    sampled_slippage_stale_secs: u64,
    sampled_slippage_ewma_alpha: f64,
    sampled_slippage_state_path: String,
    sampled_slippage_persist_secs: u64,
    sampled_slippage_bootstrap_max_deviation_bps: f64,
    min_net_edge_bps: f64,
    dynamic_funding_enabled: bool,
    funding_interval_secs: u64,
    funding_phase_offset_secs: i64,
    funding_rate_bps_multiplier: f64,
    funding_positive_rate_means_longs_pay: bool,
    funding_rate_input_mode: FundingRateInputMode,
    advisory_gross_cap: f64,
    advisory_per_pair_cap: f64,
    advisory_enabled: bool,
    champion_switch_min_delta: f64,
    block_on_champion_drift: bool,
    research_sweep_execution_cap: usize,
    research_sweep_top_k: usize,
    maintenance_report_path: String,
    maintenance_artifacts_root: String,
    maintenance_apply_script_path: String,
    maintenance_env_file_path: String,
    maintenance_deploy_script_path: String,
    maintenance_action_output_root: String,
    maintenance_action_queue_root: String,
    maintenance_action_timeout_secs: u64,
    maintenance_action_skip_pull: bool,
    ui_access_password: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FundingRateInputMode {
    Fraction,
    Percent,
    Bps,
    Auto,
}

impl FundingRateInputMode {
    fn parse(raw: Option<String>) -> Self {
        match raw
            .as_deref()
            .unwrap_or("auto")
            .trim()
            .to_ascii_lowercase()
            .as_str()
        {
            "fraction" => Self::Fraction,
            "percent" => Self::Percent,
            "bps" | "basis_points" | "basis-points" => Self::Bps,
            _ => Self::Auto,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Fraction => "fraction",
            Self::Percent => "percent",
            Self::Bps => "bps",
            Self::Auto => "auto",
        }
    }
}

impl StrategySettings {
    fn from_env() -> Self {
        let port = std::env::var("STRATEGY_SERVICE_PORT").unwrap_or_else(|_| "8083".to_string());
        let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
            "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
        });
        let data_service_url = std::env::var("STRATEGY_DATA_SERVICE_URL")
            .unwrap_or_else(|_| "http://data-service:8080".to_string());

        let pairs_raw =
            std::env::var("STRATEGY_PAIRS").unwrap_or_else(|_| {
                "PF_XBTUSD:PF_ETHUSD,PF_XBTUSD:PF_SOLUSD,PF_XBTUSD:PF_XRPUSD,PF_XBTUSD:PF_ADAUSD,PF_XBTUSD:PF_DOGEUSD,PF_XBTUSD:PF_AVAXUSD,PF_XBTUSD:PF_BNBUSD,PF_XBTUSD:PF_LINKUSD,PF_ETHUSD:PF_SOLUSD,PF_ETHUSD:PF_XRPUSD,PF_ETHUSD:PF_ADAUSD,PF_SOLUSD:PF_AVAXUSD,PF_XRPUSD:PF_ADAUSD,PF_DOGEUSD:PF_PEPEUSD,PF_SUIUSD:PF_ARBUSD,PF_TAOUSD:PF_HYPEUSD".to_string()
            });
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
        let shadow_ml_min_rows = parse_env_usize("STRATEGY_SHADOW_ML_MIN_ROWS", 64);
        let shadow_ml_training_limit = parse_env_usize("STRATEGY_SHADOW_ML_TRAINING_LIMIT", 1200);
        let trading_fee_bps = parse_env_f64("STRATEGY_TRADING_FEE_BPS", 1.2);
        let slippage_base_bps = parse_env_f64("STRATEGY_SLIPPAGE_BASE_BPS", 0.8);
        let slippage_vol_multiplier = parse_env_f64("STRATEGY_SLIPPAGE_VOL_MULTIPLIER", 0.45);
        let slippage_z_multiplier = parse_env_f64("STRATEGY_SLIPPAGE_Z_MULTIPLIER", 0.20);
        let sampled_slippage_interval_ms =
            parse_env_u64("STRATEGY_SAMPLED_SLIPPAGE_INTERVAL_MS", 1000);
        let sampled_slippage_warmup_secs =
            parse_env_u64("STRATEGY_SAMPLED_SLIPPAGE_WARMUP_SECS", 300);
        let sampled_slippage_stale_secs = parse_env_u64("STRATEGY_SAMPLED_SLIPPAGE_STALE_SECS", 20);
        let sampled_slippage_ewma_alpha =
            parse_env_f64("STRATEGY_SAMPLED_SLIPPAGE_EWMA_ALPHA", 0.2).clamp(0.01, 1.0);
        let sampled_slippage_state_path = std::env::var("STRATEGY_SAMPLED_SLIPPAGE_STATE_PATH")
            .unwrap_or_else(|_| "artifacts/runtime/sampled_slippage_state.json".to_string());
        let sampled_slippage_persist_secs =
            parse_env_u64("STRATEGY_SAMPLED_SLIPPAGE_PERSIST_SECS", 5).max(1);
        let sampled_slippage_bootstrap_max_deviation_bps =
            parse_env_f64("STRATEGY_SAMPLED_SLIPPAGE_BOOTSTRAP_MAX_DEVIATION_BPS", 3.0).max(0.0);
        let min_net_edge_bps = parse_env_f64("STRATEGY_MIN_NET_EDGE_BPS", 0.0);
        let dynamic_funding_enabled = parse_env_bool("STRATEGY_DYNAMIC_FUNDING_ENABLED", true);
        let funding_interval_secs = parse_env_u64("STRATEGY_FUNDING_INTERVAL_SECS", 3600).max(1);
        let funding_phase_offset_secs = parse_env_i64("STRATEGY_FUNDING_PHASE_OFFSET_SECS", 0);
        let funding_rate_bps_multiplier =
            parse_env_f64("STRATEGY_FUNDING_RATE_BPS_MULTIPLIER", 10_000.0).max(1.0);
        let funding_positive_rate_means_longs_pay =
            parse_env_bool("STRATEGY_FUNDING_POSITIVE_RATE_MEANS_LONGS_PAY", true);
        let funding_rate_input_mode =
            FundingRateInputMode::parse(std::env::var("STRATEGY_FUNDING_RATE_INPUT_MODE").ok());
        let advisory_gross_cap = parse_env_f64("STRATEGY_ADVISORY_GROSS_CAP", 1.0);
        let advisory_per_pair_cap = parse_env_f64("STRATEGY_ADVISORY_PER_PAIR_CAP", 0.35);
        let advisory_enabled = parse_env_bool("STRATEGY_ADVISORY_ENABLED", true);
        let champion_switch_min_delta = parse_env_f64("STRATEGY_CHAMPION_SWITCH_MIN_DELTA", 0.25);
        let block_on_champion_drift = parse_env_bool("STRATEGY_BLOCK_ON_CHAMPION_DRIFT", true);
        let research_sweep_execution_cap =
            parse_env_usize("STRATEGY_RESEARCH_SWEEP_EXECUTION_CAP", 20_000).clamp(1, 1_000_000);
        let research_sweep_top_k =
            parse_env_usize("STRATEGY_RESEARCH_SWEEP_TOP_K", 10).clamp(1, 100);
        let maintenance_report_path = std::env::var("STRATEGY_MAINTENANCE_REPORT_PATH")
            .unwrap_or_else(|_| {
                "artifacts/strategy_tuning/latest_maintenance_report.json".to_string()
            });
        let maintenance_artifacts_root = std::env::var("STRATEGY_MAINTENANCE_ARTIFACT_ROOT")
            .unwrap_or_else(|_| "artifacts/strategy_tuning".to_string());
        let maintenance_apply_script_path = std::env::var("STRATEGY_MAINTENANCE_APPLY_SCRIPT_PATH")
            .unwrap_or_else(|_| "tools/scripts/strategy_tuning_apply.py".to_string());
        let maintenance_env_file_path = std::env::var("STRATEGY_MAINTENANCE_ENV_FILE_PATH")
            .unwrap_or_else(|_| ".env.hosted".to_string());
        let maintenance_deploy_script_path =
            std::env::var("STRATEGY_MAINTENANCE_DEPLOY_SCRIPT_PATH")
                .unwrap_or_else(|_| "scripts/deploy.sh".to_string());
        let maintenance_action_output_root =
            std::env::var("STRATEGY_MAINTENANCE_ACTION_OUTPUT_ROOT")
                .unwrap_or_else(|_| "artifacts/strategy_tuning/manual_actions".to_string());
        let maintenance_action_queue_root = std::env::var("STRATEGY_MAINTENANCE_ACTION_QUEUE_ROOT")
            .unwrap_or_else(|_| "artifacts/strategy_tuning/manual_action_queue".to_string());
        let maintenance_action_timeout_secs =
            parse_env_u64("STRATEGY_MAINTENANCE_ACTION_TIMEOUT_SECS", 300);
        let maintenance_action_skip_pull =
            parse_env_bool("STRATEGY_MAINTENANCE_ACTION_SKIP_PULL", true);
        let ui_access_password =
            std::env::var("STRATEGY_UI_ACCESS_PASSWORD").unwrap_or_else(|_| "".to_string());

        Self {
            bind_addr: format!("0.0.0.0:{port}"),
            postgres_url,
            data_service_url,
            pairs,
            timeframes,
            entry_band,
            exit_band,
            stop_band,
            lookback_bars_1m: parse_env_usize("STRATEGY_LOOKBACK_BARS_1M", 520),
            lookback_bars_15m: parse_env_usize("STRATEGY_LOOKBACK_BARS_15M", 720),
            lookback_bars_1h: parse_env_usize("STRATEGY_LOOKBACK_BARS_1H", 900),
            paper_trade_persist_bars: parse_env_usize("STRATEGY_PAPER_TRADE_PERSIST_BARS", 5000),
            hold_bars_1m: parse_env_usize("STRATEGY_HOLD_BARS_1M", 20),
            hold_bars_15m: parse_env_usize("STRATEGY_HOLD_BARS_15M", 14),
            hold_bars_1h: parse_env_usize("STRATEGY_HOLD_BARS_1H", 10),
            max_half_life_bars_1m: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_1M", 120.0),
            max_half_life_bars_15m: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_15M", 90.0),
            max_half_life_bars_1h: parse_env_f64("STRATEGY_MAX_HALF_LIFE_BARS_1H", 72.0),
            funding_drag_bps,
            min_samples_target,
            reopt_interval_secs,
            shadow_ml_min_rows,
            shadow_ml_training_limit,
            trading_fee_bps,
            slippage_base_bps,
            slippage_vol_multiplier,
            slippage_z_multiplier,
            sampled_slippage_interval_ms,
            sampled_slippage_warmup_secs,
            sampled_slippage_stale_secs,
            sampled_slippage_ewma_alpha,
            sampled_slippage_state_path,
            sampled_slippage_persist_secs,
            sampled_slippage_bootstrap_max_deviation_bps,
            min_net_edge_bps,
            dynamic_funding_enabled,
            funding_interval_secs,
            funding_phase_offset_secs,
            funding_rate_bps_multiplier,
            funding_positive_rate_means_longs_pay,
            funding_rate_input_mode,
            advisory_gross_cap,
            advisory_per_pair_cap,
            advisory_enabled,
            champion_switch_min_delta,
            block_on_champion_drift,
            research_sweep_execution_cap,
            research_sweep_top_k,
            maintenance_report_path,
            maintenance_artifacts_root,
            maintenance_apply_script_path,
            maintenance_env_file_path,
            maintenance_deploy_script_path,
            maintenance_action_output_root,
            maintenance_action_queue_root,
            maintenance_action_timeout_secs,
            maintenance_action_skip_pull,
            ui_access_password,
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

    fn ui_access_enabled(&self) -> bool {
        !self.ui_access_password.trim().is_empty()
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

#[derive(Debug, Clone)]
struct SelectedSignalRow {
    signal_variant: String,
    opportunity_score: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ChampionDecision {
    Initialize,
    Unchanged,
    PromoteChallenger,
    KeepChampion,
}

impl ChampionDecision {
    fn as_str(self) -> &'static str {
        match self {
            Self::Initialize => "INITIALIZE",
            Self::Unchanged => "UNCHANGED",
            Self::PromoteChallenger => "PROMOTE_CHALLENGER",
            Self::KeepChampion => "KEEP_CHAMPION",
        }
    }
}

#[derive(Debug, Clone)]
struct ChampionTransition {
    selected_variant: String,
    selected_score: f64,
    champion_variant: String,
    challenger_variant: String,
    champion_score: f64,
    challenger_score: f64,
    score_delta: f64,
    decision: ChampionDecision,
}

#[derive(Debug)]
struct PersistSummary {
    performance_rows_written: usize,
    selected_rows_written: usize,
    drift_rows_written: usize,
    champion_promotions: usize,
    champion_locks: usize,
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
                    score_last DOUBLE PRECISION NOT NULL,
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
                 );
                 ALTER TABLE strategy_signal_performance
                 ADD COLUMN IF NOT EXISTS score_last DOUBLE PRECISION NOT NULL DEFAULT 0;
                 CREATE TABLE IF NOT EXISTS strategy_shadow_model_runs (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    run_at TIMESTAMPTZ NOT NULL,
                    model_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    training_rows INTEGER NOT NULL,
                    positive_rate DOUBLE PRECISION NOT NULL,
                    precision DOUBLE PRECISION NOT NULL,
                    brier_score DOUBLE PRECISION NOT NULL,
                    recommended_variant TEXT NOT NULL,
                    recommended_probability DOUBLE PRECISION NOT NULL,
                    agrees_with_selected BOOLEAN NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe, run_at)
                 );
                 CREATE TABLE IF NOT EXISTS strategy_champion_drift_events (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_at TIMESTAMPTZ NOT NULL,
                    champion_variant TEXT NOT NULL,
                    challenger_variant TEXT NOT NULL,
                    champion_score DOUBLE PRECISION NOT NULL,
                    challenger_score DOUBLE PRECISION NOT NULL,
                    score_delta DOUBLE PRECISION NOT NULL,
                    decision TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe, event_at)
                 );
                 CREATE TABLE IF NOT EXISTS strategy_opportunity_history (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    evaluated_at TIMESTAMPTZ NOT NULL,
                    left_instrument TEXT NOT NULL,
                    right_instrument TEXT NOT NULL,
                    selected_variant TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    direction_hint TEXT NOT NULL,
                    spread_z DOUBLE PRECISION NOT NULL,
                    opportunity_score DOUBLE PRECISION NOT NULL,
                    net_edge_bps DOUBLE PRECISION NOT NULL,
                    cost_gate_pass BOOLEAN NOT NULL,
                    actionable BOOLEAN NOT NULL,
                    rationale_codes TEXT NOT NULL DEFAULT '',
                    cost_gate_rationale_codes TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe, evaluated_at)
                 );
                 CREATE TABLE IF NOT EXISTS strategy_paper_trades (
                    pair_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    exit_mode TEXT NOT NULL,
                    left_instrument TEXT NOT NULL,
                    right_instrument TEXT NOT NULL,
                    selected_variant TEXT NOT NULL,
                    entry_ts TIMESTAMPTZ NOT NULL,
                    exit_ts TIMESTAMPTZ NOT NULL,
                    bars_held INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    exit_kind TEXT NOT NULL,
                    entry_z DOUBLE PRECISION NOT NULL,
                    exit_z DOUBLE PRECISION NOT NULL,
                    entry_index INTEGER NOT NULL,
                    exit_index INTEGER NOT NULL,
                    left_entry DOUBLE PRECISION NOT NULL,
                    left_exit DOUBLE PRECISION NOT NULL,
                    right_entry DOUBLE PRECISION NOT NULL,
                    right_exit DOUBLE PRECISION NOT NULL,
                    left_leg_bps DOUBLE PRECISION NOT NULL,
                    right_leg_bps DOUBLE PRECISION NOT NULL,
                    gross_bps DOUBLE PRECISION NOT NULL,
                    round_trip_cost_bps DOUBLE PRECISION NOT NULL,
                    net_bps DOUBLE PRECISION NOT NULL,
                    equity_pre_entry DOUBLE PRECISION NOT NULL,
                    equity_exit DOUBLE PRECISION NOT NULL,
                    equity_trade_bps DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (pair_id, timeframe, exit_mode, entry_ts, exit_ts, exit_kind)
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
        champion_switch_min_delta: f64,
    ) -> anyhow::Result<PersistSummary> {
        let mut summary = PersistSummary {
            performance_rows_written: 0,
            selected_rows_written: 0,
            drift_rows_written: 0,
            champion_promotions: 0,
            champion_locks: 0,
        };

        for variant in &evaluation.variants {
            let rationale = variant.rationale_codes.join("|");
            let written = self
                .client
                .execute(
                    "INSERT INTO strategy_signal_performance
                     (pair_id, timeframe, signal_variant, window_end, score_last, sample_count, win_rate,
                      edge_bps, reliability, regime, opportunity_score, rationale)
                     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                     ON CONFLICT (pair_id, timeframe, signal_variant, window_end)
                     DO UPDATE SET
                       score_last = EXCLUDED.score_last,
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
                        &variant.score_last,
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

        let existing = self
            .fetch_selected_signal(&evaluation.cue.pair_id, timeframe)
            .await?;
        let transition = decide_champion_transition(
            existing.as_ref(),
            evaluation,
            champion_switch_min_delta.max(0.0),
        );
        let selected_written = self
            .upsert_selected_signal(
                &evaluation.cue.pair_id,
                timeframe,
                &transition.selected_variant,
                transition.selected_score,
                evaluation.cue.evaluated_at,
            )
            .await?;
        summary.selected_rows_written += selected_written as usize;
        if transition.decision == ChampionDecision::PromoteChallenger {
            summary.champion_promotions += 1;
        }
        if transition.decision == ChampionDecision::KeepChampion {
            summary.champion_locks += 1;
        }
        if matches!(
            transition.decision,
            ChampionDecision::PromoteChallenger | ChampionDecision::KeepChampion
        ) {
            let drift_written = self
                .record_champion_drift_event(
                    &evaluation.cue.pair_id,
                    timeframe,
                    &transition,
                    evaluation.cue.evaluated_at,
                )
                .await?;
            summary.drift_rows_written += drift_written as usize;
        }

        Ok(summary)
    }

    async fn record_opportunity_history(
        &self,
        timeframe: Timeframe,
        evaluation: &PairEvaluationOutput,
    ) -> anyhow::Result<u64> {
        let rationale_codes = evaluation.cue.rationale_codes.join("|");
        let cost_gate_rationale_codes = evaluation.cue.cost_gate.rationale_codes.join("|");
        let written = self
            .client
            .execute(
                "INSERT INTO strategy_opportunity_history
                 (pair_id, timeframe, evaluated_at, left_instrument, right_instrument, selected_variant, regime,
                  direction_hint, spread_z, opportunity_score, net_edge_bps, cost_gate_pass, actionable,
                  rationale_codes, cost_gate_rationale_codes)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                 ON CONFLICT (pair_id, timeframe, evaluated_at)
                 DO UPDATE SET
                    left_instrument = EXCLUDED.left_instrument,
                    right_instrument = EXCLUDED.right_instrument,
                    selected_variant = EXCLUDED.selected_variant,
                    regime = EXCLUDED.regime,
                    direction_hint = EXCLUDED.direction_hint,
                    spread_z = EXCLUDED.spread_z,
                    opportunity_score = EXCLUDED.opportunity_score,
                    net_edge_bps = EXCLUDED.net_edge_bps,
                    cost_gate_pass = EXCLUDED.cost_gate_pass,
                    actionable = EXCLUDED.actionable,
                    rationale_codes = EXCLUDED.rationale_codes,
                    cost_gate_rationale_codes = EXCLUDED.cost_gate_rationale_codes",
                &[
                    &evaluation.cue.pair_id as &(dyn ToSql + Sync),
                    &timeframe.as_str(),
                    &evaluation.cue.evaluated_at,
                    &evaluation.cue.left_instrument,
                    &evaluation.cue.right_instrument,
                    &evaluation.cue.selected_variant,
                    &evaluation.cue.regime,
                    &evaluation.cue.direction_hint,
                    &evaluation.cue.spread_z,
                    &evaluation.cue.opportunity_score,
                    &evaluation.cue.cost_gate.net_edge_bps,
                    &evaluation.cue.cost_gate.pass,
                    &evaluation.cue.actionable,
                    &rationale_codes,
                    &cost_gate_rationale_codes,
                ],
            )
            .await?;
        Ok(written)
    }

    async fn fetch_opportunity_history(
        &self,
        timeframe: Timeframe,
        since: DateTime<Utc>,
        only_pass: bool,
        limit: i64,
    ) -> anyhow::Result<Vec<OpportunityHistoryEntry>> {
        let rows = self
            .client
            .query(
                "SELECT pair_id, left_instrument, right_instrument, timeframe, selected_variant, regime,
                        direction_hint, spread_z, opportunity_score, net_edge_bps, cost_gate_pass, actionable,
                        rationale_codes, cost_gate_rationale_codes, evaluated_at
                 FROM strategy_opportunity_history
                 WHERE timeframe=$1
                   AND evaluated_at >= $2
                   AND ($3 = FALSE OR (actionable = TRUE AND cost_gate_pass = TRUE))
                 ORDER BY evaluated_at DESC
                 LIMIT $4",
                &[&timeframe.as_str(), &since, &only_pass, &limit],
            )
            .await?;
        Ok(rows
            .into_iter()
            .map(|row| OpportunityHistoryEntry {
                pair_id: row.get(0),
                left_instrument: row.get(1),
                right_instrument: row.get(2),
                timeframe: row.get(3),
                selected_variant: row.get(4),
                regime: row.get(5),
                direction_hint: row.get(6),
                spread_z: row.get(7),
                opportunity_score: row.get(8),
                net_edge_bps: row.get(9),
                cost_gate_pass: row.get(10),
                actionable: row.get(11),
                rationale_codes: split_codes(row.get::<usize, String>(12)),
                cost_gate_rationale_codes: split_codes(row.get::<usize, String>(13)),
                evaluated_at: row.get(14),
            })
            .collect())
    }

    async fn fetch_opportunity_history_stats(
        &self,
        timeframe: Option<Timeframe>,
    ) -> anyhow::Result<Vec<OpportunityHistoryStatsEntry>> {
        let timeframe_filter = timeframe.map(|value| value.as_str().to_string());
        let rows = self
            .client
            .query(
                "SELECT timeframe,
                        COUNT(*) AS rows,
                        MIN(evaluated_at) AS first_evaluated_at,
                        MAX(evaluated_at) AS last_evaluated_at
                 FROM strategy_opportunity_history
                 WHERE ($1::text IS NULL OR timeframe = $1)
                 GROUP BY timeframe
                 ORDER BY timeframe",
                &[&timeframe_filter],
            )
            .await?;
        Ok(rows
            .into_iter()
            .map(|row| {
                let first: Option<DateTime<Utc>> = row.get(2);
                let last: Option<DateTime<Utc>> = row.get(3);
                OpportunityHistoryStatsEntry {
                    timeframe: row.get(0),
                    rows: row.get(1),
                    first_evaluated_at: first,
                    last_evaluated_at: last,
                    days_covered: days_covered(first, last),
                }
            })
            .collect())
    }

    async fn replace_paper_trades(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
        exit_mode: &str,
        rows: &[PaperTradeInsertRow],
    ) -> anyhow::Result<u64> {
        self.client
            .execute(
                "DELETE FROM strategy_paper_trades
                 WHERE pair_id = $1
                   AND timeframe = $2
                   AND exit_mode = $3",
                &[&pair_id, &timeframe.as_str(), &exit_mode],
            )
            .await?;

        let mut total_written = 0u64;
        for row in rows {
            let written = self
                .client
                .execute(
                    "INSERT INTO strategy_paper_trades
                     (pair_id, timeframe, exit_mode, left_instrument, right_instrument, selected_variant,
                      entry_ts, exit_ts, bars_held, direction, exit_kind, entry_z, exit_z, entry_index, exit_index,
                      left_entry, left_exit, right_entry, right_exit, left_leg_bps, right_leg_bps, gross_bps,
                      round_trip_cost_bps, net_bps, equity_pre_entry, equity_exit, equity_trade_bps)
                     VALUES
                     ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
                     ON CONFLICT (pair_id, timeframe, exit_mode, entry_ts, exit_ts, exit_kind)
                     DO UPDATE SET
                       left_instrument = EXCLUDED.left_instrument,
                       right_instrument = EXCLUDED.right_instrument,
                       selected_variant = EXCLUDED.selected_variant,
                       bars_held = EXCLUDED.bars_held,
                       direction = EXCLUDED.direction,
                       entry_z = EXCLUDED.entry_z,
                       exit_z = EXCLUDED.exit_z,
                       entry_index = EXCLUDED.entry_index,
                       exit_index = EXCLUDED.exit_index,
                       left_entry = EXCLUDED.left_entry,
                       left_exit = EXCLUDED.left_exit,
                       right_entry = EXCLUDED.right_entry,
                       right_exit = EXCLUDED.right_exit,
                       left_leg_bps = EXCLUDED.left_leg_bps,
                       right_leg_bps = EXCLUDED.right_leg_bps,
                       gross_bps = EXCLUDED.gross_bps,
                       round_trip_cost_bps = EXCLUDED.round_trip_cost_bps,
                       net_bps = EXCLUDED.net_bps,
                       equity_pre_entry = EXCLUDED.equity_pre_entry,
                       equity_exit = EXCLUDED.equity_exit,
                       equity_trade_bps = EXCLUDED.equity_trade_bps,
                       updated_at = NOW()",
                    &[
                        &row.pair_id as &(dyn ToSql + Sync),
                        &row.timeframe,
                        &row.exit_mode,
                        &row.left_instrument,
                        &row.right_instrument,
                        &row.selected_variant,
                        &row.entry_ts,
                        &row.exit_ts,
                        &row.bars_held,
                        &row.direction,
                        &row.exit_kind,
                        &row.entry_z,
                        &row.exit_z,
                        &row.entry_index,
                        &row.exit_index,
                        &row.left_entry,
                        &row.left_exit,
                        &row.right_entry,
                        &row.right_exit,
                        &row.left_leg_bps,
                        &row.right_leg_bps,
                        &row.gross_bps,
                        &row.round_trip_cost_bps,
                        &row.net_bps,
                        &row.equity_pre_entry,
                        &row.equity_exit,
                        &row.equity_trade_bps,
                    ],
                )
                .await?;
            total_written += written;
        }
        Ok(total_written)
    }

    async fn fetch_paper_trades(
        &self,
        timeframe: Timeframe,
        pair_id: Option<&str>,
        exit_mode: &str,
        since: DateTime<Utc>,
        limit: i64,
    ) -> anyhow::Result<Vec<PaperTradeEntry>> {
        let pair_filter = pair_id.map(str::to_string);
        let rows = self
            .client
            .query(
                "SELECT pair_id, timeframe, exit_mode, left_instrument, right_instrument, selected_variant,
                        entry_ts, exit_ts, bars_held, direction, exit_kind, entry_z, exit_z, entry_index, exit_index,
                        left_entry, left_exit, right_entry, right_exit, left_leg_bps, right_leg_bps, gross_bps,
                        round_trip_cost_bps, net_bps, equity_pre_entry, equity_exit, equity_trade_bps,
                        created_at, updated_at
                 FROM strategy_paper_trades
                 WHERE timeframe=$1
                   AND ($2::text IS NULL OR pair_id = $2)
                   AND exit_mode = $3
                   AND exit_ts >= $4
                 ORDER BY exit_ts DESC
                 LIMIT $5",
                &[&timeframe.as_str(), &pair_filter, &exit_mode, &since, &limit],
            )
            .await?;
        Ok(rows
            .into_iter()
            .map(|row| PaperTradeEntry {
                pair_id: row.get(0),
                timeframe: row.get(1),
                exit_mode: row.get(2),
                left_instrument: row.get(3),
                right_instrument: row.get(4),
                selected_variant: row.get(5),
                entry_ts: row.get(6),
                exit_ts: row.get(7),
                bars_held: row.get(8),
                direction: row.get(9),
                exit_kind: row.get(10),
                entry_z: row.get(11),
                exit_z: row.get(12),
                entry_index: row.get(13),
                exit_index: row.get(14),
                left_entry: row.get(15),
                left_exit: row.get(16),
                right_entry: row.get(17),
                right_exit: row.get(18),
                left_leg_bps: row.get(19),
                right_leg_bps: row.get(20),
                gross_bps: row.get(21),
                round_trip_cost_bps: row.get(22),
                net_bps: row.get(23),
                equity_pre_entry: row.get(24),
                equity_exit: row.get(25),
                equity_trade_bps: row.get(26),
                created_at: row.get(27),
                updated_at: row.get(28),
            })
            .collect())
    }

    async fn upsert_selected_signal(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
        selected_variant: &str,
        selected_score: f64,
        evaluated_at: DateTime<Utc>,
    ) -> anyhow::Result<u64> {
        let written = self
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
                    &pair_id as &(dyn ToSql + Sync),
                    &timeframe.as_str(),
                    &selected_variant,
                    &selected_score,
                    &evaluated_at,
                ],
            )
            .await?;
        Ok(written)
    }

    async fn record_champion_drift_event(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
        transition: &ChampionTransition,
        event_at: DateTime<Utc>,
    ) -> anyhow::Result<u64> {
        let written = self
            .client
            .execute(
                "INSERT INTO strategy_champion_drift_events
                 (pair_id, timeframe, event_at, champion_variant, challenger_variant, champion_score,
                  challenger_score, score_delta, decision)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                 ON CONFLICT (pair_id, timeframe, event_at)
                 DO UPDATE SET
                    champion_variant = EXCLUDED.champion_variant,
                    challenger_variant = EXCLUDED.challenger_variant,
                    champion_score = EXCLUDED.champion_score,
                    challenger_score = EXCLUDED.challenger_score,
                    score_delta = EXCLUDED.score_delta,
                    decision = EXCLUDED.decision",
                &[
                    &pair_id as &(dyn ToSql + Sync),
                    &timeframe.as_str(),
                    &event_at,
                    &transition.champion_variant,
                    &transition.challenger_variant,
                    &transition.champion_score,
                    &transition.challenger_score,
                    &transition.score_delta,
                    &transition.decision.as_str(),
                ],
            )
            .await?;
        Ok(written)
    }

    async fn fetch_shadow_training_rows(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
        limit: i64,
    ) -> anyhow::Result<Vec<ShadowModelTrainingRow>> {
        let rows = self
            .client
            .query(
                "SELECT signal_variant, regime, score_last, sample_count, win_rate, reliability, edge_bps
                 FROM strategy_signal_performance
                 WHERE pair_id=$1 AND timeframe=$2
                 ORDER BY window_end DESC
                 LIMIT $3",
                &[&pair_id, &timeframe.as_str(), &limit],
            )
            .await?;

        let mut result = Vec::with_capacity(rows.len());
        for row in rows {
            let variant_raw: String = row.get(0);
            let regime_raw: String = row.get(1);
            let Some(variant) = SignalVariant::parse(&variant_raw) else {
                continue;
            };
            let Some(regime) = Regime::parse(&regime_raw) else {
                continue;
            };
            let sample_count: i32 = row.get(3);
            result.push(ShadowModelTrainingRow {
                variant,
                regime,
                score_last: row.get(2),
                sample_count: sample_count.max(0) as usize,
                win_rate: row.get(4),
                reliability: row.get(5),
                edge_bps: row.get(6),
            });
        }
        Ok(result)
    }

    async fn record_shadow_model_run(
        &self,
        timeframe: Timeframe,
        evaluation: &PairEvaluationOutput,
    ) -> anyhow::Result<usize> {
        let diagnostics = &evaluation.cue.shadow_ml;
        let rationale = diagnostics.rationale_codes.join("|");
        let written = self
            .client
            .execute(
                "INSERT INTO strategy_shadow_model_runs
                 (pair_id, timeframe, run_at, model_name, status, training_rows, positive_rate, precision,
                  brier_score, recommended_variant, recommended_probability, agrees_with_selected, rationale)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                 ON CONFLICT (pair_id, timeframe, run_at)
                 DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    status = EXCLUDED.status,
                    training_rows = EXCLUDED.training_rows,
                    positive_rate = EXCLUDED.positive_rate,
                    precision = EXCLUDED.precision,
                    brier_score = EXCLUDED.brier_score,
                    recommended_variant = EXCLUDED.recommended_variant,
                    recommended_probability = EXCLUDED.recommended_probability,
                    agrees_with_selected = EXCLUDED.agrees_with_selected,
                    rationale = EXCLUDED.rationale",
                &[
                    &evaluation.cue.pair_id as &(dyn ToSql + Sync),
                    &timeframe.as_str(),
                    &evaluation.cue.evaluated_at,
                    &diagnostics.model_name,
                    &diagnostics.status,
                    &(diagnostics.training_rows as i32),
                    &diagnostics.positive_rate,
                    &diagnostics.precision,
                    &diagnostics.brier_score,
                    &diagnostics.recommended_variant,
                    &diagnostics.recommended_probability,
                    &diagnostics.agrees_with_selected,
                    &rationale,
                ],
            )
            .await?;
        Ok(written as usize)
    }

    async fn fetch_selected_signal(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
    ) -> anyhow::Result<Option<SelectedSignalRow>> {
        let row = self
            .client
            .query_opt(
                "SELECT signal_variant, opportunity_score
                 FROM strategy_selected_signal
                 WHERE pair_id=$1 AND timeframe=$2",
                &[&pair_id, &timeframe.as_str()],
            )
            .await?;
        Ok(row.map(|row| SelectedSignalRow {
            signal_variant: row.get(0),
            opportunity_score: row.get(1),
        }))
    }
}

fn resolve_variant_score(evaluation: &PairEvaluationOutput, variant: &str, fallback: f64) -> f64 {
    evaluation
        .variants
        .iter()
        .find(|item| item.variant == variant)
        .map(|item| item.opportunity_score)
        .unwrap_or(fallback)
}

fn decide_champion_transition(
    existing: Option<&SelectedSignalRow>,
    evaluation: &PairEvaluationOutput,
    champion_switch_min_delta: f64,
) -> ChampionTransition {
    let challenger_variant = evaluation.cue.selected_variant.clone();
    let challenger_score = evaluation.cue.opportunity_score;

    match existing {
        None => ChampionTransition {
            selected_variant: challenger_variant.clone(),
            selected_score: challenger_score,
            champion_variant: challenger_variant.clone(),
            challenger_variant,
            champion_score: challenger_score,
            challenger_score,
            score_delta: 0.0,
            decision: ChampionDecision::Initialize,
        },
        Some(current) if current.signal_variant == challenger_variant => ChampionTransition {
            selected_variant: challenger_variant.clone(),
            selected_score: challenger_score,
            champion_variant: current.signal_variant.clone(),
            challenger_variant,
            champion_score: challenger_score,
            challenger_score,
            score_delta: 0.0,
            decision: ChampionDecision::Unchanged,
        },
        Some(current) => {
            let champion_score = resolve_variant_score(
                evaluation,
                &current.signal_variant,
                current.opportunity_score,
            );
            let score_delta = challenger_score - champion_score;
            if score_delta >= champion_switch_min_delta {
                ChampionTransition {
                    selected_variant: challenger_variant.clone(),
                    selected_score: challenger_score,
                    champion_variant: current.signal_variant.clone(),
                    challenger_variant,
                    champion_score,
                    challenger_score,
                    score_delta,
                    decision: ChampionDecision::PromoteChallenger,
                }
            } else {
                ChampionTransition {
                    selected_variant: current.signal_variant.clone(),
                    selected_score: champion_score,
                    champion_variant: current.signal_variant.clone(),
                    challenger_variant,
                    champion_score,
                    challenger_score,
                    score_delta,
                    decision: ChampionDecision::KeepChampion,
                }
            }
        }
    }
}

#[derive(Debug, Deserialize)]
struct CuesQuery {
    timeframe: String,
    limit: Option<usize>,
    include_advisory: Option<bool>,
    taker_fee_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct BacktestQuery {
    timeframe: String,
    pair_id: String,
    bars: Option<usize>,
    taker_fee_bps: Option<f64>,
    exit_mode: Option<String>,
}

#[derive(Debug, Deserialize)]
struct LiveZQuery {
    timeframe: String,
    pair_id: String,
    points: Option<usize>,
    taker_fee_bps: Option<f64>,
    exit_mode: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OpportunityHistoryQuery {
    timeframe: String,
    hours: Option<i64>,
    only_pass: Option<bool>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct OpportunityHistoryStatsQuery {
    timeframe: Option<String>,
}

#[derive(Debug, Deserialize)]
struct PaperTradesQuery {
    timeframe: String,
    pair_id: Option<String>,
    hours: Option<i64>,
    limit: Option<usize>,
    exit_mode: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ExpectancyQuery {
    timeframe: String,
    pair_id: String,
    entry_z: Option<f64>,
    exit_z: Option<f64>,
    stop_z: Option<f64>,
    z_method: Option<String>,
    lookback_bars: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct ReplayTradesQuery {
    timeframe: String,
    pair_id: String,
    hours: Option<i64>,
    limit: Option<usize>,
    exit_mode: Option<String>,
    entry_z: Option<f64>,
    exit_z: Option<f64>,
    stop_z: Option<f64>,
    z_method: Option<String>,
    lookback_bars: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct ResearchSweepRequest {
    timeframes: Option<Vec<String>>,
    pair_ids: Option<Vec<String>>,
    entry_z_grid: Option<Vec<f64>>,
    exit_z_grid: Option<Vec<f64>>,
    stop_z_grid: Option<Vec<f64>>,
    z_methods: Option<Vec<String>>,
    lookback_bars_grid: Option<Vec<usize>>,
    max_combinations: Option<usize>,
    dry_run: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct ReoptimizeRequest {
    timeframes: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct MaintenanceArtifactQuery {
    path: String,
}

#[derive(Debug, Deserialize)]
struct MaintenanceActionRequest {
    action: String,
    operator_id: String,
    confirm: bool,
}

#[derive(Debug, Deserialize)]
struct UiAuthVerifyRequest {
    password: String,
}

#[derive(Debug, Deserialize)]
struct StrategyMarketMetricsQuery {
    instrument: String,
}

#[derive(Debug, Serialize)]
struct UiAuthStatusResponse {
    enabled: bool,
}

#[derive(Debug, Serialize)]
struct UiAuthVerifyResponse {
    ok: bool,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct StrategyMarketMetricsResponse {
    instrument: String,
    server_time: DateTime<Utc>,
    bid: f64,
    ask: f64,
    mark: f64,
    index: f64,
    change_24h_pct: f64,
    funding_rate: f64,
    open_interest: f64,
}

#[derive(Debug, Serialize)]
struct StrategyMarketMetricsUiResponse {
    instrument: String,
    server_time: DateTime<Utc>,
    bid: f64,
    ask: f64,
    mark: f64,
    index: f64,
    change_24h_pct: f64,
    funding_rate: f64,
    open_interest: f64,
    funding_interval_secs: u64,
}

#[derive(Debug, Deserialize)]
struct StrategyMarketMetricsBatchResponse {
    generated_at: DateTime<Utc>,
    metrics: Vec<StrategyMarketMetricsResponse>,
}

#[derive(Debug, Clone)]
struct PairSlippageConfig {
    key: String,
    left_instrument: String,
    right_instrument: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum SampledSlippageSource {
    Live,
    Bootstrapped,
}

#[derive(Debug, Clone)]
struct PairSlippageState {
    long_slippage_ewma_bps: f64,
    short_slippage_ewma_bps: f64,
    long_funding_bps_per_event: f64,
    short_funding_bps_per_event: f64,
    funding_available: bool,
    sample_count: usize,
    last_sample_at: DateTime<Utc>,
    source: SampledSlippageSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SampledSlippageStatus {
    Healthy,
    Warming,
    Stale,
    Down,
}

impl SampledSlippageStatus {
    fn rationale_code(self) -> Option<&'static str> {
        match self {
            Self::Healthy => None,
            Self::Warming => Some("SLIPPAGE_DATA_WARMING"),
            Self::Stale => Some("SLIPPAGE_DATA_STALE"),
            Self::Down => Some("SLIPPAGE_DATA_UNAVAILABLE"),
        }
    }
}

#[derive(Debug, Clone)]
struct PairSlippageSnapshot {
    status: SampledSlippageStatus,
    selected_slippage_bps: f64,
    selected_funding_bps_per_event: Option<f64>,
    source: Option<SampledSlippageSource>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SampledSlippageCheckpointEntry {
    key: String,
    long_slippage_ewma_bps: f64,
    short_slippage_ewma_bps: f64,
    long_funding_bps_per_event: f64,
    short_funding_bps_per_event: f64,
    funding_available: bool,
    sample_count: usize,
    last_sample_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SampledSlippageCheckpoint {
    generated_at: DateTime<Utc>,
    entries: Vec<SampledSlippageCheckpointEntry>,
}

fn bootstrap_snapshot_is_fresh(
    sample_ts: DateTime<Utc>,
    now: DateTime<Utc>,
    stale_after: chrono::Duration,
) -> bool {
    let max_age_secs = stale_after.num_seconds().saturating_mul(2).max(1);
    let max_age = chrono::Duration::seconds(max_age_secs);
    let age = now.signed_duration_since(sample_ts);
    age >= chrono::Duration::zero() && age <= max_age
}

fn bootstrap_deviation_exceeds_threshold(
    previous_long_bps: f64,
    previous_short_bps: f64,
    first_live_long_bps: f64,
    first_live_short_bps: f64,
    threshold_bps: f64,
) -> bool {
    if !previous_long_bps.is_finite()
        || !previous_short_bps.is_finite()
        || !first_live_long_bps.is_finite()
        || !first_live_short_bps.is_finite()
        || !threshold_bps.is_finite()
    {
        return true;
    }
    let threshold = threshold_bps.max(0.0);
    (first_live_long_bps - previous_long_bps).abs() > threshold
        || (first_live_short_bps - previous_short_bps).abs() > threshold
}

fn normalize_funding_rate(raw_rate: f64, mode: FundingRateInputMode) -> f64 {
    match mode {
        FundingRateInputMode::Fraction => raw_rate,
        FundingRateInputMode::Percent => raw_rate / 100.0,
        FundingRateInputMode::Bps => raw_rate / 10_000.0,
        FundingRateInputMode::Auto => {
            // Auto mode supports three common wire formats:
            // - fraction (0.00025 = 2.5 bps)
            // - percent (0.025 = 2.5 bps)
            // - bps (2.5 = 2.5 bps)
            //
            // Heuristic:
            // - very large magnitudes are treated as bps (avoids 100x inflation on values like -0.716)
            // - mid magnitudes are treated as percent
            // - tiny magnitudes are treated as fraction
            // Example:
            //   raw=-0.716 -> bps mode     => -0.0000716
            //   raw=-0.009 -> percent mode => -0.00009
            //   raw=-0.00025 -> fraction   => -0.00025
            let abs = raw_rate.abs();
            if abs >= 0.25 {
                raw_rate / 10_000.0
            } else if abs >= 0.001 {
                raw_rate / 100.0
            } else {
                raw_rate
            }
        }
    }
}

#[derive(Debug)]
struct SampledSlippageStore {
    pair_configs: Vec<PairSlippageConfig>,
    instruments: Vec<String>,
    states: RwLock<HashMap<String, PairSlippageState>>,
    hedge_ratios: RwLock<HashMap<String, f64>>,
    poll_error: RwLock<Option<String>>,
    ewma_alpha: f64,
    warmup_samples: usize,
    stale_after: chrono::Duration,
    persist_path: PathBuf,
    persist_interval: chrono::Duration,
    bootstrap_max_deviation_bps: f64,
    last_persist_at: RwLock<Option<DateTime<Utc>>>,
    funding_rate_bps_multiplier: f64,
    funding_positive_rate_means_longs_pay: bool,
    funding_rate_input_mode: FundingRateInputMode,
}

impl SampledSlippageStore {
    fn new(settings: &StrategySettings) -> Self {
        let mut pair_configs = vec![];
        let mut instruments = HashSet::new();
        for timeframe in &settings.timeframes {
            for pair in &settings.pairs {
                let pair_id = pair.pair_id();
                let key = Self::pair_key(&pair_id, *timeframe);
                pair_configs.push(PairSlippageConfig {
                    key,
                    left_instrument: pair.left.to_uppercase(),
                    right_instrument: pair.right.to_uppercase(),
                });
                instruments.insert(pair.left.to_uppercase());
                instruments.insert(pair.right.to_uppercase());
            }
        }

        let interval_ms = settings.sampled_slippage_interval_ms.max(250);
        let warmup_samples = ((settings.sampled_slippage_warmup_secs.max(1) * 1000)
            .div_ceil(interval_ms))
        .max(1) as usize;
        let stale_after_secs = settings.sampled_slippage_stale_secs.max(1);
        let persist_secs = settings.sampled_slippage_persist_secs.max(1);

        Self {
            pair_configs,
            instruments: instruments.into_iter().collect(),
            states: RwLock::new(HashMap::new()),
            hedge_ratios: RwLock::new(HashMap::new()),
            poll_error: RwLock::new(None),
            ewma_alpha: settings.sampled_slippage_ewma_alpha.clamp(0.01, 1.0),
            warmup_samples,
            stale_after: chrono::Duration::seconds(stale_after_secs as i64),
            persist_path: PathBuf::from(&settings.sampled_slippage_state_path),
            persist_interval: chrono::Duration::seconds(persist_secs as i64),
            bootstrap_max_deviation_bps: settings.sampled_slippage_bootstrap_max_deviation_bps,
            last_persist_at: RwLock::new(None),
            funding_rate_bps_multiplier: settings.funding_rate_bps_multiplier.max(1.0),
            funding_positive_rate_means_longs_pay: settings.funding_positive_rate_means_longs_pay,
            funding_rate_input_mode: settings.funding_rate_input_mode,
        }
    }

    fn pair_key(pair_id: &str, timeframe: Timeframe) -> String {
        format!("{pair_id}|{}", timeframe.as_str())
    }

    fn instruments_csv(&self) -> String {
        self.instruments.join(",")
    }

    async fn hydrate_from_disk(&self) -> anyhow::Result<usize> {
        let raw = match std::fs::read(&self.persist_path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(0),
            Err(error) => {
                anyhow::bail!(
                    "failed reading sampled slippage checkpoint '{}': {}",
                    self.persist_path.display(),
                    error
                );
            }
        };
        let checkpoint: SampledSlippageCheckpoint =
            serde_json::from_slice(&raw).map_err(|error| {
                anyhow::anyhow!(
                    "failed parsing sampled slippage checkpoint '{}': {}",
                    self.persist_path.display(),
                    error
                )
            })?;

        let valid_keys: HashSet<String> = self
            .pair_configs
            .iter()
            .map(|config| config.key.clone())
            .collect();
        let now = Utc::now();
        let mut states = self.states.write().await;
        let mut hydrated = 0usize;
        for entry in checkpoint.entries {
            if !valid_keys.contains(&entry.key) {
                continue;
            }
            if !bootstrap_snapshot_is_fresh(entry.last_sample_at, now, self.stale_after) {
                continue;
            }
            states.insert(
                entry.key,
                PairSlippageState {
                    long_slippage_ewma_bps: entry.long_slippage_ewma_bps.max(0.0),
                    short_slippage_ewma_bps: entry.short_slippage_ewma_bps.max(0.0),
                    long_funding_bps_per_event: entry.long_funding_bps_per_event,
                    short_funding_bps_per_event: entry.short_funding_bps_per_event,
                    funding_available: entry.funding_available,
                    sample_count: self.warmup_samples.max(entry.sample_count),
                    last_sample_at: entry.last_sample_at,
                    source: SampledSlippageSource::Bootstrapped,
                },
            );
            hydrated += 1;
        }

        if hydrated > 0 {
            *self.last_persist_at.write().await = Some(now);
        }
        Ok(hydrated)
    }

    async fn persist_snapshot_if_due(&self, snapshot_time: DateTime<Utc>) -> anyhow::Result<bool> {
        let should_persist = {
            let last_persist = *self.last_persist_at.read().await;
            match last_persist {
                Some(previous) => {
                    snapshot_time.signed_duration_since(previous) >= self.persist_interval
                }
                None => true,
            }
        };
        if !should_persist {
            return Ok(false);
        }

        let entries = {
            let states = self.states.read().await;
            states
                .iter()
                .map(|(key, value)| SampledSlippageCheckpointEntry {
                    key: key.clone(),
                    long_slippage_ewma_bps: value.long_slippage_ewma_bps,
                    short_slippage_ewma_bps: value.short_slippage_ewma_bps,
                    long_funding_bps_per_event: value.long_funding_bps_per_event,
                    short_funding_bps_per_event: value.short_funding_bps_per_event,
                    funding_available: value.funding_available,
                    sample_count: value.sample_count,
                    last_sample_at: value.last_sample_at,
                })
                .collect::<Vec<_>>()
        };
        if entries.is_empty() {
            return Ok(false);
        }

        let checkpoint = SampledSlippageCheckpoint {
            generated_at: snapshot_time,
            entries,
        };
        let payload = serde_json::to_vec_pretty(&checkpoint).map_err(|error| {
            anyhow::anyhow!(
                "failed serializing sampled slippage checkpoint '{}': {}",
                self.persist_path.display(),
                error
            )
        })?;

        if let Some(parent) = self.persist_path.parent() {
            std::fs::create_dir_all(parent).map_err(|error| {
                anyhow::anyhow!(
                    "failed creating checkpoint directory '{}': {}",
                    parent.display(),
                    error
                )
            })?;
        }
        let temp_path = self.persist_path.with_extension("tmp");
        std::fs::write(&temp_path, payload).map_err(|error| {
            anyhow::anyhow!(
                "failed writing sampled slippage checkpoint '{}': {}",
                temp_path.display(),
                error
            )
        })?;
        std::fs::rename(&temp_path, &self.persist_path).map_err(|error| {
            anyhow::anyhow!(
                "failed replacing sampled slippage checkpoint '{}': {}",
                self.persist_path.display(),
                error
            )
        })?;
        *self.last_persist_at.write().await = Some(snapshot_time);
        Ok(true)
    }

    async fn set_poll_error(&self, error: String) {
        *self.poll_error.write().await = Some(error);
    }

    async fn clear_poll_error(&self) {
        *self.poll_error.write().await = None;
    }

    async fn update_hedge_ratio(&self, pair_id: &str, timeframe: Timeframe, hedge_ratio: f64) {
        if !hedge_ratio.is_finite() {
            return;
        }
        self.hedge_ratios
            .write()
            .await
            .insert(Self::pair_key(pair_id, timeframe), hedge_ratio);
    }

    async fn ingest_quotes(
        &self,
        quotes: &HashMap<String, StrategyMarketMetricsResponse>,
        sampled_at: DateTime<Utc>,
    ) -> usize {
        let hedge_ratios = self.hedge_ratios.read().await.clone();
        let mut states = self.states.write().await;
        let mut updated = 0usize;

        for config in &self.pair_configs {
            let Some(left) = quotes.get(&config.left_instrument) else {
                continue;
            };
            let Some(right) = quotes.get(&config.right_instrument) else {
                continue;
            };
            let hedge_ratio = *hedge_ratios.get(&config.key).unwrap_or(&1.0);
            let Some((long_slippage_bps, short_slippage_bps)) =
                compute_pair_slippage_sample_bps(left, right, hedge_ratio)
            else {
                continue;
            };
            let funding_sample = compute_pair_funding_bps_per_event(
                left,
                right,
                hedge_ratio,
                self.funding_rate_bps_multiplier,
                self.funding_positive_rate_means_longs_pay,
                self.funding_rate_input_mode,
            );

            let state = states
                .entry(config.key.clone())
                .or_insert(PairSlippageState {
                    long_slippage_ewma_bps: long_slippage_bps,
                    short_slippage_ewma_bps: short_slippage_bps,
                    long_funding_bps_per_event: funding_sample.map(|value| value.0).unwrap_or(0.0),
                    short_funding_bps_per_event: funding_sample.map(|value| value.1).unwrap_or(0.0),
                    funding_available: funding_sample.is_some(),
                    sample_count: 0,
                    last_sample_at: sampled_at,
                    source: SampledSlippageSource::Live,
                });
            let mut bootstrapped_replaced = false;
            if state.source == SampledSlippageSource::Bootstrapped {
                let should_fail_warm_start = bootstrap_deviation_exceeds_threshold(
                    state.long_slippage_ewma_bps,
                    state.short_slippage_ewma_bps,
                    long_slippage_bps,
                    short_slippage_bps,
                    self.bootstrap_max_deviation_bps,
                );
                if should_fail_warm_start {
                    tracing::warn!(
                        pair_key = %config.key,
                        previous_long_bps = state.long_slippage_ewma_bps,
                        previous_short_bps = state.short_slippage_ewma_bps,
                        first_live_long_bps = long_slippage_bps,
                        first_live_short_bps = short_slippage_bps,
                        threshold_bps = self.bootstrap_max_deviation_bps,
                        "sampled slippage warm-start deviation exceeded threshold; reverting to warmup"
                    );
                    state.sample_count = 0;
                } else {
                    // Promote immediately to live sample when bootstrap and live quote agree.
                    state.long_slippage_ewma_bps = long_slippage_bps;
                    state.short_slippage_ewma_bps = short_slippage_bps;
                    state.sample_count = self.warmup_samples;
                    bootstrapped_replaced = true;
                }
                state.source = SampledSlippageSource::Live;
            }

            if !bootstrapped_replaced && state.sample_count == 0 {
                state.long_slippage_ewma_bps = long_slippage_bps;
                state.short_slippage_ewma_bps = short_slippage_bps;
            } else if !bootstrapped_replaced {
                state.long_slippage_ewma_bps = (self.ewma_alpha * long_slippage_bps)
                    + ((1.0 - self.ewma_alpha) * state.long_slippage_ewma_bps);
                state.short_slippage_ewma_bps = (self.ewma_alpha * short_slippage_bps)
                    + ((1.0 - self.ewma_alpha) * state.short_slippage_ewma_bps);
            }
            if let Some((long_funding_bps_per_event, short_funding_bps_per_event)) = funding_sample
            {
                state.long_funding_bps_per_event = long_funding_bps_per_event;
                state.short_funding_bps_per_event = short_funding_bps_per_event;
                state.funding_available = true;
            } else {
                state.funding_available = false;
            }
            state.sample_count = state.sample_count.saturating_add(1);
            state.last_sample_at = sampled_at;
            updated += 1;
        }

        updated
    }

    async fn snapshot_for(
        &self,
        pair_id: &str,
        timeframe: Timeframe,
        direction_hint: &str,
    ) -> PairSlippageSnapshot {
        let key = Self::pair_key(pair_id, timeframe);
        let maybe_state = self.states.read().await.get(&key).cloned();
        let poll_error = self.poll_error.read().await.clone();

        let Some(state) = maybe_state else {
            if let Some(error) = poll_error {
                tracing::warn!(
                    pair_id = %pair_id,
                    timeframe = %timeframe.as_str(),
                    error = %error,
                    "sampled slippage unavailable"
                );
            }
            return PairSlippageSnapshot {
                status: SampledSlippageStatus::Down,
                selected_slippage_bps: 0.0,
                selected_funding_bps_per_event: None,
                source: None,
            };
        };

        let age = Utc::now().signed_duration_since(state.last_sample_at);
        let status = if age > self.stale_after {
            SampledSlippageStatus::Stale
        } else if state.sample_count < self.warmup_samples {
            SampledSlippageStatus::Warming
        } else {
            SampledSlippageStatus::Healthy
        };
        let selected_slippage_bps = match direction_hint {
            "LONG_SPREAD" => state.long_slippage_ewma_bps,
            "SHORT_SPREAD" => state.short_slippage_ewma_bps,
            _ => state
                .long_slippage_ewma_bps
                .max(state.short_slippage_ewma_bps),
        };
        let selected_funding_bps_per_event = if state.funding_available {
            Some(match direction_hint {
                "LONG_SPREAD" => state.long_funding_bps_per_event,
                "SHORT_SPREAD" => state.short_funding_bps_per_event,
                _ => state
                    .long_funding_bps_per_event
                    .abs()
                    .max(state.short_funding_bps_per_event.abs()),
            })
        } else {
            None
        };

        PairSlippageSnapshot {
            status,
            selected_slippage_bps,
            selected_funding_bps_per_event,
            source: Some(state.source),
        }
    }
}

fn compute_pair_slippage_sample_bps(
    left: &StrategyMarketMetricsResponse,
    right: &StrategyMarketMetricsResponse,
    hedge_ratio: f64,
) -> Option<(f64, f64)> {
    let values = [
        left.bid,
        left.ask,
        left.index,
        right.bid,
        right.ask,
        right.index,
        hedge_ratio,
    ];
    if values.iter().any(|value| !value.is_finite()) {
        return None;
    }
    if left.bid <= 0.0
        || left.ask <= 0.0
        || left.index <= 0.0
        || right.bid <= 0.0
        || right.ask <= 0.0
        || right.index <= 0.0
    {
        return None;
    }
    if left.ask < left.bid || right.ask < right.bid {
        return None;
    }

    let ratio = hedge_ratio.abs().max(1e-9);
    let gross_notional = left.index.abs() + (ratio * right.index.abs());
    if gross_notional <= 0.0 {
        return None;
    }

    let long_leg_cost =
        (left.ask - left.index).max(0.0) + ratio * (right.index - right.bid).max(0.0);
    let short_leg_cost =
        (left.index - left.bid).max(0.0) + ratio * (right.ask - right.index).max(0.0);
    let long_bps = (long_leg_cost / gross_notional) * 10_000.0;
    let short_bps = (short_leg_cost / gross_notional) * 10_000.0;

    if long_bps.is_finite() && short_bps.is_finite() {
        Some((long_bps.max(0.0), short_bps.max(0.0)))
    } else {
        None
    }
}

fn compute_pair_funding_bps_per_event(
    left: &StrategyMarketMetricsResponse,
    right: &StrategyMarketMetricsResponse,
    hedge_ratio: f64,
    funding_rate_bps_multiplier: f64,
    positive_rate_means_longs_pay: bool,
    funding_rate_input_mode: FundingRateInputMode,
) -> Option<(f64, f64)> {
    let values = [
        left.funding_rate,
        right.funding_rate,
        left.index,
        right.index,
        hedge_ratio,
        funding_rate_bps_multiplier,
    ];
    if values.iter().any(|value| !value.is_finite()) {
        return None;
    }
    if left.index <= 0.0 || right.index <= 0.0 || funding_rate_bps_multiplier <= 0.0 {
        return None;
    }

    let ratio = hedge_ratio.abs().max(1e-9);
    let left_notional = left.index.abs();
    let right_notional = ratio * right.index.abs();
    let gross_notional = left_notional + right_notional;
    if gross_notional <= 0.0 {
        return None;
    }
    let left_weight = left_notional / gross_notional;
    let right_weight = right_notional / gross_notional;

    let sign = if positive_rate_means_longs_pay {
        1.0
    } else {
        -1.0
    };
    let left_funding_rate = normalize_funding_rate(left.funding_rate, funding_rate_input_mode);
    let right_funding_rate = normalize_funding_rate(right.funding_rate, funding_rate_input_mode);
    let left_long_cost_bps = sign * left_funding_rate * funding_rate_bps_multiplier;
    let right_long_cost_bps = sign * right_funding_rate * funding_rate_bps_multiplier;
    let left_short_cost_bps = -left_long_cost_bps;
    let right_short_cost_bps = -right_long_cost_bps;

    let long_spread_bps_per_event =
        (left_weight * left_long_cost_bps) + (right_weight * right_short_cost_bps);
    let short_spread_bps_per_event =
        (left_weight * left_short_cost_bps) + (right_weight * right_long_cost_bps);
    if !long_spread_bps_per_event.is_finite() || !short_spread_bps_per_event.is_finite() {
        return None;
    }
    Some((long_spread_bps_per_event, short_spread_bps_per_event))
}

fn expected_funding_events_crossed(
    evaluated_at: DateTime<Utc>,
    expected_hold_bars: i64,
    timeframe: Timeframe,
    funding_interval_secs: u64,
    funding_phase_offset_secs: i64,
) -> u32 {
    if expected_hold_bars <= 0 {
        return 0;
    }
    let hold_secs = expected_hold_bars.saturating_mul(timeframe.step_seconds());
    if hold_secs <= 0 {
        return 0;
    }
    let interval_secs = funding_interval_secs.max(1) as i64;
    let phase = funding_phase_offset_secs.rem_euclid(interval_secs);
    let elapsed_in_interval = (evaluated_at.timestamp() - phase).rem_euclid(interval_secs);
    let secs_to_next = if elapsed_in_interval == 0 {
        interval_secs
    } else {
        interval_secs - elapsed_in_interval
    };
    if hold_secs < secs_to_next {
        return 0;
    }
    let remainder = hold_secs - secs_to_next;
    (1 + (remainder / interval_secs)) as u32
}

fn expected_hold_hours(expected_hold_bars: i64, timeframe: Timeframe) -> f64 {
    if expected_hold_bars <= 0 {
        return 0.0;
    }
    let hold_secs = expected_hold_bars.saturating_mul(timeframe.step_seconds());
    if hold_secs <= 0 {
        return 0.0;
    }
    (hold_secs as f64) / 3600.0
}

fn funding_bps_per_hour_from_event_bps(
    funding_bps_per_event: f64,
    funding_interval_secs: u64,
) -> f64 {
    if !funding_bps_per_event.is_finite() {
        return 0.0;
    }
    let interval_hours = (funding_interval_secs.max(1) as f64) / 3600.0;
    if interval_hours <= 0.0 {
        return 0.0;
    }
    funding_bps_per_event / interval_hours
}

fn project_continuous_funding_bps(
    funding_bps_per_event: f64,
    expected_hold_bars: i64,
    timeframe: Timeframe,
    funding_interval_secs: u64,
) -> f64 {
    let hold_hours = expected_hold_hours(expected_hold_bars, timeframe);
    if hold_hours <= 0.0 {
        return 0.0;
    }
    let funding_bps_per_hour =
        funding_bps_per_hour_from_event_bps(funding_bps_per_event, funding_interval_secs);
    if !funding_bps_per_hour.is_finite() {
        return 0.0;
    }
    funding_bps_per_hour * hold_hours
}

#[derive(Debug, Clone, Copy)]
struct FundingCostEstimate {
    model: FundingModel,
    events: u32,
    bps_per_event: f64,
    total_bps: f64,
    sample_available: bool,
}

fn resolve_funding_cost_estimate(
    settings: &StrategySettings,
    output: &PairEvaluationOutput,
    timeframe: Timeframe,
    sampled: &PairSlippageSnapshot,
) -> FundingCostEstimate {
    if !settings.dynamic_funding_enabled {
        let total_bps = settings.funding_drag_bps.max(0.0);
        return FundingCostEstimate {
            model: FundingModel::Static,
            events: 0,
            bps_per_event: total_bps,
            total_bps,
            sample_available: true,
        };
    }

    let hold_hours = expected_hold_hours(output.cue.expected_hold_bars, timeframe);
    let events = expected_funding_events_crossed(
        output.cue.evaluated_at,
        output.cue.expected_hold_bars,
        timeframe,
        settings.funding_interval_secs,
        settings.funding_phase_offset_secs,
    );
    if hold_hours <= 0.0 {
        let bps_per_event = sampled.selected_funding_bps_per_event.unwrap_or(0.0);
        return FundingCostEstimate {
            model: FundingModel::Dynamic,
            events,
            bps_per_event,
            total_bps: 0.0,
            sample_available: sampled.selected_funding_bps_per_event.is_some(),
        };
    }

    let bps_per_event = sampled.selected_funding_bps_per_event.unwrap_or(0.0);
    let total_bps = project_continuous_funding_bps(
        bps_per_event,
        output.cue.expected_hold_bars,
        timeframe,
        settings.funding_interval_secs,
    );
    FundingCostEstimate {
        model: FundingModel::Dynamic,
        events,
        bps_per_event,
        total_bps,
        sample_available: sampled.selected_funding_bps_per_event.is_some(),
    }
}

fn resolve_expected_edge_bps_for_cost_gate(output: &PairEvaluationOutput) -> f64 {
    output
        .variants
        .iter()
        .find(|variant| variant.variant == output.cue.selected_variant)
        .map(|variant| (variant.edge_bps * variant.reliability).max(0.0))
        .unwrap_or_else(|| output.cue.opportunity_score.max(0.0))
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
    candidate_set: CandidateSetDiagnostics,
    portfolio_plan: PortfolioPlan,
    skipped: Vec<SkippedPair>,
}

#[derive(Debug, Serialize)]
struct BacktestPointResponse {
    ts: DateTime<Utc>,
    z: f64,
    equity: f64,
}

#[derive(Debug, Serialize)]
struct BacktestMarkerResponse {
    index: usize,
    kind: String,
}

#[derive(Debug, Serialize)]
struct BacktestResponse {
    timeframe: String,
    pair_id: String,
    generated_at: DateTime<Utc>,
    exit_mode: String,
    left_instrument: String,
    right_instrument: String,
    selected_variant: String,
    hedge_ratio: f64,
    entry_band: f64,
    exit_band: f64,
    stop_band: f64,
    round_trip_cost_bps: f64,
    points: Vec<BacktestPointResponse>,
    markers: Vec<BacktestMarkerResponse>,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct LiveZPointResponse {
    ts: DateTime<Utc>,
    z: f64,
}

#[derive(Debug, Serialize)]
struct LiveZResponse {
    timeframe: String,
    pair_id: String,
    generated_at: DateTime<Utc>,
    exit_mode: String,
    entry_band: f64,
    exit_band: f64,
    stop_band: f64,
    selected_variant: String,
    points: Vec<LiveZPointResponse>,
    markers: Vec<BacktestMarkerResponse>,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct SkippedPair {
    pair_id: String,
    reason: String,
}

#[derive(Debug, Serialize)]
struct CostGatePair {
    pair_id: String,
    left_instrument: String,
    right_instrument: String,
    timeframe: String,
    expected_edge_bps: f64,
    fee_bps: f64,
    funding_model: String,
    funding_events: u32,
    funding_bps_per_event: f64,
    funding_bps: f64,
    slippage_bps: f64,
    net_edge_bps: f64,
    pass: bool,
    setup_pass: bool,
    trade_ready: bool,
    trade_blocked_by: String,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct CostGateResponse {
    timeframe: String,
    generated_at: DateTime<Utc>,
    gates: Vec<CostGatePair>,
    skipped: Vec<SkippedPair>,
}

#[derive(Debug, Serialize)]
struct PortfolioPlanResponse {
    timeframe: String,
    generated_at: DateTime<Utc>,
    plan: PortfolioPlan,
    skipped: Vec<SkippedPair>,
}

#[derive(Debug, Serialize)]
struct OpportunityHistoryEntry {
    pair_id: String,
    left_instrument: String,
    right_instrument: String,
    timeframe: String,
    selected_variant: String,
    regime: String,
    direction_hint: String,
    spread_z: f64,
    opportunity_score: f64,
    net_edge_bps: f64,
    cost_gate_pass: bool,
    actionable: bool,
    rationale_codes: Vec<String>,
    cost_gate_rationale_codes: Vec<String>,
    evaluated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
struct OpportunityHistoryResponse {
    timeframe: String,
    generated_at: DateTime<Utc>,
    hours: i64,
    only_pass: bool,
    rows: Vec<OpportunityHistoryEntry>,
}

#[derive(Debug, Serialize, Clone)]
struct OpportunityHistoryStatsEntry {
    timeframe: String,
    rows: i64,
    first_evaluated_at: Option<DateTime<Utc>>,
    last_evaluated_at: Option<DateTime<Utc>>,
    days_covered: f64,
}

#[derive(Debug, Serialize)]
struct OpportunityHistoryStatsResponse {
    generated_at: DateTime<Utc>,
    timeframe_filter: Option<String>,
    total_rows: i64,
    first_evaluated_at: Option<DateTime<Utc>>,
    last_evaluated_at: Option<DateTime<Utc>>,
    days_covered: f64,
    by_timeframe: Vec<OpportunityHistoryStatsEntry>,
}

#[derive(Debug, Serialize)]
struct PaperTradeEntry {
    pair_id: String,
    timeframe: String,
    exit_mode: String,
    left_instrument: String,
    right_instrument: String,
    selected_variant: String,
    entry_ts: DateTime<Utc>,
    exit_ts: DateTime<Utc>,
    bars_held: i32,
    direction: String,
    exit_kind: String,
    entry_z: f64,
    exit_z: f64,
    entry_index: i32,
    exit_index: i32,
    left_entry: f64,
    left_exit: f64,
    right_entry: f64,
    right_exit: f64,
    left_leg_bps: f64,
    right_leg_bps: f64,
    gross_bps: f64,
    round_trip_cost_bps: f64,
    net_bps: f64,
    equity_pre_entry: f64,
    equity_exit: f64,
    equity_trade_bps: f64,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
struct PaperTradeInsertRow {
    pair_id: String,
    timeframe: String,
    exit_mode: String,
    left_instrument: String,
    right_instrument: String,
    selected_variant: String,
    entry_ts: DateTime<Utc>,
    exit_ts: DateTime<Utc>,
    bars_held: i32,
    direction: String,
    exit_kind: String,
    entry_z: f64,
    exit_z: f64,
    entry_index: i32,
    exit_index: i32,
    left_entry: f64,
    left_exit: f64,
    right_entry: f64,
    right_exit: f64,
    left_leg_bps: f64,
    right_leg_bps: f64,
    gross_bps: f64,
    round_trip_cost_bps: f64,
    net_bps: f64,
    equity_pre_entry: f64,
    equity_exit: f64,
    equity_trade_bps: f64,
}

#[derive(Debug, Serialize)]
struct PaperTradesResponse {
    timeframe: String,
    generated_at: DateTime<Utc>,
    hours: i64,
    pair_id: Option<String>,
    exit_mode: String,
    model_bars: usize,
    rows: Vec<PaperTradeEntry>,
}

#[derive(Debug, Clone, Serialize)]
struct ExpectancyConfig {
    entry_z: f64,
    exit_z: f64,
    stop_z: f64,
    z_method: String,
    hedge_method: String,
    lookback_bars: usize,
}

#[derive(Debug, Clone, Serialize)]
struct ExpectancyMetrics {
    trades: usize,
    win_rate: f64,
    avg_net_bps: f64,
    p25_net_bps: f64,
    p50_net_bps: f64,
    p75_net_bps: f64,
    avg_hold_bars: f64,
    avg_mae_bps: f64,
    avg_mfe_bps: f64,
    expected_min_lot_net_bps: f64,
    expected_min_lot_net_usd: f64,
}

#[derive(Debug, Serialize)]
struct ExpectancyResponse {
    timeframe: String,
    pair_id: String,
    generated_at: DateTime<Utc>,
    status: String,
    decision_state: String,
    primary_reason_code: String,
    config: ExpectancyConfig,
    metrics: Option<ExpectancyMetrics>,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct ReplayTradePathSummary {
    mae_bps: f64,
    mfe_bps: f64,
    bars_underwater: usize,
    bars_held: usize,
}

#[derive(Debug, Serialize)]
struct ReplayTradeEntry {
    trade_id: String,
    entry_ts: DateTime<Utc>,
    exit_ts: DateTime<Utc>,
    direction: String,
    entry_z: f64,
    exit_z: f64,
    net_bps: f64,
    path: ReplayTradePathSummary,
}

#[derive(Debug, Serialize)]
struct ReplayTradesResponse {
    timeframe: String,
    pair_id: String,
    generated_at: DateTime<Utc>,
    status: String,
    model_bars: usize,
    hours: i64,
    limit: i64,
    exit_mode: String,
    config: ExpectancyConfig,
    rationale_codes: Vec<String>,
    rows: Vec<ReplayTradeEntry>,
}

#[derive(Debug, Clone, Serialize)]
struct ResearchSweepCandidateResponse {
    rank: usize,
    timeframe: String,
    pair_id: String,
    config: ExpectancyConfig,
    status: String,
    decision_state: String,
    primary_reason_code: String,
    objective_score: f64,
    metrics: Option<ExpectancyMetrics>,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct ResearchSweepResponse {
    generated_at: DateTime<Utc>,
    status: String,
    request_id: String,
    dry_run: bool,
    timeframes: Vec<String>,
    pair_ids: Vec<String>,
    estimated_combinations: usize,
    executed_combinations: usize,
    successful_combinations: usize,
    failed_combinations: usize,
    top_k: usize,
    best_candidate: Option<ResearchSweepCandidateResponse>,
    top_candidates: Vec<ResearchSweepCandidateResponse>,
    max_combinations: usize,
    rationale_codes: Vec<String>,
}

#[derive(Debug, Serialize)]
struct ReoptimizeResponse {
    generated_at: DateTime<Utc>,
    timeframes: Vec<String>,
    pairs_processed: usize,
    cues_generated: usize,
    performance_rows_written: usize,
    selected_rows_written: usize,
    drift_rows_written: usize,
    champion_promotions: usize,
    champion_locks: usize,
    shadow_model_runs_written: usize,
    shadow_model_available: usize,
    shadow_model_unavailable: usize,
    cost_gate_pass: usize,
    cost_gate_fail: usize,
    portfolio_advice_available: usize,
    portfolio_advice_unavailable: usize,
    errors: Vec<ReoptError>,
}

#[derive(Debug, Serialize)]
struct MaintenanceLatestResponse {
    available: bool,
    generated_at: DateTime<Utc>,
    report: Option<serde_json::Value>,
    reason: Option<String>,
    artifact_download_route: String,
}

#[derive(Debug, Serialize)]
struct MaintenanceActionResponse {
    accepted: bool,
    action: String,
    operator_id: String,
    pass: bool,
    generated_at: DateTime<Utc>,
    report_download_path: String,
    report: Option<serde_json::Value>,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct MaintenanceActionQueueItem {
    request_id: String,
    action: String,
    mode: String,
    operator_id: String,
    queued_at: DateTime<Utc>,
    apply_script_path: String,
    policy_json_path: String,
    env_file_path: String,
    deploy_script_path: String,
    services: String,
    output_json_path: String,
    skip_pull: bool,
    timeout_secs: u64,
}

#[derive(Debug, Clone, Copy)]
enum MaintenanceAction {
    Promote,
    Revert,
}

impl MaintenanceAction {
    fn parse(value: &str) -> Option<Self> {
        match value.trim().to_uppercase().as_str() {
            "PROMOTE" => Some(Self::Promote),
            "REVERT" => Some(Self::Revert),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Promote => "PROMOTE",
            Self::Revert => "REVERT",
        }
    }

    fn script_mode(self) -> &'static str {
        match self {
            Self::Promote => "promote",
            Self::Revert => "revert",
        }
    }
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
    Unauthorized(String),
    NotFound(String),
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
            Self::Unauthorized(message) => (
                StatusCode::UNAUTHORIZED,
                Json(ErrorResponse { error: message }),
            )
                .into_response(),
            Self::NotFound(message) => (
                StatusCode::NOT_FOUND,
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
    let http_client = reqwest::Client::new();
    let sampled_slippage = Arc::new(SampledSlippageStore::new(&settings));
    match sampled_slippage.hydrate_from_disk().await {
        Ok(hydrated) => info!(
            hydrated_pairs = hydrated,
            sampled_slippage_state_path = %settings.sampled_slippage_state_path,
            sampled_slippage_stale_secs = settings.sampled_slippage_stale_secs,
            "sampled slippage warm-start hydration complete"
        ),
        Err(error) => tracing::warn!(
            error = %error,
            sampled_slippage_state_path = %settings.sampled_slippage_state_path,
            "sampled slippage warm-start hydration failed"
        ),
    }
    let state = AppState {
        repository,
        settings: settings.clone(),
        http_client,
        sampled_slippage,
    };

    let _slippage_worker = spawn_sampled_slippage_worker(state.clone());
    let _worker = spawn_reoptimize_worker(state.clone());
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/strategy/ui-auth/status", get(ui_auth_status))
        .route("/v1/strategy/ui-auth/verify", post(ui_auth_verify))
        .route("/v1/strategy/market/metrics", get(strategy_market_metrics))
        .route("/v1/strategy/pairs/cues", get(pairs_cues))
        .route("/v1/strategy/pairs/backtest", get(pairs_backtest))
        .route("/v1/strategy/pairs/live-z", get(pairs_live_z))
        .route("/v1/strategy/pairs/cost-gate", get(pairs_cost_gate))
        .route("/v1/strategy/pairs/expectancy", get(pairs_expectancy))
        .route("/v1/strategy/pairs/replay-trades", get(pairs_replay_trades))
        .route(
            "/v1/strategy/pairs/research-sweep",
            post(pairs_research_sweep),
        )
        .route("/v1/strategy/pairs/paper-trades", get(pairs_paper_trades))
        .route(
            "/v1/strategy/pairs/paper-trades/download",
            get(pairs_paper_trades_download),
        )
        .route(
            "/v1/strategy/pairs/opportunity-history",
            get(pairs_opportunity_history),
        )
        .route(
            "/v1/strategy/pairs/opportunity-history/download",
            get(pairs_opportunity_history_download),
        )
        .route(
            "/v1/strategy/pairs/opportunity-history/stats",
            get(pairs_opportunity_history_stats),
        )
        .route(
            "/v1/strategy/pairs/portfolio-plan",
            get(pairs_portfolio_plan),
        )
        .route("/v1/strategy/pairs/reoptimize", post(reoptimize))
        .route("/v1/strategy/maintenance/latest", get(maintenance_latest))
        .route(
            "/v1/strategy/maintenance/artifact",
            get(maintenance_artifact),
        )
        .route("/v1/strategy/maintenance/action", post(maintenance_action))
        .layer(cors)
        .with_state(state);

    let listener = TcpListener::bind(&settings.bind_addr).await?;
    info!(
        bind_addr = %settings.bind_addr,
        data_service_url = %settings.data_service_url,
        pairs = ?settings.pairs.iter().map(|p| p.pair_id()).collect::<Vec<_>>(),
        timeframes = ?settings.timeframes.iter().map(|t| t.as_str()).collect::<Vec<_>>(),
        entry_band = settings.entry_band,
        exit_band = settings.exit_band,
        stop_band = settings.stop_band,
        reopt_interval_secs = settings.reopt_interval_secs,
        shadow_ml_min_rows = settings.shadow_ml_min_rows,
        shadow_ml_training_limit = settings.shadow_ml_training_limit,
        trading_fee_bps = settings.trading_fee_bps,
        min_net_edge_bps = settings.min_net_edge_bps,
        sampled_slippage_interval_ms = settings.sampled_slippage_interval_ms,
        sampled_slippage_warmup_secs = settings.sampled_slippage_warmup_secs,
        sampled_slippage_stale_secs = settings.sampled_slippage_stale_secs,
        sampled_slippage_ewma_alpha = settings.sampled_slippage_ewma_alpha,
        sampled_slippage_state_path = %settings.sampled_slippage_state_path,
        sampled_slippage_persist_secs = settings.sampled_slippage_persist_secs,
        sampled_slippage_bootstrap_max_deviation_bps = settings.sampled_slippage_bootstrap_max_deviation_bps,
        paper_trade_persist_bars = settings.paper_trade_persist_bars,
        dynamic_funding_enabled = settings.dynamic_funding_enabled,
        funding_interval_secs = settings.funding_interval_secs,
        funding_phase_offset_secs = settings.funding_phase_offset_secs,
        funding_rate_bps_multiplier = settings.funding_rate_bps_multiplier,
        funding_positive_rate_means_longs_pay = settings.funding_positive_rate_means_longs_pay,
        funding_rate_input_mode = settings.funding_rate_input_mode.as_str(),
        advisory_enabled = settings.advisory_enabled,
        advisory_gross_cap = settings.advisory_gross_cap,
        advisory_per_pair_cap = settings.advisory_per_pair_cap,
        champion_switch_min_delta = settings.champion_switch_min_delta,
        block_on_champion_drift = settings.block_on_champion_drift,
        research_sweep_execution_cap = settings.research_sweep_execution_cap,
        research_sweep_top_k = settings.research_sweep_top_k,
        maintenance_report_path = %settings.maintenance_report_path,
        maintenance_artifacts_root = %settings.maintenance_artifacts_root,
        maintenance_apply_script_path = %settings.maintenance_apply_script_path,
        maintenance_env_file_path = %settings.maintenance_env_file_path,
        maintenance_deploy_script_path = %settings.maintenance_deploy_script_path,
        maintenance_action_output_root = %settings.maintenance_action_output_root,
        maintenance_action_queue_root = %settings.maintenance_action_queue_root,
        maintenance_action_timeout_secs = settings.maintenance_action_timeout_secs,
        maintenance_action_skip_pull = settings.maintenance_action_skip_pull,
        ui_access_enabled = settings.ui_access_enabled(),
        "strategy-service started"
    );

    axum::serve(listener, app).await?;
    Ok(())
}

fn spawn_sampled_slippage_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let interval_ms = state.settings.sampled_slippage_interval_ms.max(250);
        let mut interval = tokio::time::interval(std::time::Duration::from_millis(interval_ms));
        loop {
            interval.tick().await;
            match refresh_sampled_slippage(&state).await {
                Ok(_updated_pairs) => state.sampled_slippage.clear_poll_error().await,
                Err(error) => {
                    state
                        .sampled_slippage
                        .set_poll_error(error.to_string())
                        .await;
                    tracing::warn!(error = %error, "sampled slippage refresh failed");
                }
            }
        }
    })
}

async fn refresh_sampled_slippage(state: &AppState) -> anyhow::Result<usize> {
    let instruments = state.sampled_slippage.instruments_csv();
    if instruments.is_empty() {
        return Ok(0);
    }
    let upstream_base = state.settings.data_service_url.trim_end_matches('/');
    let upstream_url = reqwest::Url::parse_with_params(
        &format!("{upstream_base}/v1/market/metrics/batch"),
        &[("instruments", instruments.as_str())],
    )?;

    let response = state.http_client.get(upstream_url.clone()).send().await?;
    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        anyhow::bail!(
            "sampled slippage upstream status={} body={}",
            status.as_u16(),
            body
        );
    }
    let payload: StrategyMarketMetricsBatchResponse = response.json().await?;
    let sampled_at = payload.generated_at;
    let mut quotes = HashMap::new();
    for metric in payload.metrics {
        quotes.insert(metric.instrument.to_uppercase(), metric);
    }
    let updated = state
        .sampled_slippage
        .ingest_quotes(&quotes, sampled_at)
        .await;
    match state
        .sampled_slippage
        .persist_snapshot_if_due(sampled_at)
        .await
    {
        Ok(true) => {
            tracing::info!(
                sampled_at = %sampled_at,
                updated_pairs = updated,
                "sampled slippage checkpoint persisted"
            );
        }
        Ok(false) => {}
        Err(error) => {
            tracing::warn!(
                error = %error,
                sampled_at = %sampled_at,
                "sampled slippage checkpoint persist failed"
            );
        }
    }
    Ok(updated)
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
            let mut drift_rows_written = 0usize;
            let mut champion_promotions = 0usize;
            let mut champion_locks = 0usize;
            let mut shadow_model_runs_written = 0usize;
            let mut shadow_model_available = 0usize;
            let mut shadow_model_unavailable = 0usize;
            let mut cost_gate_pass = 0usize;
            let mut cost_gate_fail = 0usize;
            let mut portfolio_advice_available = 0usize;
            let mut portfolio_advice_unavailable = 0usize;

            for timeframe in &state.settings.timeframes {
                let (outputs, skipped, plan) = evaluate_timeframe_outputs(
                    &state,
                    *timeframe,
                    state.settings.advisory_enabled,
                    state.settings.trading_fee_bps,
                )
                .await;
                pairs_processed += state.settings.pairs.len();
                if plan.status == "AVAILABLE" {
                    portfolio_advice_available += 1;
                } else {
                    portfolio_advice_unavailable += 1;
                }
                for skipped_pair in skipped {
                    tracing::warn!(
                        pair_id = %skipped_pair.pair_id,
                        timeframe = %timeframe.as_str(),
                        reason = %skipped_pair.reason,
                        "strategy evaluation skipped"
                    );
                }

                for output in outputs {
                    cues_generated += usize::from(output.cue.actionable);
                    match output.cue.shadow_ml.status.as_str() {
                        "AVAILABLE" => shadow_model_available += 1,
                        _ => shadow_model_unavailable += 1,
                    }
                    if output.cue.cost_gate.status == "AVAILABLE" {
                        if output.cue.cost_gate.pass {
                            cost_gate_pass += 1;
                        } else {
                            cost_gate_fail += 1;
                        }
                    }

                    match state
                        .repository
                        .record_evaluation(
                            *timeframe,
                            &output,
                            state.settings.champion_switch_min_delta,
                        )
                        .await
                    {
                        Ok(summary) => {
                            performance_rows_written += summary.performance_rows_written;
                            selected_rows_written += summary.selected_rows_written;
                            drift_rows_written += summary.drift_rows_written;
                            champion_promotions += summary.champion_promotions;
                            champion_locks += summary.champion_locks;
                        }
                        Err(error) => {
                            tracing::warn!(
                                pair_id = %output.cue.pair_id,
                                timeframe = %timeframe.as_str(),
                                error = %error,
                                "failed to persist strategy evaluation"
                            );
                        }
                    }
                    match state
                        .repository
                        .record_shadow_model_run(*timeframe, &output)
                        .await
                    {
                        Ok(written) => shadow_model_runs_written += written,
                        Err(error) => {
                            tracing::warn!(
                                pair_id = %output.cue.pair_id,
                                timeframe = %timeframe.as_str(),
                                error = %error,
                                "failed to persist shadow model run"
                            );
                        }
                    }
                    if let Err(error) = state
                        .repository
                        .record_opportunity_history(*timeframe, &output)
                        .await
                    {
                        tracing::warn!(
                            pair_id = %output.cue.pair_id,
                            timeframe = %timeframe.as_str(),
                            error = %error,
                            "failed to persist opportunity history row"
                        );
                    }
                    let pair_spec = PairSpec {
                        left: output.cue.left_instrument.clone(),
                        right: output.cue.right_instrument.clone(),
                    };
                    if let Err(error) = compute_and_record_paper_trades_for_output(
                        &state, &pair_spec, *timeframe, &output,
                    )
                    .await
                    {
                        tracing::warn!(
                            pair_id = %output.cue.pair_id,
                            timeframe = %timeframe.as_str(),
                            error = %error,
                            "failed to persist paper trade rows"
                        );
                    }
                }
            }

            info!(
                pairs_processed,
                cues_generated,
                performance_rows_written,
                selected_rows_written,
                drift_rows_written,
                champion_promotions,
                champion_locks,
                shadow_model_runs_written,
                shadow_model_available,
                shadow_model_unavailable,
                cost_gate_pass,
                cost_gate_fail,
                portfolio_advice_available,
                portfolio_advice_unavailable,
                "strategy reoptimize tick complete"
            );
        }
    })
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn ui_auth_status(State(state): State<AppState>) -> Json<UiAuthStatusResponse> {
    Json(UiAuthStatusResponse {
        enabled: state.settings.ui_access_enabled(),
    })
}

async fn ui_auth_verify(
    State(state): State<AppState>,
    Json(request): Json<UiAuthVerifyRequest>,
) -> Result<Json<UiAuthVerifyResponse>, ApiError> {
    let configured_password = state.settings.ui_access_password.trim();
    if configured_password.is_empty() {
        return Ok(Json(UiAuthVerifyResponse { ok: true }));
    }
    if request.password == configured_password {
        return Ok(Json(UiAuthVerifyResponse { ok: true }));
    }
    Err(ApiError::Unauthorized("invalid password".to_string()))
}

async fn strategy_market_metrics(
    State(state): State<AppState>,
    Query(query): Query<StrategyMarketMetricsQuery>,
) -> Result<Json<StrategyMarketMetricsUiResponse>, ApiError> {
    let instrument = query.instrument.trim();
    if instrument.is_empty() {
        return Err(ApiError::BadRequest(
            "instrument query parameter is required".to_string(),
        ));
    }

    let upstream_base = state.settings.data_service_url.trim_end_matches('/');
    let upstream_url = reqwest::Url::parse_with_params(
        &format!("{upstream_base}/v1/market/metrics"),
        &[("instrument", instrument)],
    )
    .map_err(|error| ApiError::Upstream(format!("invalid upstream metrics url: {error}")))?;

    let response = reqwest::get(upstream_url.clone()).await.map_err(|error| {
        ApiError::Upstream(format!("market metrics upstream request failed: {error}"))
    })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(ApiError::Upstream(format!(
            "market metrics upstream status={} body={}",
            status.as_u16(),
            body
        )));
    }

    let payload: StrategyMarketMetricsResponse = response
        .json()
        .await
        .map_err(|error| ApiError::Upstream(format!("market metrics decode failed: {error}")))?;
    let normalized_funding_rate =
        normalize_funding_rate(payload.funding_rate, state.settings.funding_rate_input_mode);
    Ok(Json(StrategyMarketMetricsUiResponse {
        instrument: payload.instrument,
        server_time: payload.server_time,
        bid: payload.bid,
        ask: payload.ask,
        mark: payload.mark,
        index: payload.index,
        change_24h_pct: payload.change_24h_pct,
        funding_rate: normalized_funding_rate,
        open_interest: payload.open_interest,
        funding_interval_secs: state.settings.funding_interval_secs.max(1),
    }))
}

fn resolve_workspace_path(raw: &str) -> PathBuf {
    let path = PathBuf::from(raw);
    if path.is_absolute() {
        path
    } else {
        Path::new("/workspace").join(path)
    }
}

fn resolve_artifact_path(root: &Path, requested: &str) -> Result<PathBuf, ApiError> {
    if requested.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "artifact path is required".to_string(),
        ));
    }

    let requested_path = PathBuf::from(requested.trim());
    if requested_path.is_absolute() {
        return Err(ApiError::BadRequest(
            "absolute artifact path is not allowed".to_string(),
        ));
    }

    let canonical_root = root.canonicalize().map_err(|error| {
        ApiError::Upstream(format!(
            "unable to resolve artifact root '{}': {error}",
            root.display()
        ))
    })?;
    let mut candidates: Vec<PathBuf> = vec![requested_path.clone()];
    let workspace_root = Path::new("/workspace");
    if let Ok(root_relative) = canonical_root.strip_prefix(workspace_root) {
        if let Ok(stripped) = requested_path.strip_prefix(root_relative) {
            candidates.push(stripped.to_path_buf());
        }
    }
    if let Some(root_name) = canonical_root.file_name().and_then(|value| value.to_str()) {
        let components: Vec<_> = requested_path
            .components()
            .map(|component| component.as_os_str().to_string_lossy().to_string())
            .collect();
        if let Some(index) = components
            .iter()
            .position(|component| component == root_name)
        {
            let stripped =
                components
                    .iter()
                    .skip(index + 1)
                    .fold(PathBuf::new(), |mut acc, component| {
                        acc.push(component);
                        acc
                    });
            if !stripped.as_os_str().is_empty() {
                candidates.push(stripped);
            }
        }
    }

    let mut canonical_candidate: Option<PathBuf> = None;
    let mut last_candidate_path: Option<PathBuf> = None;
    for candidate_relative in candidates {
        if candidate_relative.as_os_str().is_empty() {
            continue;
        }
        let candidate = canonical_root.join(&candidate_relative);
        last_candidate_path = Some(candidate.clone());
        if let Ok(found) = candidate.canonicalize() {
            canonical_candidate = Some(found);
            break;
        }
    }
    let canonical_candidate = canonical_candidate.ok_or_else(|| {
        let display_path =
            last_candidate_path.unwrap_or_else(|| canonical_root.join(&requested_path));
        ApiError::NotFound(format!("artifact '{}' not found", display_path.display()))
    })?;

    if !canonical_candidate.starts_with(&canonical_root) {
        return Err(ApiError::BadRequest(
            "artifact path escapes configured root".to_string(),
        ));
    }
    if !canonical_candidate.is_file() {
        return Err(ApiError::NotFound(format!(
            "artifact '{}' is not a file",
            canonical_candidate.display()
        )));
    }

    Ok(canonical_candidate)
}

fn artifact_download_path(root: &Path, absolute_path: &Path) -> String {
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let canonical_target = absolute_path
        .canonicalize()
        .unwrap_or_else(|_| absolute_path.to_path_buf());
    if let Ok(relative) = canonical_target.strip_prefix(&canonical_root) {
        return relative.to_string_lossy().to_string();
    }
    canonical_target.to_string_lossy().to_string()
}

fn split_codes(raw: String) -> Vec<String> {
    raw.split('|')
        .filter_map(|item| {
            let trimmed = item.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        })
        .collect()
}

fn write_json_atomic(path: &Path, value: &impl Serialize) -> Result<(), ApiError> {
    let parent = path.parent().ok_or_else(|| {
        ApiError::Upstream(format!(
            "unable to resolve parent directory for '{}'",
            path.display()
        ))
    })?;
    std::fs::create_dir_all(parent).map_err(|error| {
        ApiError::Upstream(format!(
            "unable to create parent directory '{}': {error}",
            parent.display()
        ))
    })?;

    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    let tmp_name = format!(
        ".{}.tmp.{nanos}",
        path.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("queue-item")
    );
    let tmp_path = parent.join(tmp_name);
    let payload = serde_json::to_vec_pretty(value).map_err(|error| {
        ApiError::Upstream(format!("unable to serialize queue payload: {error}"))
    })?;
    std::fs::write(&tmp_path, payload).map_err(|error| {
        ApiError::Upstream(format!(
            "unable to write queue temp file '{}': {error}",
            tmp_path.display()
        ))
    })?;
    std::fs::rename(&tmp_path, path).map_err(|error| {
        ApiError::Upstream(format!(
            "unable to finalize queue file '{}': {error}",
            path.display()
        ))
    })?;
    Ok(())
}

fn content_type_for_path(path: &Path) -> &'static str {
    match path.extension().and_then(|value| value.to_str()) {
        Some("json") => "application/json",
        Some("log" | "txt") => "text/plain; charset=utf-8",
        Some("csv") => "text/csv; charset=utf-8",
        _ => "application/octet-stream",
    }
}

async fn maintenance_latest(State(state): State<AppState>) -> Json<MaintenanceLatestResponse> {
    let report_path = resolve_workspace_path(&state.settings.maintenance_report_path);
    let generated_at = Utc::now();
    let artifact_download_route = "/v1/strategy/maintenance/artifact?path=".to_string();

    let read_result = std::fs::read_to_string(&report_path);
    let (available, report, reason) = match read_result {
        Ok(raw) => match serde_json::from_str::<serde_json::Value>(&raw) {
            Ok(parsed) => (true, Some(parsed), None),
            Err(error) => (
                false,
                None,
                Some(format!(
                    "unable to parse maintenance report '{}': {error}",
                    report_path.display()
                )),
            ),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (
            false,
            None,
            Some(format!(
                "maintenance report not found at '{}'",
                report_path.display()
            )),
        ),
        Err(error) => (
            false,
            None,
            Some(format!(
                "unable to read maintenance report '{}': {error}",
                report_path.display()
            )),
        ),
    };

    Json(MaintenanceLatestResponse {
        available,
        generated_at,
        report,
        reason,
        artifact_download_route,
    })
}

async fn maintenance_artifact(
    State(state): State<AppState>,
    Query(query): Query<MaintenanceArtifactQuery>,
) -> Result<Response, ApiError> {
    let artifact_root = resolve_workspace_path(&state.settings.maintenance_artifacts_root);
    let artifact_path = resolve_artifact_path(&artifact_root, &query.path)?;

    let content = std::fs::read(&artifact_path).map_err(|error| {
        ApiError::NotFound(format!(
            "unable to read artifact '{}': {error}",
            artifact_path.display()
        ))
    })?;
    let filename = artifact_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("artifact.bin");

    let mut headers = HeaderMap::new();
    headers.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static(content_type_for_path(&artifact_path)),
    );
    let disposition = format!("attachment; filename=\"{filename}\"");
    let disposition_value = HeaderValue::from_str(&disposition).map_err(|error| {
        ApiError::Upstream(format!("unable to set content disposition header: {error}"))
    })?;
    headers.insert(header::CONTENT_DISPOSITION, disposition_value);

    Ok((StatusCode::OK, headers, content).into_response())
}

async fn maintenance_action(
    State(state): State<AppState>,
    Json(request): Json<MaintenanceActionRequest>,
) -> Result<Json<MaintenanceActionResponse>, ApiError> {
    let action = MaintenanceAction::parse(&request.action).ok_or_else(|| {
        ApiError::BadRequest("invalid action; expected PROMOTE or REVERT".to_string())
    })?;
    let operator_id = request.operator_id.trim().to_string();
    if operator_id.is_empty() {
        return Err(ApiError::BadRequest(
            "operator_id is required for maintenance actions".to_string(),
        ));
    }
    if !request.confirm {
        return Err(ApiError::BadRequest(
            "confirm=true is required to run maintenance actions".to_string(),
        ));
    }

    let generated_at = Utc::now();
    let artifact_root = resolve_workspace_path(&state.settings.maintenance_artifacts_root);
    let output_root = resolve_workspace_path(&state.settings.maintenance_action_output_root);
    let queue_root = resolve_workspace_path(&state.settings.maintenance_action_queue_root);
    let queue_pending_dir = queue_root.join("pending");
    let queue_processing_dir = queue_root.join("processing");
    let queue_completed_dir = queue_root.join("completed");
    let queue_failed_dir = queue_root.join("failed");
    std::fs::create_dir_all(&output_root).map_err(|error| {
        ApiError::Upstream(format!(
            "unable to create action output directory '{}': {error}",
            output_root.display()
        ))
    })?;
    for directory in [
        &queue_pending_dir,
        &queue_processing_dir,
        &queue_completed_dir,
        &queue_failed_dir,
    ] {
        std::fs::create_dir_all(directory).map_err(|error| {
            ApiError::Upstream(format!(
                "unable to create maintenance queue directory '{}': {error}",
                directory.display()
            ))
        })?;
    }

    let stamp = generated_at.format("%Y-%m-%dT%H-%M-%SZ");
    let request_id = format!("{}-{}", stamp, action.script_mode());
    let output_filename = format!("{}-{}-apply.json", stamp, action.script_mode());
    let output_path = output_root.join(output_filename);
    let queue_filename = format!("{request_id}-request.json");
    let queue_path = queue_pending_dir.join(queue_filename);

    let apply_script_path = resolve_workspace_path(&state.settings.maintenance_apply_script_path);
    let env_file_path = resolve_workspace_path(&state.settings.maintenance_env_file_path);
    let deploy_script_path = resolve_workspace_path(&state.settings.maintenance_deploy_script_path);
    let queue_item = MaintenanceActionQueueItem {
        request_id: request_id.clone(),
        action: action.as_str().to_string(),
        mode: action.script_mode().to_string(),
        operator_id: operator_id.clone(),
        queued_at: generated_at,
        apply_script_path: apply_script_path.to_string_lossy().to_string(),
        policy_json_path: "infra/config/strategy_tuning_policy.json".to_string(),
        env_file_path: env_file_path.to_string_lossy().to_string(),
        deploy_script_path: deploy_script_path.to_string_lossy().to_string(),
        services: "strategy-service".to_string(),
        output_json_path: output_path.to_string_lossy().to_string(),
        skip_pull: state.settings.maintenance_action_skip_pull,
        timeout_secs: state.settings.maintenance_action_timeout_secs.max(1),
    };
    write_json_atomic(&queue_path, &queue_item)?;

    let report_download_path = artifact_download_path(&artifact_root, &output_path);
    let queue_download_path = artifact_download_path(&artifact_root, &queue_path);
    let report = Some(serde_json::json!({
        "status": "QUEUED",
        "request_id": request_id,
        "queue_request_path": queue_download_path,
        "expected_report_path": report_download_path,
        "queued_at": generated_at,
    }));
    info!(
        action = action.as_str(),
        operator_id = %operator_id,
        queue_path = %queue_path.display(),
        report_path = %report_download_path,
        "maintenance action queued"
    );

    Ok(Json(MaintenanceActionResponse {
        accepted: true,
        action: action.as_str().to_string(),
        operator_id,
        pass: true,
        generated_at,
        report_download_path,
        report,
        error: None,
    }))
}

async fn pairs_cues(
    State(state): State<AppState>,
    Query(query): Query<CuesQuery>,
) -> Result<Json<CuesResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let limit = query.limit.unwrap_or(20).clamp(1, 100);
    let include_advisory = query
        .include_advisory
        .unwrap_or(state.settings.advisory_enabled);
    let taker_fee_bps = resolve_taker_fee_bps(query.taker_fee_bps, state.settings.trading_fee_bps)?;
    let (mut outputs, skipped, portfolio_plan) =
        evaluate_timeframe_outputs(&state, timeframe, include_advisory, taker_fee_bps).await;

    let mut cues = vec![];
    for output in outputs.drain(..) {
        let preferred_signal = state
            .repository
            .fetch_selected_signal(&output.cue.pair_id, timeframe)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?;

        let mut cue = output.cue.clone();
        if let Some(preferred) = preferred_signal {
            if preferred.signal_variant != output.cue.selected_variant {
                cue.rationale_codes.push("CHAMPION_DRIFT".to_string());
                cue.rationale_codes
                    .push(format!("CHAMPION_SELECTED:{}", preferred.signal_variant));
                cue.rationale_codes.push(format!(
                    "CHALLENGER_SELECTED:{}",
                    output.cue.selected_variant
                ));
                cue.selected_variant = preferred.signal_variant;
                cue.opportunity_score = preferred.opportunity_score;
                if state.settings.block_on_champion_drift {
                    cue.setup_actionable = false;
                    cue.actionable = false;
                    cue.direction_hint = "NONE".to_string();
                    cue.rationale_codes
                        .push("CHAMPION_DRIFT_BLOCKED".to_string());
                }
            }
        }
        refresh_setup_gate(&mut cue);
        finalize_trade_gate(&mut cue);

        cues.push(CueWithDiagnostics {
            cue,
            variants: output.variants,
            half_life_bars: output.half_life_bars,
            hedge_ratio: output.hedge_ratio,
            hedge_ratio_stability: output.hedge_ratio_stability,
        });
    }

    let candidate_set = CandidateSetDiagnostics {
        total_pairs: state.settings.pairs.len(),
        evaluated_pairs: cues.len(),
        actionable_pairs: cues.iter().filter(|item| item.cue.actionable).count(),
        cost_gate_pass_pairs: cues
            .iter()
            .filter(|item| item.cue.cost_gate.status == "AVAILABLE" && item.cue.cost_gate.pass)
            .count(),
        shadow_disagreement_pairs: cues
            .iter()
            .filter(|item| {
                item.cue.shadow_ml.status == "AVAILABLE" && !item.cue.shadow_ml.agrees_with_selected
            })
            .count(),
    };

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
        candidate_set,
        portfolio_plan,
        skipped,
    }))
}

async fn pairs_cost_gate(
    State(state): State<AppState>,
    Query(query): Query<CuesQuery>,
) -> Result<Json<CostGateResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let taker_fee_bps = resolve_taker_fee_bps(query.taker_fee_bps, state.settings.trading_fee_bps)?;
    let (outputs, skipped, _plan) = evaluate_timeframe_outputs(
        &state,
        timeframe,
        state.settings.advisory_enabled,
        taker_fee_bps,
    )
    .await;

    let gates = outputs
        .into_iter()
        .map(|output| CostGatePair {
            pair_id: output.cue.pair_id,
            left_instrument: output.cue.left_instrument,
            right_instrument: output.cue.right_instrument,
            timeframe: output.cue.timeframe,
            expected_edge_bps: output.cue.cost_gate.expected_edge_bps,
            fee_bps: output.cue.cost_gate.fee_bps,
            funding_model: output.cue.cost_gate.funding_model,
            funding_events: output.cue.cost_gate.funding_events,
            funding_bps_per_event: output.cue.cost_gate.funding_bps_per_event,
            funding_bps: output.cue.cost_gate.funding_bps,
            slippage_bps: output.cue.cost_gate.slippage_bps,
            net_edge_bps: output.cue.cost_gate.net_edge_bps,
            pass: output.cue.cost_gate.pass,
            setup_pass: output.cue.setup_gate.pass,
            trade_ready: output.cue.trade_gate.pass,
            trade_blocked_by: output.cue.trade_gate.blocked_by,
            rationale_codes: output.cue.cost_gate.rationale_codes,
        })
        .collect::<Vec<_>>();

    Ok(Json(CostGateResponse {
        timeframe: timeframe.as_str().to_string(),
        generated_at: Utc::now(),
        gates,
        skipped,
    }))
}

fn resolve_taker_fee_bps(override_value: Option<f64>, default_value: f64) -> Result<f64, ApiError> {
    match override_value {
        Some(value) if value.is_finite() && (0.0..=10_000.0).contains(&value) => Ok(value),
        Some(_) => Err(ApiError::BadRequest(
            "invalid taker_fee_bps; expected finite value in range [0, 10000]".to_string(),
        )),
        None => Ok(default_value.max(0.0)),
    }
}

fn parse_backtest_exit_mode(raw: Option<&str>) -> Result<BacktestExitMode, ApiError> {
    match raw {
        None => Ok(BacktestExitMode::MeanRevert),
        Some(value) => BacktestExitMode::parse(value).ok_or_else(|| {
            ApiError::BadRequest(
                "invalid exit_mode; expected mean_revert or opposite_extreme".to_string(),
            )
        }),
    }
}

fn parse_opportunity_history_window(
    query: &OpportunityHistoryQuery,
) -> Result<(Timeframe, i64, bool, i64), ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let hours = query.hours.unwrap_or(12).clamp(1, 168);
    let only_pass = query.only_pass.unwrap_or(true);
    let limit = query.limit.unwrap_or(5_000).clamp(1, 20_000) as i64;
    Ok((timeframe, hours, only_pass, limit))
}

fn parse_opportunity_history_stats_timeframe(
    query: &OpportunityHistoryStatsQuery,
) -> Result<Option<Timeframe>, ApiError> {
    let Some(raw_timeframe) = query.timeframe.as_ref() else {
        return Ok(None);
    };
    let timeframe = Timeframe::parse(raw_timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    Ok(Some(timeframe))
}

fn parse_paper_trades_window(
    query: &PaperTradesQuery,
) -> Result<(Timeframe, Option<String>, String, i64, i64), ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let hours = query.hours.unwrap_or(24).clamp(1, 175_200);
    let limit = query.limit.unwrap_or(5_000).clamp(1, 20_000) as i64;
    let pair_id = query
        .pair_id
        .as_ref()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let exit_mode = parse_backtest_exit_mode(query.exit_mode.as_deref())?
        .as_str()
        .to_string();
    Ok((timeframe, pair_id, exit_mode, hours, limit))
}

fn parse_z_method(raw: Option<&str>) -> Result<String, ApiError> {
    let normalized = raw
        .map(|value| value.trim().to_ascii_uppercase())
        .unwrap_or_else(|| "ROBUST_Z".to_string());
    match normalized.as_str() {
        "COINTEGRATION_Z" | "ROBUST_Z" | "VOL_NORMALIZED" | "FUNDING_ADJUSTED" => {
            Ok(normalized)
        }
        _ => Err(ApiError::BadRequest(
            "invalid z_method; expected COINTEGRATION_Z, ROBUST_Z, VOL_NORMALIZED, FUNDING_ADJUSTED"
                .to_string(),
        )),
    }
}

fn parse_expectancy_config(
    entry_z: Option<f64>,
    exit_z: Option<f64>,
    stop_z: Option<f64>,
    z_method: Option<&str>,
    lookback_bars: Option<usize>,
    settings: &StrategySettings,
) -> Result<ExpectancyConfig, ApiError> {
    let entry = entry_z.unwrap_or(settings.entry_band.abs());
    if !entry.is_finite() || !(0.2..=8.0).contains(&entry) {
        return Err(ApiError::BadRequest(
            "invalid entry_z; expected finite value in range [0.2, 8.0]".to_string(),
        ));
    }

    let exit = exit_z.unwrap_or(settings.exit_band.abs());
    if !exit.is_finite() || !(0.0..entry).contains(&exit) {
        return Err(ApiError::BadRequest(format!(
            "invalid exit_z; expected finite value in range [0.0, {entry})"
        )));
    }

    let stop = stop_z.unwrap_or(settings.stop_band.abs());
    if !stop.is_finite() || !(entry..=12.0).contains(&stop) {
        return Err(ApiError::BadRequest(format!(
            "invalid stop_z; expected finite value in range ({entry}, 12.0]"
        )));
    }

    let z_method = parse_z_method(z_method)?;
    let lookback = lookback_bars.unwrap_or(analytics_model_bars(Timeframe::OneHour));
    let lookback = lookback.clamp(120, 10_000);

    Ok(ExpectancyConfig {
        entry_z: entry,
        exit_z: exit,
        stop_z: stop,
        z_method,
        hedge_method: "HEDGE_RATIO_OLS".to_string(),
        lookback_bars: lookback,
    })
}

fn parse_expectancy_query(
    query: &ExpectancyQuery,
    settings: &StrategySettings,
) -> Result<(Timeframe, String, ExpectancyConfig), ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let pair_id = query.pair_id.trim().to_string();
    if pair_id.is_empty() {
        return Err(ApiError::BadRequest("pair_id is required".to_string()));
    }
    let mut config = parse_expectancy_config(
        query.entry_z,
        query.exit_z,
        query.stop_z,
        query.z_method.as_deref(),
        query.lookback_bars,
        settings,
    )?;
    config.lookback_bars = config.lookback_bars.max(analytics_model_bars(timeframe));
    Ok((timeframe, pair_id, config))
}

fn parse_replay_trades_query(
    query: &ReplayTradesQuery,
    settings: &StrategySettings,
) -> Result<(Timeframe, String, i64, i64, String, ExpectancyConfig), ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let pair_id = query.pair_id.trim().to_string();
    if pair_id.is_empty() {
        return Err(ApiError::BadRequest("pair_id is required".to_string()));
    }
    let hours = query.hours.unwrap_or(168).clamp(1, 175_200);
    let limit = query.limit.unwrap_or(500).clamp(1, 20_000) as i64;
    let exit_mode = parse_backtest_exit_mode(query.exit_mode.as_deref())?
        .as_str()
        .to_string();
    let mut config = parse_expectancy_config(
        query.entry_z,
        query.exit_z,
        query.stop_z,
        query.z_method.as_deref(),
        query.lookback_bars,
        settings,
    )?;
    config.lookback_bars = config.lookback_bars.max(analytics_model_bars(timeframe));
    Ok((timeframe, pair_id, hours, limit, exit_mode, config))
}

#[cfg(test)]
fn estimate_research_combinations(payload: &ResearchSweepRequest) -> usize {
    let tf = payload.timeframes.as_ref().map_or(3, Vec::len).max(1);
    let pairs = payload.pair_ids.as_ref().map_or(16, Vec::len).max(1);
    let entry = payload.entry_z_grid.as_ref().map_or(5, Vec::len).max(1);
    let exit = payload.exit_z_grid.as_ref().map_or(5, Vec::len).max(1);
    let stop = payload.stop_z_grid.as_ref().map_or(4, Vec::len).max(1);
    let z_methods = payload.z_methods.as_ref().map_or(1, Vec::len).max(1);
    let lookback = payload
        .lookback_bars_grid
        .as_ref()
        .map_or(4, Vec::len)
        .max(1);
    tf.saturating_mul(pairs)
        .saturating_mul(entry)
        .saturating_mul(exit)
        .saturating_mul(stop)
        .saturating_mul(z_methods)
        .saturating_mul(lookback)
}

fn estimate_research_combinations_resolved(
    timeframe_count: usize,
    pair_count: usize,
    entry_count: usize,
    exit_count: usize,
    stop_count: usize,
    z_method_count: usize,
    lookback_count: usize,
) -> usize {
    timeframe_count
        .max(1)
        .saturating_mul(pair_count.max(1))
        .saturating_mul(entry_count.max(1))
        .saturating_mul(exit_count.max(1))
        .saturating_mul(stop_count.max(1))
        .saturating_mul(z_method_count.max(1))
        .saturating_mul(lookback_count.max(1))
}

fn expectancy_z_method_supported(z_method: &str) -> bool {
    z_method == "ROBUST_Z"
}

fn classify_expectancy_result(
    metrics: Option<&ExpectancyMetrics>,
) -> (String, String, String, Vec<String>) {
    match metrics {
        Some(metrics)
            if metrics.trades >= 5 && metrics.avg_net_bps > 0.0 && metrics.win_rate >= 0.5 =>
        {
            (
                "AVAILABLE".to_string(),
                "TRADE_READY".to_string(),
                "EXPECTANCY_POSITIVE".to_string(),
                vec![
                    "EXPECTANCY_COMPUTED".to_string(),
                    "MIN_TRADES_MET".to_string(),
                ],
            )
        }
        Some(metrics) if metrics.trades < 5 => (
            "AVAILABLE".to_string(),
            "CAUTION".to_string(),
            "LOW_TRADE_COUNT".to_string(),
            vec![
                "EXPECTANCY_COMPUTED".to_string(),
                "LOW_TRADE_COUNT".to_string(),
            ],
        ),
        Some(_) => (
            "AVAILABLE".to_string(),
            "BLOCKED".to_string(),
            "EXPECTANCY_NON_POSITIVE".to_string(),
            vec![
                "EXPECTANCY_COMPUTED".to_string(),
                "EXPECTANCY_NON_POSITIVE".to_string(),
            ],
        ),
        None => (
            "UNAVAILABLE".to_string(),
            "CAUTION".to_string(),
            "NO_COMPLETED_TRADES".to_string(),
            vec![
                "NO_COMPLETED_TRADES".to_string(),
                "EXPECTANCY_NOT_COMPUTED".to_string(),
            ],
        ),
    }
}

fn expectancy_objective_score(metrics: &ExpectancyMetrics) -> f64 {
    let trade_weight = (metrics.trades as f64).ln_1p().max(1.0);
    metrics.expected_min_lot_net_bps * metrics.win_rate * trade_weight
}

fn default_sweep_entry_grid() -> &'static [f64] {
    &[1.4, 1.6, 1.8, 2.0, 2.2]
}

fn default_sweep_exit_grid() -> &'static [f64] {
    &[0.2, 0.4, 0.6, 0.8, 1.0]
}

fn default_sweep_stop_grid() -> &'static [f64] {
    &[2.8, 3.2, 3.6, 4.0]
}

fn default_sweep_lookback_grid() -> &'static [usize] {
    &[220, 440, 880, 1200]
}

fn resolve_unique_sorted_f64_grid(
    values: Option<&Vec<f64>>,
    defaults: &[f64],
    min_value: f64,
    max_value: f64,
    label: &str,
) -> Result<Vec<f64>, ApiError> {
    let source = values.map_or(defaults.to_vec(), Clone::clone);
    let mut dedup = HashSet::new();
    let mut resolved = Vec::with_capacity(source.len());
    for value in source {
        if !value.is_finite() || value < min_value || value > max_value {
            return Err(ApiError::BadRequest(format!(
                "invalid {label} grid value '{value}'; expected finite value in range [{min_value}, {max_value}]"
            )));
        }
        if dedup.insert(value.to_bits()) {
            resolved.push(value);
        }
    }
    resolved.sort_by(|left, right| left.total_cmp(right));
    if resolved.is_empty() {
        return Err(ApiError::BadRequest(format!(
            "{label} grid cannot be empty"
        )));
    }
    Ok(resolved)
}

fn resolve_unique_sorted_usize_grid(
    values: Option<&Vec<usize>>,
    defaults: &[usize],
    min_value: usize,
    max_value: usize,
    label: &str,
) -> Result<Vec<usize>, ApiError> {
    let source = values.map_or(defaults.to_vec(), Clone::clone);
    let mut dedup = HashSet::new();
    let mut resolved = Vec::with_capacity(source.len());
    for value in source {
        if value < min_value || value > max_value {
            return Err(ApiError::BadRequest(format!(
                "invalid {label} grid value '{value}'; expected value in range [{min_value}, {max_value}]"
            )));
        }
        if dedup.insert(value) {
            resolved.push(value);
        }
    }
    resolved.sort_unstable();
    if resolved.is_empty() {
        return Err(ApiError::BadRequest(format!(
            "{label} grid cannot be empty"
        )));
    }
    Ok(resolved)
}

fn analytics_model_bars(timeframe: Timeframe) -> usize {
    match timeframe {
        Timeframe::OneMinute => 300,
        Timeframe::FifteenMinutes => 280,
        Timeframe::OneHour => 220,
    }
}

fn days_covered(first: Option<DateTime<Utc>>, last: Option<DateTime<Utc>>) -> f64 {
    match (first, last) {
        (Some(start), Some(end)) if end >= start => {
            let seconds = (end - start).num_seconds() as f64;
            (seconds / 86_400.0).max(0.0)
        }
        _ => 0.0,
    }
}

#[derive(Debug, Clone)]
struct OpenPaperTrade {
    point_index: usize,
    ts: DateTime<Utc>,
    z: f64,
    equity_pre_entry: f64,
    left_entry: f64,
    right_entry: f64,
}

fn infer_trade_direction(entry_z: f64, exit_z: f64, entry_band: f64) -> &'static str {
    if entry_z <= -entry_band {
        "LONG_SPREAD"
    } else if entry_z >= entry_band {
        "SHORT_SPREAD"
    } else if exit_z >= entry_z {
        "LONG_SPREAD"
    } else {
        "SHORT_SPREAD"
    }
}

fn lookup_constraints(instrument: &str) -> Option<InstrumentTradingConstraints> {
    kraken_perp_constraints(instrument)
}

fn lookup_pair_constraints(
    left_instrument: &str,
    right_instrument: &str,
) -> (
    Option<InstrumentTradingConstraints>,
    Option<InstrumentTradingConstraints>,
) {
    (
        lookup_constraints(left_instrument),
        lookup_constraints(right_instrument),
    )
}

#[derive(Debug, Clone)]
struct OpenReplayTrade {
    point_index: usize,
    ts: DateTime<Utc>,
    z: f64,
    equity_pre_entry: f64,
}

fn derive_replay_trades_from_series(
    pair_id: &str,
    timeframe: Timeframe,
    series: &strategy_service::BacktestSeries,
    entry_band: f64,
) -> Vec<ReplayTradeEntry> {
    let mut open_trade: Option<OpenReplayTrade> = None;
    let mut rows = vec![];

    for marker in &series.markers {
        if marker.index >= series.points.len() {
            continue;
        }
        let point = &series.points[marker.index];
        if marker.kind == "entry" {
            let equity_pre_entry = if marker.index == 0 {
                1.0
            } else {
                series.points[marker.index - 1].equity
            };
            open_trade = Some(OpenReplayTrade {
                point_index: marker.index,
                ts: point.ts,
                z: point.z,
                equity_pre_entry,
            });
            continue;
        }

        if marker.kind != "exit" && marker.kind != "stop" {
            continue;
        }
        let Some(entry) = open_trade.take() else {
            continue;
        };
        let equity_pre_entry = entry.equity_pre_entry;
        if !equity_pre_entry.is_finite() || equity_pre_entry <= 0.0 {
            continue;
        }
        let direction = infer_trade_direction(entry.z, point.z, entry_band).to_string();
        let bars_held = marker.index.saturating_sub(entry.point_index).max(1);
        let mut mae_bps = f64::INFINITY;
        let mut mfe_bps = f64::NEG_INFINITY;
        let mut bars_underwater = 0usize;
        for path_point in &series.points[entry.point_index..=marker.index] {
            let path_bps = ((path_point.equity / equity_pre_entry) - 1.0) * 10_000.0;
            mae_bps = mae_bps.min(path_bps);
            mfe_bps = mfe_bps.max(path_bps);
            if path_bps < 0.0 {
                bars_underwater = bars_underwater.saturating_add(1);
            }
        }
        let net_bps = ((point.equity / equity_pre_entry) - 1.0) * 10_000.0;

        rows.push(ReplayTradeEntry {
            trade_id: format!(
                "{}|{}|{}|{}",
                pair_id,
                timeframe.as_str(),
                entry.ts.to_rfc3339(),
                point.ts.to_rfc3339()
            ),
            entry_ts: entry.ts,
            exit_ts: point.ts,
            direction,
            entry_z: entry.z,
            exit_z: point.z,
            net_bps,
            path: ReplayTradePathSummary {
                mae_bps: if mae_bps.is_finite() { mae_bps } else { 0.0 },
                mfe_bps: if mfe_bps.is_finite() { mfe_bps } else { 0.0 },
                bars_underwater,
                bars_held,
            },
        });
    }

    rows
}

fn percentile(values: &[f64], quantile: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if sorted.is_empty() {
        return 0.0;
    }
    sorted.sort_by(|left, right| left.total_cmp(right));
    let q = quantile.clamp(0.0, 1.0);
    let rank = q * (sorted.len().saturating_sub(1) as f64);
    let lower = rank.floor() as usize;
    let upper = rank.ceil() as usize;
    if lower == upper {
        return sorted[lower];
    }
    let weight = rank - lower as f64;
    sorted[lower] * (1.0 - weight) + sorted[upper] * weight
}

fn compute_expectancy_metrics(
    rows: &[ReplayTradeEntry],
    left_last: f64,
    right_last: f64,
    hedge_ratio: f64,
    left_constraints: Option<InstrumentTradingConstraints>,
    right_constraints: Option<InstrumentTradingConstraints>,
) -> Option<ExpectancyMetrics> {
    if rows.is_empty() {
        return None;
    }
    let net = rows.iter().map(|row| row.net_bps).collect::<Vec<_>>();
    let wins = rows.iter().filter(|row| row.net_bps > 0.0).count();
    let avg_net_bps = net.iter().sum::<f64>() / net.len() as f64;
    let avg_hold_bars = rows
        .iter()
        .map(|row| row.path.bars_held as f64)
        .sum::<f64>()
        / rows.len() as f64;
    let avg_mae_bps = rows.iter().map(|row| row.path.mae_bps).sum::<f64>() / rows.len() as f64;
    let avg_mfe_bps = rows.iter().map(|row| row.path.mfe_bps).sum::<f64>() / rows.len() as f64;
    let left_min_lot = left_constraints
        .map(|constraints| constraints.min_lot)
        .filter(|value| value.is_finite() && *value > 0.0)
        .unwrap_or(1.0);
    let target_right_qty = hedge_ratio.abs().max(1e-9) * left_min_lot;
    let right_min_lot = right_constraints
        .map(|constraints| constraints.min_lot)
        .filter(|value| value.is_finite() && *value > 0.0);
    let right_qty = if let Some(step) = right_min_lot {
        let steps = (target_right_qty / step).round().max(1.0);
        steps * step
    } else {
        target_right_qty
    };
    let gross_min_lot_notional = left_last.abs() * left_min_lot + right_last.abs() * right_qty;
    let expected_min_lot_net_usd =
        if gross_min_lot_notional.is_finite() && gross_min_lot_notional > 0.0 {
            gross_min_lot_notional * avg_net_bps / 10_000.0
        } else {
            0.0
        };

    Some(ExpectancyMetrics {
        trades: rows.len(),
        win_rate: wins as f64 / rows.len() as f64,
        avg_net_bps,
        p25_net_bps: percentile(&net, 0.25),
        p50_net_bps: percentile(&net, 0.50),
        p75_net_bps: percentile(&net, 0.75),
        avg_hold_bars,
        avg_mae_bps,
        avg_mfe_bps,
        expected_min_lot_net_bps: avg_net_bps,
        expected_min_lot_net_usd,
    })
}

#[allow(clippy::too_many_arguments)]
fn derive_paper_trades_from_series(
    pair_id: &str,
    timeframe: Timeframe,
    exit_mode: BacktestExitMode,
    left_instrument: &str,
    right_instrument: &str,
    selected_variant: &str,
    entry_band: f64,
    hedge_ratio: f64,
    round_trip_cost_bps: f64,
    left_constraints: Option<InstrumentTradingConstraints>,
    right_constraints: Option<InstrumentTradingConstraints>,
    timestamps: &[DateTime<Utc>],
    left_closes: &[f64],
    right_closes: &[f64],
    series: &strategy_service::BacktestSeries,
) -> Vec<PaperTradeInsertRow> {
    if series.points.is_empty()
        || timestamps.len() != left_closes.len()
        || timestamps.len() != right_closes.len()
        || timestamps.len() != series.points.len() + 1
    {
        return vec![];
    }

    let mut open_trade: Option<OpenPaperTrade> = None;
    let mut rows = vec![];
    for marker in &series.markers {
        if marker.index >= series.points.len() {
            continue;
        }
        let close_index = marker.index + 1;
        if close_index >= timestamps.len() {
            continue;
        }
        let point = &series.points[marker.index];
        let ts = timestamps[close_index];

        if marker.kind == "entry" {
            let equity_pre_entry = if marker.index == 0 {
                1.0
            } else {
                series.points[marker.index - 1].equity
            };
            let left_entry = if let Some(constraints) = left_constraints {
                quantize_price_to_tick(left_closes[close_index], constraints.tick_size)
                    .unwrap_or(left_closes[close_index])
            } else {
                left_closes[close_index]
            };
            let right_entry = if let Some(constraints) = right_constraints {
                quantize_price_to_tick(right_closes[close_index], constraints.tick_size)
                    .unwrap_or(right_closes[close_index])
            } else {
                right_closes[close_index]
            };
            open_trade = Some(OpenPaperTrade {
                point_index: marker.index,
                ts,
                z: point.z,
                equity_pre_entry,
                left_entry,
                right_entry,
            });
            continue;
        }

        if marker.kind != "exit" && marker.kind != "stop" {
            continue;
        }
        let Some(entry) = open_trade.take() else {
            continue;
        };
        let direction = infer_trade_direction(entry.z, point.z, entry_band);
        let left_exit = if let Some(constraints) = left_constraints {
            quantize_price_to_tick(left_closes[close_index], constraints.tick_size)
                .unwrap_or(left_closes[close_index])
        } else {
            left_closes[close_index]
        };
        let right_exit = if let Some(constraints) = right_constraints {
            quantize_price_to_tick(right_closes[close_index], constraints.tick_size)
                .unwrap_or(right_closes[close_index])
        } else {
            right_closes[close_index]
        };
        if entry.left_entry <= 0.0
            || entry.right_entry <= 0.0
            || left_exit <= 0.0
            || right_exit <= 0.0
        {
            continue;
        }

        let left_return = (left_exit / entry.left_entry) - 1.0;
        let right_return = (right_exit / entry.right_entry) - 1.0;
        let ratio = hedge_ratio.abs().max(1e-9);
        let (raw_left_bps, raw_right_bps) = if direction == "LONG_SPREAD" {
            (left_return * 10_000.0, -(ratio * right_return * 10_000.0))
        } else {
            (-left_return * 10_000.0, ratio * right_return * 10_000.0)
        };
        let equity_pre_entry = entry.equity_pre_entry;
        let equity_exit = point.equity;
        let equity_trade_bps = if equity_pre_entry > 0.0 {
            ((equity_exit / equity_pre_entry) - 1.0) * 10_000.0
        } else {
            0.0
        };
        let cost_bps = if round_trip_cost_bps.is_finite() {
            round_trip_cost_bps.max(0.0)
        } else {
            0.0
        };
        let net_bps = equity_trade_bps;
        let gross_bps = net_bps + cost_bps;
        let raw_sum = raw_left_bps + raw_right_bps;
        let (left_leg_bps, right_leg_bps) = if raw_sum.is_finite() && raw_sum.abs() > 1e-9 {
            let scale = gross_bps / raw_sum;
            (raw_left_bps * scale, raw_right_bps * scale)
        } else {
            (gross_bps * 0.5, gross_bps * 0.5)
        };

        rows.push(PaperTradeInsertRow {
            pair_id: pair_id.to_string(),
            timeframe: timeframe.as_str().to_string(),
            exit_mode: exit_mode.as_str().to_string(),
            left_instrument: left_instrument.to_string(),
            right_instrument: right_instrument.to_string(),
            selected_variant: selected_variant.to_string(),
            entry_ts: entry.ts,
            exit_ts: ts,
            bars_held: (marker.index.saturating_sub(entry.point_index)).max(1) as i32,
            direction: direction.to_string(),
            exit_kind: marker.kind.clone(),
            entry_z: entry.z,
            exit_z: point.z,
            entry_index: entry.point_index as i32,
            exit_index: marker.index as i32,
            left_entry: entry.left_entry,
            left_exit,
            right_entry: entry.right_entry,
            right_exit,
            left_leg_bps,
            right_leg_bps,
            gross_bps,
            round_trip_cost_bps: cost_bps,
            net_bps,
            equity_pre_entry,
            equity_exit,
            equity_trade_bps,
        });
    }
    rows
}

async fn compute_and_record_paper_trades_for_output(
    state: &AppState,
    pair: &PairSpec,
    timeframe: Timeframe,
    output: &PairEvaluationOutput,
) -> anyhow::Result<u64> {
    let lookback = analytics_model_bars(timeframe).max(120) as i64;
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
        return Ok(0);
    }

    let (left_constraints, right_constraints) = lookup_pair_constraints(&pair.left, &pair.right);
    let exit_mode = BacktestExitMode::MeanRevert;
    let series = compute_backtest_series(
        &timestamps,
        &left_closes,
        &right_closes,
        BacktestConfig {
            hedge_ratio: output.hedge_ratio,
            entry_band: output.cue.entry_band,
            exit_band: output.cue.exit_band,
            stop_band: output.cue.stop_band,
            round_trip_cost_bps: output.cue.cost_estimate_bps,
            exit_mode,
            left_constraints,
            right_constraints,
        },
    );
    let rows = derive_paper_trades_from_series(
        &output.cue.pair_id,
        timeframe,
        exit_mode,
        &output.cue.left_instrument,
        &output.cue.right_instrument,
        &output.cue.selected_variant,
        output.cue.entry_band,
        output.hedge_ratio,
        output.cue.cost_estimate_bps,
        left_constraints,
        right_constraints,
        &timestamps,
        &left_closes,
        &right_closes,
        &series,
    );
    state
        .repository
        .replace_paper_trades(&output.cue.pair_id, timeframe, exit_mode.as_str(), &rows)
        .await
}

async fn build_opportunity_history_response(
    state: &AppState,
    query: &OpportunityHistoryQuery,
) -> Result<OpportunityHistoryResponse, ApiError> {
    let (timeframe, hours, only_pass, limit) = parse_opportunity_history_window(query)?;
    let since = Utc::now() - chrono::Duration::hours(hours);
    let rows = state
        .repository
        .fetch_opportunity_history(timeframe, since, only_pass, limit)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    Ok(OpportunityHistoryResponse {
        timeframe: timeframe.as_str().to_string(),
        generated_at: Utc::now(),
        hours,
        only_pass,
        rows,
    })
}

async fn pairs_opportunity_history(
    State(state): State<AppState>,
    Query(query): Query<OpportunityHistoryQuery>,
) -> Result<Json<OpportunityHistoryResponse>, ApiError> {
    Ok(Json(
        build_opportunity_history_response(&state, &query).await?,
    ))
}

async fn pairs_opportunity_history_stats(
    State(state): State<AppState>,
    Query(query): Query<OpportunityHistoryStatsQuery>,
) -> Result<Json<OpportunityHistoryStatsResponse>, ApiError> {
    let timeframe_filter = parse_opportunity_history_stats_timeframe(&query)?;
    let by_timeframe = state
        .repository
        .fetch_opportunity_history_stats(timeframe_filter)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let total_rows = by_timeframe.iter().map(|row| row.rows).sum::<i64>();
    let first = by_timeframe
        .iter()
        .filter_map(|row| row.first_evaluated_at)
        .min();
    let last = by_timeframe
        .iter()
        .filter_map(|row| row.last_evaluated_at)
        .max();

    Ok(Json(OpportunityHistoryStatsResponse {
        generated_at: Utc::now(),
        timeframe_filter: timeframe_filter.map(|value| value.as_str().to_string()),
        total_rows,
        first_evaluated_at: first,
        last_evaluated_at: last,
        days_covered: days_covered(first, last),
        by_timeframe,
    }))
}

async fn pairs_opportunity_history_download(
    State(state): State<AppState>,
    Query(query): Query<OpportunityHistoryQuery>,
) -> Result<Response, ApiError> {
    let payload = build_opportunity_history_response(&state, &query).await?;
    let mut headers = HeaderMap::new();
    headers.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json"),
    );
    headers.insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&format!(
            "attachment; filename=\"opportunity-history-{}-{}h.json\"",
            payload.timeframe, payload.hours
        ))
        .map_err(|error| ApiError::Upstream(error.to_string()))?,
    );
    let body = serde_json::to_vec_pretty(&payload)
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    Ok((StatusCode::OK, headers, body).into_response())
}

async fn build_paper_trades_response(
    state: &AppState,
    query: &PaperTradesQuery,
) -> Result<PaperTradesResponse, ApiError> {
    let (timeframe, pair_id, exit_mode, hours, limit) = parse_paper_trades_window(query)?;
    let since = Utc::now() - chrono::Duration::hours(hours);
    let rows = state
        .repository
        .fetch_paper_trades(timeframe, pair_id.as_deref(), &exit_mode, since, limit)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    Ok(PaperTradesResponse {
        timeframe: timeframe.as_str().to_string(),
        generated_at: Utc::now(),
        hours,
        pair_id,
        exit_mode,
        model_bars: analytics_model_bars(timeframe),
        rows,
    })
}

async fn pairs_paper_trades(
    State(state): State<AppState>,
    Query(query): Query<PaperTradesQuery>,
) -> Result<Json<PaperTradesResponse>, ApiError> {
    Ok(Json(build_paper_trades_response(&state, &query).await?))
}

async fn pairs_paper_trades_download(
    State(state): State<AppState>,
    Query(query): Query<PaperTradesQuery>,
) -> Result<Response, ApiError> {
    let payload = build_paper_trades_response(&state, &query).await?;
    let mut headers = HeaderMap::new();
    headers.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json"),
    );
    let pair_suffix = payload
        .pair_id
        .as_ref()
        .map(|value| format!("-{}", value.replace("__", "-")))
        .unwrap_or_default();
    headers.insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&format!(
            "attachment; filename=\"paper-trades-{}{}-{}h.json\"",
            payload.timeframe, pair_suffix, payload.hours
        ))
        .map_err(|error| ApiError::Upstream(error.to_string()))?,
    );
    let body = serde_json::to_vec_pretty(&payload)
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    Ok((StatusCode::OK, headers, body).into_response())
}

async fn pairs_expectancy(
    State(state): State<AppState>,
    Query(query): Query<ExpectancyQuery>,
) -> Result<Json<ExpectancyResponse>, ApiError> {
    let (timeframe, pair_id, config) = parse_expectancy_query(&query, &state.settings)?;
    if !expectancy_z_method_supported(&config.z_method) {
        return Ok(Json(ExpectancyResponse {
            timeframe: timeframe.as_str().to_string(),
            pair_id,
            generated_at: Utc::now(),
            status: "UNAVAILABLE".to_string(),
            decision_state: "CAUTION".to_string(),
            primary_reason_code: "Z_METHOD_NOT_IMPLEMENTED".to_string(),
            config,
            metrics: None,
            rationale_codes: vec![
                "Z_METHOD_NOT_IMPLEMENTED".to_string(),
                "EXPECTANCY_REQUIRES_ROBUST_Z".to_string(),
            ],
        }));
    }

    let Some(pair) = state
        .settings
        .pairs
        .iter()
        .find(|candidate| candidate.pair_id() == pair_id)
    else {
        return Err(ApiError::BadRequest(format!(
            "pair_id '{}' is not configured",
            pair_id
        )));
    };
    let lookback = (config.lookback_bars.saturating_add(32).max(120)) as i64;
    let left = state
        .repository
        .fetch_recent_closes(&pair.left, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let right = state
        .repository
        .fetch_recent_closes(&pair.right, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (timestamps, left_closes, right_closes) = align_closes(left, right);
    if timestamps.len() < 120 {
        return Ok(Json(ExpectancyResponse {
            timeframe: timeframe.as_str().to_string(),
            pair_id,
            generated_at: Utc::now(),
            status: "UNAVAILABLE".to_string(),
            decision_state: "CAUTION".to_string(),
            primary_reason_code: "INSUFFICIENT_ALIGNED_CANDLES".to_string(),
            config,
            metrics: None,
            rationale_codes: vec![
                "INSUFFICIENT_ALIGNED_CANDLES".to_string(),
                "EXPECTANCY_NOT_COMPUTED".to_string(),
            ],
        }));
    }
    let start_idx = timestamps
        .len()
        .saturating_sub(config.lookback_bars.saturating_add(1));
    let timestamps = &timestamps[start_idx..];
    let left_closes = &left_closes[start_idx..];
    let right_closes = &right_closes[start_idx..];
    if timestamps.len() < 2 {
        return Ok(Json(ExpectancyResponse {
            timeframe: timeframe.as_str().to_string(),
            pair_id,
            generated_at: Utc::now(),
            status: "UNAVAILABLE".to_string(),
            decision_state: "CAUTION".to_string(),
            primary_reason_code: "INSUFFICIENT_MODEL_WINDOW".to_string(),
            config,
            metrics: None,
            rationale_codes: vec![
                "INSUFFICIENT_MODEL_WINDOW".to_string(),
                "EXPECTANCY_NOT_COMPUTED".to_string(),
            ],
        }));
    }

    let output = evaluate_pair_for_timeframe(
        &state,
        pair,
        timeframe,
        false,
        state.settings.trading_fee_bps,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (left_constraints, right_constraints) = lookup_pair_constraints(&pair.left, &pair.right);
    let series = compute_backtest_series(
        timestamps,
        left_closes,
        right_closes,
        BacktestConfig {
            hedge_ratio: output.hedge_ratio,
            entry_band: config.entry_z,
            exit_band: config.exit_z,
            stop_band: config.stop_z,
            round_trip_cost_bps: output.cue.cost_estimate_bps,
            exit_mode: BacktestExitMode::MeanRevert,
            left_constraints,
            right_constraints,
        },
    );
    let replay_rows =
        derive_replay_trades_from_series(&pair_id, timeframe, &series, config.entry_z);
    let metrics = compute_expectancy_metrics(
        &replay_rows,
        *left_closes.last().unwrap_or(&0.0),
        *right_closes.last().unwrap_or(&0.0),
        output.hedge_ratio,
        left_constraints,
        right_constraints,
    );
    info!(
        timeframe = %timeframe.as_str(),
        pair_id = %pair_id,
        entry_z = config.entry_z,
        exit_z = config.exit_z,
        stop_z = config.stop_z,
        z_method = %config.z_method,
        lookback_bars = config.lookback_bars,
        replay_rows = replay_rows.len(),
        status = if metrics.is_some() { "AVAILABLE" } else { "UNAVAILABLE" },
        "expectancy query computed"
    );
    let (status, decision_state, primary_reason_code, rationale_codes) =
        classify_expectancy_result(metrics.as_ref());
    Ok(Json(ExpectancyResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id,
        generated_at: Utc::now(),
        status,
        decision_state,
        primary_reason_code,
        config,
        metrics,
        rationale_codes,
    }))
}

async fn pairs_replay_trades(
    State(state): State<AppState>,
    Query(query): Query<ReplayTradesQuery>,
) -> Result<Json<ReplayTradesResponse>, ApiError> {
    let (timeframe, pair_id, hours, limit, exit_mode, config) =
        parse_replay_trades_query(&query, &state.settings)?;
    if !expectancy_z_method_supported(&config.z_method) {
        return Ok(Json(ReplayTradesResponse {
            timeframe: timeframe.as_str().to_string(),
            pair_id,
            generated_at: Utc::now(),
            status: "UNAVAILABLE".to_string(),
            model_bars: config.lookback_bars,
            hours,
            limit,
            exit_mode,
            config,
            rationale_codes: vec![
                "Z_METHOD_NOT_IMPLEMENTED".to_string(),
                "REPLAY_REQUIRES_ROBUST_Z".to_string(),
            ],
            rows: vec![],
        }));
    }
    let Some(pair) = state
        .settings
        .pairs
        .iter()
        .find(|candidate| candidate.pair_id() == pair_id)
    else {
        return Err(ApiError::BadRequest(format!(
            "pair_id '{}' is not configured",
            pair_id
        )));
    };
    let requested_bars = (hours
        .saturating_mul(3600)
        .div_euclid(timeframe.step_seconds())
        .max(120) as usize)
        .max(config.lookback_bars);
    let lookback = requested_bars.saturating_add(32) as i64;
    let left = state
        .repository
        .fetch_recent_closes(&pair.left, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let right = state
        .repository
        .fetch_recent_closes(&pair.right, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (timestamps, left_closes, right_closes) = align_closes(left, right);
    if timestamps.len() < 120 {
        return Ok(Json(ReplayTradesResponse {
            timeframe: timeframe.as_str().to_string(),
            pair_id,
            generated_at: Utc::now(),
            status: "UNAVAILABLE".to_string(),
            model_bars: requested_bars,
            hours,
            limit,
            exit_mode,
            config,
            rationale_codes: vec![
                "INSUFFICIENT_ALIGNED_CANDLES".to_string(),
                "REPLAY_NOT_COMPUTED".to_string(),
            ],
            rows: vec![],
        }));
    }
    let start_idx = timestamps
        .len()
        .saturating_sub(requested_bars.saturating_add(1));
    let timestamps = &timestamps[start_idx..];
    let left_closes = &left_closes[start_idx..];
    let right_closes = &right_closes[start_idx..];
    let output = evaluate_pair_for_timeframe(
        &state,
        pair,
        timeframe,
        false,
        state.settings.trading_fee_bps,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (left_constraints, right_constraints) = lookup_pair_constraints(&pair.left, &pair.right);
    let parsed_exit_mode = parse_backtest_exit_mode(Some(&exit_mode))?;
    let series = compute_backtest_series(
        timestamps,
        left_closes,
        right_closes,
        BacktestConfig {
            hedge_ratio: output.hedge_ratio,
            entry_band: config.entry_z,
            exit_band: config.exit_z,
            stop_band: config.stop_z,
            round_trip_cost_bps: output.cue.cost_estimate_bps,
            exit_mode: parsed_exit_mode,
            left_constraints,
            right_constraints,
        },
    );
    let cutoff = Utc::now() - chrono::Duration::hours(hours);
    let mut rows = derive_replay_trades_from_series(&pair_id, timeframe, &series, config.entry_z)
        .into_iter()
        .filter(|row| row.exit_ts >= cutoff)
        .collect::<Vec<_>>();
    rows.sort_by(|left, right| right.exit_ts.cmp(&left.exit_ts));
    rows.truncate(limit as usize);
    info!(
        timeframe = %timeframe.as_str(),
        pair_id = %pair_id,
        hours,
        limit,
        exit_mode = %exit_mode,
        lookback_bars = config.lookback_bars,
        replay_rows = rows.len(),
        status = if rows.is_empty() { "UNAVAILABLE" } else { "AVAILABLE" },
        "replay-trades query computed"
    );
    let (status, rationale_codes) = if rows.is_empty() {
        (
            "UNAVAILABLE".to_string(),
            vec![
                "NO_COMPLETED_TRADES_IN_WINDOW".to_string(),
                "REPLAY_NOT_COMPUTED".to_string(),
            ],
        )
    } else {
        (
            "AVAILABLE".to_string(),
            vec![
                "REPLAY_COMPUTED".to_string(),
                "BACKTEST_MARKERS_DERIVED".to_string(),
            ],
        )
    };
    Ok(Json(ReplayTradesResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id,
        generated_at: Utc::now(),
        status,
        model_bars: requested_bars,
        hours,
        limit,
        exit_mode,
        config,
        rationale_codes,
        rows,
    }))
}

#[derive(Debug, Clone)]
struct SweepDataset {
    left_instrument: String,
    right_instrument: String,
    timestamps: Vec<DateTime<Utc>>,
    left_closes: Vec<f64>,
    right_closes: Vec<f64>,
    hedge_ratio: f64,
    round_trip_cost_bps: f64,
}

fn build_sweep_candidate(
    timeframe: Timeframe,
    pair_id: &str,
    config: &ExpectancyConfig,
    dataset: &SweepDataset,
) -> ResearchSweepCandidateResponse {
    let required_points = config.lookback_bars.saturating_add(1);
    if dataset.timestamps.len() < required_points
        || dataset.left_closes.len() != dataset.timestamps.len()
        || dataset.right_closes.len() != dataset.timestamps.len()
    {
        return ResearchSweepCandidateResponse {
            rank: 0,
            timeframe: timeframe.as_str().to_string(),
            pair_id: pair_id.to_string(),
            config: config.clone(),
            status: "UNAVAILABLE".to_string(),
            decision_state: "CAUTION".to_string(),
            primary_reason_code: "INSUFFICIENT_MODEL_WINDOW".to_string(),
            objective_score: f64::NEG_INFINITY,
            metrics: None,
            rationale_codes: vec![
                "INSUFFICIENT_MODEL_WINDOW".to_string(),
                "SWEEP_CANDIDATE_NOT_COMPUTED".to_string(),
            ],
        };
    }

    let start_idx = dataset.timestamps.len().saturating_sub(required_points);
    let timestamps = &dataset.timestamps[start_idx..];
    let left_closes = &dataset.left_closes[start_idx..];
    let right_closes = &dataset.right_closes[start_idx..];
    let (left_constraints, right_constraints) =
        lookup_pair_constraints(&dataset.left_instrument, &dataset.right_instrument);

    let series = compute_backtest_series(
        timestamps,
        left_closes,
        right_closes,
        BacktestConfig {
            hedge_ratio: dataset.hedge_ratio,
            entry_band: config.entry_z,
            exit_band: config.exit_z,
            stop_band: config.stop_z,
            round_trip_cost_bps: dataset.round_trip_cost_bps,
            exit_mode: BacktestExitMode::MeanRevert,
            left_constraints,
            right_constraints,
        },
    );
    let replay_rows = derive_replay_trades_from_series(pair_id, timeframe, &series, config.entry_z);
    let metrics = compute_expectancy_metrics(
        &replay_rows,
        *left_closes.last().unwrap_or(&0.0),
        *right_closes.last().unwrap_or(&0.0),
        dataset.hedge_ratio,
        left_constraints,
        right_constraints,
    );
    let (status, decision_state, primary_reason_code, mut rationale_codes) =
        classify_expectancy_result(metrics.as_ref());
    let objective_score = metrics
        .as_ref()
        .map(expectancy_objective_score)
        .unwrap_or(f64::NEG_INFINITY);
    rationale_codes.push("SWEEP_EXIT_MODE_MEAN_REVERT".to_string());

    ResearchSweepCandidateResponse {
        rank: 0,
        timeframe: timeframe.as_str().to_string(),
        pair_id: pair_id.to_string(),
        config: config.clone(),
        status,
        decision_state,
        primary_reason_code,
        objective_score,
        metrics,
        rationale_codes,
    }
}

async fn pairs_research_sweep(
    State(state): State<AppState>,
    Json(payload): Json<ResearchSweepRequest>,
) -> Result<Json<ResearchSweepResponse>, ApiError> {
    let timeframes = if let Some(values) = payload.timeframes.as_ref() {
        let mut parsed = Vec::with_capacity(values.len());
        for value in values {
            let parsed_tf = Timeframe::parse(value).ok_or_else(|| {
                ApiError::BadRequest(format!(
                    "invalid timeframe '{}' in research sweep request",
                    value
                ))
            })?;
            parsed.push(parsed_tf.as_str().to_string());
        }
        if parsed.is_empty() {
            state
                .settings
                .timeframes
                .iter()
                .map(|item| item.as_str().to_string())
                .collect::<Vec<_>>()
        } else {
            parsed
        }
    } else {
        state
            .settings
            .timeframes
            .iter()
            .map(|item| item.as_str().to_string())
            .collect::<Vec<_>>()
    };

    let pair_ids = payload
        .pair_ids
        .as_ref()
        .map(|values| {
            values
                .iter()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
        })
        .filter(|values| !values.is_empty())
        .unwrap_or_else(|| {
            state
                .settings
                .pairs
                .iter()
                .map(|pair| pair.pair_id())
                .collect()
        });

    let max_combinations = payload
        .max_combinations
        .unwrap_or(20_000)
        .clamp(1, 1_000_000);
    let dry_run = payload.dry_run.unwrap_or(true);
    let request_id = format!("sweep-{}", Utc::now().format("%Y%m%dT%H%M%S%.3fZ"));
    let entry_grid = resolve_unique_sorted_f64_grid(
        payload.entry_z_grid.as_ref(),
        default_sweep_entry_grid(),
        0.2,
        8.0,
        "entry_z",
    )?;
    let exit_grid = resolve_unique_sorted_f64_grid(
        payload.exit_z_grid.as_ref(),
        default_sweep_exit_grid(),
        0.0,
        8.0,
        "exit_z",
    )?;
    let stop_grid = resolve_unique_sorted_f64_grid(
        payload.stop_z_grid.as_ref(),
        default_sweep_stop_grid(),
        0.2,
        12.0,
        "stop_z",
    )?;
    let lookback_grid = resolve_unique_sorted_usize_grid(
        payload.lookback_bars_grid.as_ref(),
        default_sweep_lookback_grid(),
        120,
        10_000,
        "lookback_bars",
    )?;

    let z_methods = payload.z_methods.as_ref().map_or_else(
        || Ok(vec!["ROBUST_Z".to_string()]),
        |values| {
            let mut methods = values
                .iter()
                .map(|value| parse_z_method(Some(value.as_str())))
                .collect::<Result<Vec<_>, _>>()?;
            methods.sort_unstable();
            methods.dedup();
            if methods.is_empty() {
                return Ok(vec!["ROBUST_Z".to_string()]);
            }
            Ok(methods)
        },
    )?;
    let unsupported_z_method = z_methods
        .iter()
        .any(|z_method| !expectancy_z_method_supported(z_method));
    let estimated_combinations = estimate_research_combinations_resolved(
        timeframes.len(),
        pair_ids.len(),
        entry_grid.len(),
        exit_grid.len(),
        stop_grid.len(),
        z_methods.len(),
        lookback_grid.len(),
    );

    info!(
        request_id = %request_id,
        dry_run,
        max_combinations,
        estimated_combinations,
        execution_cap = state.settings.research_sweep_execution_cap,
        unsupported_z_method,
        timeframe_count = timeframes.len(),
        pair_count = pair_ids.len(),
        "research sweep request evaluated"
    );

    let mut rationale_codes = vec![];
    let mut status = if unsupported_z_method {
        rationale_codes.push("UNSUPPORTED_Z_METHOD_IN_SWEEP".to_string());
        "UNAVAILABLE"
    } else if estimated_combinations > max_combinations {
        rationale_codes.push("COMBINATION_LIMIT_EXCEEDED".to_string());
        "UNAVAILABLE"
    } else if !dry_run && estimated_combinations > state.settings.research_sweep_execution_cap {
        rationale_codes.push("EXECUTION_CAP_EXCEEDED".to_string());
        "UNAVAILABLE"
    } else if dry_run {
        rationale_codes.push("RESEARCH_SWEEP_DRY_RUN_READY".to_string());
        "AVAILABLE"
    } else {
        rationale_codes.push("RESEARCH_SWEEP_EXECUTION_STARTED".to_string());
        "AVAILABLE"
    };
    if estimated_combinations > max_combinations {
        rationale_codes.push("RESEARCH_SWEEP_NOT_ACCEPTED".to_string());
    }
    if !dry_run && estimated_combinations > state.settings.research_sweep_execution_cap {
        rationale_codes.push("RESEARCH_SWEEP_NOT_ACCEPTED".to_string());
    }

    let mut executed_combinations = 0usize;
    let mut successful_combinations = 0usize;
    let mut failed_combinations = 0usize;
    let mut top_candidates = vec![];
    let mut best_candidate = None;
    let top_k = state.settings.research_sweep_top_k;

    if status == "AVAILABLE" && !dry_run {
        let mut pair_lookup = HashMap::new();
        for pair in &state.settings.pairs {
            pair_lookup.insert(pair.pair_id(), pair.clone());
        }
        let max_lookback = lookback_grid
            .iter()
            .copied()
            .max()
            .unwrap_or_else(|| analytics_model_bars(Timeframe::OneHour))
            .saturating_add(32) as i64;
        let mut dataset_cache: HashMap<(String, String), SweepDataset> = HashMap::new();
        for timeframe in &timeframes {
            let tf = Timeframe::parse(timeframe).ok_or_else(|| {
                ApiError::BadRequest(format!(
                    "invalid timeframe '{}' in research sweep request",
                    timeframe
                ))
            })?;
            for pair_id in &pair_ids {
                let Some(pair) = pair_lookup.get(pair_id) else {
                    return Err(ApiError::BadRequest(format!(
                        "pair_id '{}' is not configured",
                        pair_id
                    )));
                };
                let left = state
                    .repository
                    .fetch_recent_closes(&pair.left, tf, max_lookback)
                    .await
                    .map_err(|error| ApiError::Upstream(error.to_string()))?;
                let right = state
                    .repository
                    .fetch_recent_closes(&pair.right, tf, max_lookback)
                    .await
                    .map_err(|error| ApiError::Upstream(error.to_string()))?;
                let (timestamps, left_closes, right_closes) = align_closes(left, right);
                if timestamps.len() < 120 {
                    continue;
                }
                let output = evaluate_pair_for_timeframe(
                    &state,
                    pair,
                    tf,
                    false,
                    state.settings.trading_fee_bps,
                )
                .await
                .map_err(|error| ApiError::Upstream(error.to_string()))?;
                dataset_cache.insert(
                    (timeframe.clone(), pair_id.clone()),
                    SweepDataset {
                        left_instrument: pair.left.clone(),
                        right_instrument: pair.right.clone(),
                        timestamps,
                        left_closes,
                        right_closes,
                        hedge_ratio: output.hedge_ratio,
                        round_trip_cost_bps: output.cue.cost_estimate_bps.max(0.0),
                    },
                );
            }
        }

        let mut ranked = vec![];
        for timeframe in &timeframes {
            let tf = Timeframe::parse(timeframe).ok_or_else(|| {
                ApiError::BadRequest(format!(
                    "invalid timeframe '{}' in research sweep request",
                    timeframe
                ))
            })?;
            for pair_id in &pair_ids {
                for z_method in &z_methods {
                    for lookback in &lookback_grid {
                        for entry in &entry_grid {
                            for exit in &exit_grid {
                                for stop in &stop_grid {
                                    executed_combinations = executed_combinations.saturating_add(1);
                                    let mut config = match parse_expectancy_config(
                                        Some(*entry),
                                        Some(*exit),
                                        Some(*stop),
                                        Some(z_method.as_str()),
                                        Some(*lookback),
                                        &state.settings,
                                    ) {
                                        Ok(value) => value,
                                        Err(_) => {
                                            failed_combinations =
                                                failed_combinations.saturating_add(1);
                                            continue;
                                        }
                                    };
                                    config.lookback_bars =
                                        config.lookback_bars.max(analytics_model_bars(tf));

                                    let Some(dataset) =
                                        dataset_cache.get(&(timeframe.clone(), pair_id.clone()))
                                    else {
                                        failed_combinations = failed_combinations.saturating_add(1);
                                        continue;
                                    };
                                    let candidate =
                                        build_sweep_candidate(tf, pair_id, &config, dataset);
                                    if candidate.metrics.is_some() {
                                        successful_combinations =
                                            successful_combinations.saturating_add(1);
                                        ranked.push(candidate);
                                    } else {
                                        failed_combinations = failed_combinations.saturating_add(1);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        ranked.sort_by(|left, right| {
            right
                .objective_score
                .total_cmp(&left.objective_score)
                .then_with(|| {
                    right
                        .metrics
                        .as_ref()
                        .map_or(0.0, |metrics| metrics.p50_net_bps)
                        .total_cmp(
                            &left
                                .metrics
                                .as_ref()
                                .map_or(0.0, |metrics| metrics.p50_net_bps),
                        )
                })
                .then_with(|| {
                    right
                        .metrics
                        .as_ref()
                        .map_or(0.0, |metrics| metrics.win_rate)
                        .total_cmp(
                            &left
                                .metrics
                                .as_ref()
                                .map_or(0.0, |metrics| metrics.win_rate),
                        )
                })
        });

        top_candidates = ranked
            .into_iter()
            .take(top_k)
            .enumerate()
            .map(|(index, mut candidate)| {
                candidate.rank = index + 1;
                candidate
            })
            .collect::<Vec<_>>();
        best_candidate = top_candidates.first().cloned();
        if top_candidates.is_empty() {
            status = "UNAVAILABLE";
            rationale_codes.push("RESEARCH_SWEEP_NO_VALID_RESULTS".to_string());
        } else {
            rationale_codes.push("RESEARCH_SWEEP_EXECUTED".to_string());
        }
        info!(
            request_id = %request_id,
            dry_run = false,
            estimated_combinations,
            executed_combinations,
            successful_combinations,
            failed_combinations,
            top_candidates = top_candidates.len(),
            best_objective_score = best_candidate
                .as_ref()
                .map(|candidate| candidate.objective_score),
            "research sweep execution completed"
        );
    }

    Ok(Json(ResearchSweepResponse {
        generated_at: Utc::now(),
        status: status.to_string(),
        request_id,
        dry_run,
        timeframes,
        pair_ids,
        estimated_combinations,
        executed_combinations,
        successful_combinations,
        failed_combinations,
        top_k,
        best_candidate,
        top_candidates,
        max_combinations,
        rationale_codes,
    }))
}

async fn pairs_backtest(
    State(state): State<AppState>,
    Query(query): Query<BacktestQuery>,
) -> Result<Json<BacktestResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let exit_mode = parse_backtest_exit_mode(query.exit_mode.as_deref())?;
    let bars = query.bars.unwrap_or(300).clamp(120, 2_000);
    let Some(pair) = state
        .settings
        .pairs
        .iter()
        .find(|candidate| candidate.pair_id() == query.pair_id)
    else {
        return Err(ApiError::BadRequest(format!(
            "pair_id '{}' is not configured",
            query.pair_id
        )));
    };

    let lookback = std::cmp::max(state.settings.lookback_bars(timeframe), bars + 32) as i64;
    let left = state
        .repository
        .fetch_recent_closes(&pair.left, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let right = state
        .repository
        .fetch_recent_closes(&pair.right, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let (timestamps, left_closes, right_closes) = align_closes(left, right);
    if timestamps.len() < 120 {
        return Err(ApiError::Upstream(format!(
            "insufficient aligned candles for pair={} timeframe={} bars={}",
            query.pair_id,
            timeframe.as_str(),
            timestamps.len()
        )));
    }

    let start_idx = timestamps.len().saturating_sub(bars + 1);
    let timestamps = &timestamps[start_idx..];
    let left_closes = &left_closes[start_idx..];
    let right_closes = &right_closes[start_idx..];

    let taker_fee_bps = resolve_taker_fee_bps(query.taker_fee_bps, state.settings.trading_fee_bps)?;
    let output = evaluate_pair_for_timeframe(
        &state,
        pair,
        timeframe,
        state.settings.advisory_enabled,
        taker_fee_bps,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (left_constraints, right_constraints) = lookup_pair_constraints(&pair.left, &pair.right);

    let series = compute_backtest_series(
        timestamps,
        left_closes,
        right_closes,
        BacktestConfig {
            hedge_ratio: output.hedge_ratio,
            entry_band: output.cue.entry_band,
            exit_band: output.cue.exit_band,
            stop_band: output.cue.stop_band,
            round_trip_cost_bps: output.cue.cost_estimate_bps,
            exit_mode,
            left_constraints,
            right_constraints,
        },
    );

    if series.points.is_empty() {
        return Err(ApiError::Upstream(format!(
            "unable to compute backtest points for pair={} timeframe={}",
            query.pair_id,
            timeframe.as_str()
        )));
    }

    tracing::info!(
        pair_id = %query.pair_id,
        timeframe = %timeframe.as_str(),
        exit_mode = %exit_mode.as_str(),
        bars,
        points = series.points.len(),
        markers = series.markers.len(),
        "strategy backtest response generated"
    );

    Ok(Json(BacktestResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id: query.pair_id,
        generated_at: Utc::now(),
        exit_mode: exit_mode.as_str().to_string(),
        left_instrument: output.cue.left_instrument,
        right_instrument: output.cue.right_instrument,
        selected_variant: output.cue.selected_variant,
        hedge_ratio: output.hedge_ratio,
        entry_band: output.cue.entry_band,
        exit_band: output.cue.exit_band,
        stop_band: output.cue.stop_band,
        round_trip_cost_bps: output.cue.cost_estimate_bps,
        points: series
            .points
            .into_iter()
            .map(|point| BacktestPointResponse {
                ts: point.ts,
                z: point.z,
                equity: point.equity,
            })
            .collect(),
        markers: series
            .markers
            .into_iter()
            .map(|marker| BacktestMarkerResponse {
                index: marker.index,
                kind: marker.kind,
            })
            .collect(),
        rationale_codes: output.cue.rationale_codes,
    }))
}

async fn pairs_live_z(
    State(state): State<AppState>,
    Query(query): Query<LiveZQuery>,
) -> Result<Json<LiveZResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let exit_mode = parse_backtest_exit_mode(query.exit_mode.as_deref())?;
    let points = query.points.unwrap_or(300).clamp(120, 2_000);
    let Some(pair) = state
        .settings
        .pairs
        .iter()
        .find(|candidate| candidate.pair_id() == query.pair_id)
    else {
        return Err(ApiError::BadRequest(format!(
            "pair_id '{}' is not configured",
            query.pair_id
        )));
    };

    let lookback = std::cmp::max(state.settings.lookback_bars(timeframe), points + 32) as i64;
    let left = state
        .repository
        .fetch_recent_closes(&pair.left, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let right = state
        .repository
        .fetch_recent_closes(&pair.right, timeframe, lookback)
        .await
        .map_err(|error| ApiError::Upstream(error.to_string()))?;

    let (timestamps, left_closes, right_closes) = align_closes(left, right);
    if timestamps.len() < 120 {
        return Err(ApiError::Upstream(format!(
            "insufficient aligned candles for pair={} timeframe={} bars={}",
            query.pair_id,
            timeframe.as_str(),
            timestamps.len()
        )));
    }

    let start_idx = timestamps.len().saturating_sub(points + 1);
    let timestamps = &timestamps[start_idx..];
    let left_closes = &left_closes[start_idx..];
    let right_closes = &right_closes[start_idx..];

    let taker_fee_bps = resolve_taker_fee_bps(query.taker_fee_bps, state.settings.trading_fee_bps)?;
    let output = evaluate_pair_for_timeframe(
        &state,
        pair,
        timeframe,
        state.settings.advisory_enabled,
        taker_fee_bps,
    )
    .await
    .map_err(|error| ApiError::Upstream(error.to_string()))?;
    let (left_constraints, right_constraints) = lookup_pair_constraints(&pair.left, &pair.right);
    let series = compute_backtest_series(
        timestamps,
        left_closes,
        right_closes,
        BacktestConfig {
            hedge_ratio: output.hedge_ratio,
            entry_band: output.cue.entry_band,
            exit_band: output.cue.exit_band,
            stop_band: output.cue.stop_band,
            round_trip_cost_bps: output.cue.cost_estimate_bps,
            exit_mode,
            left_constraints,
            right_constraints,
        },
    );
    if series.points.is_empty() {
        return Err(ApiError::Upstream(format!(
            "unable to compute live z-series for pair={} timeframe={}",
            query.pair_id,
            timeframe.as_str()
        )));
    }

    tracing::info!(
        pair_id = %query.pair_id,
        timeframe = %timeframe.as_str(),
        exit_mode = %exit_mode.as_str(),
        points = series.points.len(),
        markers = series.markers.len(),
        "strategy live z-series generated"
    );

    Ok(Json(LiveZResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id: query.pair_id,
        generated_at: Utc::now(),
        exit_mode: exit_mode.as_str().to_string(),
        entry_band: output.cue.entry_band,
        exit_band: output.cue.exit_band,
        stop_band: output.cue.stop_band,
        selected_variant: output.cue.selected_variant,
        points: series
            .points
            .into_iter()
            .map(|point| LiveZPointResponse {
                ts: point.ts,
                z: point.z,
            })
            .collect(),
        markers: series
            .markers
            .into_iter()
            .map(|marker| BacktestMarkerResponse {
                index: marker.index,
                kind: marker.kind,
            })
            .collect(),
        rationale_codes: output.cue.rationale_codes,
    }))
}

async fn pairs_portfolio_plan(
    State(state): State<AppState>,
    Query(query): Query<CuesQuery>,
) -> Result<Json<PortfolioPlanResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
    let include_advisory = query
        .include_advisory
        .unwrap_or(state.settings.advisory_enabled);
    let taker_fee_bps = resolve_taker_fee_bps(query.taker_fee_bps, state.settings.trading_fee_bps)?;
    let (_outputs, skipped, plan) =
        evaluate_timeframe_outputs(&state, timeframe, include_advisory, taker_fee_bps).await;

    Ok(Json(PortfolioPlanResponse {
        timeframe: timeframe.as_str().to_string(),
        generated_at: Utc::now(),
        plan,
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
    let mut drift_rows_written = 0usize;
    let mut champion_promotions = 0usize;
    let mut champion_locks = 0usize;
    let mut shadow_model_runs_written = 0usize;
    let mut shadow_model_available = 0usize;
    let mut shadow_model_unavailable = 0usize;
    let mut cost_gate_pass = 0usize;
    let mut cost_gate_fail = 0usize;
    let mut portfolio_advice_available = 0usize;
    let mut portfolio_advice_unavailable = 0usize;
    let mut errors = vec![];

    for timeframe in &requested_timeframes {
        let (outputs, skipped, plan) = evaluate_timeframe_outputs(
            &state,
            *timeframe,
            state.settings.advisory_enabled,
            state.settings.trading_fee_bps,
        )
        .await;
        pairs_processed += state.settings.pairs.len();
        if plan.status == "AVAILABLE" {
            portfolio_advice_available += 1;
        } else {
            portfolio_advice_unavailable += 1;
        }

        for skipped_pair in skipped {
            errors.push(ReoptError {
                pair_id: skipped_pair.pair_id,
                timeframe: timeframe.as_str().to_string(),
                error: skipped_pair.reason,
            });
        }

        for output in outputs {
            cues_generated += usize::from(output.cue.actionable);
            match output.cue.shadow_ml.status.as_str() {
                "AVAILABLE" => shadow_model_available += 1,
                _ => shadow_model_unavailable += 1,
            }
            if output.cue.cost_gate.status == "AVAILABLE" {
                if output.cue.cost_gate.pass {
                    cost_gate_pass += 1;
                } else {
                    cost_gate_fail += 1;
                }
            }
            match state
                .repository
                .record_evaluation(
                    *timeframe,
                    &output,
                    state.settings.champion_switch_min_delta,
                )
                .await
            {
                Ok(summary) => {
                    performance_rows_written += summary.performance_rows_written;
                    selected_rows_written += summary.selected_rows_written;
                    drift_rows_written += summary.drift_rows_written;
                    champion_promotions += summary.champion_promotions;
                    champion_locks += summary.champion_locks;
                }
                Err(error) => errors.push(ReoptError {
                    pair_id: output.cue.pair_id.clone(),
                    timeframe: timeframe.as_str().to_string(),
                    error: error.to_string(),
                }),
            }
            if let Err(error) = state
                .repository
                .record_shadow_model_run(*timeframe, &output)
                .await
                .map(|written| shadow_model_runs_written += written)
            {
                errors.push(ReoptError {
                    pair_id: output.cue.pair_id,
                    timeframe: timeframe.as_str().to_string(),
                    error: format!("shadow model run persist failed: {error}"),
                });
                continue;
            }
            if let Err(error) = state
                .repository
                .record_opportunity_history(*timeframe, &output)
                .await
            {
                errors.push(ReoptError {
                    pair_id: output.cue.pair_id.clone(),
                    timeframe: timeframe.as_str().to_string(),
                    error: format!("opportunity history persist failed: {error}"),
                });
            }
            let pair_spec = PairSpec {
                left: output.cue.left_instrument.clone(),
                right: output.cue.right_instrument.clone(),
            };
            if let Err(error) =
                compute_and_record_paper_trades_for_output(&state, &pair_spec, *timeframe, &output)
                    .await
            {
                errors.push(ReoptError {
                    pair_id: output.cue.pair_id.clone(),
                    timeframe: timeframe.as_str().to_string(),
                    error: format!("paper trade history persist failed: {error}"),
                });
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
        drift_rows_written,
        champion_promotions,
        champion_locks,
        shadow_model_runs_written,
        shadow_model_available,
        shadow_model_unavailable,
        cost_gate_pass,
        cost_gate_fail,
        portfolio_advice_available,
        portfolio_advice_unavailable,
        errors,
    }))
}

async fn evaluate_pair_for_timeframe(
    state: &AppState,
    pair: &PairSpec,
    timeframe: Timeframe,
    advisory_enabled: bool,
    taker_fee_bps: f64,
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

    let mut output = evaluate_pair(PairEvaluationInput {
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
        taker_fee_bps,
        min_samples_target: state.settings.min_samples_target,
    })?;

    let training_rows = match state
        .repository
        .fetch_shadow_training_rows(
            &pair.pair_id(),
            timeframe,
            state.settings.shadow_ml_training_limit as i64,
        )
        .await
    {
        Ok(rows) => rows,
        Err(error) => {
            tracing::warn!(
                pair_id = %pair.pair_id(),
                timeframe = %timeframe.as_str(),
                error = %error,
                "shadow training history unavailable"
            );
            annotate_with_shadow_model(&mut output, None);
            output
                .cue
                .shadow_ml
                .rationale_codes
                .push("TRAINING_QUERY_FAILED".to_string());
            return Ok(output);
        }
    };

    let model = train_shadow_model(&training_rows, state.settings.shadow_ml_min_rows);
    let diagnostics = annotate_with_shadow_model(&mut output, model.as_ref());
    if diagnostics.status == "UNAVAILABLE" {
        tracing::info!(
            pair_id = %pair.pair_id(),
            timeframe = %timeframe.as_str(),
            rows = training_rows.len(),
            "shadow model unavailable for current evaluation"
        );
    }

    state
        .sampled_slippage
        .update_hedge_ratio(&output.cue.pair_id, timeframe, output.hedge_ratio)
        .await;

    if advisory_enabled {
        let sampled = state
            .sampled_slippage
            .snapshot_for(&output.cue.pair_id, timeframe, &output.cue.direction_hint)
            .await;
        if sampled.status == SampledSlippageStatus::Healthy {
            let funding_estimate =
                resolve_funding_cost_estimate(&state.settings, &output, timeframe, &sampled);
            let mut cost_gate = evaluate_cost_gate(CostGateInput {
                expected_edge_bps: resolve_expected_edge_bps_for_cost_gate(&output),
                fee_bps: taker_fee_bps,
                funding_model: funding_estimate.model,
                funding_events: funding_estimate.events,
                funding_bps_per_event: funding_estimate.bps_per_event,
                funding_bps: funding_estimate.total_bps,
                spread_vol_bps: output.spread_vol_bps.max(0.0),
                spread_z: output.cue.spread_z,
                sampled_slippage_bps: Some(sampled.selected_slippage_bps),
                slippage_base_bps: state.settings.slippage_base_bps,
                slippage_vol_multiplier: state.settings.slippage_vol_multiplier,
                slippage_z_multiplier: state.settings.slippage_z_multiplier,
                min_net_edge_bps: state.settings.min_net_edge_bps,
            });
            if sampled.source == Some(SampledSlippageSource::Bootstrapped) {
                cost_gate
                    .rationale_codes
                    .push("SLIPPAGE_SOURCE_BOOTSTRAPPED".to_string());
            } else {
                cost_gate
                    .rationale_codes
                    .push("SLIPPAGE_SOURCE_SAMPLED".to_string());
            }
            if funding_estimate.model == FundingModel::Dynamic {
                cost_gate
                    .rationale_codes
                    .push("FUNDING_MODEL_DYNAMIC".to_string());
                cost_gate
                    .rationale_codes
                    .push("FUNDING_CONTINUOUS_ACCRUAL".to_string());
                if funding_estimate.events == 0 {
                    cost_gate
                        .rationale_codes
                        .push("FUNDING_WINDOW_NO_SETTLEMENT".to_string());
                }
                if !funding_estimate.sample_available {
                    cost_gate
                        .rationale_codes
                        .push("FUNDING_DATA_UNAVAILABLE_INFO".to_string());
                }
            } else {
                cost_gate
                    .rationale_codes
                    .push("FUNDING_MODEL_STATIC".to_string());
            }

            if !cost_gate.pass {
                output.cue.actionable = false;
            }
            output.cue.cost_estimate_bps = (cost_gate.fee_bps + cost_gate.slippage_bps).max(0.0);
            output.cue.cost_gate = cost_gate;
        } else {
            output.cue.actionable = false;
            if let Some(reason_code) = sampled.status.rationale_code() {
                output.cue.cost_gate = strategy_service::CostGateDiagnostics::unavailable(vec![
                    reason_code.to_string(),
                ]);
            } else {
                output.cue.cost_gate = strategy_service::CostGateDiagnostics::unavailable(vec![
                    "SLIPPAGE_DATA_UNAVAILABLE".to_string(),
                ]);
            }
        }
    } else {
        output.cue.cost_gate = strategy_service::CostGateDiagnostics::unavailable(vec![
            "ADVISORY_DISABLED".to_string(),
        ]);
    }
    refresh_setup_gate(&mut output.cue);
    finalize_trade_gate(&mut output.cue);

    Ok(output)
}

fn is_cost_reason(code: &str) -> bool {
    matches!(
        code,
        "COST_GATE_BLOCKED"
            | "NEGATIVE_EXPECTED_EDGE"
            | "INVALID_FUNDING_INPUT"
            | "SLIPPAGE_SOURCE_SAMPLED"
            | "SLIPPAGE_SOURCE_BOOTSTRAPPED"
            | "SLIPPAGE_DATA_WARMING"
            | "SLIPPAGE_DATA_STALE"
            | "SLIPPAGE_DATA_UNAVAILABLE"
            | "FUNDING_MODEL_DYNAMIC"
            | "FUNDING_CONTINUOUS_ACCRUAL"
            | "FUNDING_WINDOW_NO_SETTLEMENT"
            | "FUNDING_DATA_UNAVAILABLE_INFO"
            | "FUNDING_MODEL_STATIC"
            | "ADVISORY_DISABLED"
    )
}

fn refresh_setup_gate(cue: &mut PairCue) {
    let mut setup_reasons = cue
        .rationale_codes
        .iter()
        .filter(|code| !is_cost_reason(code))
        .cloned()
        .collect::<Vec<_>>();
    if !cue.setup_actionable && setup_reasons.is_empty() {
        setup_reasons.push("SETUP_GATE_BLOCKED".to_string());
    }
    cue.setup_gate.status = "AVAILABLE".to_string();
    cue.setup_gate.pass = cue.setup_actionable;
    cue.setup_gate.rationale_codes = setup_reasons;
}

fn finalize_trade_gate(cue: &mut PairCue) {
    let setup_available = cue.setup_gate.status == "AVAILABLE";
    let setup_pass = setup_available && cue.setup_gate.pass;
    let cost_available = cue.cost_gate.status == "AVAILABLE";
    let cost_pass = cost_available && cue.cost_gate.pass;

    let (status, pass, blocked_by) = if !setup_available || !cost_available {
        ("UNAVAILABLE".to_string(), false, "UNAVAILABLE".to_string())
    } else if setup_pass && cost_pass {
        ("AVAILABLE".to_string(), true, "NONE".to_string())
    } else if !setup_pass && !cost_pass {
        ("AVAILABLE".to_string(), false, "MULTIPLE".to_string())
    } else if !setup_pass {
        ("AVAILABLE".to_string(), false, "SETUP".to_string())
    } else {
        ("AVAILABLE".to_string(), false, "COST".to_string())
    };

    let mut rationale_codes = vec![];
    if !setup_pass {
        rationale_codes.extend(cue.setup_gate.rationale_codes.iter().cloned());
    }
    if !cost_pass || !cost_available {
        rationale_codes.extend(cue.cost_gate.rationale_codes.iter().cloned());
    }
    if rationale_codes.is_empty() && !pass {
        rationale_codes.push("TRADE_GATE_BLOCKED".to_string());
    }

    cue.trade_gate.status = status;
    cue.trade_gate.pass = pass;
    cue.trade_gate.blocked_by = blocked_by;
    cue.trade_gate.rationale_codes = rationale_codes;
    cue.actionable = pass;
}

async fn evaluate_timeframe_outputs(
    state: &AppState,
    timeframe: Timeframe,
    advisory_enabled: bool,
    taker_fee_bps: f64,
) -> (Vec<PairEvaluationOutput>, Vec<SkippedPair>, PortfolioPlan) {
    let mut outputs = vec![];
    let mut skipped = vec![];

    for pair in &state.settings.pairs {
        match evaluate_pair_for_timeframe(state, pair, timeframe, advisory_enabled, taker_fee_bps)
            .await
        {
            Ok(output) => outputs.push(output),
            Err(error) => skipped.push(SkippedPair {
                pair_id: pair.pair_id(),
                reason: error.to_string(),
            }),
        }
    }

    let portfolio_plan = if advisory_enabled {
        let mut cue_snapshot = outputs
            .iter()
            .map(|output| output.cue.clone())
            .collect::<Vec<_>>();
        let plan = build_portfolio_plan(
            &cue_snapshot,
            state.settings.advisory_gross_cap,
            state.settings.advisory_per_pair_cap,
        );
        apply_portfolio_plan_to_cues(&mut cue_snapshot, &plan);
        for (output, cue) in outputs.iter_mut().zip(cue_snapshot.into_iter()) {
            output.cue = cue;
        }
        plan
    } else {
        let plan = PortfolioPlan {
            status: "UNAVAILABLE".to_string(),
            weights: vec![],
            constraints: strategy_service::PortfolioPlanConstraints {
                dollar_neutral: false,
                gross_cap: state.settings.advisory_gross_cap.max(0.0),
                per_pair_cap: state.settings.advisory_per_pair_cap.max(0.0),
            },
            rationale_codes: vec!["ADVISORY_DISABLED".to_string()],
        };
        for output in &mut outputs {
            output.cue.portfolio_hint =
                strategy_service::PortfolioHint::unavailable(vec!["ADVISORY_DISABLED".to_string()]);
        }
        plan
    };

    (outputs, skipped, portfolio_plan)
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
            left: "PF_XBTUSD".to_string(),
            right: "PF_ETHUSD".to_string(),
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

fn parse_env_i64(key: &str, default: i64) -> i64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(default)
}

fn parse_env_bool(key: &str, default: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(default)
}

#[cfg(test)]
mod tests {
    use super::{
        artifact_download_path, bootstrap_deviation_exceeds_threshold, bootstrap_snapshot_is_fresh,
        classify_expectancy_result, compute_expectancy_metrics, compute_pair_funding_bps_per_event,
        compute_pair_slippage_sample_bps, days_covered, decide_champion_transition,
        derive_paper_trades_from_series, derive_replay_trades_from_series,
        estimate_research_combinations, expectancy_objective_score,
        expected_funding_events_crossed, finalize_trade_gate, normalize_funding_rate,
        parse_backtest_exit_mode, parse_expectancy_query,
        parse_opportunity_history_stats_timeframe, parse_opportunity_history_window,
        parse_paper_trades_window, parse_replay_trades_query, percentile,
        project_continuous_funding_bps, refresh_setup_gate, resolve_artifact_path,
        resolve_taker_fee_bps, ChampionDecision, ExpectancyMetrics, ExpectancyQuery,
        FundingRateInputMode, MaintenanceAction, OpportunityHistoryQuery,
        OpportunityHistoryStatsQuery, PaperTradesQuery, ReplayTradeEntry, ReplayTradePathSummary,
        ReplayTradesQuery, ResearchSweepRequest, SampledSlippageStatus, SelectedSignalRow,
        StrategyMarketMetricsResponse, StrategySettings,
    };
    use chrono::Utc;
    use common_types::Timeframe;
    use std::fs;
    use std::path::PathBuf;
    use strategy_service::{
        BacktestExitMode, BacktestMarker, BacktestPoint, BacktestSeries, CostGateDiagnostics,
        PairCue, PairEvaluationOutput, PortfolioHint, SetupGateDiagnostics, ShadowMlDiagnostics,
        TradeGateDiagnostics, VariantEvaluation,
    };

    fn output(
        selected_variant: &str,
        selected_score: f64,
        champion_score: f64,
        challenger_score: f64,
    ) -> PairEvaluationOutput {
        PairEvaluationOutput {
            cue: PairCue {
                pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
                left_instrument: "PI_XBTUSD".to_string(),
                right_instrument: "PI_ETHUSD".to_string(),
                timeframe: "1m".to_string(),
                regime: "CALM".to_string(),
                selected_variant: selected_variant.to_string(),
                direction_hint: "NONE".to_string(),
                spread_z: 0.0,
                opportunity_score: selected_score,
                confidence_band: "MEDIUM".to_string(),
                entry_band: 1.8,
                exit_band: 0.6,
                stop_band: 3.2,
                expected_hold_bars: 12,
                cost_estimate_bps: 1.0,
                setup_actionable: false,
                actionable: false,
                rationale_codes: vec![],
                setup_gate: SetupGateDiagnostics::unavailable(vec![]),
                cost_gate: CostGateDiagnostics::unavailable(vec![]),
                trade_gate: TradeGateDiagnostics::unavailable(vec![]),
                portfolio_hint: PortfolioHint::unavailable(vec![]),
                shadow_ml: ShadowMlDiagnostics::unavailable(vec![]),
                evaluated_at: Utc::now(),
            },
            variants: vec![
                VariantEvaluation {
                    variant: "ROBUST_Z".to_string(),
                    score_last: 0.0,
                    sample_count: 100,
                    win_rate: 0.56,
                    edge_bps: champion_score,
                    reliability: 0.7,
                    regime_fit: 0.8,
                    opportunity_score: champion_score,
                    shadow_success_probability: None,
                    shadow_rank_score: None,
                    rationale_codes: vec![],
                },
                VariantEvaluation {
                    variant: "VOL_NORMALIZED".to_string(),
                    score_last: 0.0,
                    sample_count: 100,
                    win_rate: 0.57,
                    edge_bps: challenger_score,
                    reliability: 0.7,
                    regime_fit: 0.8,
                    opportunity_score: challenger_score,
                    shadow_success_probability: None,
                    shadow_rank_score: None,
                    rationale_codes: vec![],
                },
            ],
            half_life_bars: 12.0,
            hedge_ratio: 1.0,
            hedge_ratio_stability: 0.1,
            spread_vol_bps: 2.0,
        }
    }

    #[test]
    fn champion_transition_initializes_when_no_previous_selection() {
        let evaluation = output("VOL_NORMALIZED", 2.0, 1.0, 2.0);
        let transition = decide_champion_transition(None, &evaluation, 0.25);
        assert_eq!(transition.decision, ChampionDecision::Initialize);
        assert_eq!(transition.selected_variant, "VOL_NORMALIZED");
    }

    #[test]
    fn champion_transition_promotes_when_delta_exceeds_threshold() {
        let existing = SelectedSignalRow {
            signal_variant: "ROBUST_Z".to_string(),
            opportunity_score: 1.0,
        };
        let evaluation = output("VOL_NORMALIZED", 2.0, 1.0, 2.0);
        let transition = decide_champion_transition(Some(&existing), &evaluation, 0.25);
        assert_eq!(transition.decision, ChampionDecision::PromoteChallenger);
        assert_eq!(transition.selected_variant, "VOL_NORMALIZED");
        assert!((transition.score_delta - 1.0).abs() < 1e-9);
    }

    #[test]
    fn champion_transition_locks_when_delta_below_threshold() {
        let existing = SelectedSignalRow {
            signal_variant: "ROBUST_Z".to_string(),
            opportunity_score: 1.0,
        };
        let evaluation = output("VOL_NORMALIZED", 1.1, 1.0, 1.1);
        let transition = decide_champion_transition(Some(&existing), &evaluation, 0.25);
        assert_eq!(transition.decision, ChampionDecision::KeepChampion);
        assert_eq!(transition.selected_variant, "ROBUST_Z");
        assert!(transition.score_delta < 0.25);
    }

    fn temp_dir(name: &str) -> PathBuf {
        let mut path = std::env::temp_dir();
        let stamp = Utc::now().timestamp_nanos_opt().unwrap_or_default();
        path.push(format!("cryptopairs-strategy-{name}-{stamp}"));
        fs::create_dir_all(&path).expect("create temp dir");
        path
    }

    #[test]
    fn resolve_artifact_path_accepts_file_under_root() {
        let root = temp_dir("artifact-root-ok");
        let nested = root.join("nested");
        fs::create_dir_all(&nested).expect("create nested dir");
        let target = nested.join("report.json");
        fs::write(&target, b"{\"ok\":true}").expect("write report");

        let resolved = resolve_artifact_path(&root, "nested/report.json").expect("resolve path");
        assert_eq!(
            resolved.canonicalize().expect("canonical target"),
            target.canonicalize().expect("canonical resolved")
        );

        fs::remove_dir_all(&root).expect("cleanup root");
    }

    #[test]
    fn resolve_artifact_path_rejects_escape() {
        let root = temp_dir("artifact-root-escape");
        let outside = temp_dir("artifact-outside");
        let outside_file = outside.join("secret.json");
        fs::write(&outside_file, b"{\"secret\":true}").expect("write outside file");

        let requested = format!(
            "../{}/secret.json",
            outside.file_name().unwrap().to_string_lossy()
        );
        let result = resolve_artifact_path(&root, &requested);
        assert!(result.is_err());

        fs::remove_dir_all(&root).expect("cleanup root");
        fs::remove_dir_all(&outside).expect("cleanup outside");
    }
    #[test]
    fn resolve_artifact_path_accepts_workspace_prefixed_path() {
        let root = temp_dir("artifact-root-prefixed");
        let nested = root.join("runs").join("example");
        fs::create_dir_all(&nested).expect("create nested dir");
        let target = nested.join("baseline_report.json");
        fs::write(&target, b"{\"ok\":true}").expect("write report");

        let root_name = root
            .file_name()
            .expect("root name")
            .to_string_lossy()
            .to_string();
        let requested = format!("{root_name}/runs/example/baseline_report.json");
        let resolved =
            resolve_artifact_path(&root, &requested).expect("resolve workspace-prefixed path");
        assert_eq!(
            resolved.canonicalize().expect("canonical target"),
            target.canonicalize().expect("canonical resolved")
        );

        fs::remove_dir_all(&root).expect("cleanup root");
    }
    #[test]
    fn maintenance_action_parse_accepts_promote_and_revert() {
        assert!(matches!(
            MaintenanceAction::parse("PROMOTE"),
            Some(MaintenanceAction::Promote)
        ));
        assert!(matches!(
            MaintenanceAction::parse("revert"),
            Some(MaintenanceAction::Revert)
        ));
        assert!(MaintenanceAction::parse("hold").is_none());
    }

    #[test]
    fn opportunity_history_window_defaults_and_bounds() {
        let query = OpportunityHistoryQuery {
            timeframe: "1m".to_string(),
            hours: Some(999),
            only_pass: None,
            limit: Some(99_999),
        };
        let (timeframe, hours, only_pass, limit) =
            parse_opportunity_history_window(&query).expect("parse history query");
        assert_eq!(timeframe.as_str(), "1m");
        assert_eq!(hours, 168);
        assert!(only_pass);
        assert_eq!(limit, 20_000);
    }

    #[test]
    fn opportunity_history_window_rejects_invalid_timeframe() {
        let query = OpportunityHistoryQuery {
            timeframe: "5m".to_string(),
            hours: Some(12),
            only_pass: Some(true),
            limit: Some(100),
        };
        let result = parse_opportunity_history_window(&query);
        assert!(result.is_err());
    }

    #[test]
    fn opportunity_history_stats_timeframe_optional_and_validates() {
        let none_query = OpportunityHistoryStatsQuery { timeframe: None };
        let parsed_none = parse_opportunity_history_stats_timeframe(&none_query)
            .expect("parse optional timeframe");
        assert!(parsed_none.is_none());

        let valid_query = OpportunityHistoryStatsQuery {
            timeframe: Some("15m".to_string()),
        };
        let parsed_valid = parse_opportunity_history_stats_timeframe(&valid_query)
            .expect("parse valid timeframe")
            .expect("timeframe present");
        assert_eq!(parsed_valid.as_str(), "15m");

        let invalid_query = OpportunityHistoryStatsQuery {
            timeframe: Some("5m".to_string()),
        };
        assert!(parse_opportunity_history_stats_timeframe(&invalid_query).is_err());
    }

    #[test]
    fn paper_trades_window_defaults_and_bounds() {
        let query = PaperTradesQuery {
            timeframe: "1h".to_string(),
            pair_id: Some("PF_TAOUSD__PF_HYPEUSD".to_string()),
            hours: Some(2_000),
            limit: Some(99_999),
            exit_mode: Some("mean_revert".to_string()),
        };
        let (timeframe, pair_id, exit_mode, hours, limit) =
            parse_paper_trades_window(&query).expect("parse paper-trades query");
        assert_eq!(timeframe.as_str(), "1h");
        assert_eq!(pair_id.as_deref(), Some("PF_TAOUSD__PF_HYPEUSD"));
        assert_eq!(exit_mode, "mean_revert");
        assert_eq!(hours, 2_000);
        assert_eq!(limit, 20_000);
    }

    #[test]
    fn paper_trades_window_rejects_invalid_timeframe() {
        let query = PaperTradesQuery {
            timeframe: "5m".to_string(),
            pair_id: None,
            hours: Some(24),
            limit: Some(100),
            exit_mode: None,
        };
        assert!(parse_paper_trades_window(&query).is_err());
    }

    #[test]
    fn expectancy_query_defaults_and_bounds() {
        let settings = StrategySettings::from_env();
        let query = ExpectancyQuery {
            timeframe: "1m".to_string(),
            pair_id: "PF_TAOUSD__PF_HYPEUSD".to_string(),
            entry_z: Some(1.8),
            exit_z: Some(0.2),
            stop_z: Some(3.2),
            z_method: Some("robust_z".to_string()),
            lookback_bars: Some(50),
        };
        let (timeframe, pair_id, config) =
            parse_expectancy_query(&query, &settings).expect("parse expectancy query");
        assert_eq!(timeframe.as_str(), "1m");
        assert_eq!(pair_id, "PF_TAOUSD__PF_HYPEUSD");
        assert_eq!(config.z_method, "ROBUST_Z");
        assert!(config.lookback_bars >= 300);
    }

    #[test]
    fn replay_trades_query_defaults_and_bounds() {
        let settings = StrategySettings::from_env();
        let query = ReplayTradesQuery {
            timeframe: "1h".to_string(),
            pair_id: "PF_TAOUSD__PF_HYPEUSD".to_string(),
            hours: Some(200_000),
            limit: Some(99_999),
            exit_mode: Some("opposite_extreme".to_string()),
            entry_z: Some(2.1),
            exit_z: Some(0.4),
            stop_z: Some(3.5),
            z_method: Some("vol_normalized".to_string()),
            lookback_bars: Some(150),
        };
        let (timeframe, pair_id, hours, limit, exit_mode, config) =
            parse_replay_trades_query(&query, &settings).expect("parse replay query");
        assert_eq!(timeframe.as_str(), "1h");
        assert_eq!(pair_id, "PF_TAOUSD__PF_HYPEUSD");
        assert_eq!(hours, 175_200);
        assert_eq!(limit, 20_000);
        assert_eq!(exit_mode, "opposite_extreme");
        assert_eq!(config.z_method, "VOL_NORMALIZED");
        assert!(config.lookback_bars >= 220);
    }

    #[test]
    fn replay_trades_query_rejects_invalid_pair_id() {
        let settings = StrategySettings::from_env();
        let query = ReplayTradesQuery {
            timeframe: "1h".to_string(),
            pair_id: "   ".to_string(),
            hours: Some(24),
            limit: Some(100),
            exit_mode: Some("mean_revert".to_string()),
            entry_z: None,
            exit_z: None,
            stop_z: None,
            z_method: None,
            lookback_bars: None,
        };
        assert!(parse_replay_trades_query(&query, &settings).is_err());
    }

    #[test]
    fn research_sweep_estimator_uses_defaults_and_grid_sizes() {
        let default_payload = ResearchSweepRequest {
            timeframes: None,
            pair_ids: None,
            entry_z_grid: None,
            exit_z_grid: None,
            stop_z_grid: None,
            z_methods: None,
            lookback_bars_grid: None,
            max_combinations: None,
            dry_run: None,
        };
        assert_eq!(estimate_research_combinations(&default_payload), 19_200);

        let custom_payload = ResearchSweepRequest {
            timeframes: Some(vec!["1m".to_string(), "1h".to_string()]),
            pair_ids: Some(vec![
                "PF_TAOUSD__PF_HYPEUSD".to_string(),
                "PF_XRPUSD__PF_ADAUSD".to_string(),
            ]),
            entry_z_grid: Some(vec![1.6, 1.8, 2.0]),
            exit_z_grid: Some(vec![0.1, 0.2]),
            stop_z_grid: Some(vec![2.8, 3.2, 3.6]),
            z_methods: Some(vec!["ROBUST_Z".to_string(), "VOL_NORMALIZED".to_string()]),
            lookback_bars_grid: Some(vec![220, 440]),
            max_combinations: Some(10_000),
            dry_run: Some(true),
        };
        assert_eq!(estimate_research_combinations(&custom_payload), 288);
    }

    #[test]
    fn classify_expectancy_result_maps_known_states() {
        let strong = ExpectancyMetrics {
            trades: 12,
            win_rate: 0.67,
            avg_net_bps: 24.0,
            p25_net_bps: 3.0,
            p50_net_bps: 20.0,
            p75_net_bps: 32.0,
            avg_hold_bars: 14.0,
            avg_mae_bps: -11.0,
            avg_mfe_bps: 29.0,
            expected_min_lot_net_bps: 24.0,
            expected_min_lot_net_usd: 3.2,
        };
        let (status, decision, reason, _codes) = classify_expectancy_result(Some(&strong));
        assert_eq!(status, "AVAILABLE");
        assert_eq!(decision, "TRADE_READY");
        assert_eq!(reason, "EXPECTANCY_POSITIVE");

        let weak = ExpectancyMetrics {
            trades: 2,
            win_rate: 0.5,
            avg_net_bps: 6.0,
            ..strong.clone()
        };
        let (_status, decision, reason, _codes) = classify_expectancy_result(Some(&weak));
        assert_eq!(decision, "CAUTION");
        assert_eq!(reason, "LOW_TRADE_COUNT");
    }

    #[test]
    fn expectancy_objective_score_prefers_positive_expectancy_and_depth() {
        let base = ExpectancyMetrics {
            trades: 5,
            win_rate: 0.55,
            avg_net_bps: 10.0,
            p25_net_bps: 2.0,
            p50_net_bps: 8.0,
            p75_net_bps: 12.0,
            avg_hold_bars: 8.0,
            avg_mae_bps: -6.0,
            avg_mfe_bps: 14.0,
            expected_min_lot_net_bps: 10.0,
            expected_min_lot_net_usd: 1.0,
        };
        let deeper = ExpectancyMetrics {
            trades: 20,
            ..base.clone()
        };
        assert!(expectancy_objective_score(&deeper) > expectancy_objective_score(&base));

        let negative = ExpectancyMetrics {
            expected_min_lot_net_bps: -1.0,
            ..base
        };
        assert!(expectancy_objective_score(&negative) < 0.0);
    }

    #[test]
    fn analytics_model_bars_match_ui_defaults() {
        assert_eq!(super::analytics_model_bars(Timeframe::OneMinute), 300);
        assert_eq!(super::analytics_model_bars(Timeframe::FifteenMinutes), 280);
        assert_eq!(super::analytics_model_bars(Timeframe::OneHour), 220);
    }

    #[test]
    fn derive_paper_trades_computes_leg_and_equity_metrics() {
        let start = Utc::now();
        let timestamps = vec![
            start,
            start + chrono::Duration::hours(1),
            start + chrono::Duration::hours(2),
            start + chrono::Duration::hours(3),
        ];
        let left_closes = vec![100.0, 98.0, 102.0, 104.0];
        let right_closes = vec![50.0, 50.0, 49.0, 48.5];
        let series = BacktestSeries {
            points: vec![
                BacktestPoint {
                    ts: timestamps[1],
                    z: -2.0,
                    equity: 0.999,
                },
                BacktestPoint {
                    ts: timestamps[2],
                    z: 0.5,
                    equity: 1.02,
                },
                BacktestPoint {
                    ts: timestamps[3],
                    z: 0.4,
                    equity: 1.02,
                },
            ],
            markers: vec![
                BacktestMarker {
                    index: 0,
                    kind: "entry".to_string(),
                },
                BacktestMarker {
                    index: 1,
                    kind: "exit".to_string(),
                },
            ],
        };
        let rows = derive_paper_trades_from_series(
            "PF_LEFT__PF_RIGHT",
            Timeframe::OneHour,
            BacktestExitMode::MeanRevert,
            "PF_LEFT",
            "PF_RIGHT",
            "ROBUST_Z",
            1.8,
            1.0,
            2.0,
            None,
            None,
            &timestamps,
            &left_closes,
            &right_closes,
            &series,
        );
        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!(row.direction, "LONG_SPREAD");
        assert_eq!(row.exit_kind, "exit");
        assert!(row.gross_bps > 0.0);
        assert!((row.net_bps - row.equity_trade_bps).abs() < 1e-9);
        assert!((row.net_bps - (row.gross_bps - 2.0)).abs() < 1e-9);
        assert!(((row.left_leg_bps + row.right_leg_bps) - row.gross_bps).abs() < 1e-6);
        assert!(row.equity_trade_bps > 0.0);
    }

    #[test]
    fn derive_replay_trades_computes_path_metrics() {
        let start = Utc::now();
        let series = BacktestSeries {
            points: vec![
                BacktestPoint {
                    ts: start + chrono::Duration::hours(1),
                    z: -2.0,
                    equity: 0.99,
                },
                BacktestPoint {
                    ts: start + chrono::Duration::hours(2),
                    z: -1.0,
                    equity: 1.01,
                },
                BacktestPoint {
                    ts: start + chrono::Duration::hours(3),
                    z: 0.2,
                    equity: 1.02,
                },
            ],
            markers: vec![
                BacktestMarker {
                    index: 0,
                    kind: "entry".to_string(),
                },
                BacktestMarker {
                    index: 2,
                    kind: "exit".to_string(),
                },
            ],
        };

        let rows =
            derive_replay_trades_from_series("PF_LEFT__PF_RIGHT", Timeframe::OneHour, &series, 1.8);
        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!(row.direction, "LONG_SPREAD");
        assert_eq!(row.path.bars_held, 2);
        assert_eq!(row.path.bars_underwater, 1);
        assert!((row.net_bps - 200.0).abs() < 1e-9);
        assert!((row.path.mae_bps - (-100.0)).abs() < 1e-9);
        assert!((row.path.mfe_bps - 200.0).abs() < 1e-9);
    }

    #[test]
    fn expectancy_metrics_aggregate_distribution_and_min_lot_projection() {
        let rows = vec![
            ReplayTradeEntry {
                trade_id: "a".to_string(),
                entry_ts: Utc::now(),
                exit_ts: Utc::now(),
                direction: "LONG_SPREAD".to_string(),
                entry_z: -2.0,
                exit_z: 0.0,
                net_bps: 10.0,
                path: ReplayTradePathSummary {
                    mae_bps: -5.0,
                    mfe_bps: 12.0,
                    bars_underwater: 1,
                    bars_held: 10,
                },
            },
            ReplayTradeEntry {
                trade_id: "b".to_string(),
                entry_ts: Utc::now(),
                exit_ts: Utc::now(),
                direction: "SHORT_SPREAD".to_string(),
                entry_z: 2.0,
                exit_z: 0.0,
                net_bps: -5.0,
                path: ReplayTradePathSummary {
                    mae_bps: -8.0,
                    mfe_bps: 2.0,
                    bars_underwater: 4,
                    bars_held: 12,
                },
            },
            ReplayTradeEntry {
                trade_id: "c".to_string(),
                entry_ts: Utc::now(),
                exit_ts: Utc::now(),
                direction: "LONG_SPREAD".to_string(),
                entry_z: -1.9,
                exit_z: -0.1,
                net_bps: 15.0,
                path: ReplayTradePathSummary {
                    mae_bps: -3.0,
                    mfe_bps: 18.0,
                    bars_underwater: 2,
                    bars_held: 8,
                },
            },
        ];

        let metrics = compute_expectancy_metrics(&rows, 100.0, 50.0, 1.0, None, None)
            .expect("expectancy metrics");
        assert_eq!(metrics.trades, 3);
        assert!((metrics.win_rate - (2.0 / 3.0)).abs() < 1e-12);
        assert!((metrics.avg_net_bps - (20.0 / 3.0)).abs() < 1e-12);
        assert!((metrics.p25_net_bps - 2.5).abs() < 1e-12);
        assert!((metrics.p50_net_bps - 10.0).abs() < 1e-12);
        assert!((metrics.p75_net_bps - 12.5).abs() < 1e-12);
        assert!((metrics.expected_min_lot_net_usd - 0.1).abs() < 1e-9);
    }

    #[test]
    fn expectancy_metrics_uses_exchange_min_lot_notional_when_constraints_available() {
        let rows = vec![ReplayTradeEntry {
            trade_id: "x".to_string(),
            entry_ts: Utc::now(),
            exit_ts: Utc::now(),
            direction: "LONG_SPREAD".to_string(),
            entry_z: -2.0,
            exit_z: 0.0,
            net_bps: 10.0,
            path: ReplayTradePathSummary {
                mae_bps: -2.0,
                mfe_bps: 12.0,
                bars_underwater: 1,
                bars_held: 5,
            },
        }];
        let xbt = common_types::kraken_perp_constraints("PF_XBTUSD").expect("xbt constraints");
        let eth = common_types::kraken_perp_constraints("PF_ETHUSD").expect("eth constraints");
        let metrics =
            compute_expectancy_metrics(&rows, 67_000.0, 2_000.0, 1.0, Some(xbt), Some(eth))
                .expect("expectancy metrics");
        // Min-lot notional = 0.0001*67000 + 0.001*2000 = 8.7, at 10bp => 0.0087 USD.
        assert!((metrics.expected_min_lot_net_usd - 0.0087).abs() < 1e-9);
    }

    #[test]
    fn percentile_handles_empty_and_interpolates() {
        assert_eq!(percentile(&[], 0.5), 0.0);
        let values = vec![1.0, 3.0, 7.0, 9.0];
        assert!((percentile(&values, 0.5) - 5.0).abs() < 1e-12);
    }

    #[test]
    fn days_covered_handles_ranges_and_empty() {
        let start = Utc::now();
        let end = start + chrono::Duration::hours(36);
        let covered = days_covered(Some(start), Some(end));
        assert!((covered - 1.5).abs() < 1e-9);
        assert_eq!(days_covered(None, Some(end)), 0.0);
        assert_eq!(days_covered(Some(end), Some(start)), 0.0);
    }

    #[test]
    fn artifact_download_path_returns_path_relative_to_root() {
        let root = temp_dir("artifact-download-root");
        let nested = root.join("manual_actions");
        fs::create_dir_all(&nested).expect("create nested dir");
        let target = nested.join("example.json");
        fs::write(&target, b"{\"ok\":true}").expect("write report");

        let relative = artifact_download_path(&root, &target);
        assert_eq!(relative, "manual_actions/example.json");

        fs::remove_dir_all(&root).expect("cleanup root");
    }

    #[test]
    fn resolve_taker_fee_bps_uses_default_when_unset() {
        let resolved = resolve_taker_fee_bps(None, 1.2).expect("resolve default fee");
        assert!((resolved - 1.2).abs() < 1e-9);
    }

    #[test]
    fn resolve_taker_fee_bps_accepts_valid_override() {
        let resolved = resolve_taker_fee_bps(Some(10.0), 1.2).expect("resolve override fee");
        assert!((resolved - 10.0).abs() < 1e-9);
    }

    #[test]
    fn resolve_taker_fee_bps_rejects_invalid_values() {
        assert!(resolve_taker_fee_bps(Some(-0.1), 1.2).is_err());
        assert!(resolve_taker_fee_bps(Some(10_000.1), 1.2).is_err());
        assert!(resolve_taker_fee_bps(Some(f64::NAN), 1.2).is_err());
    }

    #[test]
    fn parse_backtest_exit_mode_defaults_to_mean_revert() {
        let parsed = parse_backtest_exit_mode(None).expect("parse default exit mode");
        assert_eq!(parsed.as_str(), "mean_revert");
    }

    #[test]
    fn parse_backtest_exit_mode_accepts_supported_values() {
        let mean_revert =
            parse_backtest_exit_mode(Some("mean_revert")).expect("parse mean_revert exit mode");
        assert_eq!(mean_revert.as_str(), "mean_revert");

        let opposite_extreme = parse_backtest_exit_mode(Some("opposite_extreme"))
            .expect("parse opposite_extreme exit mode");
        assert_eq!(opposite_extreme.as_str(), "opposite_extreme");
    }

    #[test]
    fn parse_backtest_exit_mode_rejects_invalid_values() {
        assert!(parse_backtest_exit_mode(Some("hold_to_expiry")).is_err());
    }

    #[test]
    fn sampled_slippage_math_uses_bid_ask_index_and_hedge_ratio() {
        let left = StrategyMarketMetricsResponse {
            instrument: "PF_LEFT".to_string(),
            server_time: Utc::now(),
            bid: 99.8,
            ask: 100.2,
            mark: 100.0,
            index: 100.0,
            change_24h_pct: 0.0,
            funding_rate: 0.0,
            open_interest: 0.0,
        };
        let right = StrategyMarketMetricsResponse {
            instrument: "PF_RIGHT".to_string(),
            server_time: Utc::now(),
            bid: 49.9,
            ask: 50.1,
            mark: 50.0,
            index: 50.0,
            change_24h_pct: 0.0,
            funding_rate: 0.0,
            open_interest: 0.0,
        };

        let (long_bps, short_bps) =
            compute_pair_slippage_sample_bps(&left, &right, 1.0).expect("slippage sample");
        assert!(long_bps > 0.0);
        assert!(short_bps > 0.0);
    }

    #[test]
    fn sampled_slippage_math_rejects_crossed_quotes() {
        let left = StrategyMarketMetricsResponse {
            instrument: "PF_LEFT".to_string(),
            server_time: Utc::now(),
            bid: 100.2,
            ask: 100.1,
            mark: 100.1,
            index: 100.1,
            change_24h_pct: 0.0,
            funding_rate: 0.0,
            open_interest: 0.0,
        };
        let right = StrategyMarketMetricsResponse {
            instrument: "PF_RIGHT".to_string(),
            server_time: Utc::now(),
            bid: 49.9,
            ask: 50.1,
            mark: 50.0,
            index: 50.0,
            change_24h_pct: 0.0,
            funding_rate: 0.0,
            open_interest: 0.0,
        };
        assert!(compute_pair_slippage_sample_bps(&left, &right, 1.0).is_none());
    }

    #[test]
    fn sampled_slippage_status_maps_to_fail_closed_codes() {
        assert_eq!(
            SampledSlippageStatus::Warming.rationale_code(),
            Some("SLIPPAGE_DATA_WARMING")
        );
        assert_eq!(
            SampledSlippageStatus::Stale.rationale_code(),
            Some("SLIPPAGE_DATA_STALE")
        );
        assert_eq!(
            SampledSlippageStatus::Down.rationale_code(),
            Some("SLIPPAGE_DATA_UNAVAILABLE")
        );
        assert_eq!(SampledSlippageStatus::Healthy.rationale_code(), None);
    }

    #[test]
    fn bootstrap_snapshot_freshness_requires_recent_non_future_samples() {
        let now = chrono::DateTime::parse_from_rfc3339("2026-02-25T12:00:00Z")
            .expect("parse now")
            .with_timezone(&Utc);
        let stale_after = chrono::Duration::seconds(20);
        assert!(bootstrap_snapshot_is_fresh(
            now - chrono::Duration::seconds(39),
            now,
            stale_after
        ));
        assert!(bootstrap_snapshot_is_fresh(
            now - chrono::Duration::seconds(40),
            now,
            stale_after
        ));
        assert!(!bootstrap_snapshot_is_fresh(
            now - chrono::Duration::seconds(41),
            now,
            stale_after
        ));
        assert!(!bootstrap_snapshot_is_fresh(
            now + chrono::Duration::seconds(1),
            now,
            stale_after
        ));
    }

    #[test]
    fn bootstrap_deviation_threshold_flags_large_or_invalid_jumps() {
        assert!(!bootstrap_deviation_exceeds_threshold(
            1.0, 1.0, 1.8, 1.2, 1.0
        ));
        assert!(bootstrap_deviation_exceeds_threshold(
            1.0, 1.0, 2.2, 1.0, 1.0
        ));
        assert!(bootstrap_deviation_exceeds_threshold(
            f64::NAN,
            1.0,
            1.0,
            1.0,
            1.0
        ));
    }

    #[test]
    fn funding_sample_math_nets_to_zero_when_leg_rates_offset() {
        let left = StrategyMarketMetricsResponse {
            instrument: "PF_LEFT".to_string(),
            server_time: Utc::now(),
            bid: 99.9,
            ask: 100.1,
            mark: 100.0,
            index: 100.0,
            change_24h_pct: 0.0,
            funding_rate: 0.0001,
            open_interest: 0.0,
        };
        let right = StrategyMarketMetricsResponse {
            instrument: "PF_RIGHT".to_string(),
            server_time: Utc::now(),
            bid: 99.9,
            ask: 100.1,
            mark: 100.0,
            index: 100.0,
            change_24h_pct: 0.0,
            funding_rate: 0.0001,
            open_interest: 0.0,
        };
        let (long_spread, short_spread) = compute_pair_funding_bps_per_event(
            &left,
            &right,
            1.0,
            10_000.0,
            true,
            FundingRateInputMode::Fraction,
        )
        .expect("funding sample should compute");
        assert!(long_spread.abs() < 1e-9);
        assert!(short_spread.abs() < 1e-9);
    }

    #[test]
    fn funding_rate_normalization_supports_fraction_percent_and_auto() {
        assert!(
            (normalize_funding_rate(0.00025, FundingRateInputMode::Fraction) - 0.00025).abs()
                < 1e-12
        );
        assert!(
            (normalize_funding_rate(0.025, FundingRateInputMode::Percent) - 0.00025).abs() < 1e-12
        );
        assert!((normalize_funding_rate(2.5, FundingRateInputMode::Bps) - 0.00025).abs() < 1e-12);
        assert!(
            (normalize_funding_rate(0.025, FundingRateInputMode::Auto) - 0.00025).abs() < 1e-12
        );
        assert!(
            (normalize_funding_rate(0.00025, FundingRateInputMode::Auto) - 0.00025).abs() < 1e-12
        );
        assert!(
            (normalize_funding_rate(0.009, FundingRateInputMode::Auto) - 0.00009).abs() < 1e-12
        );
        assert!(
            (normalize_funding_rate(-0.009, FundingRateInputMode::Auto) - (-0.00009)).abs() < 1e-12
        );
        assert!(
            (normalize_funding_rate(0.716, FundingRateInputMode::Auto) - 0.0000716).abs() < 1e-12
        );
        assert!(
            (normalize_funding_rate(-0.716, FundingRateInputMode::Auto) - (-0.0000716)).abs()
                < 1e-12
        );
    }

    #[test]
    fn expected_funding_events_respects_time_to_next_boundary() {
        let evaluated_at = chrono::DateTime::parse_from_rfc3339("2026-02-24T00:10:00Z")
            .expect("parse timestamp")
            .with_timezone(&Utc);
        let no_event =
            expected_funding_events_crossed(evaluated_at, 30, Timeframe::OneMinute, 3600, 0);
        let one_event =
            expected_funding_events_crossed(evaluated_at, 60, Timeframe::OneMinute, 3600, 0);
        let two_events =
            expected_funding_events_crossed(evaluated_at, 130, Timeframe::OneMinute, 3600, 0);
        assert_eq!(no_event, 0);
        assert_eq!(one_event, 1);
        assert_eq!(two_events, 2);
    }

    #[test]
    fn continuous_funding_projection_scales_for_sub_hour_holds() {
        let projected = project_continuous_funding_bps(0.6, 30, Timeframe::OneMinute, 3600);
        assert!((projected - 0.3).abs() < 1e-9);
    }

    #[test]
    fn continuous_funding_projection_scales_for_multi_hour_holds() {
        let projected = project_continuous_funding_bps(0.6, 130, Timeframe::OneMinute, 3600);
        assert!((projected - 1.3).abs() < 1e-9);
    }

    #[test]
    fn continuous_funding_projection_respects_funding_interval() {
        let projected = project_continuous_funding_bps(0.3, 120, Timeframe::OneMinute, 1800);
        assert!((projected - 1.2).abs() < 1e-9);
    }

    #[test]
    fn trade_gate_blocks_when_setup_fails_even_if_cost_passes() {
        let mut cue = PairCue {
            pair_id: "PF_XBTUSD__PF_ETHUSD".to_string(),
            left_instrument: "PF_XBTUSD".to_string(),
            right_instrument: "PF_ETHUSD".to_string(),
            timeframe: "1h".to_string(),
            regime: "CALM".to_string(),
            selected_variant: "COINTEGRATION_Z".to_string(),
            direction_hint: "NONE".to_string(),
            spread_z: 0.0,
            opportunity_score: 1.0,
            confidence_band: "HIGH".to_string(),
            entry_band: 1.8,
            exit_band: 0.6,
            stop_band: 3.2,
            expected_hold_bars: 12,
            cost_estimate_bps: 0.0,
            setup_actionable: false,
            actionable: false,
            rationale_codes: vec![],
            setup_gate: SetupGateDiagnostics::unavailable(vec![]),
            cost_gate: CostGateDiagnostics {
                status: "AVAILABLE".to_string(),
                expected_edge_bps: 5.0,
                fee_bps: 1.2,
                funding_model: "DYNAMIC".to_string(),
                funding_events: 12,
                funding_bps_per_event: 0.2,
                funding_bps: 2.4,
                slippage_bps: 0.5,
                net_edge_bps: 0.9,
                pass: true,
                rationale_codes: vec![],
            },
            trade_gate: TradeGateDiagnostics::unavailable(vec![]),
            portfolio_hint: PortfolioHint::unavailable(vec![]),
            shadow_ml: ShadowMlDiagnostics::unavailable(vec![]),
            evaluated_at: Utc::now(),
        };

        cue.rationale_codes.push("BELOW_ENTRY_BAND".to_string());
        refresh_setup_gate(&mut cue);
        finalize_trade_gate(&mut cue);
        assert!(cue.cost_gate.pass);
        assert!(!cue.trade_gate.pass);
        assert_eq!(cue.trade_gate.blocked_by, "SETUP");
        assert!(cue
            .trade_gate
            .rationale_codes
            .iter()
            .any(|code| code == "BELOW_ENTRY_BAND"));
    }
}
