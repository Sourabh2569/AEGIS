from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from aegis.backtesting.accounting import drawdown, high_water_mark
from aegis.feature_engine.engine import atr, price_to_ma_distance, rolling_return, sma
from aegis.portfolio.sprint2 import (
    CostModel,
    CostSchedule,
    FixedBpsSlippageModelV0,
    ResearchPortfolio,
)
from aegis.research_registry.sprint2 import RESEARCH_LABELS
from aegis.risk.engine import PositionSizingEngine, RiskProfileVersion
from aegis.shared.money import money, quantity
from aegis.strategies.baselines import Candidate, StrategyContract

# Transaction-cost assumption used for this research runner -- matches the
# bps rates already used by the platform's sprint-2 research fixture (5bps
# brokerage + 2bps other, each side). This is a documented modeling
# assumption, not a broker-reported rate, same as every backtest here.
REAL_COST_SCHEDULE = CostSchedule(
    version="AEGIS_RESEARCH_COST_ASSUMPTION_V0",
    brokerage_bps_buy=Decimal(5),
    brokerage_bps_sell=Decimal(5),
    other_bps_buy=Decimal(2),
    other_bps_sell=Decimal(2),
    verification_status="APPROVED_FIXTURE",
)
SLIPPAGE_MODEL = FixedBpsSlippageModelV0(buy_slippage_bps=Decimal(5), sell_slippage_bps=Decimal(5))
STARTING_CASH = Decimal(1_000_000)
MINIMUM_HISTORY_DAYS = 200


@dataclass(frozen=True)
class RealBarCapture:
    bars_by_instrument: dict[str, list[dict[str, Any]]]
    source_file: str
    raw_snapshot_hash: str
    bar_count: int
    instrument_count: int
    start_date: date
    end_date: date


def load_real_eod_bars(object_store_root: Path) -> RealBarCapture | None:
    """Loads the fullest real historical EOD capture from the durable object
    store -- the platform's own immutable raw-evidence layer -- rather than
    the ephemeral in-memory repository, which only keeps the latest bar per
    instrument and resets on restart. Returns None if nothing has been
    captured yet (fresh clone, CI, before any provider sync)."""
    raw_root = object_store_root / "raw"
    if not raw_root.exists():
        return None
    best: tuple[int, Path, list[dict[str, Any]]] | None = None
    for path in sorted(raw_root.glob("*/fetch_historical_eod_bars/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list) or not payload:
            continue
        if best is None or len(payload) > best[0]:
            best = (len(payload), path, payload)
    if best is None:
        return None
    _, path, payload = best
    by_instrument: dict[str, list[dict[str, Any]]] = {}
    for bar in payload:
        by_instrument.setdefault(bar["aegis_instrument_id"], []).append(bar)
    for bars in by_instrument.values():
        bars.sort(key=lambda b: b["trade_date"])
    all_dates = sorted({bar["trade_date"] for bar in payload})
    return RealBarCapture(
        bars_by_instrument=by_instrument,
        source_file=str(path),
        raw_snapshot_hash=path.stem,
        bar_count=len(payload),
        instrument_count=len(by_instrument),
        start_date=date.fromisoformat(all_dates[0]),
        end_date=date.fromisoformat(all_dates[-1]),
    )


@dataclass(frozen=True)
class RealMomentumReport:
    scenario: str
    strategy_name: str
    classification: tuple[str, ...]
    dataset_origin: str
    start_date: str
    end_date: str
    starting_cash: Decimal
    ending_nav: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    rebalance_count: int
    position_count: int
    total_transaction_cost: Decimal
    universe_size: int
    bar_count: int
    raw_snapshot_hash: str
    equity_curve: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RealMomentumResearchRunner:
    """Runs a real strategy against the real captured Nifty 50 EOD history:
    monthly rebalance, decisions from real close prices with a one real
    trading day execution lag (no intraday data exists to do better), real
    transaction costs/slippage, and the platform's own conservative risk caps
    (PositionSizingEngine / RiskProfileVersion) rather than ad hoc limits."""

    def __init__(self, capture: RealBarCapture, sector_by_instrument: dict[str, str]) -> None:
        self.capture = capture
        self.sector_by_instrument = sector_by_instrument
        self.profile = RiskProfileVersion()
        self.risk_engine = PositionSizingEngine()
        self.cost_model = CostModel()
        self._dates_by_instrument: dict[str, list[date]] = {
            instrument_id: [date.fromisoformat(bar["trade_date"]) for bar in bars]
            for instrument_id, bars in capture.bars_by_instrument.items()
        }
        self._close_by_date: dict[str, dict[str, Decimal]] = {
            instrument_id: {bar["trade_date"]: Decimal(str(bar["close"])) for bar in bars}
            for instrument_id, bars in capture.bars_by_instrument.items()
        }
        self._all_dates: list[date] = sorted(
            {
                date.fromisoformat(bar["trade_date"])
                for bars in capture.bars_by_instrument.values()
                for bar in bars
            }
        )

    def run(self, strategy: StrategyContract, scenario_name: str) -> RealMomentumReport:
        portfolio = ResearchPortfolio(
            portfolio_id=f"real-momentum-{scenario_name}", cash=money(STARTING_CASH)
        )
        rebalance_dates = self._rebalance_dates()
        equity_curve: list[dict[str, str]] = []
        hwm = money(STARTING_CASH)
        worst_drawdown = Decimal(0)
        rebalance_count = 0
        warnings = [
            "Historical simulation does not guarantee future results.",
            (
                "Orders fill at the next real trading day's close after the decision date; "
                "no intraday price data is used."
            ),
            (
                "Uses the platform's existing conservative risk profile (RiskProfileVersion): "
                "new-position sizing is set to zero once drawdown from the running high-water-mark "
                "reaches -8% (CAPITAL_PRESERVATION) or -10% (FROZEN). A portfolio that is fully in "
                "cash cannot make a new high on its own, so this can persist for an extended period "
                "once triggered -- a real, first-observed interaction, since prior fixture scenarios "
                "always passed a hardcoded zero drawdown into this risk engine."
            ),
        ]

        for decision_date in rebalance_dates:
            idx = bisect.bisect_right(self._all_dates, decision_date)
            if idx >= len(self._all_dates):
                break
            execution_date = self._all_dates[idx]
            portfolio.settle_due(execution_date)

            candidates = self._build_candidates(decision_date)
            if not candidates:
                continue
            ranked = strategy.rank_candidates(candidates)
            targets = strategy.propose_target_weights(ranked, self.profile.maximum_position_count)
            rebalance_count += 1

            portfolio_nav = self._mark_to_market(portfolio, execution_date)
            if portfolio_nav <= 0:
                continue
            # Drawdown relative to the *current* high-water-mark, as of just
            # before this cycle's trades -- this recovers as NAV makes new
            # highs. Using the all-time worst drawdown instead would
            # permanently freeze the risk engine's sizing after a single
            # >=10% dip, even once the portfolio has since recovered.
            live_drawdown = drawdown(portfolio_nav, hwm)
            sector_values, cluster_values = self._exposure_values(portfolio, execution_date)
            gross_equity_value = money(
                portfolio_nav - portfolio.cash - portfolio.unsettled_receivables
            )
            by_id = {candidate.instrument_id: candidate for candidate in candidates}

            self._sell_down(portfolio, targets, by_id, portfolio_nav, execution_date)

            for candidate in ranked:
                self._maybe_buy(
                    strategy=strategy,
                    portfolio=portfolio,
                    candidate=candidate,
                    target_weight=targets.get(candidate.instrument_id, Decimal(0)),
                    portfolio_nav=portfolio_nav,
                    sector_values=sector_values,
                    cluster_values=cluster_values,
                    gross_equity_value=gross_equity_value,
                    execution_date=execution_date,
                    current_drawdown=live_drawdown,
                )

            current_nav = self._mark_to_market(portfolio, execution_date)
            hwm = high_water_mark(hwm, current_nav)
            worst_drawdown = min(worst_drawdown, drawdown(current_nav, hwm))
            equity_curve.append({"date": execution_date.isoformat(), "nav": str(current_nav)})

        ending_nav = (
            money(Decimal(equity_curve[-1]["nav"])) if equity_curve else money(STARTING_CASH)
        )
        position_count = len([qty for qty in portfolio.positions.values() if qty > 0])
        return RealMomentumReport(
            scenario=scenario_name,
            strategy_name=strategy.strategy_name,
            classification=RESEARCH_LABELS,
            dataset_origin="ACTUAL_PROVIDER_DATA",
            start_date=self.capture.start_date.isoformat(),
            end_date=self.capture.end_date.isoformat(),
            starting_cash=money(STARTING_CASH),
            ending_nav=ending_nav,
            total_return=money((ending_nav - STARTING_CASH) / STARTING_CASH),
            max_drawdown=money(worst_drawdown),
            rebalance_count=rebalance_count,
            position_count=position_count,
            total_transaction_cost=portfolio.total_costs,
            universe_size=self.capture.instrument_count,
            bar_count=self.capture.bar_count,
            raw_snapshot_hash=self.capture.raw_snapshot_hash,
            equity_curve=equity_curve,
            warnings=warnings,
        )

    def _rebalance_dates(self) -> list[date]:
        seen: set[tuple[int, int]] = set()
        result: list[date] = []
        for current in self._all_dates:
            key = (current.year, current.month)
            if key not in seen:
                seen.add(key)
                result.append(current)
        return result

    def _build_candidates(self, as_of: date) -> list[Candidate]:
        candidates: list[Candidate] = []
        for instrument_id, bar_dates in self._dates_by_instrument.items():
            idx = bisect.bisect_right(bar_dates, as_of)
            if idx < MINIMUM_HISTORY_DAYS:
                continue
            bars = self.capture.bars_by_instrument[instrument_id][:idx]
            closes = [Decimal(str(bar["close"])) for bar in bars]
            highs = [Decimal(str(bar["high"])) for bar in bars]
            lows = [Decimal(str(bar["low"])) for bar in bars]
            volumes = [Decimal(str(bar["volume"])) for bar in bars]
            sma_50 = sma(closes, 50)
            sma_200 = sma(closes, 200)
            momentum_60 = rolling_return(closes[-61:]) if len(closes) >= 61 else None
            atr_14 = atr(highs, lows, closes, 14)
            adv_20 = sma([close * volume for close, volume in zip(closes, volumes)], 20)
            sector = self.sector_by_instrument.get(instrument_id, "UNKNOWN")
            candidates.append(
                Candidate(
                    instrument_id=instrument_id,
                    sector=sector,
                    cluster=sector,
                    close=closes[-1],
                    momentum_60=momentum_60,
                    price_to_sma_200=price_to_ma_distance(closes[-1], sma_200),
                    sma_50=sma_50,
                    sma_200=sma_200,
                    atr_14=atr_14,
                    average_daily_value_traded_20=adv_20,
                )
            )
        return candidates

    def _exact_close(self, instrument_id: str, on: date) -> Decimal | None:
        return self._close_by_date.get(instrument_id, {}).get(on.isoformat())

    def _close_on_or_before(self, instrument_id: str, as_of: date) -> Decimal | None:
        bar_dates = self._dates_by_instrument.get(instrument_id, [])
        idx = bisect.bisect_right(bar_dates, as_of)
        if idx == 0:
            return None
        return self._close_by_date[instrument_id][bar_dates[idx - 1].isoformat()]

    def _mark_to_market(self, portfolio: ResearchPortfolio, as_of: date) -> Decimal:
        market_value = Decimal(0)
        for instrument_id, qty in portfolio.positions.items():
            if qty <= 0:
                continue
            price = self._close_on_or_before(instrument_id, as_of)
            if price is None:
                continue
            market_value += qty * price
        return money(portfolio.cash + portfolio.unsettled_receivables + market_value)

    def _exposure_values(
        self, portfolio: ResearchPortfolio, as_of: date
    ) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
        sector_values: dict[str, Decimal] = {}
        cluster_values: dict[str, Decimal] = {}
        for instrument_id, qty in portfolio.positions.items():
            if qty <= 0:
                continue
            price = self._close_on_or_before(instrument_id, as_of)
            if price is None:
                continue
            notional = money(qty * price)
            sector = self.sector_by_instrument.get(instrument_id, "UNKNOWN")
            sector_values[sector] = money(sector_values.get(sector, Decimal(0)) + notional)
            cluster_values[sector] = money(cluster_values.get(sector, Decimal(0)) + notional)
        return sector_values, cluster_values

    def _sell_down(
        self,
        portfolio: ResearchPortfolio,
        targets: dict[str, Decimal],
        by_id: dict[str, Candidate],
        portfolio_nav: Decimal,
        execution_date: date,
    ) -> None:
        for instrument_id, held_qty in list(portfolio.positions.items()):
            if held_qty <= 0:
                continue
            price = self._exact_close(instrument_id, execution_date)
            if price is None:
                continue
            target_weight = targets.get(instrument_id, Decimal(0))
            target_qty = (
                quantity(money(portfolio_nav * target_weight) / price) if price > 0 else Decimal(0)
            )
            if target_qty >= held_qty:
                continue
            sell_qty = quantity(held_qty - target_qty)
            if sell_qty <= 0:
                continue
            fill_price = SLIPPAGE_MODEL.fill_price(price, "SELL")
            notional = money(sell_qty * fill_price)
            costs = self.cost_model.calculate(notional, "SELL", REAL_COST_SCHEDULE)
            portfolio.sell_t_plus_1(
                instrument_id,
                sell_qty,
                fill_price,
                costs.total_cost,
                execution_date + timedelta(days=1),
            )

    def _maybe_buy(
        self,
        *,
        strategy: StrategyContract,
        portfolio: ResearchPortfolio,
        candidate: Candidate,
        target_weight: Decimal,
        portfolio_nav: Decimal,
        sector_values: dict[str, Decimal],
        cluster_values: dict[str, Decimal],
        gross_equity_value: Decimal,
        execution_date: date,
        current_drawdown: Decimal,
    ) -> None:
        if target_weight <= 0:
            return
        price = self._exact_close(candidate.instrument_id, execution_date)
        if price is None:
            return
        held_qty = portfolio.positions.get(candidate.instrument_id, Decimal(0))
        target_qty = quantity(money(portfolio_nav * target_weight) / price)
        buy_qty = quantity(target_qty - held_qty)
        if buy_qty <= 0:
            return
        if hasattr(strategy, "invalidation_price"):
            invalidation_price = strategy.invalidation_price(candidate)
        else:
            invalidation_price = money(price * Decimal("0.90"))
        assessment = self.risk_engine.assess(
            portfolio_id=portfolio.portfolio_id,
            strategy_id=strategy.strategy_name,
            instrument_id=candidate.instrument_id,
            portfolio_nav=portfolio_nav,
            available_cash=portfolio.available_cash(),
            existing_position_value=money(held_qty * price),
            sector_value=sector_values.get(candidate.sector, Decimal(0)),
            cluster_value=cluster_values.get(candidate.cluster, Decimal(0)),
            gross_equity_value=gross_equity_value,
            entry_price=price,
            invalidation_price=invalidation_price,
            proposed_quantity=buy_qty,
            sector=candidate.sector,
            cluster=candidate.cluster,
            data_quality_status="GREEN",
            instrument_eligibility_status="ELIGIBLE",
            profile=self.profile,
            current_drawdown=current_drawdown,
        )
        if assessment.approved_quantity <= 0:
            return
        fill_price = SLIPPAGE_MODEL.fill_price(price, "BUY")
        notional = money(assessment.approved_quantity * fill_price)
        costs = self.cost_model.calculate(notional, "BUY", REAL_COST_SCHEDULE)
        try:
            portfolio.buy(
                candidate.instrument_id, assessment.approved_quantity, fill_price, costs.total_cost
            )
        except ValueError:
            return
        notional_with_cost = money(notional + costs.total_cost)
        sector_values[candidate.sector] = money(
            sector_values.get(candidate.sector, Decimal(0)) + notional_with_cost
        )
        cluster_values[candidate.cluster] = money(
            cluster_values.get(candidate.cluster, Decimal(0)) + notional_with_cost
        )
