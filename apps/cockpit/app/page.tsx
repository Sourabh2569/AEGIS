"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "./api-client";
import CockpitShell from "./cockpit-shell";

type Instrument = {
  aegis_instrument_id: string;
  current_symbol: string;
  company_legal_name: string;
  sector: string;
};

type SignalRow = {
  aegis_instrument_id: string;
  signal: "BUY" | "SELL" | "HOLD" | "NO_POSITION";
  close: string;
  momentum_60: string | null;
};

type SignalsResponse = { signals: SignalRow[]; warnings: string[] };

type PaperPortfolio = { paper_portfolio_id: string; name: string; status: string };

function money(value: string): string {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function pct(value: string | null): string | null {
  if (value === null) return null;
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function InstrumentCard({
  instrument,
  signalRow,
  signalsLoaded,
}: {
  instrument: Instrument;
  signalRow: SignalRow | undefined;
  signalsLoaded: boolean;
}) {
  const tone = signalRow?.signal ?? "loading";
  const momentumPct = signalRow ? pct(signalRow.momentum_60) : null;
  const momentumTone =
    signalRow?.momentum_60 !== null && signalRow?.momentum_60 !== undefined
      ? Number(signalRow.momentum_60) >= 0
        ? "pos"
        : "neg"
      : null;

  return (
    <Link href={`/instruments/${instrument.current_symbol}`} className="instrument-card">
      <div className="instrument-card-head">
        <span className={`instrument-avatar ${tone}`}>
          {instrument.current_symbol.slice(0, 2)}
        </span>
        <div className="instrument-card-id">
          <div className="instrument-symbol">{instrument.current_symbol}</div>
          <div className="instrument-sector">{instrument.sector}</div>
        </div>
      </div>
      <div className="instrument-company">{instrument.company_legal_name}</div>
      <div className="instrument-card-foot">
        <span className="instrument-close">{signalRow ? money(signalRow.close) : "—"}</span>
        <span className="instrument-card-badges">
          {momentumPct && (
            <span className={`delta-pill ${momentumTone}`}>{momentumPct}</span>
          )}
          {signalsLoaded && signalRow && (
            <span className={`signal-badge small ${signalRow.signal}`}>
              <span className="dot" />
              {signalRow.signal.replace("_", " ")}
            </span>
          )}
        </span>
      </div>
    </Link>
  );
}

function Home() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [signalsById, setSignalsById] = useState<Map<string, SignalRow>>(new Map());
  const [signalsLoaded, setSignalsLoaded] = useState(false);
  const [portfolios, setPortfolios] = useState<PaperPortfolio[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState("");
  const [query, setQuery] = useState("");
  const [buyOnly, setBuyOnly] = useState(false);

  useEffect(() => {
    apiGet<Instrument[]>("/api/v1/instruments", []).then((data) =>
      setInstruments([...data].sort((a, b) => a.current_symbol.localeCompare(b.current_symbol))),
    );
    apiGet<PaperPortfolio[]>("/api/v1/paper-portfolios", []).then(setPortfolios);
  }, []);

  const loadSignals = useCallback((portfolioId: string) => {
    setSignalsLoaded(false);
    const query = portfolioId ? `?paper_portfolio_id=${encodeURIComponent(portfolioId)}` : "";
    apiGet<SignalsResponse | null>(`/api/v1/signals${query}`, null).then((result) => {
      setSignalsById(new Map((result?.signals ?? []).map((row) => [row.aegis_instrument_id, row])));
      setSignalsLoaded(true);
    });
  }, []);

  useEffect(() => {
    loadSignals(selectedPortfolio);
  }, [selectedPortfolio, loadSignals]);

  const buyCount = instruments.filter(
    (instrument) => signalsById.get(instrument.aegis_instrument_id)?.signal === "BUY",
  ).length;

  const filtered = instruments.filter((instrument) => {
    const matchesQuery =
      instrument.current_symbol.toLowerCase().includes(query.toLowerCase()) ||
      instrument.company_legal_name.toLowerCase().includes(query.toLowerCase());
    if (!matchesQuery) return false;
    if (buyOnly) return signalsById.get(instrument.aegis_instrument_id)?.signal === "BUY";
    return true;
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">Open an instrument</h1>
          <p className="hint" style={{ marginTop: 0 }}>
            {instruments.length
              ? `${instruments.length} real, verified Nifty 50 instruments`
              : "Loading real instrument universe…"}
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

      <div className="picker-row">
        <input
          placeholder="Search symbol or company…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: "100%", maxWidth: 420 }}
        />
        <label className="buy-only-toggle">
          <input
            type="checkbox"
            checked={buyOnly}
            onChange={(event) => setBuyOnly(event.target.checked)}
          />
          BUY only ({buyCount})
        </label>
      </div>

      <div className="instrument-grid">
        {filtered.map((instrument) => (
          <InstrumentCard
            key={instrument.current_symbol}
            instrument={instrument}
            signalRow={signalsById.get(instrument.aegis_instrument_id)}
            signalsLoaded={signalsLoaded}
          />
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <CockpitShell>
      <Home />
    </CockpitShell>
  );
}
