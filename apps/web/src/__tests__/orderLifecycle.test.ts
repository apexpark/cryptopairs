import {
  allAcceptedDispatchAcknowledged,
  latestLifecycleState,
} from "../lib/orderLifecycle";

describe("orderLifecycle helpers", () => {
  it("requires every accepted leg to be acknowledged", () => {
    expect(
      allAcceptedDispatchAcknowledged([
        { intentDecision: "ACCEPTED", dispatch: { result: "ACKNOWLEDGED" } as any },
        { intentDecision: "ACCEPTED", dispatch: { result: "ACKNOWLEDGED" } as any },
      ])
    ).toBe(true);

    expect(
      allAcceptedDispatchAcknowledged([
        { intentDecision: "ACCEPTED", dispatch: { result: "REJECTED" } as any },
        { intentDecision: "ACCEPTED", dispatch: { result: "ACKNOWLEDGED" } as any },
      ])
    ).toBe(false);

    expect(
      allAcceptedDispatchAcknowledged([
        { intentDecision: "BLOCKED", dispatch: null },
      ])
    ).toBe(false);
  });

  it("returns latest lifecycle state from history", () => {
    expect(
      latestLifecycleState({
        idempotency_key: "key-1",
        intent: {} as any,
        state_events: [
          {
            state: "NEW",
            reason: "",
            actor: "execution-service",
            created_at: "2026-01-01T00:00:00Z",
          },
          {
            state: "ACKNOWLEDGED",
            reason: "ok",
            actor: "dispatch",
            created_at: "2026-01-01T00:00:01Z",
          },
        ],
        dispatch_attempts: [],
      } as any)
    ).toBe("ACKNOWLEDGED");
  });
});
