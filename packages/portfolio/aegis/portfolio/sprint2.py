from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from aegis.shared.ids import new_id
from aegis.shared.money import money, quantity
from aegis.shared.time import utc_now


class StrEnum(str, Enum):
    pass


class SettlementModelVersion(StrEnum):
    IMMEDIATE_SETTLEMENT_SIMULATION_V0 = "IMMEDIATE_SETTLEMENT_SIMULATION_V0"
    T_PLUS_1_CONSERVATIVE_V0 = "T_PLUS_1_CONSERVATIVE_V0"


@dataclass(frozen=True)
class CostLineItem:
    charge_type: str
    amount: Decimal


@dataclass(frozen=True)
class CostSchedule:
    version: str
    brokerage_bps_buy: Decimal
    brokerage_bps_sell: Decimal
    other_bps_buy: Decimal = Decimal(0)
    other_bps_sell: Decimal = Decimal(0)
    verification_status: str = "FIXTURE_ONLY"


@dataclass(frozen=True)
class CostCalculation:
    gross_notional: Decimal
    line_items: list[CostLineItem]
    total_cost: Decimal
    cost_schedule_version: str


class CostModel:
    def calculate(
        self, gross_notional: Decimal, side: str, schedule: CostSchedule
    ) -> CostCalculation:
        if schedule.verification_status != "APPROVED_FIXTURE":
            raise ValueError("Cost schedule is not approved for Sprint 2 research fixtures.")
        bps = (
            schedule.brokerage_bps_buy + schedule.other_bps_buy
            if side == "BUY"
            else schedule.brokerage_bps_sell + schedule.other_bps_sell
        )
        total = money(gross_notional * bps / Decimal(10000))
        return CostCalculation(
            gross_notional=money(gross_notional),
            line_items=[CostLineItem("FIXTURE_TRANSACTION_COST", total)],
            total_cost=total,
            cost_schedule_version=schedule.version,
        )


@dataclass(frozen=True)
class FixedBpsSlippageModelV0:
    buy_slippage_bps: Decimal
    sell_slippage_bps: Decimal
    version: str = "FIXED_BPS_SLIPPAGE_V0"

    def fill_price(self, reference_price: Decimal, side: str) -> Decimal:
        bps = self.buy_slippage_bps if side == "BUY" else self.sell_slippage_bps
        direction = Decimal(1) if side == "BUY" else Decimal(-1)
        return money(reference_price * (Decimal(1) + (direction * bps / Decimal(10000))))


@dataclass(frozen=True)
class SettlementLedgerEntry:
    portfolio_id: str
    instrument_id: str
    settlement_date: date
    cash_receivable: Decimal = Decimal(0)
    quantity_receivable: Decimal = Decimal(0)
    is_settled: bool = False
    id: str = field(default_factory=lambda: new_id("settlement"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ResearchPortfolio:
    portfolio_id: str
    cash: Decimal
    unsettled_receivables: Decimal = Decimal(0)
    positions: dict[str, Decimal] = field(default_factory=dict)
    average_cost: dict[str, Decimal] = field(default_factory=dict)
    realized_pnl: Decimal = Decimal(0)
    total_costs: Decimal = Decimal(0)
    total_slippage: Decimal = Decimal(0)
    settlement_ledger: list[SettlementLedgerEntry] = field(default_factory=list)

    def available_cash(self) -> Decimal:
        return money(self.cash)

    def buy(
        self, instrument_id: str, quantity_value: Decimal, fill_price: Decimal, total_cost: Decimal
    ) -> None:
        notional = money(quantity_value * fill_price)
        cash_effect = money(notional + total_cost)
        if self.cash < cash_effect:
            raise ValueError("INSUFFICIENT_SETTLED_CASH")
        existing_qty = self.positions.get(instrument_id, Decimal(0))
        existing_cost = self.average_cost.get(instrument_id, Decimal(0))
        new_qty = quantity(existing_qty + quantity_value)
        self.average_cost[instrument_id] = money(
            ((existing_qty * existing_cost) + (quantity_value * fill_price)) / new_qty
        )
        self.positions[instrument_id] = new_qty
        self.cash = money(self.cash - cash_effect)
        self.total_costs = money(self.total_costs + total_cost)

    def sell_t_plus_1(
        self,
        instrument_id: str,
        quantity_value: Decimal,
        fill_price: Decimal,
        total_cost: Decimal,
        settlement_date: date,
    ) -> None:
        existing_qty = self.positions.get(instrument_id, Decimal(0))
        if quantity_value > existing_qty:
            raise ValueError("OVERSELL")
        average = self.average_cost.get(instrument_id, Decimal(0))
        notional = money(quantity_value * fill_price)
        self.positions[instrument_id] = quantity(existing_qty - quantity_value)
        if self.positions[instrument_id] == 0:
            self.average_cost[instrument_id] = Decimal(0)
        self.realized_pnl = money(
            self.realized_pnl + ((fill_price - average) * quantity_value) - total_cost
        )
        self.unsettled_receivables = money(self.unsettled_receivables + notional - total_cost)
        self.total_costs = money(self.total_costs + total_cost)
        self.settlement_ledger.append(
            SettlementLedgerEntry(
                portfolio_id=self.portfolio_id,
                instrument_id=instrument_id,
                settlement_date=settlement_date,
                cash_receivable=money(notional - total_cost),
            )
        )

    def settle_due(self, session: date) -> None:
        for entry in self.settlement_ledger:
            if not entry.is_settled and entry.settlement_date <= session:
                self.cash = money(self.cash + entry.cash_receivable)
                self.unsettled_receivables = money(
                    self.unsettled_receivables - entry.cash_receivable
                )
                object.__setattr__(entry, "is_settled", True)
