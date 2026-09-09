"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, authPost } from "../../api-client";
import CockpitShell from "../../cockpit-shell";
import PriceChart, { type Bar, type IndicatorPoint, type RuleEvent } from "./price-chart";
import MomentumChart from "./momentum-chart";

type OhlcvResponse = {
  symbol: string;
  aegis_instrument_id: string;
  dataset_origin: string;
  raw_snapshot_hash: string;
  bars: Bar[];
};

type IndicatorApiPoint = {
  date: string;
  close: string | null;
  sma_50: string | null;
  sma_200: string | null;
  momentum_60: string | null;
  atr_14: string | null;
};

type IndicatorsResponse = {
  points: IndicatorApiPoint[];
};

type RuleEventsResponse = { events: RuleEvent[] };

type SignalInputs = {
  close: string;
  sma_50: string | null;
  sma_200: string | null;
  momentum_60: string | null;
  atr_14: string | null;
  average_daily_value_traded_20: string | null;
  invalidation_price: string | null;
};

type SignalResponse = {
  symbol: string;
  as_of: string;
  dataset_origin: string;
  raw_snapshot_hash: string;
  signal: "BUY" | "SELL" | "HOLD" | "NO_POSITION";
  eligible: boolean;
  held: boolean;
  held_quantity: string | null;
  inputs: SignalInputs | null;
  rule_thresholds: { eligibility: string; minimum_avg_daily_value_traded_20: string; stop: string };
  warnings: string[];
};

type PaperPortfolio = { paper_portfolio_id: string; name: string; status: string };

function toNumber(value: string | null): number | null {
  return value === null ? null : Number(value);
}

function pct(value: string | null): string {
  if (value === null) return "not available";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function money(value: string | null): string {
  if (value === null) return "not available";
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function Decision({ symbol }: { symbol: string }) {
  const [bars, setBars] = useState<Bar[]>([]);
  const [indicators, setIndicators] = useState<IndicatorPoint[]>([]);
  const [ruleEvents, setRuleEvents] = useState<RuleEvent[]>([]);
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [portfolios, setPortfolios] = useState<PaperPortfolio[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState("");
  const [loading, setLoading] = useState(true);
  const [actionStatus, setActionStatus] = useState<{ kind: "ok" | "error" | "info"; text: string } | null>(
    null,
  );
  const [sending, setSending] = useState(false);

  const loadSignal = useCallback(
    async (portfolioId: string) => {
      const query = portfolioId ? `?paper_portfolio_id=${encodeURIComponent(portfolioId)}` : "";
      const data = await apiGet<SignalResponse | null>(
        `/api/v1/instruments/${symbol}/signal${query}`,
        null,
      );
      setSignal(data);
    },
    [symbol],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiGet<OhlcvResponse | null>(`/api/v1/instruments/${symbol}/ohlcv`, null),
      apiGet<IndicatorsResponse | null>(`/api/v1/instruments/${symbol}/indicators`, null),
      apiGet<RuleEventsResponse | null>(`/api/v1/instruments/${symbol}/rule-events`, null),
      apiGet<PaperPortfolio[]>("/api/v1/paper-portfolios", []),
    ]).then(([ohlcv, indicatorData, ruleEventData, portfolioList]) => {
      if (cancelled) return;
      setBars(ohlcv?.bars ?? []);
      setIndicators(
        (indicatorData?.points ?? []).map((point) => ({
          date: point.date,
          close: toNumber(point.close),
          sma_50: toNumber(point.sma_50),
          sma_200: toNumber(point.sma_200),
          momentum_60: toNumber(point.momentum_60),
          atr_14: toNumber(point.atr_14),
        })),
      );
      setRuleEvents(ruleEventData?.events ?? []);
      setPortfolios(portfolioList);
      if (portfolioList.length > 0) setSelectedPortfolio(portfolioList[0].paper_portfolio_id);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  useEffect(() => {
    loadSignal(selectedPortfolio);
  }, [selectedPortfolio, loadSignal]);

  async function handleSendToPaperTrading() {
    if (!selectedPortfolio) {
      setActionStatus({ kind: "error", text: "Select a paper portfolio first." });
      return;
    }
    const lastRealDate = bars[bars.length - 1]?.date;
    if (!lastRealDate) {
      setActionStatus({ kind: "error", text: "No real trading date available yet." });
      return;
    }
    setSending(true);
    setActionStatus(null);
    try {
      const result = await authPost<{ decision_cycle_status: string }>(
        "/api/v1/paper-trading-sessions/run",
        { paper_portfolio_id: selectedPortfolio, session_date: lastRealDate },
      );
      setActionStatus({
        kind: "ok",
        text: `Decision cycle ${result.decision_cycle_status.toLowerCase()}. Any resulting intent lands PENDING_APPROVAL in the existing approval workflow.`,
      });
      await loadSignal(selectedPortfolio);
    } catch (err) {
      setActionStatus({ kind: "error", text: err instanceof Error ? err.message : "Request failed" });
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <div className="loading">Loading real market data for {symbol}…</div>;
  }

  if (bars.length === 0) {
    return (
      <div className="empty-state">
        No real historical data captured yet for {symbol}. Run a provider sync first.
      </div>
    );
  }

  const inputs = signal?.inputs;
  const canSend = signal?.signal === "BUY" || signal?.signal === "SELL";

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{symbol}</h1>
        </div>
        <Link href="/">&larr; All instruments</Link>
      </div>

      <div className="confidence-strip">
        <div className="row real">
          <span className="label">Price &amp; volume</span>
          <span className="value">
            Real, Kite Connect &middot; {bars.length} bars &middot; hash{" "}
            {signal?.raw_snapshot_hash.slice(0, 10) ?? "—"}… &middot; through {bars[bars.length - 1].date}
          </span>
        </div>
        <div className="row unavailable">
          <span className="label">Fundamentals</span>
          <span className="value">Not available — no verified fundamentals provider yet</span>
        </div>
        <div className="row unavailable">
          <span className="label">News / sentiment</span>
          <span className="value">Not available — no provider connected</span>
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-head">
            <h2>Price &middot; SMA 50/200 &middot; ATR band</h2>
          </div>
          <PriceChart bars={bars} indicators={indicators} ruleEvents={ruleEvents} />
          <MomentumChart indicators={indicators} />
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <h2>Signal, as of {signal?.as_of ?? "—"}</h2>
            </div>
            <div className="panel-body">
              {signal && (
                <span className={`signal-badge ${signal.signal}`}>
                  <span className="dot" />
                  {signal.signal.replace("_", " ")}
                </span>
              )}
              <div className="stat">
                <span className="stat-label">Close</span>
                <span className={`stat-value ${inputs ? "" : "empty"}`}>
                  {inputs ? money(inputs.close) : "Not available"}
                </span>
              </div>
              <ul className="reasoning">
                <li>
                  <span className="k">60-day momentum</span>
                  <span
                    className={
                      inputs?.momentum_60 != null
                        ? `v ${Number(inputs.momentum_60) >= 0 ? "pos" : "neg"}`
                        : "v"
                    }
                  >
                    {inputs ? pct(inputs.momentum_60) : "not available"}
                  </span>
                </li>
                <li>
                  <span className="k">SMA 50 / SMA 200</span>
                  <span className="v">
                    {inputs ? `${money(inputs.sma_50)} / ${money(inputs.sma_200)}` : "not available"}
                  </span>
                </li>
                <li>
                  <span className="k">ATR-based stop</span>
                  <span className="v">{inputs ? money(inputs.invalidation_price) : "not available"}</span>
                </li>
                <li>
                  <span className="k">20-day avg value traded</span>
                  <span className="v">
                    {inputs ? money(inputs.average_daily_value_traded_20) : "not available"}
                  </span>
                </li>
                {signal?.held && (
                  <li>
                    <span className="k">Currently held</span>
                    <span className="v">{signal.held_quantity} shares</span>
                  </li>
                )}
              </ul>
              <p className="hint">
                Eligibility rule: {signal?.rule_thresholds.eligibility ?? "—"}, min avg value traded ₹
                {signal?.rule_thresholds.minimum_avg_daily_value_traded_20 ?? "—"}. Stop:{" "}
                {signal?.rule_thresholds.stop ?? "—"}.
              </p>
              {signal?.warnings.map((warning) => (
                <p className="hint" key={warning}>
                  {warning}
                </p>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>Send to paper trading</h2>
            </div>
            <div className="panel-body action-row">
              <select value={selectedPortfolio} onChange={(event) => setSelectedPortfolio(event.target.value)}>
                {portfolios.length === 0 && <option value="">No paper portfolios yet</option>}
                {portfolios.map((portfolio) => (
                  <option key={portfolio.paper_portfolio_id} value={portfolio.paper_portfolio_id}>
                    {portfolio.name} ({portfolio.status})
                  </option>
                ))}
              </select>
              <button
                className="primary"
                disabled={sending || !canSend || portfolios.length === 0}
                onClick={handleSendToPaperTrading}
              >
                {sending ? "Running decision cycle…" : "Propose via real strategy"}
              </button>
              {!canSend && (
                <p className="hint">
                  No actionable BUY or SELL signal for this instrument right now — nothing to propose.
                </p>
              )}
              {actionStatus && <p className={`action-status ${actionStatus.kind}`}>{actionStatus.text}</p>}
              <p className="hint">
                Calls the existing decision-cycle endpoint. Any resulting intent still requires human
                approval in the existing Paper Operations approval screen — this never bypasses it.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default function InstrumentPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  return (
    <CockpitShell>
      <Decision symbol={symbol.toUpperCase()} />
    </CockpitShell>
  );
}
