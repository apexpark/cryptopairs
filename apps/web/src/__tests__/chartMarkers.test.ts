import { buildActiveTradeAnchor, buildExecutionMarkers } from "../lib/chartMarkers";
import type { OrderIntentHistoryResponse, SpreadPosition } from "../types";

function history(args: {
  key: string;
  action: "ENTRY" | "EXIT" | "EMERGENCY_STOP_CLOSE";
  spreadZ: number | null;
  evaluatedAt: string;
  finalState: "ACKNOWLEDGED" | "FILLED" | "PARTIALLY_FILLED" | "REJECTED";
}): OrderIntentHistoryResponse {
  return {
    idempotency_key: args.key,
    intent: {
      idempotency_key: args.key,
      exchange: "kraken_futures",
      account_id: "primary",
      pair_id: "PI_XBTUSD__PI_ETHUSD",
      instrument: "PI_XBTUSD",
      timeframe: "1m",
      action: args.action,
      spread_direction: "LONG_SPREAD",
      spread_z: args.spreadZ,
      side: "BUY",
      qty: 1,
      operator_confirmed: true,
      operator_id: "operator",
      min_coverage_pct: 99.5,
      decision: "ACCEPTED",
      reason: null,
      evaluated_at: args.evaluatedAt,
    },
    state_events: [
      {
        state: "APPROVED",
        reason: "ok",
        actor: "operator",
        created_at: args.evaluatedAt,
      },
      {
        state: args.finalState,
        reason: "ok",
        actor: "exchange",
        created_at: args.evaluatedAt,
      },
    ],
    dispatch_attempts: [],
  };
}

describe("chart marker overlays", () => {
  const zTimestamps = [
    "2026-02-24T00:00:00Z",
    "2026-02-24T00:01:00Z",
    "2026-02-24T00:02:00Z",
    "2026-02-24T00:03:00Z",
  ];
  const zValues = [-0.5, 0.2, 1.4, -0.1];

  it("builds persistent execution markers from executed history", () => {
    const markers = buildExecutionMarkers({
      zValues,
      zTimestamps,
      histories: [
        history({
          key: "entry-1",
          action: "ENTRY",
          spreadZ: 0.2,
          evaluatedAt: "2026-02-24T00:01:00Z",
          finalState: "ACKNOWLEDGED",
        }),
        history({
          key: "exit-1",
          action: "EXIT",
          spreadZ: -0.1,
          evaluatedAt: "2026-02-24T00:03:00Z",
          finalState: "FILLED",
        }),
        history({
          key: "blocked",
          action: "ENTRY",
          spreadZ: 1.4,
          evaluatedAt: "2026-02-24T00:02:00Z",
          finalState: "REJECTED",
        }),
      ],
    });

    expect(markers).toEqual([
      { index: 1, kind: "execution-entry" },
      { index: 3, kind: "execution-exit" },
    ]);
  });

  it("builds an active trade anchor for open positions", () => {
    const position: SpreadPosition = {
      direction: "LONG_SPREAD",
      totalSize: 1.25,
      avgEntryZ: 0.15,
      updatedAt: "2026-02-24T00:02:30Z",
    };
    const anchor = buildActiveTradeAnchor({
      currentPosition: position,
      zValues,
      histories: [
        history({
          key: "entry-open",
          action: "ENTRY",
          spreadZ: 0.2,
          evaluatedAt: "2026-02-24T00:01:00Z",
          finalState: "ACKNOWLEDGED",
        }),
      ],
    });

    expect(anchor?.entryAt).toBe("2026-02-24T00:01:00Z");
    expect(anchor?.entryZ).toBe(0.2);
    expect(anchor?.currentZ).toBe(-0.1);
    expect(anchor?.deltaZ ?? 0).toBeCloseTo(-0.3, 6);
  });
});
