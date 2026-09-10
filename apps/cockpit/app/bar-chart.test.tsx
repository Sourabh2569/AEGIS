import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BarChart from "./bar-chart";

describe("BarChart", () => {
  it("renders nothing for empty data", () => {
    const { container } = render(<BarChart data={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders one column per datum", () => {
    const { container } = render(
      <BarChart
        data={[
          { label: "A", value: 10 },
          { label: "B", value: -5 },
        ]}
      />,
    );
    expect(container.querySelectorAll(".bar-chart-col").length).toBe(2);
  });

  it("scales bar height by value/max", () => {
    const { container } = render(
      <BarChart
        data={[
          { label: "Full", value: 100 },
          { label: "Half", value: 50 },
        ]}
      />,
    );
    const bars = container.querySelectorAll<HTMLElement>(".bar-chart-bar");
    expect(bars[0].style.height).toBe("100%");
    expect(bars[1].style.height).toBe("50%");
  });

  it("auto-colors by sign when tone is not given", () => {
    const { container } = render(
      <BarChart
        data={[
          { label: "Up", value: 5 },
          { label: "Down", value: -5 },
        ]}
      />,
    );
    const bars = container.querySelectorAll(".bar-chart-bar");
    expect(bars[0]).toHaveClass("pos");
    expect(bars[1]).toHaveClass("neg");
  });

  it("lets an explicit tone override the sign default", () => {
    const { container } = render(<BarChart data={[{ label: "Weird", value: 5, tone: "neg" }]} />);
    expect(container.querySelector(".bar-chart-bar")).toHaveClass("neg");
  });
});
