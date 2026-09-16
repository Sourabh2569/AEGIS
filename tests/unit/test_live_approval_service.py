from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from aegis.audit.service import AuditLog
from aegis.live_trading.domain import (
    LiveApprovalDecision,
    LiveIntentStatus,
    LiveOrderIntent,
    LivePortfolio,
    LivePortfolioStatus,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.services import LiveApprovalService
from aegis.shared.time import utc_now

NOW = utc_now()


def _portfolio(**overrides) -> LivePortfolio:
    kwargs = {
        "name": "Pilot",
        "description": "test",
        "starting_capital": Decimal(400000),
        "pilot_capital_cap": Decimal(400000),
        "risk_profile_version_id": "v1",
        "portfolio_configuration_version": "v1",
        "created_by": "founder",
        "status": LivePortfolioStatus.ACTIVE,
    }
    kwargs.update(overrides)
    return LivePortfolio(**kwargs)


def _intent(portfolio: LivePortfolio) -> LiveOrderIntent:
    decision_time = NOW - timedelta(minutes=5)
    return LiveOrderIntent(
        live_portfolio_id=portfolio.live_portfolio_id,
        live_strategy_config_id="cfg1",
        strategy_version_id="DiversifiedRiskOverlayStrategyV2",
        instrument_id="AEGIS-IN-000001",
        side="BUY",
        proposed_quantity=Decimal(10),
        decision_time=decision_time,
        available_data_cutoff=decision_time,
        eligible_execution_time=NOW + timedelta(hours=1),
        risk_assessment_id="r1",
        configuration_version="v1",
        idempotency_key="k1",
        correlation_id="c1",
    )


def _setup(tmp_path):
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio()
    from aegis.live_trading.domain import LivePortfolioConfiguration

    repo.add_portfolio(
        portfolio,
        LivePortfolioConfiguration(
            live_portfolio_id=portfolio.live_portfolio_id,
            version="v1",
            risk_profile_version_id="v1",
            minimum_cash_weight=Decimal("0.20"),
            maximum_gross_equity_exposure=Decimal("0.80"),
            maximum_position_count=50,
            settlement_model_version="v1",
            cost_schedule_version="v1",
            execution_model_version="v1",
            market_calendar_policy="NSE_STANDARD",
            valuation_policy="CLOSE",
            corporate_action_policy="FREEZE_ON_UNSUPPORTED",
            created_by="founder",
        ),
    )
    intent = _intent(portfolio)
    repo.save_intent(intent)
    audit_log = AuditLog()
    return repo, portfolio, intent, LiveApprovalService(repo, audit_log), audit_log


def test_approve_records_a_real_approval_and_updates_the_intent(tmp_path) -> None:
    repo, _portfolio, intent, service, audit_log = _setup(tmp_path)

    approval = service.approve(
        intent.live_order_intent_id, "founder", confirmed_amount=Decimal("10000.00")
    )

    assert approval.decision == LiveApprovalDecision.APPROVED
    assert approval.confirmed_amount_nullable == Decimal("10000.00")
    updated_intent = repo.intents[intent.live_order_intent_id]
    assert updated_intent.intent_status == LiveIntentStatus.APPROVED
    assert updated_intent.approved_quantity_nullable == Decimal("10.000000")

    events = [e for e in audit_log.list_events() if e.event_type == "LIVE_INTENT_APPROVED"]
    assert len(events) == 1


def test_approve_is_blocked_when_portfolio_is_frozen(tmp_path) -> None:
    repo, portfolio, intent, service, _audit_log = _setup(tmp_path)
    repo.save_portfolio(portfolio.freeze("manual"))

    with pytest.raises(ValueError, match="APPROVAL_BLOCKED_BY_PORTFOLIO_STATE"):
        service.approve(intent.live_order_intent_id, "founder")


def test_reject_requires_a_real_reason(tmp_path) -> None:
    _repo, _portfolio, intent, service, _audit_log = _setup(tmp_path)
    with pytest.raises(ValueError, match="REJECTION_REASON_REQUIRED"):
        service.reject(intent.live_order_intent_id, "founder", "")


def test_reject_is_also_audited_fixing_papers_asymmetry(tmp_path) -> None:
    """The actual fix over PaperApprovalService: reject() must be audited
    too, given real-money stakes -- paper trading's reject() never is."""
    repo, _portfolio, intent, service, audit_log = _setup(tmp_path)

    approval = service.reject(intent.live_order_intent_id, "founder", "does not look right")

    assert approval.decision == LiveApprovalDecision.REJECTED
    updated_intent = repo.intents[intent.live_order_intent_id]
    assert updated_intent.intent_status == LiveIntentStatus.REJECTED

    events = [e for e in audit_log.list_events() if e.event_type == "LIVE_INTENT_REJECTED"]
    assert len(events) == 1
    assert events[0].after_state_json["reason"] == "does not look right"
