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

export default function LineChart({
  values,
  timestamps = [],
  markers = [],
  thresholds = [],
  height = 260,
  title,
  unavailableText = "No data available",
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
  const leftPadding = 30;
  const rightPadding = 18;
  const topPadding = 18;
  const hasTimestampAxis = timestamps.length === values.length && values.length >= 2;
  const bottomPadding = hasTimestampAxis ? 34 : 24;
  const min = Math.min(...values, ...thresholds.map((item) => item.value));
  const max = Math.max(...values, ...thresholds.map((item) => item.value));
  const span = Math.max(max - min, 1e-6);

  const mapX = (index: number) =>
    leftPadding + (index / (values.length - 1)) * (width - leftPadding - rightPadding);
  const mapY = (value: number) =>
    topPadding + (1 - (value - min) / span) * (height - topPadding - bottomPadding);

  const points = values.map((value, index) => `${mapX(index)},${mapY(value)}`).join(" ");
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
              <line key={`vx-${x}`} x1={x} y1={topPadding} x2={x} y2={height - bottomPadding} />
            );
          })}
          {Array.from({ length: 7 }).map((_, i) => {
            const y = topPadding + (i / 6) * (height - topPadding - bottomPadding);
            return (
              <line key={`hy-${y}`} x1={leftPadding} y1={y} x2={width - rightPadding} y2={y} />
            );
          })}
        </g>

        {thresholds.map((threshold, index) => {
          const y = mapY(threshold.value);
          return (
            <line
              key={`threshold-${index}`}
              x1={leftPadding}
              y1={y}
              x2={width - rightPadding}
              y2={y}
              stroke={thresholdColor(threshold.tone)}
              strokeWidth={1}
              opacity={0.9}
            />
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
              r={4}
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
