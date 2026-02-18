use chrono::{DateTime, Utc};
use common_types::Timeframe;
use serde::Serialize;

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
    pub actionable: bool,
    pub rationale_codes: Vec<String>,
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
    pub min_samples_target: usize,
}

#[derive(Debug, Clone)]
pub struct PairEvaluationOutput {
    pub cue: PairCue,
    pub variants: Vec<VariantEvaluation>,
    pub half_life_bars: f64,
    pub hedge_ratio: f64,
    pub hedge_ratio_stability: f64,
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

    let half_life_bars = estimate_half_life(&spread);
    let hedge_ratio_stability = estimate_hedge_ratio_stability(&left_log, &right_log);

    let lookback = input.left_closes.len().min(180);
    let z_scores = rolling_z_scores(&spread, lookback.max(30));
    let robust_z_scores = rolling_robust_z_scores(&spread, lookback.max(30));
    let vol_norm_scores = rolling_vol_normalized_scores(&spread, lookback.max(30));
    let funding_scores = z_scores
        .iter()
        .map(|value| value - (input.funding_drag_bps / 10.0))
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
            &spread,
            &input.left_closes,
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
    let mut direction_hint = to_direction_hint(selected.score_last, input.entry_band);
    let mut actionable = direction_hint != DirectionHint::None && selected.opportunity_score > 0.0;

    if !half_life_bars.is_finite() || half_life_bars > input.max_half_life_bars {
        actionable = false;
        direction_hint = DirectionHint::None;
        cue_rationale.push("HALF_LIFE_TOO_LONG".to_string());
    }
    if hedge_ratio_stability > 0.40 {
        actionable = false;
        direction_hint = DirectionHint::None;
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
        spread_z,
        opportunity_score: selected.opportunity_score,
        confidence_band: confidence_band.to_string(),
        entry_band: input.entry_band,
        exit_band: input.exit_band,
        stop_band: input.stop_band,
        expected_hold_bars,
        cost_estimate_bps: input.funding_drag_bps,
        actionable,
        rationale_codes: cue_rationale,
        shadow_ml: ShadowMlDiagnostics::unavailable(vec!["NOT_EVALUATED".to_string()]),
        evaluated_at,
    };

    Ok(PairEvaluationOutput {
        cue,
        variants,
        half_life_bars,
        hedge_ratio,
        hedge_ratio_stability,
    })
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
    left_prices: &[f64],
    scores: &[f64],
    entry_band: f64,
    hold_bars: usize,
) -> (usize, f64, f64) {
    if spread.len() < hold_bars + 2
        || scores.len() != spread.len()
        || left_prices.len() != spread.len()
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
        let left_price = left_prices[idx].abs().max(1e-9);
        let pnl_bps = (pnl / left_price) * 10_000.0;
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
        annotate_with_shadow_model, evaluate_pair, train_shadow_model, DirectionHint,
        PairEvaluationInput, Regime, ShadowModelTrainingRow, SignalVariant,
    };
    use chrono::{Duration, Utc};
    use common_types::Timeframe;

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
            min_samples_target: 8,
        })
        .expect("pair evaluation should succeed");

        assert_eq!(result.variants.len(), 4);
        assert!(!result.cue.selected_variant.is_empty());
        assert!(result.cue.entry_band > result.cue.exit_band);
    }

    #[test]
    fn evaluate_pair_can_reject_action_when_half_life_too_long() {
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
            min_samples_target: 6,
        })
        .expect("pair evaluation should succeed");

        assert!(!result.cue.actionable);
        assert_eq!(result.cue.direction_hint, DirectionHint::None.as_str());
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
}
