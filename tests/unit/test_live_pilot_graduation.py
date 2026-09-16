from __future__ import annotations

from decimal import Decimal

import pytest
from aegis.audit.service import AuditLog
from aegis.live_trading.domain import LiveCapitalTier, LivePortfolio, LivePortfolioConfiguration
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.services import GRADUATION_CLEAN_FILL_THRESHOLD, graduate_live_portfolio


def _portfolio(**overrides) -> LivePortfolio:
    kwargs = dict(
        name="Pilot", description="test", starting_capital=Decimal(400000),
        pilot_capital_cap=Decimal(400000), risk_profile_version_id="v1",
        portfolio_configuration_version="v1", created_by="founder",
    )
    kwargs.update(overrides)
    return LivePortfolio(**kwargs)


def _config(portfolio: LivePortfolio) -> LivePortfolioConfiguration:
    return LivePortfolioConfiguration(
        live_portfolio_id=portfolio.live_portfolio_id, version="v1", risk_profile_version_id="v1",
        minimum_cash_weight=Decimal("0.20"), maximum_gross_equity_exposure=Decimal("0.80"),
        maximum_position_count=50, settlement_model_version="v1", cost_schedule_version="v1",
        execution_model_version="v1", market_calendar_policy="NSE_STANDARD", valuation_policy="CLOSE",
        corporate_action_policy="FREEZE_ON_UNSUPPORTED", created_by="founder",
    )


def test_graduation_threshold_is_twenty() -> None:
    assert GRADUATION_CLEAN_FILL_THRESHOLD == 20


def test_graduate_rejected_below_the_clean_fill_threshold(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=19)
    repo.add_portfolio(portfolio, _config(portfolio))

    with pytest.raises(ValueError, match="GRADUATION_THRESHOLD_NOT_MET"):
        graduate_live_portfolio(
            repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
            reason="ready to scale", confirmed_new_capital_amount=Decimal(1000000),
            graduated_by="founder", audit_log=AuditLog(),
        )
    assert repo.portfolios[portfolio.live_portfolio_id].capital_tier == LiveCapitalTier.PILOT


def test_graduate_rejected_without_a_real_reason(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=20)
    repo.add_portfolio(portfolio, _config(portfolio))

    with pytest.raises(ValueError, match="REASON_REQUIRED"):
        graduate_live_portfolio(
            repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
            reason="   ", confirmed_new_capital_amount=Decimal(1000000),
            graduated_by="founder", audit_log=AuditLog(),
        )


def test_graduate_rejected_without_a_positive_confirmed_amount(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=20)
    repo.add_portfolio(portfolio, _config(portfolio))

    with pytest.raises(ValueError, match="positive real amount"):
        graduate_live_portfolio(
            repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
            reason="ready", confirmed_new_capital_amount=Decimal(0),
            graduated_by="founder", audit_log=AuditLog(),
        )


def test_graduate_succeeds_at_exactly_the_threshold_with_a_real_audit_trail(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=20)
    repo.add_portfolio(portfolio, _config(portfolio))
    audit_log = AuditLog()

    graduated = graduate_live_portfolio(
        repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
        reason="20 clean fills, real evidence looks solid", confirmed_new_capital_amount=Decimal(1500000),
        graduated_by="founder", audit_log=audit_log,
    )

    assert graduated.capital_tier == LiveCapitalTier.FULL
    assert graduated.pilot_capital_cap == Decimal("1500000.0000")
    assert graduated.graduated_by_nullable == "founder"
    assert repo.portfolios[portfolio.live_portfolio_id].capital_tier == LiveCapitalTier.FULL

    graduation_events = [
        event for event in audit_log.list_events() if event.event_type == "LIVE_PORTFOLIO_GRADUATED"
    ]
    assert len(graduation_events) == 1
    assert graduation_events[0].after_state_json["clean_fill_count_at_graduation"] == 20


def test_graduate_above_the_threshold_also_succeeds(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=57)
    repo.add_portfolio(portfolio, _config(portfolio))

    graduated = graduate_live_portfolio(
        repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
        reason="well past threshold", confirmed_new_capital_amount=Decimal(2000000),
        graduated_by="founder", audit_log=AuditLog(),
    )
    assert graduated.capital_tier == LiveCapitalTier.FULL


def test_graduate_rejected_when_already_full_tier(tmp_path) -> None:
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    portfolio = _portfolio(clean_fill_count=25, capital_tier=LiveCapitalTier.FULL)
    repo.add_portfolio(portfolio, _config(portfolio))

    with pytest.raises(ValueError, match="PILOT-tier"):
        graduate_live_portfolio(
            repository=repo, live_portfolio_id=portfolio.live_portfolio_id,
            reason="trying again", confirmed_new_capital_amount=Decimal(1000000),
            graduated_by="founder", audit_log=AuditLog(),
        )
