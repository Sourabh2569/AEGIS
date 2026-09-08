from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from enum import Enum
from typing import Any

from aegis.shared.ids import new_id
from aegis.shared.money import money, quantity
from aegis.shared.time import utc_now


class StrEnum(str, Enum):
    pass


class PortfolioRiskState(StrEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DEFENSIVE = "DEFENSIVE"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    FROZEN = "FROZEN"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"


class RiskDecision(StrEnum):
    APPROVED = "APPROVED"
    APPROVED_WITH_REDUCED_SIZE = "APPROVED_WITH_REDUCED_SIZE"
    DEFERRED = "DEFERRED"
    REJECTED = "REJECTED"
    ESCALATED_FOR_REVIEW = "ESCALATED_FOR_REVIEW"


class KillSwitchType(StrEnum):
    GLOBAL_TRADING_KILL_SWITCH = "GLOBAL_TRADING_KILL_SWITCH"
    PORTFOLIO_KILL_SWITCH = "PORTFOLIO_KILL_SWITCH"
    STRATEGY_KILL_SWITCH = "STRATEGY_KILL_SWITCH"
    INSTRUMENT_KILL_SWITCH = "INSTRUMENT_KILL_SWITCH"
    DATA_PROVIDER_KILL_SWITCH = "DATA_PROVIDER_KILL_SWITCH"


@dataclass(frozen=True)
class RiskProfileVersion:
    profile_id: str = "AEGIS_CONSERVATIVE"
    profile_version: str = "AEGIS_CONSERVATIVE_V0"
    maximum_risk_budget_per_position: Decimal = Decimal("0.005")
    maximum_total_active_risk_budget: Decimal = Decimal("0.03")
    maximum_single_position_weight: Decimal = Decimal("0.10")
    maximum_sector_weight: Decimal = Decimal("0.25")
    maximum_cluster_weight: Decimal = Decimal("0.30")
    maximum_gross_equity_exposure_normal: Decimal = Decimal("0.80")
    minimum_cash_weight_normal: Decimal = Decimal("0.20")
    maximum_position_count: int = 8
    minimum_position_count_when_deployed: int = 5
    strategy_allocation_cap: Decimal = Decimal("0.80")
    configured_gap_risk_amount: Decimal = Decimal(5)
    minimum_trade_notional: Decimal = Decimal(500)
    effective_from: datetime = field(default_factory=utc_now)
    effective_to: datetime | None = None


@dataclass(frozen=True)
class KillSwitch:
    switch_type: KillSwitchType
    scope_id: str
    is_active: bool = False
    reason: str = ""
    id: str = field(default_factory=lambda: new_id("kill-switch"))
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RiskAssessment:
    portfolio_id: str
    strategy_id: str
    instrument_id: str
    assessment_time: datetime
    portfolio_risk_state: PortfolioRiskState
    market_regime: str
    proposed_quantity: Decimal
    approved_quantity: Decimal
    position_weight_before: Decimal
    position_weight_after: Decimal
    sector_weight_before: Decimal
    sector_weight_after: Decimal
    cluster_weight_before: Decimal
    cluster_weight_after: Decimal
    available_cash_before: Decimal
    available_cash_after: Decimal
    risk_budget_before: Decimal
    risk_budget_after: Decimal
    data_quality_status: str
    instrument_eligibility_status: str
    decision: RiskDecision
    reason_codes: list[str]
    risk_profile_version: str
    risk_assessment_id: str = field(default_factory=lambda: new_id("risk-assessment"))
    created_at: datetime = field(default_factory=utc_now)


def drawdown_state(drawdown: Decimal) -> PortfolioRiskState:
    if drawdown <= Decimal("-0.10"):
        return PortfolioRiskState.FROZEN
    if drawdown <= Decimal("-0.08"):
        return PortfolioRiskState.CAPITAL_PRESERVATION
    if drawdown <= Decimal("-0.06"):
        return PortfolioRiskState.DEFENSIVE
    if drawdown <= Decimal("-0.03"):
        return PortfolioRiskState.CAUTION
    return PortfolioRiskState.NORMAL


def state_multiplier(state: PortfolioRiskState) -> Decimal:
    """New-position size as a fraction of what would otherwise be approved.

    CAUTION/DEFENSIVE/CAPITAL_PRESERVATION/FROZEN throttle size
    progressively but all stay non-zero: `drawdown_state()` derives every one
    of these purely from drawdown-vs-high-water-mark math, and that drawdown
    can only ever improve through new gains -- a fully-cash (zero-multiplier)
    portfolio can never make a new high on its own, so any automatically
    reachable state that zeroes sizing traps the portfolio there forever
    once triggered. Only EMERGENCY_EXIT is a true hard stop: `drawdown_state`
    never returns it, so it is never triggered by this ladder -- it is
    reserved for an explicit, externally-triggered override (e.g. a future
    kill-switch-style mechanism), which is exactly the scenario where a
    permanent zero is appropriate. assess() escalates that case for human
    review rather than rejecting it outright, since nothing in this state
    machine can clear it automatically.
    """
    return {
        PortfolioRiskState.NORMAL: Decimal("1.00"),
        PortfolioRiskState.CAUTION: Decimal("0.50"),
        PortfolioRiskState.DEFENSIVE: Decimal("0.25"),
        PortfolioRiskState.CAPITAL_PRESERVATION: Decimal("0.10"),
        PortfolioRiskState.FROZEN: Decimal("0.05"),
        PortfolioRiskState.EMERGENCY_EXIT: Decimal("0.00"),
    }[state]


def floor_quantity(value: Decimal) -> Decimal:
    return quantity(value.quantize(Decimal(1), rounding=ROUND_FLOOR))


class PositionSizingEngine:
    def assess(
        self,
        *,
        portfolio_id: str,
        strategy_id: str,
        instrument_id: str,
        portfolio_nav: Decimal,
        available_cash: Decimal,
        existing_position_value: Decimal,
        sector_value: Decimal,
        cluster_value: Decimal,
        gross_equity_value: Decimal,
        entry_price: Decimal,
        invalidation_price: Decimal,
        proposed_quantity: Decimal,
        sector: str,
        cluster: str,
        data_quality_status: str,
        instrument_eligibility_status: str,
        profile: RiskProfileVersion,
        current_drawdown: Decimal,
        kill_switches: list[KillSwitch] | None = None,
        market_regime: str = "NORMAL",
        side: str = "BUY",
    ) -> RiskAssessment:
        """`side="SELL"` reduces exposure rather than adding it, so none of
        the capacity caps below (cash, sector/cluster/strategy room, gross
        exposure headroom, per-position risk budget) or the drawdown-state
        size throttle apply -- they exist to gate *new* risk-taking, and
        applying them to an exit would artificially block or shrink a
        strategy's own decision to reduce a position, exactly when a
        portfolio in a drawdown state most needs to be free to de-risk.
        Kill switches, unknown sector/cluster, data quality, and eligibility
        checks still apply to both sides."""
        kill_switches = kill_switches or []
        reasons: list[str] = []
        state = drawdown_state(current_drawdown)
        multiplier = state_multiplier(state) if side == "BUY" else Decimal("1.00")
        active_blocking_kill_switch = False
        if sector == "UNKNOWN":
            reasons.append("REJECTED_UNKNOWN_SECTOR_RISK")
        if cluster == "UNKNOWN":
            reasons.append("REJECTED_UNKNOWN_CLUSTER_RISK")
        if data_quality_status not in {"GREEN", "GREEN_CAUTION"}:
            reasons.append("DATA_QUALITY_NOT_ELIGIBLE")
        if instrument_eligibility_status != "ELIGIBLE":
            reasons.append("INSTRUMENT_NOT_ELIGIBLE")
        for switch in kill_switches:
            if switch.is_active and switch.scope_id in {
                "GLOBAL",
                portfolio_id,
                strategy_id,
                instrument_id,
            }:
                reasons.append(f"KILL_SWITCH_ACTIVE:{switch.switch_type}")
                active_blocking_kill_switch = True
        risk_state_blocks_exposure = side == "BUY" and state is PortfolioRiskState.EMERGENCY_EXIT
        if risk_state_blocks_exposure:
            reasons.append(f"RISK_STATE_BLOCKS_NEW_EXPOSURE:{state}")

        if side != "BUY":
            constrained = quantity(proposed_quantity)
            risk_budget = Decimal(0)
        else:
            risk_per_share = max(
                money(entry_price - invalidation_price), money(profile.configured_gap_risk_amount)
            )
            if risk_per_share <= 0:
                reasons.append("INVALID_RISK_PER_SHARE")
                risk_per_share = Decimal(999999999)

            risk_budget = money(portfolio_nav * profile.maximum_risk_budget_per_position)
            qty_by_risk = floor_quantity(risk_budget / risk_per_share)
            qty_by_notional = floor_quantity(
                (portfolio_nav * profile.maximum_single_position_weight) / entry_price
            )
            max_spend = max(
                money(available_cash - (portfolio_nav * profile.minimum_cash_weight_normal)),
                Decimal(0),
            )
            qty_by_cash = floor_quantity(max_spend / entry_price)
            qty_by_sector = floor_quantity(
                max((portfolio_nav * profile.maximum_sector_weight) - sector_value, Decimal(0))
                / entry_price
            )
            qty_by_cluster = floor_quantity(
                max((portfolio_nav * profile.maximum_cluster_weight) - cluster_value, Decimal(0))
                / entry_price
            )
            qty_by_strategy = floor_quantity(
                (portfolio_nav * profile.strategy_allocation_cap) / entry_price
            )
            qty_by_exposure = floor_quantity(
                max(
                    (portfolio_nav * profile.maximum_gross_equity_exposure_normal)
                    - gross_equity_value,
                    Decimal(0),
                )
                / entry_price
            )
            constrained = min(
                quantity(proposed_quantity),
                qty_by_risk,
                qty_by_notional,
                qty_by_cash,
                qty_by_sector,
                qty_by_cluster,
                qty_by_strategy,
                qty_by_exposure,
            )
        approved = floor_quantity(constrained * multiplier)
        if active_blocking_kill_switch:
            approved = Decimal("0.000000")
        notional = money(approved * entry_price)
        if notional < profile.minimum_trade_notional and approved > 0:
            approved = Decimal("0.000000")
            reasons.append("BELOW_MINIMUM_TRADE_NOTIONAL")

        available_cash_after = money(available_cash - (approved * entry_price))
        position_after = money(existing_position_value + (approved * entry_price))
        sector_after = money(sector_value + (approved * entry_price))
        cluster_after = money(cluster_value + (approved * entry_price))
        if approved <= 0:
            if risk_state_blocks_exposure:
                # EMERGENCY_EXIT is never set automatically and has no
                # automatic reset -- escalate rather than silently rejecting
                # forever.
                decision = RiskDecision.ESCALATED_FOR_REVIEW
            elif reasons:
                decision = RiskDecision.REJECTED
            else:
                decision = RiskDecision.DEFERRED
                reasons.append("NO_TRADE_ZERO_SIZE")
        elif approved < proposed_quantity:
            decision = RiskDecision.APPROVED_WITH_REDUCED_SIZE
            reasons.append("SIZE_REDUCED_BY_RISK_CONSTRAINTS")
        else:
            decision = RiskDecision.APPROVED

        return RiskAssessment(
            portfolio_id=portfolio_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            assessment_time=utc_now(),
            portfolio_risk_state=state,
            market_regime=market_regime,
            proposed_quantity=quantity(proposed_quantity),
            approved_quantity=quantity(approved),
            position_weight_before=money(existing_position_value / portfolio_nav),
            position_weight_after=money(position_after / portfolio_nav),
            sector_weight_before=money(sector_value / portfolio_nav),
            sector_weight_after=money(sector_after / portfolio_nav),
            cluster_weight_before=money(cluster_value / portfolio_nav),
            cluster_weight_after=money(cluster_after / portfolio_nav),
            available_cash_before=money(available_cash),
            available_cash_after=available_cash_after,
            risk_budget_before=money(Decimal(0)),
            risk_budget_after=money(risk_budget),
            data_quality_status=data_quality_status,
            instrument_eligibility_status=instrument_eligibility_status,
            decision=decision,
            reason_codes=reasons,
            risk_profile_version=profile.profile_version,
        )
