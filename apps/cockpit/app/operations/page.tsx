"use client";

import { ShieldOff, AlertTriangle, FileUp, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet, authDelete, authPost, authPostFormData } from "../api-client";
import CockpitShell from "../cockpit-shell";
import { PanelSkeleton } from "../skeleton";

const KILL_SWITCH_TYPES = [
  "GLOBAL_TRADING_KILL_SWITCH",
  "PORTFOLIO_KILL_SWITCH",
  "STRATEGY_KILL_SWITCH",
  "INSTRUMENT_KILL_SWITCH",
  "DATA_PROVIDER_KILL_SWITCH",
  "BROKER_ADAPTER_KILL_SWITCH",
  "RISK_ENGINE_KILL_SWITCH",
  "COMPLIANCE_HOLD_KILL_SWITCH",
  "SECURITY_INCIDENT_KILL_SWITCH",
] as const;

type KillSwitch = {
  id: string;
  switch_type: string;
  scope_id: string;
  is_active: boolean;
  reason: string;
  updated_at: string;
};

type Incident = {
  id: string;
  paper_portfolio_id: string;
  incident_type: string;
  severity: string;
  description: string;
  status: string;
  created_at: string;
  resolved_at_nullable: string | null;
};

type ActionStatus = { kind: "ok" | "error"; text: string };

function KillSwitches() {
  const [switches, setSwitches] = useState<KillSwitch[] | null>(null);
  const [switchType, setSwitchType] = useState<string>(KILL_SWITCH_TYPES[0]);
  const [scopeId, setScopeId] = useState("GLOBAL");
  const [activateReason, setActivateReason] = useState("");
  const [deactivateReasons, setDeactivateReasons] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<ActionStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiGet<KillSwitch[]>("/api/v1/kill-switches", []).then(setSwitches);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleActivate() {
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/kill-switches/${encodeURIComponent(scopeId)}/activate`, {
        switch_type: switchType,
        reason: activateReason,
      });
      setStatus({ kind: "ok", text: `${switchType} activated for scope "${scopeId}".` });
      setActivateReason("");
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  async function handleDeactivate(id: string) {
    const reason = deactivateReasons[id]?.trim();
    if (!reason) {
      setStatus({ kind: "error", text: "A documented reason is required to deactivate." });
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/kill-switches/${encodeURIComponent(id)}/deactivate`, { reason });
      setStatus({ kind: "ok", text: "Kill switch deactivated." });
      setDeactivateReasons((prev) => ({ ...prev, [id]: "" }));
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const activeCount = switches?.filter((s) => s.is_active).length ?? 0;

  return (
    <div className="panel" style={{ marginBottom: 18 }}>
      <div className={`panel-head ${activeCount > 0 ? "alert" : ""}`}>
        <h2>
          <ShieldOff size={15} />
          Kill switches ({activeCount} active)
        </h2>
      </div>
      <div className="panel-body">
        {switches === null ? (
          <PanelSkeleton lines={3} />
        ) : (
          <>
            {switches.length === 0 ? (
              <p className="hint">No kill switches created yet.</p>
            ) : (
              <ul className="reasoning">
                {switches.map((switchItem) => (
                  <li key={switchItem.id}>
                    <span className="k">
                      <span
                        className={`status-pill ${switchItem.is_active ? "status-frozen" : "status-neutral"}`}
                      >
                        {switchItem.is_active ? "ACTIVE" : "inactive"}
                      </span>{" "}
                      {switchItem.switch_type} · {switchItem.scope_id}
                      <div className="hint" style={{ marginTop: 4 }}>
                        {switchItem.reason}
                      </div>
                    </span>
                    <span className="v">
                      {switchItem.is_active && (
                        <div className="reject-form">
                          <input
                            placeholder="Reason to deactivate…"
                            value={deactivateReasons[switchItem.id] ?? ""}
                            onChange={(event) =>
                              setDeactivateReasons((prev) => ({
                                ...prev,
                                [switchItem.id]: event.target.value,
                              }))
                            }
                          />
                          <button
                            disabled={busy}
                            onClick={() => handleDeactivate(switchItem.id)}
                          >
                            Deactivate
                          </button>
                        </div>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <p className="hint" style={{ marginTop: 12, marginBottom: 6 }}>
              Activate a new kill switch — this immediately blocks matching pending/approved
              paper-trade intents and future order execution.
            </p>
            <div className="reject-form" style={{ flexWrap: "wrap" }}>
              <select value={switchType} onChange={(event) => setSwitchType(event.target.value)}>
                {KILL_SWITCH_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <input
                placeholder='Scope: "GLOBAL", a portfolio id, or an instrument id'
                value={scopeId}
                onChange={(event) => setScopeId(event.target.value)}
                style={{ width: 260 }}
              />
              <input
                placeholder="Real reason (required)…"
                value={activateReason}
                onChange={(event) => setActivateReason(event.target.value)}
                style={{ width: 220 }}
              />
              <button
                className="primary"
                disabled={busy || !activateReason.trim() || !scopeId.trim()}
                onClick={handleActivate}
              >
                Activate
              </button>
            </div>
          </>
        )}
        {status && <p className={`action-status ${status.kind}`}>{status.text}</p>}
      </div>
    </div>
  );
}

function Incidents() {
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [status, setStatus] = useState<ActionStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiGet<Incident[]>("/api/v1/paper-incidents", []).then(setIncidents);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleResolve(id: string) {
    setBusy(true);
    setStatus(null);
    try {
      await authPost(`/api/v1/paper-incidents/${encodeURIComponent(id)}/resolve`);
      setStatus({ kind: "ok", text: "Incident resolved." });
      load();
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const open = incidents?.filter((incident) => incident.status !== "RESOLVED") ?? [];

  return (
    <div className="panel">
      <div className={`panel-head ${open.length > 0 ? "alert" : ""}`}>
        <h2>
          <AlertTriangle size={15} />
          Incidents ({open.length} open)
        </h2>
      </div>
      <div className="panel-body">
        {incidents === null ? (
          <PanelSkeleton lines={3} />
        ) : incidents.length === 0 ? (
          <p className="hint">No real incidents recorded yet.</p>
        ) : (
          <ul className="reasoning">
            {incidents.map((incident) => (
              <li key={incident.id}>
                <span className="k">
                  <span
                    className={`status-pill ${incident.status === "RESOLVED" ? "status-active" : "status-frozen"}`}
                  >
                    {incident.status}
                  </span>{" "}
                  {incident.incident_type} · {incident.severity}
                  <div className="hint" style={{ marginTop: 4 }}>
                    {incident.description}
                  </div>
                </span>
                <span className="v">
                  {incident.status !== "RESOLVED" && (
                    <button disabled={busy} onClick={() => handleResolve(incident.id)}>
                      Resolve
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {status && <p className={`action-status ${status.kind}`}>{status.text}</p>}
      </div>
    </div>
  );
}

type UploadResult = {
  symbol: string;
  accepted: boolean;
  skip_reason: string | null;
  run: { records_accepted: number };
};

type FundamentalsQuarter = { period_from: string; period_to: string; filing_date: string };

type FundamentalsHistory = {
  symbol: string;
  quarters: FundamentalsQuarter[];
  ttm_eps: string | null;
  ttm_eps_quarters: string[];
};

const EMPTY_HISTORY: FundamentalsHistory = {
  symbol: "",
  quarters: [],
  ttm_eps: null,
  ttm_eps_quarters: [],
};

function FundamentalsImport() {
  const [symbol, setSymbol] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<ActionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<FundamentalsHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [deletingPeriod, setDeletingPeriod] = useState<string | null>(null);

  const loadHistory = useCallback((forSymbol: string) => {
    const trimmed = forSymbol.trim();
    if (!trimmed) {
      setHistory(null);
      return;
    }
    setHistoryLoading(true);
    apiGet<FundamentalsHistory>(
      `/api/v1/fundamentals-manual-import/history/${encodeURIComponent(trimmed)}`,
      EMPTY_HISTORY
    )
      .then(setHistory)
      .finally(() => setHistoryLoading(false));
  }, []);

  // Debounced lookup -- fires 400ms after the user stops typing a symbol,
  // so "quarters on file" shows up before they even pick a file, letting
  // them see what's missing instead of guessing or re-uploading a quarter
  // that's already in.
  useEffect(() => {
    const timer = setTimeout(() => loadHistory(symbol), 400);
    return () => clearTimeout(timer);
  }, [symbol, loadHistory]);

  async function handleUpload() {
    const cleanSymbol = symbol.trim();
    if (files.length === 0 || !cleanSymbol) return;
    setBusy(true);
    setStatus(null);
    const outcomes: string[] = [];
    // Sequential, not Promise.all -- every file for this symbol overwrites
    // the same work/fundamentals_manual_import/{SYMBOL}.xml on the backend,
    // so concurrent uploads would race on that same destination.
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append("symbol", cleanSymbol);
        formData.append("file", file);
        const result = await authPostFormData<UploadResult>(
          "/api/v1/fundamentals-manual-import/upload",
          formData
        );
        outcomes.push(
          result.accepted
            ? `${file.name}: accepted`
            : `${file.name}: not accepted — ${result.skip_reason ?? "unknown reason"}`
        );
      } catch (err) {
        outcomes.push(`${file.name}: ${err instanceof Error ? err.message : "upload failed"}`);
      }
    }
    const failures = outcomes.filter((line) => !line.includes(": accepted"));
    setStatus({
      kind: failures.length === 0 ? "ok" : "error",
      text: `${cleanSymbol} — ${files.length} file(s): ${outcomes.join(" · ")}`,
    });
    setFiles([]);
    loadHistory(cleanSymbol);
    setBusy(false);
  }

  async function handleDeleteQuarter(periodTo: string) {
    const cleanSymbol = symbol.trim();
    if (!cleanSymbol) return;
    setDeletingPeriod(periodTo);
    setStatus(null);
    try {
      await authDelete(
        `/api/v1/fundamentals-manual-import/history/${encodeURIComponent(cleanSymbol)}/${encodeURIComponent(periodTo)}`
      );
      setStatus({ kind: "ok", text: `${cleanSymbol}: removed the quarter ending ${periodTo}.` });
      loadHistory(cleanSymbol);
    } catch (err) {
      setStatus({ kind: "error", text: err instanceof Error ? err.message : "Delete failed" });
    } finally {
      setDeletingPeriod(null);
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 18 }}>
      <div className="panel-head">
        <h2>
          <FileUp size={15} />
          Fundamentals — manual import
        </h2>
      </div>
      <div className="panel-body">
        <p className="hint" style={{ marginBottom: 10 }}>
          NSE&apos;s Terms of Use prohibit automated scraping of financial-results filings, so
          this is the compliant path: download a real quarterly XBRL filing yourself from{" "}
          <a
            href="https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
            target="_blank"
            rel="noreferrer"
          >
            NSE&apos;s Financial Results page
          </a>{" "}
          — Equity tab, search the symbol, pick the Non-Consolidated row, download its XBRL —
          then upload that file here. Select multiple files at once (e.g. the last 4 real
          quarters) to set a symbol up for a trailing-twelve-month figure in one go; after that,
          just the newest quarter each time keeps it current.
        </p>
        <div className="reject-form" style={{ flexWrap: "wrap" }}>
          <input
            placeholder="Symbol, e.g. CIPLA"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            style={{ width: 160 }}
          />
          <input
            type="file"
            accept=".xml"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
          <button
            className="primary"
            disabled={busy || files.length === 0 || !symbol.trim()}
            onClick={handleUpload}
          >
            {busy
              ? "Uploading…"
              : files.length > 1
                ? `Upload & parse (${files.length} files)`
                : "Upload & parse"}
          </button>
        </div>

        {symbol.trim() && (
          <div style={{ marginTop: 12 }}>
            {historyLoading ? (
              <p className="hint">Checking what&apos;s already on file for {symbol.trim()}…</p>
            ) : history && history.quarters.length > 0 ? (
              <>
                <p className="hint" style={{ marginBottom: 4 }}>
                  Quarters already on file for {symbol.trim()}:
                </p>
                <ul className="reasoning">
                  {history.quarters.map((quarter) => (
                    <li key={quarter.period_to}>
                      <span className="k">
                        {quarter.period_from} to {quarter.period_to}
                      </span>
                      <span className="v">
                        filed {quarter.filing_date}
                        <button
                          title={`Delete this quarter (${quarter.period_from} to ${quarter.period_to}) -- for a wrong upload by mistake`}
                          disabled={deletingPeriod === quarter.period_to}
                          onClick={() => handleDeleteQuarter(quarter.period_to)}
                          style={{ marginLeft: 8, padding: "2px 6px" }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="hint" style={{ marginTop: 4, marginBottom: 0 }}>
                  {history.ttm_eps
                    ? `TTM EPS available: ${history.ttm_eps} (from ${history.ttm_eps_quarters.join(", ")})`
                    : `TTM EPS not available yet — ${history.quarters.length} of 4 real, contiguous quarters on file.`}
                </p>
              </>
            ) : (
              <p className="hint">No quarters uploaded yet for {symbol.trim()}.</p>
            )}
          </div>
        )}

        {status && <p className={`action-status ${status.kind}`}>{status.text}</p>}
      </div>
    </div>
  );
}

function Operations() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">
            <ShieldOff size={20} /> Operations
          </h1>
          <p className="hint">
            Real kill switches and incidents — Gate 5 of Document 007. Kill switches here
            currently gate paper-trading intent generation and order execution only; per ADR
            0026, no live execution exists for them to gate yet.
          </p>
        </div>
      </div>
      <KillSwitches />
      <Incidents />
      <FundamentalsImport />
    </>
  );
}

export default function OperationsPage() {
  return (
    <CockpitShell>
      <Operations />
    </CockpitShell>
  );
}
