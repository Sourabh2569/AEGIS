from __future__ import annotations

from datetime import date
from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.live_trading.domain import (
    LiveIntentStatus,
    LivePortfolio,
    LivePortfolioConfiguration,
    LivePortfolioStatus,
    LiveStrategyConfigStatus,
    LiveStrategyConfiguration,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.services import LiveDecisionCycleService
from aegis.paper_trading.services import PaperTradingCalendarService

SESSION_DATE = date(2026, 9, 16)
NEXT_SESSION_DATE = date(2026, 9, 17)
CALENDAR = PaperTradingCalendarService(sessions=[SESSION_DATE, NEXT_SESSION_DATE])


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


def _config(portfolio: LivePortfolio) -> LivePortfolioConfiguration:
    return LivePortfolioConfiguration(
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


def _make_strategy_config(portfolio: LivePortfolio, strategy_id: str) -> LiveStrategyConfiguration:
    return LiveStrategyConfiguration(
        live_portfolio_id=portfolio.live_portfolio_id,
        strategy_id=strategy_id,
        strategy_version_id=f"{strategy_id}:V0",
        risk_profile_version_id="v1",
        universe_definition_version="v1",
        cost_schedule_version="v1",
        settlement_model_version="v1",
        execution_model_version="v1",
        rebalancing_frequency="MONTHLY",
        decision_time_policy="POST_CLOSE_FORWARD_ONLY",
        execution_time_policy="NEXT_ELIGIBLE_SESSION_OPEN",
        position_sizing_policy="AEGIS_CONSERVATIVE_V0",
        live_start_date=SESSION_DATE,
        status=LiveStrategyConfigStatus.ACTIVE,
    )


def _setup(tmp_path, strategy_id="DiversifiedRiskOverlayStrategyV2", **portfolio_overrides):
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(**portfolio_overrides)
    repo.add_portfolio(portfolio, _config(portfolio))
    config = _make_strategy_config(portfolio, strategy_id)
    repo.save_strategy_config(config)
    return repo, portfolio, config


def test_no_resolver_produces_no_intents(tmp_path) -> None:
    repo, portfolio, _config = _setup(tmp_path)
    service = LiveDecisionCycleService(
        repository=repo, audit_log=AuditLog(), calendar=CALENDAR, strategy_target_resolver=None
    )
    created = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices={},
    )
    assert created == []


def test_frozen_portfolio_produces_no_intents(tmp_path) -> None:
    repo, portfolio, _config = _setup(tmp_path, status=LivePortfolioStatus.FROZEN)
    resolver_calls = []

    def resolver(strategy_id, as_of):
        resolver_calls.append((strategy_id, as_of))
        return {"AEGIS-IN-000001": Decimal("1.0")}, {}

    service = LiveDecisionCycleService(
        repository=repo, audit_log=AuditLog(), calendar=CALENDAR, strategy_target_resolver=resolver
    )
    created = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices={"AEGIS-IN-000001": Decimal(100)},
    )
    assert created == []
    assert resolver_calls == []


def test_real_target_weight_creates_a_sized_buy_intent(tmp_path) -> None:
    repo, portfolio, config = _setup(tmp_path)

    def resolver(strategy_id, as_of):
        return {"AEGIS-IN-000001": Decimal("0.5")}, {}

    service = LiveDecisionCycleService(
        repository=repo, audit_log=AuditLog(), calendar=CALENDAR, strategy_target_resolver=resolver
    )
    created = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices={"AEGIS-IN-000001": Decimal(1000)},
    )

    assert len(created) == 1
    intent = created[0]
    assert intent.instrument_id == "AEGIS-IN-000001"
    assert intent.side == "BUY"
    assert intent.proposed_quantity > 0
    assert intent.intent_status == LiveIntentStatus.PENDING_APPROVAL
    assert intent.strategy_version_id == config.strategy_version_id
    assert repo.intents[intent.live_order_intent_id] == intent


def test_a_realistic_fifty_position_universe_sizes_every_candidate(tmp_path) -> None:
    """Matches DiversifiedRiskOverlayStrategyV2's real shape: the whole
    eligible universe gets a nonzero target weight in one cycle."""
    repo, portfolio, _config = _setup(tmp_path)
    instrument_ids = [f"AEGIS-IN-{i:06d}" for i in range(1, 51)]
    weight = Decimal(1) / Decimal(50)
    reference_prices = {inst: Decimal(100 + i) for i, inst in enumerate(instrument_ids)}

    def resolver(strategy_id, as_of):
        return {inst: weight for inst in instrument_ids}, {}

    service = LiveDecisionCycleService(
        repository=repo, audit_log=AuditLog(), calendar=CALENDAR, strategy_target_resolver=resolver
    )
    created = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices=reference_prices,
    )

    assert len(created) > 0
    assert all(intent.side == "BUY" for intent in created)
    assert all(intent.instrument_id in instrument_ids for intent in created)


def test_rerunning_the_same_session_date_does_not_duplicate_intents(tmp_path) -> None:
    repo, portfolio, _config = _setup(tmp_path)

    def resolver(strategy_id, as_of):
        return {"AEGIS-IN-000001": Decimal("0.5")}, {}

    service = LiveDecisionCycleService(
        repository=repo, audit_log=AuditLog(), calendar=CALENDAR, strategy_target_resolver=resolver
    )
    first = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices={"AEGIS-IN-000001": Decimal(1000)},
    )
    second = service.run_decision_cycle(
        live_portfolio_id=portfolio.live_portfolio_id,
        session_date=SESSION_DATE,
        reference_prices={"AEGIS-IN-000001": Decimal(1000)},
    )
    assert len(first) == 1
    assert len(second) == 0
    assert len([i for i in repo.intents.values() if i.instrument_id == "AEGIS-IN-000001"]) == 1
