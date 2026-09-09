"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet } from "./api-client";
import CockpitShell from "./cockpit-shell";

type Instrument = {
  current_symbol: string;
  company_legal_name: string;
  sector: string;
};

function Home() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    apiGet<Instrument[]>("/api/v1/instruments", []).then((data) =>
      setInstruments([...data].sort((a, b) => a.current_symbol.localeCompare(b.current_symbol))),
    );
  }, []);

  const filtered = instruments.filter(
    (instrument) =>
      instrument.current_symbol.toLowerCase().includes(query.toLowerCase()) ||
      instrument.company_legal_name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="symbol-search">
      <h1>Open an instrument</h1>
      <p className="sub">
        {instruments.length
          ? `${instruments.length} real, verified Nifty 50 instruments`
          : "Loading real instrument universe…"}
      </p>
      <input
        placeholder="Search symbol or company…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        style={{ width: "100%" }}
      />
      <div className="symbol-grid">
        {filtered.map((instrument) => (
          <Link
            key={instrument.current_symbol}
            href={`/instruments/${instrument.current_symbol}`}
            className="symbol-chip"
          >
            {instrument.current_symbol}
          </Link>
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
