import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AchievementBadge, AchievementGrid, type Achievement } from "./achievement-badge";

function achievement(overrides: Partial<Achievement> = {}): Achievement {
  return {
    id: "test-achievement",
    category: "PORTFOLIO",
    title: "First Live Approval",
    description: "A real paper-trade intent is approved for this portfolio for the first time.",
    achieved: false,
    achieved_at: null,
    detail: "No real approvals yet for this portfolio.",
    ...overrides,
  };
}

describe("AchievementBadge", () => {
  it("shows the locked state and its detail for an unachieved milestone", () => {
    render(<AchievementBadge achievement={achievement()} />);
    expect(screen.getByText("First Live Approval")).toBeInTheDocument();
    expect(screen.getByText("No real approvals yet for this portfolio.")).toBeInTheDocument();
    expect(document.querySelector(".achievement-card.locked")).not.toBeNull();
    expect(document.querySelector(".achievement-icon.locked")).not.toBeNull();
  });

  it("shows the achieved state with the category's tone class", () => {
    render(
      <AchievementBadge
        achievement={achievement({
          achieved: true,
          detail: "First real trade approved on 2026-09-08",
        })}
      />,
    );
    expect(document.querySelector(".achievement-card.achieved")).not.toBeNull();
    expect(document.querySelector(".achievement-icon.PORTFOLIO")).not.toBeNull();
    expect(screen.getByText("First real trade approved on 2026-09-08")).toBeInTheDocument();
  });
});

describe("AchievementGrid", () => {
  it("renders one card per achievement", () => {
    render(
      <AchievementGrid
        achievements={[
          achievement({ id: "a" }),
          achievement({ id: "b" }),
          achievement({ id: "c" }),
        ]}
      />,
    );
    expect(document.querySelectorAll(".achievement-card").length).toBe(3);
  });
});
