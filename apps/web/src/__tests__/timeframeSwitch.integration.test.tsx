import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Timeframe } from "../types";

vi.mock("@radix-ui/react-dropdown-menu", () => ({
  Root: ({ children }: { children: any }) => <div>{children}</div>,
  Trigger: ({ children }: { children: any }) => <>{children}</>,
  Content: ({ children }: { children: any }) => <div>{children}</div>,
  Item: ({
    children,
    onSelect,
    className,
  }: {
    children: any;
    onSelect?: () => void;
    className?: string;
  }) => (
    <button type="button" className={className} onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
}));

import App from "../App";

const api = vi.hoisted(() => ({
  buildStrategyMaintenanceArtifactUrl: vi.fn(),
  buildStrategyOpportunityHistoryUrl: vi.fn(),
  dispatchOrderIntent: vi.fn(),
  fetchExecutionDecision: vi.fn(),
  fetchExecutionPortfolioPositions: vi.fn(),
  fetchIntegrityHistory: vi.fn(),
  fetchKillSwitchState: vi.fn(),
  fetchMarketMetrics: vi.fn(),
  fetchOrderIntentHistory: vi.fn(),
  fetchReconcile: vi.fn(),
  fetchStrategyMaintenanceLatest: vi.fn(),
  fetchStrategyBacktest: vi.fn(),
  fetchStrategyCostGates: vi.fn(),
  fetchStrategyCues: vi.fn(),
  fetchStrategyLiveZ: vi.fn(),
  fetchStrategyOpportunityHistoryStats: vi.fn(),
  fetchStrategyPortfolioPlan: vi.fn(),
  fetchStrategyUiAuthStatus: vi.fn(),
  runStrategyMaintenanceAction: vi.fn(),
  submitOrderIntent: vi.fn(),
  verifyStrategyUiAccess: vi.fn(),
}));

vi.mock("../lib/api", () => api);

const PAIR_ID = "PI_XBTUSD__PI_ETHUSD";
const LEFT = "PI_XBTUSD";
const RIGHT = "PI_ETHUSD";

function buildCuesResponse(timeframe: Timeframe): any {
  return {
    timeframe,
    generated_at: "2026-02-20T00:00:00Z",
    cues: [
      {
        cue: {
          pair_id: PAIR_ID,
          left_instrument: LEFT,
          right_instrument: RIGHT,
          timeframe,
          regime: "CALM",
          selected_variant: "ROBUST_Z",
          direction_hint: "NONE",
          spread_z: 1.4,
          opportunity_score: 0.77,
          confidence_band: "MEDIUM",
          entry_band: 1.8,
          exit_band: 0.6,
          stop_band: 3.2,
          expected_hold_bars: 42,
          cost_estimate_bps: 1.1,
          actionable: true,
          rationale_codes: ["COST_PASS"],
          cost_gate: {
            status: "AVAILABLE",
            expected_edge_bps: 4.0,
            fee_bps: 1.0,
            funding_bps: 0.6,
            slippage_bps: 0.8,
            net_edge_bps: 1.6,
            pass: true,
            rationale_codes: ["EDGE_POSITIVE"],
          },
          portfolio_hint: {
            status: "AVAILABLE",
            target_weight: 0.3,
            risk_contribution: 0.2,
            cap_applied: false,
            rationale_codes: ["WITHIN_CAP"],
          },
          shadow_ml: {
            status: "AVAILABLE",
            model_name: "shadow-logit",
            training_rows: 200,
            positive_rate: 0.56,
            precision: 0.61,
            brier_score: 0.22,
            recommended_variant: "ROBUST_Z",
            recommended_probability: 0.62,
            agrees_with_selected: true,
            rationale_codes: ["STABLE"],
          },
          evaluated_at: "2026-02-20T00:00:00Z",
        },
        variants: [
          {
            variant: "ROBUST_Z",
            score_last: 0.77,
            sample_count: 300,
            win_rate: 0.58,
            edge_bps: 3.8,
            reliability: 0.71,
            regime_fit: 0.64,
            opportunity_score: 0.77,
            shadow_success_probability: 0.62,
            shadow_rank_score: 0.81,
            rationale_codes: ["PASS"],
          },
        ],
        half_life_bars: 36,
        hedge_ratio: 0.85,
        hedge_ratio_stability: 0.92,
      },
    ],
    candidate_set: {
      total_pairs: 1,
      evaluated_pairs: 1,
      actionable_pairs: 1,
      cost_gate_pass_pairs: 1,
      shadow_disagreement_pairs: 0,
    },
    portfolio_plan: {
      status: "AVAILABLE",
      weights: [
        {
          pair_id: PAIR_ID,
          target_weight: 0.3,
          risk_contribution: 0.2,
          cap_applied: false,
        },
      ],
      constraints: {
        dollar_neutral: true,
        gross_cap: 1,
        per_pair_cap: 0.35,
      },
      rationale_codes: ["WITHIN_CAP"],
    },
    skipped: [],
  };
}

function buildLiveZResponse(timeframe: Timeframe): any {
  const points = Array.from({ length: 24 }).map((_, index) => ({
    ts: new Date(Date.parse("2026-02-20T00:00:00Z") + index * 60_000).toISOString(),
    z: Math.sin(index / 4),
  }));
  return {
    timeframe,
    pair_id: PAIR_ID,
    generated_at: "2026-02-20T00:00:00Z",
    entry_band: 1.8,
    exit_band: 0.6,
    stop_band: 3.2,
    selected_variant: "ROBUST_Z",
    points,
    markers: [{ index: 5, kind: "entry" }, { index: 12, kind: "exit" }],
    rationale_codes: ["COST_PASS"],
  };
}

function buildBacktestResponse(timeframe: Timeframe): any {
  const points = Array.from({ length: 24 }).map((_, index) => ({
    ts: new Date(Date.parse("2026-02-20T00:00:00Z") + index * 60_000).toISOString(),
    z: Math.sin(index / 4),
    equity: 10_000 + index * 12,
  }));
  return {
    timeframe,
    pair_id: PAIR_ID,
    generated_at: "2026-02-20T00:00:00Z",
    left_instrument: LEFT,
    right_instrument: RIGHT,
    selected_variant: "ROBUST_Z",
    hedge_ratio: 0.85,
    entry_band: 1.8,
    exit_band: 0.6,
    stop_band: 3.2,
    round_trip_cost_bps: 1.4,
    points,
    markers: [{ index: 5, kind: "entry" }, { index: 12, kind: "exit" }],
    rationale_codes: ["COST_PASS"],
  };
}

function selectTimeframe(next: Timeframe): void {
  fireEvent.click(screen.getByRole("button", { name: /Timeframe:/i }));
  fireEvent.click(screen.getByText(next));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  api.buildStrategyMaintenanceArtifactUrl.mockImplementation((path: string) => path);
  api.buildStrategyOpportunityHistoryUrl.mockImplementation(() => "history.json");
  api.fetchStrategyUiAuthStatus.mockResolvedValue({ enabled: false });
  api.verifyStrategyUiAccess.mockResolvedValue({ ok: true });
  api.fetchStrategyMaintenanceLatest.mockResolvedValue({
    available: false,
    generated_at: "2026-02-20T00:00:00Z",
    report: null,
    reason: "none",
    artifact_download_route: "/v1/strategy/maintenance/artifact",
  });
  api.fetchStrategyOpportunityHistoryStats.mockResolvedValue({
    generated_at: "2026-02-20T00:00:00Z",
    timeframe_filter: null,
    total_rows: 0,
    first_evaluated_at: null,
    last_evaluated_at: null,
    days_covered: 0,
    by_timeframe: [],
  });
  api.runStrategyMaintenanceAction.mockResolvedValue({
    accepted: true,
    action: "PROMOTE",
    operator_id: "operator-kevin",
    pass: true,
    generated_at: "2026-02-20T00:00:00Z",
    report_download_path: "manual_actions/mock.json",
    report: null,
    error: null,
  });

  api.fetchStrategyCues.mockImplementation(async (timeframe: Timeframe) =>
    buildCuesResponse(timeframe)
  );
  api.fetchStrategyLiveZ.mockImplementation(async (timeframe: Timeframe) =>
    buildLiveZResponse(timeframe)
  );
  api.fetchStrategyBacktest.mockImplementation(async (timeframe: Timeframe) =>
    buildBacktestResponse(timeframe)
  );

  api.fetchKillSwitchState.mockResolvedValue({
    active: false,
    reason: "manual",
    updated_at: "2026-02-20T00:00:00Z",
  });
  api.fetchExecutionDecision.mockResolvedValue({
    instrument: LEFT,
    timeframe: "1m",
    decision: "ALLOWED",
    reason: null,
    min_coverage_pct: 99.5,
    evaluated_at: "2026-02-20T00:00:00Z",
  });
  api.fetchExecutionPortfolioPositions.mockResolvedValue({
    exchange: "kraken_futures",
    account_id: "primary",
    generated_at: "2026-02-20T00:00:00Z",
    positions: [],
  });
  api.fetchReconcile.mockResolvedValue({
    reconcile: {
      exchange: "kraken_futures",
      account_id: "primary",
      status: "OK",
      drift_notional: 0,
      reason: "ok",
      checked_at: "2026-02-20T00:00:00Z",
    },
  });
  api.fetchIntegrityHistory.mockResolvedValue({
    instrument: LEFT,
    timeframe: "1m",
    rows: [
      {
        start_ts: "2026-02-20T00:00:00Z",
        end_ts: "2026-02-20T00:59:00Z",
        status: "COMPLETE",
        coverage_pct: 100,
        reason: "ok",
        checked_at: "2026-02-20T01:00:00Z",
      },
    ],
  });
  api.fetchMarketMetrics.mockResolvedValue({
    instrument: LEFT,
    server_time: "2026-02-20T00:00:00Z",
    bid: 67324.1,
    ask: 67324.5,
    mark: 67324.3,
    index: 67317.8,
    change_24h_pct: 0.84,
    funding_rate: 0.0000021,
    open_interest: 5278812,
  });

  api.submitOrderIntent.mockResolvedValue({ decision: "BLOCKED" });
  api.dispatchOrderIntent.mockResolvedValue({ result: "REJECTED", reason: "not tested" });
  api.fetchOrderIntentHistory.mockResolvedValue({
    idempotency_key: "x",
    intent: { evaluated_at: "2026-02-20T00:00:00Z" },
    state_events: [],
    dispatch_attempts: [],
  });
});

describe("global timeframe switching", () => {
  it("refetches strategy, execution gates, and analytics data with 15m", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyCues).toHaveBeenCalledWith("1m", 20);
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        300,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        300,
        undefined,
        "mean_revert"
      );
      expect(api.fetchMarketMetrics).toHaveBeenCalledWith(LEFT);
      expect(api.fetchMarketMetrics).toHaveBeenCalledWith(RIGHT);
      expect(api.fetchExecutionPortfolioPositions).toHaveBeenCalledWith(
        "kraken_futures",
        "primary"
      );
    });
    expect(screen.getByText("XBTUSD Position Size").parentElement).toHaveTextContent("+1.00");
    expect(screen.getByText("ETHUSD Position Size").parentElement).toHaveTextContent("+0.85");

    selectTimeframe("15m");

    await waitFor(() => {
      expect(api.fetchStrategyCues).toHaveBeenCalledWith("15m", 20);
      expect(api.fetchExecutionDecision).toHaveBeenCalledWith(LEFT, "15m");
      expect(api.fetchExecutionDecision).toHaveBeenCalledWith(RIGHT, "15m");
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "15m",
        PAIR_ID,
        280,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "15m",
        PAIR_ID,
        280,
        undefined,
        "mean_revert"
      );
      expect(screen.getByRole("button", { name: /Timeframe: 15m/i })).toBeInTheDocument();
    });
  });

  it("uses 1h chart depth when switched to 1h", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        300,
        undefined,
        "mean_revert"
      );
    });

    selectTimeframe("1h");

    await waitFor(() => {
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1h",
        PAIR_ID,
        220,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1h",
        PAIR_ID,
        220,
        undefined,
        "mean_revert"
      );
      expect(screen.getByRole("button", { name: /Timeframe: 1h/i })).toBeInTheDocument();
    });
  });

  it("threads taker commission override to strategy queries when configured", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyCues).toHaveBeenCalledWith("1m", 20);
    });

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.change(screen.getByLabelText("Taker Commission"), {
      target: { value: "0.10%" },
    });

    await waitFor(() => {
      expect(api.fetchStrategyCues).toHaveBeenCalledWith("1m", 20, 10);
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith("1m", PAIR_ID, 300, 10, "mean_revert");
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        300,
        10,
        "mean_revert"
      );
    });
  });
});
