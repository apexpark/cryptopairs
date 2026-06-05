import type {
  DispatchIntentRequest,
  DispatchIntentResponse,
  ExecutionDispatchModeResponse,
  ExecutionOpenTradesResponse,
  ExecutionPortfolioPositionsResponse,
  ExecutionDecisionResponse,
  KillSwitchState,
  MarketMetricsResponse,
  OrderIntentHistoryResponse,
  OrderIntentRequest,
  OrderIntentResponse,
  ReconcileResponse,
  StrategyPairsBacktestResponse,
  StrategyPairsCandidateActionRequest,
  StrategyPairsCandidateActionResponse,
  StrategyPairsCandidateInboxResponse,
  StrategyPairsCuesResponse,
  StrategyPairsExpectancyResponse,
  StrategyPairsOpportunityHistoryResponse,
  StrategyPairsOpportunityHistoryStatsResponse,
  StrategyPairsPaperTradesResponse,
  StrategyPairsTradeNowResponse,
  StrategyPairsReplayTradesResponse,
  StrategyPairsResearchSweepRequest,
  StrategyPairsResearchSweepResponse,
  StrategyPairsLiveZResponse,
  StrategyUiAuthStatusResponse,
  StrategyTradeNowObservabilityResponse,
  StrategyUiAuthVerifyRequest,
  StrategyUiAuthVerifyResponse,
  UpdateKillSwitchRequest,
  BacktestExitMode,
  Timeframe,
} from "../types";
import { resolveServiceBaseUrl } from "./serviceBaseUrls";

const ACCOUNT_SERVICE_BASE_URL = resolveServiceBaseUrl(
  import.meta.env.VITE_ACCOUNT_SERVICE_BASE_URL,
  "account"
);
const EXECUTION_SERVICE_BASE_URL = resolveServiceBaseUrl(
  import.meta.env.VITE_EXECUTION_SERVICE_BASE_URL,
  "execution"
);
const STRATEGY_SERVICE_BASE_URL = resolveServiceBaseUrl(
  import.meta.env.VITE_STRATEGY_SERVICE_BASE_URL,
  "strategy"
);

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function withOptionalTakerFeeBps(params: URLSearchParams, takerFeeBps?: number): void {
  if (takerFeeBps == null) {
    return;
  }
  params.set("taker_fee_bps", takerFeeBps.toString());
}

export async function fetchStrategyCues(
  timeframe: Timeframe,
  limit = 20,
  takerFeeBps?: number
): Promise<StrategyPairsCuesResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("limit", limit.toString());
  withOptionalTakerFeeBps(params, takerFeeBps);
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/cues?${params.toString()}`;
  return parseJson<StrategyPairsCuesResponse>(await fetch(url));
}

export async function fetchStrategyTradeNow(
  timeframe?: Timeframe,
  takerFeeBps?: number
): Promise<StrategyPairsTradeNowResponse> {
  const params = new URLSearchParams();
  if (timeframe) {
    params.set("timeframe", timeframe);
  }
  withOptionalTakerFeeBps(params, takerFeeBps);
  const query = params.toString();
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/trade-now${
    query ? `?${query}` : ""
  }`;
  return parseJson<StrategyPairsTradeNowResponse>(await fetch(url));
}

export async function fetchStrategyTradeNowObservability(): Promise<StrategyTradeNowObservabilityResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/observability/trade-now`;
  return parseJson<StrategyTradeNowObservabilityResponse>(await fetch(url));
}

export async function fetchStrategyBacktest(
  timeframe: Timeframe,
  pairId: string,
  bars = 300,
  takerFeeBps?: number,
  exitMode?: BacktestExitMode
): Promise<StrategyPairsBacktestResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("pair_id", pairId);
  params.set("bars", bars.toString());
  withOptionalTakerFeeBps(params, takerFeeBps);
  if (exitMode) {
    params.set("exit_mode", exitMode);
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/backtest?${params.toString()}`;
  return parseJson<StrategyPairsBacktestResponse>(await fetch(url));
}

export async function fetchStrategyLiveZ(
  timeframe: Timeframe,
  pairId: string,
  points = 300,
  windowBars?: number,
  takerFeeBps?: number,
  exitMode?: BacktestExitMode
): Promise<StrategyPairsLiveZResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("pair_id", pairId);
  params.set("points", points.toString());
  if (windowBars != null && Number.isFinite(windowBars) && windowBars > 0) {
    params.set("window_bars", Math.floor(windowBars).toString());
  }
  withOptionalTakerFeeBps(params, takerFeeBps);
  if (exitMode) {
    params.set("exit_mode", exitMode);
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/live-z?${params.toString()}`;
  return parseJson<StrategyPairsLiveZResponse>(await fetch(url));
}

export async function fetchStrategyUiAuthStatus(): Promise<StrategyUiAuthStatusResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/ui-auth/status`;
  return parseJson<StrategyUiAuthStatusResponse>(await fetch(url));
}

export async function fetchStrategyOpportunityHistory(
  timeframe: Timeframe,
  hours = 168,
  onlyPass = false,
  limit = 20_000
): Promise<StrategyPairsOpportunityHistoryResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("hours", hours.toString());
  params.set("only_pass", onlyPass ? "true" : "false");
  params.set("limit", limit.toString());
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/opportunity-history?${params.toString()}`;
  return parseJson<StrategyPairsOpportunityHistoryResponse>(await fetch(url));
}

export async function fetchStrategyOpportunityHistoryStats(
  timeframe?: Timeframe
): Promise<StrategyPairsOpportunityHistoryStatsResponse> {
  const params = new URLSearchParams();
  if (timeframe) {
    params.set("timeframe", timeframe);
  }
  const query = params.toString();
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/opportunity-history/stats${
    query ? `?${query}` : ""
  }`;
  return parseJson<StrategyPairsOpportunityHistoryStatsResponse>(await fetch(url));
}

export async function verifyStrategyUiAccess(
  payload: StrategyUiAuthVerifyRequest
): Promise<StrategyUiAuthVerifyResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/ui-auth/verify`;
  return parseJson<StrategyUiAuthVerifyResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchStrategyPaperTrades(
  timeframe: Timeframe,
  pairId?: string,
  hours = 168,
  limit = 50,
  exitMode?: BacktestExitMode
): Promise<StrategyPairsPaperTradesResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("hours", hours.toString());
  params.set("limit", limit.toString());
  if (pairId && pairId.trim().length) {
    params.set("pair_id", pairId);
  }
  if (exitMode) {
    params.set("exit_mode", exitMode);
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/paper-trades?${params.toString()}`;
  return parseJson<StrategyPairsPaperTradesResponse>(await fetch(url));
}

export async function fetchStrategyExpectancy(
  timeframe: Timeframe,
  pairId: string,
  entryZ: number,
  exitZ: number,
  stopZ: number,
  zMethod: string,
  lookbackBars: number,
  trainBars?: number,
  validationBars?: number
): Promise<StrategyPairsExpectancyResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("pair_id", pairId);
  params.set("entry_z", entryZ.toString());
  params.set("exit_z", exitZ.toString());
  params.set("stop_z", stopZ.toString());
  params.set("z_method", zMethod);
  params.set("lookback_bars", lookbackBars.toString());
  if (trainBars && Number.isFinite(trainBars) && trainBars > 0) {
    params.set("train_bars", Math.floor(trainBars).toString());
  }
  if (validationBars && Number.isFinite(validationBars) && validationBars > 0) {
    params.set("validation_bars", Math.floor(validationBars).toString());
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/expectancy?${params.toString()}`;
  return parseJson<StrategyPairsExpectancyResponse>(await fetch(url));
}

export async function fetchStrategyReplayTrades(
  timeframe: Timeframe,
  pairId: string,
  hours: number,
  limit: number,
  exitMode: BacktestExitMode,
  entryZ: number,
  exitZ: number,
  stopZ: number,
  zMethod: string,
  lookbackBars: number,
  trainBars?: number,
  validationBars?: number
): Promise<StrategyPairsReplayTradesResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("pair_id", pairId);
  params.set("hours", hours.toString());
  params.set("limit", limit.toString());
  params.set("exit_mode", exitMode);
  params.set("entry_z", entryZ.toString());
  params.set("exit_z", exitZ.toString());
  params.set("stop_z", stopZ.toString());
  params.set("z_method", zMethod);
  params.set("lookback_bars", lookbackBars.toString());
  if (trainBars && Number.isFinite(trainBars) && trainBars > 0) {
    params.set("train_bars", Math.floor(trainBars).toString());
  }
  if (validationBars && Number.isFinite(validationBars) && validationBars > 0) {
    params.set("validation_bars", Math.floor(validationBars).toString());
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/replay-trades?${params.toString()}`;
  return parseJson<StrategyPairsReplayTradesResponse>(await fetch(url));
}

export async function runStrategyResearchSweep(
  payload: StrategyPairsResearchSweepRequest
): Promise<StrategyPairsResearchSweepResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/research-sweep`;
  return parseJson<StrategyPairsResearchSweepResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchStrategyCandidateInbox(
  timeframe?: Timeframe,
  limit = 3
): Promise<StrategyPairsCandidateInboxResponse> {
  const params = new URLSearchParams();
  if (timeframe) {
    params.set("timeframe", timeframe);
  }
  params.set("limit", limit.toString());
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/candidate-inbox?${params.toString()}`;
  return parseJson<StrategyPairsCandidateInboxResponse>(await fetch(url));
}

export async function submitStrategyCandidateAction(
  payload: StrategyPairsCandidateActionRequest
): Promise<StrategyPairsCandidateActionResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/candidate-action`;
  return parseJson<StrategyPairsCandidateActionResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchKillSwitchState(): Promise<KillSwitchState> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/kill-switch`;
  return parseJson<KillSwitchState>(await fetch(url));
}

export async function updateKillSwitchState(
  payload: UpdateKillSwitchRequest
): Promise<KillSwitchState> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/kill-switch`;
  return parseJson<KillSwitchState>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchExecutionDispatchMode(): Promise<ExecutionDispatchModeResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/dispatch-mode`;
  return parseJson<ExecutionDispatchModeResponse>(await fetch(url));
}

export async function fetchExecutionDecision(
  instrument: string,
  timeframe: Timeframe
): Promise<ExecutionDecisionResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/decision?instrument=${encodeURIComponent(
    instrument
  )}&timeframe=${timeframe}`;
  return parseJson<ExecutionDecisionResponse>(await fetch(url));
}

export async function fetchExecutionPortfolioPositions(
  exchange: string,
  accountId: string
): Promise<ExecutionPortfolioPositionsResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/portfolio/positions?exchange=${encodeURIComponent(
    exchange
  )}&account_id=${encodeURIComponent(accountId)}`;
  return parseJson<ExecutionPortfolioPositionsResponse>(await fetch(url));
}

export async function fetchExecutionOpenTrades(
  exchange: string,
  accountId: string,
  pairId?: string
): Promise<ExecutionOpenTradesResponse> {
  const params = new URLSearchParams();
  params.set("exchange", exchange);
  params.set("account_id", accountId);
  if (pairId && pairId.trim().length > 0) {
    params.set("pair_id", pairId);
  }
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/portfolio/open-trades?${params.toString()}`;
  return parseJson<ExecutionOpenTradesResponse>(await fetch(url));
}

export async function submitOrderIntent(
  payload: OrderIntentRequest
): Promise<OrderIntentResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/order-intent`;
  return parseJson<OrderIntentResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function dispatchOrderIntent(
  payload: DispatchIntentRequest
): Promise<DispatchIntentResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/order-intent/dispatch`;
  return parseJson<DispatchIntentResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchOrderIntentHistory(
  idempotencyKey: string
): Promise<OrderIntentHistoryResponse> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/order-intent/history?idempotency_key=${encodeURIComponent(
    idempotencyKey
  )}`;
  return parseJson<OrderIntentHistoryResponse>(await fetch(url));
}

export async function fetchReconcile(
  exchange: string,
  accountId: string
): Promise<ReconcileResponse> {
  const url = `${ACCOUNT_SERVICE_BASE_URL}/v1/account/reconcile?exchange=${encodeURIComponent(
    exchange
  )}&account_id=${encodeURIComponent(accountId)}`;
  return parseJson<ReconcileResponse>(await fetch(url));
}

export async function fetchMarketMetrics(
  instrument: string
): Promise<MarketMetricsResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/market/metrics?instrument=${encodeURIComponent(
    instrument
  )}`;
  return parseJson<MarketMetricsResponse>(await fetch(url));
}
