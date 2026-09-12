"use client";

import { Factory } from "lucide-react";
import { useEffect, useState } from "react";
import { apiGet } from "../api-client";
import CockpitShell from "../cockpit-shell";
import { money } from "../money";

type ScreenerRow = {
  symbol: string;
  aegis_instrument_id: string;
  company_legal_name: string;
  close: string | null;
  momentum_60: string | null;
  sma_50: string | null;
  sma_200: string | null;
  atr_14: string | null;
};

type ScreenerResponse = {
  as_of: string | null;
  dataset_origin: string | null;
  raw_snapshot_hash: string | null;
  sectors: Record<string, ScreenerRow[]>;
  warnings: string[];
};

const SECTOR_ORDER = ["Pharmaceuticals", "Solar & Renewable Energy", "Electronics Manufacturing"];

function pct(value: string | null): string | null {
  if (value === null) return null;
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function toneAccentClass(momentum: string | null): string {
  if (momentum === null) return "tone-accent neutral";
  return Number(momentum) >= 0 ? "tone-accent pos" : "tone-accent neg";
}

function ScreenerCard({ row }: { row: ScreenerRow }) {
  const momentumPct = pct(row.momentum_60);
  const momentumTone = row.momentum_60 !== null ? (Number(row.momentum_60) >= 0 ? "pos" : "neg") : null;
  return (
    <div className={`instrument-card ${toneAccentClass(row.momentum_60)}`}>
      <div className="instrument-card-head">
        <span className={`instrument-avatar ${momentumTone ?? "loading"}`}>
          {row.symbol.slice(0, 2)}
        </span>
        <div className="instrument-card-id">
          <div className="instrument-symbol">{row.symbol}</div>
        </div>
      </div>
      <div className="instrument-company">{row.company_legal_name}</div>
      <div className="instrument-card-foot">
        <span className="instrument-close">{row.close ? money(row.close) : "—"}</span>
        <span className="instrument-card-badges">
          {momentumPct && <span className={`delta-pill ${momentumTone}`}>{momentumPct}</span>}
        </span>
      </div>
    </div>
  );
}

function SectorSection({ sector, rows }: { sector: string; rows: ScreenerRow[] }) {
  return (
    <div className="panel" style={{ marginBottom: 18 }}>
      <div className="panel-head">
        <h2>
          <Factory size={15} />
          {sector} ({rows.length})
        </h2>
      </div>
      <div className="panel-body">
        <div className="instrument-grid">
          {rows.map((row) => (
            <ScreenerCard key={row.symbol} row={row} />
          ))}
        </div>
      </div>
    </div>
  );
}

function SectorScreener() {
  const [data, setData] = useState<ScreenerResponse | null>(null);

  useEffect(() => {
    apiGet<ScreenerResponse | null>("/api/v1/sector-screener/instruments", null).then(setData);
  }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">
            <Factory size={20} /> Sector Screener
          </h1>
          <p className="hint">
            Real price and momentum across Pharmaceuticals, Solar &amp; Renewable Energy, and
            Electronics Manufacturing — a separate, isolated universe from the main Nifty
            momentum strategy. Fundamentals are not yet available for any of these companies
            (see the Instrument Decision View for why).
          </p>
        </div>
      </div>

      {data === null ? (
        <p className="hint">Loading real sector screener data…</p>
      ) : (
        <>
          {data.warnings.length > 0 && (
            <div className="confidence-strip" style={{ marginBottom: 18 }}>
              {data.warnings.map((warning) => (
                <div className="row unavailable" key={warning}>
                  <span className="label">Sector Screener</span>
                  <span className="value">{warning}</span>
                </div>
              ))}
            </div>
          )}
          {data.as_of && (
            <p className="hint">
              Real, {data.dataset_origin} · as of {data.as_of} · hash{" "}
              {data.raw_snapshot_hash?.slice(0, 10)}…
            </p>
          )}
          {SECTOR_ORDER.map((sector) => (
            <SectorSection key={sector} sector={sector} rows={data.sectors[sector] ?? []} />
          ))}
        </>
      )}
    </>
  );
}

export default function SectorScreenerPage() {
  return (
    <CockpitShell>
      <SectorScreener />
    </CockpitShell>
  );
}
