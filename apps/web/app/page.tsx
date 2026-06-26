import AegisDashboard, { type DashboardData } from "./aegis-dashboard";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export default async function Page() {
  const [
    overview,
    providers,
    datasets,
    ingestions,
    instruments,
    audits,
    backtests,
    sprint2Reports,
    paperPortfolios,
    paperIntents,
    paperIncidents,
    paperJobs,
    paperReviews,
    dataSourceMode,
    providerHealth,
    dataFreshness,
    liveQuotes,
    marketCalendar,
  ] = await Promise.all([
    fetchJson<Record<string, unknown>>("/api/v1/system/overview", {}),
    fetchJson<DashboardData["providers"]>("/api/v1/providers", []),
    fetchJson<DashboardData["datasets"]>("/api/v1/datasets", []),
    fetchJson<DashboardData["ingestions"]>("/api/v1/ingestions", []),
    fetchJson<DashboardData["instruments"]>("/api/v1/instruments", []),
    fetchJson<DashboardData["audits"]>("/api/v1/audit-events", []),
    fetchJson<DashboardData["backtests"]>("/api/v1/backtest-runs", []),
    fetchJson<DashboardData["sprint2Reports"]>("/api/v1/sprint-2/reports", []),
    fetchJson<DashboardData["paperPortfolios"]>("/api/v1/paper-portfolios", []),
    fetchJson<DashboardData["paperIntents"]>("/api/v1/paper-trade-intents", []),
    fetchJson<DashboardData["paperIncidents"]>("/api/v1/paper-incidents", []),
    fetchJson<DashboardData["paperJobs"]>("/api/v1/paper-session-jobs", []),
    fetchJson<DashboardData["paperReviews"]>("/api/v1/paper-corporate-action-reviews", []),
    fetchJson<DashboardData["dataSourceMode"]>("/api/v1/data-source/mode", {}),
    fetchJson<DashboardData["providerHealth"]>("/api/v1/provider-health", []),
    fetchJson<DashboardData["dataFreshness"]>("/api/v1/data-freshness", []),
    fetchJson<DashboardData["liveQuotes"]>("/api/v1/live-quotes", []),
    fetchJson<DashboardData["marketCalendar"]>("/api/v1/market-calendar", []),
  ]);

  return (
    <AegisDashboard
      data={{
        overview,
        providers,
        datasets,
        ingestions,
        instruments,
        audits,
        backtests,
        sprint2Reports,
        paperPortfolios,
        paperIntents,
        paperIncidents,
        paperJobs,
        paperReviews,
        dataSourceMode,
        providerHealth,
        dataFreshness,
        liveQuotes,
        marketCalendar,
      }}
    />
  );
}
