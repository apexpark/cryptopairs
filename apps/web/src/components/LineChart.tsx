import { useEffect, useMemo, useState } from "react";
import type { ChartMarker } from "../types";

interface Threshold {
  value: number;
  tone: "warn" | "bad" | "ok" | "info";
}

interface LineChartProps {
  values: number[];
  timestamps?: string[];
  markers?: ChartMarker[];
  thresholds?: Threshold[];
  height?: number;
  title?: string;
  unavailableText?: string;
  yAxisFormatter?: (value: number) => string;
  showThresholdLabels?: boolean;
  markerRadius?: number;
  yTickCount?: number;
  valueScaleMode?: "full" | "trimmed";
  includeThresholdsInDomain?: boolean;
  mirrorThresholdLabels?: boolean;
  showLatestValueLabel?: boolean;
  latestValueLabelFormatter?: (value: number) => string;
  zoomEnabled?: boolean;
}

function markerColor(kind: ChartMarker["kind"]): string {
  if (kind === "entry") {
    return "var(--tone-ok)";
  }
  if (kind === "exit") {
    return "var(--tone-warn)";
  }
  if (kind === "execution-entry") {
    return "var(--tone-info)";
  }
  if (kind === "execution-exit") {
    return "var(--tone-execution-exit, #b38cff)";
  }
  return "var(--tone-bad)";
}

function markerStrokeColor(kind: ChartMarker["kind"]): string {
  if (kind === "execution-entry" || kind === "execution-exit") {
    return "var(--panel-2)";
  }
  return "none";
}

function markerRadiusForKind(kind: ChartMarker["kind"], defaultRadius: number): number {
  if (kind === "execution-entry" || kind === "execution-exit") {
    return defaultRadius + 1.5;
  }
  return defaultRadius;
}

function thresholdColor(tone: Threshold["tone"]): string {
  if (tone === "ok") {
    return "var(--tone-ok)";
  }
  if (tone === "info") {
    return "var(--tone-info)";
  }
  if (tone === "warn") {
    return "var(--tone-warn)";
  }
  return "var(--tone-bad)";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function percentile(sortedValues: number[], ratio: number): number {
  if (!sortedValues.length) {
    return 0;
  }
  const clampedRatio = clamp(ratio, 0, 1);
  const index = clampedRatio * (sortedValues.length - 1);
  const lowerIndex = Math.floor(index);
  const upperIndex = Math.ceil(index);
  if (lowerIndex === upperIndex) {
    return sortedValues[lowerIndex];
  }
  const weight = index - lowerIndex;
  return sortedValues[lowerIndex] * (1 - weight) + sortedValues[upperIndex] * weight;
}

export default function LineChart({
  values,
  timestamps = [],
  markers = [],
  thresholds = [],
  height = 260,
  title,
  unavailableText = "No data available",
  yAxisFormatter = (value) => value.toFixed(2),
  showThresholdLabels = false,
  markerRadius = 4,
  yTickCount = 7,
  valueScaleMode = "full",
  includeThresholdsInDomain = true,
  mirrorThresholdLabels = false,
  showLatestValueLabel = false,
  latestValueLabelFormatter = (value) => value.toFixed(2),
  zoomEnabled = false,
}: LineChartProps): JSX.Element {
  const minZoomWindowPoints = Math.min(values.length, 24);
  const zoomOptions = useMemo(() => {
    const base = [1, 2, 4, 8, 16];
    return base.filter((factor) => factor === 1 || Math.floor(values.length / factor) >= minZoomWindowPoints);
  }, [minZoomWindowPoints, values.length]);
  const [zoomFactor, setZoomFactor] = useState(1);
  const [windowEndIndex, setWindowEndIndex] = useState(values.length - 1);

  useEffect(() => {
    if (!zoomEnabled) {
      setZoomFactor(1);
      setWindowEndIndex(values.length - 1);
      return;
    }
    setZoomFactor((previous) => (zoomOptions.includes(previous) ? previous : 1));
    setWindowEndIndex((previous) => {
      const latest = values.length - 1;
      if (previous >= latest - 1) {
        return latest;
      }
      return clamp(previous, 0, latest);
    });
  }, [zoomEnabled, zoomOptions, values.length]);

  const zoomIsActive = zoomEnabled && zoomOptions.length > 1;
  const visiblePoints = zoomIsActive
    ? clamp(Math.floor(values.length / zoomFactor), minZoomWindowPoints, values.length)
    : values.length;
  const maxEndIndex = values.length - 1;
  const minEndIndex = visiblePoints - 1;
  const effectiveEndIndex = zoomIsActive
    ? clamp(windowEndIndex, minEndIndex, maxEndIndex)
    : maxEndIndex;
  const windowStartIndex = zoomIsActive ? effectiveEndIndex - visiblePoints + 1 : 0;
  const plotValues = values.slice(windowStartIndex, effectiveEndIndex + 1);
  const hasTimestampData = timestamps.length === values.length;
  const plotTimestamps = hasTimestampData
    ? timestamps.slice(windowStartIndex, effectiveEndIndex + 1)
    : [];
  const plotMarkers = markers
    .filter((marker) => marker.index >= windowStartIndex && marker.index <= effectiveEndIndex)
    .map((marker) => ({ ...marker, index: marker.index - windowStartIndex }));

  if (values.length < 2 || plotValues.length < 2) {
    return (
      <div className="chart chart-empty" style={{ height: `${height}px` }}>
        {title ? <div className="chart-title">{title}</div> : null}
        <div className="empty-text">{unavailableText}</div>
      </div>
    );
  }

  const width = 1000;
  const leftPadding = 74;
  const rightPadding = showThresholdLabels ? 82 : 24;
  const topPadding = 10;
  const hasTimestampAxis = plotTimestamps.length === plotValues.length && plotValues.length >= 2;
  const bottomPadding = hasTimestampAxis ? 28 : 18;
  const chartBottom = height - bottomPadding;
  const thresholdValues = thresholds.map((item) => item.value);
  const domainValues = includeThresholdsInDomain
    ? [...plotValues, ...thresholdValues]
    : plotValues;
  const fullMin = Math.min(...domainValues);
  const fullMax = Math.max(...domainValues);

  let domainMin = fullMin;
  let domainMax = fullMax;
  if (valueScaleMode === "trimmed" && plotValues.length >= 20) {
    const sorted = [...plotValues].sort((left, right) => left - right);
    const trimmedMin = percentile(sorted, 0.03);
    const trimmedMax = percentile(sorted, 0.97);
    const candidateMin =
      includeThresholdsInDomain && thresholdValues.length
        ? Math.min(trimmedMin, ...thresholdValues)
        : trimmedMin;
    const candidateMax =
      includeThresholdsInDomain && thresholdValues.length
        ? Math.max(trimmedMax, ...thresholdValues)
        : trimmedMax;
    const fullSpan = Math.max(fullMax - fullMin, 1e-6);
    const candidateSpan = Math.max(candidateMax - candidateMin, 1e-6);
    if (candidateSpan / fullSpan >= 0.2) {
      const recentTailWindowSize = Math.min(
        plotValues.length,
        Math.max(6, Math.ceil(plotValues.length * 0.1))
      );
      const recentTailValues = plotValues.slice(-recentTailWindowSize);
      const recentTailMin = Math.min(...recentTailValues);
      const recentTailMax = Math.max(...recentTailValues);
      // Prevent right-edge clipping by always including the recent tail in trimmed mode.
      domainMin = Math.min(candidateMin, recentTailMin);
      domainMax = Math.max(candidateMax, recentTailMax);
    }
  }
  const span = Math.max(domainMax - domainMin, 1e-6);

  const mapX = (index: number) =>
    leftPadding + (index / (plotValues.length - 1)) * (width - leftPadding - rightPadding);
  const mapY = (value: number) => {
    const raw = topPadding + (1 - (value - domainMin) / span) * (chartBottom - topPadding);
    return clamp(raw, topPadding, chartBottom);
  };

  const points = plotValues.map((value, index) => `${mapX(index)},${mapY(value)}`).join(" ");
  const latestValueIndex = plotValues.length - 1;
  const latestValue = plotValues[latestValueIndex];
  const latestX = mapX(latestValueIndex);
  const latestY = mapY(latestValue);
  const latestLabelY = clamp(latestY + 4, topPadding + 10, chartBottom - 4);
  const horizontalGridCount = Math.max(yTickCount, 3);
  const thresholdMirrorTicks = Array.from(new Set(thresholdValues))
    .sort((left, right) => right - left)
    .map((value) => ({ y: mapY(value), value }));
  const yAxisTicks =
    mirrorThresholdLabels && thresholdMirrorTicks.length
      ? thresholdMirrorTicks
      : Array.from({ length: horizontalGridCount }).map((_, index) => {
          const ratio = index / (horizontalGridCount - 1);
          const y = topPadding + ratio * (chartBottom - topPadding);
          const value = domainMax - ratio * span;
          return { y, value };
        });
  const axisTickIndexes = Array.from(
    new Set([0, Math.floor((plotValues.length - 1) / 2), plotValues.length - 1])
  );
  const xAxisLabels = hasTimestampAxis
    ? axisTickIndexes.map((index) => {
        const raw = plotTimestamps[index];
        const date = new Date(raw);
        if (Number.isNaN(date.getTime())) {
          return { index, label: `#${index}` };
        }
        const earliest = new Date(plotTimestamps[0]).getTime();
        const latest = new Date(plotTimestamps[plotTimestamps.length - 1]).getTime();
        const showDate = Number.isFinite(earliest) && Number.isFinite(latest) && latest - earliest >= 86_400_000;
        return {
          index,
          label: date.toLocaleString([], {
            month: showDate ? "short" : undefined,
            day: showDate ? "2-digit" : undefined,
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          }),
        };
      })
    : [];

  const canPanLeft = zoomIsActive && windowStartIndex > 0;
  const canPanRight = zoomIsActive && effectiveEndIndex < maxEndIndex;
  const panStep = Math.max(1, Math.floor(visiblePoints * 0.2));

  return (
    <div className="chart" style={{ height: `${height}px` }}>
      {title ? <div className="chart-title">{title}</div> : null}
      {zoomIsActive ? (
        <div className="chart-toolbar">
          <div className="chart-zoom-controls">
            {zoomOptions.map((factor) => (
              <button
                key={`zoom-${factor}`}
                type="button"
                className={factor === zoomFactor ? "active" : ""}
                onClick={() => {
                  setZoomFactor(factor);
                  setWindowEndIndex(values.length - 1);
                }}
              >
                {factor === 1 ? "Full" : `${factor}x`}
              </button>
            ))}
            <button
              type="button"
              onClick={() =>
                setWindowEndIndex((previous) => clamp(previous - panStep, minEndIndex, maxEndIndex))
              }
              disabled={!canPanLeft}
            >
              ◀
            </button>
            <button
              type="button"
              onClick={() =>
                setWindowEndIndex((previous) => clamp(previous + panStep, minEndIndex, maxEndIndex))
              }
              disabled={!canPanRight}
            >
              ▶
            </button>
            <button
              type="button"
              onClick={() => {
                setZoomFactor(1);
                setWindowEndIndex(values.length - 1);
              }}
              disabled={zoomFactor === 1 && !canPanLeft && !canPanRight}
            >
              Reset
            </button>
          </div>
          <span className="chart-zoom-meta">
            {plotValues.length}/{values.length} bars
          </span>
        </div>
      ) : null}
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
        <g className="grid">
          {Array.from({ length: 9 }).map((_, i) => {
            const x = leftPadding + (i / 8) * (width - leftPadding - rightPadding);
            return (
              <line
                key={`vx-${x}`}
                x1={x}
                y1={topPadding}
                x2={x}
                y2={chartBottom}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
          {yAxisTicks.map((tick, index) => (
            <line
              key={`hy-${index}`}
              x1={leftPadding}
              y1={tick.y}
              x2={width - rightPadding}
              y2={tick.y}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>

        {yAxisTicks.map((tick, index) => (
          <text
            key={`y-axis-label-${index}`}
            className="y-axis-label"
            x={leftPadding - 8}
            y={tick.y + 4}
            textAnchor="end"
          >
            {yAxisFormatter(tick.value)}
          </text>
        ))}

        {showThresholdLabels && mirrorThresholdLabels
          ? yAxisTicks.map((tick, index) => (
              <text
                key={`right-axis-label-${index}`}
                className="threshold-label"
                x={width - 6}
                y={tick.y + 4}
                textAnchor="end"
              >
                {yAxisFormatter(tick.value)}
              </text>
            ))
          : null}

        {thresholds.map((threshold, index) => {
          const y = mapY(threshold.value);
          const thresholdLabelY = clamp(y + 4, topPadding + 10, chartBottom - 4);
          return (
            <g key={`threshold-${index}`}>
              <line
                x1={leftPadding}
                y1={y}
                x2={width - rightPadding}
                y2={y}
                stroke={thresholdColor(threshold.tone)}
                strokeWidth={1}
                opacity={0.9}
                vectorEffect="non-scaling-stroke"
              />
              {showThresholdLabels && !mirrorThresholdLabels ? (
                <text className="threshold-label" x={width - 6} y={thresholdLabelY} textAnchor="end">
                  {yAxisFormatter(threshold.value)}
                </text>
              ) : null}
            </g>
          );
        })}

        <polyline
          fill="none"
          stroke="var(--tone-info)"
          strokeWidth={1.75}
          points={points}
          vectorEffect="non-scaling-stroke"
        />

        {showLatestValueLabel ? (
          <>
            <circle
              cx={latestX}
              cy={latestY}
              r={3.5}
              fill="var(--tone-info)"
              vectorEffect="non-scaling-stroke"
            />
            <text
              className="current-value-label"
              x={latestX + 8}
              y={latestLabelY}
              textAnchor="start"
            >
              {latestValueLabelFormatter(latestValue)}
            </text>
          </>
        ) : null}

        {plotMarkers.map((marker, index) => (
            <circle
              key={`${marker.kind}-${marker.index}-${index}`}
              cx={mapX(marker.index)}
              cy={mapY(plotValues[marker.index])}
              r={markerRadiusForKind(marker.kind, markerRadius)}
              fill={markerColor(marker.kind)}
              stroke={markerStrokeColor(marker.kind)}
              strokeWidth={marker.kind.startsWith("execution-") ? 1.5 : 0}
              vectorEffect="non-scaling-stroke"
            />
          ))}

        {xAxisLabels.map((item, idx) => (
          <text
            key={`axis-label-${item.index}`}
            className="x-axis-label"
            x={mapX(item.index)}
            y={height - 8}
            textAnchor={idx === 0 ? "start" : idx === xAxisLabels.length - 1 ? "end" : "middle"}
          >
            {item.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
