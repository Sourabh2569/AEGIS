from __future__ import annotations

from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.live_trading.domain import (
    LiveIncidentType,
    LivePortfolio,
    LivePortfolioConfiguration,
    LivePortfolioStatus,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.reconciliation import LiveReconciliationService


class FakeOrderAdapter:
    name = "kite_connect_orders"

    def __init__(self, positions=None, margins=None, raise_error=False):
        self._positions = positions or {}
        self._margins = margins or {}
        self._raise_error = raise_error

    def get_positions(self):
        if self._raise_error:
            raise RuntimeError("broker unreachable")
        return self._positions

    def get_margins(self):
        return self._margins


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


def _service(tmp_path, adapter, nav_calculator):
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    service = LiveReconciliationService(
        repository=repo,
        order_adapter=adapter,
        audit_log=AuditLog(),
        observed_nav_calculator=nav_calculator,
    )
    return repo, service


def test_matching_nav_is_green_and_does_not_freeze(tmp_path) -> None:
    portfolio = _portfolio()
    adapter = FakeOrderAdapter(margins={"net": "400000.00"})
    repo, service = _service(tmp_path, adapter, lambda positions, margins: Decimal(margins["net"]))
    repo.add_portfolio(portfolio, _config(portfolio))

    record = service.reconcile(
        live_portfolio_id=portfolio.live_portfolio_id, expected_nav=Decimal(400000)
    )

    assert record.status == "GREEN"
    assert repo.portfolios[portfolio.live_portfolio_id].status == LivePortfolioStatus.ACTIVE
    assert repo.incidents == {}


def test_a_small_rounding_difference_is_still_green(tmp_path) -> None:
    portfolio = _portfolio()
    adapter = FakeOrderAdapter(margins={"net": "399990.00"})  # 0.0025% off
    repo, service = _service(tmp_path, adapter, lambda positions, margins: Decimal(margins["net"]))
    repo.add_portfolio(portfolio, _config(portfolio))

    record = service.reconcile(
        live_portfolio_id=portfolio.live_portfolio_id, expected_nav=Decimal(400000)
    )
    assert record.status == "GREEN"


def test_a_real_material_mismatch_is_red_and_freezes_the_portfolio(tmp_path) -> None:
    portfolio = _portfolio(clean_fill_count=15)
    adapter = FakeOrderAdapter(margins={"net": "350000.00"})  # 12.5% off -- material
    repo, service = _service(tmp_path, adapter, lambda positions, margins: Decimal(margins["net"]))
    repo.add_portfolio(portfolio, _config(portfolio))
    repo.save_portfolio(portfolio)

    record = service.reconcile(
        live_portfolio_id=portfolio.live_portfolio_id, expected_nav=Decimal(400000)
    )

    assert record.status == "RED"
    updated = repo.portfolios[portfolio.live_portfolio_id]
    assert updated.status == LivePortfolioStatus.FROZEN
    assert updated.clean_fill_count == 0
    assert len(repo.incidents) == 1
    incident = next(iter(repo.incidents.values()))
    assert incident.incident_type == LiveIncidentType.RECONCILIATION_INCIDENT


def test_a_broker_call_failure_is_treated_as_red_not_a_crash(tmp_path) -> None:
    """Fail closed: if we can't even verify the broker's real state, we
    must not assume everything is fine."""
    portfolio = _portfolio()
    adapter = FakeOrderAdapter(raise_error=True)
    repo, service = _service(tmp_path, adapter, lambda positions, margins: Decimal(0))
    repo.add_portfolio(portfolio, _config(portfolio))

    record = service.reconcile(
        live_portfolio_id=portfolio.live_portfolio_id, expected_nav=Decimal(400000)
    )

    assert record.status == "RED"
    assert "RECONCILIATION_CALL_FAILED" in record.reason_codes[0]
    assert repo.portfolios[portfolio.live_portfolio_id].status == LivePortfolioStatus.FROZEN


def test_both_navs_zero_is_green_not_a_division_by_zero_crash(tmp_path) -> None:
    portfolio = _portfolio()
    adapter = FakeOrderAdapter(margins={"net": "0"})
    repo, service = _service(tmp_path, adapter, lambda positions, margins: Decimal(margins["net"]))
    repo.add_portfolio(portfolio, _config(portfolio))

    record = service.reconcile(
        live_portfolio_id=portfolio.live_portfolio_id, expected_nav=Decimal(0)
    )
    assert record.status == "GREEN"
