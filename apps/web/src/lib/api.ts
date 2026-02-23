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
  StrategyPairsOpportunityHistoryStatsResponse,
  StrategyPairsLiveZResponse,
  StrategyMaintenanceActionRequest,
  StrategyMaintenanceActionResponse,
  StrategyMaintenanceLatestResponse,
  StrategyUiAuthStatusResponse,
  StrategyUiAuthVerifyRequest,
  StrategyUiAuthVerifyResponse,
  StrategyPairsPortfolioPlanResponse,
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

export async function fetchStrategyCues(
  timeframe: Timeframe,
  limit = 20
): Promise<StrategyPairsCuesResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/cues?timeframe=${timeframe}&limit=${limit}`;
  return parseJson<StrategyPairsCuesResponse>(await fetch(url));
}

export async function fetchStrategyCostGates(
  timeframe: Timeframe
): Promise<StrategyPairsCostGateResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/cost-gate?timeframe=${timeframe}`;
  return parseJson<StrategyPairsCostGateResponse>(await fetch(url));
}

export async function fetchStrategyPortfolioPlan(
  timeframe: Timeframe
): Promise<StrategyPairsPortfolioPlanResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/portfolio-plan?timeframe=${timeframe}`;
  return parseJson<StrategyPairsPortfolioPlanResponse>(await fetch(url));
}

export async function fetchStrategyBacktest(
  timeframe: Timeframe,
  pairId: string,
  bars = 300
): Promise<StrategyPairsBacktestResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/backtest?timeframe=${timeframe}&pair_id=${encodeURIComponent(
    pairId
  )}&bars=${bars}`;
  return parseJson<StrategyPairsBacktestResponse>(await fetch(url));
}

export async function fetchStrategyLiveZ(
  timeframe: Timeframe,
  pairId: string,
  points = 300
): Promise<StrategyPairsLiveZResponse> {
  const url = `${STRATEGY_SERVICE_BASE_URL}/v1/strategy/pairs/live-z?timeframe=${timeframe}&pair_id=${encodeURIComponent(
    pairId
  )}&points=${points}`;
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
  const url = `${DATA_SERVICE_BASE_URL}/v1/market/metrics?instrument=${encodeURIComponent(
    instrument
  )}`;
  return parseJson<MarketMetricsResponse>(await fetch(url));
}
