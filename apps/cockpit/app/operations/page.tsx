"use client";

import { ShieldOff, AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet, authPost } from "../api-client";
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
