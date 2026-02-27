import {
  applyEntryLike,
  applyReduce,
  emptyPosition,
  isAddAllowed,
  isCloseAllowed,
  isEntryAllowed,
  isGateSafe,
  isReduceAllowed,
} from "../lib/tradeGuards";

const safeGate = {
  killSwitchActive: false,
  leftAllowed: true,
  rightAllowed: true,
  reconcileOk: true,
};

describe("trade guards", () => {
  it("fails closed when any gate is unsafe", () => {
    expect(isGateSafe(safeGate)).toBe(true);
    expect(isGateSafe({ ...safeGate, killSwitchActive: true })).toBe(false);
    expect(isGateSafe({ ...safeGate, leftAllowed: false })).toBe(false);
    expect(isGateSafe({ ...safeGate, rightAllowed: false })).toBe(false);
    expect(isGateSafe({ ...safeGate, reconcileOk: false })).toBe(false);
  });

  it("requires operator/size/gates for entry", () => {
    expect(
      isEntryAllowed({
        operatorConfirmed: true,
        operatorId: "operator-1",
        spreadSize: 1,
        gateState: safeGate,
      })
    ).toBe(true);

    expect(
      isEntryAllowed({
        operatorConfirmed: false,
        operatorId: "operator-1",
        spreadSize: 1,
        gateState: safeGate,
      })
    ).toBe(false);
  });

  it("supports add/reduce/close preconditions", () => {
    const pos = {
      direction: "LONG_SPREAD" as const,
      totalSize: 2,
      avgEntryZ: -2.1,
      updatedAt: "2026-01-01T00:00:00Z",
    };

    expect(
      isAddAllowed(pos, {
        operatorConfirmed: true,
        operatorId: "op",
        spreadSize: 1,
        gateState: safeGate,
      })
    ).toBe(true);
    expect(isReduceAllowed(pos, true, "op", 0.5)).toBe(true);
    expect(isCloseAllowed(pos)).toBe(true);
  });

  it("updates spread position deterministically", () => {
    const now = "2026-01-01T00:00:00Z";
    const flat = emptyPosition(now);
    const entered = applyEntryLike(flat, "LONG_SPREAD", 2, -2, now);
    expect(entered.direction).toBe("LONG_SPREAD");
    expect(entered.totalSize).toBe(2);

    const added = applyEntryLike(entered, "LONG_SPREAD", 1, -1, now);
    expect(added.totalSize).toBe(3);

    const reduced = applyReduce(added, 2.5, now);
    expect(reduced.totalSize).toBeCloseTo(0.5);

    const closed = applyReduce(reduced, 0.5, now);
    expect(closed.direction).toBe("NONE");
    expect(closed.totalSize).toBe(0);
  });

});
