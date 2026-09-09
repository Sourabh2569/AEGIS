"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { LineChart, ListChecks, Users } from "lucide-react";
import { apiGet } from "../../api-client";
import CockpitShell from "../../cockpit-shell";
import EquityChart, { type EquityPoint } from "./equity-chart";
import Gauge from "./gauge";

type Backtest = {
  scenario: string;
  dataset_origin: string;
  start_date: string;
  end_date: string;
  total_return: string;
  max_drawdown: string;
  rebalance_count: number;
  position_count: number;
  universe_size: number;
  bar_count: number;
  raw_snapshot_hash: string;
  warnings: string[];
  equity_curve: EquityPoint[];
};

type Rules = {
  eligibility: string;
  selection: string;
  sizing: string;
  stop: string;
  max_positions: number;
};

type LivePortfolio = {
  paper_portfolio_id: string;
  name: string;
  status: string;
  starting_capital: string;
  session_count: number;
  latest_nav: string | null;
  latest_drawdown: string | null;
  run_status: "HAS_RUN" | "HAS_NOT_RUN_YET";
};

type StrategyDetail = {
  strategy_id: string;
  return_to_drawdown_ratio: string | null;
  backtest: Backtest | null;
  backtest_status: "AVAILABLE" | "NOT_RUN_YET";
  benchmark_equity_curve: EquityPoint[] | null;
  rules: Rules;
  live_portfolios: LivePortfolio[];
};

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function money(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function Detail({ strategyId }: { strategyId: string }) {
  const [detail, setDetail] = useState<StrategyDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiGet<StrategyDetail | null>(`/api/v1/strategies/${strategyId}/detail`, null).then((data) => {
      if (!cancelled) {
        setDetail(data);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  if (loading) {
    return <div className="loading">Loading real strategy detail for {strategyId}…</div>;
  }

  if (!detail) {
    return <div className="empty-state">Unknown strategy: {strategyId}</div>;
  }

  const { backtest, rules, live_portfolios: livePortfolios } = detail;

  return (
    <>
      <div className="page-head">
        <h1>{detail.strategy_id}</h1>
        <Link href="/strategies">&larr; Strategy Leaderboard</Link>
      </div>

      <div className="confidence-strip">
        <div className={`row ${backtest ? "real" : "unavailable"}`}>
          <span className="label">Backtest</span>
          <span className="value">
            {backtest
              ? `Real, ${backtest.dataset_origin} · ${backtest.universe_size} instruments, ${backtest.bar_count} bars · hash ${backtest.raw_snapshot_hash.slice(0, 10)}… · ${backtest.start_date} → ${backtest.end_date}`
              : "Not available — no backtest run yet for this strategy"}
          </span>
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-head">
            <h2>
              <LineChart size={15} />
              Equity curve{detail.benchmark_equity_curve ? " vs. Equal-Weight benchmark" : ""}
            </h2>
          </div>
          {backtest ? (
            <>
              <EquityChart
                equityCurve={backtest.equity_curve}
                benchmarkCurve={detail.benchmark_equity_curve}
              />
              {backtest.warnings.length > 0 && (
                <div className="leaderboard-footnote" style={{ margin: "0 16px 16px" }}>
                  {backtest.warnings.map((warning) => (
                    <p className="hint" key={warning}>
                      {warning}
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="hint" style={{ padding: 16 }}>
              No backtest run yet — run one from the Strategy Leaderboard.
            </p>
          )}
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <h2>
                <ListChecks size={15} />
                Real rules
              </h2>
            </div>
            <div className="panel-body">
              <ul className="reasoning">
                <li>
                  <span className="k">Eligibility</span>
                  <span className="v">{rules.eligibility}</span>
                </li>
                <li>
                  <span className="k">Selection</span>
                  <span className="v">{rules.selection}</span>
                </li>
                <li>
                  <span className="k">Sizing</span>
                  <span className="v">{rules.sizing}</span>
                </li>
                <li>
                  <span className="k">Stop</span>
                  <span className="v">{rules.stop}</span>
                </li>
              </ul>
            </div>
          </div>

          {backtest && (
            <div className="panel">
              <div className="panel-head">
                <h2>Backtest metrics</h2>
              </div>
              <div className="panel-body">
                <div className="stat-and-gauge">
                  <div className="stat">
                    <span className="stat-label">Total return</span>
                    <span
                      className={`stat-value ${Number(backtest.total_return) >= 0 ? "pos" : "neg"}`}
                    >
                      {pct(backtest.total_return)}
                    </span>
                  </div>
                  <Gauge
                    value={backtest.position_count}
                    max={rules.max_positions}
                    label="Positions used"
                  />
                </div>
                <ul className="reasoning">
                  <li>
                    <span className="k">Max drawdown</span>
                    <span className="v neg">{pct(backtest.max_drawdown)}</span>
                  </li>
                  <li>
                    <span className="k">Return / drawdown</span>
                    <span className="v">
                      {detail.return_to_drawdown_ratio
                        ? `${Number(detail.return_to_drawdown_ratio).toFixed(2)}x`
                        : "n/a"}
                    </span>
                  </li>
                  <li>
                    <span className="k">Rebalances</span>
                    <span className="v">{backtest.rebalance_count}</span>
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 18 }}>
        <div className="panel-head">
          <h2>
            <Users size={15} />
            Live paper portfolios ({livePortfolios.length})
          </h2>
        </div>
        <div className="panel-body">
          {livePortfolios.length === 0 ? (
            <p className="hint">No paper portfolios are configured with this strategy yet.</p>
          ) : (
            <ul className="reasoning">
              {livePortfolios.map((portfolio) => (
                <li key={portfolio.paper_portfolio_id}>
                  <span className="k">
                    {portfolio.name} <span className="hint">({portfolio.status})</span>
                  </span>
                  <span className="v">
                    {portfolio.run_status === "HAS_RUN"
                      ? `${money(portfolio.latest_nav as string)} NAV, ${pct(portfolio.latest_drawdown)} drawdown`
                      : "has not run a session yet"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

export default function StrategyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <CockpitShell>
      <Detail strategyId={id} />
    </CockpitShell>
  );
}
