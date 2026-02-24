import { latestLifecycleState } from "./orderLifecycle";
import type { ChartMarker, OrderIntentHistoryResponse, SpreadPosition } from "../types";

const EXECUTED_STATES = new Set(["ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED"]);

export interface ActiveTradeAnchor {
  entryAt: string;
  entryZ: number;
  currentZ: number;
  deltaZ: number;
}

function toUnixMs(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nearestIndexByTimestamp(timestamps: string[], targetMs: number): number | null {
  if (!timestamps.length) {
    return null;
  }
  let bestIndex = 0;
  let bestDiff = Number.POSITIVE_INFINITY;
  for (let index = 0; index < timestamps.length; index += 1) {
    const tsMs = toUnixMs(timestamps[index]);
    if (tsMs == null) {
      continue;
    }
    const diff = Math.abs(tsMs - targetMs);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIndex = index;
    }
  }
  return Number.isFinite(bestDiff) ? bestIndex : null;
}

function nearestIndexByValue(values: number[], target: number): number | null {
  if (!values.length || !Number.isFinite(target)) {
    return null;
  }
  let bestIndex = 0;
  let bestDiff = Number.POSITIVE_INFINITY;
  for (let index = 0; index < values.length; index += 1) {
    const diff = Math.abs(values[index] - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIndex = index;
    }
  }
  return Number.isFinite(bestDiff) ? bestIndex : null;
}

function isExecutedHistory(history: OrderIntentHistoryResponse): boolean {
  return EXECUTED_STATES.has(latestLifecycleState(history));
}

function markerKindForAction(action: string): ChartMarker["kind"] | null {
  if (action === "ENTRY") {
    return "execution-entry";
  }
  if (action === "EXIT" || action === "EMERGENCY_STOP_CLOSE") {
    return "execution-exit";
  }
  return null;
}

export function buildExecutionMarkers(params: {
  zValues: number[];
  zTimestamps: string[];
  histories: OrderIntentHistoryResponse[];
}): ChartMarker[] {
  const { zValues, zTimestamps, histories } = params;
  if (!zValues.length || !zTimestamps.length || !histories.length) {
    return [];
  }

  const dedup = new Map<string, ChartMarker>();
  const executed = histories
    .filter(isExecutedHistory)
    .sort((left, right) => Date.parse(left.intent.evaluated_at) - Date.parse(right.intent.evaluated_at));

  for (const history of executed) {
    const markerKind = markerKindForAction(history.intent.action);
    if (!markerKind) {
      continue;
    }
    let index: number | null = null;
    const evaluatedMs = toUnixMs(history.intent.evaluated_at);
    if (evaluatedMs != null) {
      index = nearestIndexByTimestamp(zTimestamps, evaluatedMs);
    }
    if (index == null && history.intent.spread_z != null) {
      index = nearestIndexByValue(zValues, history.intent.spread_z);
    }
    if (index == null || index < 0 || index >= zValues.length) {
      continue;
    }
    const key = `${markerKind}-${index}`;
    if (!dedup.has(key)) {
      dedup.set(key, { index, kind: markerKind });
    }
  }

  return Array.from(dedup.values());
}

export function buildActiveTradeAnchor(params: {
  currentPosition: SpreadPosition;
  zValues: number[];
  histories: OrderIntentHistoryResponse[];
}): ActiveTradeAnchor | null {
  const { currentPosition, zValues, histories } = params;
  if (currentPosition.direction === "NONE" || currentPosition.totalSize <= 0 || !zValues.length) {
    return null;
  }

  const latestExecutedEntry = histories
    .filter((history) => history.intent.action === "ENTRY")
    .filter(isExecutedHistory)
    .sort((left, right) => Date.parse(right.intent.evaluated_at) - Date.parse(left.intent.evaluated_at))[0];

  const entryZ = latestExecutedEntry?.intent.spread_z ?? currentPosition.avgEntryZ;
  if (!Number.isFinite(entryZ)) {
    return null;
  }

  const currentZ = zValues[zValues.length - 1];
  if (!Number.isFinite(currentZ)) {
    return null;
  }

  return {
    entryAt: latestExecutedEntry?.intent.evaluated_at ?? currentPosition.updatedAt,
    entryZ,
    currentZ,
    deltaZ: currentZ - entryZ,
  };
}
