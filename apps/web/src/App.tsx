import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import LineChart from "./components/LineChart";
import {
  allAcceptedDispatchAcknowledged,
  latestLifecycleState,
} from "./lib/orderLifecycle";
import { buildActiveTradeAnchor, buildExecutionMarkers } from "./lib/chartMarkers";
import {
  fetchStrategyExpectancy,
  fetchStrategyReplayTrades,
  fetchStrategyUiAuthStatus,
  verifyStrategyUiAccess,
  fetchStrategyPaperTrades,
  fetchStrategyCandidateInbox,
  runStrategyResearchSweep,
  submitStrategyCandidateAction,
  fetchExecutionDispatchMode,
  fetchExecutionOpenTrades,
  fetchExecutionPortfolioPositions,
  dispatchOrderIntent,
  fetchExecutionDecision,
  fetchKillSwitchState,
  fetchMarketMetrics,
  fetchOrderIntentHistory,
  fetchReconcile,
  updateKillSwitchState,
  fetchStrategyBacktest,
  fetchStrategyCues,
  fetchStrategyLiveZ,
  submitOrderIntent,
} from "./lib/api";
import {
  emptyPosition,
  isAddAllowed,
  isCloseAllowed,
  isEntryAllowed,
  isGateSafe,
  isReduceAllowed,
} from "./lib/tradeGuards";
import type {
  ChartMarker,
  BacktestExitMode,
  DispatchIntentResponse,
  DirectionHint,
  ExecutionDispatchModeResponse,
  ExecutionOpenTradesResponse,
  ExecutionAction,
  KillSwitchState,
  MarketMetricsResponse,
  OrderIntentHistoryResponse,
  ReconcileResponse,
  SpreadPosition,
  StrategyPairsCuesResponse,
  StrategyPairsCandidateInboxResponse,
  StrategyPairsExpectancyResponse,
  StrategyPairsPaperTradesResponse,
  StrategyPairsReplayTradesResponse,
  StrategyPairsResearchSweepResponse,
  StrategyZMethod,
  Timeframe,
  TimelineEvent,
  TradeSide,
} from "./types";
import logoDark from "./assets/logo-dark.png";
import logoLight from "./assets/logo-light.png";

type PageId =
  | "trade"
  | "analytics"
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
  qty: number;
}

interface LegExecutionOutcome {
  instrument: string;
  intentDecision: "ACCEPTED" | "BLOCKED";
  intentReason: string | null;
  dispatch: DispatchIntentResponse | null;
  dispatchError: string | null;
  history: OrderIntentHistoryResponse | null;
}

const NAV_ITEMS: Array<{ id: PageId; label: string }> = [
  { id: "trade", label: "Trade" },
  { id: "analytics", label: "Analytics" },
  { id: "settings", label: "Settings" },
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

function defaultAnalyticsChartBars(timeframe: Timeframe): number {
  if (timeframe === "1m") {
    return 2000;
  }
  if (timeframe === "15m") {
    return 1600;
  }
  return 1200;
}

function defaultAnalyticsPaperHours(timeframe: Timeframe): number {
  if (timeframe === "1m") {
    return 2160;
  }
  if (timeframe === "15m") {
    return 8760;
  }
  return 35040;
}

function defaultAnalyticsPaperLimit(timeframe: Timeframe): number {
  if (timeframe === "1m") {
    return 500;
  }
  if (timeframe === "15m") {
    return 1000;
  }
  return 2000;
}

function clampAnalyticsChartBars(value: number): number {
  return Math.floor(clampNumber(value, 120, 2000));
}

function clampAnalyticsPaperHours(value: number): number {
  return Math.floor(clampNumber(value, 1, 175_200));
}

function clampAnalyticsPaperLimit(value: number): number {
  return Math.floor(clampNumber(value, 1, 20_000));
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

function formatUsdCompact(value: number): string {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2);
}

function scaleEquityAbsolute(values: number[], baseUsd = 100): number[] {
  if (!values.length) {
    return values;
  }
  return values.map((value) => value * baseUsd);
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

const INSTRUMENT_MIN_LOT_BY_SYMBOL: Record<string, number> = {
  PF_ADAUSD: 1.0,
  PF_ARBUSD: 1.0,
  PF_AVAXUSD: 0.01,
  PF_BNBUSD: 0.01,
  PF_DOGEUSD: 1.0,
  PF_ETHUSD: 0.001,
  PF_HYPEUSD: 0.1,
  PF_LINKUSD: 0.1,
  PF_PEPEUSD: 1000.0,
  PF_SOLUSD: 0.01,
  PF_SUIUSD: 1.0,
  PF_TAOUSD: 0.01,
  PF_XBTUSD: 0.0001,
  PF_XRPUSD: 1.0,
};

function normalizePerpSymbol(rawInstrument: string): string {
  const upper = rawInstrument.trim().toUpperCase();
  return upper.startsWith("PI_") ? `PF_${upper.slice(3)}` : upper;
}

function decimalPlacesForStep(step: number): number {
  let decimals = 0;
  let scaled = step;
  while (decimals < 8 && Math.abs(Math.round(scaled) - scaled) > 1e-9) {
    scaled *= 10;
    decimals += 1;
  }
  return decimals;
}

function quantizeDownToStep(value: number, step: number): number {
  const units = Math.floor(value / step + 1e-9);
  const quantized = units * step;
  const decimals = decimalPlacesForStep(step);
  return Number(quantized.toFixed(decimals));
}

function quantizeNearestToStep(value: number, step: number): number {
  const units = Math.max(1, Math.round(value / step));
  const quantized = units * step;
  const decimals = decimalPlacesForStep(step);
  return Number(quantized.toFixed(decimals));
}

function formatQtyForStep(qty: number, step?: number): string {
  if (!Number.isFinite(qty)) {
    return "--";
  }
  if (step == null || !Number.isFinite(step) || step <= 0) {
    return qty.toFixed(4);
  }
  const decimals = decimalPlacesForStep(step);
  return qty.toFixed(decimals);
}

const DEFAULT_SIZING_TOLERANCE_NOTIONAL_DRIFT_PCT = 12;
const DEFAULT_SIZING_TOLERANCE_HEDGE_RATIO_DRIFT_PCT = 25;

interface SpreadSizingPlan {
  targetNotionalUsd: number;
  targetHedgeRatio: number;
  leftInstrument: string;
  rightInstrument: string;
  leftSide: TradeSide;
  rightSide: TradeSide;
  referenceLeftPrice: number;
  referenceRightPrice: number;
  leftStep: number | null;
  rightStep: number | null;
  rawLeftQty: number;
  rawRightQty: number;
  plannedLeftQty: number;
  plannedRightQty: number;
  achievedNotionalUsd: number;
  achievedHedgeRatio: number;
  notionalDriftPct: number;
  hedgeRatioDriftPct: number;
  toleranceNotionalDriftPct: number;
  toleranceHedgeRatioDriftPct: number;
  driftWithinTolerance: boolean;
  adjusted: boolean;
  capApplied: boolean;
}

interface SpreadSizingPlanResult {
  plan: SpreadSizingPlan | null;
  reason: string | null;
}

interface PairNotionalRules {
  minimumNotionalUsd: number;
  incrementNotionalUsd: number;
}

function relativeDriftPct(target: number, achieved: number): number {
  if (!Number.isFinite(target) || Math.abs(target) <= 1e-12) {
    return 0;
  }
  return (Math.abs(achieved - target) / Math.abs(target)) * 100;
}

function deriveLegSides(
  direction: Exclude<DirectionHint, "NONE">,
  action: ExecutionAction
): { leftSide: TradeSide; rightSide: TradeSide } {
  const isEntry = action === "ENTRY";
  if (direction === "LONG_SPREAD") {
    return { leftSide: isEntry ? "BUY" : "SELL", rightSide: isEntry ? "SELL" : "BUY" };
  }
  return { leftSide: isEntry ? "SELL" : "BUY", rightSide: isEntry ? "BUY" : "SELL" };
}

function referencePriceForSide(
  metrics: MarketMetricsResponse | null,
  side: TradeSide
): number | null {
  if (!metrics) {
    return null;
  }
  const raw = side === "BUY" ? (metrics.ask ?? metrics.mark) : (metrics.bid ?? metrics.mark);
  return Number.isFinite(raw) && raw > 0 ? raw : null;
}

function deriveSpreadSizingPlan(params: {
  targetNotionalUsd: number;
  leftInstrument: string;
  rightInstrument: string;
  hedgeRatio: number | null | undefined;
  direction: Exclude<DirectionHint, "NONE">;
  action: ExecutionAction;
  leftMetrics: MarketMetricsResponse | null;
  rightMetrics: MarketMetricsResponse | null;
  toleranceNotionalDriftPct: number;
  toleranceHedgeRatioDriftPct: number;
  maxLeftQty?: number | null;
  maxRightQty?: number | null;
}): SpreadSizingPlanResult {
  if (!Number.isFinite(params.targetNotionalUsd) || params.targetNotionalUsd <= 0) {
    return { plan: null, reason: "Target notional (USD) must be greater than 0." };
  }

  const targetHedgeRatio =
    params.hedgeRatio != null && Number.isFinite(params.hedgeRatio) && params.hedgeRatio > 0
      ? Math.abs(params.hedgeRatio)
      : 1;
  const { leftSide, rightSide } = deriveLegSides(params.direction, params.action);
  const referenceLeftPrice = referencePriceForSide(params.leftMetrics, leftSide);
  const referenceRightPrice = referencePriceForSide(params.rightMetrics, rightSide);
  if (
    referenceLeftPrice == null ||
    !Number.isFinite(referenceLeftPrice) ||
    referenceRightPrice == null ||
    !Number.isFinite(referenceRightPrice)
  ) {
    return {
      plan: null,
      reason: "Live bid/ask prices are unavailable for sizing. Wait for fresh market metrics.",
    };
  }

  const leftNotionalFraction = 1 / (1 + targetHedgeRatio);
  const rightNotionalFraction = targetHedgeRatio / (1 + targetHedgeRatio);
  if (
    !Number.isFinite(leftNotionalFraction) ||
    leftNotionalFraction <= 0 ||
    !Number.isFinite(rightNotionalFraction) ||
    rightNotionalFraction <= 0
  ) {
    return {
      plan: null,
      reason: "Unable to derive executable leg quantities from target notional and prices.",
    };
  }

  const targetLeftNotionalUsd = params.targetNotionalUsd * leftNotionalFraction;
  const targetRightNotionalUsd = params.targetNotionalUsd * rightNotionalFraction;
  const rawLeftQty = targetLeftNotionalUsd / referenceLeftPrice;
  const rawRightQty = targetRightNotionalUsd / referenceRightPrice;
  if (!Number.isFinite(rawLeftQty) || rawLeftQty <= 0 || !Number.isFinite(rawRightQty) || rawRightQty <= 0) {
    return { plan: null, reason: "Sizing result is invalid for this pair at current prices." };
  }

  const leftStep = INSTRUMENT_MIN_LOT_BY_SYMBOL[normalizePerpSymbol(params.leftInstrument)] ?? null;
  const rightStep = INSTRUMENT_MIN_LOT_BY_SYMBOL[normalizePerpSymbol(params.rightInstrument)] ?? null;
  let plannedLeftQty =
    leftStep != null && Number.isFinite(leftStep) && leftStep > 0
      ? quantizeNearestToStep(rawLeftQty, leftStep)
      : rawLeftQty;
  let plannedRightQty =
    rightStep != null && Number.isFinite(rightStep) && rightStep > 0
      ? quantizeNearestToStep(rawRightQty, rightStep)
      : rawRightQty;
  let capApplied = false;

  if (params.maxLeftQty != null && Number.isFinite(params.maxLeftQty) && params.maxLeftQty > 0) {
    if (plannedLeftQty > params.maxLeftQty) {
      plannedLeftQty =
        leftStep != null && leftStep > 0
          ? quantizeDownToStep(params.maxLeftQty, leftStep)
          : params.maxLeftQty;
      capApplied = true;
    }
  }
  if (params.maxRightQty != null && Number.isFinite(params.maxRightQty) && params.maxRightQty > 0) {
    if (plannedRightQty > params.maxRightQty) {
      plannedRightQty =
        rightStep != null && rightStep > 0
          ? quantizeDownToStep(params.maxRightQty, rightStep)
          : params.maxRightQty;
      capApplied = true;
    }
  }

  if (!Number.isFinite(plannedLeftQty) || plannedLeftQty <= 0) {
    return {
      plan: null,
      reason: `Left leg quantity is below minimum lot step for ${formatInstrumentLabel(
        params.leftInstrument
      )}.`,
    };
  }
  if (!Number.isFinite(plannedRightQty) || plannedRightQty <= 0) {
    return {
      plan: null,
      reason: `Right leg quantity is below minimum lot step for ${formatInstrumentLabel(
        params.rightInstrument
      )}.`,
    };
  }

  const achievedLeftNotionalUsd = Math.abs(referenceLeftPrice * plannedLeftQty);
  const achievedRightNotionalUsd = Math.abs(referenceRightPrice * plannedRightQty);
  const achievedNotionalUsd = achievedLeftNotionalUsd + achievedRightNotionalUsd;
  const achievedHedgeRatio =
    achievedLeftNotionalUsd > 0 ? achievedRightNotionalUsd / achievedLeftNotionalUsd : 0;
  const notionalDriftPct = relativeDriftPct(params.targetNotionalUsd, achievedNotionalUsd);
  const hedgeRatioDriftPct = relativeDriftPct(targetHedgeRatio, achievedHedgeRatio);
  const driftWithinTolerance =
    notionalDriftPct <= params.toleranceNotionalDriftPct + 1e-9 &&
    hedgeRatioDriftPct <= params.toleranceHedgeRatioDriftPct + 1e-9;

  return {
    plan: {
      targetNotionalUsd: params.targetNotionalUsd,
      targetHedgeRatio,
      leftInstrument: params.leftInstrument,
      rightInstrument: params.rightInstrument,
      leftSide,
      rightSide,
      referenceLeftPrice,
      referenceRightPrice,
      leftStep,
      rightStep,
      rawLeftQty,
      rawRightQty,
      plannedLeftQty,
      plannedRightQty,
      achievedNotionalUsd,
      achievedHedgeRatio,
      notionalDriftPct,
      hedgeRatioDriftPct,
      toleranceNotionalDriftPct: params.toleranceNotionalDriftPct,
      toleranceHedgeRatioDriftPct: params.toleranceHedgeRatioDriftPct,
      driftWithinTolerance,
      adjusted:
        Math.abs(plannedLeftQty - rawLeftQty) > 1e-9 || Math.abs(plannedRightQty - rawRightQty) > 1e-9,
      capApplied,
    },
    reason: null,
  };
}

function normalizeUsdValue(value: number): number {
  return Number(value.toFixed(2));
}

function derivePairNotionalRules(params: {
  leftInstrument: string;
  rightInstrument: string;
  hedgeRatio: number | null | undefined;
  leftMetrics: MarketMetricsResponse | null;
  rightMetrics: MarketMetricsResponse | null;
  toleranceNotionalDriftPct: number;
  toleranceHedgeRatioDriftPct: number;
}): PairNotionalRules {
  const targetHedgeRatio =
    params.hedgeRatio != null && Number.isFinite(params.hedgeRatio) && params.hedgeRatio > 0
      ? Math.abs(params.hedgeRatio)
      : 1;
  const leftStep =
    INSTRUMENT_MIN_LOT_BY_SYMBOL[normalizePerpSymbol(params.leftInstrument)] ?? 1;
  const rightStep =
    INSTRUMENT_MIN_LOT_BY_SYMBOL[normalizePerpSymbol(params.rightInstrument)] ?? 1;

  const longSides = deriveLegSides("LONG_SPREAD", "ENTRY");
  const shortSides = deriveLegSides("SHORT_SPREAD", "ENTRY");

  const leftLong = referencePriceForSide(params.leftMetrics, longSides.leftSide);
  const rightLong = referencePriceForSide(params.rightMetrics, longSides.rightSide);
  const leftShort = referencePriceForSide(params.leftMetrics, shortSides.leftSide);
  const rightShort = referencePriceForSide(params.rightMetrics, shortSides.rightSide);

  if (
    leftLong == null ||
    rightLong == null ||
    leftShort == null ||
    rightShort == null ||
    !Number.isFinite(leftLong) ||
    !Number.isFinite(rightLong) ||
    !Number.isFinite(leftShort) ||
    !Number.isFinite(rightShort)
  ) {
    return { minimumNotionalUsd: 1, incrementNotionalUsd: 1 };
  }

  const ratioScale = 1 + targetHedgeRatio;
  if (!Number.isFinite(ratioScale) || ratioScale <= 0) {
    return { minimumNotionalUsd: 1, incrementNotionalUsd: 1 };
  }

  const directionalIncrements: number[] = [
    leftStep * leftLong * ratioScale,
    leftStep * leftShort * ratioScale,
  ];
  if (targetHedgeRatio > 1e-9) {
    directionalIncrements.push(
      rightStep * rightLong * (ratioScale / targetHedgeRatio),
      rightStep * rightShort * (ratioScale / targetHedgeRatio)
    );
  }
  const rawIncrementNotional = directionalIncrements
    .filter((value) => Number.isFinite(value) && value > 0)
    .reduce((acc, value) => Math.min(acc, value), Number.POSITIVE_INFINITY);
  const incrementNotionalUsd = normalizeUsdValue(
    Math.max(Number.isFinite(rawIncrementNotional) ? rawIncrementNotional : 1, 1)
  );
  const rawMinimumNotional = incrementNotionalUsd;
  const alignedBaseMinimum = normalizeUsdValue(
    Math.ceil(Math.max(rawMinimumNotional, incrementNotionalUsd) / incrementNotionalUsd) *
      incrementNotionalUsd
  );

  const maxIterations = 240;
  for (let i = 0; i < maxIterations; i += 1) {
    const candidate = normalizeUsdValue(alignedBaseMinimum + i * incrementNotionalUsd);
    const longPlan = deriveSpreadSizingPlan({
      targetNotionalUsd: candidate,
      leftInstrument: params.leftInstrument,
      rightInstrument: params.rightInstrument,
      hedgeRatio: targetHedgeRatio,
      direction: "LONG_SPREAD",
      action: "ENTRY",
      leftMetrics: params.leftMetrics,
      rightMetrics: params.rightMetrics,
      toleranceNotionalDriftPct: params.toleranceNotionalDriftPct,
      toleranceHedgeRatioDriftPct: params.toleranceHedgeRatioDriftPct,
    });
    const shortPlan = deriveSpreadSizingPlan({
      targetNotionalUsd: candidate,
      leftInstrument: params.leftInstrument,
      rightInstrument: params.rightInstrument,
      hedgeRatio: targetHedgeRatio,
      direction: "SHORT_SPREAD",
      action: "ENTRY",
      leftMetrics: params.leftMetrics,
      rightMetrics: params.rightMetrics,
      toleranceNotionalDriftPct: params.toleranceNotionalDriftPct,
      toleranceHedgeRatioDriftPct: params.toleranceHedgeRatioDriftPct,
    });
    if (
      longPlan.plan != null &&
      shortPlan.plan != null &&
      longPlan.plan.notionalDriftPct <= params.toleranceNotionalDriftPct + 1e-9 &&
      shortPlan.plan.notionalDriftPct <= params.toleranceNotionalDriftPct + 1e-9
    ) {
      return {
        minimumNotionalUsd: candidate,
        incrementNotionalUsd,
      };
    }
  }

  return {
    minimumNotionalUsd: alignedBaseMinimum,
    incrementNotionalUsd,
  };
}

function isNotionalAlignedToRules(value: number, rules: PairNotionalRules): boolean {
  if (!Number.isFinite(value) || value < rules.minimumNotionalUsd) {
    return false;
  }
  const steps = (value - rules.minimumNotionalUsd) / rules.incrementNotionalUsd;
  return Math.abs(steps - Math.round(steps)) < 1e-6;
}

function alignNotionalToRules(value: number, rules: PairNotionalRules): number {
  if (!Number.isFinite(value)) {
    return rules.minimumNotionalUsd;
  }
  if (value <= rules.minimumNotionalUsd) {
    return rules.minimumNotionalUsd;
  }
  const steps = Math.round((value - rules.minimumNotionalUsd) / rules.incrementNotionalUsd);
  return normalizeUsdValue(rules.minimumNotionalUsd + steps * rules.incrementNotionalUsd);
}

function formatSizingDriftBlockedMessage(plan: SpreadSizingPlan): string {
  return `Notional sizing drift exceeds tolerance (${plan.notionalDriftPct.toFixed(
    2
  )}% > ${plan.toleranceNotionalDriftPct.toFixed(
    2
  )}%). Increase target notional or adjust by pair increment.`;
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

function deriveOpportunityStatus(
  cue: StrategyPairsCuesResponse["cues"][number]["cue"],
  dataDegraded: boolean
): { label: "READY" | "WAIT" | "DATA"; toneClass: "tone-ok" | "tone-warn" | "tone-bad" } {
  if (dataDegraded) {
    return { label: "DATA", toneClass: "tone-bad" };
  }
  const tradePass = cue.trade_gate?.pass ?? cue.actionable;
  if (tradePass) {
    return { label: "READY", toneClass: "tone-ok" };
  }
  return { label: "WAIT", toneClass: "tone-warn" };
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


function buildSpreadLegs(
  leftInstrument: string,
  rightInstrument: string,
  direction: Exclude<DirectionHint, "NONE">,
  action: ExecutionAction,
  leftQty: number,
  rightQty: number
): SpreadLeg[] {
  const isEntry = action === "ENTRY";
  if (direction === "LONG_SPREAD") {
    return [
      { instrument: leftInstrument, side: isEntry ? "BUY" : "SELL", qty: leftQty },
      { instrument: rightInstrument, side: isEntry ? "SELL" : "BUY", qty: rightQty },
    ];
  }
  return [
    { instrument: leftInstrument, side: isEntry ? "SELL" : "BUY", qty: leftQty },
    { instrument: rightInstrument, side: isEntry ? "BUY" : "SELL", qty: rightQty },
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
  const [uiAuthLoading, setUiAuthLoading] = useState<boolean>(true);
  const [uiAuthEnabled, setUiAuthEnabled] = useState<boolean>(false);
  const [uiUnlocked, setUiUnlocked] = useState<boolean>(false);
  const [uiPassword, setUiPassword] = useState<string>("");
  const [uiAuthError, setUiAuthError] = useState<string | null>(null);

  const [cuesResponse, setCuesResponse] = useState<StrategyPairsCuesResponse | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [coreLoading, setCoreLoading] = useState(false);

  const [selectedPairId, setSelectedPairId] = usePersistentState<string>("cp.pair", "");

  const [killSwitch, setKillSwitch] = useState<KillSwitchState | null>(null);
  const [executionDispatchMode, setExecutionDispatchMode] =
    useState<ExecutionDispatchModeResponse | null>(null);
  const [killSwitchUpdating, setKillSwitchUpdating] = useState<boolean>(false);
  const [leftDecisionAllowed, setLeftDecisionAllowed] = useState<boolean>(false);
  const [rightDecisionAllowed, setRightDecisionAllowed] = useState<boolean>(false);
  const [reconcileResponse, setReconcileResponse] = useState<ReconcileResponse | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);

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
  const [analyticsChartBars, setAnalyticsChartBars] = useState<number>(() =>
    defaultAnalyticsChartBars("1m")
  );
  const [analyticsPaperHours, setAnalyticsPaperHours] = useState<number>(() =>
    defaultAnalyticsPaperHours("1m")
  );
  const [analyticsPaperLimit, setAnalyticsPaperLimit] = useState<number>(() =>
    defaultAnalyticsPaperLimit("1m")
  );
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
  const [candidateInbox, setCandidateInbox] =
    useState<StrategyPairsCandidateInboxResponse | null>(null);
  const [candidateInboxLoading, setCandidateInboxLoading] = useState(false);
  const [candidateInboxError, setCandidateInboxError] = useState<string | null>(null);
  const [candidateActionBusyId, setCandidateActionBusyId] = useState<string | null>(null);
  const [candidateActionMessage, setCandidateActionMessage] = useState<string | null>(null);
  const [headerLeftMetrics, setHeaderLeftMetrics] = useState<MarketMetricsResponse | null>(null);
  const [headerRightMetrics, setHeaderRightMetrics] = useState<MarketMetricsResponse | null>(null);
  const [headerMetricsError, setHeaderMetricsError] = useState<string | null>(null);
  const [spreadSize, setSpreadSize] = useState<string>("1000");
  const [operatorConfirmed, setOperatorConfirmed] = useState<boolean>(false);
  const [tradeMessage, setTradeMessage] = useState<string>("No trade submitted yet.");
  const [submitting, setSubmitting] = useState(false);

  const [positions, setPositions] = useState<Record<string, SpreadPosition>>({});
  const [openTradesResponse, setOpenTradesResponse] = useState<ExecutionOpenTradesResponse | null>(
    null
  );
  const [openTradesError, setOpenTradesError] = useState<string | null>(null);
  const [liveZTick, setLiveZTick] = useState<{ pairId: string; z: number; ts: string } | null>(
    null
  );
  const [timelineByPair, setTimelineByPair] = usePersistentState<Record<string, TimelineEvent[]>>(
    "cp.timeline",
    {}
  );
  const [intentHistoryByPair, setIntentHistoryByPair] = useState<
    Record<string, OrderIntentHistoryResponse[]>
  >({});
  const positionsRefreshSeqRef = useRef(0);
  const positionsRef = useRef<Record<string, SpreadPosition>>({});
  const openTradesRef = useRef<ExecutionOpenTradesResponse | null>(null);

  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);

  useEffect(() => {
    openTradesRef.current = openTradesResponse;
  }, [openTradesResponse]);

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
  const currentOpenTrade = useMemo(
    () => openTradesResponse?.trades.find((trade) => trade.pair_id === currentPairId) ?? null,
    [openTradesResponse, currentPairId]
  );
  const tradeZSeries = useMemo(() => {
    if (!zSeries.length) {
      return zSeries;
    }
    if (!liveZTick || liveZTick.pairId !== currentPairId || !Number.isFinite(liveZTick.z)) {
      return zSeries;
    }
    const next = [...zSeries];
    next[next.length - 1] = liveZTick.z;
    return next;
  }, [zSeries, liveZTick, currentPairId]);
  const tradeZTimestamps = useMemo(() => {
    if (!zTimestamps.length) {
      return zTimestamps;
    }
    if (!liveZTick || liveZTick.pairId !== currentPairId || !liveZTick.ts.trim().length) {
      return zTimestamps;
    }
    const next = [...zTimestamps];
    next[next.length - 1] = liveZTick.ts;
    return next;
  }, [zTimestamps, liveZTick, currentPairId]);
  const currentLiveZ = useMemo(() => {
    if (!tradeZSeries.length) {
      return null;
    }
    return tradeZSeries[tradeZSeries.length - 1];
  }, [tradeZSeries]);
  const currentLiveZUpdatedAt = useMemo(() => {
    if (liveZTick && liveZTick.pairId === currentPairId) {
      return liveZTick.ts;
    }
    if (!tradeZTimestamps.length) {
      return null;
    }
    return tradeZTimestamps[tradeZTimestamps.length - 1];
  }, [liveZTick, currentPairId, tradeZTimestamps]);
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

  const spreadSizeNumber = Number.parseFloat(spreadSize);
  const sizingToleranceNotionalDriftPct =
    executionDispatchMode?.sizing_tolerance_notional_drift_pct ??
    DEFAULT_SIZING_TOLERANCE_NOTIONAL_DRIFT_PCT;
  const sizingToleranceHedgeRatioDriftPct =
    executionDispatchMode?.sizing_tolerance_hedge_ratio_drift_pct ??
    DEFAULT_SIZING_TOLERANCE_HEDGE_RATIO_DRIFT_PCT;
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

  const gateState = useMemo(
    () => ({
      killSwitchActive: killSwitch?.active ?? true,
      leftAllowed: leftDecisionAllowed,
      rightAllowed: rightDecisionAllowed,
      reconcileOk: reconcileResponse?.reconcile?.status === "OK",
    }),
    [killSwitch?.active, leftDecisionAllowed, rightDecisionAllowed, reconcileResponse]
  );
  const simGateBypass = executionDispatchMode?.mode === "SIMULATE_ACK";
  const effectiveGateState = simGateBypass
    ? {
        killSwitchActive: false,
        leftAllowed: true,
        rightAllowed: true,
        reconcileOk: true,
      }
    : gateState;
  const requiresLiveArm = executionDispatchMode?.requires_live_arm ?? true;
  const effectiveOperatorConfirmed = operatorConfirmed || !requiresLiveArm;

  const baseEntryGuard = {
    operatorConfirmed: effectiveOperatorConfirmed,
    operatorId,
    spreadSize: spreadSizeNumber,
    gateState: effectiveGateState,
  };

  const canLongEntry = isEntryAllowed(baseEntryGuard);
  const canShortEntry = isEntryAllowed(baseEntryGuard);
  const canAddExposure = isAddAllowed(currentPosition, baseEntryGuard);
  const canReduceExposure = isReduceAllowed(
    currentPosition,
    effectiveOperatorConfirmed,
    operatorId,
    spreadSizeNumber
  );
  const canCloseSpread = isCloseAllowed(currentPosition);

  const gateSafe = isGateSafe(effectiveGateState);
  const startupStatus = useMemo(() => {
    if (coreLoading) {
      return {
        tone: "warn" as const,
        text: "Market data is syncing. Strategy signals are warming up.",
      };
    }
    if (coreError) {
      return {
        tone: "bad" as const,
        text: "Live strategy data is unavailable. Fail-closed mode is active.",
      };
    }
    return {
      tone: "ok" as const,
      text: "Market data is live.",
    };
  }, [coreLoading, coreError]);

  const refreshPositions = async (): Promise<void> => {
    const refreshSeq = ++positionsRefreshSeqRef.current;
    const [response, openTrades] = await Promise.all([
      fetchExecutionPortfolioPositions(exchange, accountId),
      fetchExecutionOpenTrades(exchange, accountId),
    ]);
    if (refreshSeq !== positionsRefreshSeqRef.current) {
      return;
    }
    const next: Record<string, SpreadPosition> = {};
    for (const row of response.positions) {
      next[row.pair_id] = {
        direction: row.direction,
        totalSize: row.total_size,
        avgEntryZ: row.avg_entry_z,
        updatedAt: row.updated_at,
      };
    }
    const hadPreviousPositions = Object.keys(positionsRef.current).length > 0;
    const hadPreviousTrades = (openTradesRef.current?.trades.length ?? 0) > 0;
    const incomingPositionsEmpty = Object.keys(next).length === 0;
    const incomingTradesEmpty = openTrades.trades.length === 0;
    const dataDegraded = coreError != null || openTrades.warnings.length > 0;
    const shouldRetainPositions = dataDegraded && incomingPositionsEmpty && hadPreviousPositions;
    const shouldRetainTrades = dataDegraded && incomingTradesEmpty && hadPreviousTrades;

    setPositions(shouldRetainPositions ? positionsRef.current : next);
    setOpenTradesResponse(shouldRetainTrades ? openTradesRef.current : openTrades);

    const warningParts: string[] = [];
    if (openTrades.warnings.length) {
      warningParts.push(openTrades.warnings.join(" | "));
    }
    if (shouldRetainPositions || shouldRetainTrades) {
      warningParts.push("Data degraded: showing last known open-trade snapshot.");
    }
    setOpenTradesError(warningParts.length ? warningParts.join(" | ") : null);
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
        const cues =
          takerFeeBpsOverride == null
            ? fetchStrategyCues(timeframe, 20)
            : fetchStrategyCues(timeframe, 20, takerFeeBpsOverride);
        const response = await cues;
        if (cancelled) {
          return;
        }
        setCuesResponse(response);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setCoreError(
          `Unable to load strategy data from live services: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      } finally {
        if (!cancelled && firstLoad) {
          setCoreLoading(false);
        }
        inFlight = false;
      }
    };

    void runCoreRefresh(true);
    const coreRefreshIntervalMs = page === "trade" ? 3_000 : analyticsRefreshMs(timeframe);
    const intervalId = window.setInterval(() => {
      void runCoreRefresh(false);
    }, coreRefreshIntervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [timeframe, uiAccessGranted, takerFeeBpsOverride, page]);

  useEffect(() => {
    if (!uiAccessGranted) {
      return;
    }
    let cancelled = false;
    void fetchExecutionDispatchMode()
      .then((mode) => {
        if (!cancelled) {
          setExecutionDispatchMode(mode);
        }
      })
      .catch(() => {
        if (!cancelled) {
          // Fail-closed for unknown mode: require explicit live arming.
          setExecutionDispatchMode({
            mode: "FAIL_CLOSED",
            requires_live_arm: true,
            sizing_tolerance_notional_drift_pct: DEFAULT_SIZING_TOLERANCE_NOTIONAL_DRIFT_PCT,
            sizing_tolerance_hedge_ratio_drift_pct: DEFAULT_SIZING_TOLERANCE_HEDGE_RATIO_DRIFT_PCT,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [uiAccessGranted]);

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
        setOpenTradesError("Open trades refresh failed. Retaining last known state.");
      }
    });
    const refreshIntervalMs = page === "trade" ? 2_000 : 10_000;
    const intervalId = window.setInterval(() => {
      void refreshPositions().catch(() => {
        if (!cancelled) {
          setOpenTradesError("Open trades refresh failed. Retaining last known state.");
        }
      });
    }, refreshIntervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [exchange, accountId, uiAccessGranted, page, coreError]);

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

      const bars = clampAnalyticsChartBars(analyticsChartBars);

      try {
        const liveZRequest =
          takerFeeBpsOverride == null
            ? fetchStrategyLiveZ(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
                bars,
                undefined,
                backtestExitMode
              )
            : fetchStrategyLiveZ(
                timeframe,
                selectedCueRow.cue.pair_id,
                bars,
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
  }, [
    selectedCueRow,
    timeframe,
    uiAccessGranted,
    takerFeeBpsOverride,
    backtestExitMode,
    analyticsChartBars,
  ]);

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
          clampAnalyticsPaperHours(analyticsPaperHours),
          clampAnalyticsPaperLimit(analyticsPaperLimit),
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
  }, [
    selectedCueRow,
    timeframe,
    backtestExitMode,
    uiAccessGranted,
    analyticsPaperHours,
    analyticsPaperLimit,
  ]);

  useEffect(() => {
    if (!uiAccessGranted || page !== "trade" || !selectedCueRow) {
      return;
    }
    let cancelled = false;
    let inFlight = false;
    const pairId = selectedCueRow.cue.pair_id;

    const tickLiveZ = async (): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      try {
        const tickerWindowBars = clampAnalyticsChartBars(analyticsChartBars);
        const response =
          takerFeeBpsOverride == null
            ? await fetchStrategyLiveZ(
                timeframe,
                pairId,
                2,
                tickerWindowBars,
                undefined,
                backtestExitMode
              )
            : await fetchStrategyLiveZ(
                timeframe,
                pairId,
                2,
                tickerWindowBars,
                takerFeeBpsOverride,
                backtestExitMode
              );
        if (cancelled || !response.points.length) {
          return;
        }
        const point = response.points[response.points.length - 1];
        setLiveZTick({ pairId, z: point.z, ts: point.ts });
      } catch {
        // Keep prior ticker value on transient errors.
      } finally {
        inFlight = false;
      }
    };

    void tickLiveZ();
    const intervalId = window.setInterval(() => {
      void tickLiveZ();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    uiAccessGranted,
    page,
    selectedCueRow,
    timeframe,
    takerFeeBpsOverride,
    backtestExitMode,
    analyticsChartBars,
  ]);

  useEffect(() => {
    if (!uiAccessGranted || page !== "analytics") {
      return;
    }
    let cancelled = false;
    let inFlight = false;
    setCandidateInboxLoading(true);

    const runCandidateInboxRefresh = async (firstLoad = false): Promise<void> => {
      if (cancelled || inFlight) {
        return;
      }
      inFlight = true;
      if (firstLoad) {
        setCandidateInboxLoading(true);
      }
      try {
        const response = await fetchStrategyCandidateInbox(timeframe, 3);
        if (cancelled) {
          return;
        }
        setCandidateInbox(response);
        setCandidateInboxError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setCandidateInbox(null);
        setCandidateInboxError(
          `Candidate inbox unavailable: ${error instanceof Error ? error.message : String(error)}`
        );
      } finally {
        if (!cancelled && firstLoad) {
          setCandidateInboxLoading(false);
        }
        inFlight = false;
      }
    };

    void runCandidateInboxRefresh(true);
    const intervalId = window.setInterval(() => {
      void runCandidateInboxRefresh(false);
    }, analyticsRefreshMs(timeframe));

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [page, timeframe, uiAccessGranted]);

  useEffect(() => {
    setExpectancyResult(null);
    setReplayResult(null);
    setResearchSweepResult(null);
    setExpectancyError(null);
    setReplayError(null);
    setResearchSweepError(null);
    setCandidateActionMessage(null);
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
      if (!dryRun) {
        const inbox = await fetchStrategyCandidateInbox(timeframe, 3);
        setCandidateInbox(inbox);
        setCandidateInboxError(null);
      }
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

  const runCandidateAction = useCallback(
    async (
      candidateId: string,
      action: "PROMOTE" | "HOLD" | "REJECT",
      note?: string
    ): Promise<void> => {
      if (!operatorId.trim().length) {
        setCandidateActionMessage("Operator ID is required to action candidates.");
        return;
      }
      const row = candidateInbox?.rows.find((entry) => entry.candidate_id === candidateId);
      if (!row) {
        setCandidateActionMessage("Candidate no longer available. Refresh and retry.");
        return;
      }
      const confirmMessage = `${action} ${formatPairLabel(row.pair_id)} ${row.timeframe} candidate?`;
      if (!window.confirm(confirmMessage)) {
        return;
      }

      setCandidateActionBusyId(candidateId);
      setCandidateActionMessage(null);
      try {
        const response = await submitStrategyCandidateAction({
          pair_id: row.pair_id,
          timeframe: row.timeframe,
          candidate_id: row.candidate_id,
          action,
          operator_id: operatorId,
          note: note ?? null,
          confirm: true,
        });
        const inbox = await fetchStrategyCandidateInbox(timeframe, 3);
        setCandidateInbox(inbox);
        setCandidateActionMessage(
          `${response.action} ${formatPairLabel(response.pair_id)} ${response.timeframe}: ${response.state_before} -> ${response.state_after}`
        );
      } catch (error) {
        setCandidateActionMessage(
          `Candidate action failed: ${error instanceof Error ? error.message : String(error)}`
        );
      } finally {
        setCandidateActionBusyId(null);
      }
    },
    [candidateInbox, operatorId, timeframe]
  );

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
    setAnalyticsChartBars(defaultAnalyticsChartBars(timeframe));
    setAnalyticsPaperHours(defaultAnalyticsPaperHours(timeframe));
    setAnalyticsPaperLimit(defaultAnalyticsPaperLimit(timeframe));
  }, [timeframe]);

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

  const toggleKillSwitch = useCallback(
    async (active: boolean): Promise<void> => {
      setKillSwitchUpdating(true);
      setGateError(null);
      try {
        const updated = await updateKillSwitchState({
          active,
          reason: active
            ? "manual kill switch enabled from spread execution panel"
            : "manual kill switch disabled from spread execution panel",
          actor: operatorId.trim().length ? operatorId : "operator-ui",
        });
        setKillSwitch(updated);
      } catch (error) {
        setGateError(
          `Kill switch update failed: ${error instanceof Error ? error.message : String(error)}`
        );
      } finally {
        setKillSwitchUpdating(false);
      }
    },
    [operatorId]
  );

  const executeTradeCommand = async (command: TradeCommand): Promise<void> => {
    if (!selectedCueRow) {
      setTradeMessage("No selected pair.");
      return;
    }

    const now = nowIso();
    const pairId = selectedCueRow.cue.pair_id;
    const current = positions[pairId] ?? emptyPosition(now);
    const currentOpenTradeSnapshot =
      openTradesResponse?.trades.find((trade) => trade.pair_id === pairId) ?? null;
    const openLeftLegQty =
      currentOpenTradeSnapshot?.legs.find(
        (leg) => leg.instrument === selectedCueRow.cue.left_instrument
      )?.qty ?? null;
    const openRightLegQty =
      currentOpenTradeSnapshot?.legs.find(
        (leg) => leg.instrument === selectedCueRow.cue.right_instrument
      )?.qty ?? null;
    const maxReducibleLeftQty =
      openLeftLegQty != null && Number.isFinite(openLeftLegQty) && openLeftLegQty > 0
        ? openLeftLegQty
        : current.totalSize;
    const maxReducibleRightQty =
      openRightLegQty != null && Number.isFinite(openRightLegQty) && openRightLegQty > 0
        ? openRightLegQty
        : undefined;
    const currentZ = Number.isFinite(currentLiveZ ?? NaN)
      ? (currentLiveZ as number)
      : selectedCueRow.cue.spread_z;

    let direction: Exclude<DirectionHint, "NONE">;
    let action: ExecutionAction;
    const targetNotionalUsd = spreadSizeNumber;
    const pairNotionalRules = derivePairNotionalRules({
      leftInstrument: selectedCueRow.cue.left_instrument,
      rightInstrument: selectedCueRow.cue.right_instrument,
      hedgeRatio: selectedCueRow.hedge_ratio,
      leftMetrics: headerLeftMetrics,
      rightMetrics: headerRightMetrics,
      toleranceNotionalDriftPct: sizingToleranceNotionalDriftPct,
      toleranceHedgeRatioDriftPct: sizingToleranceHedgeRatioDriftPct,
    });

    if (!Number.isFinite(currentZ)) {
      setTradeMessage("Current z-score unavailable. Wait for live data and retry.");
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
    } else {
      if (current.direction === "NONE" || current.totalSize <= 0) {
        setTradeMessage("No open spread to close.");
        return;
      }
      direction = current.direction;
      action = "EMERGENCY_STOP_CLOSE";
    }

    if (action !== "EMERGENCY_STOP_CLOSE") {
      if (!Number.isFinite(spreadSizeNumber) || spreadSizeNumber <= 0) {
        setTradeMessage("Target notional (USD) must be > 0.");
        return;
      }
      if (targetNotionalUsd < pairNotionalRules.minimumNotionalUsd) {
        setTradeMessage(
          `Target notional is below minimum for this pair ($${formatUsdCompact(
            pairNotionalRules.minimumNotionalUsd
          )}).`
        );
        return;
      }
      if (!isNotionalAlignedToRules(targetNotionalUsd, pairNotionalRules)) {
        setTradeMessage(
          `Target notional must move in $${formatUsdCompact(
            pairNotionalRules.incrementNotionalUsd
          )} increments above $${formatUsdCompact(pairNotionalRules.minimumNotionalUsd)}.`
        );
        return;
      }
    }

    let leftLegQty = 0;
    let rightLegQty = 0;
    let sizingPayload:
      | {
          target_notional_usd: number;
          target_hedge_ratio: number;
          reference_left_instrument: string;
          reference_right_instrument: string;
          reference_left_price: number;
          reference_right_price: number;
          planned_left_qty: number;
          planned_right_qty: number;
          achieved_notional_usd: number;
          achieved_hedge_ratio: number;
          notional_drift_pct: number;
          hedge_ratio_drift_pct: number;
          tolerance_notional_drift_pct: number;
          tolerance_hedge_ratio_drift_pct: number;
        }
      | undefined;
    if (action !== "EMERGENCY_STOP_CLOSE") {
      const planResult = deriveSpreadSizingPlan({
        targetNotionalUsd,
        leftInstrument: selectedCueRow.cue.left_instrument,
        rightInstrument: selectedCueRow.cue.right_instrument,
        hedgeRatio: selectedCueRow.hedge_ratio,
        direction,
        action,
        leftMetrics: headerLeftMetrics,
        rightMetrics: headerRightMetrics,
        toleranceNotionalDriftPct: sizingToleranceNotionalDriftPct,
        toleranceHedgeRatioDriftPct: sizingToleranceHedgeRatioDriftPct,
        maxLeftQty: action === "EXIT" ? maxReducibleLeftQty : undefined,
        maxRightQty: action === "EXIT" ? maxReducibleRightQty : undefined,
      });
      if (planResult.reason || !planResult.plan) {
        setTradeMessage(planResult.reason ?? "Sizing plan unavailable.");
        return;
      }
      const plan = planResult.plan;
      if (plan.notionalDriftPct > plan.toleranceNotionalDriftPct + 1e-9) {
        setTradeMessage(formatSizingDriftBlockedMessage(plan));
        return;
      }
      leftLegQty = plan.plannedLeftQty;
      rightLegQty = plan.plannedRightQty;
      sizingPayload = {
        target_notional_usd: plan.targetNotionalUsd,
        target_hedge_ratio: plan.targetHedgeRatio,
        reference_left_instrument: plan.leftInstrument,
        reference_right_instrument: plan.rightInstrument,
        reference_left_price: plan.referenceLeftPrice,
        reference_right_price: plan.referenceRightPrice,
        planned_left_qty: plan.plannedLeftQty,
        planned_right_qty: plan.plannedRightQty,
        achieved_notional_usd: plan.achievedNotionalUsd,
        achieved_hedge_ratio: plan.achievedHedgeRatio,
        notional_drift_pct: plan.notionalDriftPct,
        hedge_ratio_drift_pct: plan.hedgeRatioDriftPct,
        tolerance_notional_drift_pct: plan.toleranceNotionalDriftPct,
        tolerance_hedge_ratio_drift_pct: plan.toleranceHedgeRatioDriftPct,
      };
    } else {
      if (
        openLeftLegQty == null ||
        !Number.isFinite(openLeftLegQty) ||
        openLeftLegQty <= 0 ||
        openRightLegQty == null ||
        !Number.isFinite(openRightLegQty) ||
        openRightLegQty <= 0
      ) {
        setTradeMessage("Open-trade leg quantities are unavailable. Unable to close safely.");
        return;
      }
      leftLegQty = openLeftLegQty;
      rightLegQty = openRightLegQty;
    }
    const legs = buildSpreadLegs(
      selectedCueRow.cue.left_instrument,
      selectedCueRow.cue.right_instrument,
      direction,
      action,
      leftLegQty,
      rightLegQty
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
            qty: leg.qty,
            sizing: action === "EMERGENCY_STOP_CLOSE" ? undefined : sizingPayload,
            operator_confirmed: action === "EMERGENCY_STOP_CLOSE" ? false : effectiveOperatorConfirmed,
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
          setOpenTradesError("Open trades refresh failed. Retaining last known state.");
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
          zSeries={tradeZSeries}
          zTimestamps={tradeZTimestamps}
          zMarkers={tradeChartMarkers}
          analyticsError={analyticsError}
          currentPosition={currentPosition}
          openTrade={currentOpenTrade}
          openTradesCount={openTradesResponse?.trades.length ?? 0}
          openTradesError={openTradesError}
          liveCurrentZ={currentLiveZ}
          liveCurrentZUpdatedAt={currentLiveZUpdatedAt}
          intentHistory={currentIntentHistory}
          activeTradeAnchor={activeTradeAnchor}
          timeline={currentTimeline}
          spreadSize={spreadSize}
          operatorConfirmed={operatorConfirmed}
          operatorId={operatorId}
          setSpreadSize={setSpreadSize}
          setOperatorConfirmed={setOperatorConfirmed}
          setOperatorId={setOperatorId}
          canLongEntry={canLongEntry}
          canShortEntry={canShortEntry}
          canAddExposure={canAddExposure}
          canReduceExposure={canReduceExposure}
          canCloseSpread={canCloseSpread}
          requiresLiveArm={requiresLiveArm}
          dispatchMode={executionDispatchMode?.mode ?? "FAIL_CLOSED"}
          hedgeRatio={selectedCueRow?.hedge_ratio}
          leftMetrics={headerLeftMetrics}
          rightMetrics={headerRightMetrics}
          sizingToleranceNotionalDriftPct={sizingToleranceNotionalDriftPct}
          sizingToleranceHedgeRatioDriftPct={sizingToleranceHedgeRatioDriftPct}
          gateState={gateState}
          killSwitch={killSwitch}
          killSwitchUpdating={killSwitchUpdating}
          onToggleKillSwitch={toggleKillSwitch}
          reconcile={reconcileResponse?.reconcile ?? null}
          gateError={gateError}
          tradeMessage={tradeMessage}
          submitting={submitting}
          zChartHeight={tradeZChartHeight}
          dataDegraded={coreError != null}
          onCommand={executeTradeCommand}
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
          analyticsChartBars={analyticsChartBars}
          analyticsPaperHours={analyticsPaperHours}
          analyticsPaperLimit={analyticsPaperLimit}
          onAnalyticsChartBarsChange={setAnalyticsChartBars}
          onAnalyticsPaperHoursChange={setAnalyticsPaperHours}
          onAnalyticsPaperLimitChange={setAnalyticsPaperLimit}
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
          candidateInbox={candidateInbox}
          candidateInboxLoading={candidateInboxLoading}
          candidateInboxError={candidateInboxError}
          candidateActionBusyId={candidateActionBusyId}
          candidateActionMessage={candidateActionMessage}
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
          onCandidateAction={runCandidateAction}
          onDownloadExpectancy={downloadExpectancyResult}
          onDownloadReplay={downloadReplayResult}
          onDownloadSweep={downloadResearchSweepResult}
          chartHeight={analyticsChartHeight}
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
        setExchange={setExchange}
        setAccountId={setAccountId}
        setOperatorId={setOperatorId}
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
  style,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}): JSX.Element {
  return (
    <section className={`panel-card ${className ?? ""}`.trim()} style={style}>
      {title ? <h2>{title}</h2> : null}
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
  openTrade: ExecutionOpenTradesResponse["trades"][number] | null;
  openTradesCount: number;
  openTradesError: string | null;
  liveCurrentZ: number | null;
  liveCurrentZUpdatedAt: string | null;
  intentHistory: OrderIntentHistoryResponse[];
  activeTradeAnchor: { entryAt: string; entryZ: number; currentZ: number; deltaZ: number } | null;
  timeline: TimelineEvent[];
  spreadSize: string;
  operatorConfirmed: boolean;
  operatorId: string;
  setSpreadSize: (value: string) => void;
  setOperatorConfirmed: (value: boolean) => void;
  setOperatorId: (value: string) => void;
  canLongEntry: boolean;
  canShortEntry: boolean;
  canAddExposure: boolean;
  canReduceExposure: boolean;
  canCloseSpread: boolean;
  requiresLiveArm: boolean;
  dispatchMode: "FAIL_CLOSED" | "SIMULATE_ACK" | "LIVE_KRAKEN";
  hedgeRatio: number | null | undefined;
  leftMetrics: MarketMetricsResponse | null;
  rightMetrics: MarketMetricsResponse | null;
  sizingToleranceNotionalDriftPct: number;
  sizingToleranceHedgeRatioDriftPct: number;
  gateState: { killSwitchActive: boolean; leftAllowed: boolean; rightAllowed: boolean; reconcileOk: boolean };
  killSwitch: KillSwitchState | null;
  killSwitchUpdating: boolean;
  onToggleKillSwitch: (active: boolean) => Promise<void>;
  reconcile: ReconcileResponse["reconcile"];
  gateError: string | null;
  tradeMessage: string;
  submitting: boolean;
  zChartHeight: number;
  dataDegraded: boolean;
  onCommand: (command: TradeCommand) => Promise<void>;
}): JSX.Element {
  const [closeConfirmArmed, setCloseConfirmArmed] = useState(false);
  const selectedCue =
    props.cues?.cues.find((entry) => entry.cue.pair_id === props.selectedPairId) ??
    props.cues?.cues[0] ??
    null;
  const spreadSizeNumber = Number.parseFloat(props.spreadSize);
  const targetNotionalUsd = Number.isFinite(spreadSizeNumber) && spreadSizeNumber > 0 ? spreadSizeNumber : 0;
  const leftInstrument = selectedCue?.cue.left_instrument ?? "LEFT";
  const rightInstrument = selectedCue?.cue.right_instrument ?? "RIGHT";
  const openLeftLegQty =
    props.openTrade?.legs.find((leg) => leg.instrument === leftInstrument)?.qty ?? null;
  const openRightLegQty =
    props.openTrade?.legs.find((leg) => leg.instrument === rightInstrument)?.qty ?? null;
  const maxReduceLeftQty =
    openLeftLegQty != null && Number.isFinite(openLeftLegQty) && openLeftLegQty > 0
      ? openLeftLegQty
      : props.currentPosition.totalSize;
  const maxReduceRightQty =
    openRightLegQty != null && Number.isFinite(openRightLegQty) && openRightLegQty > 0
      ? openRightLegQty
      : undefined;
  const pairNotionalRules = useMemo(
    () =>
      derivePairNotionalRules({
        leftInstrument,
        rightInstrument,
        hedgeRatio: props.hedgeRatio,
        leftMetrics: props.leftMetrics,
        rightMetrics: props.rightMetrics,
        toleranceNotionalDriftPct: props.sizingToleranceNotionalDriftPct,
        toleranceHedgeRatioDriftPct: props.sizingToleranceHedgeRatioDriftPct,
      }),
    [
      leftInstrument,
      rightInstrument,
      props.hedgeRatio,
      props.leftMetrics,
      props.rightMetrics,
      props.sizingToleranceNotionalDriftPct,
      props.sizingToleranceHedgeRatioDriftPct,
    ]
  );
  const notionalValidationMessage = (): string | null => {
    if (!Number.isFinite(spreadSizeNumber) || spreadSizeNumber <= 0) {
      return "Target notional (USD) must be greater than 0.";
    }
    if (spreadSizeNumber < pairNotionalRules.minimumNotionalUsd) {
      return `Target notional is below minimum for this pair ($${formatUsdCompact(
        pairNotionalRules.minimumNotionalUsd
      )}).`;
    }
    if (!isNotionalAlignedToRules(spreadSizeNumber, pairNotionalRules)) {
      return `Target notional must move in $${formatUsdCompact(
        pairNotionalRules.incrementNotionalUsd
      )} increments above $${formatUsdCompact(pairNotionalRules.minimumNotionalUsd)}.`;
    }
    return null;
  };
  const handleSpreadSizeBlur = (): void => {
    if (!Number.isFinite(spreadSizeNumber)) {
      props.setSpreadSize(formatUsdCompact(pairNotionalRules.minimumNotionalUsd));
      return;
    }
    const normalized = alignNotionalToRules(spreadSizeNumber, pairNotionalRules);
    if (Math.abs(normalized - spreadSizeNumber) > 1e-6) {
      props.setSpreadSize(formatUsdCompact(normalized));
    }
  };
  const longEntrySizing = deriveSpreadSizingPlan({
    targetNotionalUsd,
    leftInstrument,
    rightInstrument,
    hedgeRatio: props.hedgeRatio,
    direction: "LONG_SPREAD",
    action: "ENTRY",
    leftMetrics: props.leftMetrics,
    rightMetrics: props.rightMetrics,
    toleranceNotionalDriftPct: props.sizingToleranceNotionalDriftPct,
    toleranceHedgeRatioDriftPct: props.sizingToleranceHedgeRatioDriftPct,
  });
  const shortEntrySizing = deriveSpreadSizingPlan({
    targetNotionalUsd,
    leftInstrument,
    rightInstrument,
    hedgeRatio: props.hedgeRatio,
    direction: "SHORT_SPREAD",
    action: "ENTRY",
    leftMetrics: props.leftMetrics,
    rightMetrics: props.rightMetrics,
    toleranceNotionalDriftPct: props.sizingToleranceNotionalDriftPct,
    toleranceHedgeRatioDriftPct: props.sizingToleranceHedgeRatioDriftPct,
  });
  const addExposureSizing =
    props.currentPosition.direction !== "NONE"
      ? deriveSpreadSizingPlan({
          targetNotionalUsd,
          leftInstrument,
          rightInstrument,
          hedgeRatio: props.hedgeRatio,
          direction: props.currentPosition.direction,
          action: "ENTRY",
          leftMetrics: props.leftMetrics,
          rightMetrics: props.rightMetrics,
          toleranceNotionalDriftPct: props.sizingToleranceNotionalDriftPct,
          toleranceHedgeRatioDriftPct: props.sizingToleranceHedgeRatioDriftPct,
        })
      : null;
  const reduceSizing =
    props.currentPosition.direction !== "NONE" && props.currentPosition.totalSize > 0
      ? deriveSpreadSizingPlan({
          targetNotionalUsd,
          leftInstrument,
          rightInstrument,
          hedgeRatio: props.hedgeRatio,
          direction: props.currentPosition.direction,
          action: "EXIT",
          leftMetrics: props.leftMetrics,
          rightMetrics: props.rightMetrics,
          toleranceNotionalDriftPct: props.sizingToleranceNotionalDriftPct,
          toleranceHedgeRatioDriftPct: props.sizingToleranceHedgeRatioDriftPct,
          maxLeftQty: maxReduceLeftQty,
          maxRightQty: maxReduceRightQty,
        })
      : null;

  const tradeGatePass = selectedCue ? selectedCue.cue.trade_gate?.pass ?? selectedCue.cue.actionable : false;
  const tradeGateReasons = selectedCue
    ? new Set<string>([
        ...(selectedCue.cue.trade_gate?.rationale_codes ?? []),
        ...(selectedCue.cue.setup_gate?.rationale_codes ?? selectedCue.cue.rationale_codes),
        ...(selectedCue.cue.cost_gate?.rationale_codes ?? []),
      ])
    : new Set<string>();
  const bypassExecutionGates = props.dispatchMode === "SIMULATE_ACK";

  const sizingReason = (
    result: SpreadSizingPlanResult | null,
    includeTolerance = true
  ): string | null => {
    if (!result) {
      return "No open spread position.";
    }
    if (result.reason) {
      return result.reason;
    }
    const plan = result.plan;
    if (!plan) {
      return "Sizing plan unavailable.";
    }
    if (includeTolerance && plan.notionalDriftPct > plan.toleranceNotionalDriftPct + 1e-9) {
      return formatSizingDriftBlockedMessage(plan);
    }
    return null;
  };

  const commonEntryDisableReason = (sizing: SpreadSizingPlanResult): string | null => {
    if (props.submitting) {
      return "Action in progress.";
    }
    if (props.requiresLiveArm && !props.operatorConfirmed) {
      return "Execution mode is SIM ONLY. Arm LIVE to enable entry actions.";
    }
    if (!props.operatorId.trim().length) {
      return "Operator ID is required.";
    }
    const notionalMessage = notionalValidationMessage();
    if (notionalMessage) {
      return notionalMessage;
    }
    const localSizingReason = sizingReason(sizing);
    if (localSizingReason) {
      return localSizingReason;
    }
    if (!bypassExecutionGates && props.gateState.killSwitchActive) {
      return "Kill switch is ACTIVE.";
    }
    if (!bypassExecutionGates && (!props.gateState.leftAllowed || !props.gateState.rightAllowed)) {
      return "Integrity gate is blocking one or both legs.";
    }
    if (!bypassExecutionGates && !props.gateState.reconcileOk) {
      return "Reconcile gate is NOT_OK.";
    }
    return null;
  };

  const strategyWarningMessage = (): string | null => {
    if (!selectedCue) {
      return null;
    }
    if (selectedCue.cue.trade_gate?.status === "WAIT" || tradeGateReasons.has("PERFORMANCE_HISTORY_WAIT")) {
      return "Warning: waiting for minimum paper-trade history.";
    }
    if (selectedCue.cue.trade_gate?.status === "UNAVAILABLE") {
      return "Warning: trade gate is unavailable.";
    }
    if (!tradeGatePass) {
      if (tradeGateReasons.has("AT_OR_BEYOND_STOP_BAND")) {
        return "Warning: spread is at or beyond stop band.";
      }
      if (tradeGateReasons.has("RETRACE_COOLDOWN_ACTIVE")) {
        return "Warning: retrace cooldown is active.";
      }
      if (tradeGateReasons.has("BELOW_ENTRY_BAND")) {
        return "Warning: |z| is below the entry threshold.";
      }
      if (tradeGateReasons.has("CHAMPION_DRIFT_BLOCKED")) {
        return "Warning: champion drift guard is active.";
      }
      if (tradeGateReasons.has("HEDGE_RATIO_UNSTABLE")) {
        return "Warning: hedge ratio stability is weak.";
      }
      if (tradeGateReasons.has("PERFORMANCE_GATE_BLOCKED")) {
        return "Warning: recent paper-trade profitability gate failed.";
      }
      if (tradeGateReasons.has("COST_GATE_BLOCKED")) {
        return "Warning: estimated costs exceed edge.";
      }
      return "Warning: setup/cost conditions are not favorable.";
    }
    return null;
  };

  const longEntryDisabledReason = commonEntryDisableReason(longEntrySizing);
  const shortEntryDisabledReason = commonEntryDisableReason(shortEntrySizing);
  const addExposureDisabledReason =
    (addExposureSizing ? commonEntryDisableReason(addExposureSizing) : null) ??
    (props.currentPosition.direction === "NONE"
      ? "No open spread position to add exposure."
      : null);
  const reduceNotionalMessage = notionalValidationMessage();
  const reduceExposureDisabledReason = props.submitting
    ? "Action in progress."
    : props.currentPosition.direction === "NONE" || props.currentPosition.totalSize <= 0
      ? "No open spread position to reduce."
      : props.requiresLiveArm && !props.operatorConfirmed
        ? "Execution mode is SIM ONLY. Arm LIVE to reduce."
        : !props.operatorId.trim().length
          ? "Operator ID is required."
          : reduceNotionalMessage
            ? reduceNotionalMessage
            : reduceSizing
              ? sizingReason(reduceSizing)
              : null;
  const longEntryDisabled = !!longEntryDisabledReason;
  const shortEntryDisabled = !!shortEntryDisabledReason;
  const addExposureDisabled = !!addExposureDisabledReason;
  const reduceExposureDisabled = !!reduceExposureDisabledReason;
  const closeSpreadDisabled = !props.canCloseSpread || props.submitting;
  const closeSpreadDisabledReason = props.submitting
    ? "Action in progress."
    : props.currentPosition.direction === "NONE" || props.currentPosition.totalSize <= 0
      ? "No open spread position to close."
            : null;
  const activeStrategyWarning = strategyWarningMessage();

  useEffect(() => {
    setCloseConfirmArmed(false);
  }, [props.currentPosition.direction, props.currentPosition.totalSize, props.selectedPairId, props.submitting]);

  useEffect(() => {
    if (!closeConfirmArmed) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setCloseConfirmArmed(false);
    }, 8_000);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [closeConfirmArmed]);

  const handleCloseSpread = () => {
    if (closeSpreadDisabled) {
      return;
    }
    if (!closeConfirmArmed) {
      setCloseConfirmArmed(true);
      return;
    }
    setCloseConfirmArmed(false);
    execute("close-spread");
  };

  const execute = (command: TradeCommand) => {
    void props.onCommand(command);
  };

  const handleKillSwitchToggle = (nextActive: boolean) => {
    void props.onToggleKillSwitch(nextActive);
  };

  const renderSizingPreview = (
    label: string,
    result: SpreadSizingPlanResult | null
  ): JSX.Element => {
    if (!result) {
      return <p>{label}: no open spread position.</p>;
    }
    if (result.reason || !result.plan) {
      return <p>{label}: {result.reason ?? "sizing unavailable."}</p>;
    }
    const plan = result.plan;
    return (
      <div className="execution-sizing-row">
        <p>
          {label}: {formatInstrumentLabel(plan.leftInstrument)}{" "}
          {formatQtyForStep(plan.plannedLeftQty, plan.leftStep ?? undefined)} |{" "}
          {formatInstrumentLabel(plan.rightInstrument)}{" "}
          {formatQtyForStep(plan.plannedRightQty, plan.rightStep ?? undefined)}
        </p>
        <p className={plan.driftWithinTolerance ? "small-text tone-ok" : "small-text tone-warn"}>
          Achieved ${formatUsdCompact(plan.achievedNotionalUsd)}
        </p>
        {plan.hedgeRatioDriftPct > plan.toleranceHedgeRatioDriftPct + 1e-9 ? (
          <p className="small-text tone-warn">
            Hedge ratio drift {plan.hedgeRatioDriftPct.toFixed(2)}% (lot-step constrained).
          </p>
        ) : null}
      </div>
    );
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
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {props.cues?.cues.map((entry) => {
                const status = deriveOpportunityStatus(entry.cue, props.dataDegraded);
                const displayZ =
                  entry.cue.pair_id === props.selectedPairId && props.liveCurrentZ != null
                    ? props.liveCurrentZ
                    : entry.cue.spread_z;
                return (
                  <tr
                    key={entry.cue.pair_id}
                    className={entry.cue.pair_id === props.selectedPairId ? "selected-row" : ""}
                    onClick={() => props.onSelectPair(entry.cue.pair_id)}
                  >
                    <td>{formatPairLabel(entry.cue.pair_id)}</td>
                    <td>{displayZ.toFixed(2)}</td>
                    <td>{formatSigned(entry.cue.cost_gate.net_edge_bps)}bp</td>
                    <td className={status.toneClass}>{status.label}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
          <span className="chip tone-info">
            Live Z: {props.liveCurrentZ != null ? props.liveCurrentZ.toFixed(2) : "--"}
            {props.liveCurrentZUpdatedAt ? ` @ ${formatLocalTime(props.liveCurrentZUpdatedAt)}` : ""}
          </span>
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

        <div className="timeline-card open-trades-card">
          <h3>Open Trades</h3>
          {props.openTradesError ? <p className="small-text tone-warn">{props.openTradesError}</p> : null}
          <p className="open-trades-count">Open positions (all pairs): {props.openTradesCount}</p>
          {props.openTrade ? (
            <>
              <div className="table-wrap open-trades-table-wrap">
                <table className="open-trades-table">
                  <thead>
                    <tr>
                      <th>Leg</th>
                      <th>Side</th>
                      <th>Qty</th>
                      <th>Entry</th>
                      <th>Mark</th>
                      <th>uPnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {props.openTrade.legs.map((leg) => (
                      <tr key={`${props.openTrade?.pair_id}-${leg.instrument}`}>
                        <td>{formatInstrumentLabel(leg.instrument)}</td>
                        <td>{leg.side}</td>
                        <td>{formatQtyForStep(leg.qty, undefined)}</td>
                        <td>{leg.entry_ref_price != null ? formatMetricPrice(leg.entry_ref_price) : "--"}</td>
                        <td>{leg.live_mark != null ? formatMetricPrice(leg.live_mark) : "--"}</td>
                        <td
                          className={
                            leg.unrealized_pnl_usd == null
                              ? "tone-warn"
                              : leg.unrealized_pnl_usd >= 0
                                ? "tone-ok"
                                : "tone-bad"
                          }
                        >
                          {leg.unrealized_pnl_usd == null
                            ? "--"
                            : `${leg.unrealized_pnl_usd >= 0 ? "+" : "-"}$${Math.abs(
                                leg.unrealized_pnl_usd
                              ).toFixed(2)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mini-card open-trades-summary">
                <p>
                  Spread: {props.openTrade.direction} | Size {props.openTrade.spread_units.toFixed(2)} units | Status{" "}
                  {props.openTrade.pnl_status}
                </p>
                <p>
                  Z now {props.liveCurrentZ != null ? props.liveCurrentZ.toFixed(2) : "--"} | Entry Z{" "}
                  {props.openTrade.entry_z.toFixed(2)} | Target Z{" "}
                  {selectedCue ? selectedCue.cue.exit_band.toFixed(2) : "--"}
                </p>
                <p
                  className={
                    props.openTrade.unrealized_pnl_usd == null
                      ? "tone-warn"
                      : props.openTrade.unrealized_pnl_usd >= 0
                        ? "tone-ok"
                        : "tone-bad"
                  }
                >
                  Spread uPnL:{" "}
                  {props.openTrade.unrealized_pnl_usd == null
                    ? "--"
                    : `${props.openTrade.unrealized_pnl_usd >= 0 ? "+" : "-"}$${Math.abs(
                        props.openTrade.unrealized_pnl_usd
                      ).toFixed(2)}`}
                </p>
                <p className="open-trades-updated">Updated: {formatLocalTime(props.openTrade.updated_at)}</p>
              </div>
            </>
          ) : (
            <p className="empty-text">No live position for selected pair.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Spread Execution"
        subtitle="Manual actions with fail-closed execution gates"
        className="execution-panel"
      >
        <div className="execution-grid">
          <div className="execution-block entry-block">
            <h3>Entry / Add Exposure</h3>
            <div className="execution-mode-card">
              <div className="execution-mode-row">
                <strong>Execution Mode</strong>
                <span
                  className={`mode-badge ${
                    props.requiresLiveArm ? (props.operatorConfirmed ? "live" : "sim") : "sim"
                  }`}
                >
                  {props.requiresLiveArm
                    ? props.operatorConfirmed
                      ? "LIVE ARMED"
                      : "SIM ONLY"
                    : "SIM ENABLED"}
                </span>
              </div>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={props.operatorConfirmed}
                  onChange={(event) => props.setOperatorConfirmed(event.target.checked)}
                  disabled={!props.requiresLiveArm}
                />
                {props.requiresLiveArm ? "Live Trading Armed" : "Live arm not required in SIMULATE_ACK"}
              </label>
              <div className="execution-mode-meta small-text">
                Dispatch mode: {props.dispatchMode}
              </div>
              <div className="kill-switch-row">
                <div className="kill-switch-copy">
                  <strong>Global Disable (Kill Switch)</strong>
                  <p className="small-text">
                    {props.killSwitch?.active ? "ON: entries disabled globally." : "OFF: normal operation."}
                  </p>
                </div>
                <label className="toggle-switch" aria-label="Global disable kill switch">
                  <input
                    type="checkbox"
                    checked={props.killSwitch?.active ?? true}
                    disabled={props.killSwitchUpdating || !props.operatorId.trim().length}
                    onChange={(event) => handleKillSwitchToggle(event.target.checked)}
                  />
                  <span className="toggle-slider" />
                </label>
              </div>
            </div>
            <label>
              Target Spread Notional (USD) - ${formatUsdCompact(pairNotionalRules.minimumNotionalUsd)} minimum
              <input
                type="number"
                step={pairNotionalRules.incrementNotionalUsd}
                min={pairNotionalRules.minimumNotionalUsd}
                value={props.spreadSize}
                onChange={(event) => props.setSpreadSize(event.target.value)}
                onBlur={handleSpreadSizeBlur}
              />
            </label>
            <p className="small-text execution-size-hint">
              Increment: ${formatUsdCompact(pairNotionalRules.incrementNotionalUsd)}. Used for Long, Short,
              Add, and Reduce actions. Close-all ignores this field.
            </p>
            <label>
              Operator ID
              <input
                type="text"
                value={props.operatorId}
                onChange={(event) => props.setOperatorId(event.target.value)}
              />
            </label>

            <div className="execution-preview">
              <p className="small-text">
                Target Notional ${formatUsdCompact(targetNotionalUsd)} | Hedge ratio target{" "}
                {Math.abs(props.hedgeRatio ?? 1).toFixed(4)}
              </p>
              {renderSizingPreview("Long", longEntrySizing)}
              {renderSizingPreview("Short", shortEntrySizing)}
              {props.currentPosition.direction !== "NONE" ? (
                renderSizingPreview("Add", addExposureSizing)
              ) : null}
              {props.currentPosition.direction !== "NONE" ? (
                renderSizingPreview("Reduce", reduceSizing)
              ) : null}
            </div>

            <button className="primary" disabled={longEntryDisabled} onClick={() => execute("long-entry")}>
              Long Spread Entry
            </button>
            {longEntryDisabled ? <p className="action-disabled-reason">{longEntryDisabledReason}</p> : null}
            <button
              className="danger"
              disabled={shortEntryDisabled}
              onClick={() => execute("short-entry")}
            >
              Short Spread Entry
            </button>
            {shortEntryDisabled ? <p className="action-disabled-reason">{shortEntryDisabledReason}</p> : null}
            <button className="secondary" disabled={addExposureDisabled} onClick={() => execute("add-exposure")}>
              Add Exposure to Open Spread
            </button>
            {addExposureDisabled ? <p className="action-disabled-reason">{addExposureDisabledReason}</p> : null}
            {activeStrategyWarning ? <p className="execution-strategy-warning">{activeStrategyWarning}</p> : null}

            <div className="execution-block reduce-block">
              <h3>Reduce / Close</h3>
              <button
                className="neutral"
                disabled={reduceExposureDisabled}
                onClick={() => execute("reduce-exposure")}
              >
                Reduce Exposure (partial)
              </button>
              {reduceExposureDisabled ? (
                <p className="action-disabled-reason">{reduceExposureDisabledReason}</p>
              ) : null}
              <button
                className={`danger ${closeConfirmArmed ? "confirm-armed" : ""}`.trim()}
                disabled={closeSpreadDisabled}
                onClick={handleCloseSpread}
              >
                {closeConfirmArmed ? "Confirm Close Spread" : "Close Spread (all open in pair)"}
              </button>
              {closeSpreadDisabled ? <p className="action-disabled-reason">{closeSpreadDisabledReason}</p> : null}
              {!closeSpreadDisabled && closeConfirmArmed ? (
                <div className="confirm-row">
                  <p className="confirm-hint">Press confirm to close all open legs for this pair.</p>
                  <button className="neutral" onClick={() => setCloseConfirmArmed(false)}>
                    Cancel Close
                  </button>
                </div>
              ) : null}
            </div>
            <p className="execution-last-action">Last action: {props.tradeMessage}</p>
          </div>
        </div>
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
  analyticsChartBars,
  analyticsPaperHours,
  analyticsPaperLimit,
  onAnalyticsChartBarsChange,
  onAnalyticsPaperHoursChange,
  onAnalyticsPaperLimitChange,
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
  candidateInbox,
  candidateInboxLoading,
  candidateInboxError,
  candidateActionBusyId,
  candidateActionMessage,
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
  onCandidateAction,
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
  analyticsChartBars: number;
  analyticsPaperHours: number;
  analyticsPaperLimit: number;
  onAnalyticsChartBarsChange: (value: number) => void;
  onAnalyticsPaperHoursChange: (value: number) => void;
  onAnalyticsPaperLimitChange: (value: number) => void;
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
  candidateInbox: StrategyPairsCandidateInboxResponse | null;
  candidateInboxLoading: boolean;
  candidateInboxError: string | null;
  candidateActionBusyId: string | null;
  candidateActionMessage: string | null;
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
  onCandidateAction: (
    candidateId: string,
    action: "PROMOTE" | "HOLD" | "REJECT",
    note?: string
  ) => Promise<void>;
  onDownloadExpectancy: () => void;
  onDownloadReplay: () => void;
  onDownloadSweep: () => void;
  chartHeight: number;
}): JSX.Element {
  const selected = cues?.cues.find((entry) => entry.cue.pair_id === selectedPairId) ?? cues?.cues[0];
  const pairCount = cues?.cues.length ?? 0;
  const pairDrivenChartHeight = useMemo(
    () => Math.round(clampNumber(pairCount * 33, 350, 980)),
    [pairCount]
  );
  const primaryPanelHeight = pairDrivenChartHeight + 120;
  const zScorePlotHeight = Math.max(240, primaryPanelHeight - 100);
  const equityPlotHeight = Math.max(220, primaryPanelHeight - 185);
  const displayEquitySeries = useMemo(() => scaleEquityAbsolute(equitySeries, 100), [equitySeries]);
  const equityWindowStats = useMemo(() => {
    if (!displayEquitySeries.length || !equityTimestamps.length) {
      return { returnPct: null, daysRepresented: null, annualizedReturnPct: null };
    }
    const startValue = displayEquitySeries[0];
    const endValue = displayEquitySeries[displayEquitySeries.length - 1];
    const returnPct =
      Number.isFinite(startValue) && startValue > 0 && Number.isFinite(endValue)
        ? ((endValue / startValue) - 1) * 100
        : null;
    const startTs = Date.parse(equityTimestamps[0]);
    const endTs = Date.parse(equityTimestamps[equityTimestamps.length - 1]);
    const daysRepresented =
      Number.isFinite(startTs) && Number.isFinite(endTs) && endTs >= startTs
        ? (endTs - startTs) / 86_400_000
        : null;
    const annualizedReturnPct =
      returnPct != null &&
      daysRepresented != null &&
      daysRepresented > 0 &&
      Number.isFinite(returnPct)
        ? (Math.pow(1 + returnPct / 100, 365 / daysRepresented) - 1) * 100
        : null;
    return { returnPct, daysRepresented, annualizedReturnPct };
  }, [displayEquitySeries, equityTimestamps]);

  return (
    <div className="analytics-layout">
      <div className="analytics-left-stack">
        <div className="analytics-top-left-split">
          <SectionCard
            title="Pair"
            subtitle="Select pair"
            className="analytics-primary-panel"
            style={{ height: `${primaryPanelHeight}px` }}
          >
            <div className="table-wrap analytics-pair-list">
              <table>
                <tbody>
                  {cues?.cues.map((entry) => (
                    <tr
                      key={entry.cue.pair_id}
                      className={entry.cue.pair_id === selected?.cue.pair_id ? "selected-row" : ""}
                      onClick={() => onSelectPair(entry.cue.pair_id)}
                    >
                      <td>{formatPairLabel(entry.cue.pair_id)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard title="Strategy Metrics" subtitle="Optimal strategy summary">
            {selected ? (
              <>
                <StatRow label="Opportunity Score" value={selected.cue.opportunity_score.toFixed(2)} />
                <StatRow label="Expected Hold Bars" value={selected.cue.expected_hold_bars.toString()} />
                <StatRow label="Cost Estimate" value={`${selected.cue.cost_estimate_bps.toFixed(2)} bp`} />
                <StatRow label="Confidence" value={selected.cue.confidence_band} />
              </>
            ) : (
              <p className="empty-text">No live cues available.</p>
            )}
          </SectionCard>
        </div>

        <SectionCard>
          <details className="research-controls-panel">
            <summary>
              <span>Advanced Research (Optional)</span>
              <span className="small-text">Expectancy, replay, and sweep tooling</span>
            </summary>

            <div className="research-controls-body">
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
                <p className="small-text tone-bad">
                  Research inputs are invalid. Check Z bands and ranges.
                </p>
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

              <div className="candidate-inbox-card">
                <h3>Candidate Inbox</h3>
                {candidateInboxLoading ? (
                  <p className="small-text">Loading candidate inbox...</p>
                ) : null}
                {candidateInboxError ? (
                  <p className="small-text tone-bad">{candidateInboxError}</p>
                ) : null}
                {candidateActionMessage ? (
                  <p className="small-text tone-info">{candidateActionMessage}</p>
                ) : null}
                {!candidateInboxLoading && !candidateInboxError && candidateInbox?.rows.length === 0 ? (
                  <p className="small-text">No active challengers in the inbox.</p>
                ) : null}
                {candidateInbox?.rows.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Pair</th>
                          <th>State</th>
                          <th>Variant</th>
                          <th>Obj Δ</th>
                          <th>Samples</th>
                          <th>Next</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {candidateInbox.rows.map((row) => {
                          const busy = candidateActionBusyId === row.candidate_id;
                          return (
                            <tr key={row.candidate_id}>
                              <td>{formatPairLabel(row.pair_id)}</td>
                              <td className={row.promotable ? "tone-ok" : "tone-warn"}>
                                {row.candidate_state}
                              </td>
                              <td>{row.candidate_variant}</td>
                              <td className={row.objective_delta >= 0 ? "tone-ok" : "tone-bad"}>
                                {formatSigned(row.objective_delta)}
                              </td>
                              <td>{row.probation_samples}</td>
                              <td>{formatLocalTime(row.eligible_after)}</td>
                              <td>
                                <div className="candidate-action-buttons">
                                  <button
                                    type="button"
                                    disabled={busy || !row.promotable}
                                    onClick={() => void onCandidateAction(row.candidate_id, "PROMOTE")}
                                  >
                                    Promote
                                  </button>
                                  <button
                                    type="button"
                                    disabled={busy}
                                    onClick={() => void onCandidateAction(row.candidate_id, "HOLD")}
                                  >
                                    Hold
                                  </button>
                                  <button
                                    type="button"
                                    className="danger"
                                    disabled={busy}
                                    onClick={() => void onCandidateAction(row.candidate_id, "REJECT")}
                                  >
                                    Reject
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            </div>
          </details>
        </SectionCard>
      </div>

      <div className="analytics-right-stack">
        <div className="analytics-chart-split">
          <div className="analytics-chart-col">
            <SectionCard
              title="Hypothetical Equity Curve"
              subtitle="Absolute mode (equity x $100) from live candles and current strategy bands"
              className="analytics-primary-panel"
              style={{ height: `${primaryPanelHeight}px` }}
            >
              <div className="mini-card">
                <div className="research-results-grid">
                  <div>
                    <p className="small-text">Return (window)</p>
                    <p
                      className={
                        equityWindowStats.returnPct != null && equityWindowStats.returnPct >= 0
                          ? "tone-ok"
                          : "tone-bad"
                      }
                    >
                      {equityWindowStats.returnPct != null
                        ? `${formatSigned(equityWindowStats.returnPct, 2)}%`
                        : "--"}
                    </p>
                  </div>
                  <div>
                    <p className="small-text">Days represented</p>
                    <p>{equityWindowStats.daysRepresented != null ? equityWindowStats.daysRepresented.toFixed(2) : "--"}</p>
                  </div>
                  <div>
                    <p className="small-text">Annualized return</p>
                    <p
                      className={
                        equityWindowStats.annualizedReturnPct != null &&
                        equityWindowStats.annualizedReturnPct >= 0
                          ? "tone-ok"
                          : "tone-bad"
                      }
                    >
                      {equityWindowStats.annualizedReturnPct != null
                        ? `${formatSigned(equityWindowStats.annualizedReturnPct, 2)}%`
                        : "--"}
                    </p>
                  </div>
                </div>
              </div>
              <LineChart
                values={displayEquitySeries}
                timestamps={equityTimestamps}
                height={equityPlotHeight}
                title="Hypothetical equity (absolute, equity x $100)"
                unavailableText={loading ? "Loading live candles..." : error ?? "No data"}
                yAxisFormatter={formatUsdAxisValue}
                valueScaleMode="full"
              />
            </SectionCard>

            <SectionCard>
              <details className="research-controls-panel">
                <summary>
                  <span>Paper Trades (Optional)</span>
                  <span className="small-text">Persisted paper-trade inspection</span>
                </summary>
                <div className="research-controls-body">
                  <div className="research-controls-grid">
                    <label>
                      Chart Bars
                      <input
                        type="number"
                        min="120"
                        max="2000"
                        step="1"
                        value={analyticsChartBars}
                        onChange={(event) =>
                          onAnalyticsChartBarsChange(
                            clampAnalyticsChartBars(Number.parseInt(event.target.value, 10) || 120)
                          )
                        }
                      />
                    </label>
                    <label>
                      Paper Hours
                      <input
                        type="number"
                        min="1"
                        max="175200"
                        step="1"
                        value={analyticsPaperHours}
                        onChange={(event) =>
                          onAnalyticsPaperHoursChange(
                            clampAnalyticsPaperHours(Number.parseInt(event.target.value, 10) || 1)
                          )
                        }
                      />
                    </label>
                    <label>
                      Paper Limit
                      <input
                        type="number"
                        min="1"
                        max="20000"
                        step="1"
                        value={analyticsPaperLimit}
                        onChange={(event) =>
                          onAnalyticsPaperLimitChange(
                            clampAnalyticsPaperLimit(Number.parseInt(event.target.value, 10) || 1)
                          )
                        }
                      />
                    </label>
                  </div>
                  <p className="small-text tone-info">
                    Active window: chart={clampAnalyticsChartBars(analyticsChartBars)} bars, paper=
                    {clampAnalyticsPaperHours(analyticsPaperHours)}h, limit=
                    {clampAnalyticsPaperLimit(analyticsPaperLimit)}.
                  </p>
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
                </div>
              </details>
            </SectionCard>
          </div>

          <div className="analytics-chart-col">
            <SectionCard
              title="Historical Z-Score (Entries / Exits / Stops)"
              subtitle="Derived from live spread history"
              className="analytics-primary-panel"
              style={{ height: `${primaryPanelHeight}px` }}
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
                height={zScorePlotHeight}
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

            <SectionCard>
              <details className="research-controls-panel">
                <summary>
                  <span>Diagnostics (Optional)</span>
                  <span className="small-text">Live model and gate state</span>
                </summary>
                <div className="research-controls-body">
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
                        value={
                          (selected.cue.setup_gate?.pass ??
                          selected.cue.setup_actionable ??
                          selected.cue.actionable)
                            ? "PASS"
                            : "BLOCK"
                        }
                        tone={
                          (selected.cue.setup_gate?.pass ??
                          selected.cue.setup_actionable ??
                          selected.cue.actionable)
                            ? "ok"
                            : "bad"
                        }
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
                </div>
              </details>
            </SectionCard>
          </div>
        </div>
      </div>
    </div>
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
  setExchange,
  setAccountId,
  setOperatorId,
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
  setExchange: (value: string) => void;
  setAccountId: (value: string) => void;
  setOperatorId: (value: string) => void;
  timeframe: Timeframe;
}): JSX.Element {
  return (
    <div className="settings-layout">
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
        <p className="small-text tone-info">
          Execution guardrails are enforced in Trade regardless of Settings page visibility.
        </p>
      </SectionCard>

      <SectionCard title="API Credentials" subtitle="Per-user API keys (planned)">
        <label>
          Kraken API Key
          <input value="Not yet available apart from primary user" disabled readOnly />
        </label>
        <label>
          Kraken API Secret
          <input value="Not yet available apart from primary user" disabled readOnly />
        </label>
        <label>
          Kraken API Passphrase
          <input value="Not yet available apart from primary user" disabled readOnly />
        </label>
        <p className="small-text tone-warn">Not yet available apart from primary user</p>
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
