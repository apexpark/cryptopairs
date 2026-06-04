import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("keeps mirrored left/right axis labels aligned on the same y coordinates", () => {
    const { container } = render(
      <LineChart
        values={[0.2, 1.5, -0.6, 0.9, -2.2, -3.1, -2.5]}
        thresholds={[
          { value: 3.2, tone: "bad" },
          { value: 1.8, tone: "warn" },
          { value: 0, tone: "info" },
          { value: -1.8, tone: "warn" },
          { value: -3.2, tone: "bad" },
        ]}
        showThresholdLabels
        mirrorThresholdLabels
      />
    );

    const labels320 = Array.from(container.querySelectorAll("text")).filter(
      (node) => node.textContent === "3.20"
    );
    expect(labels320).toHaveLength(2);
    expect(labels320[0]?.getAttribute("y")).toEqual(labels320[1]?.getAttribute("y"));
  });

  it("supports zoom controls when enabled", () => {
    const values = Array.from({ length: 120 }, (_, index) => Math.sin(index / 6));
    const timestamps = values.map((_, index) =>
      new Date(Date.UTC(2026, 1, 24, 0, index)).toISOString()
    );
    render(<LineChart values={values} timestamps={timestamps} zoomEnabled />);

    expect(screen.getByText("120/120 bars")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "4x" }));
    expect(screen.getByText("30/120 bars")).toBeInTheDocument();
  });

  it("anchors initial zoomed data loads to the newest point", async () => {
    const values = Array.from({ length: 400 }, (_, index) => index);
    const timestamps = values.map((_, index) =>
      new Date(Date.UTC(2026, 4, 19, 0, index)).toISOString()
    );
    const { rerender } = render(
      <LineChart
        values={[]}
        timestamps={[]}
        zoomEnabled
        initialZoomFactor={16}
        showLatestValueLabel
        latestValueLabelFormatter={(value) => `Z ${value.toFixed(2)}`}
      />
    );

    rerender(
      <LineChart
        values={values}
        timestamps={timestamps}
        zoomEnabled
        initialZoomFactor={16}
        showLatestValueLabel
        latestValueLabelFormatter={(value) => `Z ${value.toFixed(2)}`}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Z 399.00")).toBeInTheDocument();
    });
    expect(screen.queryByText("Z 24.00")).not.toBeInTheDocument();
  });

  it("uses the measured container width for wide chart viewboxes", async () => {
    class ResizeObserverMock {
      private readonly callback: ResizeObserverCallback;

      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
      }

      observe(target: Element): void {
        this.callback(
          [
            {
              target,
              contentRect: {
                width: 2200,
                height: 500,
                top: 0,
                right: 2200,
                bottom: 500,
                left: 0,
                x: 0,
                y: 0,
                toJSON: () => ({}),
              },
            } as ResizeObserverEntry,
          ],
          this as ResizeObserver
        );
      }

      unobserve(): void {}

      disconnect(): void {}
    }

    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    try {
      const { container } = render(
        <LineChart values={[0, 0.5, -0.2, 1.1]} height={500} />
      );

      await waitFor(() => {
        expect(container.querySelector("svg")?.getAttribute("viewBox")).toBe("0 0 2200 500");
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
