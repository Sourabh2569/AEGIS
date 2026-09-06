from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from aegis.backtesting.domain import (
    BacktestEvent,
    BacktestEventType,
    BacktestRun,
    CashLedgerEntry,
    OrderIntent,
    PortfolioNavSnapshot,
    PositionLedgerEntry,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPortfolio,
)


class BacktestRepository:
    def __init__(self) -> None:
        self.runs: dict[str, BacktestRun] = {}
        self.portfolios: dict[str, SimulatedPortfolio] = {}
        self.events: dict[str, list[BacktestEvent]] = {}
        self.cash_ledger: dict[str, list[CashLedgerEntry]] = {}
        self.position_ledger: dict[str, list[PositionLedgerEntry]] = {}
        self.order_intents: dict[str, list[OrderIntent]] = {}
        self.orders: dict[str, list[SimulatedOrder]] = {}
        self.fills: dict[str, list[SimulatedFill]] = {}
        self.nav_snapshots: dict[str, list[PortfolioNavSnapshot]] = {}
        self.started_jobs: set[str] = set()
        self.executed_intents: set[str] = set()

    def add_run(self, run: BacktestRun, portfolio: SimulatedPortfolio) -> None:
        self.runs[run.backtest_run_id] = run
        self.portfolios[run.backtest_run_id] = portfolio
        self.events.setdefault(run.backtest_run_id, [])
        self.cash_ledger.setdefault(run.backtest_run_id, [])
        self.position_ledger.setdefault(run.backtest_run_id, [])
        self.order_intents.setdefault(run.backtest_run_id, [])
        self.orders.setdefault(run.backtest_run_id, [])
        self.fills.setdefault(run.backtest_run_id, [])
        self.nav_snapshots.setdefault(run.backtest_run_id, [])

    def save_run(self, run: BacktestRun) -> None:
        self.runs[run.backtest_run_id] = run

    def save_portfolio(self, portfolio: SimulatedPortfolio) -> None:
        self.portfolios[portfolio.backtest_run_id] = portfolio

    def append_event(
        self,
        *,
        backtest_run_id: str,
        event_type: BacktestEventType,
        event_time: datetime,
        payload_json: dict[str, Any],
        correlation_id: str,
        market_session_date: date | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> BacktestEvent:
        sequence_number = len(self.events.setdefault(backtest_run_id, [])) + 1
        event = BacktestEvent(
            backtest_run_id=backtest_run_id,
            sequence_number=sequence_number,
            event_type=event_type,
            event_time=event_time,
            market_session_date_nullable=market_session_date,
            entity_type_nullable=entity_type,
            entity_id_nullable=entity_id,
            payload_json=payload_json,
            correlation_id=correlation_id,
        )
        self.events[backtest_run_id].append(event)
        return event

    def append_cash(self, entry: CashLedgerEntry) -> None:
        self.cash_ledger.setdefault(entry.backtest_run_id, []).append(entry)

    def append_position(self, entry: PositionLedgerEntry) -> None:
        self.position_ledger.setdefault(entry.backtest_run_id, []).append(entry)

    def append_intent(self, intent: OrderIntent) -> None:
        self.order_intents.setdefault(intent.backtest_run_id, []).append(intent)

    def replace_intent(self, intent: OrderIntent) -> None:
        intents = self.order_intents[intent.backtest_run_id]
        self.order_intents[intent.backtest_run_id] = [
            intent if existing.id == intent.id else existing for existing in intents
        ]

    def append_order(self, order: SimulatedOrder) -> None:
        self.orders.setdefault(order.backtest_run_id, []).append(order)

    def append_fill(self, fill: SimulatedFill) -> None:
        self.fills.setdefault(fill.backtest_run_id, []).append(fill)

    def append_nav(self, snapshot: PortfolioNavSnapshot) -> None:
        self.nav_snapshots.setdefault(snapshot.backtest_run_id, []).append(snapshot)

    def mark_job_started_once(self, backtest_run_id: str) -> bool:
        if backtest_run_id in self.started_jobs:
            return False
        self.started_jobs.add(backtest_run_id)
        return True

    def mark_intent_executed_once(self, intent_id: str) -> bool:
        if intent_id in self.executed_intents:
            return False
        self.executed_intents.add(intent_id)
        return True

    def realized_pnl(self, backtest_run_id: str) -> Decimal:
        return sum(
            (entry.realized_pnl_delta for entry in self.position_ledger.get(backtest_run_id, [])),
            Decimal(0),
        )

    def current_quantity(self, backtest_run_id: str) -> Decimal:
        entries = self.position_ledger.get(backtest_run_id, [])
        return entries[-1].quantity_after if entries else Decimal(0)

    def current_cost_basis(self, backtest_run_id: str) -> Decimal:
        entries = self.position_ledger.get(backtest_run_id, [])
        return entries[-1].cost_basis_after if entries else Decimal(0)


class TradingCalendarReader:
    def __init__(self, sessions: list[date], exchange: str = "NSE") -> None:
        self.sessions = sorted(sessions)
        self.exchange = exchange
        self.source_reference = f"fixture://{exchange}/calendar"

    def sessions_between(self, start_date: date, end_date: date) -> list[date]:
        return [session for session in self.sessions if start_date <= session <= end_date]

    def next_session_after(self, decision_time: datetime) -> date | None:
        local_date = decision_time.astimezone(UTC).date()
        for session in self.sessions:
            if session > local_date:
                return session
        return None

    def session_open_time(self, session: date) -> datetime:
        return datetime.combine(session, time(3, 45), tzinfo=UTC)

    def session_close_time(self, session: date) -> datetime:
        return datetime.combine(session, time(10, 0), tzinfo=UTC)


class MarketDataReader:
    def __init__(
        self, bars: dict[tuple[str, date], dict[str, Any]], dataset_version_id: str
    ) -> None:
        self.bars = bars
        self.dataset_version_id = dataset_version_id

    def has_bars(self, instrument_id: str, start_date: date, end_date: date) -> bool:
        sessions = [session for inst, session in self.bars if inst == instrument_id]
        return any(start_date <= session <= end_date for session in sessions)

    def get_open(self, instrument_id: str, session: date) -> Decimal | None:
        value = self.bars.get((instrument_id, session), {}).get("open")
        return None if value in (None, "") else Decimal(str(value))

    def get_close(self, instrument_id: str, session: date) -> Decimal | None:
        value = self.bars.get((instrument_id, session), {}).get("close")
        return None if value in (None, "") else Decimal(str(value))

    def available_time(self, instrument_id: str, session: date) -> datetime | None:
        value = self.bars.get((instrument_id, session), {}).get("available_time")
        return value if isinstance(value, datetime) else None


def update_portfolio(portfolio: SimulatedPortfolio, **changes: Any) -> SimulatedPortfolio:
    return replace(portfolio, **changes)
