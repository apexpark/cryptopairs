import { render, screen } from "@testing-library/react";
import LineChart from "../components/LineChart";

describe("LineChart current value label", () => {
  it("renders and updates the latest value label on rerender", () => {
    const { rerender } = render(
      <LineChart
        values={[0, 0.5, 1.25]}
        timestamps={[
          "2026-02-24T00:00:00Z",
          "2026-02-24T00:01:00Z",
          "2026-02-24T00:02:00Z",
        ]}
        showLatestValueLabel
        latestValueLabelFormatter={(value) => `Z ${value.toFixed(2)}`}
      />
    );

    expect(screen.getByText("Z 1.25")).toBeInTheDocument();

    rerender(
      <LineChart
        values={[0, 0.5, -1.5]}
        timestamps={[
          "2026-02-24T00:00:00Z",
          "2026-02-24T00:01:00Z",
          "2026-02-24T00:02:00Z",
        ]}
        showLatestValueLabel
        latestValueLabelFormatter={(value) => `Z ${value.toFixed(2)}`}
      />
    );

    expect(screen.getByText("Z -1.50")).toBeInTheDocument();
  });

  it("keeps recent tail points distinct in trimmed mode instead of flattening them at the floor", () => {
    const values = [...Array.from({ length: 26 }, (_, index) => Math.sin(index / 2) * 0.9), -3.6, -3.8];
    const timestamps = values.map((_, index) =>
      new Date(Date.UTC(2026, 1, 24, 0, index)).toISOString()
    );
    const { container } = render(
      <LineChart values={values} timestamps={timestamps} valueScaleMode="trimmed" />
    );

    const polyline = container.querySelector("polyline");
    expect(polyline).not.toBeNull();
    const points = (polyline?.getAttribute("points") ?? "")
      .trim()
      .split(" ")
      .filter((point) => point.includes(","));
    const yValues = points.map((point) => Number(point.split(",")[1]));
    const latestY = yValues[yValues.length - 1];
    const previousY = yValues[yValues.length - 2];

    expect(Number.isFinite(previousY)).toBe(true);
    expect(Number.isFinite(latestY)).toBe(true);
    expect(Math.abs(latestY - previousY)).toBeGreaterThan(0.5);
  });
});
