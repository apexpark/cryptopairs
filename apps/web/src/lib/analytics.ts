import type { Candle, ChartMarker, SpreadSeriesPoint } from "../types";

export function timeframeMinutes(timeframe: "1m" | "15m" | "1h"): number {
  if (timeframe === "1m") {
    return 1;
  }
  if (timeframe === "15m") {
    return 15;
  }
  return 60;
}

export function alignCandles(
  left: Candle[],
  right: Candle[]
): Array<{ ts: string; leftClose: number; rightClose: number }> {
  const rightMap = new Map<string, number>();
  for (const candle of right) {
    rightMap.set(candle.ts, candle.close);
  }

  const aligned: Array<{ ts: string; leftClose: number; rightClose: number }> = [];
  for (const candle of left) {
    const rightClose = rightMap.get(candle.ts);
    if (rightClose !== undefined && candle.close > 0 && rightClose > 0) {
      aligned.push({
        ts: candle.ts,
        leftClose: candle.close,
        rightClose,
      });
    }
  }
  return aligned;
}

export function computeSpreadSeries(
  aligned: Array<{ ts: string; leftClose: number; rightClose: number }>,
  hedgeRatio: number
): SpreadSeriesPoint[] {
  if (aligned.length < 2) {
    return [];
  }

  const spread = aligned.map((row) =>
    Math.log(row.leftClose) - hedgeRatio * Math.log(row.rightClose)
  );
  const mean = spread.reduce((sum, value) => sum + value, 0) / spread.length;
  const variance =
    spread.reduce((sum, value) => sum + (value - mean) ** 2, 0) / spread.length;
  const std = Math.sqrt(variance);
  if (!Number.isFinite(std) || std <= 0) {
    return [];
  }

  const result: SpreadSeriesPoint[] = [];
  for (let i = 1; i < aligned.length; i += 1) {
    const prev = aligned[i - 1];
    const current = aligned[i];
    const z = (spread[i] - mean) / std;
    const leftReturn = current.leftClose / prev.leftClose - 1;
    const rightReturn = current.rightClose / prev.rightClose - 1;
    const spreadReturn = leftReturn - hedgeRatio * rightReturn;
    result.push({
      ts: current.ts,
      z,
      spreadReturn,
    });
  }

  return result;
}

export function deriveMarkers(
  points: SpreadSeriesPoint[],
  entryBand: number,
  exitBand: number,
  stopBand: number
): ChartMarker[] {
  const markers: ChartMarker[] = [];
  let position: 0 | 1 | -1 = 0;

  for (let i = 0; i < points.length; i += 1) {
    const z = points[i].z;
    if (position === 0) {
      if (z <= -entryBand || z >= entryBand) {
        position = z <= -entryBand ? 1 : -1;
        markers.push({ index: i, kind: "entry" });
      }
      continue;
    }

    if (Math.abs(z) >= stopBand) {
      position = 0;
      markers.push({ index: i, kind: "stop" });
      continue;
    }

    if (Math.abs(z) <= exitBand) {
      position = 0;
      markers.push({ index: i, kind: "exit" });
    }
  }

  return markers;
}

export function simulateHypotheticalEquity(
  points: SpreadSeriesPoint[],
  entryBand: number,
  exitBand: number,
  stopBand: number,
  roundTripCostBps: number
): number[] {
  const equity: number[] = [];
  let cumulative = 1;
  let position: 0 | 1 | -1 = 0;

  for (let i = 0; i < points.length; i += 1) {
    const point = points[i];

    if (position === 0) {
      if (point.z <= -entryBand) {
        position = 1;
        cumulative *= 1 - roundTripCostBps / 20000;
      } else if (point.z >= entryBand) {
        position = -1;
        cumulative *= 1 - roundTripCostBps / 20000;
      }
    }

    if (position !== 0) {
      const signedReturn = position === 1 ? point.spreadReturn : -point.spreadReturn;
      cumulative *= 1 + signedReturn;
      if (Math.abs(point.z) <= exitBand || Math.abs(point.z) >= stopBand) {
        position = 0;
        cumulative *= 1 - roundTripCostBps / 20000;
      }
    }

    equity.push(cumulative);
  }

  return equity;
}
