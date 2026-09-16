from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from aegis.live_trading.domain import (
    LiveApproval,
    LiveExecutionPreflight,
    LiveFill,
    LiveIncident,
    LiveOrder,
    LiveOrderIntent,
    LivePortfolio,
    LivePortfolioConfiguration,
    LiveReconciliationRecord,
    LiveStrategyConfiguration,
)
from aegis.live_trading.services import LiveTradingRepository
from aegis.portfolio.sprint2 import ResearchPortfolio
from aegis.shared.dataclass_json import from_json, to_json

T = TypeVar("T")


TABLES: dict[str, tuple[str, type[Any]]] = {
    "live_portfolio": ("live_portfolio_id", LivePortfolio),
    "live_portfolio_configuration": ("live_portfolio_id", LivePortfolioConfiguration),
    "live_strategy_configuration": ("live_strategy_config_id", LiveStrategyConfiguration),
    "live_order_intent": ("live_order_intent_id", LiveOrderIntent),
    "live_approval": ("live_order_intent_id", LiveApproval),
    "live_order": ("live_order_id", LiveOrder),
    "live_fill": ("live_fill_id", LiveFill),
    "live_reconciliation_record": ("id", LiveReconciliationRecord),
    "live_incident": ("id", LiveIncident),
    "live_execution_preflight": ("id", LiveExecutionPreflight),
}


class SqliteLiveTradingRepository(LiveTradingRepository):
    """Mirrors SqlitePaperTradingRepository's exact JSON-blob-per-entity
    pattern (packages/paper_trading/aegis/paper_trading/persistence.py) --
    both packages import the same to_json/from_json helpers from
    aegis.shared.dataclass_json rather than each defining their own copy,
    since both need byte-identical Decimal/datetime/date/Enum handling and
    drift between two copies of the same encoder would be a real, avoidable
    bug. This is a shared *utility*, not a shared *dependency* between the
    two trading packages -- live_trading never imports anything from
    paper_trading, keeping Document 007's "never structurally co-mingled"
    principle true at the import-graph level too. Deliberately its own
    database file (never paper_trading.sqlite) -- Document 007's stance
    that live and paper data must never be structurally co-mingled applies
    at the storage layer too, not just in memory."""

    def __init__(self, db_path: Path | str) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._migrate()
        self._load()

    def _migrate(self) -> None:
        self.connection.execute("PRAGMA journal_mode=WAL")
        for table in TABLES:
            self.connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    entity_id TEXT PRIMARY KEY,
                    live_portfolio_id TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        self.connection.commit()

    def _load_table(self, table: str, cls: type[T]) -> list[T]:
        rows = self.connection.execute(f"SELECT payload_json FROM {table}").fetchall()
        return [from_json(row["payload_json"], cls) for row in rows]

    def _load(self) -> None:
        for item in self._load_table("live_portfolio", LivePortfolio):
            self.portfolios[item.live_portfolio_id] = item
        for item in self._load_table("live_portfolio_configuration", LivePortfolioConfiguration):
            self.portfolio_configs[item.live_portfolio_id] = item
        for item in self._load_table("live_strategy_configuration", LiveStrategyConfiguration):
            self.strategy_configs[item.live_strategy_config_id] = item
        for item in self._load_table("live_order_intent", LiveOrderIntent):
            self.intents[item.live_order_intent_id] = item
        for item in self._load_table("live_approval", LiveApproval):
            self.approvals[item.live_order_intent_id] = item
        for item in self._load_table("live_order", LiveOrder):
            self.orders[item.live_order_id] = item
        for item in self._load_table("live_fill", LiveFill):
            self.fills[item.live_fill_id] = item
        for item in self._load_table("live_reconciliation_record", LiveReconciliationRecord):
            self.reconciliations.setdefault(item.live_portfolio_id, []).append(item)
        for item in self._load_table("live_incident", LiveIncident):
            self.incidents[item.id] = item
        for item in self._load_table("live_execution_preflight", LiveExecutionPreflight):
            self.preflights[item.id] = item
        self._rebuild_research_portfolios()

    def _rebuild_research_portfolios(self) -> None:
        # Reconstructs the real cash/position ledger from persisted fills on
        # every restart (ResearchPortfolio itself is never persisted
        # directly). Unlike paper_trading's equivalent replay, this applies
        # each fill by its own intent side (BUY vs SELL) rather than always
        # calling .buy() -- a real sell that isn't replayed as a real sell
        # would silently double a position after every restart.
        for portfolio in self.portfolios.values():
            research_portfolio = ResearchPortfolio(
                portfolio_id=portfolio.live_portfolio_id, cash=portfolio.starting_capital
            )
            portfolio_fills = sorted(
                (
                    fill
                    for fill in self.fills.values()
                    if fill.live_portfolio_id == portfolio.live_portfolio_id
                ),
                key=lambda fill: fill.fill_time,
            )
            for fill in portfolio_fills:
                order = self.orders.get(fill.live_order_id)
                intent = self.intents.get(order.live_order_intent_id) if order else None
                is_sell = intent is not None and intent.side == "SELL"
                if is_sell:
                    try:
                        research_portfolio.sell_t_plus_1(
                            fill.instrument_id,
                            fill.fill_quantity,
                            fill.fill_price,
                            fill.cost_total,
                            fill.settlement_date,
                        )
                    except ValueError:
                        continue  # an incident was already recorded when this fill was first applied
                else:
                    research_portfolio.buy(
                        fill.instrument_id, fill.fill_quantity, fill.fill_price, fill.cost_total
                    )
            self.research_portfolios[portfolio.live_portfolio_id] = research_portfolio

    def persist(self) -> None:
        self._upsert_many("live_portfolio", self.portfolios.values())
        self._upsert_many("live_portfolio_configuration", self.portfolio_configs.values())
        self._upsert_many("live_strategy_configuration", self.strategy_configs.values())
        self._upsert_many("live_order_intent", self.intents.values())
        self._upsert_many("live_approval", self.approvals.values())
        self._upsert_many("live_order", self.orders.values())
        self._upsert_many("live_fill", self.fills.values())
        self._upsert_many(
            "live_reconciliation_record",
            [item for entries in self.reconciliations.values() for item in entries],
        )
        self._upsert_many("live_incident", self.incidents.values())
        self._upsert_many("live_execution_preflight", self.preflights.values())
        self.connection.commit()

    def _upsert_many(self, table: str, items: Any) -> None:
        key_field, _ = TABLES[table]
        for item in items:
            entity_id = getattr(item, key_field)
            live_portfolio_id = getattr(item, "live_portfolio_id", None)
            self.connection.execute(
                f"""
                INSERT INTO {table} (entity_id, live_portfolio_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    live_portfolio_id = excluded.live_portfolio_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (entity_id, live_portfolio_id, to_json(item), datetime.now(UTC).isoformat()),
            )

    def add_portfolio(self, portfolio: LivePortfolio, config: LivePortfolioConfiguration) -> None:
        super().add_portfolio(portfolio, config)
        self.persist()

    def save_portfolio(self, portfolio: LivePortfolio) -> None:
        super().save_portfolio(portfolio)
        self.persist()

    def save_strategy_config(self, config: LiveStrategyConfiguration) -> None:
        super().save_strategy_config(config)
        self.persist()

    def save_intent(self, intent: LiveOrderIntent) -> None:
        super().save_intent(intent)
        self.persist()

    def save_approval(self, approval: LiveApproval) -> None:
        super().save_approval(approval)
        self.persist()

    def save_order(self, order: LiveOrder) -> None:
        super().save_order(order)
        self.persist()

    def save_fill(self, fill: LiveFill) -> None:
        super().save_fill(fill)
        self.persist()

    def save_incident(self, incident: LiveIncident) -> None:
        super().save_incident(incident)
        self.persist()

    def save_preflight(self, preflight: LiveExecutionPreflight) -> None:
        super().save_preflight(preflight)
        self.persist()

    def add_reconciliation(self, record: LiveReconciliationRecord) -> None:
        super().add_reconciliation(record)
        self.persist()
