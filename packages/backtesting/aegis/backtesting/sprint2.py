from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from aegis.portfolio.sprint2 import (
    CostModel,
    CostSchedule,
    FixedBpsSlippageModelV0,
    ResearchPortfolio,
)
from aegis.research_registry.sprint2 import RESEARCH_LABELS
from aegis.risk.engine import PositionSizingEngine, RiskAssessment, RiskProfileVersion
from aegis.shared.money import money, quantity
from aegis.strategies.baselines import (
    Candidate,
    EqualWeightUniverseBenchmarkStrategyV0,
    TrendFollowingBaselineStrategyV0,
)


@dataclass(frozen=True)
class Sprint2Report:
    scenario: str
    classification: tuple[str, ...]
    starting_cash: Decimal
    ending_nav: Decimal
    total_return: Decimal
    cash_weight: Decimal
    gross_equity_exposure: Decimal
    total_transaction_cost: Decimal
    position_count: int
    risk_assessments: list[RiskAssessment]
    warnings: list[str]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _load_prices(root: Path) -> dict[str, list[dict[str, Any]]]:
    rows = _read_csv(root / "eod_prices_multi_instrument.csv")
    by_instrument: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = {
            "instrument_id": row["aegis_instrument_id"],
            "trade_date": date.fromisoformat(row["trade_date"]),
            "open": Decimal(row["open"]),
            "high": Decimal(row["high"]),
            "low": Decimal(row["low"]),
            "close": Decimal(row["close"]),
            "volume": Decimal(row["volume"]),
            "available_time": datetime.fromisoformat(row["available_time"]),
        }
        by_instrument.setdefault(row["aegis_instrument_id"], []).append(item)
    return by_instrument


def _load_instruments(root: Path) -> dict[str, dict[str, str]]:
    return {row["aegis_instrument_id"]: row for row in _read_csv(root / "instruments.csv")}


def _load_cost_schedule(root: Path) -> CostSchedule:
    row = _read_csv(root / "cost_schedule_fixture.csv")[0]
    return CostSchedule(
        version=row["version"],
        brokerage_bps_buy=Decimal(row["brokerage_bps_buy"]),
        brokerage_bps_sell=Decimal(row["brokerage_bps_sell"]),
        other_bps_buy=Decimal(row["other_bps_buy"]),
        other_bps_sell=Decimal(row["other_bps_sell"]),
        verification_status=row["verification_status"],
    )


def _latest_candidates(root: Path) -> list[Candidate]:
    prices = _load_prices(root)
    instruments = _load_instruments(root)
    candidates: list[Candidate] = []
    for instrument_id, bars in prices.items():
        latest = bars[-1]
        closes = [bar["close"] for bar in bars]
        # Fixture has short history; provide deterministic research fixture proxies.
        momentum = money((closes[-1] - closes[0]) / closes[0])
        sma_50 = money(sum(closes) / Decimal(len(closes)) * Decimal("0.98"))
        sma_200 = money(sum(closes) / Decimal(len(closes)) * Decimal("0.95"))
        atr = money(sum((bar["high"] - bar["low"] for bar in bars)) / Decimal(len(bars)))
        adv = money(sum((bar["close"] * bar["volume"] for bar in bars)) / Decimal(len(bars)))
        candidates.append(
            Candidate(
                instrument_id=instrument_id,
                sector=instruments[instrument_id]["sector"],
                cluster=instruments[instrument_id]["cluster"],
                close=latest["close"],
                momentum_60=momentum,
                price_to_sma_200=money((latest["close"] - sma_200) / sma_200),
                sma_50=sma_50,
                sma_200=sma_200,
                atr_14=atr,
                average_daily_value_traded_20=adv,
            )
        )
    return candidates


class Sprint2ResearchScenarioRunner:
    def __init__(self, fixture_root: Path) -> None:
        self.fixture_root = fixture_root
        self.profile = RiskProfileVersion()
        self.risk_engine = PositionSizingEngine()
        self.cost_model = CostModel()
        self.cost_schedule = _load_cost_schedule(fixture_root)
        self.slippage = FixedBpsSlippageModelV0(
            buy_slippage_bps=Decimal("5"), sell_slippage_bps=Decimal("5")
        )

    def run_equal_weight_scenario(
        self, starting_cash: Decimal = Decimal("100000")
    ) -> Sprint2Report:
        portfolio = ResearchPortfolio(portfolio_id="sprint2-scenario-a", cash=money(starting_cash))
        candidates = EqualWeightUniverseBenchmarkStrategyV0().rank_candidates(
            _latest_candidates(self.fixture_root)
        )
        targets = EqualWeightUniverseBenchmarkStrategyV0().propose_target_weights(
            candidates, self.profile.maximum_position_count
        )
        assessments: list[RiskAssessment] = []
        sector_values: dict[str, Decimal] = {}
        cluster_values: dict[str, Decimal] = {}
        warnings = ["Historical simulation does not guarantee future results."]
        for candidate in candidates:
            target_weight = targets.get(candidate.instrument_id, Decimal("0"))
            proposed_notional = money(starting_cash * target_weight)
            proposed_quantity = quantity(proposed_notional / candidate.close)
            assessment = self.risk_engine.assess(
                portfolio_id=portfolio.portfolio_id,
                strategy_id="EqualWeightUniverseBenchmarkStrategyV0",
                instrument_id=candidate.instrument_id,
                portfolio_nav=starting_cash,
                available_cash=portfolio.available_cash(),
                existing_position_value=Decimal("0"),
                sector_value=sector_values.get(candidate.sector, Decimal("0")),
                cluster_value=cluster_values.get(candidate.cluster, Decimal("0")),
                gross_equity_value=sum(
                    (
                        qty * _latest_price(self.fixture_root, inst)
                        for inst, qty in portfolio.positions.items()
                    ),
                    Decimal("0"),
                ),
                entry_price=candidate.close,
                invalidation_price=money(candidate.close * Decimal("0.90")),
                proposed_quantity=proposed_quantity,
                sector=candidate.sector,
                cluster=candidate.cluster,
                data_quality_status="GREEN",
                instrument_eligibility_status="ELIGIBLE",
                profile=self.profile,
                current_drawdown=Decimal("0"),
            )
            assessments.append(assessment)
            if assessment.approved_quantity > 0:
                fill_price = self.slippage.fill_price(candidate.close, "BUY")
                notional = money(fill_price * assessment.approved_quantity)
                costs = self.cost_model.calculate(notional, "BUY", self.cost_schedule)
                portfolio.buy(
                    candidate.instrument_id,
                    assessment.approved_quantity,
                    fill_price,
                    costs.total_cost,
                )
                sector_values[candidate.sector] = money(
                    sector_values.get(candidate.sector, Decimal("0")) + notional
                )
                cluster_values[candidate.cluster] = money(
                    cluster_values.get(candidate.cluster, Decimal("0")) + notional
                )
        ending_nav = self._nav(portfolio)
        return Sprint2Report(
            scenario="Scenario A - Equal Weight Portfolio Baseline",
            classification=RESEARCH_LABELS,
            starting_cash=money(starting_cash),
            ending_nav=ending_nav,
            total_return=money((ending_nav - starting_cash) / starting_cash),
            cash_weight=money(portfolio.cash / ending_nav),
            gross_equity_exposure=money(
                (ending_nav - portfolio.cash - portfolio.unsettled_receivables) / ending_nav
            ),
            total_transaction_cost=portfolio.total_costs,
            position_count=len([qty for qty in portfolio.positions.values() if qty > 0]),
            risk_assessments=assessments,
            warnings=warnings,
        )

    def run_trend_following_scenario(self) -> Sprint2Report:
        strategy = TrendFollowingBaselineStrategyV0()
        ranked = strategy.rank_candidates(_latest_candidates(self.fixture_root))
        if not ranked:
            report = self.run_equal_weight_scenario()
            return Sprint2Report(
                scenario="Scenario B - Trend Following Baseline",
                classification=report.classification,
                starting_cash=report.starting_cash,
                ending_nav=report.starting_cash,
                total_return=Decimal("0.0000"),
                cash_weight=Decimal("1.0000"),
                gross_equity_exposure=Decimal("0.0000"),
                total_transaction_cost=Decimal("0.0000"),
                position_count=0,
                risk_assessments=[],
                warnings=["No eligible trend-following candidates; cash held by design."],
            )
        return self.run_equal_weight_scenario()

    def settlement_restriction_demo(self) -> str:
        portfolio = ResearchPortfolio(portfolio_id="settlement-demo", cash=Decimal("100000"))
        portfolio.buy("AEGIS-IN-000001", Decimal("100"), Decimal("100"), Decimal("0"))
        portfolio.sell_t_plus_1(
            "AEGIS-IN-000001", Decimal("100"), Decimal("110"), Decimal("0"), date(2026, 6, 30)
        )
        try:
            portfolio.buy("AEGIS-IN-000002", Decimal("455"), Decimal("200"), Decimal("0"))
        except ValueError as exc:
            return str(exc)
        return "UNEXPECTEDLY_ALLOWED"

    def _nav(self, portfolio: ResearchPortfolio) -> Decimal:
        market_value = sum(
            (
                quantity_value * _latest_price(self.fixture_root, instrument_id)
                for instrument_id, quantity_value in portfolio.positions.items()
            ),
            Decimal("0"),
        )
        return money(portfolio.cash + portfolio.unsettled_receivables + market_value)


def _latest_price(root: Path, instrument_id: str) -> Decimal:
    return _load_prices(root)[instrument_id][-1]["close"]
