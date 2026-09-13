from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SqliteFundamentalsStore:
    """Durable store for real fundamentals quarters -- without this,
    InMemoryRepository.fundamentals_history/latest_fundamentals (and their
    _consolidated twins) live only in process memory and are lost on every
    API restart, exactly what happened repeatedly during manual-import
    testing this session. A record is already a plain JSON-safe dict (the
    parsed XBRL fields, all strings), so this is a simple payload-blob
    table keyed by (symbol, nature, period_to) -- not the typed dataclass
    mapper aegis.paper_trading.persistence uses, which reconstructs typed
    domain objects this has no need for. Mirrors
    aegis.backtesting.momentum_report_store's connection/migration style
    for consistency.

    nature is always the exact "STANDALONE"/"CONSOLIDATED" string already
    used elsewhere (see fundamentals_manual_import.py's required_nature
    and FundamentalsManualImportProvider.fundamentals_nature) -- callers
    must pass it explicitly to every method; this store never infers or
    defaults it, so Standalone and Consolidated rows can never be
    conflated by an accidental omission.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._migrate()

    def _migrate(self) -> None:
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fundamentals_quarter (
                symbol TEXT NOT NULL,
                nature TEXT NOT NULL,
                period_to TEXT NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (symbol, nature, period_to)
            )
            """
        )
        self.connection.commit()

    def upsert(self, symbol: str, nature: str, period_to: str, record: dict[str, Any]) -> None:
        """Real re-uploads of the same quarter (a corrected re-download)
        replace the row in place -- never a duplicate, matching how
        InMemoryRepository.fundamentals_history already treats period_to
        as the unique key for a symbol's quarter."""
        self.connection.execute(
            """
            INSERT INTO fundamentals_quarter (symbol, nature, period_to, record_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, nature, period_to) DO UPDATE SET record_json = excluded.record_json
            """,
            (symbol, nature, period_to, json.dumps(record)),
        )
        self.connection.commit()

    def delete(self, symbol: str, nature: str, period_to: str) -> None:
        """Mirrors the DELETE .../history/{symbol}/{period_to} endpoint's
        in-memory removal -- a mistaken upload must not survive a restart
        just because it lived in this durable store."""
        self.connection.execute(
            "DELETE FROM fundamentals_quarter WHERE symbol = ? AND nature = ? AND period_to = ?",
            (symbol, nature, period_to),
        )
        self.connection.commit()

    def load_history(self, nature: str) -> dict[str, dict[str, dict[str, Any]]]:
        """Rehydrates the exact shape InMemoryRepository.fundamentals_history
        (or its _consolidated twin) expects at startup: symbol -> period_to
        -> record. Only ever returns rows for the single nature asked for."""
        rows = self.connection.execute(
            "SELECT symbol, period_to, record_json FROM fundamentals_quarter WHERE nature = ?",
            (nature,),
        ).fetchall()
        history: dict[str, dict[str, dict[str, Any]]] = {}
        for symbol, period_to, record_json in rows:
            history.setdefault(symbol, {})[period_to] = json.loads(record_json)
        return history
