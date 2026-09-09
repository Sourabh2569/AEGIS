"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet, authPost, clearToken } from "../api-client";
import RequireAuth from "../require-auth";

type Portfolio = {
  paper_portfolio_id: string;
  name: string;
  status: string;
  starting_capital: string;
};

type NavSnapshot = {
  nav: string;
  drawdown: string;
  high_water_mark: string;
  valuation_time: string;
};

type Incident = { severity: string; description: string; status: string };

type Summary = {
  portfolio: Portfolio;
  latest_nav: NavSnapshot | null;
  open_incidents: Incident[];
};

type Instrument = { aegis_instrument_id: string; current_symbol: string };

type StrategyConfig = {
  paper_strategy_config_id: string;
  paper_portfolio_id: string;
  strategy_id: string;
};

type Intent = {
  paper_trade_intent_id: string;
  paper_portfolio_id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  proposed_quantity: string;
  approved_quantity_nullable: string | null;
  intent_status: string;
  reason_codes_json: string[];
  eligible_execution_time: string;
  created_at: string;
  strategy_version_id: string;
};

function strategyIdFrom(strategyVersionId: string): string {
  return strategyVersionId.split(":")[0];
}

type ActionStatus = { kind: "ok" | "error"; text: string };

const PAST_TENSE: Record<string, string> = { pause: "paused", resume: "resumed", freeze: "frozen" };

function money(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function pct(value: string): string {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function HealthPanel() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selected, setSelected] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [strategyConfigs, setStrategyConfigs] = useState<StrategyConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionStatus, setActionStatus] = useState<ActionStatus | null>(null);

  const loadPortfolios = useCallback(() => {
    apiGet<Portfolio[]>("/api/v1/paper-portfolios", []).then((data) => {
      setPortfolios(data);
      setSelected((current) => current || data[0]?.paper_portfolio_id || "");
    });
  }, []);

  useEffect(() => {
    loadPortfolios();
    apiGet<StrategyConfig[]>("/api/v1/paper-strategy-configurations", []).then(setStrategyConfigs);
  }, [loadPortfolios]);

  const loadSummary = useCallback((portfolioId: string) => {
    if (!portfolioId) return;
    setLoading(true);
    apiGet<Summary | null>(`/api/v1/paper-portfolios/${portfolioId}/summary`, null).then(
      (data) => {
        setSummary(data);
        setLoading(false);
      },
    );
  }, []);

  useEffect(() => {
    loadSummary(selected);
  }, [selected, loadSummary]);

  async function runAction(action: "pause" | "resume" | "freeze") {
    setBusy(true);
    setActionStatus(null);
    try {
      await authPost(`/api/v1/paper-portfolios/${selected}/${action}`);
      setActionStatus({ kind: "ok", text: `Portfolio ${PAST_TENSE[action]}.` });
      loadSummary(selected);
      loadPortfolios();
    } catch (err) {
      setActionStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const currentStatus = portfolios.find((p) => p.paper_portfolio_id === selected)?.status;
  const strategiesForSelected = strategyConfigs.filter(
    (config) => config.paper_portfolio_id === selected,
  );

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Portfolio health</h2>
      </div>
      <div className="panel-body">
        <div className="picker-row" style={{ marginBottom: 16 }}>
          <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            {portfolios.map((portfolio) => (
              <option key={portfolio.paper_portfolio_id} value={portfolio.paper_portfolio_id}>
                {portfolio.name} ({portfolio.status})
              </option>
            ))}
          </select>
          <button disabled={busy || currentStatus !== "ACTIVE"} onClick={() => runAction("pause")}>
            Pause
          </button>
          <button disabled={busy || currentStatus !== "PAUSED"} onClick={() => runAction("resume")}>
            Resume
          </button>
          <button disabled={busy} onClick={() => runAction("freeze")}>
            Freeze
          </button>
          {actionStatus && <span className={`action-status ${actionStatus.kind}`}>{actionStatus.text}</span>}
        </div>

        {loading && <p className="hint">Loading real portfolio state…</p>}

        {!loading && summary && (
          <>
            <div className="stat">
              <span className="stat-label">Latest NAV</span>
              <span className="stat-value">
                {summary.latest_nav ? money(summary.latest_nav.nav) : "has not run a session yet"}
              </span>
            </div>
            <ul className="reasoning">
              <li>
                <span className="k">Status</span>
                <span className="v">{summary.portfolio.status}</span>
              </li>
              <li>
                <span className="k">Strategy</span>
                <span className="v">
                  {strategiesForSelected.length === 0
                    ? "Not configured yet"
                    : strategiesForSelected.map((config, index) => (
                        <span key={config.paper_strategy_config_id}>
                          {index > 0 && ", "}
                          <Link href={`/strategies/${config.strategy_id}`}>
                            {config.strategy_id}
                          </Link>
                        </span>
                      ))}
                </span>
              </li>
              <li>
                <span className="k">Starting capital</span>
                <span className="v">{money(summary.portfolio.starting_capital)}</span>
              </li>
              <li>
                <span className="k">Drawdown from high-water-mark</span>
                <span className={`v ${summary.latest_nav ? "neg" : ""}`}>
                  {summary.latest_nav ? pct(summary.latest_nav.drawdown) : "not available"}
                </span>
              </li>
            </ul>
            <p className="hint" style={{ marginTop: 12 }}>
              {summary.open_incidents.length === 0
                ? "No open incidents."
                : `${summary.open_incidents.length} open incident(s): ${summary.open_incidents
                    .map((incident) => `${incident.severity} — ${incident.description}`)
                    .join("; ")}`}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function ApprovalsQueue() {
  const [intents, setIntents] = useState<Intent[] | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<ActionStatus | null>(null);

  const load = useCallback(() => {
    apiGet<Intent[]>("/api/v1/paper-trade-intents", []).then(setIntents);
  }, []);

  useEffect(() => {
    load();
    apiGet<Portfolio[]>("/api/v1/paper-portfolios", []).then(setPortfolios);
    apiGet<Instrument[]>("/api/v1/instruments", []).then(setInstruments);
  }, [load]);

  const portfolioName = (id: string) =>
    portfolios.find((p) => p.paper_portfolio_id === id)?.name ?? id;
  const symbolFor = (id: string) =>
    instruments.find((i) => i.aegis_instrument_id === id)?.current_symbol ?? id;

  const pending = (intents ?? [])
    .filter((intent) => intent.intent_status === "PENDING_APPROVAL")
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

  async function approve(id: string) {
    setBusyId(id);
    setActionStatus(null);
    try {
      await authPost(`/api/v1/paper-trade-intents/${id}/approve`);
      setActionStatus({ kind: "ok", text: "Intent approved." });
      load();
    } catch (err) {
      setActionStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusyId(null);
    }
  }

  async function reject(id: string) {
    if (!rejectReason.trim()) return;
    setBusyId(id);
    setActionStatus(null);
    try {
      await authPost(`/api/v1/paper-trade-intents/${id}/reject`, { reason: rejectReason.trim() });
      setActionStatus({ kind: "ok", text: "Intent rejected." });
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setActionStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head">
        <h2>Pending approvals ({pending.length})</h2>
        {actionStatus && <span className={`action-status ${actionStatus.kind}`}>{actionStatus.text}</span>}
      </div>
      <div className="panel-body">
        {intents === null && <p className="hint">Loading real pending intents…</p>}
        {intents !== null && pending.length === 0 && (
          <p className="hint">No paper-trade intents are waiting on a decision right now.</p>
        )}
        {pending.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Portfolio</th>
                  <th>Strategy</th>
                  <th>Proposed</th>
                  <th>Approved</th>
                  <th>Reason codes</th>
                  <th>Eligible from</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((intent) => {
                  const id = intent.paper_trade_intent_id;
                  return (
                    <tr key={id}>
                      <td>
                        <Link href={`/instruments/${symbolFor(intent.instrument_id)}`}>
                          {symbolFor(intent.instrument_id)}
                        </Link>
                      </td>
                      <td>
                        <span className={`side-badge ${intent.side}`}>{intent.side}</span>
                      </td>
                      <td>{portfolioName(intent.paper_portfolio_id)}</td>
                      <td>
                        <Link href={`/strategies/${strategyIdFrom(intent.strategy_version_id)}`}>
                          {strategyIdFrom(intent.strategy_version_id)}
                        </Link>
                      </td>
                      <td>{intent.proposed_quantity}</td>
                      <td>{intent.approved_quantity_nullable ?? "—"}</td>
                      <td>{intent.reason_codes_json.join(", ") || "None"}</td>
                      <td>{new Date(intent.eligible_execution_time).toLocaleDateString()}</td>
                      <td>
                        {rejectingId === id ? (
                          <div className="reject-form">
                            <input
                              placeholder="Reason…"
                              value={rejectReason}
                              onChange={(event) => setRejectReason(event.target.value)}
                            />
                            <button
                              disabled={busyId === id || !rejectReason.trim()}
                              onClick={() => reject(id)}
                            >
                              Confirm
                            </button>
                            <button
                              disabled={busyId === id}
                              onClick={() => {
                                setRejectingId(null);
                                setRejectReason("");
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="reject-form">
                            <button disabled={busyId === id} onClick={() => approve(id)}>
                              Approve
                            </button>
                            <button
                              disabled={busyId === id}
                              onClick={() => {
                                setRejectingId(id);
                                setRejectReason("");
                              }}
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  const router = useRouter();
  return (
    <RequireAuth>
      <div className="shell">
        <header className="topbar">
          <div className="brand">
            <span className="mark" />
            AEGIS Cockpit
            <span className="sub">Decision support</span>
          </div>
          <div className="topbar-actions">
            <Link href="/">Instruments</Link>
            <Link href="/strategies">Strategies</Link>
            <Link href="/actionables">Actionables</Link>
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
              <h1 className="leaderboard-title">Portfolio &amp; Approvals</h1>
              <p className="hint">
                Real paper-portfolio state and pending intents — approving or rejecting here
                calls the exact same endpoints the dashboard uses.
              </p>
            </div>
          </div>
          <HealthPanel />
          <ApprovalsQueue />
        </main>
      </div>
    </RequireAuth>
  );
}
