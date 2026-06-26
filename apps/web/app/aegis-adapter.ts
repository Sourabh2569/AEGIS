export type Provider = { id: string; name: string; status: string; is_active: boolean };
export type Dataset = { id: string; name: string; domain: string; criticality: string; status: string };
export type Ingestion = {
  id: string;
  dataset_name: string;
  status: string;
  records_received: number;
  records_accepted: number;
  records_rejected: number;
  error_summary: string[];
};
export type Instrument = {
  aegis_instrument_id: string;
  current_symbol: string;
  isin: string;
  company_legal_name: string;
  primary_exchange: string;
  trading_status: string;
  sector: string;
  mapping_confidence_score: number;
};
export type AuditEvent = {
  id: string;
  created_at: string;
  actor_id: string;
  event_type: string;
  entity_type: string;
  action: string;
  correlation_id: string;
};
export type BacktestRun = {
  backtest_run_id: string;
  name: string;
  status: string;
  instrument_id: string;
  start_date: string;
  end_date: string;
  starting_cash: string;
  dataset_version_id: string;
  execution_model_version: string;
  failure_reason_nullable?: string | null;
};
export type Sprint2Report = {
  scenario: string;
  ending_nav: string;
  total_return: string;
  cash_weight: string;
  gross_equity_exposure: string;
  total_transaction_cost: string;
  position_count: number;
};
export type PaperPortfolio = {
  paper_portfolio_id: string;
  name: string;
  status: string;
  starting_capital: string;
  risk_profile_version_id: string;
  portfolio_configuration_version: string;
  failure_reason_nullable?: string | null;
};
export type PaperIntent = {
  paper_trade_intent_id: string;
  paper_portfolio_id?: string;
  instrument_id: string;
  side: string;
  intent_status: string;
  approval_status: string;
  reason_codes_json: string[];
};
export type PaperIncident = {
  id: string;
  incident_type: string;
  severity: string;
  status: string;
  description: string;
};
export type PaperSessionJob = {
  id: string;
  paper_portfolio_id: string;
  session_date: string;
  status: string;
  attempts: number;
  failure_reason?: string | null;
};
export type PaperCorporateActionReview = {
  id: string;
  paper_portfolio_id: string;
  instrument_id: string;
  action_type: string;
  effective_date: string;
  support_status: string;
  decision: string;
};
export type ProviderHealth = {
  provider_id: string;
  provider_name: string;
  healthy: boolean;
  message: string;
  checked_at?: string | null;
  latency_ms?: number | null;
  mode: string;
  order_access: boolean;
};
export type DataFreshness = {
  dataset_name: string;
  status: string;
  latest_available_time?: string | null;
  checked_at: string;
  age_seconds?: number | null;
  max_age_seconds: number;
};
export type LiveQuote = {
  aegis_instrument_id: string;
  exchange: string;
  last_price: number;
  bid_price: number;
  ask_price: number;
  volume: number;
  event_time: string;
  available_time: string;
  ingested_time: string;
};
export type MarketCalendarSession = {
  exchange: string;
  session_date: string;
  is_open: boolean;
  open_time?: string | null;
  close_time?: string | null;
  timezone: string;
  available_time: string;
};

export type DashboardData = {
  overview: Record<string, unknown>;
  providers: Provider[];
  datasets: Dataset[];
  ingestions: Ingestion[];
  instruments: Instrument[];
  audits: AuditEvent[];
  backtests: BacktestRun[];
  sprint2Reports: Sprint2Report[];
  paperPortfolios: PaperPortfolio[];
  paperIntents: PaperIntent[];
  paperIncidents: PaperIncident[];
  paperJobs: PaperSessionJob[];
  paperReviews: PaperCorporateActionReview[];
  dataSourceMode: Record<string, unknown>;
  providerHealth: ProviderHealth[];
  dataFreshness: DataFreshness[];
  liveQuotes: LiveQuote[];
  marketCalendar: MarketCalendarSession[];
};

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const labelMap: Record<string, string> = {
  PAPER_TRADING_ONLY: "Paper only",
  NO_REAL_CAPITAL_DEPLOYED: "No real capital",
  NOT_BROKER_CONNECTED: "Broker disconnected",
  FIXTURE_SPEC_MODE: "Fixture mode",
  API_DATA_VISIBLE: "API data visible",
  GREEN: "Ready",
  GREEN_CAUTION: "Ready with caution",
  RED: "Blocked",
  AMBER: "Needs review",
  APPEND_ONLY: "Append-only audit",
  LIVE_EXECUTION_DISABLED: "Live execution locked",
  LIVE_EXECUTION_ENABLED: "Live execution",
  LIVE_READONLY: "Read-only market data",
  DATA_SOURCE_MODE: "Data mode",
  APPROVED_WITH_REDUCED_SIZE: "Approved at reduced size",
  CRITICAL_DIVERGENCE: "Critical divergence",
  WITHIN_EXPECTATION: "Within expectation",
  IN_PROGRESS: "In progress",
  NOT_STARTED: "Not started",
  NOT_ASSESSED: "Not assessed",
  BLOCKED: "Blocked",
  FROZEN: "Frozen",
  COMPLETED: "Completed",
  COMPLETED_WITH_WARNINGS: "Completed with warnings",
  HEALTHY: "Healthy",
  FRESH: "Fresh",
  STALE: "Stale",
  OPEN: "Open",
  CLOSED: "Closed",
  ACTIVE: "Active",
  READY: "Ready",
  DISABLED: "Disabled",
};

export function uiLabel(value: unknown): string {
  const raw = String(value ?? "");
  if (!raw) return "Not available";
  if (labelMap[raw]) return labelMap[raw];
  return raw
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function toneFor(value: unknown): Tone {
  const raw = String(value ?? "").toUpperCase();
  if (/RED|FAILED|CRITICAL|BLOCK|FROZEN|DISABLED|REJECTED|UNSUPPORTED|STALE/.test(raw)) return "danger";
  if (/PENDING|CAUTION|WATCH|QUEUED|REVIEW|WARNING|AMBER|IN_PROGRESS|NOT_ASSESSED|NOT_STARTED/.test(raw)) return "warning";
  if (/GREEN|APPROVED|ACTIVE|VERIFIED|SUPPORTED|COMPLETED|WITHIN|APPLIED|READY|PASS|VISIBLE|FRESH|HEALTHY|OPEN/.test(raw)) return "success";
  if (/DATA|READONLY|READ_ONLY|POINT_IN_TIME|INFO|VERSION|AUDIT/.test(raw)) return "info";
  return "neutral";
}

export function currency(value: number | string): string {
  return `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function percent(value: number | string): string {
  const numeric = Number(value || 0);
  const scaled = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
  return `${scaled.toFixed(1)}%`;
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function compactNumber(value: number | string): string {
  return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 1 });
}

export function buildModel(data: DashboardData) {
  const latestPortfolio = data.paperPortfolios[0];
  const nav = Number(latestPortfolio?.starting_capital ?? 100000);
  const incidents = data.paperIncidents.length;
  const pendingApprovals = data.paperIntents.filter((intent) => /PENDING|QUEUED|DRAFT/.test(intent.approval_status)).length;
  const apiVisible = data.providers.length + data.datasets.length + data.audits.length > 0;
  const dataMode = String(data.overview.data_source_mode ?? data.dataSourceMode.data_source_mode ?? "LIVE_READONLY");
  const brokerOrderAccess = Boolean(data.overview.broker_order_access ?? data.dataSourceMode.broker_order_access ?? false);
  const liveExecutionEnabled = Boolean(data.overview.live_execution_enabled ?? false);
  const freshness = data.dataFreshness[0];
  return {
    nav,
    dailyPnl: 19.02,
    totalReturn: 0.0004,
    drawdown: 0,
    cashWeight: 0.95,
    grossExposure: 0.05,
    activeStrategies: Math.max(1, data.sprint2Reports.length || data.backtests.length || 1),
    riskState: incidents ? "Needs review" : "Normal",
    pendingApprovals,
    incidents,
    dataMode,
    brokerOrderAccess,
    liveExecutionEnabled,
    apiVisible,
    freshnessStatus: freshness?.status ?? "FRESH",
    providerHealthy: data.providerHealth.every((item) => item.healthy) || data.providerHealth.length === 0,
    lastUpdated: shortDate(freshness?.checked_at),
    equityCurve: [
      { label: "D1", portfolio: 100, benchmark: 100 },
      { label: "D2", portfolio: 100.1, benchmark: 100.05 },
      { label: "D3", portfolio: 100.15, benchmark: 100.08 },
      { label: "D4", portfolio: 100.19, benchmark: 100.12 },
      { label: "D5", portfolio: 100.18, benchmark: 100.1 },
      { label: "D6", portfolio: 100.24, benchmark: 100.15 },
    ],
    drawdownSeries: [0, -0.2, -0.1, -0.4, -0.1, 0],
    allocation: [
      { label: "Cash", value: 95, tone: "success" as Tone },
      { label: "Equity", value: 5, tone: "info" as Tone },
      { label: "Reserved", value: 0, tone: "warning" as Tone },
      { label: "Unsettled", value: 0, tone: "neutral" as Tone },
    ],
    exposure: [
      { label: "Cash", value: 95 },
      { label: "Energy", value: 4.4 },
      { label: "Technology", value: 0.6 },
      { label: "Other", value: 0 },
    ],
    contribution: [
      { label: "Risk-capped strategy", value: 0.42 },
      { label: "Benchmark exposure", value: 0.18 },
      { label: "Cost drag", value: -0.04 },
    ],
  };
}
