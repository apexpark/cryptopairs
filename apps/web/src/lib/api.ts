import type {
  DataQueryResponse,
  DispatchIntentRequest,
  DispatchIntentResponse,
  ExecutionPortfolioPositionsResponse,
  ExecutionDecisionResponse,
  IntegrityHistoryResponse,
  KillSwitchState,
  MarketMetricsResponse,
  OrderIntentHistoryResponse,
  OrderIntentRequest,
  OrderIntentResponse,
  ReconcileResponse,
  StrategyPairsBacktestResponse,
  StrategyPairsCostGateResponse,
  StrategyPairsCuesResponse,
  StrategyPairsPaperTradesResponse,
  StrategyPairsOpportunityHistoryStatsResponse,
  StrategyPairsLiveZResponse,
  StrategyMaintenanceActionRequest,
  StrategyMaintenanceActionResponse,
  StrategyMaintenanceLatestResponse,
  StrategyUiAuthStatusResponse,
  StrategyUiAuthVerifyRequest,
  StrategyUiAuthVerifyResponse,
  StrategyPairsPortfolioPlanResponse,
  BacktestExitMode,
  Timeframe,
} from "../types";

const DATA_SERVICE_BASE_URL =
  import.meta.env.VITE_DATA_SERVICE_BASE_URL ?? "http://127.0.0.1:8080";
const ACCOUNT_SERVICE_BASE_URL =
  import.meta.env.VITE_ACCOUNT_SERVICE_BASE_URL ?? "http://127.0.0.1:8081";
const EXECUTION_SERVICE_BASE_URL =
  import.meta.env.VITE_EXECUTION_SERVICE_BASE_URL ?? "http://127.0.0.1:8082";
const STRATEGY_SERVICE_BASE_URL =
  import.meta.env.VITE_STRATEGY_SERVICE_BASE_URL ?? "http://127.0.0.1:8083";

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

export async function fetchStrategyCostGates(
  timeframe: Timeframe,
  takerFeeBps?: number
): Promise<StrategyPairsCostGateResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  withOptionalTakerFeeBps(params, takerFeeBps);
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/cost-gate?${params.toString()}`;
  return parseJson<StrategyPairsCostGateResponse>(await fetch(url));
}

export async function fetchStrategyPortfolioPlan(
  timeframe: Timeframe,
  takerFeeBps?: number
): Promise<StrategyPairsPortfolioPlanResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  withOptionalTakerFeeBps(params, takerFeeBps);
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/portfolio-plan?${params.toString()}`;
  return parseJson<StrategyPairsPortfolioPlanResponse>(await fetch(url));
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
  takerFeeBps?: number,
  exitMode?: BacktestExitMode
): Promise<StrategyPairsLiveZResponse> {
  const params = new URLSearchParams();
  params.set("timeframe", timeframe);
  params.set("pair_id", pairId);
  params.set("points", points.toString());
  withOptionalTakerFeeBps(params, takerFeeBps);
  if (exitMode) {
    params.set("exit_mode", exitMode);
  }
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/live-z?${params.toString()}`;
  return parseJson<StrategyPairsLiveZResponse>(await fetch(url));
}

export async function fetchStrategyMaintenanceLatest(): Promise<StrategyMaintenanceLatestResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/maintenance/latest`;
  return parseJson<StrategyMaintenanceLatestResponse>(await fetch(url));
}

export async function runStrategyMaintenanceAction(
  payload: StrategyMaintenanceActionRequest
): Promise<StrategyMaintenanceActionResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/maintenance/action`;
  return parseJson<StrategyMaintenanceActionResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

export async function fetchStrategyUiAuthStatus(): Promise<StrategyUiAuthStatusResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/ui-auth/status`;
  return parseJson<StrategyUiAuthStatusResponse>(await fetch(url));
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

export function buildStrategyMaintenanceArtifactUrl(path: string): string {
  return `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/maintenance/artifact?path=${encodeURIComponent(
    path
  )}`;
}

export function buildStrategyOpportunityHistoryUrl(
  timeframe: Timeframe,
  hours = 12,
  onlyPass = true,
  limit = 5000
): string {
  return `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/opportunity-history/download?timeframe=${encodeURIComponent(
    timeframe
  )}&hours=${hours}&only_pass=${onlyPass ? "true" : "false"}&limit=${limit}`;
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

export async function fetchKillSwitchState(): Promise<KillSwitchState> {
  const url = `${EXECUTION_SERVICE_BASE_URL}/v1/execution/kill-switch`;
  return parseJson<KillSwitchState>(await fetch(url));
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

export async function queryCandles(
  instrument: string,
  timeframe: Timeframe,
  startTs: string,
  endTs: string
): Promise<DataQueryResponse> {
  const url = `${DATA_SERVICE_BASE_URL}/v1/data/query`;
  return parseJson<DataQueryResponse>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        instrument,
        timeframe,
        start_ts: startTs,
        end_ts: endTs,
      }),
    })
  );
}

export async function fetchIntegrityHistory(
  instrument: string,
  timeframe: Timeframe,
  limit = 50
): Promise<IntegrityHistoryResponse> {
  const url = `${DATA_SERVICE_BASE_URL}/v1/integrity/history?instrument=${encodeURIComponent(
    instrument
  )}&timeframe=${timeframe}&limit=${limit}`;
  return parseJson<IntegrityHistoryResponse>(await fetch(url));
}

export async function fetchMarketMetrics(
  instrument: string
): Promise<MarketMetricsResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/market/metrics?instrument=${encodeURIComponent(
    instrument
  )}`;
  return parseJson<MarketMetricsResponse>(await fetch(url));
}
