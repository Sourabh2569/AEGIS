"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, authPost, clearToken } from "../api-client";
import RequireAuth from "../require-auth";

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

function Leaderboard() {
  const router = useRouter();
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
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark" />
          AEGIS Cockpit
          <span className="sub">Decision support</span>
        </div>
        <div className="topbar-actions">
          <Link href="/">Instruments</Link>
          <Link href="/actionables">Actionables</Link>
          <Link href="/portfolio">Portfolio</Link>
          <button
            onClick={() => {
              clearToken();
              router.replace("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <div className="page-head">
          <div>
            <h1 className="leaderboard-title">Strategy Leaderboard</h1>
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

        {rows === null && <div className="loading">Loading real strategy results…</div>}

        {rows !== null && (
          <div className="leaderboard-list">
            {rows.map((row, index) => (
              <div key={row.strategy_id} className="panel leaderboard-card">
                <div className="panel-head">
                  <span className="leaderboard-rank">#{index + 1}</span>
                  <Link href={`/strategies/${row.strategy_id}`} className="leaderboard-name">
                    {row.strategy_id}
                  </Link>
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
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <RequireAuth>
      <Leaderboard />
    </RequireAuth>
  );
}
