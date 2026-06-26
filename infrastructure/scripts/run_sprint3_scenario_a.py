from datetime import date, datetime, timezone
from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.paper_trading.services import PaperTradingOrchestrator, PaperTradingRepository, all_admission_evidence, all_readiness_green


repo = PaperTradingRepository()
orch = PaperTradingOrchestrator(repo, AuditLog())
portfolio = orch.create_portfolio(
    name="Sprint 3 Scenario A",
    description="Forward-only paper trading fixture",
    starting_capital=Decimal("100000"),
    created_by="FOUNDER",
)
config = orch.create_strategy_config(portfolio.paper_portfolio_id)
orch.admit_and_activate_strategy(config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER")
session = orch.run_decision_cycle(
    paper_portfolio_id=portfolio.paper_portfolio_id,
    session_date=date(2026, 6, 26),
    readiness_flags=all_readiness_green(),
    reference_prices={"AEGIS-IN-000001": Decimal("112")},
)
intent = next(iter(repo.intents.values()))
orch.approvals.approve(intent.paper_trade_intent_id, "RISK_REVIEWER", datetime(2026, 6, 26, 11, 0, tzinfo=timezone.utc))
orders = orch.execute_approved_orders(
    paper_portfolio_id=portfolio.paper_portfolio_id,
    execution_time=datetime(2026, 6, 29, 3, 45, tzinfo=timezone.utc),
    reference_prices={"AEGIS-IN-000001": Decimal("113")},
)
nav = orch.value_and_reconcile(portfolio.paper_portfolio_id, {"AEGIS-IN-000001": Decimal("114")})
evidence = orch.evidence_package(portfolio.paper_portfolio_id)
print(
    {
        "portfolio": portfolio.paper_portfolio_id,
        "session_status": session.decision_cycle_status,
        "intent_status": repo.intents[intent.paper_trade_intent_id].intent_status,
        "orders": [order.status for order in orders],
        "nav": nav.nav,
        "reconciliation": nav.reconciliation_status,
        "evidence_classification": evidence.classification,
    }
)
