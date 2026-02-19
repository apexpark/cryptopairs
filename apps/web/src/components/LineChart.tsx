import type { ChartMarker } from "../types";

interface Threshold {
  value: number;
  tone: "warn" | "bad" | "ok" | "info";
}

interface LineChartProps {
  values: number[];
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
  const padding = 24;
  const min = Math.min(...values, ...thresholds.map((item) => item.value));
  const max = Math.max(...values, ...thresholds.map((item) => item.value));
  const span = Math.max(max - min, 1e-6);

  const mapX = (index: number) =>
    padding + (index / (values.length - 1)) * (width - padding * 2);
  const mapY = (value: number) =>
    padding + (1 - (value - min) / span) * (height - padding * 2);

  const points = values.map((value, index) => `${mapX(index)},${mapY(value)}`).join(" ");

  return (
    <div className="chart" style={{ minHeight: `${height}px` }}>
      {title ? <div className="chart-title">{title}</div> : null}
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <g className="grid">
          {Array.from({ length: 9 }).map((_, i) => {
            const x = padding + (i / 8) * (width - padding * 2);
            return <line key={`vx-${x}`} x1={x} y1={padding} x2={x} y2={height - padding} />;
          })}
          {Array.from({ length: 7 }).map((_, i) => {
            const y = padding + (i / 6) * (height - padding * 2);
            return <line key={`hy-${y}`} x1={padding} y1={y} x2={width - padding} y2={y} />;
          })}
        </g>

        {thresholds.map((threshold, index) => {
          const y = mapY(threshold.value);
          return (
            <line
              key={`threshold-${index}`}
              x1={padding}
              y1={y}
              x2={width - padding}
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
      </svg>
    </div>
  );
}
