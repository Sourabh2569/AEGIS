import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Gauge from "./gauge";

function filledPathColor(container: HTMLElement): string | null {
  const paths = container.querySelectorAll("path");
  return paths[1]?.getAttribute("stroke") ?? null;
}

describe("Gauge", () => {
  it("uses the buy tone at 80% or more deployment", () => {
    const { container } = render(<Gauge value={8} max={10} label="Positions used" />);
    expect(filledPathColor(container)).toBe("var(--buy)");
  });

  it("uses the accent tone between 50% and 80% deployment", () => {
    const { container } = render(<Gauge value={6} max={10} label="Positions used" />);
    expect(filledPathColor(container)).toBe("var(--accent)");
  });

  it("uses the neutral tone below 50% deployment", () => {
    const { container } = render(<Gauge value={2} max={10} label="Positions used" />);
    expect(filledPathColor(container)).toBe("var(--neutral)");
  });

  it("does not divide by zero when max is 0", () => {
    const { container } = render(<Gauge value={0} max={0} label="Positions used" />);
    expect(filledPathColor(container)).toBe("var(--neutral)");
  });

  it("renders the value, max, and label as text", () => {
    render(<Gauge value={6} max={10} label="Positions used" />);
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("/ 10")).toBeInTheDocument();
    expect(screen.getByText("Positions used")).toBeInTheDocument();
  });
});
