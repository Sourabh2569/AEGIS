from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from aegis.paper_trading.domain import (
    PaperApproval,
    PaperCorporateActionReview,
    PaperDriftAssessment,
    PaperEvidencePackage,
    PaperFill,
    PaperLedgerEntry,
    PaperNavSnapshot,
    PaperOrder,
    PaperPortfolio,
    PaperPortfolioConfiguration,
    PaperReconciliationRecord,
    PaperStrategyConfiguration,
    PaperTradeIntent,
    PaperTradingIncident,
    PaperTradingSession,
)
from aegis.paper_trading.services import PaperTradingRepository
from aegis.portfolio.sprint2 import ResearchPortfolio
from aegis.shared.dataclass_json import from_json, to_json

T = TypeVar("T")


TABLES: dict[str, tuple[str, type[Any]]] = {
    "paper_portfolio": ("paper_portfolio_id", PaperPortfolio),
    "paper_portfolio_configuration": ("paper_portfolio_id", PaperPortfolioConfiguration),
    "paper_strategy_configuration": ("paper_strategy_config_id", PaperStrategyConfiguration),
    "paper_trading_session": ("paper_trading_session_id", PaperTradingSession),
    "paper_trade_intent": ("paper_trade_intent_id", PaperTradeIntent),
    "paper_approval": ("paper_trade_intent_id", PaperApproval),
    "paper_order": ("paper_order_id", PaperOrder),
    "paper_fill": ("paper_fill_id", PaperFill),
    "paper_ledger_entry": ("id", PaperLedgerEntry),
    "paper_nav_snapshot": ("id", PaperNavSnapshot),
    "paper_reconciliation_record": ("id", PaperReconciliationRecord),
    "paper_incident": ("id", PaperTradingIncident),
    "paper_drift_assessment": ("id", PaperDriftAssessment),
    "paper_evidence_package": ("id", PaperEvidencePackage),
    "paper_corporate_action_review": ("id", PaperCorporateActionReview),
}


class SqlitePaperTradingRepository(PaperTradingRepository):
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
                    paper_portfolio_id TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_repository_meta (
                key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def _load_table(self, table: str, cls: type[T]) -> list[T]:
        rows = self.connection.execute(f"SELECT payload_json FROM {table}").fetchall()
        return [from_json(row["payload_json"], cls) for row in rows]

    def _load(self) -> None:
        for item in self._load_table("paper_portfolio", PaperPortfolio):
            self.portfolios[item.paper_portfolio_id] = item
        for item in self._load_table("paper_portfolio_configuration", PaperPortfolioConfiguration):
            self.portfolio_configs[item.paper_portfolio_id] = item
        for item in self._load_table("paper_strategy_configuration", PaperStrategyConfiguration):
            self.strategy_configs[item.paper_strategy_config_id] = item
        for item in self._load_table("paper_trading_session", PaperTradingSession):
            self.sessions[item.paper_trading_session_id] = item
        for item in self._load_table("paper_trade_intent", PaperTradeIntent):
            self.intents[item.paper_trade_intent_id] = item
        for item in self._load_table("paper_approval", PaperApproval):
            self.approvals[item.paper_trade_intent_id] = item
        for item in self._load_table("paper_order", PaperOrder):
            self.orders[item.paper_order_id] = item
        for item in self._load_table("paper_fill", PaperFill):
            self.fills[item.paper_fill_id] = item
        for item in self._load_table("paper_ledger_entry", PaperLedgerEntry):
            self.ledger.setdefault(item.paper_portfolio_id, []).append(item)
        for item in self._load_table("paper_nav_snapshot", PaperNavSnapshot):
            self.nav.setdefault(item.paper_portfolio_id, []).append(item)
        for item in self._load_table("paper_reconciliation_record", PaperReconciliationRecord):
            self.reconciliations.setdefault(item.paper_portfolio_id, []).append(item)
        for item in self._load_table("paper_incident", PaperTradingIncident):
            self.incidents[item.id] = item
        for item in self._load_table("paper_drift_assessment", PaperDriftAssessment):
            self.drift[item.id] = item
        for item in self._load_table("paper_evidence_package", PaperEvidencePackage):
            self.evidence[item.id] = item
        for item in self._load_table("paper_corporate_action_review", PaperCorporateActionReview):
            self.corporate_action_reviews[item.id] = item
        for portfolio in self.portfolios.values():
            paper = ResearchPortfolio(
                portfolio_id=portfolio.paper_portfolio_id,
                cash=portfolio.starting_capital,
            )
            for fill in sorted(
                [
                    item
                    for item in self.fills.values()
                    if item.paper_portfolio_id == portfolio.paper_portfolio_id
                ],
                key=lambda item: item.fill_time,
            ):
                paper.buy(
                    fill.instrument_id,
                    fill.fill_quantity,
                    fill.simulated_fill_price,
                    fill.cost_total,
                )
            self.paper_portfolios[portfolio.paper_portfolio_id] = paper

    def persist(self) -> None:
        self._upsert_many("paper_portfolio", self.portfolios.values())
        self._upsert_many("paper_portfolio_configuration", self.portfolio_configs.values())
        self._upsert_many("paper_strategy_configuration", self.strategy_configs.values())
        self._upsert_many("paper_trading_session", self.sessions.values())
        self._upsert_many("paper_trade_intent", self.intents.values())
        self._upsert_many("paper_approval", self.approvals.values())
        self._upsert_many("paper_order", self.orders.values())
        self._upsert_many("paper_fill", self.fills.values())
        self._upsert_many(
            "paper_ledger_entry", [item for entries in self.ledger.values() for item in entries]
        )
        self._upsert_many(
            "paper_nav_snapshot", [item for entries in self.nav.values() for item in entries]
        )
        self._upsert_many(
            "paper_reconciliation_record",
            [item for entries in self.reconciliations.values() for item in entries],
        )
        self._upsert_many("paper_incident", self.incidents.values())
        self._upsert_many("paper_drift_assessment", self.drift.values())
        self._upsert_many("paper_evidence_package", self.evidence.values())
        self._upsert_many("paper_corporate_action_review", self.corporate_action_reviews.values())
        self.connection.commit()

    def _upsert_many(self, table: str, items: Any) -> None:
        key_field, _ = TABLES[table]
        for item in items:
            entity_id = getattr(item, key_field)
            paper_portfolio_id = getattr(item, "paper_portfolio_id", None)
            self.connection.execute(
                f"""
                INSERT INTO {table} (entity_id, paper_portfolio_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    paper_portfolio_id = excluded.paper_portfolio_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (entity_id, paper_portfolio_id, to_json(item), datetime.now(UTC).isoformat()),
            )

    def add_portfolio(self, portfolio: PaperPortfolio, config: PaperPortfolioConfiguration) -> None:
        super().add_portfolio(portfolio, config)
        self.persist()

    def save_portfolio(self, portfolio: PaperPortfolio) -> None:
        super().save_portfolio(portfolio)
        self.persist()

    def save_strategy_config(self, config: PaperStrategyConfiguration) -> None:
        super().save_strategy_config(config)
        self.persist()
