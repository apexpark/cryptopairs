use axum::{
    extract::{Query, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use common_types::Timeframe;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use strategy_service::{
    annotate_with_shadow_model, apply_portfolio_plan_to_cues, build_portfolio_plan,
    compute_backtest_series, evaluate_cost_gate, evaluate_pair, train_shadow_model, BacktestConfig,
    CandidateSetDiagnostics, CostGateInput, PairCue, PairEvaluationInput, PairEvaluationOutput,
    PortfolioPlan, Regime, ShadowModelTrainingRow, SignalVariant,
};
use tokio::net::TcpListener;
use tokio_postgres::{types::ToSql, Client, NoTls};
use tower_http::cors::{Any, CorsLayer};
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
    shadow_ml_min_rows: usize,
    shadow_ml_training_limit: usize,
    trading_fee_bps: f64,
    slippage_base_bps: f64,
    slippage_vol_multiplier: f64,
    slippage_z_multiplier: f64,
    min_net_edge_bps: f64,
    advisory_gross_cap: f64,
    advisory_per_pair_cap: f64,
    advisory_enabled: bool,
    champion_switch_min_delta: f64,
    block_on_champion_drift: bool,
    maintenance_report_path: String,
    maintenance_artifacts_root: String,
    maintenance_apply_script_path: String,
    maintenance_env_file_path: String,
    maintenance_deploy_script_path: String,
    maintenance_action_output_root: String,
    maintenance_action_queue_root: String,
    maintenance_action_timeout_secs: u64,
    maintenance_action_skip_pull: bool,
}

impl StrategySettings {
    fn from_env() -> Self {
        let port = std::env::var("STRATEGY_SERVICE_PORT").unwrap_or_else(|_| "8083".to_string());
        let postgres_url = std::env::var("POSTGRES_URL").unwrap_or_else(|_| {
            "postgres://cryptopairs:cryptopairs@127.0.0.1:5432/cryptopairs".to_string()
        });

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
        let min_net_edge_bps = parse_env_f64("STRATEGY_MIN_NET_EDGE_BPS", 0.0);
        let advisory_gross_cap = parse_env_f64("STRATEGY_ADVISORY_GROSS_CAP", 1.0);
        let advisory_per_pair_cap = parse_env_f64("STRATEGY_ADVISORY_PER_PAIR_CAP", 0.35);
        let advisory_enabled = parse_env_bool("STRATEGY_ADVISORY_ENABLED", true);
        let champion_switch_min_delta = parse_env_f64("STRATEGY_CHAMPION_SWITCH_MIN_DELTA", 0.25);
        let block_on_champion_drift = parse_env_bool("STRATEGY_BLOCK_ON_CHAMPION_DRIFT", true);
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
            shadow_ml_min_rows,
            shadow_ml_training_limit,
            trading_fee_bps,
            slippage_base_bps,
            slippage_vol_multiplier,
            slippage_z_multiplier,
            min_net_edge_bps,
            advisory_gross_cap,
            advisory_per_pair_cap,
            advisory_enabled,
            champion_switch_min_delta,
            block_on_champion_drift,
            maintenance_report_path,
            maintenance_artifacts_root,
            maintenance_apply_script_path,
            maintenance_env_file_path,
            maintenance_deploy_script_path,
            maintenance_action_output_root,
            maintenance_action_queue_root,
            maintenance_action_timeout_secs,
            maintenance_action_skip_pull,
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
}

#[derive(Debug, Deserialize)]
struct BacktestQuery {
    timeframe: String,
    pair_id: String,
    bars: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct LiveZQuery {
    timeframe: String,
    pair_id: String,
    points: Option<usize>,
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
    funding_bps: f64,
    slippage_bps: f64,
    net_edge_bps: f64,
    pass: bool,
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
    let state = AppState {
        repository,
        settings: settings.clone(),
    };

    let _worker = spawn_reoptimize_worker(state.clone());
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/strategy/pairs/cues", get(pairs_cues))
        .route("/v1/strategy/pairs/backtest", get(pairs_backtest))
        .route("/v1/strategy/pairs/live-z", get(pairs_live_z))
        .route("/v1/strategy/pairs/cost-gate", get(pairs_cost_gate))
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
        advisory_enabled = settings.advisory_enabled,
        advisory_gross_cap = settings.advisory_gross_cap,
        advisory_per_pair_cap = settings.advisory_per_pair_cap,
        champion_switch_min_delta = settings.champion_switch_min_delta,
        block_on_champion_drift = settings.block_on_champion_drift,
        maintenance_report_path = %settings.maintenance_report_path,
        maintenance_artifacts_root = %settings.maintenance_artifacts_root,
        maintenance_apply_script_path = %settings.maintenance_apply_script_path,
        maintenance_env_file_path = %settings.maintenance_env_file_path,
        maintenance_deploy_script_path = %settings.maintenance_deploy_script_path,
        maintenance_action_output_root = %settings.maintenance_action_output_root,
        maintenance_action_queue_root = %settings.maintenance_action_queue_root,
        maintenance_action_timeout_secs = settings.maintenance_action_timeout_secs,
        maintenance_action_skip_pull = settings.maintenance_action_skip_pull,
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
                let (outputs, skipped, plan) =
                    evaluate_timeframe_outputs(&state, *timeframe, state.settings.advisory_enabled)
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
    let (mut outputs, skipped, portfolio_plan) =
        evaluate_timeframe_outputs(&state, timeframe, include_advisory).await;

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
                    cue.actionable = false;
                    cue.direction_hint = "NONE".to_string();
                    cue.rationale_codes
                        .push("CHAMPION_DRIFT_BLOCKED".to_string());
                }
            }
        }

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
    let (outputs, skipped, _plan) =
        evaluate_timeframe_outputs(&state, timeframe, state.settings.advisory_enabled).await;

    let gates = outputs
        .into_iter()
        .map(|output| CostGatePair {
            pair_id: output.cue.pair_id,
            left_instrument: output.cue.left_instrument,
            right_instrument: output.cue.right_instrument,
            timeframe: output.cue.timeframe,
            expected_edge_bps: output.cue.cost_gate.expected_edge_bps,
            fee_bps: output.cue.cost_gate.fee_bps,
            funding_bps: output.cue.cost_gate.funding_bps,
            slippage_bps: output.cue.cost_gate.slippage_bps,
            net_edge_bps: output.cue.cost_gate.net_edge_bps,
            pass: output.cue.cost_gate.pass,
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

fn days_covered(first: Option<DateTime<Utc>>, last: Option<DateTime<Utc>>) -> f64 {
    match (first, last) {
        (Some(start), Some(end)) if end >= start => {
            let seconds = (end - start).num_seconds() as f64;
            (seconds / 86_400.0).max(0.0)
        }
        _ => 0.0,
    }
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

async fn pairs_backtest(
    State(state): State<AppState>,
    Query(query): Query<BacktestQuery>,
) -> Result<Json<BacktestResponse>, ApiError> {
    let timeframe = Timeframe::parse(&query.timeframe).ok_or_else(|| {
        ApiError::BadRequest("invalid timeframe; expected 1m, 15m, 1h".to_string())
    })?;
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

    let output =
        evaluate_pair_for_timeframe(&state, pair, timeframe, state.settings.advisory_enabled)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?;

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
        bars,
        points = series.points.len(),
        markers = series.markers.len(),
        "strategy backtest response generated"
    );

    Ok(Json(BacktestResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id: query.pair_id,
        generated_at: Utc::now(),
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

    let output =
        evaluate_pair_for_timeframe(&state, pair, timeframe, state.settings.advisory_enabled)
            .await
            .map_err(|error| ApiError::Upstream(error.to_string()))?;
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
        points = series.points.len(),
        markers = series.markers.len(),
        "strategy live z-series generated"
    );

    Ok(Json(LiveZResponse {
        timeframe: timeframe.as_str().to_string(),
        pair_id: query.pair_id,
        generated_at: Utc::now(),
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
    let (_outputs, skipped, plan) =
        evaluate_timeframe_outputs(&state, timeframe, include_advisory).await;

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
        let (outputs, skipped, plan) =
            evaluate_timeframe_outputs(&state, *timeframe, state.settings.advisory_enabled).await;
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
                    pair_id: output.cue.pair_id,
                    timeframe: timeframe.as_str().to_string(),
                    error: format!("opportunity history persist failed: {error}"),
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

    if advisory_enabled {
        let cost_gate = evaluate_cost_gate(CostGateInput {
            expected_edge_bps: output.cue.opportunity_score.max(0.0),
            fee_bps: state.settings.trading_fee_bps,
            funding_bps: output.cue.cost_estimate_bps.max(0.0),
            spread_vol_bps: output.spread_vol_bps.max(0.0),
            spread_z: output.cue.spread_z,
            slippage_base_bps: state.settings.slippage_base_bps,
            slippage_vol_multiplier: state.settings.slippage_vol_multiplier,
            slippage_z_multiplier: state.settings.slippage_z_multiplier,
            min_net_edge_bps: state.settings.min_net_edge_bps,
        });

        if !cost_gate.pass {
            output.cue.actionable = false;
            if !output
                .cue
                .rationale_codes
                .iter()
                .any(|code| code == "COST_GATE_BLOCKED")
            {
                output
                    .cue
                    .rationale_codes
                    .push("COST_GATE_BLOCKED".to_string());
            }
        }
        output.cue.cost_gate = cost_gate;
    } else {
        output.cue.cost_gate = strategy_service::CostGateDiagnostics::unavailable(vec![
            "ADVISORY_DISABLED".to_string(),
        ]);
    }

    Ok(output)
}

async fn evaluate_timeframe_outputs(
    state: &AppState,
    timeframe: Timeframe,
    advisory_enabled: bool,
) -> (Vec<PairEvaluationOutput>, Vec<SkippedPair>, PortfolioPlan) {
    let mut outputs = vec![];
    let mut skipped = vec![];

    for pair in &state.settings.pairs {
        match evaluate_pair_for_timeframe(state, pair, timeframe, advisory_enabled).await {
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
        artifact_download_path, days_covered, decide_champion_transition,
        parse_opportunity_history_stats_timeframe, parse_opportunity_history_window,
        resolve_artifact_path, ChampionDecision, MaintenanceAction, OpportunityHistoryQuery,
        OpportunityHistoryStatsQuery, SelectedSignalRow,
    };
    use chrono::Utc;
    use std::fs;
    use std::path::PathBuf;
    use strategy_service::{
        CostGateDiagnostics, PairCue, PairEvaluationOutput, PortfolioHint, ShadowMlDiagnostics,
        VariantEvaluation,
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
                actionable: false,
                rationale_codes: vec![],
                cost_gate: CostGateDiagnostics::unavailable(vec![]),
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
}
