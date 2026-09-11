import { apiGet } from "./api-client";

type SummaryLite = { latest_nav: { nav: string } | null };

export type CombinedReturn = {
  returnPct: number | null;
  combinedNav: number;
  combinedStartingCapital: number;
  countWithNav: number;
};

/** Real combined return across a set of paper portfolios, derived from the
 * same GET /api/v1/paper-portfolios/{id}/summary call the Portfolio page's
 * HealthPanel already makes for one portfolio at a time -- no new backend
 * endpoint, just the same real NAV data aggregated across all of them. */
export async function fetchCombinedReturn(
  portfolios: { paper_portfolio_id: string; starting_capital: string }[],
): Promise<CombinedReturn> {
  const summaries = await Promise.all(
    portfolios.map((portfolio) =>
      apiGet<SummaryLite | null>(
        `/api/v1/paper-portfolios/${portfolio.paper_portfolio_id}/summary`,
        null,
      ),
    ),
  );

  let combinedNav = 0;
  let combinedStartingCapital = 0;
  let countWithNav = 0;

  portfolios.forEach((portfolio, index) => {
    const nav = summaries[index]?.latest_nav?.nav;
    if (nav === null || nav === undefined) return;
    combinedNav += Number(nav);
    combinedStartingCapital += Number(portfolio.starting_capital);
    countWithNav += 1;
  });

  const returnPct =
    countWithNav > 0 && combinedStartingCapital > 0
      ? (combinedNav - combinedStartingCapital) / combinedStartingCapital
      : null;

  return { returnPct, combinedNav, combinedStartingCapital, countWithNav };
}

export function signedPct(value: number): string {
  const formatted = (value * 100).toFixed(2);
  return `${value >= 0 ? "+" : ""}${formatted}%`;
}
