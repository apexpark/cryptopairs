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
});
