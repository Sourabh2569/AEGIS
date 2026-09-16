"use client";

import { AlertTriangle, Radio, Wallet, ClipboardCheck, GraduationCap, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet, authPost, getRole } from "../api-client";
import CockpitShell from "../cockpit-shell";
import { money } from "../money";
import { PanelSkeleton } from "../skeleton";

type LivePortfolio = {
  live_portfolio_id: string;
  name: string;
  status: string;
  capital_tier: "PILOT" | "FULL";
  clean_fill_count: number;
  starting_capital: string;
  pilot_capital_cap: string;
};

type Summary = {
  portfolio: LivePortfolio;
  cash: string;
  unsettled_receivables: string;
  positions: Record<string, string>;
  open_incidents: { severity: string; description: string; status: string }[];
};

type PilotStatus = {
  capital_tier: string;
  clean_fill_count: number;
  graduation_threshold: number;
  threshold_met: boolean;
  pilot_capital_cap: string;
};

type Intent = {
  live_order_intent_id: string;
  live_portfolio_id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  proposed_quantity: string;
  approved_quantity_nullable: string | null;
  intent_status: string;
  reason_codes_json: string[];
  created_at: string;
};

type LiveOrder = {
  live_order_id: string;
  instrument_id: string;
  status: string;
  requested_quantity: string;
  broker_order_id_nullable: string | null;
  rejection_reason_nullable: string | null;
};

type ActionStatus = { kind: "ok" | "error"; text: string };

function useIsFounder(): boolean {
  const [founder, setFounder] = useState(false);
  useEffect(() => {
    setFounder(getRole() === "FOUNDER");
  }, []);
  return founder;
}

function FounderGate({ children }: { children: React.ReactNode }) {
  const isFounder = useIsFounder();
  if (!isFounder) {
    return <p className="founder-gate">Founder role required for this action.</p>;
  }
  return <>{children}</>;
}

function statusPillClass(status: string): string {
  if (status === "ACTIVE") return "status-active";
  if (status === "PAUSED") return "status-paused";
  if (status === "FROZEN" || status === "FAILED") return "status-frozen";
  return "status-neutral";
}

function LiveWarningBanner() {
  return (
    <div className="live-warning-banner">
      <AlertTriangle size={16} />
      <span>LIVE — REAL MONEY. Every action below can place a real broker order.</span>
      <span className="sub">
        Categorically blocked today: LIVE_EXECUTION_ENABLED / BROKER_ORDER_ACCESS remain hard-off.
      </span>
    </div>
  );
}

function PortfolioPicker({
  portfolios,
  selected,
  onSelect,
  onCreated,
}: {
  portfolios: LivePortfolio[];
  selected: string;
  onSelect: (id: string) => void;
  onCreated: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [startingCapital, setStartingCapital] = useState("400000");
  const [pilotCap, setPilotCap] = useState("400000");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<ActionStatus | null>(null);

  async function create() {
    setBusy(true);
    setStatus(null);
    try {
      await authPost("/api/v1/live-portfolios", {
        name: name.trim() || "Pilot",
        starting_capital: startingCapital,
        pilot_capital_cap: pilotCap,
      });
      setStatus({ kind: "ok", text: "Live portfolio created." });
      setCreating(false);
      setName("");
      onCreated();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <h2>
          <Radio size={15} />
          Live pilot portfolio
        </h2>
        {status && <span className={`action-status ${status.kind}`}>{status.text}</span>}
      </div>
      <div className="panel-body">
        <div className="picker-row" style={{ marginBottom: creating ? 12 : 0 }}>
          <select value={selected} onChange={(event) => onSelect(event.target.value)}>
            {portfolios.length === 0 && <option value="">No live portfolios yet</option>}
            {portfolios.map((p) => (
              <option key={p.live_portfolio_id} value={p.live_portfolio_id}>
                {p.name} ({p.status}, {p.capital_tier})
              </option>
            ))}
          </select>
          <FounderGate>
            <button disabled={busy} onClick={() => setCreating((v) => !v)}>
              {creating ? "Cancel" : "New pilot portfolio"}
            </button>
          </FounderGate>
        </div>
        {creating && (
          <FounderGate>
            <div className="reject-form">
              <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
              <input
                placeholder="Starting capital"
                value={startingCapital}
                onChange={(e) => setStartingCapital(e.target.value)}
              />
              <input
                placeholder="Pilot capital cap"
                value={pilotCap}
                onChange={(e) => setPilotCap(e.target.value)}
              />
              <button disabled={busy} onClick={create}>
                Create
              </button>
            </div>
          </FounderGate>
        )}
      </div>
    </div>
  );
}

function PortfolioControlPanel({
  portfolioId,
  onChanged,
}: {
  portfolioId: string;
  onChanged: () => void;
}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [pilotStatus, setPilotStatus] = useState<PilotStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<ActionStatus | null>(null);

  const load = useCallback(() => {
    if (!portfolioId) return;
    apiGet<Summary | null>(`/api/v1/live-portfolios/${portfolioId}/summary`, null).then(setSummary);
    apiGet<PilotStatus | null>(`/api/v1/live-portfolios/${portfolioId}/pilot-status`, null).then(
      setPilotStatus,
    );
  }, [portfolioId]);

  useEffect(() => {
    load();
  }, [load]);

  async function runAction(action: string, body?: unknown) {
    setBusy(true);
    setStatus(null);
    try {
      const result = await authPost<{ created_intent_count?: number }>(
        `/api/v1/live-portfolios/${portfolioId}/${action}`,
        body,
      );
      const detail =
        action === "decision-cycle" && typeof result?.created_intent_count === "number"
          ? ` (${result.created_intent_count} real intent(s) proposed)`
          : "";
      setStatus({ kind: "ok", text: `${action} done${detail}.` });
      load();
      onChanged();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  if (!portfolioId) return null;
  if (!summary) return <PanelSkeleton lines={5} />;

  const positionRows = Object.entries(summary.positions);

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <h2>
          <Wallet size={15} />
          Pilot health
        </h2>
        {status && <span className={`action-status ${status.kind}`}>{status.text}</span>}
      </div>
      <div className="panel-body">
        <ul className="reasoning">
          <li>
            <span className="k">Status</span>
            <span className={`status-pill ${statusPillClass(summary.portfolio.status)}`}>
              {summary.portfolio.status}
            </span>
          </li>
          <li>
            <span className="k">Capital tier</span>
            <span className={`tier-pill ${summary.portfolio.capital_tier}`}>
              {summary.portfolio.capital_tier}
            </span>
          </li>
          <li>
            <span className="k">Real cash</span>
            <span className="v">{money(summary.cash, { compact: true })}</span>
          </li>
          <li>
            <span className="k">Unsettled receivables</span>
            <span className="v">{money(summary.unsettled_receivables, { compact: true })}</span>
          </li>
          <li>
            <span className="k">Pilot capital cap</span>
            <span className="v">{money(summary.portfolio.pilot_capital_cap, { compact: true })}</span>
          </li>
          <li>
            <span className="k">Clean fills toward graduation</span>
            <span className="v">
              {pilotStatus ? `${pilotStatus.clean_fill_count} of ${pilotStatus.graduation_threshold}` : "…"}
            </span>
          </li>
        </ul>

        {positionRows.length > 0 && (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>Real quantity held</th>
                </tr>
              </thead>
              <tbody>
                {positionRows.map(([instrumentId, qty]) => (
                  <tr key={instrumentId}>
                    <td>{instrumentId}</td>
                    <td>{qty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="hint" style={{ marginTop: 12 }}>
          {summary.open_incidents.length === 0
            ? "No open incidents."
            : `${summary.open_incidents.length} open incident(s): ${summary.open_incidents
                .map((incident) => `${incident.severity} — ${incident.description}`)
                .join("; ")}`}
        </p>

        <div className="picker-row" style={{ marginTop: 14, flexWrap: "wrap" }}>
          <FounderGate>
            <button disabled={busy} onClick={() => runAction("activate")}>
              Activate
            </button>
          </FounderGate>
          <button disabled={busy} onClick={() => runAction("pause")}>
            Pause
          </button>
          <FounderGate>
            <button disabled={busy} onClick={() => runAction("resume")}>
              Resume
            </button>
          </FounderGate>
          <button disabled={busy} onClick={() => runAction("freeze")}>
            Freeze
          </button>
          <FounderGate>
            <button disabled={busy} onClick={() => runAction("decision-cycle")}>
              Run decision cycle
            </button>
          </FounderGate>
          <button disabled={busy} onClick={() => runAction("reconcile-now")}>
            <RefreshCw size={13} style={{ marginRight: 4 }} />
            Reconcile now
          </button>
        </div>
      </div>
    </div>
  );
}

function PendingIntentsPanel({
  portfolioId,
  onChanged,
}: {
  portfolioId: string;
  onChanged: () => void;
}) {
  const [intents, setIntents] = useState<Intent[] | null>(null);
  const [orders, setOrders] = useState<LiveOrder[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<ActionStatus | null>(null);
  const [confirmingBatch, setConfirmingBatch] = useState(false);
  const [batchConfirmText, setBatchConfirmText] = useState("");

  const load = useCallback(() => {
    if (!portfolioId) return;
    apiGet<Intent[]>("/api/v1/live-order-intents", []).then((all) =>
      setIntents(all.filter((i) => i.live_portfolio_id === portfolioId)),
    );
    apiGet<LiveOrder[]>("/api/v1/live-orders", []).then(setOrders);
  }, [portfolioId]);

  useEffect(() => {
    load();
  }, [load]);

  const pending = (intents ?? []).filter((i) => i.intent_status === "PENDING_APPROVAL");
  const approved = (intents ?? []).filter((i) => i.intent_status === "APPROVED");
  const buyCount = pending.filter((i) => i.side === "BUY").length;
  const sellCount = pending.filter((i) => i.side === "SELL").length;

  async function approveOne(id: string) {
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/live-order-intents/${id}/approve`);
      setStatus({ kind: "ok", text: "Approved." });
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  async function rejectOne(id: string) {
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/live-order-intents/${id}/reject`, { reason: "Rejected from Cockpit" });
      setStatus({ kind: "ok", text: "Rejected." });
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  async function approveWholeCycle() {
    setBusy(true);
    setStatus(null);
    try {
      const result = await authPost<{ approved_count: number }>(
        `/api/v1/live-portfolios/${portfolioId}/approve-pending-cycle`,
      );
      setStatus({ kind: "ok", text: `Approved ${result.approved_count} real intent(s).` });
      setConfirmingBatch(false);
      setBatchConfirmText("");
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  async function executeApproved() {
    setBusy(true);
    setStatus(null);
    try {
      const result = await authPost<unknown[]>(
        `/api/v1/live-portfolios/${portfolioId}/execute-approved-orders`,
      );
      setStatus({ kind: "ok", text: `Execution attempted for ${result.length} order(s).` });
      onChanged();
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  async function pollOrders() {
    setBusy(true);
    setStatus(null);
    try {
      await authPost("/api/v1/live-orders/poll");
      setStatus({ kind: "ok", text: "Polled real broker order status." });
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const requiredBatchText = `APPROVE ${pending.length}`;

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <h2>
          <ClipboardCheck size={15} />
          Pending rebalance cycle ({pending.length})
        </h2>
        {status && <span className={`action-status ${status.kind}`}>{status.text}</span>}
      </div>
      <div className="panel-body">
        {intents === null && <p className="hint">Loading real pending intents…</p>}
        {intents !== null && pending.length === 0 && approved.length === 0 && (
          <p className="hint">No live intents are waiting on a decision right now.</p>
        )}

        {pending.length > 0 && (
          <>
            <p className="hint" style={{ marginBottom: 10 }}>
              {buyCount} buy / {sellCount} sell across {pending.length} real position(s).
            </p>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Side</th>
                    <th>Proposed qty</th>
                    <th>Reason codes</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((intent) => (
                    <tr key={intent.live_order_intent_id}>
                      <td>{intent.instrument_id}</td>
                      <td>
                        <span className={`side-badge ${intent.side}`}>{intent.side}</span>
                      </td>
                      <td>{intent.proposed_quantity}</td>
                      <td>{intent.reason_codes_json.join(", ") || "None"}</td>
                      <td>
                        <FounderGate>
                          <div className="reject-form">
                            <button disabled={busy} onClick={() => approveOne(intent.live_order_intent_id)}>
                              Approve
                            </button>
                            <button disabled={busy} onClick={() => rejectOne(intent.live_order_intent_id)}>
                              Reject
                            </button>
                          </div>
                        </FounderGate>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <FounderGate>
              {!confirmingBatch ? (
                <button style={{ marginTop: 12 }} disabled={busy} onClick={() => setConfirmingBatch(true)}>
                  Approve whole cycle ({pending.length})
                </button>
              ) : (
                <div className="typed-confirm">
                  <span>
                    Type <strong>{requiredBatchText}</strong> to approve all {pending.length} real intents
                    in this rebalance cycle at once.
                  </span>
                  <div className="typed-confirm-row">
                    <input
                      value={batchConfirmText}
                      onChange={(e) => setBatchConfirmText(e.target.value)}
                      placeholder={requiredBatchText}
                    />
                    <button
                      disabled={busy || batchConfirmText !== requiredBatchText}
                      onClick={approveWholeCycle}
                    >
                      Confirm
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => {
                        setConfirmingBatch(false);
                        setBatchConfirmText("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </FounderGate>
          </>
        )}

        {approved.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <p className="hint">{approved.length} real intent(s) approved, awaiting real execution.</p>
            <FounderGate>
              <button disabled={busy} onClick={executeApproved}>
                Execute approved orders now
              </button>
            </FounderGate>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <button disabled={busy} onClick={pollOrders}>
            Poll real broker order status
          </button>
          {orders !== null && orders.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Status</th>
                    <th>Broker order id</th>
                    <th>Rejection reason</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.slice(0, 20).map((order) => (
                    <tr key={order.live_order_id}>
                      <td>{order.instrument_id}</td>
                      <td>{order.status}</td>
                      <td>{order.broker_order_id_nullable ?? "—"}</td>
                      <td>{order.rejection_reason_nullable ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function GraduatePanel({ portfolioId, onChanged }: { portfolioId: string; onChanged: () => void }) {
  const [pilotStatus, setPilotStatus] = useState<PilotStatus | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [confirmAmountText, setConfirmAmountText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<ActionStatus | null>(null);

  const load = useCallback(() => {
    if (!portfolioId) return;
    apiGet<PilotStatus | null>(`/api/v1/live-portfolios/${portfolioId}/pilot-status`, null).then(
      setPilotStatus,
    );
  }, [portfolioId]);

  useEffect(() => {
    load();
  }, [load]);

  async function graduate() {
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/live-portfolios/${portfolioId}/graduate`, {
        reason: reason.trim(),
        confirmed_new_capital_amount: amount,
      });
      setStatus({ kind: "ok", text: "Graduated to FULL capital tier." });
      setConfirming(false);
      setReason("");
      setAmount("");
      setConfirmAmountText("");
      load();
      onChanged();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  if (!pilotStatus || pilotStatus.capital_tier === "FULL") return null;

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>
          <GraduationCap size={15} />
          Graduate to full capital
        </h2>
        {status && <span className={`action-status ${status.kind}`}>{status.text}</span>}
      </div>
      <div className="panel-body">
        <p className="hint">
          {pilotStatus.clean_fill_count} of {pilotStatus.graduation_threshold} clean real fills.{" "}
          {pilotStatus.threshold_met ? "Threshold met." : "Threshold not yet met."}
        </p>
        <FounderGate>
          {!confirming ? (
            <button disabled={!pilotStatus.threshold_met} onClick={() => setConfirming(true)}>
              Start graduation
            </button>
          ) : (
            <div className="typed-confirm">
              <input placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <input
                placeholder="New confirmed capital amount"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <span>
                Type the exact amount (<strong>{amount || "…"}</strong>) again to confirm this is a
                real, deliberate capital increase.
              </span>
              <div className="typed-confirm-row">
                <input
                  value={confirmAmountText}
                  onChange={(e) => setConfirmAmountText(e.target.value)}
                  placeholder="Confirm amount"
                />
                <button
                  disabled={
                    busy || !reason.trim() || !amount.trim() || confirmAmountText !== amount.trim()
                  }
                  onClick={graduate}
                >
                  Graduate
                </button>
                <button disabled={busy} onClick={() => setConfirming(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </FounderGate>
      </div>
    </div>
  );
}

export default function LiveTradingPage() {
  const [portfolios, setPortfolios] = useState<LivePortfolio[]>([]);
  const [selected, setSelected] = useState("");

  const loadPortfolios = useCallback(() => {
    apiGet<LivePortfolio[]>("/api/v1/live-portfolios", []).then((data) => {
      setPortfolios(data);
      setSelected((current) => current || data[0]?.live_portfolio_id || "");
    });
  }, []);

  useEffect(() => {
    loadPortfolios();
  }, [loadPortfolios]);

  return (
    <CockpitShell>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">Live Trading</h1>
          <p className="hint">
            A fully gated real-money pilot. Every mutating action here calls the exact same
            role-checked backend endpoints as any other client would.
          </p>
        </div>
      </div>
      <LiveWarningBanner />
      <PortfolioPicker
        portfolios={portfolios}
        selected={selected}
        onSelect={setSelected}
        onCreated={loadPortfolios}
      />
      {selected && (
        <>
          <PortfolioControlPanel portfolioId={selected} onChanged={loadPortfolios} />
          <PendingIntentsPanel portfolioId={selected} onChanged={loadPortfolios} />
          <GraduatePanel portfolioId={selected} onChanged={loadPortfolios} />
        </>
      )}
    </CockpitShell>
  );
}
