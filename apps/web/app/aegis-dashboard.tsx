"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Database,
  FileWarning,
  Gauge,
  GitBranch,
  Landmark,
  Layers,
  Lock,
  LucideIcon,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { buildModel, compactNumber, currency, percent, shortDate, toneFor, uiLabel, type DashboardData, type Tone } from "./aegis-adapter";

export type { DashboardData } from "./aegis-adapter";

type SectionId =
  | "command"
  | "lineage"
  | "dataHealth"
  | "licensing"
  | "features"
  | "universe"
  | "research"
  | "risk"
  | "drift"
  | "corporate"
  | "paper"
  | "liveReadiness"
  | "complianceSecurity"
  | "liveOps"
  | "schema";

const navGroups: Array<{ label: string; items: Array<{ id: SectionId; title: string; icon: LucideIcon }> }> = [
  { label: "Overview", items: [{ id: "command", title: "Command Center", icon: Gauge }] },
  {
    label: "Data Foundation",
    items: [
      { id: "lineage", title: "Dataset Lineage", icon: GitBranch },
      { id: "dataHealth", title: "Data Health", icon: Activity },
      { id: "licensing", title: "Provider Licensing", icon: Landmark },
      { id: "features", title: "Feature Versioning", icon: SlidersHorizontal },
      { id: "universe", title: "Instrument Universe", icon: Layers },
      { id: "corporate", title: "Corporate Actions", icon: FileWarning },
    ],
  },
  {
    label: "Research & Intelligence",
    items: [
      { id: "research", title: "Research Lab", icon: BookOpenCheck },
      { id: "risk", title: "Risk Attribution", icon: BarChart3 },
      { id: "drift", title: "Drift Statistics", icon: Activity },
    ],
  },
  { label: "Paper Operations", items: [{ id: "paper", title: "Paper Operations", icon: Workflow }] },
  {
    label: "Live Readiness",
    items: [
      { id: "liveReadiness", title: "Live Readiness", icon: Lock },
      { id: "complianceSecurity", title: "Compliance & Security", icon: ShieldCheck },
      { id: "liveOps", title: "Live Ops & Incidents", icon: ShieldAlert },
    ],
  },
  { label: "System", items: [{ id: "schema", title: "Database Internals", icon: Database }] },
];

const sectionMeta: Record<SectionId, { title: string; eyebrow: string; subtitle: string; action: string }> = {
  command: { title: "Command Center", eyebrow: "Overview", subtitle: "Executive state, portfolio health, risk posture, and attention queue.", action: "Review alerts" },
  lineage: { title: "Dataset Lineage", eyebrow: "Data Foundation", subtitle: "Provider-to-decision traceability, version trust, and point-in-time evidence.", action: "Export lineage" },
  dataHealth: { title: "Data Health", eyebrow: "Data Foundation", subtitle: "Provider health, quote freshness, calendar state, and quality readiness.", action: "View providers" },
  licensing: { title: "Provider Licensing", eyebrow: "Data Foundation", subtitle: "Permitted uses, data rights, display readiness, and license constraints.", action: "Review rights" },
  features: { title: "Feature Versioning", eyebrow: "Data Foundation", subtitle: "Feature availability, frozen versions, source dependencies, and no-look-ahead controls.", action: "Compare versions" },
  universe: { title: "Instrument Universe", eyebrow: "Data Foundation", subtitle: "Every instrument the platform tracks, with real provider-verified identifiers and classification.", action: "Export register" },
  research: { title: "Research Lab", eyebrow: "Research & Intelligence", subtitle: "Hypotheses, manifests, experiments, holdouts, and paper-observation comparison.", action: "Compare runs" },
  risk: { title: "Risk Attribution", eyebrow: "Research & Intelligence", subtitle: "Budget use, constraint impact, exposure concentration, and kill-switch state.", action: "Open rule registry" },
  drift: { title: "Drift Statistics", eyebrow: "Research & Intelligence", subtitle: "Forward paper behavior versus research expectations and recommended response.", action: "Review drift" },
  corporate: { title: "Corporate Actions", eyebrow: "Data Foundation", subtitle: "Action coverage, exception handling, ledger impact, and portfolio safety response.", action: "Review queue" },
  paper: { title: "Paper Operations", eyebrow: "Paper Operations", subtitle: "Forward workflow, approvals, simulated fills, settlement, reconciliation, and incidents.", action: "Run readiness check" },
  liveReadiness: { title: "Live Readiness", eyebrow: "Live Readiness", subtitle: "Why live execution remains locked and which gates block future pilot consideration.", action: "View controls" },
  complianceSecurity: { title: "Compliance & Security", eyebrow: "Live Readiness", subtitle: "Control maturity, evidence coverage, environment separation, and security blockers.", action: "Open evidence" },
  liveOps: { title: "Live Ops & Incidents", eyebrow: "Live Readiness", subtitle: "Future operations architecture, incident response, kill switches, and reconciliation readiness.", action: "View runbook" },
  schema: { title: "Database Internals", eyebrow: "System", subtitle: "Schema relationships, audit boundaries, persistence state, and storage evidence.", action: "Inspect schema" },
};

const technicalControls = [
  ["LIVE_EXECUTION_ENABLED", "false"],
  ["BROKER_ORDER_ACCESS", "false"],
  ["DATA_SOURCE_MODE", "LIVE_READONLY"],
  ["PAPER_TRADING_ONLY", "true"],
  ["AUDIT_MODE", "APPEND_ONLY"],
  ["NOT_BROKER_CONNECTED", "true"],
];

const liveGates: Array<[string, number, string]> = [
  ["Research integrity", 15, "In progress"],
  ["Paper evidence", 35, "In progress"],
  ["Portfolio and risk", 30, "In progress"],
  ["Security", 8, "Not started"],
  ["Operations", 5, "Not started"],
  ["Legal and compliance", 0, "Not assessed"],
  ["Governance approvals", 0, "Not started"],
  ["Controlled pilot", 0, "Blocked"],
];

const featureRows = [
  ["Momentum 20D", "dataset-version-1", "After close", "Frozen"],
  ["Volatility 20D", "dataset-version-1", "After close", "Frozen"],
  ["Gap risk input", "risk-profile-v0", "Pre-decision", "Active"],
];

const driftRows = [
  ["Signal frequency", "10 expected", "9 observed", "Within expectation"],
  ["Fill quality", "5 bps expected", "5 bps observed", "Within expectation"],
  ["Drawdown", "0-8% expected", "0.0%", "Within expectation"],
  ["Corporate action exceptions", "0 expected", "1 observed", "Critical divergence"],
];

export default function AegisDashboard({ data }: { data: DashboardData }) {
  const [section, setSection] = useState<SectionId>("command");
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState<"controls" | "audit" | null>(null);
  const [view, setView] = useState("Executive");
  const [paperDay, setPaperDay] = useState(0);
  const [failClosed, setFailClosed] = useState(false);
  const model = useMemo(() => buildModel(data), [data]);
  const meta = sectionMeta[section];

  return (
    <div className="aegis-shell">
      <Sidebar collapsed={collapsed} section={section} setSection={setSection} model={model} />
      <main className="aegis-main">
        <TopCommandBar meta={meta} collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} view={view} setView={setView} data={data} />
        <OperatingStatusRail model={model} apiVisible={model.apiVisible} onControls={() => setDrawer("controls")} />
        <PageHeader meta={meta} action={meta.action} onAction={() => setDrawer(section === "schema" ? "audit" : "controls")} />
        <div className="aegis-content">{renderSection({ section, data, model, failClosed, setFailClosed, paperDay, setPaperDay })}</div>
      </main>
      <DetailDrawer open={drawer !== null} title={drawer === "audit" ? "Audit and developer evidence" : "Operating controls"} onClose={() => setDrawer(null)}>
        {drawer === "audit" ? <AuditEvidence data={data} /> : <OperatingControls />}
      </DetailDrawer>
    </div>
  );
}

function Sidebar({
  collapsed,
  section,
  setSection,
  model,
}: {
  collapsed: boolean;
  section: SectionId;
  setSection: (section: SectionId) => void;
  model: ReturnType<typeof buildModel>;
}) {
  return (
    <aside className={`aegis-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="brand-lockup">
        <img
          className="brand-logo"
          src="/brand/aegis-logo.png?v=20260627"
          alt="AEGIS - AI-powered investment intelligence"
          width={232}
          height={93}
          style={{
            width: collapsed ? 54 : 232,
            maxWidth: "100%",
            height: collapsed ? 54 : "auto",
            objectFit: collapsed ? "cover" : "contain",
            objectPosition: "left center",
          }}
        />
      </div>
      <nav aria-label="AEGIS navigation" className="nav-stack">
        {navGroups.map((group) => (
          <div className="nav-group" key={group.label}>
            {!collapsed && <div className="nav-group-label">{group.label}</div>}
            {group.items.map(({ id, title, icon: Icon }) => (
              <button className={`nav-item ${section === id ? "is-active" : ""}`} key={id} onClick={() => setSection(id)} title={title}>
                <Icon aria-hidden className="nav-icon" />
                {!collapsed && <span>{title}</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <StatusChip tone={toneFor(model.dataSourceState)} label={model.dataSourceLabel} raw={model.dataSourceState} />
        {!collapsed && <StatusChip tone="success" label="Paper environment" raw="PAPER_TRADING_ONLY" />}
        {!collapsed && <StatusChip tone="danger" label="Live locked" raw="LIVE_EXECUTION_ENABLED=false" />}
      </div>
    </aside>
  );
}

function TopCommandBar({
  meta,
  collapsed,
  onCollapse,
  view,
  setView,
  data,
}: {
  meta: (typeof sectionMeta)[SectionId];
  collapsed: boolean;
  onCollapse: () => void;
  view: string;
  setView: (value: string) => void;
  data: DashboardData;
}) {
  return (
    <header className="top-command">
      <div className="top-left">
        <IconButton label={collapsed ? "Expand navigation" : "Collapse navigation"} onClick={onCollapse}>{collapsed ? <ChevronRight /> : <ChevronLeft />}</IconButton>
        <div>
          <div className="breadcrumb">{meta.eyebrow}</div>
          <div className="top-title">{meta.title}</div>
        </div>
      </div>
      <div className="top-controls">
        <Selector label="Portfolio" value={data.paperPortfolios[0]?.name ?? "Primary paper portfolio"} />
        <Selector label="Period" value="Forward window" />
        <SegmentedControl options={["Executive", "Operations"]} value={view} onChange={setView} />
        <div className="command-search"><Search aria-hidden size={16} /><span>Search or command</span><kbd>⌘K</kbd></div>
      </div>
    </header>
  );
}

function OperatingStatusRail({ model, apiVisible, onControls }: { model: ReturnType<typeof buildModel>; apiVisible: boolean; onControls: () => void }) {
  return (
    <section className="status-rail" aria-label="Operating status">
      <StatusChip tone={toneFor(model.dataSourceState)} label={`Data source: ${model.dataSourceLabel}`} raw={model.dataSourceState} />
      <StatusChip tone="success" label="No real capital" raw="NO_REAL_CAPITAL_DEPLOYED" />
      <StatusChip tone="danger" label="Live execution locked" raw="LIVE_EXECUTION_ENABLED=false" />
      <StatusChip tone="danger" label="Broker access disabled" raw="BROKER_ORDER_ACCESS_DISABLED" />
      <StatusChip tone={model.fixtureDataVisible ? "warning" : apiVisible ? "success" : "warning"} label={model.fixtureDataVisible ? "Fixture data visible" : "API data visible"} raw={model.fixtureDataVisible ? "FIXTURE" : "API_DATA_VISIBLE"} />
      <button className="rail-action" onClick={onControls}>View controls</button>
    </section>
  );
}

function PageHeader({ meta, action, onAction }: { meta: (typeof sectionMeta)[SectionId]; action: string; onAction: () => void }) {
  return (
    <section className="page-header">
      <div>
        <span className="eyebrow">{meta.eyebrow}</span>
        <h2>{meta.title}</h2>
        <p>{meta.subtitle}</p>
      </div>
      <button className="primary-action" onClick={onAction}>{action}</button>
    </section>
  );
}

function renderSection(args: {
  section: SectionId;
  data: DashboardData;
  model: ReturnType<typeof buildModel>;
  failClosed: boolean;
  setFailClosed: (value: boolean) => void;
  paperDay: number;
  setPaperDay: (value: number | ((value: number) => number)) => void;
}) {
  switch (args.section) {
    case "lineage":
      return <LineagePage data={args.data} />;
    case "dataHealth":
      return <DataHealthPage data={args.data} model={args.model} />;
    case "licensing":
      return <LicensingPage data={args.data} />;
    case "features":
      return <FeaturePage />;
    case "universe":
      return <UniversePage data={args.data} />;
    case "research":
      return <ResearchPage data={args.data} model={args.model} />;
    case "risk":
      return <RiskPage model={args.model} failClosed={args.failClosed} />;
    case "drift":
      return <DriftPage failClosed={args.failClosed} />;
    case "corporate":
      return <CorporatePage data={args.data} failClosed={args.failClosed} />;
    case "paper":
      return <PaperPage data={args.data} model={args.model} setFailClosed={args.setFailClosed} setPaperDay={args.setPaperDay} paperDay={args.paperDay} />;
    case "liveReadiness":
      return <LiveReadinessPage />;
    case "complianceSecurity":
      return <CompliancePage />;
    case "liveOps":
      return <LiveOpsPage />;
    case "schema":
      return <SchemaPage data={args.data} />;
    default:
      return <CommandCenter data={args.data} model={args.model} failClosed={args.failClosed} />;
  }
}

function CommandCenter({ data, model, failClosed }: { data: DashboardData; model: ReturnType<typeof buildModel>; failClosed: boolean }) {
  return (
    <>
      <KpiGrid>
        <KpiCard label="Data source" value={model.dataSourceLabel} hint={model.actualDataIngested ? "Actual provider data ingested" : "No verified provider ingestion yet"} trend={model.dataSourceState} tone={toneFor(model.dataSourceState)} />
        <KpiCard label="Dataset freshness" value={uiLabel(model.freshnessStatus)} hint="Freshness is backend-derived" trend={model.lastUpdated} tone={toneFor(model.freshnessStatus)} />
        <KpiCard label="Broker access" value="Disabled" hint="No order placement, holdings, funds, or live execution" trend="Locked" tone="danger" />
        <KpiCard label="Paper data use" value={model.paperTradingUseLiveData ? "Blocked" : "Fixture only"} hint="Actual data does not flow into paper trading" trend="Fail closed" tone={model.paperTradingUseLiveData ? "danger" : "warning"} />
      </KpiGrid>
      <section className="hero-grid">
        <ChartCard title="Portfolio equity curve versus benchmark" subtitle="Paper portfolio index, normalized to 100" note="Source: governed paper and research fixtures">
          <LineChart data={model.equityCurve} />
        </ChartCard>
        <ChartCard title="Capital allocation" subtitle="Cash, equity, reserved, unsettled" note="No real capital deployed">
          <DonutChart data={model.allocation} center="95% cash" />
        </ChartCard>
      </section>
      <section className="analytics-grid three">
        <ChartCard title="Drawdown timeline" subtitle="Current drawdown remains inside policy band">
          <AreaBars values={model.drawdownSeries} labels={["D1", "D2", "D3", "D4", "D5", "D6"]} />
        </ChartCard>
        <ChartCard title="Strategy contribution" subtitle="Attribution before detailed ledger review">
          <ContributionBars data={model.contribution} />
        </ChartCard>
        <ChartCard title="Sector and cash exposure" subtitle="Capital concentration view">
          <HorizontalBars data={model.exposure} suffix="%" />
        </ChartCard>
      </section>
      <OperatingPipeline />
      <section className="analytics-grid two">
        <DecisionQueue data={data} failClosed={failClosed} />
        <EventFeed title="Recent audit events" events={data.audits} />
      </section>
    </>
  );
}

function LineagePage({ data }: { data: DashboardData }) {
  const rows = data.datasets.length ? data.datasets.map((dataset) => [dataset.name, dataset.domain, uiLabel(dataset.status), dataset.criticality, "Versioned evidence"]) : [["EOD prices", "Market data", "Ready", "Critical", "Versioned evidence"]];
  return (
    <>
      <KpiGrid><KpiCard label="Dataset versions" value={String(rows.length)} hint="Governed records visible" tone="success" /><KpiCard label="Critical failures" value="0" hint="RED blocks downstream use" tone="success" /><KpiCard label="Point-in-time checks" value="Pass" hint="Availability timestamps enforced" tone="info" /><KpiCard label="Raw objects" value={String(Math.max(3, data.ingestions.length))} hint="Immutable capture" tone="info" /></KpiGrid>
      <LineageFlow />
      <section className="analytics-grid two">
        <ChartCard title="Validation distribution" subtitle="Dataset readiness composition"><DonutChart center="Ready" data={[{ label: "Ready", value: 82, tone: "success" }, { label: "Caution", value: 18, tone: "warning" }]} /></ChartCard>
        <ChartCard title="Freshness timeline" subtitle="Available time to decision flow"><Timeline items={["Provider fetch", "Raw capture", "Validation", "Dataset version", "Feature availability", "Paper decision"]} /></ChartCard>
      </section>
      <DataTable title="Detailed lineage register" headers={["Dataset", "Domain", "Status", "Criticality", "Lineage"]} rows={rows} />
    </>
  );
}

function DataHealthPage({ data, model }: { data: DashboardData; model: ReturnType<typeof buildModel> }) {
  const healthRows = data.providerHealth.length ? data.providerHealth.map((item) => [item.provider_name, item.healthy ? "Healthy" : "Failed", uiLabel(item.mode), String(item.order_access), `${item.latency_ms ?? 0} ms`, item.message]) : [["Provider setup required", "Not configured", "Read-only data source", "false", "n/a", "No verified provider health check has passed"]];
  const quoteRows = data.liveQuotes.length ? data.liveQuotes.map((quote) => [quote.aegis_instrument_id, quote.exchange, currency(quote.last_price), currency(quote.bid_price), currency(quote.ask_price), compactNumber(quote.volume), shortDate(quote.available_time)]) : [["Live quote feed is not configured", "Historical EOD only", "n/a", "n/a", "n/a", "n/a", "Provider setup required"]];
  return (
    <>
      <KpiGrid><KpiCard label="Provider health" value={model.providerHealthy ? "Healthy" : "Review"} hint="Read-only adapter state" tone={model.providerHealthy ? "success" : "warning"} /><KpiCard label="Data freshness" value={uiLabel(model.freshnessStatus)} hint="Quote availability checked" tone={toneFor(model.freshnessStatus)} /><KpiCard label="Market calendar" value="Open governed" hint="Execution dates controlled by calendar" tone="info" /><KpiCard label="Read-only mode" value="Locked" hint="Broker order access false" tone="success" /></KpiGrid>
      <section className="analytics-grid two">
        <ChartCard title="Provider health matrix" subtitle="Operational state by provider"><HealthMatrix rows={healthRows} /></ChartCard>
        <ChartCard title="Quote latency trend" subtitle="Freshness remains within threshold"><AreaBars values={[12, 10, 14, 9, 13, 11]} labels={["09:15", "10:00", "11:00", "12:00", "13:00", "Now"]} /></ChartCard>
      </section>
      <section className="analytics-grid two">
        <ChartCard title="Data-quality distribution" subtitle="Critical datasets must remain ready"><DonutChart center="Ready" data={[{ label: "Ready", value: 88, tone: "success" }, { label: "Caution", value: 12, tone: "warning" }]} /></ChartCard>
        <ChartCard title="Market-calendar status" subtitle="Exchange sessions govern eligible dates"><Timeline items={(data.marketCalendar.length ? data.marketCalendar : [{ session_date: "2026-06-26", is_open: true }]).map((session) => `${session.session_date} · ${session.is_open ? "Open" : "Closed"}`)} /></ChartCard>
      </section>
      <DataTable title={data.liveQuotes.length ? "Live quote snapshots" : "Live quote feed is not configured. Historical EOD activation remains available."} headers={["Instrument", "Exchange", "Last", "Bid", "Ask", "Volume", "Available"]} rows={quoteRows} />
    </>
  );
}

function LicensingPage({ data }: { data: DashboardData }) {
  const rows = data.providers.length
    ? data.providers.map((provider) => [
        provider.name,
        uiLabel(provider.capabilities?.license_status ?? "NOT_APPROVED"),
        "Research, paper display",
        provider.capabilities?.dashboard_display_rights ? "Allowed" : "Restricted",
        provider.capabilities?.model_training_rights ? "Allowed" : "Restricted",
        "Tracked",
      ])
    : [["mock_market_data", "Not available", "Research, paper display", "Restricted", "Restricted", "Tracked"]];
  const approvedCount = data.providers.filter((provider) => provider.capabilities?.license_status === "APPROVED").length;
  return <VisualEvidencePage kpis={[["Approved providers", String(approvedCount), "Permitted data paths", approvedCount ? "success" : "warning"], ["Live broker rights", "0", "No broker configured", "danger"], ["Display rights", uiLabel(data.providers[0]?.capabilities?.license_status ?? "NOT_APPROVED"), "Dashboard use", data.providers[0]?.capabilities?.dashboard_display_rights ? "success" : "warning"], ["Model training", "Restricted", "Requires rights", "warning"]]} primary={<ChartCard title="Licensing readiness" subtitle="Allowed, restricted, and blocked uses"><ReadinessBars data={[["Allowed use", data.providers.length ? Math.round((approvedCount / data.providers.length) * 100) : 0], ["Restricted use", data.providers.length ? Math.round(((data.providers.length - approvedCount) / data.providers.length) * 100) : 0], ["Blocked use", 0]]} /></ChartCard>} secondary={<DataTable title="Provider permission matrix" headers={["Provider", "Status", "Permitted use", "Display", "Training", "Expiry"]} rows={rows} />} />;
}

function FeaturePage() {
  return <VisualEvidencePage kpis={[["Frozen features", "2", "Manifest locked", "success"], ["Active risk inputs", "1", "Sizing input", "info"], ["Look-ahead breaches", "0", "Timing pass", "success"], ["Feature policy", "Frozen", "No mutation", "success"]]} primary={<ChartCard title="Feature timing pipeline" subtitle="Raw close to decision availability"><Timeline items={["Raw close", "Validation", "Feature run", "Availability stamp", "Manifest freeze", "Decision"]} /></ChartCard>} secondary={<DataTable title="Feature registry" headers={["Feature", "Source", "Availability", "Status"]} rows={featureRows} />} />;
}

function UniversePage({ data }: { data: DashboardData }) {
  const instruments = data.instruments;
  const total = instruments.length;
  const sectorCounts = new Map<string, number>();
  for (const instrument of instruments) {
    const sector = instrument.sector || "Unclassified";
    sectorCounts.set(sector, (sectorCounts.get(sector) ?? 0) + 1);
  }
  const sectorBars = Array.from(sectorCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value }));
  const activeCount = instruments.filter((instrument) => instrument.trading_status === "ACTIVE").length;
  const avgConfidence = total ? Math.round((instruments.reduce((sum, instrument) => sum + instrument.mapping_confidence_score, 0) / total) * 100) : 0;
  const rows = total
    ? [...instruments]
        .sort((a, b) => a.current_symbol.localeCompare(b.current_symbol))
        .map((instrument) => [
          instrument.current_symbol,
          instrument.company_legal_name,
          instrument.sector || "Unclassified",
          instrument.isin,
          instrument.listing_date ?? "Unknown",
          uiLabel(instrument.trading_status),
        ])
    : [["No instruments synced yet", "Run a provider sync to populate the universe", "-", "-", "-", "Not configured"]];
  return (
    <VisualEvidencePage
      kpis={[
        ["Universe size", String(total), "Real NSE-listed instruments tracked", total ? "success" : "warning"],
        ["Sectors covered", String(sectorCounts.size), "Distinct sector classifications", "info"],
        ["Active listings", `${activeCount}/${total}`, "Trading status ACTIVE", total && activeCount === total ? "success" : "warning"],
        ["Mapping confidence", `${avgConfidence}%`, "Average curated-metadata confidence", avgConfidence >= 95 ? "success" : "warning"],
      ]}
      primary={
        <ChartCard title="Sector composition" subtitle="Instrument count by sector, from provider-verified classification">
          <HorizontalBars data={sectorBars.length ? sectorBars : [{ label: "No data", value: 0 }]} />
        </ChartCard>
      }
      secondary={<DataTable title="Instrument register" headers={["Symbol", "Company", "Sector", "ISIN", "Listing date", "Status"]} rows={rows} />}
    />
  );
}

function formatReturn(value: string | number): string {
  // Always a plain fraction from the real momentum backend (never pre-scaled),
  // unlike percent()'s heuristic which misreads returns over 100% (e.g. a real
  // 283% gain as "2.8%") because it can't tell a large fraction from an
  // already-scaled percentage.
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function RealMomentumSection({ data }: { data: DashboardData }) {
  const momentumReports = data.realMomentumReports.filter((report) => report.scenario.includes("Trend-Following"));
  const benchmarkReports = data.realMomentumReports.filter((report) => report.scenario.includes("Equal-Weight Benchmark"));
  const momentum = momentumReports[momentumReports.length - 1];
  const benchmark = benchmarkReports[benchmarkReports.length - 1];

  if (!momentum || !benchmark) {
    return (
      <ChartCard title="Real Nifty 50 momentum backtest" subtitle="First investment thesis, evaluated against real captured data">
        <AlertCard
          tone="info"
          title="No real backtest run yet"
          body="POST /api/v1/research/momentum/run against real captured Kite data to populate this section."
        />
      </ChartCard>
    );
  }

  const momentumBase = Number(momentum.equity_curve[0]?.nav ?? momentum.starting_cash);
  const benchmarkBase = Number(benchmark.equity_curve[0]?.nav ?? benchmark.starting_cash);
  const sampleEvery = Math.max(1, Math.ceil(momentum.equity_curve.length / 24));
  const comparisonSeries = momentum.equity_curve
    .filter((_, index) => index % sampleEvery === 0)
    .map((point, sampledIndex) => {
      const rawIndex = sampledIndex * sampleEvery;
      const benchmarkPoint = benchmark.equity_curve[rawIndex];
      return {
        label: point.date.slice(0, 7),
        portfolio: momentumBase ? (Number(point.nav) / momentumBase) * 100 : 100,
        benchmark: benchmarkPoint && benchmarkBase ? (Number(benchmarkPoint.nav) / benchmarkBase) * 100 : 100,
      };
    });

  const rows = [
    [
      momentum.scenario,
      momentum.strategy_name,
      formatReturn(momentum.total_return),
      formatReturn(momentum.max_drawdown),
      String(momentum.rebalance_count),
      String(momentum.position_count),
      currency(Number(momentum.total_transaction_cost)),
    ],
    [
      benchmark.scenario,
      benchmark.strategy_name,
      formatReturn(benchmark.total_return),
      formatReturn(benchmark.max_drawdown),
      String(benchmark.rebalance_count),
      String(benchmark.position_count),
      currency(Number(benchmark.total_transaction_cost)),
    ],
  ];

  return (
    <>
      <KpiGrid>
        <KpiCard label="Momentum total return" value={formatReturn(momentum.total_return)} hint={`${momentum.start_date} to ${momentum.end_date}, real Kite data`} tone={Number(momentum.total_return) >= 0 ? "success" : "danger"} />
        <KpiCard label="Benchmark total return" value={formatReturn(benchmark.total_return)} hint="Equal-weight, same universe and window" tone="info" />
        <KpiCard label="Momentum max drawdown" value={formatReturn(momentum.max_drawdown)} hint="Platform's own conservative risk profile applied" tone="warning" />
        <KpiCard label="Real universe" value={`${momentum.universe_size} stocks`} hint={`${momentum.bar_count.toLocaleString()} real EOD bars, hash ${momentum.raw_snapshot_hash.slice(0, 10)}…`} tone="success" />
      </KpiGrid>
      <section className="hero-grid single">
        <ChartCard title="Momentum vs. equal-weight benchmark" subtitle="Indexed to 100 at inception, quarterly-sampled from the real equity curve" note="Real Kite-sourced EOD data -- see warnings below for modeling assumptions">
          <LineChart data={comparisonSeries} />
        </ChartCard>
      </section>
      <DataTable
        title="Real Nifty 50 momentum backtest -- ACTUAL_PROVIDER_DATA"
        headers={["Scenario", "Strategy", "Return", "Max drawdown", "Rebalances", "Positions held", "Transaction cost"]}
        rows={rows}
      />
      <ChartCard title="Modeling assumptions and findings" subtitle="Disclosed, not hidden">
        {momentum.warnings.map((warning) => (
          <AlertCard key={warning} tone="info" title={warning} body="" />
        ))}
      </ChartCard>
    </>
  );
}

function ResearchPage({ data, model }: { data: DashboardData; model: ReturnType<typeof buildModel> }) {
  const activation = data.researchActivation ?? {};
  const blockers = Array.isArray(activation.blockers) ? activation.blockers : [];
  const eligible = Array.isArray(activation.eligible_datasets) ? activation.eligible_datasets : [];
  const rows = data.sprint2Reports.length ? data.sprint2Reports.map((report) => [report.scenario, report.total_return, report.gross_equity_exposure, report.total_transaction_cost, "Research only"]) : [["Equal weight benchmark", "0.4%", "5.0%", "₹40", "Research only"]];
  const blockerRows = blockers.length
    ? blockers.map((blocker: Record<string, unknown>) => [uiLabel(blocker.code), String(blocker.label ?? "Blocked"), uiLabel(blocker.severity), String(blocker.remediation ?? "Resolve gate")])
    : [["Historical activation", "Eligible", "Ready", "Dataset can be used for research-only manifests"]];
  const eligibleRows = eligible.length
    ? eligible.map((dataset: Record<string, unknown>) => [String(dataset.dataset_version_id), uiLabel(dataset.validation_status), String(dataset.quality_score), uiLabel(dataset.classification), "Paper/live locked"])
    : [["No eligible dataset", model.researchActivationLabel, "0", "Actual historical research only", "Provider or licensed file required"]];
  return (
    <>
      <RealMomentumSection data={data} />
      <KpiGrid>
        <KpiCard label="Historical activation" value={model.researchActivationLabel} hint="Real data must pass license, lineage, and quality gates" trend={model.researchActivationStatus} tone={toneFor(model.researchActivationStatus)} />
        <KpiCard label="Eligible datasets" value={String(model.researchEligibleDatasetCount)} hint="Only non-fixture raw snapshots qualify" tone={model.researchEligibleDatasetCount > 0 ? "success" : "warning"} />
        <KpiCard label="Research mode" value={uiLabel(activation.research_mode ?? "ACTUAL_HISTORICAL_RESEARCH_ONLY")} hint="No paper or live promotion from this gate" tone="info" />
        <KpiCard label="Safety" value="Paper/live locked" hint="No broker execution, no holdings mutation" tone="success" />
      </KpiGrid>
      <section className="hero-grid single">
        <ChartCard title="Research lifecycle funnel" subtitle="Licensed historical data to frozen experiment manifest">
          <Funnel items={["Licensed data", "Raw immutable capture", "Validation", "Lineage", "Activation", "Frozen manifest"]} />
        </ChartCard>
      </section>
      <section className="analytics-grid two">
        <DataTable title="Historical activation blockers" headers={["Gate", "State", "Severity", "Remediation"]} rows={blockerRows} />
        <DataTable title="Research-eligible datasets" headers={["Dataset version", "Validation", "Quality", "Classification", "Trading use"]} rows={eligibleRows} />
      </section>
      <DataTable title="Fixture demo (Sprint 2) -- not real data" headers={["Scenario", "Return", "Exposure", "Cost drag", "Classification"]} rows={rows} />
    </>
  );
}

function RiskPage({ model, failClosed }: { model: ReturnType<typeof buildModel>; failClosed: boolean }) {
  return <VisualEvidencePage kpis={[["Risk state", failClosed ? "Frozen" : "Normal", "Drawdown state machine", failClosed ? "danger" : "success"], ["Risk budget used", "42%", "Per-position cap", "info"], ["Cash weight", percent(model.cashWeight), "Liquidity retained", "success"], ["Active kill switches", failClosed ? "1" : "0", "Fail-closed control", failClosed ? "danger" : "success"]]} primary={<ChartCard title="Risk budget utilization" subtitle="Budget consumed by active constraints"><RiskMeter value={42} /></ChartCard>} secondary={<><section className="analytics-grid two"><ChartCard title="Requested versus approved size" subtitle="Constraint impact waterfall"><Waterfall data={[["Requested", 100], ["Risk cap", -36], ["Cash reserve", -12], ["Approved", 52]]} /></ChartCard><ChartCard title="Sector exposure" subtitle="Concentration after sizing"><HorizontalBars data={model.exposure} suffix="%" /></ChartCard></section><DataTable title="Risk rule registry" headers={["Entity", "Measure", "Constraint", "Decision"]} rows={[["Portfolio", "Gross exposure", "Max 80%", "Within limit"], ["Instrument", "Gap risk", "Risk cap", "Approved at reduced size"], ["Kill switch", "Global", "Inactive", failClosed ? "Frozen" : "Ready"]]} /></>} />;
}

function DriftPage({ failClosed }: { failClosed: boolean }) {
  return <VisualEvidencePage kpis={[["Recommended action", failClosed ? "Pause and review" : "Continue monitoring", "Based on divergence severity", failClosed ? "danger" : "success"], ["Signal drift", "Within", "Frequency band", "success"], ["Fill drift", "Within", "Slippage band", "success"], ["Action exceptions", failClosed ? "Critical" : "Watch", "Corporate action feed", failClosed ? "danger" : "warning"]]} primary={<ChartCard title="Expected versus observed behavior" subtitle="Paper observations remain within research band"><ComparisonBands /></ChartCard>} secondary={<DataTable title="Drift evidence register" headers={["Metric", "Expected", "Observed", "Severity"]} rows={driftRows} />} />;
}

function CorporatePage({ data, failClosed }: { data: DashboardData; failClosed: boolean }) {
  const rows = data.paperReviews.length ? data.paperReviews.map((review) => [review.action_type, review.instrument_id, review.effective_date, uiLabel(review.support_status), review.decision]) : [["Split", "AEGIS-IN-000001", "2026-06-30", "Supported", "Ledger adjustment allowed"], ["Demerger", "AEGIS-IN-000001", "2026-06-30", "Unsupported", failClosed ? "Freeze portfolio" : "Review required"]];
  return <VisualEvidencePage kpis={[["Coverage", "2 supported", "Split and dividend", "success"], ["Unsupported", String(rows.filter((row) => row.join(" ").includes("Unsupported")).length), "Fail closed", "warning"], ["Ledger impact", "Modeled", "Cash and position paths", "info"], ["Portfolio response", failClosed ? "Frozen" : "Review", "Safety first", failClosed ? "danger" : "warning"]]} primary={<ChartCard title="Corporate-action coverage" subtitle="Supported versus unsupported action model"><DonutChart center="Coverage" data={[{ label: "Supported", value: 70, tone: "success" }, { label: "Review", value: 20, tone: "warning" }, { label: "Unsupported", value: 10, tone: "danger" }]} /></ChartCard>} secondary={<DataTable title="Pending review queue" headers={["Action", "Instrument", "Effective date", "Support", "Ledger decision"]} rows={rows} />} />;
}

function PaperPage({ data, model, setFailClosed, setPaperDay, paperDay }: { data: DashboardData; model: ReturnType<typeof buildModel>; setFailClosed: (value: boolean) => void; setPaperDay: (value: number | ((value: number) => number)) => void; paperDay: number }) {
  const rows = data.paperJobs.length ? data.paperJobs.map((job) => [job.id.slice(0, 10), job.session_date, uiLabel(job.status), String(job.attempts), job.failure_reason ?? "Ready"]) : [["job-forward", "2026-06-26", "Completed", "1", "Intent generated"]];
  return (
    <>
      <div className="guarded-actions"><button onClick={() => setPaperDay((value) => value + 1)}>Advance paper day</button><button className="danger-link" onClick={() => setFailClosed(true)}>Trigger fail-closed review</button><span>Guarded paper-only simulation controls</span></div>
      <VisualEvidencePage kpis={[["Paper status", "Ready", "Forward-only simulation", "success"], ["Current NAV", currency(model.nav + paperDay * 19), "Paper portfolio", "success"], ["Pending approvals", String(model.pendingApprovals), "Human review required", "warning"], ["Reconciliation", "Ready", "NAV matched expected state", "success"]]} primary={<ChartCard title="Paper-trading lifecycle" subtitle="Intent to evidence package"><Funnel items={["Ready", "Decision", "Approval", "Paper fill", "Settlement", "Reconcile", "Evidence"]} /></ChartCard>} secondary={<><section className="analytics-grid two"><ChartCard title="NAV versus benchmark" subtitle="Paper observation line"><LineChart data={model.equityCurve} /></ChartCard><ChartCard title="Order outcome mix" subtitle="Paper orders only"><DonutChart center="Paper" data={[{ label: "Filled", value: 70, tone: "success" }, { label: "Queued", value: 20, tone: "warning" }, { label: "Rejected", value: 10, tone: "danger" }]} /></ChartCard></section><DataTable title="Paper session jobs" headers={["Record", "Session", "Status", "Attempts", "Note"]} rows={rows} /></>} />
    </>
  );
}

function LiveReadinessPage() {
  return <VisualEvidencePage kpis={[["Live status", "Locked", "No broker connection", "danger"], ["Readiness", "11%", "0 of 8 gates passed", "warning"], ["Broker accounts", "0", "No credentials", "success"], ["Pilot scope", "Blocked", "Approval gates incomplete", "danger"]]} primary={<ChartCard title="Eight-gate readiness tracker" subtitle="Live execution remains locked"><GateProgress gates={liveGates} /></ChartCard>} secondary={<section className="analytics-grid two"><AlertCard tone="danger" title="Live execution is locked" body="No broker is connected, no real capital is deployed, and no live order action exists." /><ChartCard title="What must happen next" subtitle="Evidence before pilot consideration"><Timeline items={["Complete legal memo", "Security threat model", "Broker contract review", "Operations tabletop", "Founder and risk approvals"]} /></ChartCard></section>} />;
}

function CompliancePage() {
  return <VisualEvidencePage kpis={[["Control maturity", "Early", "Evidence collection in progress", "warning"], ["Blocking controls", "5", "Live impact", "danger"], ["Secrets posture", "Not ready", "Vault required", "warning"], ["Two-person rule", "Required", "Future live governance", "info"]]} primary={<ChartCard title="Compliance and security coverage" subtitle="Evidence completion by domain"><ReadinessBars data={[["Legal", 20], ["Security", 12], ["Operations", 18], ["Governance", 8]]} /></ChartCard>} secondary={<DataTable title="Control matrix" headers={["Control", "Requirement", "Owner", "Live impact"]} rows={[["CMP-001", "India applicability memo", "Compliance owner", "Blocks live"], ["SEC-001", "Production secrets", "Security owner", "Blocks live"], ["REL-001", "Release approvals", "Engineering owner", "Blocks live"]]} />} />;
}

function LiveOpsPage() {
  return <VisualEvidencePage kpis={[["Execution gateway", "Future only", "No active broker controls", "info"], ["Incidents", "0 active", "Response model ready", "success"], ["Kill switches", "Designed", "Cannot silently fail", "info"], ["Reconciliation", "Required", "Future hard gate", "warning"]]} primary={<ChartCard title="Future live operations architecture" subtitle="Architecture visible, controls inactive"><Pipeline stages={["Strategy", "Risk", "Approval", "Gateway", "Broker adapter", "Acknowledgement", "Reconciliation"]} /></ChartCard>} secondary={<section className="analytics-grid two"><ChartCard title="Incident severity model" subtitle="Response priority"><HorizontalBars data={[{ label: "Critical", value: 0 }, { label: "High", value: 1 }, { label: "Moderate", value: 2 }, { label: "Low", value: 3 }]} /></ChartCard><AlertCard tone="info" title="No active live controls" body="This page explains future operations architecture without adding broker execution capability." /></section>} />;
}

function SchemaPage({ data }: { data: DashboardData }) {
  return <VisualEvidencePage kpis={[["Schema areas", "4 sprints", "Foundation to paper ops", "info"], ["Persistence", "SQLite path", "Local hardening", "info"], ["Audit", "Append-only", "Correlation IDs", "success"], ["API records", String(data.audits.length), "Visible events", "info"]]} primary={<ChartCard title="Data architecture map" subtitle="Provider to audit evidence"><LineageFlow compact /></ChartCard>} secondary={<DataTable title="Schema and evidence boundaries" headers={["Boundary", "Source", "Destination", "Failure mode"]} rows={[["Provider adapter", "Raw payload", "Object store", "License incident"], ["Validation", "Raw object", "Dataset version", "RED blocks usage"], ["Paper queue", "Session job", "Intent", "Job failed"], ["Audit", "State change", "Append-only event", "Evidence retained"]]} />} />;
}

function VisualEvidencePage({ kpis, primary, secondary }: { kpis: Array<[string, string, string, string]>; primary: ReactNode; secondary: ReactNode }) {
  return (
    <>
      <KpiGrid>{kpis.map(([label, value, hint, tone]) => <KpiCard key={label} label={label} value={value} hint={hint} tone={tone as Tone} />)}</KpiGrid>
      <section className="hero-grid single">{primary}</section>
      {secondary}
    </>
  );
}

function KpiGrid({ children }: { children: ReactNode }) {
  return <section className="kpi-grid">{children}</section>;
}

function KpiCard({ label, value, hint, trend, tone = "neutral" }: { label: string; value: string; hint: string; trend?: string; tone?: Tone }) {
  return (
    <article className={`kpi-card tone-${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-hint">{hint}</div>
      {trend && <div className="kpi-trend">{trend}</div>}
    </article>
  );
}

function ChartCard({ title, subtitle, note, children }: { title: string; subtitle: string; note?: string; children: ReactNode }) {
  return (
    <section className="chart-card">
      <div className="chart-head"><div><h3>{title}</h3><p>{subtitle}</p></div><Sparkles size={16} aria-hidden /></div>
      <div className="chart-body">{children}</div>
      {note && <div className="chart-note">{note}</div>}
    </section>
  );
}

function StatusChip({ label, raw, tone }: { label: string; raw: string; tone: Tone }) {
  return <span className={`status-chip tone-${tone}`} title={raw}><span className="status-dot" />{label}</span>;
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return <button aria-label={label} className="icon-button" onClick={onClick}>{children}</button>;
}

function Selector({ label, value }: { label: string; value: string }) {
  return <button className="selector"><span>{label}</span><strong>{value}</strong></button>;
}

function SegmentedControl({ options, value, onChange }: { options: string[]; value: string; onChange: (value: string) => void }) {
  return <div className="segmented">{options.map((option) => <button key={option} className={value === option ? "is-active" : ""} onClick={() => onChange(option)}>{option}</button>)}</div>;
}

function LineChart({ data }: { data: Array<{ label: string; portfolio: number; benchmark: number }> }) {
  const max = Math.max(...data.map((item) => Math.max(item.portfolio, item.benchmark)));
  const min = Math.min(...data.map((item) => Math.min(item.portfolio, item.benchmark)));
  return <div className="line-chart" role="img" aria-label="Portfolio and benchmark line chart">{data.map((item) => <div className="line-col" key={item.label}><span className="bar portfolio" style={{ height: `${35 + ((item.portfolio - min) / Math.max(1, max - min)) * 60}%` }} /><span className="bar benchmark" style={{ height: `${35 + ((item.benchmark - min) / Math.max(1, max - min)) * 60}%` }} /><em>{item.label}</em></div>)}<Legend items={["Portfolio", "Benchmark"]} /></div>;
}

function DonutChart({ data, center }: { data: Array<{ label: string; value: number; tone: Tone }>; center: string }) {
  const stops = data.reduce<{ total: number; parts: string[] }>((acc, item) => {
    const start = acc.total;
    const end = acc.total + item.value;
    acc.parts.push(`var(--tone-${item.tone}) ${start}% ${end}%`);
    acc.total = end;
    return acc;
  }, { total: 0, parts: [] });
  return <div className="donut-wrap"><div className="donut" style={{ background: `conic-gradient(${stops.parts.join(", ")})` }}><span>{center}</span></div><div className="donut-legend">{data.map((item) => <StatusChip key={item.label} label={`${item.label} ${item.value}%`} raw={item.label} tone={item.tone} />)}</div></div>;
}

function HorizontalBars({ data, suffix = "" }: { data: Array<{ label: string; value: number }>; suffix?: string }) {
  const max = Math.max(...data.map((item) => Math.abs(item.value)), 1);
  return <div className="h-bars">{data.map((item) => <div className="h-bar-row" key={item.label}><span>{item.label}</span><div><b style={{ width: `${(Math.abs(item.value) / max) * 100}%` }} /></div><strong>{item.value}{suffix}</strong></div>)}</div>;
}

function ContributionBars({ data }: { data: Array<{ label: string; value: number }> }) {
  return <div className="h-bars">{data.map((item) => <div className="h-bar-row" key={item.label}><span>{item.label}</span><div><b className={item.value < 0 ? "negative" : ""} style={{ width: `${Math.min(100, Math.abs(item.value) * 180)}%` }} /></div><strong>{item.value > 0 ? "+" : ""}{item.value.toFixed(2)}%</strong></div>)}</div>;
}

function AreaBars({ values, labels }: { values: number[]; labels: string[] }) {
  const max = Math.max(...values.map((v) => Math.abs(v)), 1);
  return <div className="area-bars">{values.map((value, index) => <div className="area-bar" key={labels[index]}><b className={value < 0 ? "negative" : ""} style={{ height: `${18 + (Math.abs(value) / max) * 70}%` }} /><span>{labels[index]}</span></div>)}</div>;
}

function Timeline({ items }: { items: string[] }) {
  return <ol className="timeline">{items.map((item, index) => <li key={item}><span>{index + 1}</span><p>{item}</p></li>)}</ol>;
}

function Funnel({ items }: { items: string[] }) {
  return <div className="funnel">{items.map((item, index) => <div style={{ width: `${100 - index * 7}%` }} key={item}>{item}</div>)}</div>;
}

function RiskMeter({ value }: { value: number }) {
  return <div className="risk-meter"><div className="meter-track"><b style={{ width: `${value}%` }} /></div><strong>{value}% used</strong><p>Budget remains inside conservative policy.</p></div>;
}

function ReadinessBars({ data }: { data: Array<[string, number]> }) {
  return <HorizontalBars data={data.map(([label, value]) => ({ label, value }))} suffix="%" />;
}

function Waterfall({ data }: { data: Array<[string, number]> }) {
  return <div className="waterfall">{data.map(([label, value]) => <div key={label} className={value < 0 ? "is-negative" : ""}><b style={{ height: `${Math.max(18, Math.abs(value))}%` }} /><span>{label}</span><strong>{value}</strong></div>)}</div>;
}

function ComparisonBands() {
  return <div className="comparison-band"><div className="band safe"><span>Expected band</span></div><div className="observed" style={{ left: "58%" }}>Observed</div></div>;
}

function GateProgress({ gates }: { gates: Array<[string, number, string]> }) {
  return <div className="gate-grid">{gates.map(([gate, value, status]) => <div className="gate" key={gate}><div><strong>{gate}</strong><StatusChip label={status} raw={status} tone={toneFor(status)} /></div><div className="meter-track"><b style={{ width: `${value}%` }} /></div></div>)}</div>;
}

function HealthMatrix({ rows }: { rows: string[][] }) {
  return <div className="health-matrix">{rows.map((row) => <div key={row.join("-")}><StatusChip label={row[1]} raw={row[1]} tone={toneFor(row[1])} /><strong>{row[0]}</strong><span>{row[2]} · order access {row[3]}</span><em>{row[4]}</em></div>)}</div>;
}

function Pipeline({ stages }: { stages: string[] }) {
  return <div className="pipeline">{stages.map((stage, index) => <div className="pipeline-stage" key={stage}><CheckCircle2 size={18} /><strong>{stage}</strong>{index < stages.length - 1 && <ArrowRight size={14} />}</div>)}</div>;
}

function OperatingPipeline() {
  return <ChartCard title="Data activation flow" subtitle="Provider data is blocked from paper trading until a later explicit activation"><Pipeline stages={["Provider setup", "Raw capture", "Validation", "Curated dataset", "Research eligibility"]} /></ChartCard>;
}

function LineageFlow({ compact = false }: { compact?: boolean }) {
  return <ChartCard title={compact ? "Schema relationship flow" : "Lineage flow map"} subtitle="Provider to decision dependency path"><Pipeline stages={["Provider", "Raw object", "Validation", "Dataset version", "Feature run", "Experiment", "Paper decision"]} /></ChartCard>;
}

function DecisionQueue({ data, failClosed }: { data: DashboardData; failClosed: boolean }) {
  const items = [
    failClosed ? "Fail-closed review is active" : "No critical fail-closed review active",
    `${data.paperIntents.length} paper trade intents visible`,
    `${data.paperIncidents.length} open paper incident records`,
    `${data.dataFreshness.length ? uiLabel(data.dataFreshness[0].status) : "Provider setup required"} data freshness state`,
  ];
  return <ChartCard title="Priority decision queue" subtitle="What needs operator attention">{items.map((item) => <AlertCard key={item} tone={item.includes("critical") || item.includes("Fail") ? "danger" : "info"} title={item} body="Open the relevant section for evidence and next action." />)}</ChartCard>;
}

function EventFeed({ title, events }: { title: string; events: Array<{ id: string; event_type: string; created_at: string; action: string }> }) {
  const rows = events.length ? events.slice(0, 5).map((event) => [shortDate(event.created_at), uiLabel(event.event_type), uiLabel(event.action)]) : [["Now", "Append-only audit", "Evidence retained"]];
  return <DataTable title={title} headers={["Time", "Event", "Action"]} rows={rows} />;
}

function AlertCard({ title, body, tone }: { title: string; body: string; tone: Tone }) {
  const Icon = tone === "danger" ? AlertTriangle : tone === "success" ? CheckCircle2 : Clock3;
  return <div className={`alert-card tone-${tone}`}><Icon size={18} /><div><strong>{title}</strong><p>{body}</p></div></div>;
}

function DataTable({ title, headers, rows }: { title: string; headers: string[]; rows: string[][] }) {
  const [query, setQuery] = useState("");
  const filtered = rows.filter((row) => row.join(" ").toLowerCase().includes(query.toLowerCase()));
  return (
    <section className="table-card">
      <div className="table-toolbar"><div><h3>{title}</h3><p>Detailed evidence register</p></div><label><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter records" /></label><button>Columns</button><button>Export</button></div>
      <div className="table-scroll"><table><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{(filtered.length ? filtered : [["No matching rows", ...headers.slice(1).map(() => "")]]).map((row, index) => <tr key={`${row.join("-")}-${index}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{cellIndex > 0 && toneFor(cell) !== "neutral" ? <StatusChip label={uiLabel(cell)} raw={cell} tone={toneFor(cell)} /> : cell}</td>)}</tr>)}</tbody></table></div>
    </section>
  );
}

function Legend({ items }: { items: string[] }) {
  return <div className="legend">{items.map((item) => <span key={item}><i />{item}</span>)}</div>;
}

function DetailDrawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return <aside className="detail-drawer" aria-label={title}><div className="drawer-head"><h3>{title}</h3><IconButton label="Close drawer" onClick={onClose}><X /></IconButton></div>{children}</aside>;
}

function OperatingControls() {
  return <div className="drawer-stack">{technicalControls.map(([key, value]) => <div className="tech-row" key={key}><code>{key}</code><StatusChip label={uiLabel(value)} raw={`${key}=${value}`} tone={toneFor(value)} /></div>)}<AlertCard tone="danger" title="No live execution capability" body="The frontend exposes no buy, sell, broker connect, or live order controls." /></div>;
}

function AuditEvidence({ data }: { data: DashboardData }) {
  return <div className="drawer-stack"><p className="drawer-copy">Canonical technical values remain available in audit and developer views.</p><EventFeed title="Audit trail" events={data.audits} /></div>;
}
