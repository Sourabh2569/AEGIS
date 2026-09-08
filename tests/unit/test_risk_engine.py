from __future__ import annotations

from decimal import Decimal

from aegis.risk.engine import (
    PortfolioRiskState,
    PositionSizingEngine,
    RiskDecision,
    RiskProfileVersion,
    state_multiplier,
)


def test_state_multiplier_for_every_risk_state() -> None:
    assert state_multiplier(PortfolioRiskState.NORMAL) == Decimal("1.00")
    assert state_multiplier(PortfolioRiskState.CAUTION) == Decimal("0.50")
    assert state_multiplier(PortfolioRiskState.DEFENSIVE) == Decimal("0.25")
    assert state_multiplier(PortfolioRiskState.CAPITAL_PRESERVATION) == Decimal("0.10")
    assert state_multiplier(PortfolioRiskState.FROZEN) == Decimal("0.05")
    # EMERGENCY_EXIT is the one true hard stop -- see below for why it's safe
    # to keep at zero: drawdown_state() can never produce it automatically.
    assert state_multiplier(PortfolioRiskState.EMERGENCY_EXIT) == Decimal("0.00")


def _assess(current_drawdown: Decimal):
    return PositionSizingEngine().assess(
        portfolio_id="p",
        strategy_id="s",
        instrument_id="i",
        portfolio_nav=Decimal(1_000_000),
        available_cash=Decimal(1_000_000),
        existing_position_value=Decimal(0),
        sector_value=Decimal(0),
        cluster_value=Decimal(0),
        gross_equity_value=Decimal(0),
        entry_price=Decimal(100),
        invalidation_price=Decimal(90),
        proposed_quantity=Decimal(100),
        sector="Financials",
        cluster="FINANCIALS",
        data_quality_status="GREEN",
        instrument_eligibility_status="ELIGIBLE",
        profile=RiskProfileVersion(),
        current_drawdown=current_drawdown,
    )


def test_capital_preservation_reduces_size_instead_of_blocking_it() -> None:
    """A -8% drawdown must still allow a small new position -- otherwise a
    fully-cash portfolio can never make a new high on its own and would be
    permanently locked out of ever recovering (the bug found via the real
    momentum backtest)."""
    assessment = _assess(Decimal("-0.08"))

    assert assessment.portfolio_risk_state == PortfolioRiskState.CAPITAL_PRESERVATION
    assert assessment.approved_quantity > 0
    assert assessment.decision == RiskDecision.APPROVED_WITH_REDUCED_SIZE
    assert not any("RISK_STATE_BLOCKS_NEW_EXPOSURE" in reason for reason in assessment.reason_codes)


def test_frozen_reduces_size_further_but_still_does_not_lock_out() -> None:
    """A -11% drawdown is more severe than CAPITAL_PRESERVATION and must size
    even smaller, but for the same reason as CAPITAL_PRESERVATION -- it is
    reached purely by drawdown-vs-high-water-mark math, and a fully-cash
    portfolio can never make a new high on its own -- it must not be an
    absolute zero, or the exact same permanent lockout recurs one tier up
    (which is what the real momentum backtest hit before this fix: the first
    pass only fixed CAPITAL_PRESERVATION and the strategy walked straight
    into a FROZEN dead end instead)."""
    assessment = _assess(Decimal("-0.11"))

    assert assessment.portfolio_risk_state == PortfolioRiskState.FROZEN
    assert assessment.approved_quantity > 0
    assert assessment.decision == RiskDecision.APPROVED_WITH_REDUCED_SIZE
    assert not any("RISK_STATE_BLOCKS_NEW_EXPOSURE" in reason for reason in assessment.reason_codes)


def test_frozen_sizes_smaller_than_capital_preservation() -> None:
    frozen = _assess(Decimal("-0.11"))
    capital_preservation = _assess(Decimal("-0.08"))

    assert frozen.approved_quantity < capital_preservation.approved_quantity


def test_emergency_exit_is_unreachable_via_drawdown_and_stays_a_hard_stop() -> None:
    """drawdown_state() never returns EMERGENCY_EXIT for any input -- it is
    reserved for a future explicit override (e.g. a kill-switch-style
    mechanism), not something the automatic drawdown ladder can walk into.
    That is exactly why it is safe to leave at a true zero multiplier: unlike
    CAPITAL_PRESERVATION/FROZEN, nothing can trigger it without an external
    decision, so it can't reproduce the same permanent-lockout bug."""
    for probe in [
        Decimal(0),
        Decimal("-0.05"),
        Decimal("-0.09"),
        Decimal("-0.50"),
        Decimal(-1),
    ]:
        assert _assess(probe).portfolio_risk_state != PortfolioRiskState.EMERGENCY_EXIT


def test_normal_state_is_unaffected() -> None:
    assessment = _assess(Decimal(0))

    assert assessment.portfolio_risk_state == PortfolioRiskState.NORMAL
    assert assessment.decision == RiskDecision.APPROVED
    assert assessment.reason_codes == []


def test_sell_is_not_capped_by_buy_capacity_constraints() -> None:
    """A SELL reduces exposure -- it must not be artificially shrunk by caps
    meant to gate new risk-taking (cash available, sector/cluster/strategy
    room, gross exposure headroom). Found via the paper-trading bridge: a
    real full-exit SELL of 44 shares was silently clamped to 43 because the
    engine applied buy-capacity math to every trade regardless of side."""
    assessment = PositionSizingEngine().assess(
        portfolio_id="p",
        strategy_id="s",
        instrument_id="i",
        portfolio_nav=Decimal(1_000_000),
        # Deliberately starved cash/sector/exposure room -- a BUY of this
        # size would be heavily constrained by qty_by_cash/qty_by_sector/
        # qty_by_exposure; a SELL must ignore all of that.
        available_cash=Decimal(0),
        existing_position_value=Decimal(500_000),
        sector_value=Decimal(900_000),
        cluster_value=Decimal(900_000),
        gross_equity_value=Decimal(950_000),
        entry_price=Decimal(100),
        invalidation_price=Decimal(90),
        proposed_quantity=Decimal(5000),
        sector="Financials",
        cluster="FINANCIALS",
        data_quality_status="GREEN",
        instrument_eligibility_status="ELIGIBLE",
        profile=RiskProfileVersion(),
        current_drawdown=Decimal(
            "-0.08"
        ),  # CAPITAL_PRESERVATION -- must not throttle a sell either
        side="SELL",
    )

    assert assessment.approved_quantity == Decimal("5000.000000")
    assert assessment.decision == RiskDecision.APPROVED


def test_buy_is_still_capped_by_capacity_constraints() -> None:
    """The side-aware change must not weaken BUY sizing -- only SELL skips
    the capacity caps."""
    assessment = PositionSizingEngine().assess(
        portfolio_id="p",
        strategy_id="s",
        instrument_id="i",
        portfolio_nav=Decimal(1_000_000),
        available_cash=Decimal(0),
        existing_position_value=Decimal(0),
        sector_value=Decimal(0),
        cluster_value=Decimal(0),
        gross_equity_value=Decimal(0),
        entry_price=Decimal(100),
        invalidation_price=Decimal(90),
        proposed_quantity=Decimal(5000),
        sector="Financials",
        cluster="FINANCIALS",
        data_quality_status="GREEN",
        instrument_eligibility_status="ELIGIBLE",
        profile=RiskProfileVersion(),
        current_drawdown=Decimal(0),
        side="BUY",
    )

    assert assessment.approved_quantity == Decimal("0.000000")
