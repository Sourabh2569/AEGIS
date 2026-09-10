"use client";

import Link from "next/link";
import { ShieldCheck, FlaskConical, Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { apiGet } from "../api-client";
import CockpitShell from "../cockpit-shell";
import { PanelSkeleton } from "../skeleton";

type Gate1 = {
  real_backtests_run: number;
  dataset_origin: string | null;
  universe_size: number | null;
  detail: string;
};

type PortfolioEvidence = {
  paper_portfolio_id: string;
  name: string;
  status: string;
  days_active: number | null;
  real_session_count: number;
  worst_drawdown_observed: string | null;
  reconciliation_count: number;
  reconciliation_mismatch_count: number;
};

type Gate2 = {
  portfolio_count: number;
  total_real_sessions: number;
  longest_days_active: number;
  total_reconciliation_mismatches: number;
  portfolios: PortfolioEvidence[];
};

type Evidence = { as_of: string; gate_1_research_integrity: Gate1; gate_2_paper_trading_evidence: Gate2 };

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function Readiness() {
  const [evidence, setEvidence] = useState<Evidence | null>(null);

  useEffect(() => {
    apiGet<Evidence | null>("/api/v1/live-readiness/evidence", null).then(setEvidence);
  }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">
            <ShieldCheck size={20} /> Live Readiness
          </h1>
          <p className="hint">
            Real evidence toward Document 007&apos;s Gates 1 and 2 -- this platform stays
            paper-trading-only until every gate is passed and evidenced. Numbers here are
            honestly near-zero by design when the evidence clock has just restarted.
          </p>
        </div>
      </div>

      {evidence === null ? (
        <PanelSkeleton lines={5} />
      ) : (
        <>
          <div className="panel" style={{ marginBottom: 18 }}>
            <div className="panel-head">
              <h2>
                <FlaskConical size={15} />
                Gate 1 -- Research integrity
              </h2>
            </div>
            <div className="panel-body">
              <ul className="reasoning">
                <li>
                  <span className="k">Real strategy backtests on record</span>
                  <span className="v">{evidence.gate_1_research_integrity.real_backtests_run}</span>
                </li>
                <li>
                  <span className="k">Dataset origin</span>
                  <span className="v">
                    {evidence.gate_1_research_integrity.dataset_origin ?? "not available"}
                  </span>
                </li>
                <li>
                  <span className="k">Real universe size</span>
                  <span className="v">
                    {evidence.gate_1_research_integrity.universe_size ?? "not available"}
                  </span>
                </li>
              </ul>
              <p className="hint">{evidence.gate_1_research_integrity.detail}</p>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>
                <Layers size={15} />
                Gate 2 -- Paper-trading evidence
              </h2>
            </div>
            <div className="panel-body">
              <ul className="reasoning">
                <li>
                  <span className="k">Real paper portfolios</span>
                  <span className="v">{evidence.gate_2_paper_trading_evidence.portfolio_count}</span>
                </li>
                <li>
                  <span className="k">Total real sessions run</span>
                  <span className="v">
                    {evidence.gate_2_paper_trading_evidence.total_real_sessions}
                  </span>
                </li>
                <li>
                  <span className="k">Longest real track record</span>
                  <span className="v">
                    {evidence.gate_2_paper_trading_evidence.longest_days_active} days
                  </span>
                </li>
                <li>
                  <span className="k">Reconciliation mismatches</span>
                  <span
                    className={
                      evidence.gate_2_paper_trading_evidence.total_reconciliation_mismatches > 0
                        ? "v neg"
                        : "v"
                    }
                  >
                    {evidence.gate_2_paper_trading_evidence.total_reconciliation_mismatches}
                  </span>
                </li>
              </ul>

              {evidence.gate_2_paper_trading_evidence.portfolios.length === 0 ? (
                <p className="hint">
                  No real paper portfolios yet -- the evidence clock starts once one runs.
                </p>
              ) : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Portfolio</th>
                        <th>Status</th>
                        <th>Days active</th>
                        <th>Sessions</th>
                        <th>Worst drawdown</th>
                        <th>Mismatches</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evidence.gate_2_paper_trading_evidence.portfolios.map((row) => (
                        <tr key={row.paper_portfolio_id}>
                          <td>
                            <Link href={`/portfolio`}>{row.name}</Link>
                          </td>
                          <td>{row.status}</td>
                          <td>{row.days_active ?? "not activated"}</td>
                          <td>{row.real_session_count}</td>
                          <td>{pct(row.worst_drawdown_observed)}</td>
                          <td>
                            {row.reconciliation_mismatch_count} of {row.reconciliation_count}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default function LiveReadinessPage() {
  return (
    <CockpitShell>
      <Readiness />
    </CockpitShell>
  );
}
