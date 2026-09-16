from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from aegis.shared.ids import new_id
from aegis.shared.money import INR, money, quantity
from aegis.shared.time import require_aware_utc, utc_now


class StrEnum(str, Enum):
    pass


# Deliberately the mirror-image of paper_trading's PAPER_LABELS -- these
# facts are always true of anything built in this package, and must never
# be confused with a paper-trading result. This package's DOMAIN STATE
# (portfolios, intents, orders, fills) stays entirely separate from
# packages/paper_trading's (Document 007: live and paper data must never
# be structurally co-mingled) -- shared domain concepts (incident types,
# order status shape) are deliberately re-declared here rather than
# imported, even at the cost of some duplication. A genuinely stateless,
# non-domain utility like PaperTradingCalendarService (just a real list of
# NSE session dates, no paper-specific state at all) is the one exception,
# reused directly rather than duplicated -- see preflight.py.
LIVE_LABELS = (
    "REAL_CAPITAL_AT_RISK",
    "REAL_BROKER_ORDER",
    "HUMAN_APPROVAL_REQUIRED_PER_ORDER",
    "NOT_A_SIMULATION",
)


class LiveCapitalTier(StrEnum):
    PILOT = "PILOT"
    FULL = "FULL"


class LivePortfolioStatus(StrEnum):
    """Mirrors PaperPortfolioStatus's drawdown ladder exactly -- the same
    risk-state machinery (drawdown-derived NORMAL/CAUTION/DEFENSIVE/
    CAPITAL_PRESERVATION states feed into this the same way) must behave
    identically for live as for paper."""

    DRAFT = "DRAFT"
    SETUP_PENDING = "SETUP_PENDING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    CAUTION = "CAUTION"
    DEFENSIVE = "DEFENSIVE"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    PAUSED = "PAUSED"
    FROZEN = "FROZEN"
    COMPLETED = "COMPLETED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class LiveStrategyConfigStatus(StrEnum):
    DRAFT = "DRAFT"
    ADMISSION_PENDING = "ADMISSION_PENDING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class LiveIntentStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LiveApprovalDecision(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    BLOCKED = "BLOCKED"


class LiveOrderStatus(StrEnum):
    """More states than PaperOrderStatus needs, because a real broker fill
    is genuinely asynchronous -- unlike a simulated fill, which resolves
    synchronously within the same request, a real order can sit OPEN or
    PARTIALLY_FILLED for real, unpredictable amounts of time."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    SUBMITTED_TO_BROKER = "SUBMITTED_TO_BROKER"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED_BY_BROKER = "REJECTED_BY_BROKER"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"


class LiveIncidentType(StrEnum):
    DATA_INCIDENT = "DATA_INCIDENT"
    RISK_INCIDENT = "RISK_INCIDENT"
    EXECUTION_INCIDENT = "EXECUTION_INCIDENT"
    BROKER_INCIDENT = "BROKER_INCIDENT"
    RECONCILIATION_INCIDENT = "RECONCILIATION_INCIDENT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    COMPLIANCE_INCIDENT = "COMPLIANCE_INCIDENT"
    CONFIGURATION_INCIDENT = "CONFIGURATION_INCIDENT"
    KILL_SWITCH_INCIDENT = "KILL_SWITCH_INCIDENT"


@dataclass(frozen=True)
class LivePortfolio:
    name: str
    description: str
    starting_capital: Decimal
    pilot_capital_cap: Decimal
    risk_profile_version_id: str
    portfolio_configuration_version: str
    created_by: str
    currency: str = INR
    status: LivePortfolioStatus = LivePortfolioStatus.DRAFT
    capital_tier: LiveCapitalTier = LiveCapitalTier.PILOT
    clean_fill_count: int = 0
    id: str = field(default_factory=lambda: new_id("live-portfolio-row"))
    live_portfolio_id: str = field(default_factory=lambda: new_id("live-portfolio"))
    created_at: datetime = field(default_factory=utc_now)
    activated_at_nullable: datetime | None = None
    paused_at_nullable: datetime | None = None
    completed_at_nullable: datetime | None = None
    retired_at_nullable: datetime | None = None
    failure_reason_nullable: str | None = None
    graduated_at_nullable: datetime | None = None
    graduated_by_nullable: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "starting_capital", money(self.starting_capital))
        object.__setattr__(self, "pilot_capital_cap", money(self.pilot_capital_cap))
        if self.pilot_capital_cap <= 0:
            raise ValueError("pilot_capital_cap must be a positive real amount.")

    @property
    def labels(self) -> tuple[str, ...]:
        return LIVE_LABELS

    def activate(self) -> LivePortfolio:
        if self.status not in {LivePortfolioStatus.READY, LivePortfolioStatus.SETUP_PENDING}:
            raise ValueError("Live portfolio must be READY or SETUP_PENDING before activation.")
        return replace(self, status=LivePortfolioStatus.ACTIVE, activated_at_nullable=utc_now())

    def freeze(self, reason: str) -> LivePortfolio:
        return replace(self, status=LivePortfolioStatus.FROZEN, failure_reason_nullable=reason)

    def pause(self, reason: str) -> LivePortfolio:
        return replace(
            self,
            status=LivePortfolioStatus.PAUSED,
            paused_at_nullable=utc_now(),
            failure_reason_nullable=reason,
        )

    def resume(self) -> LivePortfolio:
        if self.status != LivePortfolioStatus.PAUSED:
            raise ValueError("Only a PAUSED live portfolio can resume.")
        return replace(self, status=LivePortfolioStatus.ACTIVE, paused_at_nullable=None)

    def record_clean_fill(self) -> LivePortfolio:
        return replace(self, clean_fill_count=self.clean_fill_count + 1)

    def reset_clean_fill_count(self) -> LivePortfolio:
        """Called on any broker rejection or RED reconciliation -- 'clean'
        means zero errors, not just 'some fills happened'."""
        return replace(self, clean_fill_count=0)

    def graduate(self, *, new_capital_cap: Decimal, graduated_by: str) -> LivePortfolio:
        """Never called automatically -- always a distinct, role-gated,
        reason-and-amount-confirmed API call (see Phase 6/8 of the live
        trading plan). This method only enforces the domain invariant that
        graduation is a one-way PILOT -> FULL transition; the 20-clean-fill
        threshold and role/reason checks are enforced by the caller, not
        here, matching how activate()/pause() only enforce their own
        state-machine shape."""
        if self.capital_tier != LiveCapitalTier.PILOT:
            raise ValueError("Only a PILOT-tier live portfolio can graduate.")
        return replace(
            self,
            capital_tier=LiveCapitalTier.FULL,
            pilot_capital_cap=money(new_capital_cap),
            graduated_at_nullable=utc_now(),
            graduated_by_nullable=graduated_by,
        )


@dataclass(frozen=True)
class LivePortfolioConfiguration:
    live_portfolio_id: str
    version: str
    risk_profile_version_id: str
    minimum_cash_weight: Decimal
    maximum_gross_equity_exposure: Decimal
    maximum_position_count: int
    settlement_model_version: str
    cost_schedule_version: str
    execution_model_version: str
    market_calendar_policy: str
    valuation_policy: str
    corporate_action_policy: str
    created_by: str
    id: str = field(default_factory=lambda: new_id("live-pf-config"))
    created_at: datetime = field(default_factory=utc_now)
    frozen_at_nullable: datetime | None = None

    def freeze(self) -> LivePortfolioConfiguration:
        return replace(self, frozen_at_nullable=utc_now())


@dataclass(frozen=True)
class LiveStrategyConfiguration:
    live_portfolio_id: str
    strategy_id: str
    strategy_version_id: str
    risk_profile_version_id: str
    universe_definition_version: str
    cost_schedule_version: str
    settlement_model_version: str
    execution_model_version: str
    rebalancing_frequency: str
    decision_time_policy: str
    execution_time_policy: str
    position_sizing_policy: str
    live_start_date: date
    status: LiveStrategyConfigStatus = LiveStrategyConfigStatus.DRAFT
    live_end_date_nullable: date | None = None
    id: str = field(default_factory=lambda: new_id("live-strategy-config-row"))
    live_strategy_config_id: str = field(default_factory=lambda: new_id("live-strategy-config"))
    created_at: datetime = field(default_factory=utc_now)
    frozen_at_nullable: datetime | None = None
    approved_by_nullable: str | None = None

    def freeze(self) -> LiveStrategyConfiguration:
        return replace(self, frozen_at_nullable=utc_now(), status=LiveStrategyConfigStatus.READY)

    def activate(self, approved_by: str) -> LiveStrategyConfiguration:
        if self.frozen_at_nullable is None:
            raise ValueError("Live strategy configuration must be frozen before activation.")
        return replace(
            self, status=LiveStrategyConfigStatus.ACTIVE, approved_by_nullable=approved_by
        )


@dataclass(frozen=True)
class LiveOrderIntent:
    """Deliberately identical data-timing/execution-ordering invariants to
    paper_trading's PaperTradeIntent -- a real order proposal is exactly as
    forward-only and point-in-time-honest as a simulated one; nothing about
    being real relaxes that discipline."""

    live_portfolio_id: str
    live_strategy_config_id: str
    strategy_version_id: str
    instrument_id: str
    side: str
    proposed_quantity: Decimal
    decision_time: datetime
    available_data_cutoff: datetime
    eligible_execution_time: datetime
    risk_assessment_id: str
    configuration_version: str
    idempotency_key: str
    correlation_id: str
    approved_quantity_nullable: Decimal | None = None
    approval_status: LiveApprovalDecision = LiveApprovalDecision.PENDING_APPROVAL
    intent_status: LiveIntentStatus = LiveIntentStatus.PENDING_APPROVAL
    reason_codes_json: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("live-intent-row"))
    live_order_intent_id: str = field(default_factory=lambda: new_id("live-intent"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_quantity", quantity(self.proposed_quantity))
        if self.approved_quantity_nullable is not None:
            object.__setattr__(
                self, "approved_quantity_nullable", quantity(self.approved_quantity_nullable)
            )
        object.__setattr__(self, "decision_time", require_aware_utc(self.decision_time))
        object.__setattr__(
            self, "available_data_cutoff", require_aware_utc(self.available_data_cutoff)
        )
        object.__setattr__(
            self, "eligible_execution_time", require_aware_utc(self.eligible_execution_time)
        )
        if self.available_data_cutoff > self.decision_time:
            raise ValueError("DATA_TIMING_VIOLATION")
        if self.eligible_execution_time <= self.decision_time:
            raise ValueError("EXECUTION_NOT_AFTER_DECISION")


@dataclass(frozen=True)
class LiveApproval:
    live_order_intent_id: str
    approver_id: str
    decision: LiveApprovalDecision
    decision_time: datetime
    risk_assessment_id: str
    live_strategy_config_id: str
    reason: str
    expiry_time: datetime
    confirmed_amount_nullable: Decimal | None = None
    id: str = field(default_factory=lambda: new_id("live-approval-row"))
    live_approval_id: str = field(default_factory=lambda: new_id("live-approval"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", require_aware_utc(self.decision_time))
        object.__setattr__(self, "expiry_time", require_aware_utc(self.expiry_time))

    def is_valid_at(self, value: datetime) -> bool:
        return (
            self.decision == LiveApprovalDecision.APPROVED
            and require_aware_utc(value) <= self.expiry_time
        )


@dataclass(frozen=True)
class LiveOrder:
    live_order_intent_id: str
    live_portfolio_id: str
    instrument_id: str
    status: LiveOrderStatus
    requested_quantity: Decimal
    idempotency_key: str
    broker_order_id_nullable: str | None = None
    submitted_at_nullable: datetime | None = None
    filled_quantity: Decimal = Decimal(0)
    remaining_quantity: Decimal = Decimal(0)
    rejection_reason_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("live-order-row"))
    live_order_id: str = field(default_factory=lambda: new_id("live-order"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class LiveFill:
    """Deliberately has no simulated_fill_price/slippage-model field at all
    -- unlike PaperFill, every value here comes only from what the broker
    actually reported. Its absence is the guarantee a live fill can never
    be fabricated or approximated."""

    live_order_id: str
    live_portfolio_id: str
    instrument_id: str
    fill_time: datetime
    fill_quantity: Decimal
    fill_price: Decimal
    broker_fill_reference: str
    gross_notional: Decimal
    cost_total: Decimal
    net_cash_effect: Decimal
    settlement_date: date
    fill_status: str
    id: str = field(default_factory=lambda: new_id("live-fill-row"))
    live_fill_id: str = field(default_factory=lambda: new_id("live-fill"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_time", require_aware_utc(self.fill_time))


@dataclass(frozen=True)
class LiveReconciliationRecord:
    """Unlike PaperReconciliationRecord (self-referential -- no independent
    data source), observed_nav here comes from the broker's own real
    get_positions()/get_margins() response -- a genuine independent
    comparison against the internal ledger's expected_nav."""

    live_portfolio_id: str
    reconciliation_time: datetime
    expected_nav: Decimal
    observed_nav: Decimal
    status: str
    reason_codes: list[str]
    id: str = field(default_factory=lambda: new_id("live-recon"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class LiveIncident:
    live_portfolio_id: str
    incident_type: LiveIncidentType
    severity: str
    description: str
    status: str
    reason_codes: list[str]
    id: str = field(default_factory=lambda: new_id("live-incident"))
    created_at: datetime = field(default_factory=utc_now)
    resolved_at_nullable: datetime | None = None


@dataclass(frozen=True)
class LiveExecutionPreflight:
    """No paper-trading analog -- Document 007 names this as its own
    distinct pipeline stage, and unlike paper trading's simulated path,
    a real broker call is irreversible, so every attempted order (even one
    that never reaches the broker) gets its own persisted, auditable
    record here with every individual check's real result, not just an
    overall pass/fail."""

    live_order_intent_id: str
    live_portfolio_id: str
    checked_at: datetime
    passed: bool
    check_results: dict[str, bool]
    failure_reasons: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("live-preflight"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", require_aware_utc(self.checked_at))


def default_live_approval_expiry(decision_time: datetime) -> datetime:
    return require_aware_utc(decision_time) + timedelta(hours=18)
