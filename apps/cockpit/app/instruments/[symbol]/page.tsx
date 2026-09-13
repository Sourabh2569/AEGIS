"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  IndianRupee,
  Activity,
  ShieldAlert,
  BarChart3,
  FileText,
  Percent,
  Wallet,
  Scale,
} from "lucide-react";
import { apiGet, authPost } from "../../api-client";
import CockpitShell from "../../cockpit-shell";
import { KpiCard, KpiStrip } from "../../kpi-strip";
import { money } from "../../money";
import { KpiStripSkeleton, Skeleton } from "../../skeleton";
import PriceChart, { type Bar, type IndicatorPoint, type RuleEvent } from "./price-chart";
import MomentumChart from "./momentum-chart";

type OhlcvResponse = {
  symbol: string;
  aegis_instrument_id: string;
  dataset_origin: string;
  raw_snapshot_hash: string;
  bars: Bar[];
};

type IndicatorApiPoint = {
  date: string;
  close: string | null;
  sma_50: string | null;
  sma_200: string | null;
  momentum_60: string | null;
  atr_14: string | null;
};

type IndicatorsResponse = {
  points: IndicatorApiPoint[];
};

type RuleEventsResponse = { events: RuleEvent[] };

type SignalInputs = {
  close: string;
  sma_50: string | null;
  sma_200: string | null;
  momentum_60: string | null;
  atr_14: string | null;
  average_daily_value_traded_20: string | null;
  invalidation_price: string | null;
};

type SignalResponse = {
  symbol: string;
  as_of: string;
  dataset_origin: string;
  raw_snapshot_hash: string;
  signal: "BUY" | "SELL" | "HOLD" | "NO_POSITION";
  eligible: boolean;
  held: boolean;
  held_quantity: string | null;
  inputs: SignalInputs | null;
  rule_thresholds: { eligibility: string; minimum_avg_daily_value_traded_20: string; stop: string };
  warnings: string[];
};

type PaperPortfolio = { paper_portfolio_id: string; name: string; status: string };

type ConsolidatedFundamentals =
  | { available: false; real_quarters_on_file: number; ttm_eps: null; ttm_eps_quarters: [] }
  | {
      available: true;
      dataset_origin: string;
      period_from: string;
      period_to: string;
      filing_date: string;
      revenue_from_operations: string | null;
      other_income: string | null;
      total_income: string | null;
      total_expenses: string | null;
      employee_benefit_expense: string | null;
      finance_costs: string | null;
      depreciation_and_amortisation: string | null;
      profit_before_tax: string | null;
      tax_expense: string | null;
      profit_for_period: string | null;
      basic_eps: string | null;
      diluted_eps: string | null;
      paid_up_equity_share_capital: string | null;
      face_value_per_share: string | null;
      debt_equity_ratio: string | null;
      source_xbrl_url: string | null;
      ttm_eps: string | null;
      ttm_eps_quarters: string[];
      real_quarters_on_file: number;
    };

type FundamentalsResponse =
  | { available: false; reason: string; consolidated: ConsolidatedFundamentals }
  | {
      available: true;
      dataset_origin: string;
      period_from: string;
      period_to: string;
      filing_date: string;
      revenue_from_operations: string | null;
      other_income: string | null;
      total_income: string | null;
      total_expenses: string | null;
      employee_benefit_expense: string | null;
      finance_costs: string | null;
      depreciation_and_amortisation: string | null;
      profit_before_tax: string | null;
      tax_expense: string | null;
      profit_for_period: string | null;
      basic_eps: string | null;
      diluted_eps: string | null;
      paid_up_equity_share_capital: string | null;
      face_value_per_share: string | null;
      debt_equity_ratio: string | null;
      source_xbrl_url: string | null;
      ttm_eps: string | null;
      ttm_eps_quarters: string[];
      real_quarters_on_file: number;
      consolidated: ConsolidatedFundamentals;
    };

function toNumber(value: string | null): number | null {
  return value === null ? null : Number(value);
}

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

/** The fields Standalone and Consolidated fundamentals share -- both API
 * shapes carry every one of these when available:true, so a row/KPI
 * definition can read from either without knowing which nature it got. */
type FundamentalsFields = {
  period_from: string;
  period_to: string;
  filing_date: string;
  revenue_from_operations: string | null;
  other_income: string | null;
  total_income: string | null;
  total_expenses: string | null;
  employee_benefit_expense: string | null;
  finance_costs: string | null;
  depreciation_and_amortisation: string | null;
  profit_before_tax: string | null;
  tax_expense: string | null;
  profit_for_period: string | null;
  basic_eps: string | null;
  diluted_eps: string | null;
  paid_up_equity_share_capital: string | null;
  face_value_per_share: string | null;
  debt_equity_ratio: string | null;
  source_xbrl_url: string | null;
  ttm_eps: string | null;
  ttm_eps_quarters: string[];
  real_quarters_on_file: number;
};

function netMargin(profit: string | null, revenue: string | null): string {
  if (!profit || !revenue) return "not available";
  return `${((Number(profit) / Number(revenue)) * 100).toFixed(1)}%`;
}

function impliedShares(paidUp: string | null, faceValue: string | null): string {
  if (!paidUp || !faceValue) return "not available";
  return Math.round(Number(paidUp) / Number(faceValue)).toLocaleString("en-IN");
}

function peRatio(close: string | undefined, ttmEps: string | null): string | null {
  if (!ttmEps || Number(ttmEps) <= 0 || !close) return null;
  return `${(Number(close) / Number(ttmEps)).toFixed(1)}x`;
}

const FUNDAMENTALS_TABLE_ROWS: Array<
  | { kind: "section"; label: string }
  | { kind: "metric"; label: string; get: (v: FundamentalsFields, close: string | undefined) => string }
> = [
  { kind: "section", label: "Income" },
  {
    kind: "metric",
    label: "Revenue from operations",
    get: (v) => (v.revenue_from_operations ? money(v.revenue_from_operations, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Other income",
    get: (v) => (v.other_income ? money(v.other_income, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Total income",
    get: (v) => (v.total_income ? money(v.total_income, { compact: true }) : "not available"),
  },
  { kind: "section", label: "Expenses" },
  {
    kind: "metric",
    label: "Total expenses",
    get: (v) => (v.total_expenses ? money(v.total_expenses, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Employee benefit expense",
    get: (v) =>
      v.employee_benefit_expense ? money(v.employee_benefit_expense, { compact: true }) : "not available",
  },
  {
    kind: "metric",
    label: "Finance costs",
    get: (v) => (v.finance_costs ? money(v.finance_costs, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Depreciation & amortisation",
    get: (v) =>
      v.depreciation_and_amortisation
        ? money(v.depreciation_and_amortisation, { compact: true })
        : "not available",
  },
  { kind: "section", label: "Profitability" },
  {
    kind: "metric",
    label: "Profit before tax",
    get: (v) => (v.profit_before_tax ? money(v.profit_before_tax, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Tax expense",
    get: (v) => (v.tax_expense ? money(v.tax_expense, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Profit for the period",
    get: (v) => (v.profit_for_period ? money(v.profit_for_period, { compact: true }) : "not available"),
  },
  {
    kind: "metric",
    label: "Net profit margin",
    get: (v) => netMargin(v.profit_for_period, v.revenue_from_operations),
  },
  { kind: "section", label: "Per share & leverage" },
  {
    kind: "metric",
    label: "EPS (basic / diluted)",
    get: (v) => `${v.basic_eps ?? "n/a"} / ${v.diluted_eps ?? "n/a"}`,
  },
  {
    kind: "metric",
    label: "EPS (TTM, basic)",
    get: (v) => v.ttm_eps ?? `not available — ${v.real_quarters_on_file} of 4 quarters on file`,
  },
  {
    kind: "metric",
    label: "P/E (TTM)",
    get: (v, close) => peRatio(close, v.ttm_eps) ?? "not available",
  },
  {
    kind: "metric",
    label: "Shares outstanding (implied)",
    get: (v) => impliedShares(v.paid_up_equity_share_capital, v.face_value_per_share),
  },
  {
    kind: "metric",
    label: "Debt / Equity ratio",
    get: (v) => v.debt_equity_ratio ?? "not available",
  },
];

function Decision({ symbol }: { symbol: string }) {
  const [bars, setBars] = useState<Bar[]>([]);
  const [indicators, setIndicators] = useState<IndicatorPoint[]>([]);
  const [ruleEvents, setRuleEvents] = useState<RuleEvent[]>([]);
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [portfolios, setPortfolios] = useState<PaperPortfolio[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState("");
  const [loading, setLoading] = useState(true);
  const [fundamentals, setFundamentals] = useState<FundamentalsResponse | null>(null);
  const [actionStatus, setActionStatus] = useState<{ kind: "ok" | "error" | "info"; text: string } | null>(
    null,
  );
  const [sending, setSending] = useState(false);

  const loadSignal = useCallback(
    async (portfolioId: string) => {
      const query = portfolioId ? `?paper_portfolio_id=${encodeURIComponent(portfolioId)}` : "";
      const data = await apiGet<SignalResponse | null>(
        `/api/v1/instruments/${symbol}/signal${query}`,
        null,
      );
      setSignal(data);
    },
    [symbol],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiGet<OhlcvResponse | null>(`/api/v1/instruments/${symbol}/ohlcv`, null),
      apiGet<IndicatorsResponse | null>(`/api/v1/instruments/${symbol}/indicators`, null),
      apiGet<RuleEventsResponse | null>(`/api/v1/instruments/${symbol}/rule-events`, null),
      apiGet<PaperPortfolio[]>("/api/v1/paper-portfolios", []),
      apiGet<FundamentalsResponse | null>(`/api/v1/instruments/${symbol}/fundamentals`, null),
    ]).then(([ohlcv, indicatorData, ruleEventData, portfolioList, fundamentalsData]) => {
      if (cancelled) return;
      setBars(ohlcv?.bars ?? []);
      setIndicators(
        (indicatorData?.points ?? []).map((point) => ({
          date: point.date,
          close: toNumber(point.close),
          sma_50: toNumber(point.sma_50),
          sma_200: toNumber(point.sma_200),
          momentum_60: toNumber(point.momentum_60),
          atr_14: toNumber(point.atr_14),
        })),
      );
      setRuleEvents(ruleEventData?.events ?? []);
      setPortfolios(portfolioList);
      if (portfolioList.length > 0) setSelectedPortfolio(portfolioList[0].paper_portfolio_id);
      setFundamentals(fundamentalsData);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  useEffect(() => {
    loadSignal(selectedPortfolio);
  }, [selectedPortfolio, loadSignal]);

  async function handleSendToPaperTrading() {
    if (!selectedPortfolio) {
      setActionStatus({ kind: "error", text: "Select a paper portfolio first." });
      return;
    }
    const lastRealDate = bars[bars.length - 1]?.date;
    if (!lastRealDate) {
      setActionStatus({ kind: "error", text: "No real trading date available yet." });
      return;
    }
    setSending(true);
    setActionStatus(null);
    try {
      const result = await authPost<{ decision_cycle_status: string }>(
        "/api/v1/paper-trading-sessions/run",
        { paper_portfolio_id: selectedPortfolio, session_date: lastRealDate },
      );
      setActionStatus({
        kind: "ok",
        text: `Decision cycle ${result.decision_cycle_status.toLowerCase()}. Any resulting intent lands PENDING_APPROVAL in the existing approval workflow.`,
      });
      await loadSignal(selectedPortfolio);
    } catch (err) {
      setActionStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <>
        <KpiStripSkeleton count={4} />
        <div className="panel">
          <div className="panel-body">
            <Skeleton height={360} radius={8} />
          </div>
        </div>
      </>
    );
  }

  if (bars.length === 0) {
    return (
      <div className="empty-state">
        No real historical data captured yet for {symbol}. Run a provider sync first.
      </div>
    );
  }

  const inputs = signal?.inputs;
  const canSend = signal?.signal === "BUY" || signal?.signal === "SELL";

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{symbol}</h1>
        </div>
        <Link href="/">&larr; All instruments</Link>
      </div>

      <div className="confidence-strip">
        <div className="row real">
          <span className="label">Price &amp; volume</span>
          <span className="value">
            Real, Kite Connect &middot; {bars.length} bars &middot; hash{" "}
            {signal?.raw_snapshot_hash.slice(0, 10) ?? "—"}… &middot; through {bars[bars.length - 1].date}
          </span>
        </div>
        <div
          className={`row ${
            fundamentals?.available || fundamentals?.consolidated.available ? "real" : "unavailable"
          }`}
        >
          <span className="label">Fundamentals</span>
          <span className="value">
            {fundamentals?.available || fundamentals?.consolidated.available
              ? `Real, NSE XBRL · ${
                  [
                    fundamentals?.consolidated.available && "Consolidated",
                    fundamentals?.available && "Standalone",
                  ]
                    .filter(Boolean)
                    .join(" + ")
                }`
              : (fundamentals?.reason ?? "Not available — no verified fundamentals provider yet")}
          </span>
        </div>
        <div className="row unavailable">
          <span className="label">News / sentiment</span>
          <span className="value">Not available — no provider connected</span>
        </div>
      </div>

      <KpiStrip>
        <KpiCard
          icon={IndianRupee}
          label="Close"
          value={inputs ? money(inputs.close) : "n/a"}
          caption={signal?.as_of ? `as of ${signal.as_of}` : undefined}
        />
        <KpiCard
          icon={Activity}
          label="60-day momentum"
          value={inputs ? pct(inputs.momentum_60) : "n/a"}
          delta={
            inputs?.momentum_60 != null
              ? {
                  text: pct(inputs.momentum_60),
                  tone: Number(inputs.momentum_60) >= 0 ? "pos" : "neg",
                }
              : null
          }
        />
        <KpiCard
          icon={ShieldAlert}
          label="ATR-based stop"
          value={inputs ? money(inputs.invalidation_price) : "n/a"}
          caption="close − 2 × ATR_14"
        />
        <KpiCard
          icon={BarChart3}
          label="20-day avg value traded"
          value={inputs ? money(inputs.average_daily_value_traded_20, { compact: true }) : "n/a"}
          caption="minimum ₹100,000 to be eligible"
        />
      </KpiStrip>

      {(() => {
        const standalone: FundamentalsFields | null = fundamentals?.available ? fundamentals : null;
        const consolidated: FundamentalsFields | null = fundamentals?.consolidated.available
          ? fundamentals.consolidated
          : null;
        const primary = consolidated ?? standalone;
        const primaryLabel = consolidated ? "Consolidated" : standalone ? "Standalone" : null;
        if (!primary) return null;
        const pe = peRatio(inputs?.close, primary.ttm_eps);
        const columns = [
          consolidated && { label: "Consolidated", data: consolidated },
          standalone && { label: "Standalone", data: standalone },
        ].filter((c): c is { label: string; data: FundamentalsFields } => Boolean(c));

        return (
          <>
            <KpiStrip>
              <KpiCard
                icon={Percent}
                label="P/E (TTM)"
                value={pe ?? "not available"}
                caption={
                  primary.ttm_eps
                    ? `${primaryLabel} · ${primary.ttm_eps_quarters.length} real quarters`
                    : `${primaryLabel} · ${primary.real_quarters_on_file} of 4 quarters on file`
                }
              />
              <KpiCard
                icon={Wallet}
                label="EPS (TTM, basic)"
                value={primary.ttm_eps ?? "not available"}
                caption={primaryLabel ?? undefined}
              />
              <KpiCard
                icon={Activity}
                label="Net profit margin"
                value={netMargin(primary.profit_for_period, primary.revenue_from_operations)}
                caption={`${primaryLabel} · ${primary.period_from} to ${primary.period_to}`}
              />
              <KpiCard
                icon={IndianRupee}
                label="Revenue (latest qtr)"
                value={
                  primary.revenue_from_operations
                    ? money(primary.revenue_from_operations, { compact: true })
                    : "not available"
                }
                caption={primaryLabel ?? undefined}
              />
              <KpiCard
                icon={Scale}
                label="Debt / Equity"
                value={primary.debt_equity_ratio ?? "not available"}
                caption="self-reported — see note below"
              />
            </KpiStrip>

            <div className="panel" style={{ marginBottom: 18 }}>
              <div className="panel-head">
                <h2>
                  <FileText size={15} />
                  Real fundamentals — {columns.map((c) => c.label).join(" vs. ")}
                </h2>
              </div>
              <div className="panel-body">
                <div className="table-wrap">
                  <table className="data-table fundamentals-compare">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        {columns.map((c) => (
                          <th key={c.label}>{c.label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {FUNDAMENTALS_TABLE_ROWS.map((row) =>
                        row.kind === "section" ? (
                          <tr className="table-section" key={row.label}>
                            <td colSpan={1 + columns.length}>{row.label}</td>
                          </tr>
                        ) : (
                          <tr key={row.label}>
                            <td>{row.label}</td>
                            {columns.map((c) => (
                              <td className="num" key={c.label}>
                                {row.get(c.data, inputs?.close)}
                              </td>
                            ))}
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="hint" style={{ marginTop: 10, marginBottom: 0 }}>
                  {columns
                    .map((c) => `${c.label} filed ${c.data.filing_date}`)
                    .join(" · ")}{" "}
                  · real quarterly results, not a balance sheet
                  {consolidated?.source_xbrl_url || standalone?.source_xbrl_url ? " — " : ""}
                  {(consolidated?.source_xbrl_url ?? standalone?.source_xbrl_url) && (
                    <a
                      href={(consolidated ?? standalone)?.source_xbrl_url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                    >
                      source XBRL filing
                    </a>
                  )}
                </p>
                {primary.ttm_eps && (
                  <p className="hint" style={{ marginBottom: 0, marginTop: 4 }}>
                    TTM EPS sums basic EPS from 4 real, contiguous quarters; P/E divides that by
                    the close price above, not a same-day quote.{" "}
                    {!consolidated &&
                      "Standalone-only earnings read higher than a commonly-quoted market P/E for a company with large subsidiaries (e.g. Jio, Retail) outside the standalone entity — upload a Consolidated filing for the comparable figure."}
                    {consolidated &&
                      "Consolidated is the figure comparable to a commonly-quoted market P/E."}
                  </p>
                )}
                {primary.debt_equity_ratio && (
                  <p className="hint" style={{ marginBottom: 0, marginTop: 4 }}>
                    Debt/Equity is the company&apos;s own self-reported figure, not derived by
                    AEGIS — a value this low likely reflects a net-debt basis (borrowings net of
                    cash and investments) rather than the gross debt commonly used in
                    externally-reported figures.
                  </p>
                )}
              </div>
            </div>
          </>
        );
      })()}

      <div className="grid">
        <div className="panel">
          <div className="panel-head">
            <h2>Price &middot; SMA 50/200 &middot; ATR band</h2>
          </div>
          <p className="hint chart-legend">
            <span className="chart-legend-buy">&#9650; eligibility started</span>
            <span className="chart-legend-sell">&#9660; eligibility ended</span>
            <span>SMA 50</span>
            <span>SMA 200</span>
            <span>dashed &plusmn;2 ATR</span>
          </p>
          <PriceChart bars={bars} indicators={indicators} ruleEvents={ruleEvents} />
          <MomentumChart indicators={indicators} />
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <h2>Signal, as of {signal?.as_of ?? "—"}</h2>
            </div>
            <div className="panel-body">
              {signal && (
                <span className={`signal-badge ${signal.signal}`}>
                  <span className="dot" />
                  {signal.signal.replace("_", " ")}
                </span>
              )}
              <ul className="reasoning">
                <li>
                  <span className="k">SMA 50 / SMA 200</span>
                  <span className="v">
                    {inputs ? `${money(inputs.sma_50)} / ${money(inputs.sma_200)}` : "not available"}
                  </span>
                </li>
                {signal?.held && (
                  <li>
                    <span className="k">Currently held</span>
                    <span className="v">{signal.held_quantity} shares</span>
                  </li>
                )}
              </ul>
              <p className="hint">
                Eligibility rule: {signal?.rule_thresholds.eligibility ?? "—"}, min avg value traded ₹
                {signal?.rule_thresholds.minimum_avg_daily_value_traded_20 ?? "—"}. Stop:{" "}
                {signal?.rule_thresholds.stop ?? "—"}.
              </p>
              {signal?.warnings.map((warning) => (
                <p className="hint" key={warning}>
                  {warning}
                </p>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>Send to paper trading</h2>
            </div>
            <div className="panel-body action-row">
              <select value={selectedPortfolio} onChange={(event) => setSelectedPortfolio(event.target.value)}>
                {portfolios.length === 0 && <option value="">No paper portfolios yet</option>}
                {portfolios.map((portfolio) => (
                  <option key={portfolio.paper_portfolio_id} value={portfolio.paper_portfolio_id}>
                    {portfolio.name} ({portfolio.status})
                  </option>
                ))}
              </select>
              <button
                className="primary"
                disabled={sending || !canSend || portfolios.length === 0}
                onClick={handleSendToPaperTrading}
              >
                {sending ? "Running decision cycle…" : "Propose via real strategy"}
              </button>
              {!canSend && (
                <p className="hint">
                  No actionable BUY or SELL signal for this instrument right now — nothing to propose.
                </p>
              )}
              {actionStatus && <p className={`action-status ${actionStatus.kind}`}>{actionStatus.text}</p>}
              <p className="hint">
                Calls the existing decision-cycle endpoint. Any resulting intent still requires human
                approval in the existing Paper Operations approval screen — this never bypasses it.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default function InstrumentPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  return (
    <CockpitShell>
      <Decision symbol={symbol.toUpperCase()} />
    </CockpitShell>
  );
}
