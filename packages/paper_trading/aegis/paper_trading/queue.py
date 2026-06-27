from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from aegis.paper_trading.services import PaperTradingOrchestrator, all_readiness_green
from aegis.shared.ids import new_id
from aegis.shared.time import utc_now


@dataclass(frozen=True)
class PaperSessionJob:
    paper_portfolio_id: str
    session_date: date
    reference_prices: dict[str, Decimal]
    readiness_flags: dict[str, bool] = field(default_factory=all_readiness_green)
    status: str = "QUEUED"
    attempts: int = 0
    failure_reason_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("paper-session-job"))
    created_at: datetime = field(default_factory=utc_now)


class SqlitePaperSessionQueue:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_session_job (
                id TEXT PRIMARY KEY,
                paper_portfolio_id TEXT NOT NULL,
                session_date TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                failure_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def enqueue(self, job: PaperSessionJob) -> PaperSessionJob:
        self.connection.execute(
            """
            INSERT INTO paper_session_job (
                id, paper_portfolio_id, session_date, status, attempts, payload_json,
                failure_reason, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.paper_portfolio_id,
                job.session_date.isoformat(),
                job.status,
                job.attempts,
                self._payload(job),
                job.failure_reason_nullable,
                job.created_at.isoformat(),
                utc_now().isoformat(),
            ),
        )
        self.connection.commit()
        return job

    def claim_next(self) -> PaperSessionJob | None:
        row = self.connection.execute(
            "SELECT * FROM paper_session_job WHERE status = 'QUEUED' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self.connection.execute(
            "UPDATE paper_session_job SET status = 'RUNNING', attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (utc_now().isoformat(), row["id"]),
        )
        self.connection.commit()
        payload = json.loads(row["payload_json"])
        return PaperSessionJob(
            id=row["id"],
            paper_portfolio_id=row["paper_portfolio_id"],
            session_date=date.fromisoformat(row["session_date"]),
            reference_prices={
                key: Decimal(value) for key, value in payload["reference_prices"].items()
            },
            readiness_flags=payload["readiness_flags"],
            status="RUNNING",
            attempts=row["attempts"] + 1,
            failure_reason_nullable=row["failure_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def complete(self, job_id: str) -> None:
        self.connection.execute(
            "UPDATE paper_session_job SET status = 'COMPLETED', updated_at = ? WHERE id = ?",
            (utc_now().isoformat(), job_id),
        )
        self.connection.commit()

    def fail(self, job_id: str, reason: str) -> None:
        self.connection.execute(
            "UPDATE paper_session_job SET status = 'FAILED', failure_reason = ?, updated_at = ? WHERE id = ?",
            (reason, utc_now().isoformat(), job_id),
        )
        self.connection.commit()

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM paper_session_job ORDER BY created_at"
            )
        ]

    def run_once(self, orchestrator: PaperTradingOrchestrator) -> PaperSessionJob | None:
        job = self.claim_next()
        if job is None:
            return None
        try:
            orchestrator.run_decision_cycle(
                paper_portfolio_id=job.paper_portfolio_id,
                session_date=job.session_date,
                readiness_flags=job.readiness_flags,
                reference_prices=job.reference_prices,
            )
        except Exception as exc:
            self.fail(job.id, str(exc))
            raise
        self.complete(job.id)
        return job

    def _payload(self, job: PaperSessionJob) -> str:
        return json.dumps(
            {
                "reference_prices": {
                    key: str(value) for key, value in job.reference_prices.items()
                },
                "readiness_flags": job.readiness_flags,
            },
            sort_keys=True,
        )
