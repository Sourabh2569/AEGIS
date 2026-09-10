from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SqliteMomentumReportStore:
    """Durable, append-only store for real momentum backtest reports.

    A report (see RealMomentumReport / run_real_momentum_backtest in
    aegis_api.main) is already a plain JSON-safe dict -- the output of the
    existing jsonable() helper -- so this is a simple payload-blob table,
    not the typed dataclass<->SQLite mapper aegis.paper_trading.persistence
    uses (that mapper reconstructs typed domain dataclasses on load; a
    backtest report has no such type to reconstruct into). Mirrors that
    module's connection/migration style for consistency.
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
            CREATE TABLE IF NOT EXISTS momentum_report (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def append(self, report: dict[str, Any], *, created_at: str) -> None:
        self.connection.execute(
            "INSERT INTO momentum_report (payload_json, created_at) VALUES (?, ?)",
            (json.dumps(report), created_at),
        )
        self.connection.commit()

    def load_all(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT payload_json FROM momentum_report ORDER BY id ASC"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
