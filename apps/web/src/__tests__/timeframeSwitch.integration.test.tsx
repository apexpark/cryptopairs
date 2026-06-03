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
  dispatchOrderIntent: vi.fn(),
  fetchExecutionDispatchMode: vi.fn(),
  fetchExecutionDecision: vi.fn(),
  fetchExecutionPortfolioPositions: vi.fn(),
  fetchKillSwitchState: vi.fn(),
  fetchMarketMetrics: vi.fn(),
  fetchOrderIntentHistory: vi.fn(),
  fetchReconcile: vi.fn(),
  fetchStrategyOpportunityHistory: vi.fn(),
  fetchStrategyOpportunityHistoryStats: vi.fn(),
  fetchStrategyBacktest: vi.fn(),
  fetchStrategyCues: vi.fn(),
  fetchStrategyLiveZ: vi.fn(),
  fetchStrategyTradeNow: vi.fn(),
  fetchStrategyUiAuthStatus: vi.fn(),
  submitOrderIntent: vi.fn(),
  updateKillSwitchState: vi.fn(),
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

function buildTradeNowRow(pairId: string, timeframe: Timeframe, bucket: "TRADE_NOW" | "WATCHLIST" | "EXCLUDED"): any {
  const spreadZ = bucket === "EXCLUDED" ? 1.2 : bucket === "WATCHLIST" ? -1.1 : -2.1;
  return {
    pair_id: pairId,
    left_instrument: pairId.split("__")[0],
    right_instrument: pairId.split("__")[1],
    timeframe,
    selected_variant: "ROBUST_Z",
    direction_hint: bucket === "WATCHLIST" ? "NONE" : bucket === "EXCLUDED" ? "SHORT_SPREAD" : "LONG_SPREAD",
    spread_z: spreadZ,
    entry_distance_z: Math.abs(spreadZ) - 1.8,
    opportunity_score: bucket === "TRADE_NOW" ? 9.2 : bucket === "WATCHLIST" ? 7.4 : 1.1,
    confidence_band: bucket === "EXCLUDED" ? "MEDIUM" : "HIGH",
    expected_hold_bars: 18,
    net_edge_bps: bucket === "EXCLUDED" ? 0.8 : 12.4,
    setup_gate_pass: bucket !== "WATCHLIST",
    cost_gate_pass: true,
    trade_gate_pass: bucket !== "WATCHLIST",
    open_live_trade: false,
    portfolio_target_weight: bucket === "EXCLUDED" ? null : 0.3,
    portfolio_risk_contribution: bucket === "EXCLUDED" ? null : 0.2,
    approval_source:
      bucket === "TRADE_NOW"
        ? "LEARNING_SELECTION"
        : bucket === "WATCHLIST"
          ? "LEARNING_SELECTION"
          : "NONE",
    requires_fresh_overlay: bucket === "WATCHLIST",
    learning_recommendation: bucket === "EXCLUDED" ? null : "PROMOTE",
    learning_trade_eligible: bucket === "EXCLUDED" ? null : true,
    learning_selection_selected: bucket === "EXCLUDED" ? null : true,
    learning_reason_codes: bucket === "WATCHLIST" ? ["LEARNING_OVERLAY_STALE"] : [],
    learning_cycle_generated_at: bucket === "EXCLUDED" ? null : "2026-02-20T00:00:00Z",
    selected_config_source: bucket === "EXCLUDED" ? "LEGACY_ROW_FALLBACK" : "AUTO_CHAMPION",
    legacy_fallback_active: bucket === "EXCLUDED",
    decision_bucket: bucket,
    decision_reason_code:
      bucket === "TRADE_NOW"
        ? "LEARNING_SELECTED_AND_LIVE_GATES_PASS"
        : bucket === "WATCHLIST"
          ? "APPROVED_BUT_WAITING_ON_LIVE_CONDITIONS"
          : "PROVENANCE_POLICY_BLOCKED",
    blocked_reason_code: bucket === "EXCLUDED" ? "LEGACY_FALLBACK_ACTIVE" : null,
    watch_reason_code: bucket === "WATCHLIST" ? "SETUP_GATE_NOT_PASSING" : null,
    rationale_codes:
      bucket === "EXCLUDED"
        ? ["LEGACY_FALLBACK_ACTIVE", "OUTSIDE_APPROVED_UNIVERSE"]
        : ["APPROVAL_SOURCE_LEARNING_SELECTION", "NON_LEGACY_CHAMPION"],
  };
}

function buildTradeNowResponse(timeframe: Timeframe): any {
  return {
    generated_at: "2026-02-20T00:00:00Z",
    timeframe_filter: timeframe,
    learning_overlay_generated_at: "2026-02-20T00:00:00Z",
    learning_overlay_age_seconds: 600,
    learning_overlay_fresh: true,
    learning_overlay_ttl_seconds: 86400,
    tradable_now: [buildTradeNowRow(PAIR_ID, timeframe, "TRADE_NOW")],
    watchlist: [buildTradeNowRow("PI_SOLUSD__PI_AVAXUSD", timeframe, "WATCHLIST")],
    excluded: [buildTradeNowRow("PI_DOGEUSD__PI_PEPEUSD", timeframe, "EXCLUDED")],
  };
}

function buildEmptyTradeNowResponse(timeframe: Timeframe): any {
  return {
    generated_at: "2026-02-20T00:00:00Z",
    timeframe_filter: timeframe,
    learning_overlay_generated_at: "2026-02-20T00:00:00Z",
    learning_overlay_age_seconds: 600,
    learning_overlay_fresh: true,
    learning_overlay_ttl_seconds: 86400,
    tradable_now: [],
    watchlist: [],
    excluded: [],
  };
}

function buildOpportunityHistoryResponse(timeframe: Timeframe): any {
  const start = Date.parse("2026-02-13T00:00:00Z");
  const readyRows = [
    { pair_id: PAIR_ID, offsetMinutes: 0, actionable: true, cost_gate_pass: true, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: [] },
    { pair_id: PAIR_ID, offsetMinutes: 15, actionable: true, cost_gate_pass: true, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: [] },
    { pair_id: PAIR_ID, offsetMinutes: 120, actionable: true, cost_gate_pass: true, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: [] },
    { pair_id: "PI_SOLUSD__PI_AVAXUSD", offsetMinutes: 180, actionable: true, cost_gate_pass: true, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: [] },
  ];
  const blockedRows = [
    { pair_id: PAIR_ID, offsetMinutes: 45, actionable: false, cost_gate_pass: true, rationale_codes: ["PERFORMANCE_HISTORY_WAIT"], cost_gate_rationale_codes: [] },
    { pair_id: "PI_SOLUSD__PI_AVAXUSD", offsetMinutes: 240, actionable: true, cost_gate_pass: false, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: ["COST_GATE_BLOCKED"] },
    { pair_id: "PI_SOLUSD__PI_AVAXUSD", offsetMinutes: 300, actionable: true, cost_gate_pass: false, rationale_codes: ["SETUP_PASS"], cost_gate_rationale_codes: ["COST_GATE_BLOCKED"] },
  ];
  const rows = [...readyRows, ...blockedRows].map((row, index) => ({
    pair_id: row.pair_id,
    left_instrument: row.pair_id.split("__")[0],
    right_instrument: row.pair_id.split("__")[1],
    timeframe,
    selected_variant: "ROBUST_Z",
    regime: "CALM",
    direction_hint: "LONG_SPREAD",
    spread_z: index % 2 === 0 ? -2.1 : -1.1,
    opportunity_score: 7.5,
    net_edge_bps: row.cost_gate_pass ? 12.4 : 2.1,
    cost_gate_pass: row.cost_gate_pass,
    actionable: row.actionable,
    rationale_codes: row.rationale_codes,
    cost_gate_rationale_codes: row.cost_gate_rationale_codes,
    evaluated_at: new Date(start + row.offsetMinutes * 60_000).toISOString(),
  }));
  return {
    timeframe,
    generated_at: "2026-02-20T00:00:00Z",
    hours: 168,
    only_pass: false,
    rows,
  };
}

function buildOpportunityHistoryStatsResponse(timeframe: Timeframe): any {
  return {
    generated_at: "2026-02-20T00:00:00Z",
    timeframe_filter: timeframe,
    total_rows: 22056,
    first_evaluated_at: "2026-01-01T00:00:00Z",
    last_evaluated_at: "2026-02-24T00:00:00Z",
    days_covered: 54.01,
    by_timeframe: [
      {
        timeframe,
        rows: 22056,
        first_evaluated_at: "2026-01-01T00:00:00Z",
        last_evaluated_at: "2026-02-24T00:00:00Z",
        days_covered: 54.01,
      },
    ],
  };
}

function selectTimeframe(next: Timeframe): void {
  fireEvent.click(screen.getByRole("button", { name: /Timeframe:/i }));
  fireEvent.click(screen.getByText(next));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  api.fetchStrategyUiAuthStatus.mockResolvedValue({ enabled: false });
  api.verifyStrategyUiAccess.mockResolvedValue({ ok: true });

  api.fetchStrategyCues.mockImplementation(async (timeframe: Timeframe) =>
    buildCuesResponse(timeframe)
  );
  api.fetchStrategyTradeNow.mockImplementation(async (timeframe: Timeframe) =>
    timeframe === "1h" ? buildEmptyTradeNowResponse(timeframe) : buildTradeNowResponse(timeframe)
  );
  api.fetchStrategyOpportunityHistory.mockImplementation(async (timeframe: Timeframe) =>
    buildOpportunityHistoryResponse(timeframe)
  );
  api.fetchStrategyOpportunityHistoryStats.mockImplementation(async (timeframe: Timeframe) =>
    buildOpportunityHistoryStatsResponse(timeframe)
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
  api.fetchExecutionDispatchMode.mockResolvedValue({
    mode: "LIVE_KRAKEN",
    requires_live_arm: true,
  });
  api.updateKillSwitchState.mockResolvedValue({
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
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1m");
      expect(api.fetchStrategyOpportunityHistory).toHaveBeenCalledWith("1m", 168, false, 20000);
      expect(api.fetchStrategyOpportunityHistoryStats).toHaveBeenCalledWith("1m");
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
        2000,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
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
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("15m");
      expect(api.fetchStrategyOpportunityHistory).toHaveBeenCalledWith("15m", 168, false, 20000);
      expect(api.fetchStrategyOpportunityHistoryStats).toHaveBeenCalledWith("15m");
      expect(api.fetchExecutionDecision).toHaveBeenCalledWith(LEFT, "15m");
      expect(api.fetchExecutionDecision).toHaveBeenCalledWith(RIGHT, "15m");
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "15m",
        PAIR_ID,
        1600,
        1600,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "15m",
        PAIR_ID,
        1600,
        undefined,
        "mean_revert"
      );
      expect(screen.getByRole("button", { name: /Timeframe: 15m/i })).toBeInTheDocument();
    });
  });

  it("uses 1h chart depth when switched to 1h", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1m");
      expect(api.fetchStrategyOpportunityHistory).toHaveBeenCalledWith("1m", 168, false, 20000);
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
        2000,
        undefined,
        "mean_revert"
      );
    });

    selectTimeframe("1h");

    await waitFor(() => {
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1h");
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1h",
        PAIR_ID,
        1200,
        1200,
        undefined,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1h",
        PAIR_ID,
        1200,
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
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1m", 10);
      expect(api.fetchStrategyOpportunityHistory).toHaveBeenCalledWith("1m", 168, false, 20000);
      expect(api.fetchStrategyLiveZ).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
        2000,
        10,
        "mean_revert"
      );
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
        10,
        "mean_revert"
      );
    });
  });

  it("warns when a persisted pair falls back to the live cue set without overwriting storage", async () => {
    const missingPairId = "PI_SOLUSD__PI_AVAXUSD";
    window.localStorage.setItem("cp.pair", JSON.stringify(missingPairId));

    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyBacktest).toHaveBeenCalledWith(
        "1m",
        PAIR_ID,
        2000,
        undefined,
        "mean_revert"
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Research Bench" }));

    expect(
      screen.getByText(
        "Saved pair SOLUSD/AVAXUSD is no longer in the live cue set. Research Bench is currently showing XBTUSD/ETHUSD until you select another live pair."
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/Active chart pair:/i)).toHaveTextContent("XBTUSD/ETHUSD");
    expect(screen.getByText(/Active chart pair:/i)).toHaveTextContent("Mean Revert");
    expect(screen.getByText(/Active chart pair:/i)).toHaveTextContent("Backend default");
    expect(JSON.parse(window.localStorage.getItem("cp.pair") ?? "null")).toBe(missingPairId);
  });

  it("renders the trade-now buckets and explains when a timeframe has no approved universe rows", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1m");
    });

    expect(
      screen.getByText(
        "Approved operator surface: Trade Now, Watchlist, Excluded, and Research Bench."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
    expect(screen.getByText("Excluded")).toBeInTheDocument();
    expect(screen.getByText(/waiting for 0\.70 more z/i)).toBeInTheDocument();
    expect(screen.getAllByText("Research Bench").length).toBeGreaterThan(0);
    expect(screen.getByText("Cadence Snapshot")).toBeInTheDocument();
    expect(screen.getByText("Approved-ready rows/day")).toBeInTheDocument();
    expect(screen.getByText("Stored history coverage")).toBeInTheDocument();

    selectTimeframe("1h");

    await waitFor(() => {
      expect(api.fetchStrategyTradeNow).toHaveBeenCalledWith("1h");
    });

    expect(
      screen.getByText(
        "No approved universe rows exist for 1h. This timeframe currently has no learning-selected or operator-promoted active rows, so Trade Now stays empty and the Research Bench below remains advisory only."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No current approved universe rows exist for 1h, so cadence reporting stays unavailable until learning selection or operator promotion approves a live set."
      )
    ).toBeInTheDocument();
  });
});
