export type Timeframe = "1m" | "15m" | "1h";

export type DirectionHint = "LONG_SPREAD" | "SHORT_SPREAD" | "NONE";

export interface CostGate {
  status: "AVAILABLE" | "UNAVAILABLE";
  expected_edge_bps: number;
  fee_bps: number;
  funding_bps: number;
  slippage_bps: number;
  net_edge_bps: number;
  pass: boolean;
  rationale_codes: string[];
}

export interface PortfolioHint {
  status: "AVAILABLE" | "UNAVAILABLE";
  target_weight: number;
  risk_contribution: number;
  cap_applied: boolean;
  rationale_codes: string[];
}

export interface ShadowMl {
  status: "AVAILABLE" | "UNAVAILABLE";
  model_name: string;
  training_rows: number;
  positive_rate: number;
  precision: number;
  brier_score: number;
  recommended_variant: string;
  recommended_probability: number;
  agrees_with_selected: boolean;
  rationale_codes: string[];
}

export interface Cue {
  pair_id: string;
  left_instrument: string;
  right_instrument: string;
  timeframe: Timeframe;
  regime: "CALM" | "TRENDING" | "SHOCK";
  selected_variant: string;
  direction_hint: DirectionHint;
  spread_z: number;
  opportunity_score: number;
  confidence_band: "LOW" | "MEDIUM" | "HIGH";
  entry_band: number;
  exit_band: number;
  stop_band: number;
  expected_hold_bars: number;
  cost_estimate_bps: number;
  actionable: boolean;
  rationale_codes: string[];
  cost_gate: CostGate;
  portfolio_hint: PortfolioHint;
  shadow_ml: ShadowMl;
  evaluated_at: string;
}

export interface CueVariant {
  variant: string;
  score_last: number;
  sample_count: number;
  win_rate: number;
  edge_bps: number;
  reliability: number;
  regime_fit: number;
  opportunity_score: number;
  shadow_success_probability: number | null;
  shadow_rank_score: number | null;
  rationale_codes: string[];
}

export interface CueRow {
  cue: Cue;
  variants: CueVariant[];
  half_life_bars: number;
  hedge_ratio: number;
  hedge_ratio_stability: number;
}

export interface StrategyPairsCuesResponse {
  timeframe: Timeframe;
  generated_at: string;
  cues: CueRow[];
  candidate_set: {
    total_pairs: number;
    evaluated_pairs: number;
    actionable_pairs: number;
    cost_gate_pass_pairs: number;
    shadow_disagreement_pairs: number;
  };
  portfolio_plan: {
    status: "AVAILABLE" | "UNAVAILABLE";
    weights: Array<{
      pair_id: string;
      target_weight: number;
      risk_contribution: number;
      cap_applied: boolean;
    }>;
    constraints: {
      dollar_neutral: boolean;
      gross_cap: number;
      per_pair_cap: number;
    };
    rationale_codes: string[];
  };
  skipped: Array<{ pair_id: string; reason: string }>;
}

export interface StrategyPairsCostGateResponse {
  timeframe: Timeframe;
  generated_at: string;
  gates: Array<{
    pair_id: string;
    left_instrument: string;
    right_instrument: string;
    timeframe: Timeframe;
    expected_edge_bps: number;
    fee_bps: number;
    funding_bps: number;
    slippage_bps: number;
    net_edge_bps: number;
    pass: boolean;
    rationale_codes: string[];
  }>;
  skipped: Array<{ pair_id: string; reason: string }>;
}

export interface StrategyPairsPortfolioPlanResponse {
  timeframe: Timeframe;
  generated_at: string;
  plan: {
    status: "AVAILABLE" | "UNAVAILABLE";
    weights: Array<{
      pair_id: string;
      target_weight: number;
      risk_contribution: number;
      cap_applied: boolean;
    }>;
    constraints: {
      dollar_neutral: boolean;
      gross_cap: number;
      per_pair_cap: number;
    };
    rationale_codes: string[];
  };
  skipped: Array<{ pair_id: string; reason: string }>;
}

export interface IntegrityHistoryResponse {
  instrument: string;
  timeframe: Timeframe;
  rows: Array<{
    start_ts: string;
    end_ts: string;
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    reason: string;
    checked_at: string;
  }>;
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface DataQueryResponse {
  instrument: string;
  timeframe: Timeframe;
  start_ts: string;
  end_ts: string;
  candles: Candle[];
  integrity: {
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    missing_ranges: Array<{ start_ts: string; end_ts: string; reason: string }>;
    last_verified_at: string;
    warnings: string[];
  };
}

export interface KillSwitchState {
  active: boolean;
  reason: string;
  updated_at: string;
}

export interface ExecutionDecisionResponse {
  instrument: string;
  timeframe: Timeframe;
  decision: "ALLOWED" | "BLOCKED";
  reason: string | null;
  min_coverage_pct: number;
  evaluated_at: string;
}

export type ExecutionAction = "ENTRY" | "EXIT" | "EMERGENCY_STOP_CLOSE";
export type TradeSide = "BUY" | "SELL";

export interface OrderIntentRequest {
  idempotency_key: string;
  exchange: string;
  account_id: string;
  instrument: string;
  timeframe: Timeframe;
  action: ExecutionAction;
  side: TradeSide;
  qty: number;
  operator_confirmed: boolean;
  operator_id: string | null;
  min_coverage_pct: number;
}

export interface OrderIntentResponse {
  idempotency_key: string;
  exchange: string;
  account_id: string;
  instrument: string;
  timeframe: Timeframe;
  action: ExecutionAction;
  side: TradeSide;
  qty: number;
  operator_confirmed: boolean;
  operator_id: string | null;
  min_coverage_pct: number;
  decision: "ACCEPTED" | "BLOCKED";
  reason: string | null;
  evaluated_at: string;
}

export interface ReconcileResponse {
  reconcile: {
    exchange: string;
    account_id: string;
    ts: string;
    status: "OK" | "STALE_SNAPSHOT" | "DRIFT_EXCEEDED";
    drift_notional: number;
    notes: string;
  } | null;
}

export interface SpreadPosition {
  direction: DirectionHint;
  totalSize: number;
  avgEntryZ: number;
  updatedAt: string;
}

export interface TimelineEvent {
  ts: string;
  text: string;
  tone: "ok" | "warn" | "bad";
}

export interface SpreadSeriesPoint {
  ts: string;
  z: number;
  spreadReturn: number;
}

export interface ChartMarker {
  index: number;
  kind: "entry" | "exit" | "stop";
}
