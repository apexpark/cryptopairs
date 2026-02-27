import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useCallback, useEffect, useMemo, useState } from "react";
import LineChart from "./components/LineChart";
import {
  allAcceptedDispatchAcknowledged,
  latestLifecycleState,
} from "./lib/orderLifecycle";
import { buildActiveTradeAnchor, buildExecutionMarkers } from "./lib/chartMarkers";
import {
  buildStrategyMaintenanceArtifactUrl,
  buildStrategyOpportunityHistoryUrl,
  fetchStrategyExpectancy,
  fetchStrategyReplayTrades,
  fetchStrategyUiAuthStatus,
  verifyStrategyUiAccess,
  fetchStrategyPaperTrades,
  fetchStrategyOpportunityHistoryStats,
  fetchStrategyMaintenanceLatest,
  runStrategyResearchSweep,
  runStrategyMaintenanceAction,
  fetchExecutionPortfolioPositions,
  dispatchOrderIntent,
  fetchExecutionDecision,
  fetchIntegrityHistory,
  fetchKillSwitchState,
  fetchMarketMetrics,
  fetchOrderIntentHistory,
  fetchReconcile,
  fetchStrategyBacktest,
  fetchStrategyCostGates,
  fetchStrategyCues,
  fetchStrategyLiveZ,
  fetchStrategyPortfolioPlan,
  submitOrderIntent,
} from "./lib/api";
import {
  emptyPosition,
  isAddAllowed,
  isCloseAllowed,
  isEntryAllowed,
  isGateSafe,
  isReduceAllowed,
  isStopConfigured,
} from "./lib/tradeGuards";
import type {
  ChartMarker,
  BacktestExitMode,
  DispatchIntentResponse,
  DirectionHint,
  ExecutionAction,
  IntegrityHistoryResponse,
  KillSwitchState,
  MarketMetricsResponse,
  OrderIntentHistoryResponse,
  ReconcileResponse,
  SpreadPosition,
  StrategyPairsCostGateResponse,
  StrategyPairsCuesResponse,
  StrategyPairsExpectancyResponse,
  StrategyPairsPaperTradesResponse,
  StrategyPairsReplayTradesResponse,
  StrategyPairsResearchSweepResponse,
  StrategyPairsOpportunityHistoryStatsResponse,
  StrategyMaintenanceActionResponse,
  StrategyMaintenanceLatestResponse,
  StrategyPairsPortfolioPlanResponse,
  StrategyZMethod,
  Timeframe,
  TimelineEvent,
  TradeSide,
} from "./types";
import logoDark from "./assets/logo-dark.png";
import logoLight from "./assets/logo-light.png";

type PageId =
  | "trade"
  | "how-it-works"
  | "markets"
  | "analytics"
  | "portfolio"
  | "data-quality"
  | "maintenance"
  | "settings";

type ThemeMode = "dark" | "light";

type TradeCommand =
  | "long-entry"
  | "short-entry"
  | "add-exposure"
  | "reduce-exposure"
  | "close-spread";

interface SpreadLeg {
  instrument: string;
  side: TradeSide;
}

interface LegExecutionOutcome {
  instrument: string;
  intentDecision: "ACCEPTED" | "BLOCKED";
  intentReason: string | null;
  dispatch: DispatchIntentResponse | null;
  dispatchError: string | null;
  history: OrderIntentHistoryResponse | null;
}

interface ModelHealthSnapshot {
  timeframe: Timeframe;
  status: "AVAILABLE" | "UNAVAILABLE" | "NO_CUES" | "ERROR" | "LOADING";
  rationaleCodes: string[];
  sampledSlippageActive: boolean;
  fundingModel: string | null;
  fundingEvents: number | null;
  fundingBpsPerEvent: number | null;
  fundingBps: number | null;
  message: string | null;
  updatedAt: string | null;
}

const NAV_ITEMS: Array<{ id: PageId; label: string }> = [
  { id: "trade", label: "Trade" },
  { id: "how-it-works", label: "How This Works" },
  { id: "markets", label: "Markets" },
  { id: "analytics", label: "Analytics" },
  { id: "portfolio", label: "Portfolio" },
  { id: "data-quality", label: "Data Quality" },
  { id: "maintenance", label: "Maintenance" },
  { id: "settings", label: "Settings" },
];

type HowItWorksTabId =
  | "pairs-trading"
  | "opportunity-engine"
  | "hedge-ratio"
  | "risks"
  | "definitions"
  | "reoptimise";

const HOW_IT_WORKS_TABS: Array<{
  id: HowItWorksTabId;
  label: string;
  title: string;
  intro: string;
  paragraphs: string[];
  bullets: string[];
}> = [
  {
    id: "pairs-trading",
    label: "What Is Pairs Trading",
    title: "What Is Pairs Trading",
    intro:
      "Pairs trading focuses on the relationship between two futures contracts, not a single market direction.",
    paragraphs: [
      "Think of two runners tied by a rope. They can separate for short periods, then pull back toward each other.",
      "The platform measures that distance as a spread and flags unusual stretches as potential opportunities.",
      "A spread trade opens opposite legs so your result is driven more by relationship movement than broad market trend.",
    ],
    bullets: [
      "Long Spread: buy one leg and sell the other using model sizing.",
      "Short Spread: reverse those legs when stretch is in the opposite direction.",
      "Goal: capture spread convergence with controlled risk, not predict absolute price.",
    ],
  },
  {
    id: "opportunity-engine",
    label: "Opportunity Engine",
    title: "Opportunity Engine",
    intro:
      "The Opportunity Engine scans configured pairs and ranks potential setups on every cycle.",
    paragraphs: [
      "It evaluates multiple spread variants, not one fixed formula, then measures how far the spread is from recent normal behavior.",
      "It applies cost and quality checks before a setup can be considered actionable, including fees, funding drag, slippage, and stability.",
      "It then selects the best-performing variant from recent live behavior and publishes cue details for operator review.",
    ],
    bullets: [
      "Inputs: spread signal, z-score stretch, regime, stability, and execution costs.",
      "Output: direction hint, confidence, entry/exit/stop bands, and rationale tags.",
      "Fail-safe: if quality or safety checks fail, cue remains non-actionable.",
    ],
  },
  {
    id: "hedge-ratio",
    label: "Hedge Ratio",
    title: "Hedge Ratio and Leg Sizing",
    intro:
      "The hedge ratio is the balance setting between the two legs that aims to neutralize shared market movement.",
    paragraphs: [
      "Its purpose is to isolate relative mispricing between the pair, so P&L is driven more by spread convergence or divergence and less by broad crypto direction.",
      "When you set spread size, the system converts that into leg quantities using the current hedge ratio and contract constraints.",
      "The ratio is recalculated over time as relationships evolve, so leg sizing adapts to new market structure.",
    ],
    bullets: [
      "Example: 1.00 spread unit can become Long A 1.00 vs Short B 0.62.",
      "Sizing is applied consistently for entry, add, reduce, and close actions.",
      "If ratio stability degrades, the opportunity engine can downgrade or block entry.",
    ],
  },
  {
    id: "risks",
    label: "Risks",
    title: "Key Risks to Understand",
    intro:
      "Pairs trading reduces some directional exposure, but it does not remove risk.",
    paragraphs: [
      "Relationship risk: pairs can stop mean-reverting or shift into a new regime where historical behavior no longer applies.",
      "Execution and cost risk: slippage, partial fills, fees, and funding can erase expected edge.",
      "Data and model risk: stale or incomplete data can lead to poor cues, which is why integrity and reconciliation gates are enforced.",
    ],
    bullets: [
      "Leverage and liquidation risk still apply if sizing is too aggressive.",
      "Fail-closed mode blocks new entries when gates are unsafe.",
      "Operator can still reduce or close open spread exposure during degraded conditions.",
    ],
  },
  {
    id: "definitions",
    label: "Definitions",
    title: "Trading Terms Used In This UI",
    intro: "These are the plain-language meanings of the key fields shown on the Trade and Analytics pages.",
    paragraphs: [
      "These terms are computed each cycle from live market and strategy data, then displayed as decision support.",
      "They do not guarantee profit on their own; they describe the current setup quality and gating status.",
    ],
    bullets: [
      "Z: how far the spread is from its recent normal level, measured in standard deviations.",
      "Edge: estimated advantage after expected spread behavior, usually compared against costs in basis points.",
      "Gate: a pass/block safety check (cost, data quality, reconcile, kill switch, and model guards).",
      "Opportunity Score: ranked setup quality number combining stretch, regime fit, costs, and stability.",
      "Cost Estimate: expected execution friction (fees, funding, slippage) in basis points.",
    ],
  },
  {
    id: "reoptimise",
    label: "Reoptimise",
    title: "Reoptimise and Shadow Model Fields",
    intro: "These diagnostics explain how the strategy chooses its active variant and validates it with shadow models.",
    paragraphs: [
      "Reoptimisation continuously re-evaluates candidate spread variants and promotes the best recent performer when policy allows.",
      "Shadow metrics are advisory checks that reduce model-drift risk before changes are promoted.",
    ],
    bullets: [
      "Champion Variant: currently selected strategy variant used for cues and bands.",
      "Shadow Agreement: whether shadow model preference matches the active champion choice.",
      "Cost Gate: pass/block outcome after fees, funding, and slippage are netted from expected edge.",
      "Shadow ML Precision: recent hit-rate quality of the shadow model on labeled outcomes.",
    ],
  },
];

const TIMEFRAMES: Timeframe[] = ["1m", "15m", "1h"];
const RESEARCH_Z_METHODS: StrategyZMethod[] = [
  "ROBUST_Z",
  "COINTEGRATION_Z",
  "VOL_NORMALIZED",
  "FUNDING_ADJUSTED",
];
const WEB_BUILD_STAMP = "2026-02-23-02";

function analyticsRefreshMs(timeframe: Timeframe): number {
  if (timeframe === "1m") {
    return 15_000;
  }
  if (timeframe === "15m") {
    return 45_000;
  }
  return 90_000;
}

function loadingModelHealthSnapshot(timeframe: Timeframe): ModelHealthSnapshot {
  return {
    timeframe,
    status: "LOADING",
    rationaleCodes: [],
    sampledSlippageActive: false,
    fundingModel: null,
    fundingEvents: null,
    fundingBpsPerEvent: null,
    fundingBps: null,
    message: null,
    updatedAt: null,
  };
}

function usePersistentState<T>(key: string, fallback: T): [T, (updater: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) {
        return fallback;
      }
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  });

  const update = (updater: T | ((prev: T) => T)) => {
    setState((prev) => {
      const next = typeof updater === "function" ? (updater as (prev: T) => T)(prev) : updater;
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // best effort persistence
      }
      return next;
    });
  };

  return [state, update];
}

function preferredTheme(): ThemeMode {
  return "dark";
}

function formatSigned(value: number, digits = 2): string {
  const abs = Math.abs(value).toFixed(digits);
  return `${value >= 0 ? "+" : "-"}${abs}`;
}

function parseCommissionPercentToBps(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed.length) {
    return null;
  }
  const normalized = trimmed.endsWith("%") ? trimmed.slice(0, -1).trim() : trimmed;
  if (!normalized.length) {
    return null;
  }
  const percentValue = Number.parseFloat(normalized);
  if (!Number.isFinite(percentValue) || percentValue < 0) {
    return null;
  }
  return percentValue * 100;
}

function formatMetricPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  const abs = Math.abs(value);
  if (abs >= 1_000) {
    return value.toFixed(0);
  }
  if (abs >= 100) {
    return value.toFixed(2);
  }
  if (abs >= 1) {
    return value.toFixed(3);
  }
  return value.toFixed(6);
}

function formatMetricPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatFundingRateBpsPerHour(
  ratePerFundingInterval: number | null | undefined,
  fundingIntervalSecs: number | null | undefined
): string {
  if (
    ratePerFundingInterval == null ||
    !Number.isFinite(ratePerFundingInterval) ||
    fundingIntervalSecs == null ||
    !Number.isFinite(fundingIntervalSecs) ||
    fundingIntervalSecs <= 0
  ) {
    return "--";
  }
  const hourlyScale = 3600 / fundingIntervalSecs;
  const bpsPerHour = ratePerFundingInterval * 10_000 * hourlyScale;
  return `${bpsPerHour >= 0 ? "+" : ""}${bpsPerHour.toFixed(2)} bps/hr`;
}

function formatSignedMetric(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  const abs = Math.abs(value).toFixed(digits);
  return `${value >= 0 ? "+" : "-"}${abs}`;
}

function formatUsdAxisValue(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}m`;
  }
  if (abs >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}k`;
  }
  return `$${value.toFixed(2)}`;
}

function scaleEquityForDisplay(
  values: number[],
  baseUsd = 100,
  deltaMultiplier = 110
): number[] {
  if (!values.length) {
    return values;
  }
  const anchor = values[0];
  return values.map((value) => baseUsd + (value - anchor) * deltaMultiplier);
}

function formatLocalDateTime(value: string | number | Date): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(date);
}

function formatLocalTime(value: string | number | Date): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(date);
}

function downloadJsonFile(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function useViewportHeightPx(): number {
  const [height, setHeight] = useState<number>(() => {
    if (typeof window === "undefined") {
      return 900;
    }
    return window.innerHeight;
  });

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const onResize = (): void => setHeight(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return height;
}

function derivePairLotSizes(
  hedgeRatio: number | null | undefined
): { leftSize: number; rightSize: number } {
  const sanitizedHedgeRatio =
    hedgeRatio != null && Number.isFinite(hedgeRatio) && hedgeRatio > 0
      ? Math.abs(hedgeRatio)
      : 1;
  return { leftSize: 1, rightSize: sanitizedHedgeRatio };
}

function formatOpenInterest(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}m`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}k`;
  }
  return value.toFixed(0);
}

function formatInstrumentLabel(instrument: string): string {
  return instrument.replace(/^PI_/, "").replace(/^PF_/, "");
}

function formatPairLabel(pairId: string): string {
  return pairId
    .split("__")
    .map((instrument) => formatInstrumentLabel(instrument))
    .join("/");
}

function marketMetricInstrumentCandidates(instrument: string): string[] {
  const trimmed = instrument.trim();
  if (!trimmed.length) {
    return [];
  }

  const candidates = [trimmed];
  if (trimmed.startsWith("PF_")) {
    candidates.push(`PI_${trimmed.slice(3)}`);
  } else if (trimmed.startsWith("PI_")) {
    candidates.push(`PF_${trimmed.slice(3)}`);
  } else {
    candidates.push(`PI_${trimmed}`);
    candidates.push(`PF_${trimmed}`);
  }
  return Array.from(new Set(candidates));
}

async function fetchMarketMetricsWithFallback(
  instrument: string
): Promise<MarketMetricsResponse> {
  const candidates = marketMetricInstrumentCandidates(instrument);
  let lastError: unknown = null;
  for (const candidate of candidates) {
    try {
      return await fetchMarketMetrics(candidate);
    } catch (error) {
      lastError = error;
    }
  }
  if (lastError instanceof Error) {
    throw lastError;
  }
  throw new Error(`No market metrics available for ${instrument}`);
}

function describeRationaleCode(code: string): string {
  const mapping: Record<string, string> = {
    BELOW_ENTRY_BAND: "Spread has not stretched far enough to trigger an entry.",
    AT_OR_BEYOND_STOP_BAND:
      "Spread is at or beyond the configured stop band, so new entries are blocked.",
    RETRACE_COOLDOWN_ACTIVE:
      "A recent stop breach triggered cooldown; entry re-arms only after 25% retrace from stop toward entry.",
    COST_GATE_BLOCKED: "Expected edge does not clear estimated fees, funding, and slippage.",
    NEGATIVE_EXPECTED_EDGE: "Expected edge is negative after cost adjustments.",
    NEGATIVE_EDGE: "Recent edge estimate is negative for this setup.",
    HEDGE_RATIO_UNSTABLE: "Hedge ratio stability is weak, so pair balancing is less reliable.",
    LOW_SAMPLE: "Recent sample size is limited, reducing confidence.",
    CHAMPION_DRIFT: "Best-performing model selection is drifting.",
    CHAMPION_DRIFT_BLOCKED: "Model drift guard is active, so entries are blocked.",
    PAIR_NOT_IN_PORTFOLIO_PLAN: "Pair is currently outside the advisory portfolio plan.",
    INSUFFICIENT_TRAINING_HISTORY: "Shadow ML history is still building and not used for approvals.",
    SLIPPAGE_SOURCE_SAMPLED:
      "Cost gate uses live sampled slippage estimates from bid/ask/index quotes.",
    SLIPPAGE_SOURCE_BOOTSTRAPPED:
      "Cost gate is temporarily using a warm-start sampled slippage checkpoint until live samples confirm it.",
    SLIPPAGE_DATA_WARMING:
      "Live slippage feed is still warming up; entry remains blocked until enough samples are collected.",
    SLIPPAGE_DATA_STALE:
      "Live slippage feed is stale; entry remains blocked until fresh quotes are restored.",
    SLIPPAGE_DATA_UNAVAILABLE:
      "Live slippage feed is unavailable; entry remains blocked in fail-closed mode.",
    SETUP_GATE_BLOCKED: "Setup conditions for entry are not currently satisfied.",
    TRADE_GATE_BLOCKED: "Combined setup/cost gate did not pass.",
  };
  return mapping[code] ?? code.replaceAll("_", " ").toLowerCase();
}

function explainPairActionability(
  selected: StrategyPairsCuesResponse["cues"][number] | undefined
): {
  headline: string;
  tone: "ok" | "bad" | "warn";
  details: string[];
  reasons: string[];
} {
  if (!selected) {
    return {
      headline: "No pair selected.",
      tone: "warn",
      details: ["Select a pair to view live entry blocking reasons."],
      reasons: [],
    };
  }

  const { cue, hedge_ratio_stability } = selected;
  const setupReasons = cue.setup_gate?.rationale_codes ?? cue.rationale_codes;
  const costReasons = cue.cost_gate.rationale_codes ?? [];
  const tradeGate = cue.trade_gate ?? {
    status: cue.cost_gate.status === "AVAILABLE" ? "AVAILABLE" : "UNAVAILABLE",
    pass: cue.actionable,
    blocked_by: cue.actionable ? "NONE" : "UNAVAILABLE",
    rationale_codes: cue.actionable
      ? []
      : Array.from(new Set([...setupReasons, ...costReasons])),
  };
  const tradeReasons = tradeGate.rationale_codes ?? [];
  const mergedReasons = Array.from(new Set([...setupReasons, ...costReasons, ...tradeReasons]));
  const costUnavailable = cue.cost_gate.status !== "AVAILABLE";
  const costBlocked =
    costUnavailable ||
    costReasons.includes("COST_GATE_BLOCKED") ||
    costReasons.includes("NEGATIVE_EXPECTED_EDGE") ||
    (cue.cost_gate.status === "AVAILABLE" && !cue.cost_gate.pass);

  const details: string[] = [];
  if (setupReasons.includes("BELOW_ENTRY_BAND")) {
    details.push(
      `Current spread z-score is ${cue.spread_z.toFixed(2)}, inside the entry trigger at ±${cue.entry_band.toFixed(2)}.`
    );
  }
  if (setupReasons.includes("AT_OR_BEYOND_STOP_BAND")) {
    details.push(
      `Current spread z-score is ${cue.spread_z.toFixed(2)}, at or beyond the stop level ±${cue.stop_band.toFixed(2)}; entries are disabled until it moves back inside stop limits.`
    );
  }
  if (setupReasons.includes("RETRACE_COOLDOWN_ACTIVE")) {
    const rearmLevel = cue.stop_band - (cue.stop_band - cue.entry_band) * 0.25;
    details.push(
      `Recent stop breach detected. New entries stay blocked until z-score retraces to ±${rearmLevel.toFixed(2)} (25% back from stop toward entry).`
    );
  }
  if (costUnavailable) {
    details.push("Cost economics are unavailable right now, so trading remains fail-closed.");
  } else if (costBlocked) {
    details.push(
      `Net edge is ${formatSigned(cue.cost_gate.net_edge_bps)}bp after costs, so the cost gate remains blocked.`
    );
  } else {
    details.push(
      `Net edge is ${formatSigned(cue.cost_gate.net_edge_bps)}bp after costs, so economics currently pass.`
    );
  }
  if (setupReasons.includes("HEDGE_RATIO_UNSTABLE")) {
    details.push(
      `Hedge ratio stability is ${(hedge_ratio_stability * 100).toFixed(1)}%, below preferred stability for neutral sizing.`
    );
  }
  if (setupReasons.includes("LOW_SAMPLE")) {
    details.push("Recent setup history is limited, so confidence is intentionally reduced.");
  }
  if (setupReasons.includes("CHAMPION_DRIFT_BLOCKED")) {
    details.push("Variant drift guard is active until model selection stabilizes.");
  }

  if (!details.length) {
    details.push(
      tradeGate.pass
        ? "Setup and cost gates are currently passing."
        : "At least one strategy or safety gate is currently blocking entry."
    );
  }

  if (tradeGate.pass) {
    return {
      headline: "Allowed: setup and cost economics are currently passing.",
      tone: "ok",
      details,
      reasons: mergedReasons,
    };
  }

  if (tradeGate.blocked_by === "SETUP" && setupReasons.includes("AT_OR_BEYOND_STOP_BAND")) {
    return {
      headline: "Blocked for now: spread is at/through stop level, so entry is disabled.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }
  if (tradeGate.blocked_by === "SETUP" && setupReasons.includes("RETRACE_COOLDOWN_ACTIVE")) {
    return {
      headline: "Blocked for now: waiting for 25% retrace after stop breach before re-entry.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }

  if (tradeGate.blocked_by === "SETUP" && setupReasons.includes("BELOW_ENTRY_BAND")) {
    return {
      headline: "Blocked for now: spread stretch is not yet at entry level.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }
  if (tradeGate.blocked_by === "COST") {
    return {
      headline: "Blocked for now: expected edge does not clear trade costs.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }
  if (tradeGate.blocked_by === "MULTIPLE") {
    return {
      headline: "Blocked for now: both setup conditions and cost economics are failing.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }
  if (tradeGate.blocked_by === "SETUP" && setupReasons.includes("HEDGE_RATIO_UNSTABLE")) {
    return {
      headline: "Blocked for now: hedge sizing is unstable for reliable spread neutrality.",
      tone: "bad",
      details,
      reasons: mergedReasons,
    };
  }

  return {
    headline: "Blocked for now: one or more strategy gates are not satisfied.",
    tone: "bad",
    details,
    reasons: mergedReasons,
  };
}

function toneFromStatus(status?: string): "ok" | "warn" | "bad" {
  if (status === "COMPLETE" || status === "OK") {
    return "ok";
  }
  if (status === "PARTIAL_BACKFILLED" || status === "STALE") {
    return "warn";
  }
  return "bad";
}

function formatMaintenanceStepLabel(stepKey: string): string {
  const mapping: Record<string, string> = {
    health: "Health checks",
    baseline_report: "Baseline report",
    candidate_apply_dry_run: "Candidate apply dry-run",
    candidate_apply_live: "Candidate apply live",
    candidate_report: "Candidate report",
    restore_original: "Restore original profile",
  };
  return mapping[stepKey] ?? stepKey.replaceAll("_", " ");
}

function buildSpreadLegs(
  leftInstrument: string,
  rightInstrument: string,
  direction: Exclude<DirectionHint, "NONE">,
  action: ExecutionAction
): SpreadLeg[] {
  const isEntry = action === "ENTRY";
  if (direction === "LONG_SPREAD") {
    return [
      { instrument: leftInstrument, side: isEntry ? "BUY" : "SELL" },
      { instrument: rightInstrument, side: isEntry ? "SELL" : "BUY" },
    ];
  }
  return [
    { instrument: leftInstrument, side: isEntry ? "SELL" : "BUY" },
    { instrument: rightInstrument, side: isEntry ? "BUY" : "SELL" },
  ];
}

function nowIso(): string {
  return new Date().toISOString();
}

function App(): JSX.Element {
  const viewportHeightPx = useViewportHeightPx();
  const tradeZChartHeight = useMemo(
    () => Math.round(clampNumber(viewportHeightPx * 0.44, 340, 560)),
    [viewportHeightPx]
  );
  const analyticsChartHeight = useMemo(
    () => Math.round(clampNumber(viewportHeightPx * 0.4, 320, 520)),
    [viewportHeightPx]
  );

  const [theme, setTheme] = usePersistentState<ThemeMode>("cp.theme", preferredTheme());
  const [page, setPage] = useState<PageId>("trade");
  const [timeframe, setTimeframe] = usePersistentState<Timeframe>("cp.timeframe", "1m");
  const [backtestExitMode, setBacktestExitMode] = usePersistentState<BacktestExitMode>(
    "cp.backtest_exit_mode",
    "mean_revert"
  );

  const [exchange, setExchange] = usePersistentState<string>("cp.exchange", "kraken_futures");
  const [accountId, setAccountId] = usePersistentState<string>("cp.account_id", "primary");
  const [operatorId, setOperatorId] = usePersistentState<string>("cp.operator", "operator-kevin");
  const [takerCommissionPct, setTakerCommissionPct] = usePersistentState<string>(
    "cp.taker_commission_pct",
    ""
  );
  const [apiKey, setApiKey] = useState<string>("");
  const [apiSecret, setApiSecret] = useState<string>("");
  const [apiPassphrase, setApiPassphrase] = useState<string>("");
  const [showApiSecrets, setShowApiSecrets] = useState<boolean>(false);
  const [uiAuthLoading, setUiAuthLoading] = useState<boolean>(true);
  const [uiAuthEnabled, setUiAuthEnabled] = useState<boolean>(false);
  const [uiUnlocked, setUiUnlocked] = useState<boolean>(false);
  const [uiPassword, setUiPassword] = useState<string>("");
  const [uiAuthError, setUiAuthError] = useState<string | null>(null);

  const [cuesResponse, setCuesResponse] = useState<StrategyPairsCuesResponse | null>(null);
  const [costResponse, setCostResponse] = useState<StrategyPairsCostGateResponse | null>(null);
  const [planResponse, setPlanResponse] = useState<StrategyPairsPortfolioPlanResponse | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [coreLoading, setCoreLoading] = useState(false);

  const [selectedPairId, setSelectedPairId] = usePersistentState<string>("cp.pair", "");

  const [killSwitch, setKillSwitch] = useState<KillSwitchState | null>(null);
  const [leftDecisionAllowed, setLeftDecisionAllowed] = useState<boolean>(false);
  const [rightDecisionAllowed, setRightDecisionAllowed] = useState<boolean>(false);
  const [reconcileResponse, setReconcileResponse] = useState<ReconcileResponse | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);

  const [leftIntegrity, setLeftIntegrity] = useState<IntegrityHistoryResponse | null>(null);
  const [rightIntegrity, setRightIntegrity] = useState<IntegrityHistoryResponse | null>(null);

  const [zSeries, setZSeries] = useState<number[]>([]);
  const [zTimestamps, setZTimestamps] = useState<string[]>([]);
  const [equitySeries, setEquitySeries] = useState<number[]>([]);
  const [equityTimestamps, setEquityTimestamps] = useState<string[]>([]);
  const [zMarkers, setZMarkers] = useState<ChartMarker[]>([]);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [paperTrades, setPaperTrades] = useState<StrategyPairsPaperTradesResponse | null>(null);
  const [paperTradesError, setPaperTradesError] = useState<string | null>(null);
  const [paperTradesLoading, setPaperTradesLoading] = useState(false);
  const [researchEntryZ, setResearchEntryZ] = usePersistentState<string>(
    "cp.research.entry_z",
    "1.8"
  );
  const [researchExitZ, setResearchExitZ] = usePersistentState<string>(
    "cp.research.exit_z",
    "0.6"
  );
  const [researchStopZ, setResearchStopZ] = usePersistentState<string>(
    "cp.research.stop_z",
    "3.2"
  );
  const [researchLookbackBars, setResearchLookbackBars] = usePersistentState<string>(
    "cp.research.lookback_bars",
    "220"
  );
  const [researchHours, setResearchHours] = usePersistentState<string>(
    "cp.research.hours",
    "720"
  );
  const [researchLimit, setResearchLimit] = usePersistentState<string>(
    "cp.research.limit",
    "50"
  );
  const [researchMaxCombinations, setResearchMaxCombinations] = usePersistentState<string>(
    "cp.research.max_combinations",
    "20000"
  );
  const [researchZMethod, setResearchZMethod] = usePersistentState<StrategyZMethod>(
    "cp.research.z_method",
    "ROBUST_Z"
  );
  const [expectancyResult, setExpectancyResult] =
    useState<StrategyPairsExpectancyResponse | null>(null);
  const [expectancyLoading, setExpectancyLoading] = useState(false);
  const [expectancyError, setExpectancyError] = useState<string | null>(null);
  const [replayResult, setReplayResult] = useState<StrategyPairsReplayTradesResponse | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [researchSweepResult, setResearchSweepResult] =
    useState<StrategyPairsResearchSweepResponse | null>(null);
  const [researchSweepLoading, setResearchSweepLoading] = useState(false);
  const [researchSweepError, setResearchSweepError] = useState<string | null>(null);
  const [headerLeftMetrics, setHeaderLeftMetrics] = useState<MarketMetricsResponse | null>(null);
  const [headerRightMetrics, setHeaderRightMetrics] = useState<MarketMetricsResponse | null>(null);
  const [headerMetricsError, setHeaderMetricsError] = useState<string | null>(null);
  const [maintenanceLatest, setMaintenanceLatest] =
    useState<StrategyMaintenanceLatestResponse | null>(null);
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null);
  const [maintenanceActionLoading, setMaintenanceActionLoading] = useState(false);
  const [maintenanceActionMessage, setMaintenanceActionMessage] = useState<string | null>(null);
  const [historyStats, setHistoryStats] =
    useState<StrategyPairsOpportunityHistoryStatsResponse | null>(null);
  const [historyStatsLoading, setHistoryStatsLoading] = useState(false);
  const [historyStatsError, setHistoryStatsError] = useState<string | null>(null);
  const [modelHealthByTimeframe, setModelHealthByTimeframe] = useState<
    Record<Timeframe, ModelHealthSnapshot>
  >({
    "1m": loadingModelHealthSnapshot("1m"),
    "15m": loadingModelHealthSnapshot("15m"),
    "1h": loadingModelHealthSnapshot("1h"),
  });
  const [modelHealthLoading, setModelHealthLoading] = useState(false);
  const [modelHealthError, setModelHealthError] = useState<string | null>(null);

  const [stopMethod, setStopMethod] = useState<"Z-Score" | "Dollar" | "Percent">("Z-Score");
  const [stopValue, setStopValue] = useState<string>("3.2");
  const [altStop, setAltStop] = useState<string>("150");
  const [spreadSize, setSpreadSize] = useState<string>("1.25");
  const [operatorConfirmed, setOperatorConfirmed] = useState<boolean>(false);
  const [tradeMessage, setTradeMessage] = useState<string>("No trade submitted yet.");
  const [submitting, setSubmitting] = useState(false);

  const [positions, setPositions] = useState<Record<string, SpreadPosition>>({});
  const [timelineByPair, setTimelineByPair] = usePersistentState<Record<string, TimelineEvent[]>>(
    "cp.timeline",
    {}
  );
  const [intentHistoryByPair, setIntentHistoryByPair] = useState<
    Record<string, OrderIntentHistoryResponse[]>
  >({});

  const selectedCueRow = useMemo(() => {
    if (!cuesResponse?.cues.length) {
      return null;
    }
    return (
      cuesResponse.cues.find((entry) => entry.cue.pair_id === selectedPairId) ?? cuesResponse.cues[0]
    );
  }, [cuesResponse, selectedPairId]);

  useEffect(() => {
    if (selectedCueRow && selectedPairId !== selectedCueRow.cue.pair_id) {
      setSelectedPairId(selectedCueRow.cue.pair_id);
    }
  }, [selectedCueRow, selectedPairId, setSelectedPairId]);

  const currentPairId = selectedCueRow?.cue.pair_id ?? "";
  const currentPosition =
    (currentPairId ? positions[currentPairId] : undefined) ?? emptyPosition(nowIso());
  const currentTimeline = timelineByPair[currentPairId] ?? [];
  const currentIntentHistory = intentHistoryByPair[currentPairId] ?? [];
  const persistentExecutionMarkers = useMemo(
    () =>
      buildExecutionMarkers({
        zValues: zSeries,
        zTimestamps,
        histories: currentIntentHistory,
      }),
    [zSeries, zTimestamps, currentIntentHistory]
  );
  const tradeChartMarkers = useMemo(
    () => [...zMarkers, ...persistentExecutionMarkers],
    [zMarkers, persistentExecutionMarkers]
  );
  const activeTradeAnchor = useMemo(
    () =>
      buildActiveTradeAnchor({
        currentPosition,
        zValues: zSeries,
        histories: currentIntentHistory,
      }),
    [currentPosition, zSeries, currentIntentHistory]
  );
  const uiAccessGranted = !uiAuthLoading && (!uiAuthEnabled || uiUnlocked);

  useEffect(() => {
    let cancelled = false;
    const refreshUiAccessStatus = async (): Promise<void> => {
      setUiAuthLoading(true);
      try {
        const status = await fetchStrategyUiAuthStatus();
        if (cancelled) {
          return;
        }
        const storedUnlock = window.sessionStorage.getItem("cp.ui.unlocked") === "true";
        setUiAuthEnabled(status.enabled);
        setUiUnlocked(!status.enabled || storedUnlock);
        setUiAuthError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setUiAuthEnabled(true);
        setUiUnlocked(false);
        setUiAuthError(
          `Unable to verify access requirement: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      } finally {
        if (!cancelled) {
          setUiAuthLoading(false);
        }
      }
    };

    void refreshUiAccessStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const stopValueNumber = Number.parseFloat(stopValue);
  const spreadSizeNumber = Number.parseFloat(spreadSize);
  const takerFeeBpsOverride = useMemo(
    () => parseCommissionPercentToBps(takerCommissionPct),
    [takerCommissionPct]
  );
  const researchEntryZNumber = Number.parseFloat(researchEntryZ);
  const researchExitZNumber = Number.parseFloat(researchExitZ);
  const researchStopZNumber = Number.parseFloat(researchStopZ);
  const researchLookbackBarsNumber = Number.parseInt(researchLookbackBars, 10);
  const researchHoursNumber = Number.parseInt(researchHours, 10);
  const researchLimitNumber = Number.parseInt(researchLimit, 10);
  const researchMaxCombinationsNumber = Number.parseInt(researchMaxCombinations, 10);
  const researchInputsValid =
    Number.isFinite(researchEntryZNumber) &&
    Number.isFinite(researchExitZNumber) &&
    Number.isFinite(researchStopZNumber) &&
    Number.isFinite(researchLookbackBarsNumber) &&
    Number.isFinite(researchHoursNumber) &&
    Number.isFinite(researchLimitNumber) &&
    Number.isFinite(researchMaxCombinationsNumber) &&
    researchEntryZNumber > 0 &&
    researchExitZNumber >= 0 &&
    researchStopZNumber > researchEntryZNumber &&
    researchLookbackBarsNumber > 0 &&
    researchHoursNumber > 0 &&
    researchLimitNumber > 0 &&
    researchMaxCombinationsNumber > 0;

  const stopConfigured = isStopConfigured(stopMethod, stopValueNumber);
  const gateState = useMemo(
    () => ({
      killSwitchActive: killSwitch?.active ?? true,
      leftAllowed: leftDecisionAllowed,
      rightAllowed: rightDecisionAllowed,
      reconcileOk: reconcileResponse?.reconcile?.status === "OK",
    }),
    [killSwitch?.active, leftDecisionAllowed, rightDecisionAllowed, reconcileResponse]
  );

  const baseEntryGuard = {
    stopConfigured,
    operatorConfirmed,
    operatorId,
    spreadSize: spreadSizeNumber,
    gateState,
  };

  const canLongEntry = isEntryAllowed(baseEntryGuard);
  const canShortEntry = isEntryAllowed(baseEntryGuard);
  const canAddExposure = isAddAllowed(currentPosition, baseEntryGuard);
  const canReduceExposure = isReduceAllowed(
    currentPosition,
    operatorConfirmed,
    operatorId,
    spreadSizeNumber
  );
  const canCloseSpread = isCloseAllowed(currentPosition);

  const gateSafe = isGateSafe(gateState);
  const latestLeftIntegrity = leftIntegrity?.rows?.[0] ?? null;
  const latestRightIntegrity = rightIntegrity?.rows?.[0] ?? null;
  const startupStatus = useMemo(() => {
    if (coreLoading) {
      return {
        tone: "warn" as const,
        text: "Market data is syncing. Backfill is running before trading gates open.",
      };
    }
    if (coreError) {
      return {
        tone: "bad" as const,
        text: "Live strategy data is unavailable. Fail-closed mode is active.",
      };
    }
    if (!selectedCueRow || !latestLeftIntegrity || !latestRightIntegrity) {
      return {
        tone: "warn" as const,
        text: "Waiting for first integrity checks and backfill confirmation.",
      };
    }

    const readyStatuses = new Set(["COMPLETE", "PARTIAL_BACKFILLED"]);
    const leftReady =
      readyStatuses.has(latestLeftIntegrity.status) && latestLeftIntegrity.coverage_pct >= 99.5;
    const rightReady =
      readyStatuses.has(latestRightIntegrity.status) && latestRightIntegrity.coverage_pct >= 99.5;
    if (leftReady && rightReady) {
      return {
        tone: "ok" as const,
        text: `Data sync complete. ${formatInstrumentLabel(
          selectedCueRow.cue.left_instrument
        )} ${latestLeftIntegrity.coverage_pct.toFixed(2)}%, ${formatInstrumentLabel(
          selectedCueRow.cue.right_instrument
        )} ${latestRightIntegrity.coverage_pct.toFixed(2)}%.`,
      };
    }

    return {
      tone: "warn" as const,
      text: `Backfill in progress. ${formatInstrumentLabel(
        selectedCueRow.cue.left_instrument
      )} ${latestLeftIntegrity.coverage_pct.toFixed(2)}% (${latestLeftIntegrity.status}), ${formatInstrumentLabel(
        selectedCueRow.cue.right_instrument
      )} ${latestRightIntegrity.coverage_pct.toFixed(2)}% (${latestRightIntegrity.status}).`,
    };
  }, [coreLoading, coreError, latestLeftIntegrity, latestRightIntegrity, selectedCueRow]);

  const refreshPositions = async (): Promise<void> => {
    const response = await fetchExecutionPortfolioPositions(exchange, accountId);
    const next: Record<string, SpreadPosition> = {};
    for (const row of response.positions) {
      next[row.pair_id] = {
        direction: row.direction,
        totalSize: row.total_size,
        avgEntryZ: row.avg_entry_z,
        updatedAt: row.updated_at,
      };
    }
    setPositions(next);
  };

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    let cancelled = false;
    let inFlight = false;

    const runCoreRefresh = async (firstLoad = false): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      if (firstLoad) {
        setCoreLoading(true);
      }
      setCoreError(null);

      try {
        const cuesRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyCues(timeframe, 20)
            : fetchStrategyCues(timeframe, 20, takerFeeBpsOverride);
        const costGatesRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyCostGates(timeframe)
            : fetchStrategyCostGates(timeframe, takerFeeBpsOverride);
        const planRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyPortfolioPlan(timeframe)
            : fetchStrategyPortfolioPlan(timeframe, takerFeeBpsOverride);
        const [cues, costs, plan] = await Promise.all([
          cuesRequest,
          costGatesRequest,
          planRequest,
        ]);
        if (cancelled) {
          return;
        }
        setCuesResponse(cues);
        setCostResponse(costs);
        setPlanResponse(plan);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setCoreError(
          `Unable to load strategy data from live services: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
        setCuesResponse(null);
        setCostResponse(null);
        setPlanResponse(null);
      } finally {
        if (!cancelled && firstLoad) {
          setCoreLoading(false);
        }
        inFlight = false;
      }
    };

    void runCoreRefresh(true);
    const intervalId = window.setInterval(() => {
      void runCoreRefresh(false);
    }, analyticsRefreshMs(timeframe));

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [timeframe, uiAccessGranted, takerFeeBpsOverride]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    if (!selectedCueRow) {
      return;
    }

    let cancelled = false;
    setGateError(null);

    Promise.all([
      fetchKillSwitchState(),
      fetchExecutionDecision(selectedCueRow.cue.left_instrument, timeframe),
      fetchExecutionDecision(selectedCueRow.cue.right_instrument, timeframe),
      fetchReconcile(exchange, accountId),
    ])
      .then(([kill, left, right, reconcile]) => {
        if (cancelled) {
          return;
        }
        setKillSwitch(kill);
        setLeftDecisionAllowed(left.decision === "ALLOWED");
        setRightDecisionAllowed(right.decision === "ALLOWED");
        setReconcileResponse(reconcile);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setGateError(
          `Gate state unavailable. UI is fail-closed: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
        setKillSwitch({ active: true, reason: "unknown", updated_at: nowIso() });
        setLeftDecisionAllowed(false);
        setRightDecisionAllowed(false);
        setReconcileResponse({ reconcile: null });
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCueRow, timeframe, exchange, accountId, uiAccessGranted]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    let cancelled = false;
    void refreshPositions().catch(() => {
      if (!cancelled) {
        setPositions({});
      }
    });
    const intervalId = window.setInterval(() => {
      void refreshPositions().catch(() => {
        if (!cancelled) {
          setPositions({});
        }
      });
    }, 10_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [exchange, accountId, uiAccessGranted]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    if (!selectedCueRow) {
      return;
    }

    let cancelled = false;
    Promise.all([
      fetchIntegrityHistory(selectedCueRow.cue.left_instrument, timeframe, 50),
      fetchIntegrityHistory(selectedCueRow.cue.right_instrument, timeframe, 50),
    ])
      .then(([left, right]) => {
        if (cancelled) {
          return;
        }
        setLeftIntegrity(left);
        setRightIntegrity(right);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setLeftIntegrity(null);
        setRightIntegrity(null);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCueRow, timeframe, uiAccessGranted]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    if (!selectedCueRow) {
      setZSeries([]);
      setZTimestamps([]);
      setEquitySeries([]);
      setEquityTimestamps([]);
      setZMarkers([]);
      setAnalyticsError("No pair selected.");
      setAnalyticsLoading(false);
      return;
    }

    let cancelled = false;
    let inFlight = false;
    setAnalyticsLoading(true);

    const runAnalyticsRefresh = async (firstLoad = false): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      if (firstLoad) {
        setAnalyticsLoading(true);
      }

      const bars = timeframe === "1m" ? 300 : timeframe === "15m" ? 280 : 220;

      try {
        const liveZRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyLiveZ(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
                undefined,
                backtestExitMode
              )
            : fetchStrategyLiveZ(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
                takerFeeBpsOverride,
                backtestExitMode
              );
        const backtestRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyBacktest(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
                undefined,
                backtestExitMode
              )
            : fetchStrategyBacktest(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
                takerFeeBpsOverride,
                backtestExitMode
              );
        const [liveZ, backtest] = await Promise.all([
          liveZRequest,
          backtestRequest,
        ]);

        if (cancelled) {
          return;
        }

        if (liveZ.points.length < 20 || backtest.points.length < 20) {
          setAnalyticsError("Insufficient aligned data for analytics charts.");
          setZSeries([]);
          setZTimestamps([]);
          setEquitySeries([]);
          setEquityTimestamps([]);
          setZMarkers([]);
          return;
        }

        const zValues = liveZ.points.map((point) => point.z);
        const zTimes = liveZ.points.map((point) => point.ts);
        const equity = backtest.points.map((point) => point.equity);
        const equityTimes = backtest.points.map((point) => point.ts);
        const markers = liveZ.markers.filter((marker) =>
          marker.kind === "entry" || marker.kind === "exit" || marker.kind === "stop"
        );

        setZSeries(zValues);
        setZTimestamps(zTimes);
        setZMarkers(markers);
        setEquitySeries(equity);
        setEquityTimestamps(equityTimes);
        setAnalyticsError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setAnalyticsError(
          `Analytics unavailable from strategy services: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      } finally {
        if (!cancelled && firstLoad) {
          setAnalyticsLoading(false);
        }
        inFlight = false;
      }
    };

    void runAnalyticsRefresh(true);
    const refreshIntervalId = window.setInterval(() => {
      void runAnalyticsRefresh(false);
    }, analyticsRefreshMs(timeframe));

    return () => {
      cancelled = true;
      window.clearInterval(refreshIntervalId);
    };
  }, [selectedCueRow, timeframe, uiAccessGranted, takerFeeBpsOverride, backtestExitMode]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    if (!selectedCueRow) {
      setPaperTrades(null);
      setPaperTradesError("No pair selected.");
      setPaperTradesLoading(false);
      return;
    }

    let cancelled = false;
    let inFlight = false;
    setPaperTradesLoading(true);

    const runPaperTradesRefresh = async (firstLoad = false): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      if (firstLoad) {
        setPaperTradesLoading(true);
      }
      try {
        const response = await fetchStrategyPaperTrades(
          timeframe,
          selectedCueRow.cue.pair_id,
          720,
          24,
          backtestExitMode
        );
        if (cancelled) {
          return;
        }
        setPaperTrades(response);
        setPaperTradesError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setPaperTrades(null);
        setPaperTradesError(
          `Paper-trade history unavailable: ${error instanceof Error ? error.message : String(error)}`
        );
      } finally {
        if (!cancelled && firstLoad) {
          setPaperTradesLoading(false);
        }
        inFlight = false;
      }
    };

    void runPaperTradesRefresh(true);
    const intervalId = window.setInterval(() => {
      void runPaperTradesRefresh(false);
    }, analyticsRefreshMs(timeframe));

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedCueRow, timeframe, backtestExitMode, uiAccessGranted]);

  const refreshMaintenanceReport = useCallback(async (firstLoad = false): Promise<void> => {
    if (firstLoad) {
      setMaintenanceLoading(true);
    }
    try {
      const response = await fetchStrategyMaintenanceLatest();
      setMaintenanceLatest(response);
      setMaintenanceError(null);
    } catch (error) {
      setMaintenanceLatest(null);
      setMaintenanceError(
        `Maintenance report unavailable: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      if (firstLoad) {
        setMaintenanceLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    void refreshMaintenanceReport(true);
    const intervalId = window.setInterval(() => {
      void refreshMaintenanceReport(false);
    }, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [refreshMaintenanceReport, uiAccessGranted]);

  const refreshHistoryStats = useCallback(async (firstLoad = false): Promise<void> => {
    if (firstLoad) {
      setHistoryStatsLoading(true);
    }
    try {
      const response = await fetchStrategyOpportunityHistoryStats();
      setHistoryStats(response);
      setHistoryStatsError(null);
    } catch (error) {
      setHistoryStats(null);
      setHistoryStatsError(
        `Opportunity history stats unavailable: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      if (firstLoad) {
        setHistoryStatsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    void refreshHistoryStats(true);
    const intervalId = window.setInterval(() => {
      void refreshHistoryStats(false);
    }, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [refreshHistoryStats, uiAccessGranted]);

  const refreshModelHealth = useCallback(async (firstLoad = false): Promise<void> => {
    if (firstLoad) {
      setModelHealthLoading(true);
    }
    try {
      const responses = await Promise.all(
        TIMEFRAMES.map(async (tf) => {
          const response =
            takerFeeBpsOverride == null
              ? await fetchStrategyCues(tf, 1)
              : await fetchStrategyCues(tf, 1, takerFeeBpsOverride);
          return { timeframe: tf, response };
        })
      );

      const next: Record<Timeframe, ModelHealthSnapshot> = {
        "1m": loadingModelHealthSnapshot("1m"),
        "15m": loadingModelHealthSnapshot("15m"),
        "1h": loadingModelHealthSnapshot("1h"),
      };
      const updatedAt = nowIso();

      for (const item of responses) {
        const selectedCue = item.response.cues[0]?.cue;
        if (!selectedCue) {
          next[item.timeframe] = {
            timeframe: item.timeframe,
            status: "NO_CUES",
            rationaleCodes: [],
            sampledSlippageActive: false,
            fundingModel: null,
            fundingEvents: null,
            fundingBpsPerEvent: null,
            fundingBps: null,
            message: "No cues returned.",
            updatedAt,
          };
          continue;
        }
        const costGate = selectedCue.cost_gate;
        const rationaleCodes = costGate.rationale_codes ?? [];
        next[item.timeframe] = {
          timeframe: item.timeframe,
          status: costGate.status === "AVAILABLE" ? "AVAILABLE" : "UNAVAILABLE",
          rationaleCodes,
          sampledSlippageActive:
            rationaleCodes.includes("SLIPPAGE_SOURCE_SAMPLED") ||
            rationaleCodes.includes("SLIPPAGE_SOURCE_BOOTSTRAPPED"),
          fundingModel: costGate.funding_model ?? null,
          fundingEvents: costGate.funding_events ?? null,
          fundingBpsPerEvent: costGate.funding_bps_per_event ?? null,
          fundingBps: costGate.funding_bps ?? null,
          message: null,
          updatedAt,
        };
      }
      setModelHealthByTimeframe(next);
      setModelHealthError(null);
    } catch (error) {
      setModelHealthError(
        `Model health unavailable: ${error instanceof Error ? error.message : String(error)}`
      );
      const failedAt = nowIso();
      setModelHealthByTimeframe((prev) => {
        const next = { ...prev };
        for (const tf of TIMEFRAMES) {
          next[tf] = {
            ...next[tf],
            status: "ERROR",
            message: "Unable to fetch cues.",
            updatedAt: failedAt,
          };
        }
        return next;
      });
    } finally {
      if (firstLoad) {
        setModelHealthLoading(false);
      }
    }
  }, [takerFeeBpsOverride]);

  useEffect(() => {
    if (!uiAccessGranted || page !== "maintenance") {
      return;
    }
    void refreshModelHealth(true);
    const intervalId = window.setInterval(() => {
      void refreshModelHealth(false);
    }, 60_000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [page, refreshModelHealth, uiAccessGranted]);

  const executeMaintenanceAction = useCallback(
    async (action: "PROMOTE" | "REVERT"): Promise<StrategyMaintenanceActionResponse> => {
      setMaintenanceActionLoading(true);
      setMaintenanceActionMessage(null);
      try {
        const response = await runStrategyMaintenanceAction({
          action,
          operator_id: operatorId,
          confirm: true,
        });
        const queueStatus = String(response.report?.status ?? "").toUpperCase();
        if (response.pass) {
          if (queueStatus === "QUEUED") {
            setMaintenanceActionMessage(
              `${response.action} queued successfully. Host worker will execute it shortly and publish the action report.`
            );
          } else {
            setMaintenanceActionMessage(
              `${response.action} completed successfully. Action report is available for download.`
            );
          }
        } else {
          setMaintenanceActionMessage(
            response.error ??
              `${response.action} completed with errors. Review the action report before retrying.`
          );
        }
        await refreshMaintenanceReport(false);
        await refreshHistoryStats(false);
        return response;
      } finally {
        setMaintenanceActionLoading(false);
      }
    },
    [operatorId, refreshMaintenanceReport, refreshHistoryStats]
  );

  useEffect(() => {
    setExpectancyResult(null);
    setReplayResult(null);
    setResearchSweepResult(null);
    setExpectancyError(null);
    setReplayError(null);
    setResearchSweepError(null);
  }, [currentPairId, timeframe, backtestExitMode]);

  const runExpectancyResearch = useCallback(async (): Promise<void> => {
    if (!selectedCueRow) {
      setExpectancyError("No pair selected.");
      return;
    }
    if (!researchInputsValid) {
      setExpectancyError("Research inputs are invalid.");
      return;
    }
    setExpectancyLoading(true);
    setExpectancyError(null);
    try {
      const response = await fetchStrategyExpectancy(
        timeframe,
        selectedCueRow.cue.pair_id,
        researchEntryZNumber,
        researchExitZNumber,
        researchStopZNumber,
        researchZMethod,
        researchLookbackBarsNumber
      );
      setExpectancyResult(response);
    } catch (error) {
      setExpectancyResult(null);
      setExpectancyError(
        `Expectancy query failed: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      setExpectancyLoading(false);
    }
  }, [
    researchEntryZNumber,
    researchExitZNumber,
    researchInputsValid,
    researchLookbackBarsNumber,
    researchStopZNumber,
    researchZMethod,
    selectedCueRow,
    timeframe,
  ]);

  const runReplayResearch = useCallback(async (): Promise<void> => {
    if (!selectedCueRow) {
      setReplayError("No pair selected.");
      return;
    }
    if (!researchInputsValid) {
      setReplayError("Research inputs are invalid.");
      return;
    }
    setReplayLoading(true);
    setReplayError(null);
    try {
      const response = await fetchStrategyReplayTrades(
        timeframe,
        selectedCueRow.cue.pair_id,
        researchHoursNumber,
        researchLimitNumber,
        backtestExitMode,
        researchEntryZNumber,
        researchExitZNumber,
        researchStopZNumber,
        researchZMethod,
        researchLookbackBarsNumber
      );
      setReplayResult(response);
    } catch (error) {
      setReplayResult(null);
      setReplayError(
        `Replay query failed: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      setReplayLoading(false);
    }
  }, [
    backtestExitMode,
    researchEntryZNumber,
    researchExitZNumber,
    researchHoursNumber,
    researchInputsValid,
    researchLimitNumber,
    researchLookbackBarsNumber,
    researchStopZNumber,
    researchZMethod,
    selectedCueRow,
    timeframe,
  ]);

  const runResearchSweep = useCallback(async (dryRun: boolean): Promise<void> => {
    if (!selectedCueRow) {
      setResearchSweepError("No pair selected.");
      return;
    }
    if (!researchInputsValid) {
      setResearchSweepError("Research inputs are invalid.");
      return;
    }
    setResearchSweepLoading(true);
    setResearchSweepError(null);
    try {
      const response = await runStrategyResearchSweep({
        timeframes: [timeframe],
        pair_ids: [selectedCueRow.cue.pair_id],
        entry_z_grid: [researchEntryZNumber],
        exit_z_grid: [researchExitZNumber],
        stop_z_grid: [researchStopZNumber],
        z_methods: [researchZMethod],
        lookback_bars_grid: [researchLookbackBarsNumber],
        max_combinations: researchMaxCombinationsNumber,
        dry_run: dryRun,
      });
      setResearchSweepResult(response);
    } catch (error) {
      setResearchSweepResult(null);
      setResearchSweepError(
        `Research sweep failed: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      setResearchSweepLoading(false);
    }
  }, [
    researchEntryZNumber,
    researchExitZNumber,
    researchInputsValid,
    researchLookbackBarsNumber,
    researchMaxCombinationsNumber,
    researchStopZNumber,
    researchZMethod,
    selectedCueRow,
    timeframe,
  ]);

  const applyCueBandsToResearch = useCallback((): void => {
    if (!selectedCueRow) {
      return;
    }
    setResearchEntryZ(selectedCueRow.cue.entry_band.toFixed(2));
    setResearchExitZ(selectedCueRow.cue.exit_band.toFixed(2));
    setResearchStopZ(selectedCueRow.cue.stop_band.toFixed(2));
  }, [selectedCueRow, setResearchEntryZ, setResearchExitZ, setResearchStopZ]);

  const downloadExpectancyResult = useCallback((): void => {
    if (!expectancyResult) {
      return;
    }
    downloadJsonFile(
      `expectancy-${expectancyResult.timeframe}-${expectancyResult.pair_id}-${Date.now()}.json`,
      expectancyResult
    );
  }, [expectancyResult]);

  const downloadReplayResult = useCallback((): void => {
    if (!replayResult) {
      return;
    }
    downloadJsonFile(
      `replay-trades-${replayResult.timeframe}-${replayResult.pair_id}-${Date.now()}.json`,
      replayResult
    );
  }, [replayResult]);

  const downloadResearchSweepResult = useCallback((): void => {
    if (!researchSweepResult) {
      return;
    }
    downloadJsonFile(`research-sweep-${researchSweepResult.request_id}.json`, researchSweepResult);
  }, [researchSweepResult]);

  const headerLeftInstrument = selectedCueRow?.cue.left_instrument ?? "PF_XBTUSD";
  const headerRightInstrument = selectedCueRow?.cue.right_instrument ?? "PF_ETHUSD";
  const headerLeftLabel = formatInstrumentLabel(headerLeftInstrument);
  const headerRightLabel = formatInstrumentLabel(headerRightInstrument);
  const headerHedgeRatio = selectedCueRow?.hedge_ratio ?? 1;
  const directionHint = selectedCueRow?.cue.direction_hint ?? "NONE";
  const leftBid = headerLeftMetrics?.bid ?? headerLeftMetrics?.mark ?? null;
  const leftAsk = headerLeftMetrics?.ask ?? headerLeftMetrics?.mark ?? null;
  const rightBid = headerRightMetrics?.bid ?? headerRightMetrics?.mark ?? null;
  const rightAsk = headerRightMetrics?.ask ?? headerRightMetrics?.mark ?? null;
  const leftIndex = headerLeftMetrics?.index ?? headerLeftMetrics?.mark ?? null;
  const rightIndex = headerRightMetrics?.index ?? headerRightMetrics?.mark ?? null;
  const spreadPrice =
    leftBid != null &&
    leftAsk != null &&
    rightBid != null &&
    rightAsk != null &&
    leftIndex != null &&
    rightIndex != null
      ? directionHint === "LONG_SPREAD"
        ? leftAsk - headerHedgeRatio * rightBid
        : directionHint === "SHORT_SPREAD"
          ? leftBid - headerHedgeRatio * rightAsk
          : leftIndex - headerHedgeRatio * rightIndex
      : null;
  const spreadFundingRate =
    headerLeftMetrics && headerRightMetrics
      ? headerLeftMetrics.funding_rate - headerHedgeRatio * headerRightMetrics.funding_rate
      : null;
  const spreadFundingIntervalSecs =
    headerLeftMetrics?.funding_interval_secs ??
    headerRightMetrics?.funding_interval_secs ??
    null;
  const pairLotSizes = derivePairLotSizes(headerHedgeRatio);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    let cancelled = false;

    const refreshMetrics = async (): Promise<void> => {
      const [leftResult, rightResult] = await Promise.allSettled([
        fetchMarketMetricsWithFallback(headerLeftInstrument),
        fetchMarketMetricsWithFallback(headerRightInstrument),
      ]);
      if (cancelled) {
        return;
      }

      const nextLeft = leftResult.status === "fulfilled" ? leftResult.value : null;
      const nextRight = rightResult.status === "fulfilled" ? rightResult.value : null;
      setHeaderLeftMetrics(nextLeft);
      setHeaderRightMetrics(nextRight);

      const errors: string[] = [];
      if (leftResult.status === "rejected") {
        errors.push(
          `${headerLeftLabel}: ${
            leftResult.reason instanceof Error ? leftResult.reason.message : String(leftResult.reason)
          }`
        );
      }
      if (rightResult.status === "rejected") {
        errors.push(
          `${headerRightLabel}: ${
            rightResult.reason instanceof Error
              ? rightResult.reason.message
              : String(rightResult.reason)
          }`
        );
      }
      setHeaderMetricsError(errors.length ? `Live metrics partial failure: ${errors.join(" | ")}` : null);
    };

    void refreshMetrics();
    const intervalId = window.setInterval(() => {
      void refreshMetrics();
    }, 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    headerLeftInstrument,
    headerRightInstrument,
    headerLeftLabel,
    headerRightLabel,
    uiAccessGranted,
  ]);

  const addTimelineEvent = (pairId: string, event: TimelineEvent): void => {
    setTimelineByPair((prev) => {
      const current = prev[pairId] ?? [];
      return {
        ...prev,
        [pairId]: [event, ...current].slice(0, 40),
      };
    });
  };

  const upsertIntentHistories = (
    pairId: string,
    histories: OrderIntentHistoryResponse[]
  ): void => {
    if (!histories.length) {
      return;
    }
    setIntentHistoryByPair((prev) => {
      const existing = prev[pairId] ?? [];
      const byKey = new Map<string, OrderIntentHistoryResponse>();
      for (const item of existing) {
        byKey.set(item.idempotency_key, item);
      }
      for (const item of histories) {
        byKey.set(item.idempotency_key, item);
      }
      const merged = Array.from(byKey.values()).sort((a, b) => {
        const left = Date.parse(a.intent.evaluated_at);
        const right = Date.parse(b.intent.evaluated_at);
        return right - left;
      });
      return {
        ...prev,
        [pairId]: merged.slice(0, 30),
      };
    });
  };

  const executeTradeCommand = async (command: TradeCommand): Promise<void> => {
    if (!selectedCueRow) {
      setTradeMessage("No selected pair.");
      return;
    }

    const now = nowIso();
    const pairId = selectedCueRow.cue.pair_id;
    const current = positions[pairId] ?? emptyPosition(now);
    const currentZ = selectedCueRow.cue.spread_z;

    let direction: Exclude<DirectionHint, "NONE">;
    let action: ExecutionAction;
    let qty = spreadSizeNumber;

    if (!Number.isFinite(spreadSizeNumber) || spreadSizeNumber <= 0) {
      setTradeMessage("Spread size must be > 0.");
      return;
    }

    if (command === "long-entry") {
      direction = "LONG_SPREAD";
      action = "ENTRY";
    } else if (command === "short-entry") {
      direction = "SHORT_SPREAD";
      action = "ENTRY";
    } else if (command === "add-exposure") {
      if (current.direction === "NONE") {
        setTradeMessage("No open spread to add exposure to.");
        return;
      }
      direction = current.direction;
      action = "ENTRY";
    } else if (command === "reduce-exposure") {
      if (current.direction === "NONE" || current.totalSize <= 0) {
        setTradeMessage("No open spread to reduce.");
        return;
      }
      direction = current.direction;
      action = "EXIT";
      qty = Math.min(spreadSizeNumber, current.totalSize);
    } else {
      if (current.direction === "NONE" || current.totalSize <= 0) {
        setTradeMessage("No open spread to close.");
        return;
      }
      direction = current.direction;
      action = "EMERGENCY_STOP_CLOSE";
      qty = current.totalSize;
    }

    const legs = buildSpreadLegs(
      selectedCueRow.cue.left_instrument,
      selectedCueRow.cue.right_instrument,
      direction,
      action
    );

    setSubmitting(true);
    try {
      const responses = await Promise.all(
        legs.map((leg, index) =>
          submitOrderIntent({
            idempotency_key: `${Date.now()}-${pairId}-${command}-${leg.instrument}-${index}`,
            exchange,
            account_id: accountId,
            pair_id: pairId,
            instrument: leg.instrument,
            timeframe,
            action,
            spread_direction: direction,
            spread_z: action === "ENTRY" ? currentZ : null,
            side: leg.side,
            qty,
            operator_confirmed: action === "EMERGENCY_STOP_CLOSE" ? false : operatorConfirmed,
            operator_id: action === "EMERGENCY_STOP_CLOSE" ? null : operatorId,
            min_coverage_pct: 99.5,
          })
        )
      );

      const outcomes: LegExecutionOutcome[] = await Promise.all(
        responses.map(async (response): Promise<LegExecutionOutcome> => {
          if (response.decision !== "ACCEPTED") {
            return {
              instrument: response.instrument,
              intentDecision: response.decision,
              intentReason: response.reason,
              dispatch: null,
              dispatchError: null,
              history: null,
            };
          }

          try {
            const dispatch = await dispatchOrderIntent({
              idempotency_key: response.idempotency_key,
              actor: operatorId.trim().length ? operatorId : "operator-ui",
            });
            let history: OrderIntentHistoryResponse | null = null;
            try {
              history = await fetchOrderIntentHistory(response.idempotency_key);
            } catch {
              history = null;
            }
            return {
              instrument: response.instrument,
              intentDecision: response.decision,
              intentReason: response.reason,
              dispatch,
              dispatchError: null,
              history,
            };
          } catch (error) {
            return {
              instrument: response.instrument,
              intentDecision: response.decision,
              intentReason: response.reason,
              dispatch: null,
              dispatchError: error instanceof Error ? error.message : String(error),
              history: null,
            };
          }
        })
      );

      const acceptedCount = outcomes.filter((outcome) => outcome.intentDecision === "ACCEPTED").length;
      const blockedCount = outcomes.length - acceptedCount;
      const allDispatchAcknowledged = allAcceptedDispatchAcknowledged(outcomes);

      const histories = outcomes
        .map((outcome) => outcome.history)
        .filter((value): value is OrderIntentHistoryResponse => !!value);
      upsertIntentHistories(pairId, histories);

      const summaryTone: TimelineEvent["tone"] = allDispatchAcknowledged
        ? "ok"
        : blockedCount > 0
          ? "bad"
          : "warn";
      addTimelineEvent(pairId, {
        ts: now,
        text: `${command.toUpperCase()} accepted=${acceptedCount} blocked=${blockedCount} dispatch=${
          allDispatchAcknowledged ? "ACKNOWLEDGED" : "NOT_FULLY_ACKED"
        }`,
        tone: summaryTone,
      });

      for (const outcome of outcomes) {
        const dispatchText = outcome.dispatch
          ? `${outcome.dispatch.result}${outcome.dispatch.reason ? ` (${outcome.dispatch.reason})` : ""}`
          : outcome.dispatchError
            ? `DISPATCH_ERROR (${outcome.dispatchError})`
            : "DISPATCH_SKIPPED";
        addTimelineEvent(pairId, {
          ts: nowIso(),
          text: `${outcome.instrument}: ${outcome.intentDecision} -> ${dispatchText}`,
          tone:
            outcome.intentDecision === "ACCEPTED" && outcome.dispatch?.result === "ACKNOWLEDGED"
              ? "ok"
              : outcome.intentDecision === "BLOCKED" || outcome.dispatch?.result === "REJECTED"
                ? "bad"
                : "warn",
        });
      }

      if (acceptedCount > 0) {
        await refreshPositions().catch(() => {
          setPositions({});
        });
      }

      const legsText = outcomes
        .map((outcome) => {
          const dispatchResult = outcome.dispatch?.result ?? "NO_DISPATCH";
          return `${outcome.instrument}: ${outcome.intentDecision}/${dispatchResult}`;
        })
        .join(" | ");
      if (allDispatchAcknowledged) {
        setTradeMessage(`Spread dispatched and acknowledged. ${legsText}`);
      } else if (acceptedCount > 0) {
        setTradeMessage(
          `Intents accepted but not fully acknowledged by dispatch. ${legsText}. Review timeline for reasons.`
        );
      } else {
        setTradeMessage(`Spread action blocked. ${legsText}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addTimelineEvent(pairId, {
        ts: now,
        text: `SUBMIT ERROR (${message})`,
        tone: "bad",
      });
      setTradeMessage(`Submission error: ${message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const unlockUiAccess = async (): Promise<void> => {
    if (!uiAuthEnabled) {
      setUiUnlocked(true);
      return;
    }
    if (!uiPassword.trim().length) {
      setUiAuthError("Password is required.");
      return;
    }
    setUiAuthLoading(true);
    setUiAuthError(null);
    try {
      const response = await verifyStrategyUiAccess({ password: uiPassword });
      if (!response.ok) {
        setUiAuthError("Invalid password.");
        return;
      }
      setUiUnlocked(true);
      window.sessionStorage.setItem("cp.ui.unlocked", "true");
      setUiPassword("");
    } catch (error) {
      setUiAuthError(
        `Unable to verify password: ${error instanceof Error ? error.message : String(error)}`
      );
    } finally {
      setUiAuthLoading(false);
    }
  };

  const logoSrc = theme === "dark" ? logoDark : logoLight;
  const pageLabel = NAV_ITEMS.find((item) => item.id === page)?.label ?? "Trade";

  if (!uiAccessGranted) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h1>Pairs Access</h1>
          <p className="auth-subtitle">
            {uiAuthLoading ? "Checking access policy..." : "Enter password to continue."}
          </p>
          {!uiAuthLoading ? (
            <>
              <input
                type="password"
                value={uiPassword}
                onChange={(event) => setUiPassword(event.target.value)}
                placeholder="Password"
                autoFocus
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void unlockUiAccess();
                  }
                }}
              />
              <button type="button" onClick={() => void unlockUiAccess()} disabled={uiAuthLoading}>
                Unlock
              </button>
            </>
          ) : null}
          {uiAuthError ? <p className="small-text tone-bad">{uiAuthError}</p> : null}
        </div>
      </div>
    );
  }

  const content = (() => {
    if (page === "trade") {
      return (
        <TradePage
          cues={cuesResponse}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
          zSeries={zSeries}
          zTimestamps={zTimestamps}
          zMarkers={tradeChartMarkers}
          analyticsError={analyticsError}
          currentPosition={currentPosition}
          intentHistory={currentIntentHistory}
          activeTradeAnchor={activeTradeAnchor}
          timeline={currentTimeline}
          stopMethod={stopMethod}
          stopValue={stopValue}
          altStop={altStop}
          spreadSize={spreadSize}
          operatorConfirmed={operatorConfirmed}
          operatorId={operatorId}
          setStopMethod={setStopMethod}
          setStopValue={setStopValue}
          setAltStop={setAltStop}
          setSpreadSize={setSpreadSize}
          setOperatorConfirmed={setOperatorConfirmed}
          setOperatorId={setOperatorId}
          stopConfigured={stopConfigured}
          canLongEntry={canLongEntry}
          canShortEntry={canShortEntry}
          canAddExposure={canAddExposure}
          canReduceExposure={canReduceExposure}
          canCloseSpread={canCloseSpread}
          gateState={gateState}
          killSwitch={killSwitch}
          reconcile={reconcileResponse?.reconcile ?? null}
          gateError={gateError}
          tradeMessage={tradeMessage}
          submitting={submitting}
          zChartHeight={tradeZChartHeight}
          onCommand={executeTradeCommand}
        />
      );
    }

    if (page === "how-it-works") {
      return <HowThisWorksPage />;
    }

    if (page === "markets") {
      return (
        <MarketsPage
          cues={cuesResponse}
          costs={costResponse}
          loading={coreLoading}
          error={coreError}
        />
      );
    }

    if (page === "analytics") {
      return (
        <AnalyticsPage
          cues={cuesResponse}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
          zSeries={zSeries}
          zTimestamps={zTimestamps}
          zMarkers={zMarkers}
          equitySeries={equitySeries}
          equityTimestamps={equityTimestamps}
          loading={analyticsLoading}
          error={analyticsError}
          paperTrades={paperTrades}
          paperTradesLoading={paperTradesLoading}
          paperTradesError={paperTradesError}
          researchEntryZ={researchEntryZ}
          researchExitZ={researchExitZ}
          researchStopZ={researchStopZ}
          researchLookbackBars={researchLookbackBars}
          researchHours={researchHours}
          researchLimit={researchLimit}
          researchMaxCombinations={researchMaxCombinations}
          researchZMethod={researchZMethod}
          researchInputsValid={researchInputsValid}
          expectancyResult={expectancyResult}
          expectancyLoading={expectancyLoading}
          expectancyError={expectancyError}
          replayResult={replayResult}
          replayLoading={replayLoading}
          replayError={replayError}
          researchSweepResult={researchSweepResult}
          researchSweepLoading={researchSweepLoading}
          researchSweepError={researchSweepError}
          setResearchEntryZ={setResearchEntryZ}
          setResearchExitZ={setResearchExitZ}
          setResearchStopZ={setResearchStopZ}
          setResearchLookbackBars={setResearchLookbackBars}
          setResearchHours={setResearchHours}
          setResearchLimit={setResearchLimit}
          setResearchMaxCombinations={setResearchMaxCombinations}
          setResearchZMethod={setResearchZMethod}
          onApplyCueBands={applyCueBandsToResearch}
          onRunExpectancy={runExpectancyResearch}
          onRunReplay={runReplayResearch}
          onRunSweepDryRun={() => runResearchSweep(true)}
          onRunSweepExecute={() => runResearchSweep(false)}
          onDownloadExpectancy={downloadExpectancyResult}
          onDownloadReplay={downloadReplayResult}
          onDownloadSweep={downloadResearchSweepResult}
          chartHeight={analyticsChartHeight}
        />
      );
    }

    if (page === "portfolio") {
      return (
        <PortfolioPage
          plan={planResponse}
          positions={positions}
          selectedPairId={currentPairId}
          onSelectPair={setSelectedPairId}
        />
      );
    }

    if (page === "data-quality") {
      return (
        <DataQualityPage
          selected={selectedCueRow}
          left={leftIntegrity}
          right={rightIntegrity}
          gateState={gateState}
        />
      );
    }

    if (page === "maintenance") {
      return (
        <MaintenancePage
          timeframe={timeframe}
          historyStats={historyStats}
          historyStatsLoading={historyStatsLoading}
          historyStatsError={historyStatsError}
          modelHealthByTimeframe={modelHealthByTimeframe}
          modelHealthLoading={modelHealthLoading}
          modelHealthError={modelHealthError}
          maintenanceLatest={maintenanceLatest}
          maintenanceLoading={maintenanceLoading}
          maintenanceError={maintenanceError}
          maintenanceActionLoading={maintenanceActionLoading}
          maintenanceActionMessage={maintenanceActionMessage}
          operatorId={operatorId}
          onRunMaintenanceAction={executeMaintenanceAction}
        />
      );
    }

    return (
      <SettingsPage
        theme={theme}
        setTheme={setTheme}
        exchange={exchange}
        accountId={accountId}
        operatorId={operatorId}
        takerCommissionPct={takerCommissionPct}
        setTakerCommissionPct={setTakerCommissionPct}
        effectiveTakerFeeBps={takerFeeBpsOverride}
        backtestExitMode={backtestExitMode}
        setBacktestExitMode={setBacktestExitMode}
        apiKey={apiKey}
        apiSecret={apiSecret}
        apiPassphrase={apiPassphrase}
        showApiSecrets={showApiSecrets}
        setExchange={setExchange}
        setAccountId={setAccountId}
        setOperatorId={setOperatorId}
        setApiKey={setApiKey}
        setApiSecret={setApiSecret}
        setApiPassphrase={setApiPassphrase}
        setShowApiSecrets={setShowApiSecrets}
        timeframe={timeframe}
      />
    );
  })();

  return (
    <div className={`app ${theme}`}>
      <header className="topbar">
        <div className="topbar-left">
          <img src={logoSrc} alt="Pairs logo" className="brand-logo" />
          <h1>{pageLabel}</h1>
        </div>

        <div className="metrics-row">
          <Metric label={`${headerLeftLabel} Mark`} value={formatMetricPrice(headerLeftMetrics?.mark)} />
          <Metric label={`${headerLeftLabel} Index`} value={formatMetricPrice(headerLeftMetrics?.index)} />
          <Metric label={`${headerRightLabel} Mark`} value={formatMetricPrice(headerRightMetrics?.mark)} />
          <Metric label={`${headerRightLabel} Index`} value={formatMetricPrice(headerRightMetrics?.index)} />
          <Metric label="Net Spread Price" value={formatSignedMetric(spreadPrice, 3)} />
          <Metric
            label={`${headerLeftLabel} Position Size`}
            value={formatSignedMetric(pairLotSizes.leftSize, 2)}
            tone="neutral"
          />
          <Metric
            label={`${headerRightLabel} Position Size`}
            value={formatSignedMetric(pairLotSizes.rightSize, 2)}
            tone="neutral"
          />
          <Metric
            label="Net Spread Funding"
            value={formatFundingRateBpsPerHour(spreadFundingRate, spreadFundingIntervalSecs)}
          />
        </div>

        <div className="topbar-right">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="timeframe-button">
                Timeframe: {timeframe}
                <span className="caret">▾</span>
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content sideOffset={8} className="dropdown-content">
              {TIMEFRAMES.map((value) => (
                <DropdownMenu.Item
                  key={value}
                  className={`dropdown-item ${timeframe === value ? "selected" : ""}`}
                  onSelect={() => setTimeframe(value)}
                >
                  {value}
                  {timeframe === value ? <span className="check">✓</span> : null}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      </header>

      <div className={`startup-status tone-${startupStatus.tone}`}>
        {startupStatus.text}
      </div>

      <div className="app-body">
        <aside className="side-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`side-nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </aside>

        <section className="content-shell">{content}</section>
      </div>

      <footer className="footer-note">
        <span>Global timeframe selector applies to all pages and strategy panels.</span>
        <span className={gateSafe ? "tone-ok" : "tone-bad"}>
          {gateSafe
            ? "Trade gates healthy"
            : "Fail-closed mode: entry actions blocked until all gates are safe"}
        </span>
        {headerMetricsError ? <span className="tone-warn">{headerMetricsError}</span> : null}
        <span className="small-text" aria-hidden="true">
          build {WEB_BUILD_STAMP}
        </span>
      </footer>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}): JSX.Element {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={`metric-value tone-${tone}`}>{value}</div>
    </div>
  );
}

function SectionCard({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`panel-card ${className ?? ""}`.trim()}>
      <h2>{title}</h2>
      {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
      {children}
    </section>
  );
}

function TradePage(props: {
  cues: StrategyPairsCuesResponse | null;
  selectedPairId: string;
  onSelectPair: (pairId: string) => void;
  zSeries: number[];
  zTimestamps: string[];
  zMarkers: ChartMarker[];
  analyticsError: string | null;
  currentPosition: SpreadPosition;
  intentHistory: OrderIntentHistoryResponse[];
  activeTradeAnchor: { entryAt: string; entryZ: number; currentZ: number; deltaZ: number } | null;
  timeline: TimelineEvent[];
  stopMethod: "Z-Score" | "Dollar" | "Percent";
  stopValue: string;
  altStop: string;
  spreadSize: string;
  operatorConfirmed: boolean;
  operatorId: string;
  setStopMethod: (value: "Z-Score" | "Dollar" | "Percent") => void;
  setStopValue: (value: string) => void;
  setAltStop: (value: string) => void;
  setSpreadSize: (value: string) => void;
  setOperatorConfirmed: (value: boolean) => void;
  setOperatorId: (value: string) => void;
  stopConfigured: boolean;
  canLongEntry: boolean;
  canShortEntry: boolean;
  canAddExposure: boolean;
  canReduceExposure: boolean;
  canCloseSpread: boolean;
  gateState: { killSwitchActive: boolean; leftAllowed: boolean; rightAllowed: boolean; reconcileOk: boolean };
  killSwitch: KillSwitchState | null;
  reconcile: ReconcileResponse["reconcile"];
  gateError: string | null;
  tradeMessage: string;
  submitting: boolean;
  zChartHeight: number;
  onCommand: (command: TradeCommand) => Promise<void>;
}): JSX.Element {
  const selectedCue =
    props.cues?.cues.find((entry) => entry.cue.pair_id === props.selectedPairId) ??
    props.cues?.cues[0] ??
    null;

  const execute = (command: TradeCommand) => {
    void props.onCommand(command);
  };

  return (
    <div className="trade-grid">
      <SectionCard
        title="Opportunities"
        subtitle="Pairs scanner: z-score | edge | gate"
        className="opportunities-panel"
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Z</th>
                <th>Edge</th>
                <th>Ready</th>
              </tr>
            </thead>
            <tbody>
              {props.cues?.cues.map((entry) => (
                <tr
                  key={entry.cue.pair_id}
                  className={entry.cue.pair_id === props.selectedPairId ? "selected-row" : ""}
                  onClick={() => props.onSelectPair(entry.cue.pair_id)}
                >
                  <td>{formatPairLabel(entry.cue.pair_id)}</td>
                  <td>{entry.cue.spread_z.toFixed(2)}</td>
                  <td>{formatSigned(entry.cue.cost_gate.net_edge_bps)}bp</td>
                  <td className={(entry.cue.trade_gate?.pass ?? entry.cue.actionable) ? "tone-ok" : "tone-bad"}>
                    {(entry.cue.trade_gate?.pass ?? entry.cue.actionable) ? "PASS" : "BLOCK"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mini-card">
          <h3>Open spread summary</h3>
          <p>
            Direction: <span className="tone-info">{props.currentPosition.direction}</span>
          </p>
          <p>Total size: {props.currentPosition.totalSize.toFixed(2)} spread units</p>
          <p>Avg entry z-score: {props.currentPosition.avgEntryZ.toFixed(2)}</p>
          <p>Updated: {formatLocalTime(props.currentPosition.updatedAt)}</p>
          {props.activeTradeAnchor ? (
            <p className="tone-info">
              Active trade anchor: entry {props.activeTradeAnchor.entryZ.toFixed(2)} at{" "}
              {formatLocalTime(props.activeTradeAnchor.entryAt)} | current{" "}
              {props.activeTradeAnchor.currentZ.toFixed(2)} | ΔZ{" "}
              {formatSigned(props.activeTradeAnchor.deltaZ, 2)}
            </p>
          ) : null}
          <p>Tracked intents: {props.intentHistory.length}</p>
          {props.intentHistory.slice(0, 2).map((history) => {
            const latestState = latestLifecycleState(history);
            return (
              <p key={history.idempotency_key} className="small-text">
                {history.intent.instrument}: {latestState}
              </p>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Z Score Chart"
        subtitle="Spread z-score chart and rationale"
        className="analysis-panel"
      >
        <LineChart
          values={props.zSeries}
          timestamps={props.zTimestamps}
          markers={props.zMarkers}
          thresholds={
            selectedCue
              ? [
                  { value: 0, tone: "info" },
                  { value: selectedCue.cue.entry_band, tone: "warn" },
                  { value: -selectedCue.cue.entry_band, tone: "warn" },
                  { value: selectedCue.cue.stop_band, tone: "bad" },
                  { value: -selectedCue.cue.stop_band, tone: "bad" },
                ]
              : []
          }
          title="Z score (entry / mean / stop)"
          unavailableText={props.analyticsError ?? "No live z-score data"}
          height={props.zChartHeight}
          yAxisFormatter={(value) => value.toFixed(2)}
          showThresholdLabels
          mirrorThresholdLabels
          markerRadius={6}
          valueScaleMode="trimmed"
          includeThresholdsInDomain
          showLatestValueLabel
          latestValueLabelFormatter={(value) => `Z ${value.toFixed(2)}`}
        />

        <div className="chip-row">
          <span className="chip">Signal dots: entry/exit/stop (recomputed)</span>
          <span className="chip tone-info">Execution dots: persist from executed intents</span>
        </div>

        <div className="chip-row">
          {selectedCue?.cue.rationale_codes.length ? (
            selectedCue.cue.rationale_codes.map((code) => (
              <span key={code} className="chip">
                {code}
              </span>
            ))
          ) : (
            <>
              <span className="chip tone-ok">COINT PASS</span>
              <span className="chip tone-info">HALF-LIFE OK</span>
              <span className="chip tone-ok">COST PASS</span>
              <span className="chip tone-warn">REGIME {selectedCue?.cue.regime ?? "N/A"}</span>
            </>
          )}
        </div>

        <div className="timeline-card">
          <h3>Intent timeline</h3>
          {props.timeline.length ? (
            props.timeline.map((event, index) => (
              <p key={`${event.ts}-${index}`} className={`tone-${event.tone}`}>
                {formatLocalTime(event.ts)} {event.text}
              </p>
            ))
          ) : (
            <p className="empty-text">No live intent events yet.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Spread Execution"
        subtitle="Stop is prerequisite for entry actions"
        className="execution-panel"
      >
        <div className="execution-grid">
          <div className="execution-block stop-block">
            <h3>Stop Configuration (Required)</h3>
            <label>
              Method
              <select
                value={props.stopMethod}
                onChange={(event) =>
                  props.setStopMethod(event.target.value as "Z-Score" | "Dollar" | "Percent")
                }
              >
                <option value="Z-Score">Z-Score</option>
                <option value="Dollar">Dollar</option>
                <option value="Percent">Percent</option>
              </select>
            </label>
            <label>
              Value
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.stopValue}
                onChange={(event) => props.setStopValue(event.target.value)}
              />
            </label>
            <label>
              Alt stop
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.altStop}
                onChange={(event) => props.setAltStop(event.target.value)}
              />
            </label>
            <div className={`status-pill ${props.stopConfigured ? "ok" : "bad"}`}>
              Stop ready: {props.stopConfigured ? "yes" : "no"}
            </div>
          </div>

          <div className="execution-block entry-block">
            <h3>Entry / Add Exposure</h3>
            <label>
              Spread size (units)
              <input
                type="number"
                step="0.01"
                min="0"
                value={props.spreadSize}
                onChange={(event) => props.setSpreadSize(event.target.value)}
              />
            </label>
            <label>
              Operator ID
              <input
                type="text"
                value={props.operatorId}
                onChange={(event) => props.setOperatorId(event.target.value)}
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={props.operatorConfirmed}
                onChange={(event) => props.setOperatorConfirmed(event.target.checked)}
              />
              Live Trading Armed
            </label>

            <button disabled={!props.canLongEntry || props.submitting} onClick={() => execute("long-entry")}>
              Long Spread Entry
            </button>
            <button
              className="danger"
              disabled={!props.canShortEntry || props.submitting}
              onClick={() => execute("short-entry")}
            >
              Short Spread Entry
            </button>
            <button disabled={!props.canAddExposure || props.submitting} onClick={() => execute("add-exposure")}>
              Add Exposure to Open Spread
            </button>
          </div>

          <div className="execution-block reduce-block">
            <h3>Reduce / Close</h3>
            <button disabled={!props.canReduceExposure || props.submitting} onClick={() => execute("reduce-exposure")}>
              Reduce Exposure (partial)
            </button>
            <button
              className="danger"
              disabled={!props.canCloseSpread || props.submitting}
              onClick={() => execute("close-spread")}
            >
              Close Spread (all open in pair)
            </button>
          </div>

          <div className="execution-status-block">
            <div className="gate-grid">
              <div className={`status-pill ${props.gateState.killSwitchActive ? "bad" : "ok"}`}>
                Kill switch: {props.gateState.killSwitchActive ? "ACTIVE" : "OFF"}
              </div>
              <div className={`status-pill ${props.gateState.leftAllowed ? "ok" : "bad"}`}>
                Left integrity gate: {props.gateState.leftAllowed ? "ALLOWED" : "BLOCKED"}
              </div>
              <div className={`status-pill ${props.gateState.rightAllowed ? "ok" : "bad"}`}>
                Right integrity gate: {props.gateState.rightAllowed ? "ALLOWED" : "BLOCKED"}
              </div>
              <div className={`status-pill ${props.gateState.reconcileOk ? "ok" : "bad"}`}>
                Reconcile gate: {props.gateState.reconcileOk ? "OK" : "NOT_OK"}
              </div>
            </div>

            <div className="message-box">
              <strong>Result:</strong> {props.tradeMessage}
              {props.killSwitch ? (
                <div className="small-text">Kill switch reason: {props.killSwitch.reason}</div>
              ) : null}
              {props.reconcile ? (
                <div className="small-text">
                  Reconcile status: {props.reconcile.status} (drift {props.reconcile.drift_notional.toFixed(2)})
                </div>
              ) : null}
              {props.gateError ? <div className="tone-bad small-text">{props.gateError}</div> : null}
            </div>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

function MarketsPage({
  cues,
  costs,
  loading,
  error,
}: {
  cues: StrategyPairsCuesResponse | null;
  costs: StrategyPairsCostGateResponse | null;
  loading: boolean;
  error: string | null;
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Markets" subtitle="Live strategy candidate overview">
        {loading ? <p>Loading live data...</p> : null}
        {error ? <p className="tone-bad">{error}</p> : null}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Regime</th>
                <th>Score</th>
                <th>Actionable</th>
              </tr>
            </thead>
            <tbody>
              {cues?.cues.map((entry) => (
                <tr key={entry.cue.pair_id}>
                  <td>{formatPairLabel(entry.cue.pair_id)}</td>
                  <td>{entry.cue.regime}</td>
                  <td>{entry.cue.opportunity_score.toFixed(2)}</td>
                  <td className={entry.cue.actionable ? "tone-ok" : "tone-warn"}>
                    {entry.cue.actionable ? "YES" : "NO"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Cost Gates" subtitle="Live edge versus cost diagnostics">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Net Edge</th>
                <th>Pass</th>
              </tr>
            </thead>
            <tbody>
              {costs?.gates.map((gate) => (
                <tr key={gate.pair_id}>
                  <td>{formatPairLabel(gate.pair_id)}</td>
                  <td>{formatSigned(gate.net_edge_bps)}bp</td>
                  <td className={gate.pass ? "tone-ok" : "tone-bad"}>{gate.pass ? "PASS" : "BLOCK"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function HowThisWorksPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<HowItWorksTabId>("pairs-trading");
  const tab = HOW_IT_WORKS_TABS.find((item) => item.id === activeTab) ?? HOW_IT_WORKS_TABS[0];

  return (
    <div className="how-layout">
      <SectionCard
        title="How This Works"
        subtitle="Layman explainer for manual-first spread trading"
        className="how-main-panel"
      >
        <div className="how-tabs">
          {HOW_IT_WORKS_TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`how-tab-button ${item.id === activeTab ? "active" : ""}`}
              onClick={() => setActiveTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="how-tab-content">
          <h3>{tab.title}</h3>
          <p>{tab.intro}</p>
          {tab.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          <ul>
            {tab.bullets.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </SectionCard>

      <SectionCard title="Operator Workflow" subtitle="How decisions are made in this UI">
        <ol className="how-steps">
          <li>Select timeframe and pair.</li>
          <li>Review opportunity cues, z-score chart, and rationale tags.</li>
          <li>Set stop method and value before any entry can be sent.</li>
          <li>Arm live trading, then submit long or short spread entry manually.</li>
          <li>Monitor gates continuously and reduce/close if conditions degrade.</li>
        </ol>
        <p className="small-text">
          Manual-first mode: the system informs and enforces guardrails, while the operator
          decides when to act.
        </p>
      </SectionCard>
    </div>
  );
}

function AnalyticsPage({
  cues,
  selectedPairId,
  onSelectPair,
  zSeries,
  zTimestamps,
  zMarkers,
  equitySeries,
  equityTimestamps,
  loading,
  error,
  paperTrades,
  paperTradesLoading,
  paperTradesError,
  researchEntryZ,
  researchExitZ,
  researchStopZ,
  researchLookbackBars,
  researchHours,
  researchLimit,
  researchMaxCombinations,
  researchZMethod,
  researchInputsValid,
  expectancyResult,
  expectancyLoading,
  expectancyError,
  replayResult,
  replayLoading,
  replayError,
  researchSweepResult,
  researchSweepLoading,
  researchSweepError,
  setResearchEntryZ,
  setResearchExitZ,
  setResearchStopZ,
  setResearchLookbackBars,
  setResearchHours,
  setResearchLimit,
  setResearchMaxCombinations,
  setResearchZMethod,
  onApplyCueBands,
  onRunExpectancy,
  onRunReplay,
  onRunSweepDryRun,
  onRunSweepExecute,
  onDownloadExpectancy,
  onDownloadReplay,
  onDownloadSweep,
  chartHeight,
}: {
  cues: StrategyPairsCuesResponse | null;
  selectedPairId: string;
  onSelectPair: (value: string) => void;
  zSeries: number[];
  zTimestamps: string[];
  zMarkers: ChartMarker[];
  equitySeries: number[];
  equityTimestamps: string[];
  loading: boolean;
  error: string | null;
  paperTrades: StrategyPairsPaperTradesResponse | null;
  paperTradesLoading: boolean;
  paperTradesError: string | null;
  researchEntryZ: string;
  researchExitZ: string;
  researchStopZ: string;
  researchLookbackBars: string;
  researchHours: string;
  researchLimit: string;
  researchMaxCombinations: string;
  researchZMethod: StrategyZMethod;
  researchInputsValid: boolean;
  expectancyResult: StrategyPairsExpectancyResponse | null;
  expectancyLoading: boolean;
  expectancyError: string | null;
  replayResult: StrategyPairsReplayTradesResponse | null;
  replayLoading: boolean;
  replayError: string | null;
  researchSweepResult: StrategyPairsResearchSweepResponse | null;
  researchSweepLoading: boolean;
  researchSweepError: string | null;
  setResearchEntryZ: (value: string) => void;
  setResearchExitZ: (value: string) => void;
  setResearchStopZ: (value: string) => void;
  setResearchLookbackBars: (value: string) => void;
  setResearchHours: (value: string) => void;
  setResearchLimit: (value: string) => void;
  setResearchMaxCombinations: (value: string) => void;
  setResearchZMethod: (value: StrategyZMethod) => void;
  onApplyCueBands: () => void;
  onRunExpectancy: () => Promise<void>;
  onRunReplay: () => Promise<void>;
  onRunSweepDryRun: () => Promise<void>;
  onRunSweepExecute: () => Promise<void>;
  onDownloadExpectancy: () => void;
  onDownloadReplay: () => void;
  onDownloadSweep: () => void;
  chartHeight: number;
}): JSX.Element {
  const selected = cues?.cues.find((entry) => entry.cue.pair_id === selectedPairId) ?? cues?.cues[0];
  const actionabilityExplanation = explainPairActionability(selected);
  const displayEquitySeries = useMemo(
    () => scaleEquityForDisplay(equitySeries, 100, 110),
    [equitySeries]
  );

  return (
    <div className="analytics-layout">
      <div className="analytics-left-stack">
        <SectionCard title="Strategy Metrics" subtitle="Optimal strategy summary">
          {selected ? (
            <>
              <StatRow label="Opportunity Score" value={selected.cue.opportunity_score.toFixed(2)} />
              <StatRow label="Expected Hold Bars" value={selected.cue.expected_hold_bars.toString()} />
              <StatRow label="Cost Estimate" value={`${selected.cue.cost_estimate_bps.toFixed(2)} bp`} />
              <StatRow label="Confidence" value={selected.cue.confidence_band} />
              <StatRow
                label="Shadow ML Precision"
                value={selected.cue.shadow_ml.precision.toFixed(2)}
                tone="ok"
              />
            </>
          ) : (
            <p className="empty-text">No live cues available.</p>
          )}

          <label>
            Pair
            <select
              value={selected?.cue.pair_id ?? ""}
              onChange={(event) => onSelectPair(event.target.value)}
            >
              {cues?.cues.map((entry) => (
                <option key={entry.cue.pair_id} value={entry.cue.pair_id}>
                  {formatPairLabel(entry.cue.pair_id)}
                </option>
              ))}
            </select>
          </label>
        </SectionCard>

        <SectionCard title="Diagnostics" subtitle="Reoptimize and shadow model status">
          {selected ? (
            <>
              <StatRow label="Champion Variant" value={selected.cue.selected_variant} />
              <StatRow
                label="Shadow Agreement"
                value={selected.cue.shadow_ml.agrees_with_selected ? "YES" : "NO"}
                tone={selected.cue.shadow_ml.agrees_with_selected ? "ok" : "warn"}
              />
              <StatRow
                label="Setup Gate"
                value={(selected.cue.setup_gate?.pass ?? selected.cue.setup_actionable ?? selected.cue.actionable) ? "PASS" : "BLOCK"}
                tone={(selected.cue.setup_gate?.pass ?? selected.cue.setup_actionable ?? selected.cue.actionable) ? "ok" : "bad"}
              />
              <StatRow
                label="Cost Economics"
                value={selected.cue.cost_gate.pass ? "PASS" : "BLOCK"}
                tone={selected.cue.cost_gate.pass ? "ok" : "bad"}
              />
              <StatRow
                label="Trade Ready"
                value={(selected.cue.trade_gate?.pass ?? selected.cue.actionable) ? "PASS" : "BLOCK"}
                tone={(selected.cue.trade_gate?.pass ?? selected.cue.actionable) ? "ok" : "bad"}
              />
            </>
          ) : (
            <p className="empty-text">No diagnostics available.</p>
          )}
        </SectionCard>

        <SectionCard title="Paper Trades (Persisted)" subtitle="Per-trade leg PnL breakdown">
          {paperTrades?.model_bars ? (
            <p className="small-text tone-info">Model window: {paperTrades.model_bars} bars</p>
          ) : null}
          {paperTradesLoading ? <p className="small-text">Loading persisted paper trades...</p> : null}
          {paperTradesError ? <p className="small-text tone-bad">{paperTradesError}</p> : null}
          {!paperTradesLoading && !paperTradesError && paperTrades?.rows.length === 0 ? (
            <p className="small-text">No persisted paper trades found for this pair/timeframe window.</p>
          ) : null}
          {paperTrades?.rows.length ? (
            <div className="table-wrap analytics-paper-trades-table">
              <table>
                <thead>
                  <tr>
                    <th>Exit</th>
                    <th>Dir</th>
                    <th>Hold</th>
                    <th>Left</th>
                    <th>Right</th>
                    <th>Net</th>
                    <th>Equity</th>
                  </tr>
                </thead>
                <tbody>
                  {paperTrades.rows.map((row) => (
                    <tr key={`${row.entry_ts}-${row.exit_ts}-${row.exit_kind}`}>
                      <td>{formatLocalTime(row.exit_ts)}</td>
                      <td>{row.direction === "LONG_SPREAD" ? "LONG" : "SHORT"}</td>
                      <td>{row.bars_held}</td>
                      <td className={row.left_leg_bps >= 0 ? "tone-ok" : "tone-bad"}>
                        {formatSigned(row.left_leg_bps)}bp
                      </td>
                      <td className={row.right_leg_bps >= 0 ? "tone-ok" : "tone-bad"}>
                        {formatSigned(row.right_leg_bps)}bp
                      </td>
                      <td className={row.net_bps >= 0 ? "tone-ok" : "tone-bad"}>
                        {formatSigned(row.net_bps)}bp
                      </td>
                      <td className={row.equity_trade_bps >= 0 ? "tone-ok" : "tone-bad"}>
                        {formatSigned(row.equity_trade_bps)}bp
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Research Controls"
          subtitle="Run expectancy/replay with parameter overrides and export results"
        >
          <div className="research-controls-grid">
            <label>
              Entry Z
              <input
                type="number"
                min="0.2"
                max="8"
                step="0.01"
                value={researchEntryZ}
                onChange={(event) => setResearchEntryZ(event.target.value)}
              />
            </label>
            <label>
              Exit Z
              <input
                type="number"
                min="0"
                step="0.01"
                value={researchExitZ}
                onChange={(event) => setResearchExitZ(event.target.value)}
              />
            </label>
            <label>
              Stop Z
              <input
                type="number"
                min="0.2"
                max="12"
                step="0.01"
                value={researchStopZ}
                onChange={(event) => setResearchStopZ(event.target.value)}
              />
            </label>
            <label>
              Lookback Bars
              <input
                type="number"
                min="120"
                max="10000"
                step="1"
                value={researchLookbackBars}
                onChange={(event) => setResearchLookbackBars(event.target.value)}
              />
            </label>
            <label>
              Replay Hours
              <input
                type="number"
                min="1"
                max="175200"
                step="1"
                value={researchHours}
                onChange={(event) => setResearchHours(event.target.value)}
              />
            </label>
            <label>
              Replay Limit
              <input
                type="number"
                min="1"
                max="20000"
                step="1"
                value={researchLimit}
                onChange={(event) => setResearchLimit(event.target.value)}
              />
            </label>
            <label>
              Sweep Max Combos
              <input
                type="number"
                min="1"
                max="1000000"
                step="1"
                value={researchMaxCombinations}
                onChange={(event) => setResearchMaxCombinations(event.target.value)}
              />
            </label>
            <label>
              Z Method
              <select
                value={researchZMethod}
                onChange={(event) => setResearchZMethod(event.target.value as StrategyZMethod)}
              >
                {RESEARCH_Z_METHODS.map((method) => (
                  <option key={method} value={method}>
                    {method}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {!researchInputsValid ? (
            <p className="small-text tone-bad">Research inputs are invalid. Check Z bands and ranges.</p>
          ) : null}

          <div className="research-controls-actions">
            <button type="button" onClick={onApplyCueBands}>
              Use Cue Bands
            </button>
            <button
              type="button"
              onClick={() => void onRunExpectancy()}
              disabled={!researchInputsValid || expectancyLoading}
            >
              {expectancyLoading ? "Running..." : "Run Expectancy"}
            </button>
            <button
              type="button"
              onClick={() => void onRunReplay()}
              disabled={!researchInputsValid || replayLoading}
            >
              {replayLoading ? "Running..." : "Run Replay"}
            </button>
            <button
              type="button"
              onClick={() => void onRunSweepDryRun()}
              disabled={!researchInputsValid || researchSweepLoading}
            >
              {researchSweepLoading ? "Running..." : "Run Sweep Dry-Run"}
            </button>
            <button
              type="button"
              onClick={() => void onRunSweepExecute()}
              disabled={!researchInputsValid || researchSweepLoading}
            >
              {researchSweepLoading ? "Running..." : "Run Sweep Execute"}
            </button>
          </div>

          <div className="research-results-grid">
            <div className="mini-card">
              <h3>Expectancy</h3>
              {expectancyError ? <p className="small-text tone-bad">{expectancyError}</p> : null}
              {expectancyResult ? (
                <>
                  <p>
                    Status:{" "}
                    <span className={expectancyResult.status === "AVAILABLE" ? "tone-ok" : "tone-bad"}>
                      {expectancyResult.status}
                    </span>
                  </p>
                  <p>Decision: {expectancyResult.decision_state}</p>
                  <p>Reason: {expectancyResult.primary_reason_code}</p>
                  <p>Trades: {expectancyResult.metrics?.trades ?? 0}</p>
                  <p>
                    Avg net:{" "}
                    {expectancyResult.metrics ? `${formatSigned(expectancyResult.metrics.avg_net_bps)}bp` : "--"}
                  </p>
                  <p>
                    Win rate:{" "}
                    {expectancyResult.metrics
                      ? `${(expectancyResult.metrics.win_rate * 100).toFixed(2)}%`
                      : "--"}
                  </p>
                  <button type="button" onClick={onDownloadExpectancy}>
                    Download Expectancy JSON
                  </button>
                </>
              ) : (
                <p className="small-text">No expectancy result loaded.</p>
              )}
            </div>

            <div className="mini-card">
              <h3>Replay</h3>
              {replayError ? <p className="small-text tone-bad">{replayError}</p> : null}
              {replayResult ? (
                <>
                  <p>
                    Status:{" "}
                    <span className={replayResult.status === "AVAILABLE" ? "tone-ok" : "tone-bad"}>
                      {replayResult.status}
                    </span>
                  </p>
                  <p>Rows: {replayResult.rows.length}</p>
                  <p>Mode: {replayResult.exit_mode}</p>
                  <p>Window: {replayResult.hours}h</p>
                  <button type="button" onClick={onDownloadReplay}>
                    Download Replay JSON
                  </button>
                </>
              ) : (
                <p className="small-text">No replay result loaded.</p>
              )}
            </div>

            <div className="mini-card">
              <h3>Sweep</h3>
              {researchSweepError ? <p className="small-text tone-bad">{researchSweepError}</p> : null}
              {researchSweepResult ? (
                <>
                  <p>
                    Status:{" "}
                    <span
                      className={researchSweepResult.status === "AVAILABLE" ? "tone-ok" : "tone-bad"}
                    >
                      {researchSweepResult.status}
                    </span>
                  </p>
                  <p>Request: {researchSweepResult.request_id}</p>
                  <p>Mode: {researchSweepResult.dry_run ? "Dry-run" : "Execute"}</p>
                  <p>
                    Combos: {researchSweepResult.estimated_combinations} /{" "}
                    {researchSweepResult.max_combinations}
                  </p>
                  <p>
                    Executed: {researchSweepResult.executed_combinations} | Success:{" "}
                    {researchSweepResult.successful_combinations} | Failed:{" "}
                    {researchSweepResult.failed_combinations}
                  </p>
                  {researchSweepResult.best_candidate ? (
                    <>
                      <p className="small-text tone-info">
                        Best: {formatPairLabel(researchSweepResult.best_candidate.pair_id)}{" "}
                        {researchSweepResult.best_candidate.timeframe} | entry{" "}
                        {researchSweepResult.best_candidate.config.entry_z.toFixed(2)} exit{" "}
                        {researchSweepResult.best_candidate.config.exit_z.toFixed(2)} stop{" "}
                        {researchSweepResult.best_candidate.config.stop_z.toFixed(2)} | lookback{" "}
                        {researchSweepResult.best_candidate.config.lookback_bars}
                      </p>
                      <p className="small-text">
                        Objective: {formatSigned(researchSweepResult.best_candidate.objective_score)} | Trades:{" "}
                        {researchSweepResult.best_candidate.metrics?.trades ?? 0} | Win rate:{" "}
                        {researchSweepResult.best_candidate.metrics
                          ? `${(researchSweepResult.best_candidate.metrics.win_rate * 100).toFixed(
                              2
                            )}%`
                          : "--"}
                      </p>
                    </>
                  ) : null}
                  <button type="button" onClick={onDownloadSweep}>
                    Download Sweep JSON
                  </button>
                </>
              ) : (
                <p className="small-text">No sweep result loaded.</p>
              )}
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="analytics-right-stack">
        <div className="analytics-chart-split">
          <SectionCard
            title="Hypothetical Equity Curve"
            subtitle="Derived from live candles and current strategy bands"
          >
            <LineChart
              values={displayEquitySeries}
              timestamps={equityTimestamps}
              height={chartHeight}
              title="Hypothetical equity (base $100, 110x scaled deltas)"
              unavailableText={loading ? "Loading live candles..." : error ?? "No data"}
              yAxisFormatter={formatUsdAxisValue}
              valueScaleMode="trimmed"
            />
          </SectionCard>

          <SectionCard
            title="Historical Z-Score (Entries / Exits / Stops)"
            subtitle="Derived from live spread history"
          >
            <LineChart
              values={zSeries}
              timestamps={zTimestamps}
              markers={zMarkers}
              thresholds={
                selected
                  ? [
                      { value: 0, tone: "info" },
                      { value: selected.cue.entry_band, tone: "warn" },
                      { value: -selected.cue.entry_band, tone: "warn" },
                      { value: selected.cue.stop_band, tone: "bad" },
                      { value: -selected.cue.stop_band, tone: "bad" },
                    ]
                  : []
              }
              height={chartHeight}
              title="Entry=green, Exit=amber, Stop=red"
              unavailableText={loading ? "Loading live candles..." : error ?? "No data"}
              yAxisFormatter={(value) => value.toFixed(2)}
              showThresholdLabels
              mirrorThresholdLabels
              markerRadius={6}
              valueScaleMode="trimmed"
              includeThresholdsInDomain
            />
          </SectionCard>
        </div>
        <SectionCard
          title="Why This Pair Is Allowed / Blocked"
          subtitle="Plain-language gate explanation for the selected pair"
          className="analytics-explainer"
        >
          <div className={`status-pill ${actionabilityExplanation.tone === "ok" ? "ok" : "bad"}`}>
            {actionabilityExplanation.headline}
          </div>

          <ul className="analytics-explainer-list">
            {actionabilityExplanation.details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>

          {actionabilityExplanation.reasons.length ? (
            <>
              <h3>Gate reasons</h3>
              <ul className="analytics-explainer-list">
                {actionabilityExplanation.reasons.map((reason) => (
                  <li key={reason}>{describeRationaleCode(reason)}</li>
                ))}
              </ul>
            </>
          ) : null}
        </SectionCard>

      </div>
    </div>
  );
}

function MaintenancePage({
  timeframe,
  historyStats,
  historyStatsLoading,
  historyStatsError,
  modelHealthByTimeframe,
  modelHealthLoading,
  modelHealthError,
  maintenanceLatest,
  maintenanceLoading,
  maintenanceError,
  maintenanceActionLoading,
  maintenanceActionMessage,
  operatorId,
  onRunMaintenanceAction,
}: {
  timeframe: Timeframe;
  historyStats: StrategyPairsOpportunityHistoryStatsResponse | null;
  historyStatsLoading: boolean;
  historyStatsError: string | null;
  modelHealthByTimeframe: Record<Timeframe, ModelHealthSnapshot>;
  modelHealthLoading: boolean;
  modelHealthError: string | null;
  maintenanceLatest: StrategyMaintenanceLatestResponse | null;
  maintenanceLoading: boolean;
  maintenanceError: string | null;
  maintenanceActionLoading: boolean;
  maintenanceActionMessage: string | null;
  operatorId: string;
  onRunMaintenanceAction: (action: "PROMOTE" | "REVERT") => Promise<StrategyMaintenanceActionResponse>;
}): JSX.Element {
  const maintenanceReport = maintenanceLatest?.report ?? null;
  const maintenanceStepEntries = maintenanceReport ? Object.entries(maintenanceReport.steps) : [];
  const [maintenanceActionError, setMaintenanceActionError] = useState<string | null>(null);
  const downloadHours = [24, 72, 168];
  const selectedStats =
    historyStats?.by_timeframe.find((entry) => entry.timeframe === timeframe) ?? null;

  const runMaintenanceAction = async (action: "PROMOTE" | "REVERT"): Promise<void> => {
    if (!operatorId.trim().length) {
      setMaintenanceActionError("Operator ID is required before running PROMOTE/REVERT.");
      return;
    }
    const confirmation = window.confirm(
      `${action} will apply strategy tuning values and redeploy strategy-service. Continue?`
    );
    if (!confirmation) {
      return;
    }
    try {
      setMaintenanceActionError(null);
      await onRunMaintenanceAction(action);
    } catch (error) {
      setMaintenanceActionError(
        `Unable to execute ${action}: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  };

  return (
    <div className="split-grid">
      <SectionCard
        title="Opportunity History Downloads"
        subtitle="Quantify tradeable activity and export PASS/all events by timeframe window"
      >
        {historyStatsLoading ? <p className="small-text">Loading history meter...</p> : null}
        {historyStatsError ? <p className="small-text tone-bad">{historyStatsError}</p> : null}
        {selectedStats ? (
          <div className="mini-card">
            <h3>Retention Meter ({timeframe})</h3>
            <p>
              Days covered: <span className="tone-info">{selectedStats.days_covered.toFixed(2)}</span>
            </p>
            <p>Total rows: {selectedStats.rows}</p>
            <p>
              Range:{" "}
              {selectedStats.first_evaluated_at
                ? formatLocalDateTime(selectedStats.first_evaluated_at)
                : "n/a"}{" "}
              to{" "}
              {selectedStats.last_evaluated_at
                ? formatLocalDateTime(selectedStats.last_evaluated_at)
                : "n/a"}
            </p>
          </div>
        ) : (
          <p className="small-text">No history stats available yet for {timeframe}.</p>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Window</th>
                <th>PASS Only</th>
                <th>All Rows</th>
              </tr>
            </thead>
            <tbody>
              {downloadHours.map((hours) => (
                <tr key={hours}>
                  <td>{hours === 168 ? "7d" : `${hours}h`}</td>
                  <td>
                    <a href={buildStrategyOpportunityHistoryUrl(timeframe, hours, true, 5000)}>
                      Download
                    </a>
                  </td>
                  <td>
                    <a href={buildStrategyOpportunityHistoryUrl(timeframe, hours, false, 5000)}>
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard
        title="Live Model Health"
        subtitle="Sampled slippage and dynamic funding readiness by timeframe"
      >
        {modelHealthLoading ? <p className="small-text">Loading model health...</p> : null}
        {modelHealthError ? <p className="small-text tone-bad">{modelHealthError}</p> : null}
        <div className="table-wrap">
          <table className="model-health-table">
            <thead>
              <tr>
                <th>TF</th>
                <th>Gate</th>
                <th>Slippage</th>
                <th>Funding</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {TIMEFRAMES.map((tf) => {
                const row = modelHealthByTimeframe[tf];
                const gateClass =
                  row.status === "AVAILABLE"
                    ? "tone-ok"
                    : row.status === "LOADING"
                      ? "tone-warn"
                      : "tone-bad";
                const fundingLabel =
                  row.fundingModel == null
                    ? "--"
                    : `${row.fundingModel} e=${row.fundingEvents ?? 0} bps/event=${
                        row.fundingBpsPerEvent == null ? "--" : row.fundingBpsPerEvent.toFixed(3)
                      }`;
                const details =
                  row.message ??
                  (row.rationaleCodes.length
                    ? row.rationaleCodes.slice(0, 2).join(", ")
                    : "No rationale codes");
                return (
                  <tr key={tf}>
                    <td>{tf}</td>
                    <td className={gateClass}>{row.status}</td>
                    <td className={row.sampledSlippageActive ? "tone-ok" : "tone-bad"}>
                      {row.sampledSlippageActive ? "SAMPLED" : "UNAVAILABLE"}
                    </td>
                    <td>{fundingLabel}</td>
                    <td>{details}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="small-text">
          Updated:{" "}
          {modelHealthByTimeframe[timeframe]?.updatedAt
            ? formatLocalDateTime(modelHealthByTimeframe[timeframe].updatedAt)
            : "--"}
        </p>
      </SectionCard>

      <SectionCard
        title="Automated Daily Maintenance"
        subtitle="Scheduled health checks and strategy tuning decision reports"
        className="analytics-maintenance"
      >
        {maintenanceLoading ? <p className="small-text">Loading maintenance report...</p> : null}
        {maintenanceError ? <p className="tone-bad small-text">{maintenanceError}</p> : null}
        {maintenanceLatest && !maintenanceLatest.available ? (
          <p className="small-text">
            {maintenanceLatest.reason ?? "No maintenance report is available yet."}
          </p>
        ) : null}

        {maintenanceReport ? (
          <>
            <div className={`status-pill ${maintenanceReport.status === "PASS" ? "ok" : "bad"}`}>
              Latest cycle: {maintenanceReport.status}
            </div>
            <p className="small-text">
              Run: {maintenanceReport.run_id} at {formatLocalDateTime(maintenanceReport.generated_at)}
            </p>
            <p className="small-text">
              Decision:{" "}
              <span className={maintenanceReport.decision === "PROMOTE" ? "tone-ok" : "tone-warn"}>
                {maintenanceReport.decision}
              </span>
            </p>
            <p className="small-text">
              Operator: <span className="tone-info">{operatorId || "unset"}</span>
            </p>

            <div className="maintenance-actions">
              <button
                type="button"
                disabled={maintenanceActionLoading}
                onClick={() => void runMaintenanceAction("PROMOTE")}
              >
                One-Click Promote
              </button>
              <button
                type="button"
                className="danger"
                disabled={maintenanceActionLoading}
                onClick={() => void runMaintenanceAction("REVERT")}
              >
                One-Click Revert
              </button>
            </div>
            {maintenanceActionLoading ? (
              <p className="small-text">Running maintenance action...</p>
            ) : null}
            {maintenanceActionMessage ? (
              <p className="small-text tone-info">{maintenanceActionMessage}</p>
            ) : null}
            {maintenanceActionError ? (
              <p className="small-text tone-bad">{maintenanceActionError}</p>
            ) : null}

            {maintenanceReport.decision_reasons.length ? (
              <ul className="analytics-explainer-list">
                {maintenanceReport.decision_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : null}

            {maintenanceStepEntries.length ? (
              <div className="maintenance-steps">
                {maintenanceStepEntries.map(([stepName, stepResult]) => (
                  <div key={stepName} className="maintenance-step-row">
                    <span>{formatMaintenanceStepLabel(stepName)}</span>
                    <span className={stepResult.pass ? "tone-ok" : "tone-bad"}>
                      {stepResult.pass ? "PASS" : "FAIL"}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            {maintenanceReport.downloads.length ? (
              <>
                <h3>Downloads</h3>
                <ul className="maintenance-downloads">
                  {maintenanceReport.downloads.map((item) => (
                    <li key={`${item.label}-${item.path}`}>
                      <a href={buildStrategyMaintenanceArtifactUrl(item.path)}>{item.label}</a>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="small-text">No downloadable artifacts found for the latest run.</p>
            )}
          </>
        ) : null}
      </SectionCard>
    </div>
  );
}

function PortfolioPage({
  plan,
  positions,
  selectedPairId,
  onSelectPair,
}: {
  plan: StrategyPairsPortfolioPlanResponse | null;
  positions: Record<string, SpreadPosition>;
  selectedPairId: string;
  onSelectPair: (pairId: string) => void;
}): JSX.Element {
  const entries = Object.entries(positions);

  return (
    <div className="split-grid">
      <SectionCard title="Portfolio" subtitle="Live open spread positions (server-truth execution ledger)">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Direction</th>
                <th>Size</th>
                <th>Avg Z</th>
              </tr>
            </thead>
            <tbody>
              {entries.length ? (
                entries.map(([pairId, position]) => (
                  <tr
                    key={pairId}
                    className={pairId === selectedPairId ? "selected-row" : ""}
                    onClick={() => onSelectPair(pairId)}
                  >
                    <td>{formatPairLabel(pairId)}</td>
                    <td>{position.direction}</td>
                    <td>{position.totalSize.toFixed(2)}</td>
                    <td>{position.avgEntryZ.toFixed(2)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="empty-text">
                    No open spread positions in execution ledger.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Portfolio Plan" subtitle="Live strategy advisory weights">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pair</th>
                <th>Target Weight</th>
                <th>Risk Contribution</th>
              </tr>
            </thead>
            <tbody>
              {plan?.plan.weights.map((weight) => (
                <tr key={weight.pair_id}>
                  <td>{formatPairLabel(weight.pair_id)}</td>
                  <td>{weight.target_weight.toFixed(2)}</td>
                  <td>{(weight.risk_contribution * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function DataQualityPage({
  selected,
  left,
  right,
  gateState,
}: {
  selected: StrategyPairsCuesResponse["cues"][number] | null;
  left: IntegrityHistoryResponse | null;
  right: IntegrityHistoryResponse | null;
  gateState: { killSwitchActive: boolean; leftAllowed: boolean; rightAllowed: boolean; reconcileOk: boolean };
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Data Quality" subtitle="Integrity history from data-service">
        <StatRow
          label="Execution impact"
          value={gateState.leftAllowed && gateState.rightAllowed ? "ENTRY ALLOWED" : "ENTRY BLOCKED"}
          tone={gateState.leftAllowed && gateState.rightAllowed ? "ok" : "bad"}
        />

        <h3>
          {selected?.cue.left_instrument
            ? formatInstrumentLabel(selected.cue.left_instrument)
            : "Left Instrument"}
        </h3>
        <IntegrityTable rows={left?.rows ?? []} />

        <h3>
          {selected?.cue.right_instrument
            ? formatInstrumentLabel(selected.cue.right_instrument)
            : "Right Instrument"}
        </h3>
        <IntegrityTable rows={right?.rows ?? []} />
      </SectionCard>

      <SectionCard title="Details" subtitle="Backfill and gating context">
        <p>
          Kill switch: <span className={gateState.killSwitchActive ? "tone-bad" : "tone-ok"}>{gateState.killSwitchActive ? "ACTIVE" : "OFF"}</span>
        </p>
        <p>
          Left gate: <span className={gateState.leftAllowed ? "tone-ok" : "tone-bad"}>{gateState.leftAllowed ? "ALLOWED" : "BLOCKED"}</span>
        </p>
        <p>
          Right gate: <span className={gateState.rightAllowed ? "tone-ok" : "tone-bad"}>{gateState.rightAllowed ? "ALLOWED" : "BLOCKED"}</span>
        </p>
        <p>
          Reconcile gate: <span className={gateState.reconcileOk ? "tone-ok" : "tone-bad"}>{gateState.reconcileOk ? "OK" : "NOT_OK"}</span>
        </p>
      </SectionCard>
    </div>
  );
}

function IntegrityTable({
  rows,
}: {
  rows: Array<{
    start_ts: string;
    end_ts: string;
    status: "COMPLETE" | "PARTIAL_BACKFILLED" | "INCOMPLETE" | "STALE" | "FAILED";
    coverage_pct: number;
    reason: string;
    checked_at: string;
  }>;
}): JSX.Element {
  const visibleRows = rows.slice(0, 8);
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Checked</th>
              <th>Status</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              visibleRows.map((row) => (
                <tr key={`${row.checked_at}-${row.start_ts}`}>
                  <td>{formatLocalTime(row.checked_at)}</td>
                  <td className={`tone-${toneFromStatus(row.status)}`}>{row.status}</td>
                  <td>{row.coverage_pct.toFixed(2)}%</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3} className="empty-text">
                  No live integrity rows available.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="small-text">
        Showing latest {visibleRows.length} checks (newest first) from {rows.length} stored rows.
      </p>
    </>
  );
}

function SettingsPage({
  theme,
  setTheme,
  exchange,
  accountId,
  operatorId,
  takerCommissionPct,
  setTakerCommissionPct,
  effectiveTakerFeeBps,
  backtestExitMode,
  setBacktestExitMode,
  apiKey,
  apiSecret,
  apiPassphrase,
  showApiSecrets,
  setExchange,
  setAccountId,
  setOperatorId,
  setApiKey,
  setApiSecret,
  setApiPassphrase,
  setShowApiSecrets,
  timeframe,
}: {
  theme: ThemeMode;
  setTheme: (value: ThemeMode | ((prev: ThemeMode) => ThemeMode)) => void;
  exchange: string;
  accountId: string;
  operatorId: string;
  takerCommissionPct: string;
  setTakerCommissionPct: (value: string) => void;
  effectiveTakerFeeBps: number | null;
  backtestExitMode: BacktestExitMode;
  setBacktestExitMode: (value: BacktestExitMode) => void;
  apiKey: string;
  apiSecret: string;
  apiPassphrase: string;
  showApiSecrets: boolean;
  setExchange: (value: string) => void;
  setAccountId: (value: string) => void;
  setOperatorId: (value: string) => void;
  setApiKey: (value: string) => void;
  setApiSecret: (value: string) => void;
  setApiPassphrase: (value: string) => void;
  setShowApiSecrets: (value: boolean) => void;
  timeframe: Timeframe;
}): JSX.Element {
  return (
    <div className="split-grid">
      <SectionCard title="Settings" subtitle="Manual trading defaults and UI preferences">
        <label>
          Theme
          <select value={theme} onChange={(event) => setTheme(event.target.value as ThemeMode)}>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>

        <label>
          Exchange
          <input value={exchange} onChange={(event) => setExchange(event.target.value)} />
        </label>

        <label>
          Account ID
          <input value={accountId} onChange={(event) => setAccountId(event.target.value)} />
        </label>

        <label>
          Default Operator ID
          <input value={operatorId} onChange={(event) => setOperatorId(event.target.value)} />
        </label>

        <label>
          Taker Commission
          <input
            value={takerCommissionPct}
            onChange={(event) => setTakerCommissionPct(event.target.value)}
            placeholder="0.10%"
          />
        </label>

        <p className="small-text">
          Percent used in strategy fee calculations (example: <code>0.10%</code>).
        </p>
        {effectiveTakerFeeBps == null ? (
          <p className="small-text tone-warn">
            Invalid commission format. Using backend default fee settings.
          </p>
        ) : (
          <p className="small-text">
            Effective fee override: {effectiveTakerFeeBps.toFixed(2)} bps.
          </p>
        )}

        <label>
          Backtest Exit Mode
          <select
            value={backtestExitMode}
            onChange={(event) => setBacktestExitMode(event.target.value as BacktestExitMode)}
          >
            <option value="mean_revert">Mean Revert Exit</option>
            <option value="opposite_extreme">Opposite Extreme Exit</option>
          </select>
        </label>
        <p className="small-text">
          Controls analytics backtest/live-z marker logic. Live trade execution logic is unchanged.
        </p>

        <div className="mini-card">
          <h3>Current global timeframe</h3>
          <p>{timeframe}</p>
        </div>
      </SectionCard>

      <SectionCard title="API Credentials" subtitle="Session-only fields for local operator testing">
        <label>
          Kraken API Key
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="API key"
          />
        </label>

        <label>
          Kraken API Secret
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiSecret}
            onChange={(event) => setApiSecret(event.target.value)}
            placeholder="API secret"
          />
        </label>

        <label>
          Kraken API Passphrase
          <input
            type={showApiSecrets ? "text" : "password"}
            autoComplete="off"
            value={apiPassphrase}
            onChange={(event) => setApiPassphrase(event.target.value)}
            placeholder="Optional passphrase"
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={showApiSecrets}
            onChange={(event) => setShowApiSecrets(event.target.checked)}
          />
          Show values in clear text
        </label>

        <button
          type="button"
          className="danger"
          onClick={() => {
            setApiKey("");
            setApiSecret("");
            setApiPassphrase("");
          }}
        >
          Clear Session Keys
        </button>

        <p className="small-text">
          Session only: keys stay in browser memory and are not written to repo files.
        </p>
      </SectionCard>

      <SectionCard title="Safety Defaults" subtitle="Fail-closed behavior">
        <p className="tone-ok">Entry/exit require operator confirmation.</p>
        <p className="tone-ok">Emergency close is available for open spread flattening.</p>
        <p className="tone-ok">If gate state is unavailable, entry buttons remain disabled.</p>
        <p className="small-text">
          Live credentials should remain backend-managed and encrypted at rest.
        </p>
      </SectionCard>
    </div>
  );
}

function StatRow({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}): JSX.Element {
  return (
    <div className="stat-row">
      <div className="stat-label">{label}</div>
      <div className={`stat-value tone-${tone}`}>{value}</div>
    </div>
  );
}

export default App;
