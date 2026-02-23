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
}

function markerColor(kind: ChartMarker["kind"]): string {
  if (kind === "entry") {
    return "var(--tone-ok)";
  }
  if (kind === "exit") {
    return "var(--tone-warn)";
  }
  return "var(--tone-bad)";
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
}: LineChartProps): JSX.Element {
  if (values.length < 2) {
    return (
      <div className="chart chart-empty" style={{ minHeight: `${height}px` }}>
        {title ? <div className="chart-title">{title}</div> : null}
        <div className="empty-text">{unavailableText}</div>
      </div>
    );
  }

  const width = 1000;
  const leftPadding = 74;
  const rightPadding = showThresholdLabels ? 82 : 24;
  const topPadding = 18;
  const hasTimestampAxis = timestamps.length === values.length && values.length >= 2;
  const bottomPadding = hasTimestampAxis ? 40 : 24;
  const chartBottom = height - bottomPadding;
  const thresholdValues = thresholds.map((item) => item.value);
  const fullMin = Math.min(...values, ...thresholdValues);
  const fullMax = Math.max(...values, ...thresholdValues);

  let domainMin = fullMin;
  let domainMax = fullMax;
  if (valueScaleMode === "trimmed" && values.length >= 20) {
    const sorted = [...values].sort((left, right) => left - right);
    const trimmedMin = percentile(sorted, 0.03);
    const trimmedMax = percentile(sorted, 0.97);
    const candidateMin = thresholdValues.length ? Math.min(trimmedMin, ...thresholdValues) : trimmedMin;
    const candidateMax = thresholdValues.length ? Math.max(trimmedMax, ...thresholdValues) : trimmedMax;
    const fullSpan = Math.max(fullMax - fullMin, 1e-6);
    const candidateSpan = Math.max(candidateMax - candidateMin, 1e-6);
    if (candidateSpan / fullSpan >= 0.2) {
      domainMin = candidateMin;
      domainMax = candidateMax;
    }
  }
  const span = Math.max(domainMax - domainMin, 1e-6);

  const mapX = (index: number) =>
    leftPadding + (index / (values.length - 1)) * (width - leftPadding - rightPadding);
  const mapY = (value: number) => {
    const raw = topPadding + (1 - (value - domainMin) / span) * (chartBottom - topPadding);
    return clamp(raw, topPadding, chartBottom);
  };

  const points = values.map((value, index) => `${mapX(index)},${mapY(value)}`).join(" ");
  const horizontalGridCount = Math.max(yTickCount, 3);
  const yAxisTicks = Array.from({ length: horizontalGridCount }).map((_, index) => {
    const ratio = index / (horizontalGridCount - 1);
    const y = topPadding + ratio * (chartBottom - topPadding);
    const value = domainMax - ratio * span;
    return { y, value };
  });
  const axisTickIndexes = Array.from(new Set([0, Math.floor((values.length - 1) / 2), values.length - 1]));
  const xAxisLabels = hasTimestampAxis
    ? axisTickIndexes.map((index) => {
        const raw = timestamps[index];
        const date = new Date(raw);
        if (Number.isNaN(date.getTime())) {
          return { index, label: `#${index}` };
        }
        const earliest = new Date(timestamps[0]).getTime();
        const latest = new Date(timestamps[timestamps.length - 1]).getTime();
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

  return (
    <div className="chart" style={{ minHeight: `${height}px` }}>
      {title ? <div className="chart-title">{title}</div> : null}
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <g className="grid">
          {Array.from({ length: 9 }).map((_, i) => {
            const x = leftPadding + (i / 8) * (width - leftPadding - rightPadding);
            return (
              <line key={`vx-${x}`} x1={x} y1={topPadding} x2={x} y2={chartBottom} />
            );
          })}
          {yAxisTicks.map((tick, index) => (
            <line key={`hy-${index}`} x1={leftPadding} y1={tick.y} x2={width - rightPadding} y2={tick.y} />
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

        {thresholds.map((threshold, index) => {
          const y = mapY(threshold.value);
          const thresholdLabelY = clamp(y - 4, topPadding + 10, chartBottom - 4);
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
              />
              {showThresholdLabels ? (
                <text className="threshold-label" x={width - 6} y={thresholdLabelY} textAnchor="end">
                  {yAxisFormatter(threshold.value)}
                </text>
              ) : null}
            </g>
          );
        })}

        <polyline fill="none" stroke="var(--tone-info)" strokeWidth={2} points={points} />

        {markers
          .filter((marker) => marker.index >= 0 && marker.index < values.length)
          .map((marker, index) => (
            <circle
              key={`${marker.kind}-${marker.index}-${index}`}
              cx={mapX(marker.index)}
              cy={mapY(values[marker.index])}
              r={markerRadius}
              fill={markerColor(marker.kind)}
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
