from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from aegis.live_trading.domain import (
    LiveApproval,
    LiveApprovalDecision,
    LiveExecutionPreflight,
    LiveFill,
    LiveIncident,
    LiveIncidentType,
    LiveOrder,
    LiveOrderIntent,
    LiveOrderStatus,
    LivePortfolio,
    LivePortfolioConfiguration,
    LiveReconciliationRecord,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.shared.time import utc_now


def _portfolio(**overrides) -> LivePortfolio:
    kwargs = {
        "name": "Pilot",
        "description": "test pilot",
        "starting_capital": Decimal(400000),
        "pilot_capital_cap": Decimal(400000),
        "risk_profile_version_id": "v1",
        "portfolio_configuration_version": "v1",
        "created_by": "founder",
    }
    kwargs.update(overrides)
    return LivePortfolio(**kwargs)


def test_a_fresh_store_has_nothing_in_it(tmp_path: Path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live_trading.sqlite")
    assert repo.portfolios == {}
    assert repo.intents == {}
    assert repo.fills == {}


def test_a_saved_portfolio_round_trips_through_the_same_store(tmp_path: Path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live_trading.sqlite")
    portfolio = _portfolio()
    config = LivePortfolioConfiguration(
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
    )
    repo.add_portfolio(portfolio, config)

    assert repo.portfolios[portfolio.live_portfolio_id].name == "Pilot"
    assert repo.portfolio_configs[portfolio.live_portfolio_id].maximum_position_count == 50


def test_a_real_process_restart_still_sees_everything_a_prior_process_wrote(
    tmp_path: Path,
) -> None:
    """The actual point of this store: a brand-new SqliteLiveTradingRepository
    -- standing in for the API process restarting -- pointed at the same
    file must see everything a prior instance wrote, exactly like
    SqlitePaperTradingRepository already does."""
    db_path = tmp_path / "live_trading.sqlite"
    first_process = SqliteLiveTradingRepository(db_path)
    portfolio = _portfolio(clean_fill_count=7)
    config = LivePortfolioConfiguration(
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
    )
    first_process.add_portfolio(portfolio, config)

    now = utc_now()
    intent = LiveOrderIntent(
        live_portfolio_id=portfolio.live_portfolio_id,
        live_strategy_config_id="cfg1",
        strategy_version_id="DiversifiedRiskOverlayStrategyV2",
        instrument_id="AEGIS-IN-000001",
        side="BUY",
        proposed_quantity=Decimal(10),
        decision_time=now,
        available_data_cutoff=now,
        eligible_execution_time=now + timedelta(hours=1),
        risk_assessment_id="r1",
        configuration_version="v1",
        idempotency_key="k1",
        correlation_id="c1",
    )
    first_process.save_intent(intent)

    approval = LiveApproval(
        live_order_intent_id=intent.live_order_intent_id,
        approver_id="founder",
        decision=LiveApprovalDecision.APPROVED,
        decision_time=now,
        risk_assessment_id="r1",
        live_strategy_config_id="cfg1",
        reason="looks fine",
        expiry_time=now + timedelta(hours=18),
        confirmed_amount_nullable=Decimal("1234.56"),
    )
    first_process.save_approval(approval)

    order = LiveOrder(
        live_order_intent_id=intent.live_order_intent_id,
        live_portfolio_id=portfolio.live_portfolio_id,
        instrument_id="AEGIS-IN-000001",
        status=LiveOrderStatus.FILLED,
        requested_quantity=Decimal(10),
        idempotency_key="k1",
        broker_order_id_nullable="BROKER-ORDER-999",
        filled_quantity=Decimal(10),
    )
    first_process.save_order(order)

    fill = LiveFill(
        live_order_id=order.live_order_id,
        live_portfolio_id=portfolio.live_portfolio_id,
        instrument_id="AEGIS-IN-000001",
        fill_time=now,
        fill_quantity=Decimal(10),
        fill_price=Decimal("1234.5600"),
        broker_fill_reference="BROKER-FILL-1",
        gross_notional=Decimal("12345.6000"),
        cost_total=Decimal("12.3400"),
        net_cash_effect=Decimal("-12357.9400"),
        settlement_date=now.date(),
        fill_status="COMPLETE",
    )
    first_process.save_fill(fill)

    incident = LiveIncident(
        live_portfolio_id=portfolio.live_portfolio_id,
        incident_type=LiveIncidentType.RECONCILIATION_INCIDENT,
        severity="HIGH",
        description="a real mismatch",
        status="OPEN",
        reason_codes=["POSITION_MISMATCH"],
    )
    first_process.save_incident(incident)

    reconciliation = LiveReconciliationRecord(
        live_portfolio_id=portfolio.live_portfolio_id,
        reconciliation_time=now,
        expected_nav=Decimal("400000.0000"),
        observed_nav=Decimal("399000.0000"),
        status="RED",
        reason_codes=["POSITION_MISMATCH"],
    )
    first_process.add_reconciliation(reconciliation)

    preflight = LiveExecutionPreflight(
        live_order_intent_id=intent.live_order_intent_id,
        live_portfolio_id=portfolio.live_portfolio_id,
        checked_at=now,
        passed=True,
        check_results={"kill_switches": True, "capital_cap": True},
    )
    first_process.save_preflight(preflight)

    second_process = SqliteLiveTradingRepository(db_path)

    assert second_process.portfolios[portfolio.live_portfolio_id].clean_fill_count == 7
    assert second_process.intents[intent.live_order_intent_id].instrument_id == "AEGIS-IN-000001"
    assert second_process.approvals[
        intent.live_order_intent_id
    ].confirmed_amount_nullable == Decimal("1234.56")
    assert second_process.orders[order.live_order_id].broker_order_id_nullable == "BROKER-ORDER-999"
    assert second_process.fills[fill.live_fill_id].fill_price == Decimal("1234.5600")
    assert second_process.fills[fill.live_fill_id].broker_fill_reference == "BROKER-FILL-1"
    assert (
        second_process.incidents[incident.id].incident_type
        == LiveIncidentType.RECONCILIATION_INCIDENT
    )
    assert second_process.reconciliations[portfolio.live_portfolio_id][0].status == "RED"
    assert second_process.preflights[preflight.id].passed is True
    # research_portfolios is never persisted directly -- it must be
    # correctly rebuilt from the persisted BUY fill above on restart.
    reloaded_ledger = second_process.research_portfolios[portfolio.live_portfolio_id]
    assert reloaded_ledger.positions["AEGIS-IN-000001"] == Decimal("10.000000")
    assert reloaded_ledger.cash == portfolio.starting_capital - Decimal("12357.9400")


def test_re_saving_the_same_portfolio_replaces_it_not_duplicates_it(tmp_path: Path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live_trading.sqlite")
    portfolio = _portfolio()
    config = LivePortfolioConfiguration(
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
    )
    repo.add_portfolio(portfolio, config)
    updated = portfolio.record_clean_fill()
    repo.save_portfolio(updated)

    reloaded = SqliteLiveTradingRepository(tmp_path / "live_trading.sqlite")
    assert len(reloaded.portfolios) == 1
    assert reloaded.portfolios[portfolio.live_portfolio_id].clean_fill_count == 1
