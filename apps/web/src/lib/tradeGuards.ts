import type { DirectionHint, SpreadPosition } from "../types";

export interface GateState {
  killSwitchActive: boolean;
  leftAllowed: boolean;
  rightAllowed: boolean;
  reconcileOk: boolean;
}

export interface EntryGuardInput {
  operatorConfirmed: boolean;
  operatorId: string;
  spreadSize: number;
  gateState: GateState;
}

export function isGateSafe(gateState: GateState): boolean {
  return (
    gateState.killSwitchActive === false &&
    gateState.leftAllowed &&
    gateState.rightAllowed &&
    gateState.reconcileOk
  );
}

export function isEntryAllowed(input: EntryGuardInput): boolean {
  return (
    input.operatorConfirmed &&
    input.operatorId.trim().length > 0 &&
    Number.isFinite(input.spreadSize) &&
    input.spreadSize > 0 &&
    isGateSafe(input.gateState)
  );
}

export function isAddAllowed(
  position: SpreadPosition | undefined,
  input: EntryGuardInput
): boolean {
  return !!position && position.direction !== "NONE" && isEntryAllowed(input);
}

export function isReduceAllowed(
  position: SpreadPosition | undefined,
  operatorConfirmed: boolean,
  operatorId: string,
  spreadSize: number
): boolean {
  return (
    !!position &&
    position.direction !== "NONE" &&
    position.totalSize > 0 &&
    operatorConfirmed &&
    operatorId.trim().length > 0 &&
    spreadSize > 0
  );
}

export function isCloseAllowed(position: SpreadPosition | undefined): boolean {
  return !!position && position.direction !== "NONE" && position.totalSize > 0;
}

export function emptyPosition(nowIso: string): SpreadPosition {
  return {
    direction: "NONE",
    totalSize: 0,
    avgEntryZ: 0,
    updatedAt: nowIso,
  };
}

export function applyEntryLike(
  current: SpreadPosition,
  requestedDirection: Exclude<DirectionHint, "NONE">,
  size: number,
  currentZ: number,
  nowIso: string
): SpreadPosition {
  if (size <= 0) {
    return current;
  }

  if (current.direction === "NONE") {
    return {
      direction: requestedDirection,
      totalSize: size,
      avgEntryZ: currentZ,
      updatedAt: nowIso,
    };
  }

  if (current.direction === requestedDirection) {
    const total = current.totalSize + size;
    const weightedZ =
      (current.avgEntryZ * current.totalSize + currentZ * size) /
      Math.max(total, Number.EPSILON);
    return {
      direction: requestedDirection,
      totalSize: total,
      avgEntryZ: weightedZ,
      updatedAt: nowIso,
    };
  }

  if (size < current.totalSize) {
    return {
      ...current,
      totalSize: current.totalSize - size,
      updatedAt: nowIso,
    };
  }

  if (size === current.totalSize) {
    return emptyPosition(nowIso);
  }

  return {
    direction: requestedDirection,
    totalSize: size - current.totalSize,
    avgEntryZ: currentZ,
    updatedAt: nowIso,
  };
}

export function applyReduce(
  current: SpreadPosition,
  size: number,
  nowIso: string
): SpreadPosition {
  if (current.direction === "NONE" || size <= 0) {
    return current;
  }

  if (size >= current.totalSize) {
    return emptyPosition(nowIso);
  }

  return {
    ...current,
    totalSize: current.totalSize - size,
    updatedAt: nowIso,
  };
}
