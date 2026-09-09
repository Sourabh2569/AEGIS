"use client";

import Link from "next/link";
import { TrendingDown, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../api-client";
import CockpitShell from "../cockpit-shell";

type ActionableRow = {
  symbol: string;
  aegis_instrument_id: string;
  action: "BUY" | "SELL";
  close: string;
  momentum_60: string | null;
  sma_50: string | null;
  sma_200: string | null;
  invalidation_price?: string | null;
  held_quantity?: string;
};

type ActionablesResponse = {
  as_of: string;
  dataset_origin: string;
  raw_snapshot_hash: string;
  paper_portfolio_id: string | null;
  actionables: ActionableRow[];
  warnings: string[];
};

type PaperPortfolio = { paper_portfolio_id: string; name: string; status: string };

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function money(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function Feed() {
  const [portfolios, setPortfolios] = useState<PaperPortfolio[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState("");
  const [data, setData] = useState<ActionablesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<PaperPortfolio[]>("/api/v1/paper-portfolios", []).then(setPortfolios);
  }, []);

  const load = useCallback((portfolioId: string) => {
    setLoading(true);
    const query = portfolioId ? `?paper_portfolio_id=${encodeURIComponent(portfolioId)}` : "";
    apiGet<ActionablesResponse | null>(`/api/v1/actionables${query}`, null).then((result) => {
      setData(result);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    load(selectedPortfolio);
  }, [selectedPortfolio, load]);

  const sells = data?.actionables.filter((row) => row.action === "SELL") ?? [];
  const buys = data?.actionables.filter((row) => row.action === "BUY") ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">Actionables Feed</h1>
          <p className="hint">
            What{" "}
            <Link href="/strategies/TrendFollowingBaselineStrategyV0">
              TrendFollowingBaselineStrategyV0
            </Link>{" "}
            says to do right now, across the full instrument universe.
          </p>
        </div>
        <div>
          <select
            value={selectedPortfolio}
            onChange={(event) => setSelectedPortfolio(event.target.value)}
          >
            <option value="">No portfolio selected (BUY only)</option>
            {portfolios.map((portfolio) => (
              <option key={portfolio.paper_portfolio_id} value={portfolio.paper_portfolio_id}>
                {portfolio.name} ({portfolio.status})
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="loading">Loading real signals across the universe…</div>}

      {!loading && data && (
        <>
          <div className="confidence-strip">
            <div className="row real">
              <span className="label">As of</span>
              <span className="value">
                Real, {data.dataset_origin} · {data.as_of} · hash{" "}
                {data.raw_snapshot_hash.slice(0, 10)}…
              </span>
            </div>
          </div>
          {data.warnings.map((warning) => (
            <p className="hint" key={warning}>
              {warning}
            </p>
          ))}

          <div className="panel" style={{ marginTop: 16, marginBottom: 16 }}>
            <div className="panel-head">
              <h2>
                <TrendingDown size={15} />
                Sell ({sells.length})
              </h2>
            </div>
            <div className="panel-body">
              {sells.length === 0 ? (
                <p className="hint">
                  No held positions have dropped out of eligibility right now.
                </p>
              ) : (
                <ul className="reasoning">
                  {sells.map((row) => (
                    <li key={row.aegis_instrument_id}>
                      <span className="k">
                        <Link href={`/instruments/${row.symbol}`}>{row.symbol}</Link>{" "}
                        <span className="hint">held {row.held_quantity}</span>
                      </span>
                      <span className="v">
                        {money(row.close)} ·{" "}
                        <span
                          className={
                            row.momentum_60 !== null
                              ? Number(row.momentum_60) >= 0
                                ? "v pos"
                                : "v neg"
                              : ""
                          }
                        >
                          {pct(row.momentum_60)} momentum
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>
                <TrendingUp size={15} />
                Buy ({buys.length})
              </h2>
            </div>
            <div className="panel-body">
              {buys.length === 0 ? (
                <p className="hint">
                  No instruments are currently eligible under the real strategy rules.
                </p>
              ) : (
                <ul className="reasoning">
                  {buys.map((row) => (
                    <li key={row.aegis_instrument_id}>
                      <span className="k">
                        <Link href={`/instruments/${row.symbol}`}>{row.symbol}</Link>
                      </span>
                      <span className="v">
                        {money(row.close)} ·{" "}
                        <span
                          className={
                            row.momentum_60 !== null
                              ? Number(row.momentum_60) >= 0
                                ? "v pos"
                                : "v neg"
                              : ""
                          }
                        >
                          {pct(row.momentum_60)} momentum
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default function ActionablesPage() {
  return (
    <CockpitShell>
      <Feed />
    </CockpitShell>
  );
}
