from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.paper_trading.domain import IncidentType
from aegis.paper_trading.services import PaperTradingOrchestrator, PaperTradingRepository, all_admission_evidence, all_readiness_green
from aegis.risk.engine import KillSwitchType


repo = PaperTradingRepository()
orch = PaperTradingOrchestrator(repo, AuditLog())
portfolio = orch.create_portfolio(
    name="Sprint 3 Failures",
    description="Fixture failures",
    starting_capital=Decimal("100000"),
    created_by="FOUNDER",
)
config = orch.create_strategy_config(portfolio.paper_portfolio_id)
orch.admit_and_activate_strategy(config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER")

red_flags = all_readiness_green()
red_flags["dataset_green_or_caution"] = False
blocked_session = orch.run_decision_cycle(
    paper_portfolio_id=portfolio.paper_portfolio_id,
    session_date=date(2026, 6, 26),
    readiness_flags=red_flags,
    reference_prices={"AEGIS-IN-000001": Decimal("112")},
)

# Use a fresh portfolio for approval/kill-switch checks after the data-failure freeze.
portfolio2 = orch.create_portfolio(
    name="Sprint 3 Approval",
    description="Fixture approval expiry",
    starting_capital=Decimal("100000"),
    created_by="FOUNDER",
)
config2 = orch.create_strategy_config(portfolio2.paper_portfolio_id)
orch.admit_and_activate_strategy(config2.paper_strategy_config_id, all_admission_evidence(), "FOUNDER")
orch.run_decision_cycle(
    paper_portfolio_id=portfolio2.paper_portfolio_id,
    session_date=date(2026, 6, 26),
    readiness_flags=all_readiness_green(),
    reference_prices={"AEGIS-IN-000001": Decimal("112")},
)
intent = [item for item in repo.intents.values() if item.paper_portfolio_id == portfolio2.paper_portfolio_id][0]
approval = orch.approvals.approve(intent.paper_trade_intent_id, "RISK_REVIEWER", datetime(2026, 6, 26, 11, 0, tzinfo=timezone.utc))
expired = orch.approvals.expire_due(approval.expiry_time + timedelta(seconds=1))
switch = orch.activate_kill_switch(KillSwitchType.PORTFOLIO_KILL_SWITCH, portfolio2.paper_portfolio_id, "fixture")
drift = orch.monitoring.assess_drift(paper_strategy_config_id=config2.paper_strategy_config_id, expected_signal_count=10, observed_signal_count=1)
incident = orch.incidents.create(
    paper_portfolio_id=portfolio2.paper_portfolio_id,
    incident_type=IncidentType.CORPORATE_ACTION_INCIDENT,
    severity="CRITICAL",
    description="Unsupported corporate action fixture",
    reason_codes=["UNRESOLVED_CORPORATE_ACTION"],
    freeze=True,
    correlation_id="fixture-correlation",
)
print(
    {
        "blocked_session": blocked_session.decision_cycle_status,
        "blocked_reason": blocked_session.failure_reason_nullable,
        "expired_approvals": [item.decision for item in expired],
        "kill_switch_active": switch.is_active,
        "drift": drift.severity,
        "incident": incident.incident_type,
        "portfolio2_state": repo.portfolios[portfolio2.paper_portfolio_id].status,
    }
)
