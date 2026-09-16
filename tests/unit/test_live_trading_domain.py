from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from aegis.live_trading.domain import (
    LIVE_LABELS,
    LiveApproval,
    LiveApprovalDecision,
    LiveCapitalTier,
    LiveExecutionPreflight,
    LiveFill,
    LiveOrderIntent,
    LivePortfolio,
    LivePortfolioStatus,
)
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


def test_pilot_capital_cap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive real amount"):
        _portfolio(pilot_capital_cap=Decimal(0))
    with pytest.raises(ValueError, match="positive real amount"):
        _portfolio(pilot_capital_cap=Decimal(-1000))


def test_new_portfolio_defaults_to_pilot_tier_with_zero_clean_fills() -> None:
    portfolio = _portfolio()
    assert portfolio.capital_tier == LiveCapitalTier.PILOT
    assert portfolio.clean_fill_count == 0
    assert portfolio.status == LivePortfolioStatus.DRAFT


def test_labels_are_honest_about_real_capital() -> None:
    assert _portfolio().labels == LIVE_LABELS
    assert "REAL_CAPITAL_AT_RISK" in LIVE_LABELS
    assert "NOT_A_SIMULATION" in LIVE_LABELS


def test_activate_requires_ready_or_setup_pending() -> None:
    portfolio = _portfolio()
    with pytest.raises(ValueError):
        portfolio.activate()
    ready = _portfolio(status=LivePortfolioStatus.READY)
    activated = ready.activate()
    assert activated.status == LivePortfolioStatus.ACTIVE
    assert activated.activated_at_nullable is not None


def test_pause_then_resume_round_trips() -> None:
    active = _portfolio(status=LivePortfolioStatus.ACTIVE)
    paused = active.pause("manual review")
    assert paused.status == LivePortfolioStatus.PAUSED
    assert paused.failure_reason_nullable == "manual review"
    resumed = paused.resume()
    assert resumed.status == LivePortfolioStatus.ACTIVE
    assert resumed.paused_at_nullable is None


def test_resume_requires_paused_status() -> None:
    with pytest.raises(ValueError):
        _portfolio(status=LivePortfolioStatus.ACTIVE).resume()


def test_clean_fill_count_increments_and_resets() -> None:
    portfolio = _portfolio()
    incremented = portfolio.record_clean_fill().record_clean_fill().record_clean_fill()
    assert incremented.clean_fill_count == 3
    reset = incremented.reset_clean_fill_count()
    assert reset.clean_fill_count == 0


def test_graduate_requires_pilot_tier() -> None:
    full = _portfolio(capital_tier=LiveCapitalTier.FULL)
    with pytest.raises(ValueError, match="PILOT-tier"):
        full.graduate(new_capital_cap=Decimal(1000000), graduated_by="founder")


def test_graduate_transitions_to_full_with_a_real_audit_trail() -> None:
    portfolio = _portfolio(clean_fill_count=20)
    graduated = portfolio.graduate(new_capital_cap=Decimal(1000000), graduated_by="founder")
    assert graduated.capital_tier == LiveCapitalTier.FULL
    assert graduated.pilot_capital_cap == Decimal("1000000.0000")
    assert graduated.graduated_by_nullable == "founder"
    assert graduated.graduated_at_nullable is not None
    # graduate() itself never checks the clean-fill threshold -- that's the
    # caller's (service-layer) responsibility, matching activate()/pause()
    # only enforcing their own state-machine shape.


def test_intent_rejects_data_timing_violation() -> None:
    now = utc_now()
    with pytest.raises(ValueError, match="DATA_TIMING_VIOLATION"):
        LiveOrderIntent(
            live_portfolio_id="p1",
            live_strategy_config_id="cfg",
            strategy_version_id="DiversifiedRiskOverlayStrategyV2",
            instrument_id="AEGIS-IN-000001",
            side="BUY",
            proposed_quantity=Decimal(10),
            decision_time=now,
            available_data_cutoff=now + timedelta(hours=1),  # after decision -- invalid
            eligible_execution_time=now + timedelta(hours=2),
            risk_assessment_id="r1",
            configuration_version="v1",
            idempotency_key="k1",
            correlation_id="c1",
        )


def test_intent_rejects_execution_not_after_decision() -> None:
    now = utc_now()
    with pytest.raises(ValueError, match="EXECUTION_NOT_AFTER_DECISION"):
        LiveOrderIntent(
            live_portfolio_id="p1",
            live_strategy_config_id="cfg",
            strategy_version_id="DiversifiedRiskOverlayStrategyV2",
            instrument_id="AEGIS-IN-000001",
            side="BUY",
            proposed_quantity=Decimal(10),
            decision_time=now,
            available_data_cutoff=now,
            eligible_execution_time=now,  # not after decision_time -- invalid
            risk_assessment_id="r1",
            configuration_version="v1",
            idempotency_key="k1",
            correlation_id="c1",
        )


def test_approval_is_valid_only_when_approved_and_unexpired() -> None:
    now = utc_now()
    approved = LiveApproval(
        live_order_intent_id="i1",
        approver_id="founder",
        decision=LiveApprovalDecision.APPROVED,
        decision_time=now,
        risk_assessment_id="r1",
        live_strategy_config_id="cfg",
        reason="looks fine",
        expiry_time=now + timedelta(hours=1),
    )
    assert approved.is_valid_at(now) is True
    assert approved.is_valid_at(now + timedelta(hours=2)) is False

    rejected = LiveApproval(
        live_order_intent_id="i1",
        approver_id="founder",
        decision=LiveApprovalDecision.REJECTED,
        decision_time=now,
        risk_assessment_id="r1",
        live_strategy_config_id="cfg",
        reason="not today",
        expiry_time=now + timedelta(hours=1),
    )
    assert rejected.is_valid_at(now) is False


def test_live_fill_has_no_simulated_price_field() -> None:
    """The actual safety guarantee: there is no field on this dataclass a
    caller could accidentally populate with a fabricated/simulated price."""
    fill_fields = set(LiveFill.__dataclass_fields__.keys())
    assert "simulated_fill_price" not in fill_fields
    assert "slippage_amount" not in fill_fields
    assert "slippage_bps" not in fill_fields
    assert "fill_price" in fill_fields
    assert "broker_fill_reference" in fill_fields


def test_execution_preflight_records_every_check_not_just_pass_fail() -> None:
    preflight = LiveExecutionPreflight(
        live_order_intent_id="i1",
        live_portfolio_id="p1",
        checked_at=utc_now(),
        passed=False,
        check_results={
            "kill_switches": True,
            "portfolio_status": True,
            "market_open": True,
            "approval_valid": True,
            "capital_cap": False,
            "broker_healthy": True,
            "idempotency": True,
            "minimum_notional": True,
        },
        failure_reasons=["capital_cap"],
    )
    assert preflight.passed is False
    assert preflight.check_results["capital_cap"] is False
    assert "capital_cap" in preflight.failure_reasons
