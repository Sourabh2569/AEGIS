"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, IndianRupee, TrendingUp } from "lucide-react";
import { apiGet } from "../../api-client";
import CockpitShell from "../../cockpit-shell";
import { FundamentalsDashboard, type FundamentalsResponse } from "../../fundamentals-dashboard";
import { KpiCard, KpiStrip } from "../../kpi-strip";
import { money } from "../../money";

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

function pct(value: string | null): string | null {
  if (value === null) return null;
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function SectorScreenerCompany({ symbol }: { symbol: string }) {
  const [row, setRow] = useState<ScreenerRow | null>(null);
  const [sector, setSector] = useState<string | null>(null);
  const [fundamentals, setFundamentals] = useState<FundamentalsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiGet<ScreenerResponse | null>("/api/v1/sector-screener/instruments", null),
      apiGet<FundamentalsResponse | null>(`/api/v1/instruments/${symbol}/fundamentals`, null),
    ]).then(([screener, fundamentalsData]) => {
      if (cancelled) return;
      if (screener) {
        for (const [sectorName, rows] of Object.entries(screener.sectors)) {
          const match = rows.find((candidate) => candidate.symbol === symbol);
          if (match) {
            setRow(match);
            setSector(sectorName);
            break;
          }
        }
      }
      setFundamentals(fundamentalsData);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (loading) {
    return <p className="hint">Loading real Sector Screener data for {symbol}…</p>;
  }

  if (!row) {
    return (
      <div className="empty-state">
        {symbol} is not a real Sector Screener company, or no real price data has been synced yet
        — run a sync first.
      </div>
    );
  }

  const fundamentalsReal = fundamentals?.available || fundamentals?.consolidated.available;
  const momentumPct = pct(row.momentum_60);
  const momentumTone: "pos" | "neg" =
    row.momentum_60 !== null && Number(row.momentum_60) >= 0 ? "pos" : "neg";

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{symbol}</h1>
          <p className="hint" style={{ marginTop: 4, marginBottom: 0 }}>
            {row.company_legal_name} · {sector}
          </p>
        </div>
        <Link href="/sector-screener">&larr; Sector Screener</Link>
      </div>

      <div className="confidence-strip">
        <div className="row real">
          <span className="label">Price &amp; momentum</span>
          <span className="value">
            Real, Kite Connect · isolated Sector Screener universe, separate from the main
            50-instrument momentum strategy
          </span>
        </div>
        <div className={`row ${fundamentalsReal ? "real" : "unavailable"}`}>
          <span className="label">Fundamentals</span>
          <span className="value">
            {fundamentalsReal
              ? `Real, NSE XBRL · ${[
                  fundamentals?.consolidated.available && "Consolidated",
                  fundamentals?.available && "Standalone",
                ]
                  .filter(Boolean)
                  .join(" + ")}`
              : (fundamentals?.reason ?? "Not available — no real quarterly filing uploaded yet")}
          </span>
        </div>
      </div>

      <KpiStrip>
        <KpiCard icon={IndianRupee} label="Close" value={row.close ? money(row.close) : "n/a"} />
        <KpiCard
          icon={Activity}
          label="60-day momentum"
          value={momentumPct ?? "n/a"}
          delta={momentumPct ? { text: momentumPct, tone: momentumTone } : null}
        />
        <KpiCard
          icon={TrendingUp}
          label="SMA 50 / SMA 200"
          value={`${row.sma_50 ? money(row.sma_50) : "n/a"} / ${row.sma_200 ? money(row.sma_200) : "n/a"}`}
          caption="real momentum inputs, no trading strategy runs on this universe"
        />
      </KpiStrip>

      <FundamentalsDashboard fundamentals={fundamentals} close={row.close ?? undefined} />

      {!fundamentalsReal && (
        <div className="panel">
          <div className="panel-body">
            <p className="hint" style={{ marginBottom: 0 }}>
              No real fundamentals uploaded yet for {symbol}. Upload a real Standalone or
              Consolidated quarterly filing from the{" "}
              <Link href="/operations">Operations page</Link>&apos;s manual-import panel — it
              works for any real company, not just the main 50-instrument universe.
            </p>
          </div>
        </div>
      )}
    </>
  );
}

export default function SectorScreenerCompanyPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  return (
    <CockpitShell>
      <SectorScreenerCompany symbol={symbol.toUpperCase()} />
    </CockpitShell>
  );
}
