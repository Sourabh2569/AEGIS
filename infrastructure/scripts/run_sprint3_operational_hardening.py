from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import PaperSessionJob, SqlitePaperSessionQueue
from aegis.paper_trading.services import (
    PaperTradingCalendarService,
    PaperTradingOrchestrator,
    all_admission_evidence,
)


db_path = Path("work/sprint3_operational_hardening.sqlite")
queue_path = Path("work/sprint3_operational_queue.sqlite")
db_path.parent.mkdir(parents=True, exist_ok=True)
if db_path.exists():
    db_path.unlink()
if queue_path.exists():
    queue_path.unlink()

calendar = PaperTradingCalendarService.from_csv(Path("sample_data/sprint_3/forward_market_calendar.csv"))
repo = SqlitePaperTradingRepository(db_path)
orch = PaperTradingOrchestrator(repo, AuditLog(), calendar=calendar)
queue = SqlitePaperSessionQueue(queue_path)

portfolio = orch.create_portfolio(
    name="Sprint 3 Operational Hardening",
    description="DB and queue backed paper fixture",
    starting_capital=Decimal("100000"),
    created_by="FOUNDER",
)
config = orch.create_strategy_config(portfolio.paper_portfolio_id)
orch.admit_and_activate_strategy(config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER")

job = queue.enqueue(
    PaperSessionJob(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        reference_prices={"AEGIS-IN-000001": Decimal("112")},
    )
)
queue.run_once(orch)
intent = next(intent for intent in repo.intents.values() if intent.paper_portfolio_id == portfolio.paper_portfolio_id)

reloaded = SqlitePaperTradingRepository(db_path)
review = orch.corporate_actions.review(
    paper_portfolio_id=portfolio.paper_portfolio_id,
    instrument_id="AEGIS-IN-000001",
    action_type="DEMERGER",
    effective_date=date(2026, 6, 30),
    verification_status="PENDING",
    supported=False,
    reviewer_id="DATA_STEWARD",
    correlation_id="operational-hardening",
)

print(
    {
        "db_path": str(db_path),
        "queue_job": job.id,
        "queue_status": queue.list_jobs()[0]["status"],
        "persisted_portfolios": len(reloaded.portfolios),
        "persisted_intents": len(reloaded.intents),
        "eligible_execution_time": intent.eligible_execution_time.isoformat(),
        "corporate_action_decision": review.decision,
        "portfolio_status": repo.portfolios[portfolio.paper_portfolio_id].status,
    }
)
