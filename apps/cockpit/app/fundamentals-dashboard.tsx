"use client";

import { Activity, FileText, IndianRupee, Percent, Scale, Wallet } from "lucide-react";
import { KpiCard, KpiStrip } from "./kpi-strip";
import { money } from "./money";

export type ConsolidatedFundamentals =
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

export type FundamentalsResponse =
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

/** The fields Standalone and Consolidated fundamentals share -- both API
 * shapes carry every one of these when available:true, so a row/KPI
 * definition can read from either without knowing which nature it got. */
export type FundamentalsFields = {
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

/** Shared by the main Instrument Decision View and the Sector Screener's
 * per-company page -- same real KPI strip + Standalone/Consolidated
 * comparison table, built once so both stay in sync instead of drifting
 * copies. Renders nothing if neither nature is available (an honest
 * empty state -- the caller decides what to show instead, if anything). */
export function FundamentalsDashboard({
  fundamentals,
  close,
}: {
  fundamentals: FundamentalsResponse | null | undefined;
  close?: string;
}) {
  const standalone: FundamentalsFields | null = fundamentals?.available ? fundamentals : null;
  const consolidated: FundamentalsFields | null = fundamentals?.consolidated.available
    ? fundamentals.consolidated
    : null;
  const primary = consolidated ?? standalone;
  const primaryLabel = consolidated ? "Consolidated" : standalone ? "Standalone" : null;
  if (!primary) return null;
  const pe = peRatio(close, primary.ttm_eps);
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
                          {row.get(c.data, close)}
                        </td>
                      ))}
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <p className="hint" style={{ marginTop: 10, marginBottom: 0 }}>
            {columns.map((c) => `${c.label} filed ${c.data.filing_date}`).join(" · ")} · real
            quarterly results, not a balance sheet
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
              TTM EPS sums basic EPS from 4 real, contiguous quarters; P/E divides that by the
              close price above, not a same-day quote.{" "}
              {!consolidated &&
                "Standalone-only earnings read higher than a commonly-quoted market P/E for a company with large subsidiaries (e.g. Jio, Retail) outside the standalone entity — upload a Consolidated filing for the comparable figure."}
              {consolidated && "Consolidated is the figure comparable to a commonly-quoted market P/E."}
            </p>
          )}
          {primary.debt_equity_ratio && (
            <p className="hint" style={{ marginBottom: 0, marginTop: 4 }}>
              Debt/Equity is the company&apos;s own self-reported figure, not derived by AEGIS —
              a value this low likely reflects a net-debt basis (borrowings net of cash and
              investments) rather than the gross debt commonly used in externally-reported
              figures.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
