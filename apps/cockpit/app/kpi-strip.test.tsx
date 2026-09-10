import { render, screen } from "@testing-library/react";
import { Wallet } from "lucide-react";
import { describe, expect, it } from "vitest";
import { KpiCard, KpiStrip } from "./kpi-strip";

describe("KpiCard", () => {
  it("renders the label and value", () => {
    render(<KpiCard icon={Wallet} label="Total AUM" value="₹60,00,000" />);
    expect(screen.getByText("Total AUM")).toBeInTheDocument();
    expect(screen.getByText("₹60,00,000")).toBeInTheDocument();
  });

  it("renders a positive delta pill with the pos tone class", () => {
    render(
      <KpiCard icon={Wallet} label="Return" value="12%" delta={{ text: "+12%", tone: "pos" }} />,
    );
    expect(screen.getByText("+12%")).toHaveClass("delta-pill", "pos");
  });

  it("renders a negative delta pill with the neg tone class", () => {
    render(
      <KpiCard
        icon={Wallet}
        label="Max drawdown"
        value="-25.24%"
        delta={{ text: "worst peak-to-trough", tone: "neg" }}
      />,
    );
    expect(screen.getByText("worst peak-to-trough")).toHaveClass("delta-pill", "neg");
  });

  it("renders a caption when provided", () => {
    render(<KpiCard icon={Wallet} label="Active" value="22" caption="of 42 total" />);
    expect(screen.getByText("of 42 total")).toBeInTheDocument();
  });

  it("renders no foot section when neither delta nor caption is given", () => {
    const { container } = render(<KpiCard icon={Wallet} label="Active" value="22" />);
    expect(container.querySelector(".kpi-card-foot")).toBeNull();
  });
});

describe("KpiStrip", () => {
  it("wraps children in a kpi-strip container", () => {
    const { container } = render(
      <KpiStrip>
        <KpiCard icon={Wallet} label="A" value="1" />
        <KpiCard icon={Wallet} label="B" value="2" />
      </KpiStrip>,
    );
    expect(container.querySelector(".kpi-strip")?.children.length).toBe(2);
  });
});
