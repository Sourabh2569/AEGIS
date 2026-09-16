from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from aegis.live_trading.domain import (
    LiveApproval,
    LiveApprovalDecision,
    LiveCapitalTier,
    LiveOrderIntent,
    LivePortfolio,
    LivePortfolioStatus,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.preflight import ExecutionPreflightGate
from aegis.paper_trading.services import PaperTradingCalendarService
from aegis.provider_adapters.base import ProviderHealthResult
from aegis.risk.engine import KillSwitch, KillSwitchType
from aegis.shared.time import utc_now


class FakeHealthyOrderAdapter:
    name = "kite_connect_orders"

    def get_health_status(self) -> ProviderHealthResult:
        return ProviderHealthResult(healthy=True, message="ready")


class FakeUnhealthyOrderAdapter:
    name = "kite_connect_orders"

    def get_health_status(self) -> ProviderHealthResult:
        return ProviderHealthResult(healthy=False, message="not configured")


NOW = utc_now()
EXECUTION_TIME = NOW
CALENDAR = PaperTradingCalendarService(sessions=[NOW.date() - timedelta(days=1), NOW.date()])


def _portfolio(**overrides) -> LivePortfolio:
    kwargs = dict(
        name="Pilot",
        description="test",
        starting_capital=Decimal(400000),
        pilot_capital_cap=Decimal(400000),
        risk_profile_version_id="v1",
        portfolio_configuration_version="v1",
        created_by="founder",
        status=LivePortfolioStatus.ACTIVE,
    )
    kwargs.update(overrides)
    return LivePortfolio(**kwargs)


def _intent(portfolio: LivePortfolio, *, proposed_quantity=Decimal(10), idempotency_key="k1") -> LiveOrderIntent:
    decision_time = NOW - timedelta(minutes=5)
    return LiveOrderIntent(
        live_portfolio_id=portfolio.live_portfolio_id,
        live_strategy_config_id="cfg1",
        strategy_version_id="DiversifiedRiskOverlayStrategyV2",
        instrument_id="AEGIS-IN-000001",
        side="BUY",
        proposed_quantity=proposed_quantity,
        decision_time=decision_time,
        available_data_cutoff=decision_time,
        eligible_execution_time=NOW + timedelta(hours=1),
        risk_assessment_id="r1",
        configuration_version="v1",
        idempotency_key=idempotency_key,
        correlation_id="c1",
    )


def _valid_approval(intent: LiveOrderIntent) -> LiveApproval:
    return LiveApproval(
        live_order_intent_id=intent.live_order_intent_id,
        approver_id="founder",
        decision=LiveApprovalDecision.APPROVED,
        decision_time=NOW,
        risk_assessment_id="r1",
        live_strategy_config_id="cfg1",
        reason="looks fine",
        expiry_time=NOW + timedelta(hours=18),
    )


def _gate(tmp_path, adapter=None) -> tuple[ExecutionPreflightGate, SqliteLiveTradingRepository]:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    gate = ExecutionPreflightGate(
        repository=repo, calendar=CALENDAR, order_adapter=adapter or FakeHealthyOrderAdapter()
    )
    return gate, repo


def test_all_green_passes_and_records_every_check(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))

    preflight = gate.check(
        intent=intent,
        portfolio=portfolio,
        execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000),
        existing_deployed_notional=Decimal(0),
        kill_switches=[],
    )
    assert preflight.passed is True
    assert preflight.failure_reasons == []
    assert set(preflight.check_results.keys()) == {
        "kill_switches", "portfolio_status", "market_open", "approval_valid",
        "capital_cap", "broker_healthy", "idempotency", "minimum_notional",
    }
    assert all(preflight.check_results.values())


def test_active_global_kill_switch_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    switch = KillSwitch(switch_type=KillSwitchType.GLOBAL_TRADING_KILL_SWITCH, scope_id="GLOBAL", is_active=True, reason="halt")

    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[switch],
    )
    assert preflight.passed is False
    assert "kill_switches" in preflight.failure_reasons


def test_active_broker_adapter_kill_switch_blocks_via_adapter_name_scope(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    switch = KillSwitch(
        switch_type=KillSwitchType.BROKER_ADAPTER_KILL_SWITCH,
        scope_id="kite_connect_orders",
        is_active=True,
        reason="broker under maintenance",
    )
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[switch],
    )
    assert preflight.passed is False
    assert "kill_switches" in preflight.failure_reasons


def test_inactive_kill_switch_does_not_block(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    switch = KillSwitch(switch_type=KillSwitchType.GLOBAL_TRADING_KILL_SWITCH, scope_id="GLOBAL", is_active=False)
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[switch],
    )
    assert preflight.passed is True


def test_frozen_portfolio_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio(status=LivePortfolioStatus.FROZEN)
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "portfolio_status" in preflight.failure_reasons


def test_market_closed_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    closed_day = NOW.replace(year=2020, month=1, day=1)  # not in CALENDAR.sessions
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=closed_day,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "market_open" in preflight.failure_reasons


def test_missing_approval_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    # no approval saved at all
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "approval_valid" in preflight.failure_reasons


def test_expired_approval_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio)
    expired = LiveApproval(
        live_order_intent_id=intent.live_order_intent_id,
        approver_id="founder",
        decision=LiveApprovalDecision.APPROVED,
        decision_time=NOW - timedelta(hours=20),
        risk_assessment_id="r1",
        live_strategy_config_id="cfg1",
        reason="looks fine",
        expiry_time=NOW - timedelta(hours=1),
    )
    repo.save_approval(expired)
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "approval_valid" in preflight.failure_reasons


def test_pilot_capital_cap_exceeded_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio(pilot_capital_cap=Decimal(5000), capital_tier=LiveCapitalTier.PILOT)
    intent = _intent(portfolio, proposed_quantity=Decimal(10))
    repo.save_approval(_valid_approval(intent))
    # 10 shares * Rs 1000 = Rs 10,000 notional, already Rs 4,000 deployed -> exceeds Rs 5,000 cap
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(4000), kill_switches=[],
    )
    assert preflight.passed is False
    assert "capital_cap" in preflight.failure_reasons


def test_pilot_capital_cap_is_not_checked_once_graduated_to_full(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio(
        pilot_capital_cap=Decimal(5000), capital_tier=LiveCapitalTier.FULL
    )
    intent = _intent(portfolio, proposed_quantity=Decimal(1000))
    repo.save_approval(_valid_approval(intent))
    # Would massively exceed the old pilot cap, but capital_tier is FULL now.
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.check_results["capital_cap"] is True


def test_unhealthy_broker_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path, adapter=FakeUnhealthyOrderAdapter())
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "broker_healthy" in preflight.failure_reasons


def test_duplicate_idempotency_key_blocks(tmp_path) -> None:
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio, idempotency_key="already-used")
    repo.save_approval(_valid_approval(intent))
    repo.executed_idempotency_keys.add("already-used")
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "idempotency" in preflight.failure_reasons


def test_below_minimum_trade_notional_blocks(tmp_path) -> None:
    """The real, not theoretical, concern for a broadly diversified
    rebalancing strategy: a tiny per-position allocation must be blocked,
    never silently rounded up to fabricate a fill."""
    gate, repo = _gate(tmp_path)
    portfolio = _portfolio()
    intent = _intent(portfolio, proposed_quantity=Decimal("0.4"))
    repo.save_approval(_valid_approval(intent))
    # 0.4 shares * Rs 100 = Rs 40 notional, well under the Rs 500 floor.
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(100), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "minimum_notional" in preflight.failure_reasons


def test_an_exception_during_a_check_fails_closed_not_propagates(tmp_path) -> None:
    """Fail-closed on uncertainty -- an adapter that raises must be treated
    as unhealthy, not crash the whole preflight evaluation."""

    class ExplodingAdapter:
        name = "kite_connect_orders"

        def get_health_status(self):
            raise RuntimeError("network error")

    gate, repo = _gate(tmp_path, adapter=ExplodingAdapter())
    portfolio = _portfolio()
    intent = _intent(portfolio)
    repo.save_approval(_valid_approval(intent))
    preflight = gate.check(
        intent=intent, portfolio=portfolio, execution_time=EXECUTION_TIME,
        entry_price=Decimal(1000), existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert preflight.passed is False
    assert "broker_healthy" in preflight.failure_reasons
    # Every other check still ran and was recorded -- one exploding check
    # must not skip the rest.
    assert len(preflight.check_results) == 8
