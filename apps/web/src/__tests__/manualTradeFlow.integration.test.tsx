import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
  fetchStrategyBacktest: vi.fn(),
  fetchStrategyCues: vi.fn(),
  fetchStrategyLiveZ: vi.fn(),
  fetchStrategyUiAuthStatus: vi.fn(),
  submitOrderIntent: vi.fn(),
  updateKillSwitchState: vi.fn(),
  verifyStrategyUiAccess: vi.fn(),
}));

vi.mock("../lib/api", () => api);

const PAIR_ID = "PI_XBTUSD__PI_ETHUSD";
const LEFT = "PI_XBTUSD";
const RIGHT = "PI_ETHUSD";

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  api.fetchStrategyUiAuthStatus.mockResolvedValue({ enabled: false });
  api.verifyStrategyUiAccess.mockResolvedValue({ ok: true });

  api.fetchStrategyCues.mockResolvedValue({
    timeframe: "1m",
    generated_at: "2026-02-20T00:00:00Z",
    cues: [
      {
        cue: {
          pair_id: PAIR_ID,
          left_instrument: LEFT,
          right_instrument: RIGHT,
          timeframe: "1m",
          regime: "CALM",
          selected_variant: "ROBUST_Z",
          direction_hint: "NONE",
          spread_z: -2.1,
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
          target_weight: 0.35,
          risk_contribution: 0.2,
          cap_applied: false,
        },
      ],
      constraints: {
        dollar_neutral: true,
        gross_cap: 1.0,
        per_pair_cap: 0.4,
      },
      rationale_codes: ["PASS"],
    },
    skipped: [],
  });
  api.fetchStrategyLiveZ.mockResolvedValue({
    timeframe: "1m",
    pair_id: PAIR_ID,
    generated_at: "2026-02-20T00:00:00Z",
    entry_band: 1.8,
    exit_band: 0.6,
    stop_band: 3.2,
    selected_variant: "ROBUST_Z",
    points: Array.from({ length: 40 }, (_, i) => ({
      ts: `2026-02-20T00:${String(i).padStart(2, "0")}:00Z`,
      z: -2 + i * 0.05,
    })),
    markers: [],
    rationale_codes: [],
  });
  api.fetchStrategyBacktest.mockResolvedValue({
    timeframe: "1m",
    pair_id: PAIR_ID,
    generated_at: "2026-02-20T00:00:00Z",
    left_instrument: LEFT,
    right_instrument: RIGHT,
    selected_variant: "ROBUST_Z",
    hedge_ratio: 0.85,
    entry_band: 1.8,
    exit_band: 0.6,
    stop_band: 3.2,
    round_trip_cost_bps: 1.2,
    points: Array.from({ length: 40 }, (_, i) => ({
      ts: `2026-02-20T00:${String(i).padStart(2, "0")}:00Z`,
      z: -2 + i * 0.05,
      equity: 10_000 + i * 10,
    })),
    markers: [],
    rationale_codes: [],
  });

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
  api.fetchReconcile.mockResolvedValue({
    reconcile: {
      exchange: "kraken_futures",
      account_id: "primary",
      ts: "2026-02-20T00:00:00Z",
      status: "OK",
      drift_notional: 0,
      notes: "ok",
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

  api.fetchExecutionPortfolioPositions
    .mockResolvedValueOnce({
      exchange: "kraken_futures",
      account_id: "primary",
      generated_at: "2026-02-20T00:00:00Z",
      positions: [],
    })
    .mockResolvedValue({
      exchange: "kraken_futures",
      account_id: "primary",
      generated_at: "2026-02-20T00:00:10Z",
      positions: [
        {
          pair_id: PAIR_ID,
          direction: "LONG_SPREAD",
          total_size: 1.25,
          avg_entry_z: -2.1,
          updated_at: "2026-02-20T00:00:10Z",
        },
      ],
    });

  api.submitOrderIntent.mockImplementation(async (payload: any) => ({
    ...payload,
    decision: "ACCEPTED",
    reason: null,
    evaluated_at: "2026-02-20T00:00:00Z",
  }));
  api.dispatchOrderIntent.mockImplementation(async (payload: any) => ({
    idempotency_key: payload.idempotency_key,
    result: "ACKNOWLEDGED",
    from_state: "PENDING_SUBMIT",
    to_state: "ACKNOWLEDGED",
    exchange_order_id: `ex-${payload.idempotency_key}`,
    reason: "simulate ack",
    attempted_at: "2026-02-20T00:00:00Z",
  }));
  api.fetchOrderIntentHistory.mockImplementation(async (idempotencyKey: string) => ({
    idempotency_key: idempotencyKey,
    intent: { evaluated_at: "2026-02-20T00:00:00Z" },
    state_events: [
      { state: "NEW", reason: "", actor: "execution-service", created_at: "2026-02-20T00:00:00Z" },
      {
        state: "APPROVED",
        reason: "",
        actor: "execution-service",
        created_at: "2026-02-20T00:00:00Z",
      },
      {
        state: "PENDING_SUBMIT",
        reason: "",
        actor: "dispatch",
        created_at: "2026-02-20T00:00:01Z",
      },
      {
        state: "ACKNOWLEDGED",
        reason: "",
        actor: "dispatch",
        created_at: "2026-02-20T00:00:02Z",
      },
    ],
    dispatch_attempts: [],
  }));
});

describe("manual trade flow", () => {
  it("submits and dispatches long spread entry with spread metadata", async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.fetchStrategyCues).toHaveBeenCalled();
      expect(api.fetchExecutionDecision).toHaveBeenCalledTimes(2);
      expect(api.fetchMarketMetrics).toHaveBeenCalledWith(LEFT);
      expect(api.fetchMarketMetrics).toHaveBeenCalledWith(RIGHT);
    });
    expect(screen.getByText("XBTUSD Position Size").parentElement).toHaveTextContent("+1.00");
    expect(screen.getByText("ETHUSD Position Size").parentElement).toHaveTextContent("+0.85");

    const targetNotionalInput = screen.getByLabelText(
      /Target Spread Notional \(USD\)/i
    ) as HTMLInputElement;
    fireEvent.change(targetNotionalInput, { target: { value: targetNotionalInput.min || "1000" } });
    fireEvent.blur(targetNotionalInput);

    fireEvent.click(screen.getByLabelText(/Live Trading Armed/i));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Long Spread Entry" })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Long Spread Entry" }));

    await waitFor(() => {
      expect(api.submitOrderIntent).toHaveBeenCalledTimes(2);
      expect(api.dispatchOrderIntent).toHaveBeenCalledTimes(2);
    });

    const firstPayload = api.submitOrderIntent.mock.calls[0][0];
    expect(firstPayload.pair_id).toBe(PAIR_ID);
    expect(firstPayload.spread_direction).toBe("LONG_SPREAD");
    expect(firstPayload.spread_z).toBeCloseTo(-0.05, 6);

    await waitFor(() => {
      expect(
        screen.getByText((content) => content.includes("Last action: Spread dispatched and acknowledged."))
      ).toBeInTheDocument();
      expect(api.fetchExecutionPortfolioPositions).toHaveBeenCalledWith(
        "kraken_futures",
        "primary"
      );
    });
  });
});
