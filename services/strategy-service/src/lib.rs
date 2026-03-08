use chrono::{DateTime, Utc};
use common_types::{
    kraken_perp_constraints, quantize_price_to_tick, quantize_to_step,
    InstrumentTradingConstraints, Timeframe,
};
use serde::Serialize;

const EXECUTABLE_SPREAD_NOTIONAL_DRIFT_TOLERANCE_PCT: f64 = 12.0;
const EXECUTABLE_SPREAD_HEDGE_DRIFT_TOLERANCE_PCT: f64 = 25.0;
const EXECUTABLE_SPREAD_SEARCH_STEPS: usize = 240;

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
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub hold_bars: usize,
    pub max_half_life_bars: f64,
    pub funding_drag_bps: f64,
    pub taker_fee_bps: f64,
    pub min_samples_target: usize,
}

#[derive(Debug, Clone)]
pub struct PairEvaluationOutput {
    pub cue: PairCue,
    pub variants: Vec<VariantEvaluation>,
    pub half_life_bars: f64,
    pub hedge_ratio: f64,
    pub hedge_ratio_stability: f64,
    pub spread_vol_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct BacktestPoint {
    pub ts: DateTime<Utc>,
    pub z: f64,
    pub signal_z: f64,
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
    pub selected_variant: SignalVariant,
    pub z_window: usize,
    pub funding_drag_bps: f64,
    pub entry_band: f64,
    pub exit_band: f64,
    pub stop_band: f64,
    pub round_trip_cost_bps: f64,
    pub exit_mode: BacktestExitMode,
    pub left_constraints: Option<InstrumentTradingConstraints>,
    pub right_constraints: Option<InstrumentTradingConstraints>,
}

#[derive(Debug, Clone, Copy)]
struct ExecutableSpreadUnit {
    left_qty: f64,
    right_qty: f64,
    achieved_notional_usd: f64,
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
    let left_constraints = kraken_perp_constraints(&input.left_instrument);
    let right_constraints = kraken_perp_constraints(&input.right_instrument);
    let left_prices = quantize_close_series_to_ticks(
        &input.left_closes,
        left_constraints.map(|value| value.tick_size),
    );
    let right_prices = quantize_close_series_to_ticks(
        &input.right_closes,
        right_constraints.map(|value| value.tick_size),
    );
    let executable_unit = derive_executable_spread_unit(
        *left_prices
            .last()
            .ok_or_else(|| anyhow::anyhow!("missing left close for {}", input.pair_id))?,
        *right_prices
            .last()
            .ok_or_else(|| anyhow::anyhow!("missing right close for {}", input.pair_id))?,
        hedge_ratio,
        left_constraints,
        right_constraints,
    )
    .ok_or_else(|| {
        anyhow::anyhow!(
            "unable to derive executable spread unit for pair={} left={} right={}",
            input.pair_id,
            input.left_instrument,
            input.right_instrument
        )
    })?;
    let spread = build_executable_spread_series(
        &left_prices,
        &right_prices,
        executable_unit.left_qty,
        executable_unit.right_qty,
    );
    let spread_diffs = spread
        .windows(2)
        .map(|window| window[1] - window[0])
        .collect::<Vec<_>>();
    let spread_vol_bps = if executable_unit.achieved_notional_usd > 0.0 {
        (stddev(&spread_diffs) / executable_unit.achieved_notional_usd) * 10_000.0
    } else {
        0.0
    };

    let half_life_bars = estimate_half_life(&spread);
    let hedge_ratio_stability = estimate_hedge_ratio_stability(&left_log, &right_log);

    let lookback = input.left_closes.len().min(180);
    let signal_window = lookback.max(30);
    let signal_series = build_variant_score_series(&spread, signal_window, input.funding_drag_bps);
    let z_scores = signal_series.cointegration_z.as_slice();
    let robust_z_scores = signal_series.robust_z.as_slice();
    let vol_norm_scores = signal_series.vol_normalized.as_slice();
    let funding_scores = signal_series.funding_adjusted.as_slice();

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
            &spread,
            series,
            input.entry_band,
            input.hold_bars,
            executable_unit.achieved_notional_usd,
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

    let mut selected = variants
        .iter()
        .max_by(|left, right| {
            left.opportunity_score
                .partial_cmp(&right.opportunity_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("no signal variants evaluated"))?;

    let mut cue_rationale = selected.rationale_codes.clone();
    let selected_variant = SignalVariant::parse(&selected.variant);
    let selected_scores = selected_variant
        .map(|variant| signal_series.for_variant(variant))
        .unwrap_or(z_scores);
    let selected_spread_z = *selected_scores.last().unwrap_or(&0.0);
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
    let evaluated_at = input.timestamps.last().copied().unwrap_or_else(Utc::now);
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
        spread_z: selected_spread_z,
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
        evaluated_at,
    };

    Ok(PairEvaluationOutput {
        cue,
        variants,
        half_life_bars,
        hedge_ratio,
        hedge_ratio_stability,
        spread_vol_bps,
    })
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

    let left_prices = quantize_close_series_to_ticks(
        left_closes,
        config.left_constraints.map(|value| value.tick_size),
    );
    let right_prices = quantize_close_series_to_ticks(
        right_closes,
        config.right_constraints.map(|value| value.tick_size),
    );
    let Some(executable_unit) = derive_executable_spread_unit(
        *left_prices.last().unwrap_or(&0.0),
        *right_prices.last().unwrap_or(&0.0),
        config.hedge_ratio,
        config.left_constraints,
        config.right_constraints,
    ) else {
        return BacktestSeries {
            points: vec![],
            markers: vec![],
        };
    };
    let spread = build_executable_spread_series(
        &left_prices,
        &right_prices,
        executable_unit.left_qty,
        executable_unit.right_qty,
    );
    let signal_series =
        build_variant_score_series(&spread, config.z_window, config.funding_drag_bps);
    let z_scores = signal_series.for_variant(config.selected_variant);
    if z_scores.len() != spread.len() {
        return BacktestSeries {
            points: vec![],
            markers: vec![],
        };
    }

    compute_backtest_series_from_zscores(
        timestamps,
        &left_prices,
        &right_prices,
        &spread,
        z_scores,
        config,
        executable_unit,
    )
}

fn compute_backtest_series_from_zscores(
    timestamps: &[DateTime<Utc>],
    left_closes: &[f64],
    right_closes: &[f64],
    spread_values: &[f64],
    z_scores: &[f64],
    config: BacktestConfig,
    executable_unit: ExecutableSpreadUnit,
) -> BacktestSeries {
    if z_scores.len() != timestamps.len() || spread_values.len() != timestamps.len() {
        return BacktestSeries {
            points: vec![],
            markers: vec![],
        };
    }

    let mut points = Vec::with_capacity(timestamps.len().saturating_sub(1));
    let mut markers = vec![];
    let mut position: i8 = 0;
    let mut equity = 1.0;
    let mut entry_spread_value: Option<f64> = None;
    let mut entry_notional_usd = 0.0;
    let mut entry_trade_z: Option<f64> = None;
    let mut entry_sigma_usd = 0.0;
    let mut equity_at_entry = 1.0;
    let round_trip_cost = (config.round_trip_cost_bps.max(0.0) / 20_000.0).clamp(0.0, 1.0);
    let stop_abs = config.stop_band.abs();
    let entry_abs = config.entry_band.abs().max(0.0);
    let stop_to_entry_span = (stop_abs - entry_abs).max(0.0);
    let rearm_level = stop_abs - stop_to_entry_span * STOP_RETRACE_FRACTION;
    let mut short_entry_cooldown_active = false;
    let mut long_entry_cooldown_active = false;

    for idx in 1..timestamps.len() {
        let signal_z = z_scores[idx];
        let left_now = left_closes[idx];
        let right_now = right_closes[idx];
        let current_spread_value = spread_values[idx];
        let position_at_bar_start = position;
        let mut chart_z = signal_z;
        if stop_abs > 0.0 {
            if signal_z >= stop_abs {
                short_entry_cooldown_active = true;
            }
            if signal_z <= -stop_abs {
                long_entry_cooldown_active = true;
            }
            if short_entry_cooldown_active && signal_z <= rearm_level {
                short_entry_cooldown_active = false;
            }
            if long_entry_cooldown_active && signal_z >= -rearm_level {
                long_entry_cooldown_active = false;
            }
        }

        if position_at_bar_start == 0 {
            let at_or_beyond_stop = signal_z.abs() >= config.stop_band.abs();
            if at_or_beyond_stop {
                // Fail closed: never open new entries at/through the stop level.
            } else if signal_z <= -config.entry_band {
                if !long_entry_cooldown_active {
                    if let Some(trade_sigma_usd) =
                        trailing_spread_sigma_usd(spread_values, idx, config.z_window)
                    {
                        position = 1;
                        entry_spread_value = Some(current_spread_value);
                        entry_notional_usd = executable_spread_notional_usd(
                            left_now,
                            right_now,
                            executable_unit.left_qty,
                            executable_unit.right_qty,
                        );
                        entry_trade_z = Some(signal_z);
                        entry_sigma_usd = trade_sigma_usd;
                        equity *= 1.0 - round_trip_cost;
                        equity_at_entry = equity;
                        markers.push(BacktestMarker {
                            index: points.len(),
                            kind: "entry".to_string(),
                        });
                    }
                }
            } else if signal_z >= config.entry_band && !short_entry_cooldown_active {
                if let Some(trade_sigma_usd) =
                    trailing_spread_sigma_usd(spread_values, idx, config.z_window)
                {
                    position = -1;
                    entry_spread_value = Some(current_spread_value);
                    entry_notional_usd = executable_spread_notional_usd(
                        left_now,
                        right_now,
                        executable_unit.left_qty,
                        executable_unit.right_qty,
                    );
                    entry_trade_z = Some(signal_z);
                    entry_sigma_usd = trade_sigma_usd;
                    equity *= 1.0 - round_trip_cost;
                    equity_at_entry = equity;
                    markers.push(BacktestMarker {
                        index: points.len(),
                        kind: "entry".to_string(),
                    });
                }
            }
        } else {
            // Only evaluate close conditions for positions that were open
            // at the start of this bar. This prevents same-bar entry+stop overlays.
            let open_spread_value = entry_spread_value.unwrap_or(current_spread_value);
            let pnl_usd = if position == 1 {
                current_spread_value - open_spread_value
            } else {
                open_spread_value - current_spread_value
            };
            let pnl_return = if entry_notional_usd > 0.0 {
                pnl_usd / entry_notional_usd
            } else {
                0.0
            };
            equity = equity_at_entry * (1.0 + pnl_return);
            let direction_sign = if position == 1 { 1.0 } else { -1.0 };
            let trade_z = match entry_trade_z {
                Some(entry_z) if entry_sigma_usd > 1e-9 => {
                    entry_z + direction_sign * (pnl_usd / entry_sigma_usd)
                }
                _ => signal_z,
            };
            chart_z = trade_z;
            let exit_equity_after_cost = equity * (1.0 - round_trip_cost);
            let profitable_after_exit = exit_equity_after_cost > equity_at_entry;

            if trade_z.abs() >= config.stop_band {
                if position == 1 {
                    long_entry_cooldown_active = true;
                } else {
                    short_entry_cooldown_active = true;
                }
                position = 0;
                equity *= 1.0 - round_trip_cost;
                entry_spread_value = None;
                entry_notional_usd = 0.0;
                entry_trade_z = None;
                entry_sigma_usd = 0.0;
                equity_at_entry = equity;
                markers.push(BacktestMarker {
                    index: points.len(),
                    kind: "stop".to_string(),
                });
            } else {
                let should_exit = match config.exit_mode {
                    BacktestExitMode::MeanRevert => {
                        trade_z.abs() <= config.exit_band && profitable_after_exit
                    }
                    BacktestExitMode::OppositeExtreme => {
                        ((position == 1 && trade_z >= config.entry_band)
                            || (position == -1 && trade_z <= -config.entry_band))
                            && profitable_after_exit
                    }
                };
                if should_exit {
                    position = 0;
                    equity *= 1.0 - round_trip_cost;
                    entry_spread_value = None;
                    entry_notional_usd = 0.0;
                    entry_trade_z = None;
                    entry_sigma_usd = 0.0;
                    equity_at_entry = equity;
                    markers.push(BacktestMarker {
                        index: points.len(),
                        kind: "exit".to_string(),
                    });
                }
            }
        }

        points.push(BacktestPoint {
            ts: timestamps[idx],
            z: chart_z,
            signal_z,
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
    spread: &[f64],
    scores: &[f64],
    entry_band: f64,
    hold_bars: usize,
    achieved_notional_usd: f64,
) -> (usize, f64, f64) {
    if spread.len() < hold_bars + 2 || scores.len() != spread.len() || achieved_notional_usd <= 0.0
    {
        return (0, 0.0, 0.0);
    }

    let mut outcomes = vec![];
    for idx in 0..(spread.len() - hold_bars) {
        let score = scores[idx];
        let pnl = if score >= entry_band {
            spread[idx] - spread[idx + hold_bars]
        } else if score <= -entry_band {
            spread[idx + hold_bars] - spread[idx]
        } else {
            continue;
        };
        let pnl_bps = (pnl / achieved_notional_usd) * 10_000.0;
        outcomes.push(pnl_bps);
    }

    if outcomes.is_empty() {
        return (0, 0.0, 0.0);
    }

    let wins = outcomes.iter().filter(|value| **value > 0.0).count();
    let win_rate = wins as f64 / outcomes.len() as f64;
    let edge_bps = mean(&outcomes);
    (outcomes.len(), win_rate, edge_bps)
}

fn lot_step(constraints: Option<InstrumentTradingConstraints>) -> f64 {
    constraints
        .filter(|value| value.min_lot.is_finite() && value.min_lot > 0.0)
        .map(|value| value.min_lot)
        .unwrap_or(1.0)
}

fn quantize_close_series_to_ticks(values: &[f64], tick_size: Option<f64>) -> Vec<f64> {
    values
        .iter()
        .map(|value| {
            if let Some(tick) =
                tick_size.filter(|candidate| candidate.is_finite() && *candidate > 0.0)
            {
                quantize_price_to_tick(*value, tick).unwrap_or(*value)
            } else {
                *value
            }
        })
        .collect()
}

fn build_executable_spread_series(
    left_prices: &[f64],
    right_prices: &[f64],
    left_qty: f64,
    right_qty: f64,
) -> Vec<f64> {
    left_prices
        .iter()
        .zip(right_prices.iter())
        .map(|(left, right)| left_qty * *left - right_qty * *right)
        .collect()
}

fn trailing_spread_sigma_usd(spread_values: &[f64], idx: usize, window: usize) -> Option<f64> {
    if spread_values.is_empty() || idx >= spread_values.len() || idx < 2 {
        return None;
    }
    let win = window.max(2).min(idx);
    let slice = &spread_values[(idx - win)..idx];
    let sigma = stddev(slice);
    (sigma.is_finite() && sigma > 1e-9).then_some(sigma)
}

fn executable_spread_notional_usd(
    left_price: f64,
    right_price: f64,
    left_qty: f64,
    right_qty: f64,
) -> f64 {
    (left_price * left_qty).abs() + (right_price * right_qty).abs()
}

fn derive_executable_spread_unit(
    left_price: f64,
    right_price: f64,
    hedge_ratio: f64,
    left_constraints: Option<InstrumentTradingConstraints>,
    right_constraints: Option<InstrumentTradingConstraints>,
) -> Option<ExecutableSpreadUnit> {
    if !left_price.is_finite()
        || left_price <= 0.0
        || !right_price.is_finite()
        || right_price <= 0.0
    {
        return None;
    }

    let target_hedge_ratio = if hedge_ratio.is_finite() && hedge_ratio.abs() > 1e-9 {
        hedge_ratio.abs()
    } else {
        1.0
    };
    let ratio_scale = 1.0 + target_hedge_ratio;
    if !ratio_scale.is_finite() || ratio_scale <= 0.0 {
        return None;
    }

    let left_step = lot_step(left_constraints);
    let right_step = lot_step(right_constraints);
    let increment_candidates = [
        left_step * left_price * ratio_scale,
        right_step * right_price * (ratio_scale / target_hedge_ratio.max(1e-9)),
    ];
    let increment_notional_usd = increment_candidates
        .into_iter()
        .filter(|value| value.is_finite() && *value > 0.0)
        .fold(f64::INFINITY, f64::min);
    if !increment_notional_usd.is_finite() || increment_notional_usd <= 0.0 {
        return None;
    }

    let mut best_plan: Option<(ExecutableSpreadUnit, f64)> = None;
    for idx in 0..EXECUTABLE_SPREAD_SEARCH_STEPS {
        let target_notional_usd = increment_notional_usd * (idx as f64 + 1.0);
        let raw_left_qty = target_notional_usd / ratio_scale / left_price;
        let raw_right_qty = target_notional_usd * target_hedge_ratio / ratio_scale / right_price;
        let Some(left_qty) = quantize_to_step(raw_left_qty, left_step).filter(|value| *value > 0.0)
        else {
            continue;
        };
        let Some(right_qty) =
            quantize_to_step(raw_right_qty, right_step).filter(|value| *value > 0.0)
        else {
            continue;
        };
        let achieved_left_notional = (left_qty * left_price).abs();
        let achieved_right_notional = (right_qty * right_price).abs();
        let achieved_notional_usd = achieved_left_notional + achieved_right_notional;
        if !achieved_notional_usd.is_finite() || achieved_notional_usd <= 0.0 {
            continue;
        }
        let achieved_hedge_ratio = if achieved_left_notional > 0.0 {
            achieved_right_notional / achieved_left_notional
        } else {
            0.0
        };
        let notional_drift_pct =
            ((achieved_notional_usd - target_notional_usd).abs() / target_notional_usd) * 100.0;
        let hedge_ratio_drift_pct = if target_hedge_ratio > 0.0 {
            ((achieved_hedge_ratio - target_hedge_ratio).abs() / target_hedge_ratio) * 100.0
        } else {
            0.0
        };
        let plan = ExecutableSpreadUnit {
            left_qty,
            right_qty,
            achieved_notional_usd,
        };
        let drift_score = notional_drift_pct + hedge_ratio_drift_pct;
        if notional_drift_pct <= EXECUTABLE_SPREAD_NOTIONAL_DRIFT_TOLERANCE_PCT
            && hedge_ratio_drift_pct <= EXECUTABLE_SPREAD_HEDGE_DRIFT_TOLERANCE_PCT
        {
            return Some(plan);
        }
        match best_plan {
            Some((_, best_score)) if drift_score >= best_score => {}
            _ => best_plan = Some((plan, drift_score)),
        }
    }

    best_plan.map(|(plan, _)| plan)
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
        if idx < win {
            continue;
        }
        let slice = &values[(idx - win)..idx];
        let std = stddev(slice);
        if std > 0.0 {
            result[idx] = (values[idx] - mean(slice)) / std;
        }
    }
    result
}

#[derive(Debug, Clone)]
struct VariantScoreSeries {
    cointegration_z: Vec<f64>,
    robust_z: Vec<f64>,
    vol_normalized: Vec<f64>,
    funding_adjusted: Vec<f64>,
}

impl VariantScoreSeries {
    fn for_variant(&self, variant: SignalVariant) -> &[f64] {
        match variant {
            SignalVariant::CointegrationZ => self.cointegration_z.as_slice(),
            SignalVariant::RobustZ => self.robust_z.as_slice(),
            SignalVariant::VolNormalized => self.vol_normalized.as_slice(),
            SignalVariant::FundingAdjusted => self.funding_adjusted.as_slice(),
        }
    }
}

fn build_variant_score_series(
    spread: &[f64],
    window: usize,
    funding_drag_bps: f64,
) -> VariantScoreSeries {
    let cointegration_z = rolling_z_scores(spread, window);
    let robust_z = rolling_robust_z_scores(spread, window);
    let vol_normalized = rolling_vol_normalized_scores(spread, window);
    let funding_adjusted = cointegration_z
        .iter()
        .map(|value| value - (funding_drag_bps / 10.0))
        .collect::<Vec<_>>();
    VariantScoreSeries {
        cointegration_z,
        robust_z,
        vol_normalized,
        funding_adjusted,
    }
}

fn rolling_robust_z_scores(values: &[f64], window: usize) -> Vec<f64> {
    if values.is_empty() {
        return vec![];
    }
    let mut result = vec![0.0; values.len()];
    let win = window.max(10).min(values.len());
    for idx in 0..values.len() {
        if idx < win {
            continue;
        }
        let slice = &values[(idx - win)..idx];
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
    let diffs = values
        .windows(2)
        .map(|window| window[1] - window[0])
        .collect::<Vec<_>>();
    let vol = rolling_z_scores(&diffs, window.max(10));
    let mut normalized = vec![0.0; values.len()];
    for idx in 0..values.len() {
        let vol_idx = idx.saturating_sub(1).min(vol.len().saturating_sub(1));
        let vol_penalty = 1.0 + vol[vol_idx].abs();
        normalized[idx] = z[idx] / vol_penalty;
    }
    normalized
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

#[cfg(test)]
mod tests {
    use super::{
        annotate_with_shadow_model, build_executable_spread_series, build_portfolio_plan,
        build_variant_score_series, compute_backtest_series, compute_backtest_series_from_zscores,
        derive_executable_spread_unit, evaluate_cost_gate, evaluate_pair, mean,
        quantize_close_series_to_ticks, rolling_z_scores, stddev, to_direction_hint_with_stop,
        to_direction_hint_with_stop_retrace, train_shadow_model, BacktestConfig, BacktestExitMode,
        CostGateDiagnostics, CostGateInput, DirectionHint, ExecutableSpreadUnit, FundingModel,
        PairCue, PairEvaluationInput, PortfolioHint, Regime, SetupGateDiagnostics,
        ShadowMlDiagnostics, ShadowModelTrainingRow, SignalVariant, TradeGateDiagnostics,
    };
    use chrono::{Duration, Utc};
    use common_types::{kraken_perp_constraints, Timeframe};

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
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
        })
        .expect("pair evaluation should succeed");

        assert_eq!(result.variants.len(), 4);
        assert!(!result.cue.selected_variant.is_empty());
        assert!(result.cue.entry_band > result.cue.exit_band);
    }

    #[test]
    fn evaluate_pair_sets_cue_spread_z_from_selected_variant() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps,
            left_closes: left.clone(),
            right_closes: right.clone(),
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
        })
        .expect("pair evaluation should succeed");

        let left_constraints = kraken_perp_constraints("PI_XBTUSD");
        let right_constraints = kraken_perp_constraints("PI_ETHUSD");
        let left_prices =
            quantize_close_series_to_ticks(&left, left_constraints.map(|value| value.tick_size));
        let right_prices =
            quantize_close_series_to_ticks(&right, right_constraints.map(|value| value.tick_size));
        let executable_unit = derive_executable_spread_unit(
            *left_prices.last().expect("left last close"),
            *right_prices.last().expect("right last close"),
            result.hedge_ratio,
            left_constraints,
            right_constraints,
        )
        .expect("executable spread unit should derive");
        let spread = build_executable_spread_series(
            &left_prices,
            &right_prices,
            executable_unit.left_qty,
            executable_unit.right_qty,
        );
        let signal_series = build_variant_score_series(&spread, spread.len().clamp(30, 180), 0.6);
        let selected_variant = SignalVariant::parse(&result.cue.selected_variant)
            .expect("selected variant should parse");
        let expected_z = *signal_series
            .for_variant(selected_variant)
            .last()
            .expect("selected series should have last value");

        assert!((result.cue.spread_z - expected_z).abs() < 1e-9);
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
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
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
            entry_band: 1.2,
            exit_band: 0.5,
            stop_band: 3.0,
            hold_bars: 8,
            max_half_life_bars: 10.0,
            funding_drag_bps: 0.5,
            taker_fee_bps: 1.2,
            min_samples_target: 6,
        })
        .expect("pair evaluation should succeed");

        assert!(result
            .cue
            .rationale_codes
            .iter()
            .any(|code| code == "HALF_LIFE_TOO_LONG"));
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
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 10,
            max_half_life_bars: 120.0,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
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
                selected_variant: SignalVariant::CointegrationZ,
                z_window: timestamps.len().min(180),
                funding_drag_bps: 0.0,
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
    fn backtest_series_last_z_matches_selected_variant_cue() {
        let (timestamps, left, right) = synthetic_pair_series(260);
        let left_constraints = kraken_perp_constraints("PI_XBTUSD");
        let right_constraints = kraken_perp_constraints("PI_ETHUSD");
        let result = evaluate_pair(PairEvaluationInput {
            pair_id: "PI_XBTUSD__PI_ETHUSD".to_string(),
            left_instrument: "PI_XBTUSD".to_string(),
            right_instrument: "PI_ETHUSD".to_string(),
            timeframe: Timeframe::OneMinute,
            timestamps: timestamps.clone(),
            left_closes: left.clone(),
            right_closes: right.clone(),
            entry_band: 1.6,
            exit_band: 0.5,
            stop_band: 3.2,
            hold_bars: 12,
            max_half_life_bars: 120.0,
            funding_drag_bps: 0.6,
            taker_fee_bps: 1.2,
            min_samples_target: 8,
        })
        .expect("pair evaluation should succeed");

        let series = compute_backtest_series(
            &timestamps,
            &left,
            &right,
            BacktestConfig {
                hedge_ratio: result.hedge_ratio,
                selected_variant: SignalVariant::parse(&result.cue.selected_variant)
                    .expect("selected variant should parse"),
                z_window: timestamps.len().min(180),
                funding_drag_bps: 0.6,
                entry_band: result.cue.entry_band,
                exit_band: result.cue.exit_band,
                stop_band: result.cue.stop_band,
                round_trip_cost_bps: result.cue.cost_estimate_bps,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints,
                right_constraints,
            },
        );

        let last_chart_z = series.points.last().expect("series should have points").z;
        assert!((last_chart_z - result.cue.spread_z).abs() < 1e-9);
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
                selected_variant: SignalVariant::CointegrationZ,
                z_window: timestamps.len().min(180),
                funding_drag_bps: 0.0,
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
                selected_variant: SignalVariant::CointegrationZ,
                z_window: timestamps.len().min(180),
                funding_drag_bps: 0.0,
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
                selected_variant: SignalVariant::CointegrationZ,
                z_window: timestamps.len().min(180),
                funding_drag_bps: 0.0,
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
        let z_scores = vec![
            0.0, 1.4, 1.8, 1.3, 0.7, 0.2, -0.1, -0.8, -1.3, -1.7, -1.2, -0.4, 0.3, 1.2,
        ];
        let (timestamps, left, right) = synthetic_spread_path(&z_scores);
        let spread_values = build_executable_spread_series(&left, &right, 1.0, 1.0);
        let executable_unit = test_executable_unit(1.0, 1.0, &left, &right);

        let mean_revert = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 3,
                funding_drag_bps: 0.0,
                entry_band: 1.0,
                exit_band: 0.25,
                stop_band: 4.0,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
        );
        let opposite_extreme = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 3,
                funding_drag_bps: 0.0,
                entry_band: 1.0,
                exit_band: 0.25,
                stop_band: 4.0,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::OppositeExtreme,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
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
        let z_scores = vec![
            -0.5, 0.3, 1.1, 1.3, 1.25, 1.18, 1.15, 0.9, 0.2, -0.4, -1.0, -1.2, -1.0, -0.6, -0.1,
        ];
        let (timestamps, left, right) = synthetic_spread_path(&z_scores);
        let entry_band = 1.0;
        let stop_band = 1.2;
        let rearm_level = stop_band - (stop_band - entry_band) * 0.25;
        let spread_values = build_executable_spread_series(&left, &right, 1.0, 1.0);
        let executable_unit = test_executable_unit(1.0, 1.0, &left, &right);

        let series = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 3,
                funding_drag_bps: 0.0,
                entry_band,
                exit_band: 0.3,
                stop_band,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
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

    #[test]
    fn executable_backtest_long_spread_pnl_improves_when_spread_reverts_up() {
        let timestamps = synthetic_timestamps(6);
        let left = vec![100.0, 101.0, 98.0, 99.0, 100.0, 101.0];
        let right = vec![100.0; 6];
        let spread_values = build_executable_spread_series(&left, &right, 1.0, 1.0);
        let z_scores = vec![0.0, 0.0, -2.2, -1.6, -1.0, -0.2];
        let executable_unit = test_executable_unit(1.0, 1.0, &left, &right);

        let series = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 2,
                funding_drag_bps: 0.0,
                entry_band: 1.8,
                exit_band: 0.5,
                stop_band: 3.2,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
        );

        let entry_idx = series
            .markers
            .iter()
            .find(|marker| marker.kind == "entry")
            .expect("long entry marker")
            .index;
        let exit_idx = series
            .markers
            .iter()
            .find(|marker| marker.kind == "exit")
            .expect("long exit marker")
            .index;

        assert!(series.points[entry_idx].equity >= 1.0);
        assert!(series.points[exit_idx].equity > series.points[entry_idx].equity);
        assert!(series.points[exit_idx].equity > 1.0);
        assert!((series.points[entry_idx].z + 2.2).abs() < 1e-9);
        assert!(series.points[exit_idx].z > series.points[entry_idx].z);
        assert!(series.points[exit_idx].z.abs() < series.points[entry_idx].z.abs());
        assert!((series.points[entry_idx].signal_z + 2.2).abs() < 1e-9);
    }

    #[test]
    fn executable_backtest_short_spread_pnl_improves_when_spread_reverts_down() {
        let timestamps = synthetic_timestamps(6);
        let left = vec![100.0, 99.0, 102.0, 101.0, 100.0, 99.0];
        let right = vec![100.0; 6];
        let spread_values = build_executable_spread_series(&left, &right, 1.0, 1.0);
        let z_scores = vec![0.0, 0.0, 2.2, 1.6, 1.0, 0.2];
        let executable_unit = test_executable_unit(1.0, 1.0, &left, &right);

        let series = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 2,
                funding_drag_bps: 0.0,
                entry_band: 1.8,
                exit_band: 0.5,
                stop_band: 3.2,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
        );

        let entry_idx = series
            .markers
            .iter()
            .find(|marker| marker.kind == "entry")
            .expect("short entry marker")
            .index;
        let exit_idx = series
            .markers
            .iter()
            .find(|marker| marker.kind == "exit")
            .expect("short exit marker")
            .index;

        assert!(series.points[entry_idx].equity >= 1.0);
        assert!(series.points[exit_idx].equity > series.points[entry_idx].equity);
        assert!(series.points[exit_idx].equity > 1.0);
        assert!((series.points[entry_idx].z - 2.2).abs() < 1e-9);
        assert!(series.points[exit_idx].z < series.points[entry_idx].z);
        assert!(series.points[exit_idx].z.abs() < series.points[entry_idx].z.abs());
        assert!((series.points[entry_idx].signal_z - 2.2).abs() < 1e-9);
    }

    #[test]
    fn backtest_skips_entry_when_trade_sigma_is_unavailable() {
        let timestamps = synthetic_timestamps(5);
        let left = vec![100.0; 5];
        let right = vec![100.0; 5];
        let spread_values = build_executable_spread_series(&left, &right, 1.0, 1.0);
        let z_scores = vec![0.0, -2.2, -2.0, -1.8, -1.6];
        let executable_unit = test_executable_unit(1.0, 1.0, &left, &right);

        let series = compute_backtest_series_from_zscores(
            &timestamps,
            &left,
            &right,
            &spread_values,
            &z_scores,
            BacktestConfig {
                hedge_ratio: 1.0,
                selected_variant: SignalVariant::CointegrationZ,
                z_window: 3,
                funding_drag_bps: 0.0,
                entry_band: 1.8,
                exit_band: 0.5,
                stop_band: 3.2,
                round_trip_cost_bps: 0.0,
                exit_mode: BacktestExitMode::MeanRevert,
                left_constraints: None,
                right_constraints: None,
            },
            executable_unit,
        );

        assert!(series.markers.is_empty());
        assert!(series.points.iter().all(|point| point.z == point.signal_z));
    }

    #[test]
    fn rolling_z_scores_use_prior_window_reference() {
        let values = (0..=11).map(|value| value as f64).collect::<Vec<_>>();
        let scores = rolling_z_scores(&values, 10);
        let expected = (10.0 - mean(&values[0..10])) / stddev(&values[0..10]);
        assert_eq!(scores[0], 0.0);
        assert_eq!(scores[9], 0.0);
        assert!((scores[10] - expected).abs() < 1e-9);
        assert!(scores[10] > 1.8);
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

    fn synthetic_timestamps(n: usize) -> Vec<chrono::DateTime<Utc>> {
        let start = Utc::now() - Duration::minutes(n as i64);
        (0..n)
            .map(|idx| start + Duration::minutes(idx as i64))
            .collect()
    }

    fn test_executable_unit(
        left_qty: f64,
        right_qty: f64,
        left_prices: &[f64],
        right_prices: &[f64],
    ) -> ExecutableSpreadUnit {
        let achieved_notional_usd = left_prices
            .last()
            .zip(right_prices.last())
            .map(|(left_price, right_price)| {
                (left_qty * *left_price).abs() + (right_qty * *right_price).abs()
            })
            .unwrap_or(0.0);
        ExecutableSpreadUnit {
            left_qty,
            right_qty,
            achieved_notional_usd,
        }
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
            evaluated_at: Utc::now(),
        }
    }
}
