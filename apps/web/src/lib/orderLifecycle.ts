import type { DispatchIntentResponse, OrderIntentHistoryResponse } from "../types";

export interface DispatchSummaryInput {
  intentDecision: "ACCEPTED" | "BLOCKED";
  dispatch: DispatchIntentResponse | null;
}

export function allAcceptedDispatchAcknowledged(
  outcomes: DispatchSummaryInput[]
): boolean {
  const accepted = outcomes.filter((outcome) => outcome.intentDecision === "ACCEPTED");
  return (
    accepted.length > 0 &&
    accepted.every((outcome) => outcome.dispatch?.result === "ACKNOWLEDGED")
  );
}

export function latestLifecycleState(
  history: OrderIntentHistoryResponse
): string {
  return history.state_events[history.state_events.length - 1]?.state ?? "N/A";
}
