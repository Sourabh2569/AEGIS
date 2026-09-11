"use client";

import Link from "next/link";
import { Trophy, ListChecks, Award, Users, Wallet, BarChart3, Medal } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet, authPost } from "../api-client";
import BarChart from "../bar-chart";
import CockpitShell from "../cockpit-shell";
import { KpiCard, KpiStrip } from "../kpi-strip";
import { KpiStripSkeleton, PanelSkeleton } from "../skeleton";
import Sparkline from "./sparkline";

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
};

type Live = {
  portfolio_count: number;
  combined_starting_capital: string;
  combined_latest_nav: string;
  combined_return: string | null;
  worst_drawdown: string;
};

type LeaderboardRow = {
  strategy_id: string;
  return_to_drawdown_ratio: string | null;
  backtest: Backtest | null;
  backtest_status: "AVAILABLE" | "NOT_RUN_YET";
  equity_curve_sparkline: string[] | null;
  live: Live | null;
  live_status: "AVAILABLE" | "NO_LIVE_PORTFOLIOS_YET";
};

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function money(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function shortName(strategyId: string): string {
  return strategyId.replace(/(Baseline|Benchmark)?StrategyV0$/, "");
}

function isBenchmark(strategyId: string): boolean {
  return strategyId.includes("Benchmark");
}

const MEDAL_TONE = ["gold", "silver", "bronze"] as const;

function RankMedal({ rank }: { rank: number }) {
  if (rank >= MEDAL_TONE.length) return null;
  return <Medal size={15} className={`rank-medal ${MEDAL_TONE[rank]}`} />;
}

function Leaderboard() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  const [running, setRunning] = useState(false);
  const [runStatus, setRunStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const load = useCallback(() => {
    apiGet<LeaderboardRow[]>("/api/v1/strategies/leaderboard", []).then(setRows);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRunBacktest() {
    setRunning(true);
    setRunStatus(null);
    try {
      await authPost("/api/v1/research/momentum/run");
      setRunStatus({ kind: "ok", text: "Real backtest complete — results below are fresh." });
      load();
    } catch (err) {
      setRunStatus({
        kind: "error",
        text: err instanceof Error ? err.message : "Request failed",
      });
    } finally {
      setRunning(false);
    }
  }

  const anyMissingBacktest = rows?.some((row) => row.backtest_status === "NOT_RUN_YET") ?? false;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">
            <Trophy size={20} /> Strategy Leaderboard
          </h1>
          <p className="hint">
            Ranked by real backtested return ÷ |max drawdown| — a plain ratio of two real
            numbers, not a Sharpe ratio.
          </p>
        </div>
        <div className="leaderboard-run">
          <button className="primary" disabled={running} onClick={handleRunBacktest}>
            {running
              ? "Running real backtest…"
              : anyMissingBacktest
                ? "Run backtest (all 3 strategies)"
                : "Re-run backtest"}
          </button>
          {runStatus && <p className={`action-status ${runStatus.kind}`}>{runStatus.text}</p>}
        </div>
      </div>

      {rows === null && (
        <>
          <KpiStripSkeleton count={4} />
          <div className="leaderboard-list">
            <PanelSkeleton lines={3} />
            <PanelSkeleton lines={3} />
            <PanelSkeleton lines={3} />
          </div>
        </>
      )}

      {rows !== null && (
        <>
          {(() => {
            const withBacktest = rows.filter((row) => row.backtest !== null);
            const leader = rows[0]?.return_to_drawdown_ratio !== null ? rows[0] : null;
            const totalLivePortfolios = rows.reduce(
              (sum, row) => sum + (row.live?.portfolio_count ?? 0),
              0,
            );
            const totalLiveAum = rows.reduce(
              (sum, row) => sum + Number(row.live?.combined_latest_nav ?? 0),
              0,
            );
            return (
              <>
                <KpiStrip>
                  <KpiCard
                    icon={ListChecks}
                    label="Strategies backtested"
                    value={`${withBacktest.length} / ${rows.length}`}
                    caption="real momentum backtests run"
                  />
                  <KpiCard
                    icon={Award}
                    label="Best ratio"
                    value={
                      leader ? `${Number(leader.return_to_drawdown_ratio).toFixed(2)}x` : "n/a"
                    }
                    caption={leader ? shortName(leader.strategy_id) : "no backtest yet"}
                  />
                  <KpiCard
                    icon={Users}
                    label="Live portfolios"
                    value={String(totalLivePortfolios)}
                    caption="running any of these strategies"
                  />
                  <KpiCard
                    icon={Wallet}
                    label="Live AUM"
                    value={money(String(totalLiveAum))}
                    caption="combined latest NAV"
                  />
                </KpiStrip>

                {withBacktest.length > 0 && (
                  <div className="panel" style={{ marginBottom: 18 }}>
                    <div className="panel-head">
                      <h2>
                        <BarChart3 size={15} />
                        Total return by strategy
                      </h2>
                    </div>
                    <div className="panel-body">
                      <BarChart
                        data={withBacktest.map((row) => ({
                          label: `${shortName(row.strategy_id)} (${isBenchmark(row.strategy_id) ? "benchmark" : "strategy"})`,
                          value: Number(row.backtest!.total_return) * 100,
                        }))}
                        formatValue={(v) => `${v.toFixed(1)}%`}
                      />
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </>
      )}

      {rows !== null && (
        <div className="leaderboard-list">
          {rows.map((row, index) => (
            <div
              key={row.strategy_id}
              className={`panel leaderboard-card ${index === 0 && row.return_to_drawdown_ratio !== null ? "leader" : ""}`}
            >
              <div className="panel-head">
                <span className="leaderboard-rank">
                  #{index + 1}
                  {row.backtest_status === "AVAILABLE" && <RankMedal rank={index} />}
                </span>
                <Link href={`/strategies/${row.strategy_id}`} className="leaderboard-name">
                  {row.strategy_id}
                </Link>
                <span
                  className={`strategy-kind-tag ${isBenchmark(row.strategy_id) ? "benchmark" : "strategy"}`}
                >
                  {isBenchmark(row.strategy_id) ? "Benchmark" : "Strategy"}
                </span>
                {row.equity_curve_sparkline && (
                  <Sparkline
                    values={row.equity_curve_sparkline}
                    tone={
                      row.return_to_drawdown_ratio !== null &&
                      Number(row.return_to_drawdown_ratio) >= 0
                        ? "pos"
                        : "neg"
                    }
                  />
                )}
                <span
                  className={`leaderboard-ratio ${
                    row.return_to_drawdown_ratio === null
                      ? "na"
                      : Number(row.return_to_drawdown_ratio) >= 0
                        ? "pos"
                        : "neg"
                  }`}
                >
                  {row.return_to_drawdown_ratio === null
                    ? "ratio n/a"
                    : `${Number(row.return_to_drawdown_ratio).toFixed(2)}x return/drawdown`}
                </span>
              </div>
                <div className="panel-body">
                  <div className="leaderboard-columns">
                    <div>
                      <h3>Real backtest</h3>
                      {row.backtest ? (
                        <ul className="reasoning">
                          <li>
                            <span className="k">Total return</span>
                            <span
                              className={`v ${Number(row.backtest.total_return) >= 0 ? "pos" : "neg"}`}
                            >
                              {pct(row.backtest.total_return)}
                            </span>
                          </li>
                          <li>
                            <span className="k">Max drawdown</span>
                            <span className="v neg">{pct(row.backtest.max_drawdown)}</span>
                          </li>
                          <li>
                            <span className="k">Rebalances</span>
                            <span className="v">{row.backtest.rebalance_count}</span>
                          </li>
                          <li>
                            <span className="k">Universe</span>
                            <span className="v">
                              {row.backtest.universe_size} instruments, {row.backtest.bar_count}{" "}
                              bars
                            </span>
                          </li>
                          <li>
                            <span className="k">Period</span>
                            <span className="v">
                              {row.backtest.start_date} → {row.backtest.end_date}
                            </span>
                          </li>
                        </ul>
                      ) : (
                        <p className="hint">No backtest run yet for this strategy.</p>
                      )}
                    </div>
                    <div>
                      <h3>Live paper trading</h3>
                      {row.live ? (
                        <ul className="reasoning">
                          <li>
                            <span className="k">Portfolios</span>
                            <span className="v">{row.live.portfolio_count} (all statuses)</span>
                          </li>
                          <li>
                            <span className="k">Combined return</span>
                            <span
                              className={
                                row.live.combined_return !== null
                                  ? `v ${Number(row.live.combined_return) >= 0 ? "pos" : "neg"}`
                                  : "v"
                              }
                            >
                              {pct(row.live.combined_return)}
                            </span>
                          </li>
                          <li>
                            <span className="k">Combined NAV / start</span>
                            <span className="v">
                              {money(row.live.combined_latest_nav)} /{" "}
                              {money(row.live.combined_starting_capital)}
                            </span>
                          </li>
                          <li>
                            <span className="k">Worst drawdown</span>
                            <span className="v neg">{pct(row.live.worst_drawdown)}</span>
                          </li>
                        </ul>
                      ) : (
                        <p className="hint">
                          No live paper portfolios have run a session with this strategy yet.
                        </p>
                      )}
                    </div>
                  </div>
                  {row.backtest && row.backtest.warnings.length > 0 && (
                    <div className="leaderboard-footnote">
                      {row.backtest.warnings.map((warning) => (
                        <p className="hint" key={warning}>
                          {warning}
                        </p>
                      ))}
                      <p className="hint">
                        Dataset: {row.backtest.dataset_origin}, hash{" "}
                        {row.backtest.raw_snapshot_hash.slice(0, 10)}…
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
    </>
  );
}

export default function Page() {
  return (
    <CockpitShell>
      <Leaderboard />
    </CockpitShell>
  );
}
