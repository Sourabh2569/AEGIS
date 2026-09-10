// lightweight-charts needs literal color strings, not CSS custom properties,
// so this mirrors the light-theme tokens in globals.css as one shared source
// of truth for the three chart wrappers instead of three separate copies.
export const CHART_THEME = {
  background: "#ffffff",
  text: "#5b6472",
  grid: "#edf0f5",
  border: "#e2e6ee",
  accent: "#2f6fed",
  benchmark: "#9aa3b2",
  buy: "#17a672",
  sell: "#e0334f",
  hold: "#c97f14",
} as const;
