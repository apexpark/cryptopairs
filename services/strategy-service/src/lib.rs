use chrono::{DateTime, Utc};
use common_types::{quantize_price_to_tick, InstrumentTradingConstraints, Timeframe};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Regime {
    Calm,
    Trending,
    Shock,
}

impl Regime {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Calm => "CALM",
            Self::Trending => "TRENDING",
            Self::Shock => "SHOCK",
        }
    }

    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "CALM" => Some(Self::Calm),
            "TRENDING" => Some(Self::Trending),
            "SHOCK" => Some(Self::Shock),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum SignalVariant {
    CointegrationZ,
    RobustZ,
    VolNormalized,
    FundingAdjusted,
}

impl SignalVariant {
    pub fn all() -> [Self; 4] {
        [
            Self::CointegrationZ,
            Self::RobustZ,
            Self::VolNormalized,
            Self::FundingAdjusted,
        ]
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::CointegrationZ => "COINTEGRATION_Z",
            Self::RobustZ => "ROBUST_Z",
            Self::VolNormalized => "VOL_NORMALIZED",
            Self::FundingAdjusted => "FUNDING_ADJUSTED",
        }
    }

    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "COINTEGRATION_Z" => Some(Self::CointegrationZ),
            "ROBUST_Z" => Some(Self::RobustZ),
            "VOL_NORMALIZED" => Some(Self::VolNormalized),
            "FUNDING_ADJUSTED" => Some(Self::FundingAdjusted),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum DirectionHint {
    LongSpread,
    ShortSpread,
    None,
}

impl DirectionHint {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::LongSpread => "LONG_SPREAD",
            Self::ShortSpread => "SHORT_SPREAD",
            Self::None => "NONE",
        }
    }
}

const STOP_RETRACE_FRACTION: f64 = 0.25;
const MIN_PRIOR_Z_STDDEV: f64 = 1e-6;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum FundingModel {
    Static,
    Dynamic,
}

impl FundingModel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Static => "STATIC",
            Self::Dynamic => "DYNAMIC",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct VariantEvaluation {
    pub variant: String,
    pub score_last: f64,
    pub sample_count: usize,
    pub win_rate: f64,
    pub edge_bps: f64,
    pub reliability: f64,
    pub regime_fit: f64,
    pub opportunity_score: f64,
    pub shadow_success_probability: Option<f64>,
    pub shadow_rank_score: Option<f64>,
    pub rationale_codes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CostGateDiagnostics {
    pub status: String,
    pub expected_edge_bps: f64,
    pub fee_bps: f64,
    pub funding_model: String,
    pub funding_events: u32,
    pub funding_bps_per_event: f64,
    pub funding_bps: f64,
    pub slippage_bps: f64,
    pub net_edge_bps: f64,
    pub pass: bool,
    pub rationale_codes: Vec<String>,
}

impl CostGateDiagnostics {
    pub fn unavailable(rationale_codes: Vec<String>) -> Self {
        Self {
            status: "WAIT".to_string(),
            expected_edge_bps: 0.0,
            fee_bps: 0.0,
            funding_model: FundingModel::Static.as_str().to_string(),
            funding_events: 0,
            funding_bps_per_event: 0.0,
            funding_bps: 0.0,
            slippage_bps: 0.0,
            net_edge_bps: 0.0,
            pass: false,
            rationale_codes,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SetupGateDiagnostics {
    pub status: String,
    pub pass: bool,
    pub rationale_codes: Vec<String>,
}

impl SetupGateDiagnostics {
    pub fn unavailable(rationale_codes: Vec<String>) -> Self {
        Self {
            status: "WAIT".to_string(),
            pass: false,
            rationale_codes,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct TradeGateDiagnostics {
    pub status: String,
    pub pass: bool,
    pub blocked_by: String,
    pub rationale_codes: Vec<String>,
}

impl TradeGateDiagnostics {
    pub fn unavailable(rationale_codes: Vec<String>) -> Self {
        Self {
            status: "WAIT".to_string(),
            pass: false,
            blocked_by: "WAIT".to_string(),
            rationale_codes,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct CostGateInput {
    pub expected_edge_bps: f64,
    pub fee_bps: f64,
    pub funding_model: FundingModel,
    pub funding_events: u32,
    pub funding_bps_per_event: f64,
    pub funding_bps: f64,
    pub spread_vol_bps: f64,
    pub spread_z: f64,
    pub sampled_slippage_bps: Option<f64>,
    pub slippage_base_bps: f64,
    pub slippage_vol_multiplier: f64,
    pub slippage_z_multiplier: f64,
    pub min_net_edge_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PortfolioHint {
    pub status: String,
    pub target_weight: f64,
    pub risk_contribution: f64,
    pub cap_applied: bool,
    pub rationale_codes: Vec<String>,
}

impl PortfolioHint {
    pub fn unavailable(rationale_codes: Vec<String>) -> Self {
        Self {
            status: "UNAVAILABLE".to_string(),
            target_weight: 0.0,
            risk_contribution: 0.0,
            cap_applied: false,
            rationale_codes,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PortfolioPlanEntry {
    pub pair_id: String,
    pub target_weight: f64,
    pub risk_contribution: f64,
    pub cap_applied: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct PortfolioPlanConstraints {
    pub dollar_neutral: bool,
    pub gross_cap: f64,
    pub per_pair_cap: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PortfolioPlan {
    pub status: String,
    pub weights: Vec<PortfolioPlanEntry>,
    pub constraints: PortfolioPlanConstraints,
    pub rationale_codes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CandidateSetDiagnostics {
    pub total_pairs: usize,
    pub evaluated_pairs: usize,
    pub actionable_pairs: usize,
    pub cost_gate_pass_pairs: usize,
    pub shadow_disagreement_pairs: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct ShadowMlDiagnostics {
    pub status: String,
    pub model_name: String,
    pub training_rows: usize,
    pub positive_rate: f64,
    pub precision: f64,
    pub brier_score: f64,
    pub recommended_variant: String,
    pub recommended_probability: f64,
    pub agrees_with_selected: bool,
    pub rationale_codes: Vec<String>,
}

impl ShadowMlDiagnostics {
    pub fn unavailable(rationale_codes: Vec<String>) -> Self {
        Self {
            status: "UNAVAILABLE".to_string(),
            model_name: "LOGISTIC_V1".to_string(),
            training_rows: 0,
            positive_rate: 0.0,
            precision: 0.0,
            brier_score: 0.0,
            recommended_variant: "NONE".to_string(),
            recommended_probability: 0.0,
            agrees_with_selected: false,
            rationale_codes,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SelectedSignalConfig {
    pub variant: String,
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub lookback_bars: usize,
    pub hold_bars: usize,
    pub max_half_life_bars: f64,
    pub train_bars: usize,
    pub validation_bars: usize,
    pub source: String,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CueSelectionState {
    pub best_variant: String,
    pub best_opportunity_score: f64,
    pub best_direction_hint: String,
    pub best_confidence_band: String,
    pub stored_champion_variant: Option<String>,
    pub stored_champion_score: Option<f64>,
    pub stored_champion_direction_hint: Option<String>,
    pub stored_champion_confidence_band: Option<String>,
    pub transition_decision: String,
    pub score_delta_to_champion: Option<f64>,
    pub drift_active: bool,
    pub source: String,
    pub validation_state: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PairCue {
    pub pair_id: String,
    pub left_instrument: String,
    pub right_instrument: String,
    pub timeframe: String,
    pub regime: String,
    pub selected_variant: String,
    pub direction_hint: String,
    pub spread_z: f64,
    pub opportunity_score: f64,
    pub confidence_band: String,
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub expected_hold_bars: i64,
    pub cost_estimate_bps: f64,
    pub setup_actionable: bool,
    pub actionable: bool,
    pub rationale_codes: Vec<String>,
    pub setup_gate: SetupGateDiagnostics,
    pub cost_gate: CostGateDiagnostics,
    pub trade_gate: TradeGateDiagnostics,
    pub portfolio_hint: PortfolioHint,
    pub shadow_ml: ShadowMlDiagnostics,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub selection_state: Option<CueSelectionState>,
    pub selected_signal_config: SelectedSignalConfig,
    pub evaluated_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct PairEvaluationInput {
    pub pair_id: String,
    pub left_instrument: String,
    pub right_instrument: String,
    pub timeframe: Timeframe,
    pub timestamps: Vec<DateTime<Utc>>,
    pub left_closes: Vec<f64>,
    pub right_closes: Vec<f64>,
    pub lookback_bars: usize,
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub hold_bars: usize,
    pub max_half_life_bars: f64,
    pub train_bars: usize,
    pub validation_bars: usize,
    pub funding_drag_bps: f64,
    pub taker_fee_bps: f64,
    pub min_samples_target: usize,
    pub selected_signal_config: Option<SelectedSignalConfig>,
}

#[derive(Debug, Clone)]
pub struct PairEvaluationOutput {
    pub cue: PairCue,
    pub variants: Vec<VariantEvaluation>,
    pub half_life_bars: f64,
    pub hedge_ratio: f64,
    pub hedge_ratio_stability: f64,
    pub spread_vol_bps: f64,
    pub stored_champion_variant: Option<String>,
    pub stored_champion_projection: Option<PairCue>,
    pub flatline_diagnostics: SignalFlatlineDiagnostics,
}

#[derive(Debug, Clone, Serialize)]
pub struct SignalFlatlineDiagnostics {
    pub status: String,
    pub window_bars: usize,
    pub z_stddev: f64,
    pub z_p95_minus_p5: f64,
    pub zero_crossings: usize,
    pub entry_band_crossings: usize,
    pub max_abs_z: f64,
    pub rationale_codes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BacktestPoint {
    pub ts: DateTime<Utc>,
    pub z: f64,
    pub equity: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct BacktestMarker {
    pub index: usize,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BacktestSeries {
    pub points: Vec<BacktestPoint>,
    pub markers: Vec<BacktestMarker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BacktestExitMode {
    MeanRevert,
    OppositeExtreme,
}

impl BacktestExitMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::MeanRevert => "mean_revert",
            Self::OppositeExtreme => "opposite_extreme",
        }
    }

    pub fn parse(raw: &str) -> Option<Self> {
        match raw.trim().to_ascii_lowercase().as_str() {
            "mean_revert" => Some(Self::MeanRevert),
            "opposite_extreme" => Some(Self::OppositeExtreme),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct BacktestConfig {
    pub hedge_ratio: f64,
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub round_trip_cost_bps: f64,
    pub exit_mode: BacktestExitMode,
    pub left_constraints: Option<InstrumentTradingConstraints>,
    pub right_constraints: Option<InstrumentTradingConstraints>,
}

#[derive(Debug, Clone)]
pub struct ShadowModelTrainingRow {
    pub variant: SignalVariant,
    pub regime: Regime,
    pub score_last: f64,
    pub sample_count: usize,
    pub win_rate: f64,
    pub reliability: f64,
    pub edge_bps: f64,
}

#[derive(Debug, Clone)]
pub struct ShadowModelMetrics {
    pub training_rows: usize,
    pub positive_rate: f64,
    pub precision: f64,
    pub brier_score: f64,
}

#[derive(Debug, Clone)]
pub struct ShadowModel {
    pub model_name: String,
    pub metrics: ShadowModelMetrics,
    weights: [f64; SHADOW_FEATURE_COUNT],
}

const SHADOW_FEATURE_COUNT: usize = 10;
const SHADOW_MODEL_NAME: &str = "LOGISTIC_V1";

pub fn train_shadow_model(rows: &[ShadowModelTrainingRow], min_rows: usize) -> Option<ShadowModel> {
    let required_rows = min_rows.max(32);
    if rows.len() < required_rows {
        return None;
    }

    let mut positives = 0usize;
    let mut samples = Vec::with_capacity(rows.len());
    for row in rows {
        let label = if row.edge_bps > 0.0 { 1.0 } else { 0.0 };
        positives += usize::from(label > 0.0);
        samples.push((
            shadow_features(
                row.variant,
                row.regime,
                row.score_last,
                row.sample_count,
                row.win_rate,
                row.reliability,
            ),
            label,
        ));
    }

    let negatives = rows.len().saturating_sub(positives);
    if positives < 8 || negatives < 8 {
        return None;
    }

    let mut weights = [0.0_f64; SHADOW_FEATURE_COUNT];
    let lr = 0.9;
    let l2 = 0.02;
    let sample_count = rows.len() as f64;

    for _epoch in 0..280 {
        let mut gradients = [0.0_f64; SHADOW_FEATURE_COUNT];
        for (features, label) in &samples {
            let probability = sigmoid(dot(&weights, features));
            let error = probability - label;
            for idx in 0..SHADOW_FEATURE_COUNT {
                gradients[idx] += error * features[idx];
            }
        }

        for idx in 0..SHADOW_FEATURE_COUNT {
            let regularizer = if idx == 0 { 0.0 } else { l2 * weights[idx] };
            let gradient = (gradients[idx] / sample_count) + regularizer;
            weights[idx] -= lr * gradient;
        }
    }

    let mut true_positive = 0usize;
    let mut predicted_positive = 0usize;
    let mut brier_sum = 0.0;
    for (features, label) in &samples {
        let probability = sigmoid(dot(&weights, features));
        brier_sum += (probability - label).powi(2);
        if probability >= 0.55 {
            predicted_positive += 1;
            if *label > 0.0 {
                true_positive += 1;
            }
        }
    }

    let precision = if predicted_positive == 0 {
        0.0
    } else {
        true_positive as f64 / predicted_positive as f64
    };
    let metrics = ShadowModelMetrics {
        training_rows: rows.len(),
        positive_rate: positives as f64 / rows.len() as f64,
        precision,
        brier_score: brier_sum / rows.len() as f64,
    };

    Some(ShadowModel {
        model_name: SHADOW_MODEL_NAME.to_string(),
        metrics,
        weights,
    })
}

impl ShadowModel {
    pub fn predict_probability(
        &self,
        variant: SignalVariant,
        regime: Regime,
        score_last: f64,
        sample_count: usize,
        win_rate: f64,
        reliability: f64,
    ) -> f64 {
        let features = shadow_features(
            variant,
            regime,
            score_last,
            sample_count,
            win_rate,
            reliability,
        );
        sigmoid(dot(&self.weights, &features))
    }
}

pub fn annotate_with_shadow_model(
    output: &mut PairEvaluationOutput,
    model: Option<&ShadowModel>,
) -> ShadowMlDiagnostics {
    let Some(model) = model else {
        let diagnostics =
            ShadowMlDiagnostics::unavailable(vec!["INSUFFICIENT_TRAINING_HISTORY".to_string()]);
        output.cue.shadow_ml = diagnostics.clone();
        return diagnostics;
    };

    let regime = Regime::parse(&output.cue.regime).unwrap_or(Regime::Calm);
    let mut recommended_variant = "NONE".to_string();
    let mut recommended_probability = 0.0;
    let mut recommended_rank_score = f64::NEG_INFINITY;

    for variant in &mut output.variants {
        let parsed_variant = SignalVariant::parse(&variant.variant);
        if let Some(parsed_variant) = parsed_variant {
            let probability = model.predict_probability(
                parsed_variant,
                regime,
                variant.score_last,
                variant.sample_count,
                variant.win_rate,
                variant.reliability,
            );
            let rank_score = if variant.opportunity_score >= 0.0 {
                variant.opportunity_score * (0.5 + probability)
            } else {
                variant.opportunity_score * (1.5 - probability)
            };
            variant.shadow_success_probability = Some(probability);
            variant.shadow_rank_score = Some(rank_score);
            if rank_score > recommended_rank_score {
                recommended_rank_score = rank_score;
                recommended_variant = variant.variant.clone();
                recommended_probability = probability;
            }
        } else {
            variant.shadow_success_probability = None;
            variant.shadow_rank_score = None;
        }
    }

    let agrees_with_selected = recommended_variant == output.cue.selected_variant;
    if !agrees_with_selected && recommended_variant != "NONE" {
        output
            .cue
            .rationale_codes
            .push("SHADOW_ML_VARIANT_DISAGREEMENT".to_string());
    }

    let diagnostics = ShadowMlDiagnostics {
        status: "AVAILABLE".to_string(),
        model_name: model.model_name.clone(),
        training_rows: model.metrics.training_rows,
        positive_rate: model.metrics.positive_rate,
        precision: model.metrics.precision,
        brier_score: model.metrics.brier_score,
        recommended_variant,
        recommended_probability,
        agrees_with_selected,
        rationale_codes: vec![],
    };
    output.cue.shadow_ml = diagnostics.clone();
    diagnostics
}

pub fn evaluate_cost_gate(input: CostGateInput) -> CostGateDiagnostics {
    let mut rationale_codes = vec![];

    let expected_edge_bps = input.expected_edge_bps;
    if expected_edge_bps <= 0.0 {
        rationale_codes.push("NEGATIVE_EXPECTED_EDGE".to_string());
    }

    let fee_bps = input.fee_bps.max(0.0);
    let funding_bps_per_event = if input.funding_bps_per_event.is_finite() {
        input.funding_bps_per_event
    } else {
        rationale_codes.push("INVALID_FUNDING_INPUT".to_string());
        0.0
    };
    let funding_bps = if input.funding_bps.is_finite() {
        input.funding_bps
    } else {
        rationale_codes.push("INVALID_FUNDING_INPUT".to_string());
        0.0
    };
    let slippage_bps = if let Some(sampled) = input.sampled_slippage_bps {
        sampled.max(0.0)
    } else {
        (input.slippage_base_bps.max(0.0)
            + input.slippage_vol_multiplier.max(0.0) * input.spread_vol_bps.max(0.0)
            + input.slippage_z_multiplier.max(0.0) * input.spread_z.abs())
        .max(0.0)
    };

    // Funding is informational for operators and is no longer part of
    // the automated cost-gate blocking decision.
    let net_edge_bps = expected_edge_bps - fee_bps - slippage_bps;
    let pass = net_edge_bps > input.min_net_edge_bps.max(0.0);
    if !pass {
        rationale_codes.push("COST_GATE_BLOCKED".to_string());
    }

    CostGateDiagnostics {
        status: "AVAILABLE".to_string(),
        expected_edge_bps,
        fee_bps,
        funding_model: input.funding_model.as_str().to_string(),
        funding_events: input.funding_events,
        funding_bps_per_event,
        funding_bps,
        slippage_bps,
        net_edge_bps,
        pass,
        rationale_codes,
    }
}

pub fn build_portfolio_plan(cues: &[PairCue], gross_cap: f64, per_pair_cap: f64) -> PortfolioPlan {
    let constraints = PortfolioPlanConstraints {
        dollar_neutral: false,
        gross_cap: gross_cap.max(0.0),
        per_pair_cap: per_pair_cap.max(0.0),
    };

    let mut active = vec![];
    for cue in cues {
        if !cue.actionable || cue.cost_gate.status != "AVAILABLE" || !cue.cost_gate.pass {
            continue;
        }
        let sign = match cue.direction_hint.as_str() {
            "LONG_SPREAD" => 1.0,
            "SHORT_SPREAD" => -1.0,
            _ => 0.0,
        };
        if sign == 0.0 {
            continue;
        }

        let score = cue.opportunity_score.max(0.0);
        let net_edge = cue.cost_gate.net_edge_bps.max(0.0);
        let raw = sign * score.max(0.01) * net_edge.max(0.01);
        active.push((cue.pair_id.clone(), raw));
    }

    if active.len() < 2 {
        return PortfolioPlan {
            status: "UNAVAILABLE".to_string(),
            weights: vec![],
            constraints,
            rationale_codes: vec!["INSUFFICIENT_ACTIONABLE_PAIRS".to_string()],
        };
    }

    let mean_raw = active.iter().map(|(_, raw)| *raw).sum::<f64>() / active.len() as f64;
    let mut scaled = active
        .into_iter()
        .map(|(pair_id, raw)| (pair_id, raw - mean_raw))
        .collect::<Vec<_>>();

    let gross_abs = scaled.iter().map(|(_, weight)| weight.abs()).sum::<f64>();
    if gross_abs <= 1e-12 {
        return PortfolioPlan {
            status: "UNAVAILABLE".to_string(),
            weights: vec![],
            constraints,
            rationale_codes: vec!["ZERO_SIGNAL_VECTOR".to_string()],
        };
    }
    let target_gross = constraints.gross_cap.max(1e-9);
    let scale = target_gross / gross_abs;
    for (_, weight) in &mut scaled {
        *weight *= scale;
    }

    let mut any_cap_applied = false;
    if constraints.per_pair_cap > 0.0 {
        for (_, weight) in &mut scaled {
            if weight.abs() > constraints.per_pair_cap {
                *weight = constraints.per_pair_cap.copysign(*weight);
                any_cap_applied = true;
            }
        }
    }

    let demeaned = scaled.iter().map(|(_, weight)| *weight).sum::<f64>() / scaled.len() as f64;
    for (_, weight) in &mut scaled {
        *weight -= demeaned;
    }

    if constraints.per_pair_cap > 0.0 {
        for (_, weight) in &mut scaled {
            if weight.abs() > constraints.per_pair_cap {
                *weight = constraints.per_pair_cap.copysign(*weight);
                any_cap_applied = true;
            }
        }
    }

    let gross_abs = scaled.iter().map(|(_, weight)| weight.abs()).sum::<f64>();
    if gross_abs > constraints.gross_cap && gross_abs > 0.0 {
        let scale_down = constraints.gross_cap / gross_abs;
        for (_, weight) in &mut scaled {
            *weight *= scale_down;
        }
    }

    if scaled.len() > 1 {
        for _ in 0..3 {
            let net = scaled.iter().map(|(_, weight)| *weight).sum::<f64>();
            if net.abs() <= 1e-8 {
                break;
            }
            let adjust = net / scaled.len() as f64;
            for (_, weight) in &mut scaled {
                *weight -= adjust;
                if constraints.per_pair_cap > 0.0 && weight.abs() > constraints.per_pair_cap {
                    *weight = constraints.per_pair_cap.copysign(*weight);
                    any_cap_applied = true;
                }
            }
        }
    }

    let neutral_sum = scaled.iter().map(|(_, weight)| *weight).sum::<f64>();
    let dollar_neutral = neutral_sum.abs() <= 1e-6;
    let risk_denom = scaled
        .iter()
        .map(|(_, weight)| weight.abs())
        .sum::<f64>()
        .max(1e-9);
    let mut weights = scaled
        .into_iter()
        .map(|(pair_id, weight)| PortfolioPlanEntry {
            pair_id,
            target_weight: weight,
            risk_contribution: weight.abs() / risk_denom,
            cap_applied: constraints.per_pair_cap > 0.0 && weight.abs() >= constraints.per_pair_cap,
        })
        .collect::<Vec<_>>();
    weights.sort_by(|left, right| {
        right
            .target_weight
            .abs()
            .partial_cmp(&left.target_weight.abs())
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut rationale_codes = vec![];
    if any_cap_applied {
        rationale_codes.push("PER_PAIR_CAP_APPLIED".to_string());
    }
    if !dollar_neutral {
        rationale_codes.push("NEUTRALITY_APPROXIMATED".to_string());
    }

    PortfolioPlan {
        status: "AVAILABLE".to_string(),
        weights,
        constraints: PortfolioPlanConstraints {
            dollar_neutral,
            gross_cap: constraints.gross_cap,
            per_pair_cap: constraints.per_pair_cap,
        },
        rationale_codes,
    }
}

pub fn apply_portfolio_plan_to_cues(cues: &mut [PairCue], plan: &PortfolioPlan) {
    let mut index = std::collections::HashMap::with_capacity(plan.weights.len());
    for entry in &plan.weights {
        index.insert(entry.pair_id.as_str(), entry);
    }

    for cue in cues {
        if let Some(entry) = index.get(cue.pair_id.as_str()) {
            cue.portfolio_hint = PortfolioHint {
                status: "AVAILABLE".to_string(),
                target_weight: entry.target_weight,
                risk_contribution: entry.risk_contribution,
                cap_applied: entry.cap_applied,
                rationale_codes: vec![],
            };
        } else {
            cue.portfolio_hint =
                PortfolioHint::unavailable(vec!["PAIR_NOT_IN_PORTFOLIO_PLAN".to_string()]);
        }
    }
}

pub fn evaluate_pair(input: PairEvaluationInput) -> anyhow::Result<PairEvaluationOutput> {
    if input.left_closes.len() != input.right_closes.len()
        || input.timestamps.len() != input.left_closes.len()
    {
        return Err(anyhow::anyhow!(
            "aligned series mismatch for pair={} left={} right={}",
            input.pair_id,
            input.left_closes.len(),
            input.right_closes.len()
        ));
    }
    if input.left_closes.len() < 120 {
        return Err(anyhow::anyhow!(
            "insufficient data for pair={} bars={} (need >=120)",
            input.pair_id,
            input.left_closes.len()
        ));
    }

    let left_log = input
        .left_closes
        .iter()
        .map(|value| value.max(1e-9).ln())
        .collect::<Vec<_>>();
    let right_log = input
        .right_closes
        .iter()
        .map(|value| value.max(1e-9).ln())
        .collect::<Vec<_>>();

    let hedge_ratio = ols_beta(&left_log, &right_log).unwrap_or(1.0);
    let spread = left_log
        .iter()
        .zip(right_log.iter())
        .map(|(left, right)| left - hedge_ratio * right)
        .collect::<Vec<_>>();
    let spread_diffs = spread
        .windows(2)
        .map(|window| window[1] - window[0])
        .collect::<Vec<_>>();
    let spread_vol_bps = stddev(&spread_diffs) * 10_000.0;

    let half_life_bars = estimate_half_life(&spread);
    let hedge_ratio_stability = estimate_hedge_ratio_stability(&left_log, &right_log);

    let lookback = input.left_closes.len().min(180);
    let z_scores = rolling_z_scores(&spread, lookback.max(30));
    let robust_z_scores = rolling_robust_z_scores(&spread, lookback.max(30));
    let vol_norm_scores = rolling_vol_normalized_scores(&spread, lookback.max(30));
    let funding_penalty_z = funding_drag_to_z_penalty(input.funding_drag_bps, spread_vol_bps);
    let funding_scores = z_scores
        .iter()
        .map(|value| shrink_score_magnitude(*value, funding_penalty_z))
        .collect::<Vec<_>>();

    let spread_z = *z_scores.last().unwrap_or(&0.0);
    let regime = classify_regime(&spread, spread_z);

    let mut variants = Vec::with_capacity(SignalVariant::all().len());
    for variant in SignalVariant::all() {
        let series = match variant {
            SignalVariant::CointegrationZ => &z_scores,
            SignalVariant::RobustZ => &robust_z_scores,
            SignalVariant::VolNormalized => &vol_norm_scores,
            SignalVariant::FundingAdjusted => &funding_scores,
        };
        let score_last = *series.last().unwrap_or(&0.0);
        let (sample_count, win_rate, edge_bps) = estimate_edge_bps(
            &input.left_closes,
            &input.right_closes,
            hedge_ratio,
            series,
            input.entry_band,
            input.hold_bars,
        );
        let reliability = reliability(sample_count, win_rate, input.min_samples_target);
        let regime_fit = regime_fit_multiplier(regime, variant);
        let score_multiplier = (score_last.abs() / input.entry_band.max(0.1)).clamp(0.25, 2.0);
        let opportunity_score = edge_bps * reliability * regime_fit * score_multiplier;
        let mut rationale_codes = vec![];
        if sample_count < input.min_samples_target {
            rationale_codes.push("LOW_SAMPLE".to_string());
        }
        if edge_bps <= 0.0 {
            rationale_codes.push("NEGATIVE_EDGE".to_string());
        }
        if score_last.abs() < input.entry_band {
            rationale_codes.push("BELOW_ENTRY_BAND".to_string());
        }

        variants.push(VariantEvaluation {
            variant: variant.as_str().to_string(),
            score_last,
            sample_count,
            win_rate,
            edge_bps,
            reliability,
            regime_fit,
            opportunity_score,
            shadow_success_probability: None,
            shadow_rank_score: None,
            rationale_codes,
        });
    }

    let fallback_selected = variants
        .iter()
        .max_by(|left, right| {
            left.opportunity_score
                .partial_cmp(&right.opportunity_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("no signal variants evaluated"))?;

    let evaluated_at = input.timestamps.last().copied().unwrap_or_else(Utc::now);
    let mut selected_signal_config = input
        .selected_signal_config
        .unwrap_or(SelectedSignalConfig {
            variant: fallback_selected.variant.clone(),
            entry_band: input.entry_band,
            exit_band: input.exit_band,
            stop_band: input.stop_band,
            lookback_bars: input.lookback_bars,
            hold_bars: input.hold_bars,
            max_half_life_bars: input.max_half_life_bars,
            train_bars: input.train_bars,
            validation_bars: input.validation_bars,
            source: "SETTINGS_DEFAULT".to_string(),
            updated_at: evaluated_at,
        });
    let configured_variant = SignalVariant::parse(&selected_signal_config.variant);
    let mut selected = configured_variant
        .and_then(|variant| {
            variants
                .iter()
                .find(|candidate| SignalVariant::parse(&candidate.variant) == Some(variant))
                .cloned()
        })
        .unwrap_or_else(|| fallback_selected.clone());
    if SignalVariant::parse(&selected_signal_config.variant).is_none()
        || selected_signal_config.variant != selected.variant
    {
        selected_signal_config.variant = selected.variant.clone();
    }

    let mut cue_rationale = selected.rationale_codes.clone();
    let selected_variant = SignalVariant::parse(&selected.variant);
    let selected_scores = match selected_variant {
        Some(SignalVariant::CointegrationZ) => z_scores.as_slice(),
        Some(SignalVariant::RobustZ) => robust_z_scores.as_slice(),
        Some(SignalVariant::VolNormalized) => vol_norm_scores.as_slice(),
        Some(SignalVariant::FundingAdjusted) => funding_scores.as_slice(),
        None => z_scores.as_slice(),
    };
    let flatline_diagnostics =
        compute_flatline_diagnostics(selected_scores, input.timeframe, input.entry_band);
    let unbounded_direction_hint = to_direction_hint(selected.score_last, input.entry_band);
    let (mut direction_hint, entry_gate_block_reason) = to_direction_hint_with_stop_retrace(
        selected_scores,
        input.entry_band,
        input.stop_band,
        STOP_RETRACE_FRACTION,
    );
    if unbounded_direction_hint != DirectionHint::None && direction_hint == DirectionHint::None {
        cue_rationale.push(entry_gate_block_reason.to_string());
    }
    let mut actionable = direction_hint != DirectionHint::None && selected.opportunity_score > 0.0;

    if !half_life_bars.is_finite() || half_life_bars > input.max_half_life_bars {
        // Advisory warning only: no longer a hard entry block.
        cue_rationale.push("HALF_LIFE_TOO_LONG".to_string());
    }
    if hedge_ratio_stability > 0.40 {
        // Advisory warning only: no longer a hard entry block.
        cue_rationale.push("HEDGE_RATIO_UNSTABLE".to_string());
    }
    if selected.sample_count < input.min_samples_target {
        actionable = false;
        direction_hint = DirectionHint::None;
    }

    let confidence_band = confidence_band(
        selected.reliability,
        selected.sample_count,
        input.min_samples_target,
    );
    let expected_hold_bars = half_life_bars
        .round()
        .clamp(1.0, (input.hold_bars as f64 * 3.0).max(1.0)) as i64;

    let cue = PairCue {
        pair_id: input.pair_id,
        left_instrument: input.left_instrument,
        right_instrument: input.right_instrument,
        timeframe: input.timeframe.as_str().to_string(),
        regime: regime.as_str().to_string(),
        selected_variant: std::mem::take(&mut selected.variant),
        direction_hint: direction_hint.as_str().to_string(),
        spread_z,
        opportunity_score: selected.opportunity_score,
        confidence_band: confidence_band.to_string(),
        entry_band: input.entry_band,
        exit_band: input.exit_band,
        stop_band: input.stop_band,
        expected_hold_bars,
        cost_estimate_bps: input.funding_drag_bps.max(0.0) + input.taker_fee_bps.max(0.0),
        setup_actionable: actionable,
        actionable,
        rationale_codes: cue_rationale,
        setup_gate: SetupGateDiagnostics {
            status: "AVAILABLE".to_string(),
            pass: actionable,
            rationale_codes: selected.rationale_codes.clone(),
        },
        cost_gate: CostGateDiagnostics::unavailable(vec!["NOT_EVALUATED".to_string()]),
        trade_gate: TradeGateDiagnostics::unavailable(vec!["NOT_EVALUATED".to_string()]),
        portfolio_hint: PortfolioHint::unavailable(vec!["NOT_EVALUATED".to_string()]),
        shadow_ml: ShadowMlDiagnostics::unavailable(vec!["NOT_EVALUATED".to_string()]),
        selection_state: None,
        selected_signal_config,
        evaluated_at,
    };

    Ok(PairEvaluationOutput {
        cue,
        variants,
        half_life_bars,
        hedge_ratio,
        hedge_ratio_stability,
        spread_vol_bps,
        stored_champion_variant: None,
        stored_champion_projection: None,
        flatline_diagnostics,
    })
}

fn flatline_window_bars(timeframe: Timeframe) -> usize {
    match timeframe {
        Timeframe::OneMinute => 720,
        Timeframe::FifteenMinutes => 384,
        Timeframe::OneHour => 336,
    }
}

fn compute_flatline_diagnostics(
    selected_scores: &[f64],
    timeframe: Timeframe,
    entry_band: f64,
) -> SignalFlatlineDiagnostics {
    let window_bars = flatline_window_bars(timeframe);
    let finite_scores = selected_scores
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    let start_idx = finite_scores.len().saturating_sub(window_bars);
    let window = &finite_scores[start_idx..];
    if window.len() < 2 {
        return SignalFlatlineDiagnostics {
            status: "HEALTHY".to_string(),
            window_bars,
            z_stddev: 0.0,
            z_p95_minus_p5: 0.0,
            zero_crossings: 0,
            entry_band_crossings: 0,
            max_abs_z: 0.0,
            rationale_codes: vec!["INSUFFICIENT_DATA".to_string()],
        };
    }

    let z_stddev = stddev(window);
    let z_p95_minus_p5 = percentile(window, 0.95) - percentile(window, 0.05);
    let max_abs_z = window.iter().map(|value| value.abs()).fold(0.0, f64::max);
    let mut zero_crossings = 0usize;
    for pair in window.windows(2) {
        let prev = pair[0];
        let curr = pair[1];
        if (prev <= 0.0 && curr > 0.0) || (prev >= 0.0 && curr < 0.0) {
            zero_crossings = zero_crossings.saturating_add(1);
        }
    }
    let mut entry_band_crossings = 0usize;
    for pair in window.windows(2) {
        let prev_outside = pair[0].abs() >= entry_band;
        let curr_outside = pair[1].abs() >= entry_band;
        if !prev_outside && curr_outside {
            entry_band_crossings = entry_band_crossings.saturating_add(1);
        }
    }

    let warn_checks = [
        ("FLATLINE_LOW_STDDEV_WARN", z_stddev < 0.35),
        ("FLATLINE_LOW_RANGE_WARN", z_p95_minus_p5 < 1.20),
        ("FLATLINE_LOW_ZERO_CROSS_WARN", zero_crossings < 2),
        (
            "FLATLINE_NO_ENTRY_BAND_CROSS_WARN",
            entry_band_crossings == 0,
        ),
    ];
    let flatline_checks = [
        ("FLATLINE_LOW_STDDEV", z_stddev < 0.20),
        ("FLATLINE_LOW_RANGE", z_p95_minus_p5 < 0.70),
        ("FLATLINE_NO_ZERO_CROSS", zero_crossings == 0),
        ("FLATLINE_NO_ENTRY_BAND_CROSS", entry_band_crossings == 0),
        (
            "FLATLINE_LOW_MAX_ABS_Z",
            max_abs_z < entry_band.abs().max(0.1) * 0.75,
        ),
    ];
    let warn_hits = warn_checks.iter().filter(|(_, pass)| *pass).count();
    let flatline_hits = flatline_checks.iter().filter(|(_, pass)| *pass).count();

    let mut rationale_codes = vec![];
    if flatline_hits >= 3 {
        rationale_codes.extend(
            flatline_checks
                .iter()
                .filter_map(|(code, pass)| (*pass).then_some((*code).to_string())),
        );
    } else if warn_hits >= 2 {
        rationale_codes.extend(
            warn_checks
                .iter()
                .filter_map(|(code, pass)| (*pass).then_some((*code).to_string())),
        );
    }
    let status = if flatline_hits >= 3 {
        "FLATLINE"
    } else if warn_hits >= 2 {
        "WARN"
    } else {
        "HEALTHY"
    };

    SignalFlatlineDiagnostics {
        status: status.to_string(),
        window_bars,
        z_stddev,
        z_p95_minus_p5,
        zero_crossings,
        entry_band_crossings,
        max_abs_z,
        rationale_codes,
    }
}

pub fn compute_backtest_series(
    timestamps: &[DateTime<Utc>],
    left_closes: &[f64],
    right_closes: &[f64],
    config: BacktestConfig,
) -> BacktestSeries {
    if timestamps.len() < 2
        || timestamps.len() != left_closes.len()
        || timestamps.len() != right_closes.len()
    {
        return BacktestSeries {
            points: vec![],
            markers: vec![],
        };
    }

    let spread = left_closes
        .iter()
        .zip(right_closes.iter())
        .map(|(left, right)| left.max(1e-9).ln() - config.hedge_ratio * right.max(1e-9).ln())
        .collect::<Vec<_>>();
    let z_window = 30;
    let z_scores = rolling_z_scores_prior(&spread, z_window);

    let mut points = Vec::with_capacity(timestamps.len().saturating_sub(1));
    let mut markers = vec![];
    let mut position: i8 = 0;
    let mut equity = 1.0;
    let round_trip_cost = (config.round_trip_cost_bps.max(0.0) / 20_000.0).clamp(0.0, 1.0);
    let left_tick = config
        .left_constraints
        .filter(|constraints| constraints.tick_size.is_finite() && constraints.tick_size > 0.0)
        .map(|constraints| constraints.tick_size);
    let right_tick = config
        .right_constraints
        .filter(|constraints| constraints.tick_size.is_finite() && constraints.tick_size > 0.0)
        .map(|constraints| constraints.tick_size);
    let stop_abs = config.stop_band.abs();
    let entry_abs = config.entry_band.abs().max(0.0);
    let stop_to_entry_span = (stop_abs - entry_abs).max(0.0);
    let rearm_level = stop_abs - stop_to_entry_span * STOP_RETRACE_FRACTION;
    let mut short_entry_cooldown_active = false;
    let mut long_entry_cooldown_active = false;

    for idx in 1..timestamps.len() {
        let z = z_scores[idx];
        let left_prev = if let Some(tick) = left_tick {
            quantize_price_to_tick(left_closes[idx - 1], tick).unwrap_or(left_closes[idx - 1])
        } else {
            left_closes[idx - 1]
        };
        let left_now = if let Some(tick) = left_tick {
            quantize_price_to_tick(left_closes[idx], tick).unwrap_or(left_closes[idx])
        } else {
            left_closes[idx]
        };
        let right_prev = if let Some(tick) = right_tick {
            quantize_price_to_tick(right_closes[idx - 1], tick).unwrap_or(right_closes[idx - 1])
        } else {
            right_closes[idx - 1]
        };
        let right_now = if let Some(tick) = right_tick {
            quantize_price_to_tick(right_closes[idx], tick).unwrap_or(right_closes[idx])
        } else {
            right_closes[idx]
        };
        let left_return = if left_prev > 0.0 {
            (left_now / left_prev) - 1.0
        } else {
            0.0
        };
        let right_return = if right_prev > 0.0 {
            (right_now / right_prev) - 1.0
        } else {
            0.0
        };
        let spread_return = left_return - config.hedge_ratio * right_return;
        let position_at_bar_start = position;
        if stop_abs > 0.0 {
            if z >= stop_abs {
                short_entry_cooldown_active = true;
            }
            if z <= -stop_abs {
                long_entry_cooldown_active = true;
            }
            if short_entry_cooldown_active && z <= rearm_level {
                short_entry_cooldown_active = false;
            }
            if long_entry_cooldown_active && z >= -rearm_level {
                long_entry_cooldown_active = false;
            }
        }

        if position_at_bar_start == 0 {
            let at_or_beyond_stop = z.abs() >= config.stop_band.abs();
            if at_or_beyond_stop {
                // Fail closed: never open new entries at/through the stop level.
            } else if z <= -config.entry_band {
                if !long_entry_cooldown_active {
                    position = 1;
                    equity *= 1.0 - round_trip_cost;
                    markers.push(BacktestMarker {
                        index: points.len(),
                        kind: "entry".to_string(),
                    });
                }
            } else if z >= config.entry_band && !short_entry_cooldown_active {
                position = -1;
                equity *= 1.0 - round_trip_cost;
                markers.push(BacktestMarker {
                    index: points.len(),
                    kind: "entry".to_string(),
                });
            }
        } else {
            // Only evaluate close conditions for positions that were open
            // at the start of this bar. This prevents same-bar entry+stop overlays.
            let signed_return = if position == 1 {
                spread_return
            } else {
                -spread_return
            };
            equity *= 1.0 + signed_return;

            if z.abs() >= config.stop_band {
                position = 0;
                equity *= 1.0 - round_trip_cost;
                markers.push(BacktestMarker {
                    index: points.len(),
                    kind: "stop".to_string(),
                });
            } else {
                let should_exit = match config.exit_mode {
                    BacktestExitMode::MeanRevert => z.abs() <= config.exit_band,
                    BacktestExitMode::OppositeExtreme => {
                        (position == 1 && z >= config.entry_band)
                            || (position == -1 && z <= -config.entry_band)
                    }
                };
                if should_exit {
                    position = 0;
                    equity *= 1.0 - round_trip_cost;
                    markers.push(BacktestMarker {
                        index: points.len(),
                        kind: "exit".to_string(),
                    });
                }
            }
        }

        points.push(BacktestPoint {
            ts: timestamps[idx],
            z,
            equity,
        });
    }

    BacktestSeries { points, markers }
}

fn to_direction_hint(score: f64, entry_band: f64) -> DirectionHint {
    if score >= entry_band {
        DirectionHint::ShortSpread
    } else if score <= -entry_band {
        DirectionHint::LongSpread
    } else {
        DirectionHint::None
    }
}

fn to_direction_hint_with_stop(score: f64, entry_band: f64, stop_band: f64) -> DirectionHint {
    if !score.is_finite() {
        return DirectionHint::None;
    }
    if stop_band.is_finite() && stop_band > 0.0 && score.abs() >= stop_band.abs() {
        return DirectionHint::None;
    }
    to_direction_hint(score, entry_band)
}

fn to_direction_hint_with_stop_retrace(
    scores: &[f64],
    entry_band: f64,
    stop_band: f64,
    retrace_fraction: f64,
) -> (DirectionHint, &'static str) {
    let Some(score) = scores.last().copied() else {
        return (DirectionHint::None, "AT_OR_BEYOND_STOP_BAND");
    };
    if !score.is_finite() {
        return (DirectionHint::None, "AT_OR_BEYOND_STOP_BAND");
    }

    let unbounded = to_direction_hint(score, entry_band);
    if unbounded == DirectionHint::None {
        return (DirectionHint::None, "AT_OR_BEYOND_STOP_BAND");
    }
    let candidate = to_direction_hint_with_stop(score, entry_band, stop_band);
    if candidate == DirectionHint::None {
        return (DirectionHint::None, "AT_OR_BEYOND_STOP_BAND");
    }

    let stop = stop_band.abs();
    if !stop.is_finite() || stop <= 0.0 {
        return (candidate, "AT_OR_BEYOND_STOP_BAND");
    }

    let entry = entry_band.abs().max(0.0);
    let retrace = retrace_fraction.clamp(0.0, 1.0);
    let stop_to_entry_span = (stop - entry).max(0.0);
    let rearm_level = stop - stop_to_entry_span * retrace;

    let mut short_cooldown_active = false;
    let mut long_cooldown_active = false;
    for sample in scores {
        if !sample.is_finite() {
            continue;
        }
        if *sample >= stop {
            short_cooldown_active = true;
        }
        if *sample <= -stop {
            long_cooldown_active = true;
        }
        if short_cooldown_active && *sample <= rearm_level {
            short_cooldown_active = false;
        }
        if long_cooldown_active && *sample >= -rearm_level {
            long_cooldown_active = false;
        }
    }

    if candidate == DirectionHint::ShortSpread && short_cooldown_active {
        return (DirectionHint::None, "RETRACE_COOLDOWN_ACTIVE");
    }
    if candidate == DirectionHint::LongSpread && long_cooldown_active {
        return (DirectionHint::None, "RETRACE_COOLDOWN_ACTIVE");
    }

    (candidate, "AT_OR_BEYOND_STOP_BAND")
}

fn confidence_band(
    reliability: f64,
    sample_count: usize,
    min_samples_target: usize,
) -> &'static str {
    if reliability >= 0.70 && sample_count >= min_samples_target {
        "HIGH"
    } else if reliability >= 0.40 {
        "MEDIUM"
    } else {
        "LOW"
    }
}

fn reliability(sample_count: usize, win_rate: f64, min_samples_target: usize) -> f64 {
    if sample_count == 0 {
        return 0.0;
    }
    let sample_factor = (sample_count as f64 / min_samples_target.max(1) as f64).min(1.0);
    sample_factor * win_rate.clamp(0.0, 1.0).sqrt()
}

fn regime_fit_multiplier(regime: Regime, variant: SignalVariant) -> f64 {
    match (regime, variant) {
        (Regime::Calm, SignalVariant::CointegrationZ) => 1.0,
        (Regime::Calm, SignalVariant::RobustZ) => 0.9,
        (Regime::Calm, SignalVariant::VolNormalized) => 0.8,
        (Regime::Calm, SignalVariant::FundingAdjusted) => 0.85,
        (Regime::Trending, SignalVariant::CointegrationZ) => 0.7,
        (Regime::Trending, SignalVariant::RobustZ) => 1.0,
        (Regime::Trending, SignalVariant::VolNormalized) => 0.95,
        (Regime::Trending, SignalVariant::FundingAdjusted) => 0.8,
        (Regime::Shock, SignalVariant::CointegrationZ) => 0.6,
        (Regime::Shock, SignalVariant::RobustZ) => 0.95,
        (Regime::Shock, SignalVariant::VolNormalized) => 1.0,
        (Regime::Shock, SignalVariant::FundingAdjusted) => 0.9,
    }
}

fn classify_regime(spread: &[f64], latest_z: f64) -> Regime {
    if spread.len() < 3 {
        return Regime::Calm;
    }
    let diffs = spread
        .windows(2)
        .map(|window| window[1] - window[0])
        .collect::<Vec<_>>();
    let vol = stddev(&diffs).max(1e-9);
    let drift = mean(&diffs).abs();
    let trend_strength = drift / vol;

    if latest_z.abs() >= 2.8 {
        Regime::Shock
    } else if trend_strength >= 0.45 {
        Regime::Trending
    } else {
        Regime::Calm
    }
}

fn estimate_edge_bps(
    left_prices: &[f64],
    right_prices: &[f64],
    hedge_ratio: f64,
    scores: &[f64],
    entry_band: f64,
    hold_bars: usize,
) -> (usize, f64, f64) {
    if hold_bars == 0
        || left_prices.len() < hold_bars + 1
        || scores.len() != left_prices.len()
        || right_prices.len() != left_prices.len()
    {
        return (0, 0.0, 0.0);
    }

    let mut outcomes = vec![];
    for idx in 0..(left_prices.len() - hold_bars) {
        let score = scores[idx];
        let left_entry = left_prices[idx].abs().max(1e-9);
        let left_exit = left_prices[idx + hold_bars].abs().max(1e-9);
        let right_entry = right_prices[idx].abs().max(1e-9);
        let right_exit = right_prices[idx + hold_bars].abs().max(1e-9);
        let left_return = (left_exit / left_entry) - 1.0;
        let right_return = (right_exit / right_entry) - 1.0;
        let spread_return = left_return - hedge_ratio * right_return;
        let pnl_return = if score >= entry_band {
            -spread_return
        } else if score <= -entry_band {
            spread_return
        } else {
            continue;
        };
        if pnl_return.is_finite() {
            outcomes.push(pnl_return * 10_000.0);
        }
    }

    if outcomes.is_empty() {
        return (0, 0.0, 0.0);
    }

    let wins = outcomes.iter().filter(|value| **value > 0.0).count();
    let win_rate = wins as f64 / outcomes.len() as f64;
    let edge_bps = mean(&outcomes);
    (outcomes.len(), win_rate, edge_bps)
}

fn estimate_half_life(spread: &[f64]) -> f64 {
    if spread.len() < 4 {
        return f64::INFINITY;
    }
    let x = spread[..spread.len() - 1].to_vec();
    let y = spread
        .windows(2)
        .map(|window| window[1] - window[0])
        .collect::<Vec<_>>();
    let var_x = variance(&x);
    if var_x <= 0.0 {
        return f64::INFINITY;
    }
    let beta = covariance(&x, &y) / var_x;
    if beta >= 0.0 {
        return f64::INFINITY;
    }
    let half_life = -std::f64::consts::LN_2 / beta;
    if half_life.is_finite() && half_life > 0.0 {
        half_life
    } else {
        f64::INFINITY
    }
}

fn estimate_hedge_ratio_stability(left_log: &[f64], right_log: &[f64]) -> f64 {
    if left_log.len() < 80 || left_log.len() != right_log.len() {
        return 1.0;
    }
    let split = left_log.len() / 2;
    let beta_a = ols_beta(&left_log[..split], &right_log[..split]).unwrap_or(1.0);
    let beta_b = ols_beta(&left_log[split..], &right_log[split..]).unwrap_or(beta_a);
    (beta_b - beta_a).abs() / beta_a.abs().max(1e-9)
}

fn ols_beta(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 3 {
        return None;
    }
    let var_y = variance(y);
    if var_y <= 0.0 {
        return None;
    }
    Some(covariance(x, y) / var_y)
}

fn rolling_z_scores(values: &[f64], window: usize) -> Vec<f64> {
    if values.is_empty() {
        return vec![];
    }
    let mut result = vec![0.0; values.len()];
    let win = window.max(10).min(values.len());
    for idx in 0..values.len() {
        if idx + 1 < win {
            continue;
        }
        let slice = &values[(idx + 1 - win)..=idx];
        let std = stddev(slice);
        if std > 0.0 {
            result[idx] = (values[idx] - mean(slice)) / std;
        }
    }
    result
}

fn rolling_z_scores_prior(values: &[f64], window: usize) -> Vec<f64> {
    if values.len() < 2 {
        return vec![0.0; values.len()];
    }
    let mut result = vec![0.0; values.len()];
    let win = window.max(10).min(values.len() - 1);
    for idx in 0..values.len() {
        if idx < win {
            continue;
        }
        let slice = &values[(idx - win)..idx];
        let std = stddev(slice);
        if std.is_finite() && std >= MIN_PRIOR_Z_STDDEV {
            result[idx] = (values[idx] - mean(slice)) / std;
        }
    }
    result
}

fn rolling_robust_z_scores(values: &[f64], window: usize) -> Vec<f64> {
    if values.is_empty() {
        return vec![];
    }
    let mut result = vec![0.0; values.len()];
    let win = window.max(10).min(values.len());
    for idx in 0..values.len() {
        if idx + 1 < win {
            continue;
        }
        let slice = &values[(idx + 1 - win)..=idx];
        let med = median(slice);
        let mut abs_dev = slice
            .iter()
            .map(|value| (value - med).abs())
            .collect::<Vec<_>>();
        abs_dev.sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
        let mad = median(&abs_dev).max(1e-9);
        result[idx] = 0.6745 * (values[idx] - med) / mad;
    }
    result
}

fn rolling_vol_normalized_scores(values: &[f64], window: usize) -> Vec<f64> {
    let z = rolling_z_scores(values, window);
    if values.len() < 2 {
        return z;
    }
    let abs_diffs = values
        .windows(2)
        .map(|window| (window[1] - window[0]).abs())
        .collect::<Vec<_>>();
    let vol_pressure = rolling_robust_z_scores(&abs_diffs, window.max(10));
    let mut normalized = vec![0.0; values.len()];
    for idx in 0..values.len() {
        let vol_idx = idx
            .saturating_sub(1)
            .min(vol_pressure.len().saturating_sub(1));
        let vol_penalty = 1.0 + vol_pressure[vol_idx].max(0.0);
        normalized[idx] = z[idx] / vol_penalty;
    }
    normalized
}

fn funding_drag_to_z_penalty(funding_drag_bps: f64, spread_vol_bps: f64) -> f64 {
    if !funding_drag_bps.is_finite() || funding_drag_bps <= 0.0 {
        return 0.0;
    }
    let spread_vol = spread_vol_bps.abs().max(1.0);
    (funding_drag_bps / spread_vol).clamp(0.0, 4.0)
}

fn shrink_score_magnitude(score: f64, penalty: f64) -> f64 {
    if !score.is_finite() {
        return 0.0;
    }
    let shrunk = (score.abs() - penalty.max(0.0)).max(0.0);
    score.signum() * shrunk
}

fn shadow_features(
    variant: SignalVariant,
    regime: Regime,
    score_last: f64,
    sample_count: usize,
    win_rate: f64,
    reliability: f64,
) -> [f64; SHADOW_FEATURE_COUNT] {
    [
        1.0,
        (score_last.abs() / 6.0).clamp(0.0, 1.5),
        ((sample_count as f64).ln_1p() / 6.0).clamp(0.0, 1.5),
        win_rate.clamp(0.0, 1.0),
        reliability.clamp(0.0, 1.0),
        if regime == Regime::Trending { 1.0 } else { 0.0 },
        if regime == Regime::Shock { 1.0 } else { 0.0 },
        if variant == SignalVariant::RobustZ {
            1.0
        } else {
            0.0
        },
        if variant == SignalVariant::VolNormalized {
            1.0
        } else {
            0.0
        },
        if variant == SignalVariant::FundingAdjusted {
            1.0
        } else {
            0.0
        },
    ]
}

fn dot(left: &[f64; SHADOW_FEATURE_COUNT], right: &[f64; SHADOW_FEATURE_COUNT]) -> f64 {
    left.iter()
        .zip(right.iter())
        .map(|(l, r)| l * r)
        .sum::<f64>()
}

fn sigmoid(value: f64) -> f64 {
    if value >= 0.0 {
        let exp = (-value).exp();
        1.0 / (1.0 + exp)
    } else {
        let exp = value.exp();
        exp / (1.0 + exp)
    }
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

fn variance(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let avg = mean(values);
    values
        .iter()
        .map(|value| (value - avg).powi(2))
        .sum::<f64>()
        / values.len() as f64
}

fn stddev(values: &[f64]) -> f64 {
    variance(values).sqrt()
}

fn covariance(left: &[f64], right: &[f64]) -> f64 {
    if left.len() != right.len() || left.len() < 2 {
        return 0.0;
    }
    let left_mean = mean(left);
    let right_mean = mean(right);
    left.iter()
        .zip(right.iter())
        .map(|(l, r)| (l - left_mean) * (r - right_mean))
        .sum::<f64>()
        / left.len() as f64
}

fn median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    let mid = sorted.len() / 2;
    if sorted.len().is_multiple_of(2) {
        (sorted[mid - 1] + sorted[mid]) / 2.0
    } else {
        sorted[mid]
    }
}

fn percentile(values: &[f64], percentile: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    let max_index = sorted.len().saturating_sub(1);
    let target = percentile.clamp(0.0, 1.0) * max_index as f64;
    let lower = target.floor() as usize;
    let upper = target.ceil() as usize;
    if lower == upper {
        sorted[lower]
    } else {
        let weight = target - lower as f64;
        sorted[lower] * (1.0 - weight) + sorted[upper] * weight
    }
}

#[cfg(test)]
mod tests {
    use super::{
        annotate_with_shadow_model, build_portfolio_plan, compute_backtest_series,
        compute_flatline_diagnostics, estimate_edge_bps, evaluate_cost_gate, evaluate_pair,
        funding_drag_to_z_penalty, rolling_vol_normalized_scores, rolling_z_scores,
        rolling_z_scores_prior, shrink_score_magnitude, to_direction_hint_with_stop,
        to_direction_hint_with_stop_retrace, train_shadow_model, BacktestConfig, BacktestExitMode,
        CostGateDiagnostics, CostGateInput, DirectionHint, FundingModel, PairCue,
        PairEvaluationInput, PortfolioHint, Regime, SelectedSignalConfig, SetupGateDiagnostics,
        ShadowMlDiagnostics, ShadowModelTrainingRow, SignalVariant, TradeGateDiagnostics,
    };
    use chrono::{Duration, Utc};
    use common_types::Timeframe;

    fn test_selected_signal_config(variant: &str) -> SelectedSignalConfig {
        SelectedSignalConfig {
            variant: variant.to_string(),
            entry_band: 1.8,
            exit_band: 0.6,
            stop_band: 3.2,
            lookback_bars: 520,
            hold_bars: 20,
            max_half_life_bars: 120.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            source: "TEST".to_string(),
            updated_at: Utc::now(),
        }
    }

    #[test]
    fn evaluate_pair_emits_variant_metrics() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left,
            right_closes: right,
            lookback_bars: 520,
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
            selected_signal_config: None,
        })
        .expect("pair evaluation should succeed");

        assert_eq!(result.variants.len(), 4);
        assert!(!result.cue.selected_variant.is_empty());
        assert!(result.cue.entry_band > result.cue.exit_band);
    }

    #[test]
    fn evaluate_pair_uses_selected_signal_config_variant_when_provided() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left,
            right_closes: right,
            lookback_bars: 520,
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
            selected_signal_config: Some(test_selected_signal_config("ROBUST_Z")),
        })
        .expect("pair evaluation should succeed");

        assert_eq!(result.cue.selected_variant, "ROBUST_Z");
        assert_eq!(result.cue.selected_signal_config.variant, "ROBUST_Z");
    }

    #[test]
    fn evaluate_pair_cost_estimate_includes_taker_fee() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left,
            right_closes: right,
            lookback_bars: 520,
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
            selected_signal_config: None,
        })
        .expect("pair evaluation should succeed");

        assert!((result.cue.cost_estimate_bps - 1.8).abs() < 1e-9);
    }

    #[test]
    fn evaluate_pair_adds_half_life_warning_when_half_life_is_too_long() {
        let (timestamps, mut left, right) = synthetic_pair_series(240);
        for (idx, value) in left.iter_mut().enumerate() {
            *value *= 1.0 + (idx as f64 * 0.0012);
        }
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left,
            right_closes: right,
            lookback_bars: 520,
            entry_band: 1.2,
            exit_band: 0.5,
            stop_band: 3.0,
            hold_bars: 8,
            max_half_life_bars: 10.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            funding_drag_bps: 0.5,
            taker_fee_bps: 1.2,
            min_samples_target: 6,
            selected_signal_config: None,
        })
        .expect("pair evaluation should succeed");

        assert!(result
            .cue
            .rationale_codes
            .iter()
            .any(|code| code == "HALF_LIFE_TOO_LONG"));
    }

    #[test]
    fn flatline_diagnostics_marks_constant_series_as_flatline() {
        let scores = vec![0.04; 800];
        let diagnostics = compute_flatline_diagnostics(&scores, Timeframe::OneMinute, 1.8);
        assert_eq!(diagnostics.status, "FLATLINE");
        assert_eq!(diagnostics.window_bars, 720);
        assert_eq!(diagnostics.zero_crossings, 0);
        assert_eq!(diagnostics.entry_band_crossings, 0);
    }

    #[test]
    fn flatline_diagnostics_marks_active_series_as_healthy() {
        let scores = (0..900)
            .map(|idx| ((idx as f64) / 13.0).sin() * 2.2)
            .collect::<Vec<_>>();
        let diagnostics = compute_flatline_diagnostics(&scores, Timeframe::OneMinute, 1.8);
        assert_eq!(diagnostics.status, "HEALTHY");
        assert!(diagnostics.zero_crossings > 2);
    }

    #[test]
    fn shadow_model_can_train_and_annotate_variants() {
        let rows = synthetic_shadow_training_rows(240);
        let model = train_shadow_model(&rows, 64).expect("shadow model should train");
        assert!(model.metrics.precision.is_finite());
        assert!(model.metrics.brier_score.is_finite());
        assert!((0.0..=1.0).contains(&model.metrics.positive_rate));
        assert!(model.metrics.training_rows >= 240);

        let (timestamps, left, right) = synthetic_pair_series(280);
        let mut output = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left,
            right_closes: right,
            lookback_bars: 520,
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 10,
            max_half_life_bars: 120.0,
            train_bars: 64_800,
            validation_bars: 30_240,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
            selected_signal_config: None,
        })
        .expect("pair evaluation should succeed");

        let diagnostics = annotate_with_shadow_model(&mut output, Some(&model));
        assert_eq!(diagnostics.status, "AVAILABLE");
        assert_eq!(diagnostics.model_name, "LOGISTIC_V1");
        assert!(diagnostics.training_rows >= 240);
        assert!(output
            .variants
            .iter()
            .all(|variant| variant.shadow_success_probability.is_some()));
    }

    #[test]
    fn shadow_model_marks_unavailable_when_training_is_insufficient() {
        let rows = synthetic_shadow_training_rows(20);
        let model = train_shadow_model(&rows, 64);
        assert!(model.is_none());
    }

    #[test]
    fn cost_gate_blocks_when_costs_exceed_edge() {
        let diagnostics = evaluate_cost_gate(CostGateInput {
            expected_edge_bps: 2.4,
            fee_bps: 1.0,
            funding_model: FundingModel::Dynamic,
            funding_events: 1,
            funding_bps_per_event: 0.8,
            funding_bps: 0.8,
            spread_vol_bps: 2.0,
            spread_z: 1.9,
            sampled_slippage_bps: None,
            slippage_base_bps: 0.6,
            slippage_vol_multiplier: 0.5,
            slippage_z_multiplier: 0.2,
            min_net_edge_bps: 0.0,
        });
        assert_eq!(diagnostics.status, "AVAILABLE");
        assert!(!diagnostics.pass);
        assert!(diagnostics
            .rationale_codes
            .iter()
            .any(|code| code == "COST_GATE_BLOCKED"));
    }

    #[test]
    fn cost_gate_prefers_sampled_slippage_when_present() {
        let diagnostics = evaluate_cost_gate(CostGateInput {
            expected_edge_bps: 3.5,
            fee_bps: 1.0,
            funding_model: FundingModel::Dynamic,
            funding_events: 1,
            funding_bps_per_event: 0.5,
            funding_bps: 0.5,
            spread_vol_bps: 9.0,
            spread_z: 2.1,
            sampled_slippage_bps: Some(0.6),
            slippage_base_bps: 1.2,
            slippage_vol_multiplier: 0.8,
            slippage_z_multiplier: 0.5,
            min_net_edge_bps: 0.0,
        });
        assert!(diagnostics.pass);
        assert!((diagnostics.slippage_bps - 0.6).abs() < 1e-9);
    }

    #[test]
    fn cost_gate_pass_is_not_reduced_by_funding_component() {
        let diagnostics = evaluate_cost_gate(CostGateInput {
            expected_edge_bps: 3.5,
            fee_bps: 1.0,
            funding_model: FundingModel::Dynamic,
            funding_events: 3,
            funding_bps_per_event: 2.0,
            funding_bps: 6.0,
            spread_vol_bps: 0.0,
            spread_z: 0.0,
            sampled_slippage_bps: Some(0.6),
            slippage_base_bps: 0.0,
            slippage_vol_multiplier: 0.0,
            slippage_z_multiplier: 0.0,
            min_net_edge_bps: 0.0,
        });
        assert!(diagnostics.pass);
        assert!((diagnostics.net_edge_bps - 1.9).abs() < 1e-9);
    }

    #[test]
    fn funding_penalty_converts_bps_to_dimensionless_shrink() {
        let low_vol_penalty = funding_drag_to_z_penalty(2.0, 10.0);
        let high_vol_penalty = funding_drag_to_z_penalty(2.0, 200.0);
        assert!(low_vol_penalty > high_vol_penalty);
        let long_score = shrink_score_magnitude(-2.0, low_vol_penalty);
        let short_score = shrink_score_magnitude(2.0, low_vol_penalty);
        assert!(long_score.abs() < 2.0);
        assert!(short_score.abs() < 2.0);
        assert!(long_score < 0.0);
        assert!(short_score > 0.0);
    }

    #[test]
    fn estimate_edge_bps_uses_leg_return_domain() {
        let left = vec![100.0, 101.0, 102.0];
        let right = vec![100.0, 100.0, 100.0];
        let scores = vec![-2.0, 2.0, 0.0];
        let (samples, win_rate, edge_bps) = estimate_edge_bps(&left, &right, 1.0, &scores, 1.0, 1);
        assert_eq!(samples, 2);
        assert!((win_rate - 0.5).abs() < 1e-9);
        // Long from 100->101 is +100bp, short from 101->102 is -99.0099bp.
        assert!((edge_bps - 0.4950495).abs() < 1e-3);
    }

    #[test]
    fn vol_normalized_uses_robust_vol_pressure() {
        let values = vec![
            0.0, 0.1, 0.0, 0.08, 0.0, 0.09, 0.0, 0.07, 0.0, 0.08, 0.0, 0.09, 3.0, -2.8, 2.6, -2.4,
        ];
        let raw = rolling_z_scores(&values, 10);
        let normalized = rolling_vol_normalized_scores(&values, 10);
        let idx = values.len() - 1;
        assert!(normalized[idx].abs() <= raw[idx].abs() + 1e-9);
    }

    #[test]
    fn portfolio_plan_respects_caps_and_neutrality() {
        let cues = vec![
            synthetic_cue("PI_XBTUSD__PI_ETHUSD", "LONG_SPREAD", 8.0, 3.0),
            synthetic_cue("PI_SOLUSD__PI_ETHUSD", "SHORT_SPREAD", 7.5, 2.9),
            synthetic_cue("PI_AVAXUSD__PI_ETHUSD", "LONG_SPREAD", 4.2, 2.1),
        ];
        let plan = build_portfolio_plan(&cues, 1.0, 0.4);
        assert_eq!(plan.status, "AVAILABLE");
        assert!(!plan.weights.is_empty());
        let gross = plan
            .weights
            .iter()
            .map(|entry| entry.target_weight.abs())
            .sum::<f64>();
        assert!(gross <= 1.0 + 1e-6);
        assert!(plan
            .weights
            .iter()
            .all(|entry| entry.target_weight.abs() <= 0.4 + 1e-6));
        let net = plan
            .weights
            .iter()
            .map(|entry| entry.target_weight)
            .sum::<f64>();
        assert!(
            net.abs() <= 1e-4
                || plan
                    .rationale_codes
                    .iter()
                    .any(|code| code == "NEUTRALITY_APPROXIMATED")
        );
    }

    #[test]
    fn backtest_series_emits_points_and_markers() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let series = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.15,
                entry_band: 1.6,
                exit_band: 0.6,
                stop_band: 3.2,
                round_trip_cost_bps: 2.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );
        assert!(series.points.len() > 200);
        assert!(series.markers.iter().all(|marker| marker.kind == "entry"
            || marker.kind == "exit"
            || marker.kind == "stop"));
    }

    #[test]
    fn rolling_prior_z_uses_only_past_window() {
        let values = vec![1.0, 2.0, 3.0, 100.0];
        let z = rolling_z_scores_prior(&values, 3);
        assert!((z[0] - 0.0).abs() < 1e-12);
        assert!((z[1] - 0.0).abs() < 1e-12);
        assert!((z[2] - 0.0).abs() < 1e-12);
        // idx=3 uses only [1,2,3] as normalization window.
        assert!((z[3] - 120.02499739637572).abs() < 1e-9);
    }

    #[test]
    fn rolling_prior_z_suppresses_nearly_flat_window_variance() {
        let mut values = vec![7.428334145058403; 31];
        values[29] += 1e-12;
        values[30] = 7.428096919781667;

        let z = rolling_z_scores_prior(&values, 30);

        assert!((z[30] - 0.0).abs() < 1e-12);
    }

    #[test]
    fn backtest_series_is_invariant_to_future_tail_spike_before_final_bar() {
        let base_spread = (0..120)
            .map(|idx| (idx as f64 / 8.0).sin() * 0.9 + (idx as f64 / 19.0).cos() * 0.35)
            .collect::<Vec<_>>();
        let mut shocked_spread = base_spread.clone();
        let final_idx = shocked_spread.len() - 1;
        shocked_spread[final_idx] += 12.0;

        let (timestamps_a, left_a, right_a) = synthetic_spread_path(&base_spread);
        let (timestamps_b, left_b, right_b) = synthetic_spread_path(&shocked_spread);
        let config = BacktestConfig {
            hedge_ratio: 1.0,
            entry_band: 1.0,
            exit_band: 0.25,
            stop_band: 3.2,
            round_trip_cost_bps: 0.0,
            exit_mode: BacktestExitMode::MeanRevert,
            left_constraints: None,
            right_constraints: None,
        };
        let series_a = compute_backtest_series(&timestamps_a, &left_a, &right_a, config);
        let series_b = compute_backtest_series(&timestamps_b, &left_b, &right_b, config);

        assert_eq!(series_a.points.len(), series_b.points.len());
        for idx in 0..series_a.points.len().saturating_sub(1) {
            let z_diff = (series_a.points[idx].z - series_b.points[idx].z).abs();
            let eq_diff = (series_a.points[idx].equity - series_b.points[idx].equity).abs();
            assert!(
                z_diff < 1e-12,
                "z changed at idx {} due to future-only spike: {}",
                idx,
                z_diff
            );
            assert!(
                eq_diff < 1e-12,
                "equity changed at idx {} due to future-only spike: {}",
                idx,
                eq_diff
            );
        }
    }

    #[test]
    fn backtest_series_returns_empty_when_lengths_mismatch() {
        let (timestamps, left, right) = synthetic_pair_series(40);
        let series = compute_backtest_series(
            &timestamps,
            &left[1..],
            &right,
            BacktestConfig {
                hedge_ratio: 1.0,
                entry_band: 1.8,
                exit_band: 0.6,
                stop_band: 3.2,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );
        assert!(series.points.is_empty());
        assert!(series.markers.is_empty());
    }

    #[test]
    fn backtest_markers_do_not_overlap_at_same_index() {
        let (timestamps, mut left, right) = synthetic_pair_series(260);
        // Force an extreme z-move that can otherwise produce same-bar entry+stop
        // if close logic is evaluated immediately after opening a position.
        left[180] *= 1.45;

        let series = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.15,
                entry_band: 1.0,
                exit_band: 0.2,
                stop_band: 1.2,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );

        let mut seen = std::collections::HashSet::new();
        for marker in &series.markers {
            assert!(
                seen.insert(marker.index),
                "multiple markers at same index {}",
                marker.index
            );
        }
    }

    #[test]
    fn backtest_entries_are_not_opened_at_or_beyond_stop_band() {
        let (timestamps, mut left, right) = synthetic_pair_series(260);
        left[180] *= 1.45;
        let stop_band = 1.2;
        let series = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.15,
                entry_band: 1.0,
                exit_band: 0.2,
                stop_band,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );

        let mut entry_count = 0usize;
        for marker in &series.markers {
            if marker.kind == "entry" {
                entry_count += 1;
                let z = series
                    .points
                    .get(marker.index)
                    .expect("entry marker index should map to chart point")
                    .z
                    .abs();
                assert!(
                    z < stop_band,
                    "entry marker at index {} should be below stop band; got |z|={}",
                    marker.index,
                    z
                );
            }
        }
        assert!(
            entry_count > 0,
            "expected at least one entry marker in synthetic series"
        );
    }

    #[test]
    fn backtest_exit_mode_opposite_extreme_holds_longer_than_mean_revert() {
        let mut spread = vec![0.0; 40];
        spread.extend([
            0.2, 0.4, 0.6, 1.0, 1.5, 2.1, 1.7, 1.0, 0.3, 0.1, -0.1, -0.4, -0.9, -1.4, -1.9, -2.2,
            -1.6, -1.0, -0.3, 0.2, 0.8, 1.4, 1.9,
        ]);
        let (timestamps, left, right) = synthetic_spread_path(&spread);

        let mean_revert = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.0,
                entry_band: 1.0,
                exit_band: 0.25,
                stop_band: 4.0,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );
        let opposite_extreme = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.0,
                entry_band: 1.0,
                exit_band: 0.25,
                stop_band: 4.0,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::OppositeExtreme,
                left_constraints: None,
                right_constraints: None,
            },
        );

        let mean_entry = mean_revert
            .markers
            .iter()
            .find(|marker| marker.kind == "entry")
            .expect("mean-revert entry")
            .index;
        let mean_exit = mean_revert
            .markers
            .iter()
            .find(|marker| marker.kind == "exit")
            .expect("mean-revert exit")
            .index;
        let opposite_entry = opposite_extreme
            .markers
            .iter()
            .find(|marker| marker.kind == "entry")
            .expect("opposite entry")
            .index;
        let opposite_exit = opposite_extreme
            .markers
            .iter()
            .find(|marker| marker.kind == "exit")
            .expect("opposite exit")
            .index;

        assert!(mean_exit > mean_entry);
        assert!(opposite_exit > opposite_entry);
        assert!(
            opposite_exit > mean_exit,
            "opposite-extreme exit should occur later than mean-revert exit"
        );
    }

    #[test]
    fn direction_hint_with_stop_suppresses_entries_at_or_beyond_stop() {
        assert_eq!(
            to_direction_hint_with_stop(2.0, 1.8, 3.2),
            DirectionHint::ShortSpread
        );
        assert_eq!(
            to_direction_hint_with_stop(-2.0, 1.8, 3.2),
            DirectionHint::LongSpread
        );
        assert_eq!(
            to_direction_hint_with_stop(3.2, 1.8, 3.2),
            DirectionHint::None
        );
        assert_eq!(
            to_direction_hint_with_stop(-3.2, 1.8, 3.2),
            DirectionHint::None
        );
        assert_eq!(
            to_direction_hint_with_stop(4.0, 1.8, 3.2),
            DirectionHint::None
        );
    }

    #[test]
    fn direction_hint_requires_positive_side_retrace_after_stop_breach() {
        let blocked_scores = vec![0.2, 1.9, 3.25, 3.05, 2.95];
        let (hint, reason) = to_direction_hint_with_stop_retrace(&blocked_scores, 1.8, 3.2, 0.25);
        assert_eq!(hint, DirectionHint::None);
        assert_eq!(reason, "RETRACE_COOLDOWN_ACTIVE");

        let rearmed_scores = vec![0.2, 1.9, 3.25, 3.05, 2.84];
        let (hint, reason) = to_direction_hint_with_stop_retrace(&rearmed_scores, 1.8, 3.2, 0.25);
        assert_eq!(hint, DirectionHint::ShortSpread);
        assert_eq!(reason, "AT_OR_BEYOND_STOP_BAND");
    }

    #[test]
    fn direction_hint_requires_negative_side_retrace_after_stop_breach() {
        let blocked_scores = vec![-0.3, -2.1, -3.22, -3.0, -2.9];
        let (hint, reason) = to_direction_hint_with_stop_retrace(&blocked_scores, 1.8, 3.2, 0.25);
        assert_eq!(hint, DirectionHint::None);
        assert_eq!(reason, "RETRACE_COOLDOWN_ACTIVE");

        let rearmed_scores = vec![-0.3, -2.1, -3.22, -3.0, -2.8];
        let (hint, reason) = to_direction_hint_with_stop_retrace(&rearmed_scores, 1.8, 3.2, 0.25);
        assert_eq!(hint, DirectionHint::LongSpread);
        assert_eq!(reason, "AT_OR_BEYOND_STOP_BAND");
    }

    #[test]
    fn backtest_retrace_cooldown_blocks_reentry_until_rearm_level() {
        let mut spread = vec![0.0; 40];
        spread.extend([
            -0.5, 0.3, 1.4, 2.1, 2.4, 2.0, 1.7, 1.3, 0.9, 0.2, -0.4, -1.0, -1.2, -1.0, -0.6, -0.1,
        ]);
        let (timestamps, left, right) = synthetic_spread_path(&spread);
        let entry_band = 1.0;
        let stop_band = 1.2;
        let rearm_level = stop_band - (stop_band - entry_band) * 0.25;

        let series = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: 1.0,
                entry_band,
                exit_band: 0.3,
                stop_band,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
        );

        let stop_marker = series
            .markers
            .iter()
            .find(|marker| marker.kind == "stop")
            .expect("expected at least one stop marker");
        let stop_z = series.points[stop_marker.index].z;
        assert!(stop_z.abs() >= stop_band);

        let rearm_idx = series
            .points
            .iter()
            .enumerate()
            .skip(stop_marker.index + 1)
            .find_map(|(idx, point)| {
                if stop_z > 0.0 {
                    (point.z <= rearm_level).then_some(idx)
                } else {
                    (point.z >= -rearm_level).then_some(idx)
                }
            })
            .expect("expected retrace through rearm threshold");

        let entry_before_rearm = series.markers.iter().any(|marker| {
            marker.kind == "entry" && marker.index > stop_marker.index && marker.index < rearm_idx
        });
        assert!(
            !entry_before_rearm,
            "entry marker occurred before retrace cooldown rearm"
        );
    }

    fn synthetic_pair_series(n: usize) -> (Vec<chrono::DateTime<Utc>>, Vec<f64>, Vec<f64>) {
        let start = Utc::now() - Duration::minutes(n as i64);
        let mut timestamps = Vec::with_capacity(n);
        let mut right = Vec::with_capacity(n);
        let mut left = Vec::with_capacity(n);

        let mut spread = 0.0;
        for idx in 0..n {
            let ts = start + Duration::minutes(idx as i64);
            timestamps.push(ts);

            let base = 100.0 + idx as f64 * 0.04 + (idx as f64 / 12.0).sin() * 1.2;
            right.push(base.max(1.0));

            spread = 0.92 * spread + (idx as f64 / 9.0).sin() * 0.03;
            let left_log = right[idx].ln() * 1.15 + spread;
            left.push(left_log.exp());
        }

        (timestamps, left, right)
    }

    fn synthetic_spread_path(spread: &[f64]) -> (Vec<chrono::DateTime<Utc>>, Vec<f64>, Vec<f64>) {
        let start = Utc::now() - Duration::minutes(spread.len() as i64);
        let mut timestamps = Vec::with_capacity(spread.len());
        let mut left = Vec::with_capacity(spread.len());
        let mut right = Vec::with_capacity(spread.len());
        for (idx, value) in spread.iter().enumerate() {
            timestamps.push(start + Duration::minutes(idx as i64));
            right.push(100.0);
            left.push(100.0 * value.exp());
        }
        (timestamps, left, right)
    }

    fn synthetic_shadow_training_rows(n: usize) -> Vec<ShadowModelTrainingRow> {
        let mut rows = Vec::with_capacity(n);
        for idx in 0..n {
            let variant = match idx % 4 {
                0 => SignalVariant::CointegrationZ,
                1 => SignalVariant::RobustZ,
                2 => SignalVariant::VolNormalized,
                _ => SignalVariant::FundingAdjusted,
            };
            let regime = match idx % 3 {
                0 => Regime::Calm,
                1 => Regime::Trending,
                _ => Regime::Shock,
            };
            let score_last = match variant {
                SignalVariant::RobustZ => 2.0 + (idx as f64 / 31.0).sin() * 0.4,
                SignalVariant::VolNormalized => 1.4 + (idx as f64 / 19.0).sin() * 0.5,
                SignalVariant::FundingAdjusted => 1.2 + (idx as f64 / 27.0).sin() * 0.5,
                SignalVariant::CointegrationZ => 1.1 + (idx as f64 / 25.0).sin() * 0.5,
            };
            let sample_count = 10 + (idx % 22);
            let win_rate = match (variant, regime) {
                (SignalVariant::RobustZ, Regime::Trending) => 0.67,
                (SignalVariant::VolNormalized, Regime::Shock) => 0.64,
                (SignalVariant::CointegrationZ, Regime::Calm) => 0.62,
                _ => 0.44,
            };
            let reliability = (win_rate * ((sample_count as f64) / 25.0)).clamp(0.0, 1.0);
            let edge_bps = if win_rate >= 0.55 {
                4.0 + score_last * 1.2
            } else {
                -3.0 - score_last
            };
            rows.push(ShadowModelTrainingRow {
                variant,
                regime,
                score_last,
                sample_count,
                win_rate,
                reliability,
                edge_bps,
            });
        }
        rows
    }

    fn synthetic_cue(
        pair_id: &str,
        direction: &str,
        opportunity_score: f64,
        net_edge_bps: f64,
    ) -> PairCue {
        PairCue {
            pair_id: pair_id.to_string(),
            left_instrument: "LEFT".to_string(),
            right_instrument: "RIGHT".to_string(),
            timeframe: "1m".to_string(),
            regime: "CALM".to_string(),
            selected_variant: "ROBUST_Z".to_string(),
            direction_hint: direction.to_string(),
            spread_z: 1.9,
            opportunity_score,
            confidence_band: "MEDIUM".to_string(),
            entry_band: 1.8,
            exit_band: 0.6,
            stop_band: 3.2,
            expected_hold_bars: 12,
            cost_estimate_bps: 0.6,
            setup_actionable: true,
            actionable: true,
            rationale_codes: vec![],
            setup_gate: SetupGateDiagnostics {
                status: "AVAILABLE".to_string(),
                pass: true,
                rationale_codes: vec![],
            },
            cost_gate: CostGateDiagnostics {
                status: "AVAILABLE".to_string(),
                expected_edge_bps: opportunity_score,
                fee_bps: 0.8,
                funding_model: FundingModel::Dynamic.as_str().to_string(),
                funding_events: 1,
                funding_bps_per_event: 0.6,
                funding_bps: 0.6,
                slippage_bps: 0.5,
                net_edge_bps,
                pass: true,
                rationale_codes: vec![],
            },
            trade_gate: TradeGateDiagnostics {
                status: "AVAILABLE".to_string(),
                pass: true,
                blocked_by: "NONE".to_string(),
                rationale_codes: vec![],
            },
            portfolio_hint: PortfolioHint::unavailable(vec!["NOT_EVALUATED".to_string()]),
            shadow_ml: ShadowMlDiagnostics::unavailable(vec!["NOT_EVALUATED".to_string()]),
            selection_state: None,
            selected_signal_config: test_selected_signal_config("ROBUST_Z"),
            evaluated_at: Utc::now(),
        }
    }
}
