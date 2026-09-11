"use client";

import Link from "next/link";
import {
  Compass,
  Wallet,
  Layers,
  ClipboardCheck,
  Trophy,
  Zap,
  TrendingUp,
  Award,
  IndianRupee,
} from "lucide-react";
import { useEffect, useState } from "react";
import { apiGet } from "../api-client";
import CockpitShell from "../cockpit-shell";
import { KpiCard, KpiStrip } from "../kpi-strip";
import { AchievementGrid, type Achievement } from "../achievement-badge";
import { money } from "../money";
import { fetchCombinedReturn, signedPct, type CombinedReturn } from "../portfolio-return";
import { Skeleton } from "../skeleton";
import { shortName } from "../strategy-name";

type Portfolio = {
  paper_portfolio_id: string;
  name: string;
  status: string;
  starting_capital: string;
};

type Intent = {
  paper_trade_intent_id: string;
  intent_status: string;
  eligible_execution_time: string;
  side: "BUY" | "SELL";
  instrument_id: string;
};

type LeaderboardRow = { strategy_id: string; return_to_drawdown_ratio: string | null };

type SignalRow = { symbol: string; signal: string; close: string; momentum_60: string | null };
type SignalsResponse = { signals: SignalRow[] };
type AchievementsResponse = { achievements: Achievement[] };
type Instrument = { aegis_instrument_id: string; current_symbol: string };

function Overview() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [intents, setIntents] = useState<Intent[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [achievements, setAchievements] = useState<Achievement[] | null>(null);
  const [topSignals, setTopSignals] = useState<SignalRow[]>([]);
  const [combined, setCombined] = useState<CombinedReturn | null>(null);

  useEffect(() => {
    apiGet<Portfolio[]>("/api/v1/paper-portfolios", []).then((data) => {
      setPortfolios(data);
      fetchCombinedReturn(data).then(setCombined);
    });
    apiGet<Intent[]>("/api/v1/paper-trade-intents", []).then(setIntents);
    apiGet<Instrument[]>("/api/v1/instruments", []).then(setInstruments);
    apiGet<LeaderboardRow[]>("/api/v1/strategies/leaderboard", []).then(setLeaderboard);
    apiGet<AchievementsResponse | null>("/api/v1/achievements", null).then((result) =>
      setAchievements(result?.achievements ?? []),
    );
    apiGet<SignalsResponse | null>("/api/v1/signals", null).then((result) => {
      const buys = (result?.signals ?? [])
        .filter((row) => row.signal === "BUY")
        .sort((a, b) => Number(b.momentum_60 ?? 0) - Number(a.momentum_60 ?? 0))
        .slice(0, 5);
      setTopSignals(buys);
    });
  }, []);

  const symbolFor = (id: string) =>
    instruments.find((instrument) => instrument.aegis_instrument_id === id)?.current_symbol ?? id;

  const activePortfolios = portfolios.filter((portfolio) => portfolio.status === "ACTIVE");
  const totalAum = portfolios.reduce(
    (sum, portfolio) => sum + Number(portfolio.starting_capital),
    0,
  );
  const pending = intents.filter((intent) => intent.intent_status === "PENDING_APPROVAL");
  const overdue = pending.filter(
    (intent) => new Date(intent.eligible_execution_time) <= new Date(),
  );
  const ranked = leaderboard.filter((row) => row.return_to_drawdown_ratio !== null);
  const bestRatio = ranked.length > 0 ? Number(ranked[0].return_to_drawdown_ratio) : null;
  const achievedCount = achievements?.filter((achievement) => achievement.achieved).length ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="leaderboard-title">
            <Compass size={20} /> Overview
          </h1>
          <p className="hint">
            Real portfolio health, top signals, and earned milestones — one glance.
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
          <Link href="/live-readiness" className="hint">
            Live readiness evidence →
          </Link>
          <Link href="/operations" className="hint">
            Kill switches &amp; incidents →
          </Link>
        </div>
      </div>

      <KpiStrip>
        <KpiCard
          icon={IndianRupee}
          label="Total AUM"
          value={
            combined && combined.countWithNav > 0
              ? money(combined.combinedNav, { compact: true })
              : "n/a"
          }
          delta={
            combined && combined.returnPct !== null
              ? { text: signedPct(combined.returnPct), tone: combined.returnPct >= 0 ? "pos" : "neg" }
              : null
          }
          caption={combined ? `current NAV across ${combined.countWithNav} portfolios` : undefined}
        />
        <KpiCard
          icon={Wallet}
          label="Starting capital"
          value={money(totalAum, { compact: true })}
          caption={`across ${portfolios.length} real paper portfolios`}
        />
        <KpiCard
          icon={Layers}
          label="Active portfolios"
          value={String(activePortfolios.length)}
          caption={`of ${portfolios.length} total`}
        />
        <KpiCard
          icon={ClipboardCheck}
          label="Pending approvals"
          value={String(pending.length)}
          delta={overdue.length > 0 ? { text: `${overdue.length} overdue`, tone: "neg" } : null}
        />
        <KpiCard
          icon={Trophy}
          label="Best strategy ratio"
          value={bestRatio !== null ? `${bestRatio.toFixed(2)}x` : "n/a"}
          caption={ranked.length > 0 ? shortName(ranked[0].strategy_id) : "no backtest yet"}
        />
      </KpiStrip>

      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head">
          <h2>
            <Award size={15} />
            Achievements ({achievedCount}/{achievements?.length ?? 0})
          </h2>
        </div>
        <div className="panel-body">
          {achievements === null ? (
            <div className="achievement-grid">
              <Skeleton height={62} radius={12} />
              <Skeleton height={62} radius={12} />
              <Skeleton height={62} radius={12} />
            </div>
          ) : achievedCount === 0 ? (
            <p className="hint">
              No real milestones earned yet — run a backtest, approve a real trade, or let a
              portfolio ride out a drawdown to start earning these.
            </p>
          ) : (
            <>
              {/* Overview is a one-glance HUD -- only real, earned milestones are worth a
                  card here. The full achieved/locked breakdown (including every "no data
                  yet" placeholder per portfolio) stays available via a direct call to
                  GET /api/v1/achievements for anyone who wants the complete picture. */}
              <AchievementGrid achievements={achievements.filter((a) => a.achieved)} />
              {achievements.length - achievedCount > 0 && (
                <p className="hint">
                  {achievements.length - achievedCount} more real milestones not reached yet.
                </p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className={`panel-head ${overdue.length > 0 ? "alert" : ""}`}>
            <h2>
              <Zap size={15} />
              Needs attention
            </h2>
          </div>
          <div className="panel-body">
            {overdue.length === 0 ? (
              <p className="hint">No approvals are overdue right now.</p>
            ) : (
              <ul className="reasoning">
                {overdue.map((intent) => (
                  <li key={intent.paper_trade_intent_id}>
                    <span className="k">
                      {intent.side} {symbolFor(intent.instrument_id)}
                    </span>
                    <span className="v">
                      due {new Date(intent.eligible_execution_time).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="hint">
              <Link href="/portfolio">Review in Portfolio &amp; Approvals →</Link>
            </p>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>
              <TrendingUp size={15} />
              Top real signals
            </h2>
          </div>
          <div className="panel-body">
            {topSignals.length === 0 ? (
              <p className="hint">No BUY-eligible instruments right now.</p>
            ) : (
              <ul className="reasoning">
                {topSignals.map((row) => (
                  <li key={row.symbol}>
                    <span className="k">
                      <Link href={`/instruments/${row.symbol}`}>{row.symbol}</Link>
                    </span>
                    <span className="v pos">
                      {(Number(row.momentum_60) * 100).toFixed(1)}% momentum
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="hint">
              <Link href="/actionables">See full Actionables Feed →</Link>
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

export default function OverviewPage() {
  return (
    <CockpitShell>
      <Overview />
    </CockpitShell>
  );
}
