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


PAPER_LABELS = (
    "PAPER_TRADING_ONLY",
    "NO_REAL_CAPITAL_DEPLOYED",
    "NOT_LIVE_APPROVED",
    "NOT_BROKER_CONNECTED",
    "PAPER_RESULTS_DO_NOT_GUARANTEE_LIVE_PERFORMANCE",
)


class PaperPortfolioStatus(StrEnum):
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


class PaperStrategyConfigStatus(StrEnum):
    DRAFT = "DRAFT"
    ADMISSION_PENDING = "ADMISSION_PENDING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    CAUTION = "CAUTION"
    DEFENSIVE = "DEFENSIVE"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class LifecycleStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class PaperIntentStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PaperApprovalDecision(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    BLOCKED = "BLOCKED"


class PaperOrderStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    ELIGIBLE = "ELIGIBLE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    UNFILLED = "UNFILLED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class DriftState(StrEnum):
    WITHIN_EXPECTATION = "WITHIN_EXPECTATION"
    WATCH = "WATCH"
    MATERIAL_DIVERGENCE = "MATERIAL_DIVERGENCE"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"


class IncidentType(StrEnum):
    DATA_INCIDENT = "DATA_INCIDENT"
    FEATURE_INCIDENT = "FEATURE_INCIDENT"
    STRATEGY_INCIDENT = "STRATEGY_INCIDENT"
    RISK_INCIDENT = "RISK_INCIDENT"
    EXECUTION_SIMULATION_INCIDENT = "EXECUTION_SIMULATION_INCIDENT"
    SETTLEMENT_INCIDENT = "SETTLEMENT_INCIDENT"
    CORPORATE_ACTION_INCIDENT = "CORPORATE_ACTION_INCIDENT"
    RECONCILIATION_INCIDENT = "RECONCILIATION_INCIDENT"
    AUDIT_INCIDENT = "AUDIT_INCIDENT"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    CONFIGURATION_INCIDENT = "CONFIGURATION_INCIDENT"
    KILL_SWITCH_INCIDENT = "KILL_SWITCH_INCIDENT"


@dataclass(frozen=True)
class PaperPortfolio:
    name: str
    description: str
    starting_capital: Decimal
    risk_profile_version_id: str
    portfolio_configuration_version: str
    created_by: str
    currency: str = INR
    status: PaperPortfolioStatus = PaperPortfolioStatus.DRAFT
    id: str = field(default_factory=lambda: new_id("paper-portfolio-row"))
    paper_portfolio_id: str = field(default_factory=lambda: new_id("paper-portfolio"))
    created_at: datetime = field(default_factory=utc_now)
    activated_at_nullable: datetime | None = None
    paused_at_nullable: datetime | None = None
    completed_at_nullable: datetime | None = None
    retired_at_nullable: datetime | None = None
    failure_reason_nullable: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "starting_capital", money(self.starting_capital))

    @property
    def labels(self) -> tuple[str, ...]:
        return PAPER_LABELS

    def activate(self) -> "PaperPortfolio":
        if self.status not in {PaperPortfolioStatus.READY, PaperPortfolioStatus.SETUP_PENDING}:
            raise ValueError("Paper portfolio must be READY or SETUP_PENDING before activation.")
        return replace(self, status=PaperPortfolioStatus.ACTIVE, activated_at_nullable=utc_now())

    def freeze(self, reason: str) -> "PaperPortfolio":
        return replace(self, status=PaperPortfolioStatus.FROZEN, failure_reason_nullable=reason)

    def pause(self, reason: str) -> "PaperPortfolio":
        return replace(
            self,
            status=PaperPortfolioStatus.PAUSED,
            paused_at_nullable=utc_now(),
            failure_reason_nullable=reason,
        )


@dataclass(frozen=True)
class PaperPortfolioConfiguration:
    paper_portfolio_id: str
    version: str
    risk_profile_version_id: str
    minimum_cash_weight: Decimal
    maximum_gross_equity_exposure: Decimal
    maximum_position_count: int
    settlement_model_version: str
    cost_schedule_version: str
    slippage_model_version: str
    execution_model_version: str
    market_calendar_policy: str
    valuation_policy: str
    corporate_action_policy: str
    created_by: str
    id: str = field(default_factory=lambda: new_id("paper-pf-config"))
    created_at: datetime = field(default_factory=utc_now)
    frozen_at_nullable: datetime | None = None

    def freeze(self) -> "PaperPortfolioConfiguration":
        return replace(self, frozen_at_nullable=utc_now())

    def update_cost_schedule(self, value: str) -> "PaperPortfolioConfiguration":
        if self.frozen_at_nullable is not None:
            raise ValueError("Frozen paper portfolio configuration is immutable.")
        return replace(self, cost_schedule_version=value)


@dataclass(frozen=True)
class PaperStrategyConfiguration:
    paper_portfolio_id: str
    strategy_id: str
    strategy_version_id: str
    research_family_id: str
    risk_profile_version_id: str
    dataset_version_policy: str
    feature_version_policy: str
    universe_definition_version: str
    cost_schedule_version: str
    slippage_model_version: str
    settlement_model_version: str
    corporate_action_version: str
    execution_model_version: str
    rebalancing_frequency: str
    decision_time_policy: str
    execution_time_policy: str
    market_regime_policy: str
    position_sizing_policy: str
    paper_start_date: date
    status: PaperStrategyConfigStatus = PaperStrategyConfigStatus.DRAFT
    paper_end_date_nullable: date | None = None
    id: str = field(default_factory=lambda: new_id("paper-strategy-config-row"))
    paper_strategy_config_id: str = field(default_factory=lambda: new_id("paper-strategy-config"))
    created_at: datetime = field(default_factory=utc_now)
    frozen_at_nullable: datetime | None = None
    approved_by_nullable: str | None = None

    def freeze(self) -> "PaperStrategyConfiguration":
        return replace(self, frozen_at_nullable=utc_now(), status=PaperStrategyConfigStatus.READY)

    def activate(self, approved_by: str) -> "PaperStrategyConfiguration":
        if self.frozen_at_nullable is None:
            raise ValueError("Paper strategy configuration must be frozen before activation.")
        return replace(
            self,
            status=PaperStrategyConfigStatus.ACTIVE,
            approved_by_nullable=approved_by,
        )

    def update_strategy_version(self, value: str) -> "PaperStrategyConfiguration":
        if self.frozen_at_nullable is not None:
            raise ValueError("Frozen paper strategy configuration is immutable.")
        return replace(self, strategy_version_id=value)


@dataclass(frozen=True)
class PaperTradingSession:
    paper_portfolio_id: str
    session_date: date
    market_session_status: str
    data_readiness_status: str
    portfolio_risk_state: str
    decision_cycle_status: LifecycleStatus
    execution_cycle_status: LifecycleStatus
    reconciliation_status: str
    correlation_id: str
    feature_run_id_nullable: str | None = None
    market_regime_snapshot_id_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("paper-session-row"))
    paper_trading_session_id: str = field(default_factory=lambda: new_id("paper-session"))
    started_at: datetime = field(default_factory=utc_now)
    completed_at_nullable: datetime | None = None
    failure_reason_nullable: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperTradeIntent:
    paper_portfolio_id: str
    paper_strategy_config_id: str
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
    approval_status: PaperApprovalDecision = PaperApprovalDecision.PENDING_APPROVAL
    intent_status: PaperIntentStatus = PaperIntentStatus.PENDING_APPROVAL
    reason_codes_json: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("paper-intent-row"))
    paper_trade_intent_id: str = field(default_factory=lambda: new_id("paper-intent"))
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
class PaperApproval:
    paper_trade_intent_id: str
    approver_id: str
    decision: PaperApprovalDecision
    decision_time: datetime
    risk_assessment_id: str
    paper_strategy_config_id: str
    reason: str
    expiry_time: datetime
    exception_reference_id_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("paper-approval-row"))
    paper_approval_id: str = field(default_factory=lambda: new_id("paper-approval"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", require_aware_utc(self.decision_time))
        object.__setattr__(self, "expiry_time", require_aware_utc(self.expiry_time))

    def is_valid_at(self, value: datetime) -> bool:
        return (
            self.decision == PaperApprovalDecision.APPROVED
            and require_aware_utc(value) <= self.expiry_time
        )


@dataclass(frozen=True)
class PaperOrder:
    paper_trade_intent_id: str
    paper_portfolio_id: str
    instrument_id: str
    status: PaperOrderStatus
    scheduled_execution_time: datetime
    eligible_execution_time: datetime
    requested_quantity: Decimal
    execution_model_version: str
    idempotency_key: str
    submitted_at_nullable: datetime | None = None
    executed_at_nullable: datetime | None = None
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    rejection_reason_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("paper-order-row"))
    paper_order_id: str = field(default_factory=lambda: new_id("paper-order"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperFill:
    paper_order_id: str
    paper_portfolio_id: str
    instrument_id: str
    fill_time: datetime
    fill_quantity: Decimal
    reference_price: Decimal
    reference_price_time: datetime
    simulated_fill_price: Decimal
    gross_notional: Decimal
    slippage_amount: Decimal
    slippage_bps: Decimal
    cost_total: Decimal
    net_cash_effect: Decimal
    settlement_date: date
    fill_status: str
    id: str = field(default_factory=lambda: new_id("paper-fill-row"))
    paper_fill_id: str = field(default_factory=lambda: new_id("paper-fill"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_time", require_aware_utc(self.fill_time))
        object.__setattr__(
            self, "reference_price_time", require_aware_utc(self.reference_price_time)
        )


@dataclass(frozen=True)
class PaperLedgerEntry:
    paper_portfolio_id: str
    ledger_type: str
    event_time: datetime
    amount: Decimal
    balance_after: Decimal
    source_reference: str
    configuration_version: str
    correlation_id: str
    audit_event_id_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("paper-ledger"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperNavSnapshot:
    paper_portfolio_id: str
    valuation_time: datetime
    available_cash: Decimal
    unsettled_receivables: Decimal
    market_value: Decimal
    nav: Decimal
    high_water_mark: Decimal
    drawdown: Decimal
    reconciliation_status: str
    id: str = field(default_factory=lambda: new_id("paper-nav"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperReconciliationRecord:
    paper_portfolio_id: str
    reconciliation_time: datetime
    expected_nav: Decimal
    observed_nav: Decimal
    status: str
    reason_codes: list[str]
    id: str = field(default_factory=lambda: new_id("paper-recon"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperTradingIncident:
    paper_portfolio_id: str
    incident_type: IncidentType
    severity: str
    description: str
    status: str
    reason_codes: list[str]
    id: str = field(default_factory=lambda: new_id("paper-incident"))
    created_at: datetime = field(default_factory=utc_now)
    resolved_at_nullable: datetime | None = None


@dataclass(frozen=True)
class PaperDriftAssessment:
    paper_strategy_config_id: str
    assessment_time: datetime
    drift_category: str
    severity: DriftState
    expected_range_reference: str
    observed_value: Decimal
    market_regime: str
    recommended_action: str
    reason_codes: list[str]
    id: str = field(default_factory=lambda: new_id("paper-drift"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperEvidencePackage:
    paper_portfolio_id: str
    paper_strategy_config_id: str
    generated_at: datetime
    payload_json: dict[str, Any]
    classification: tuple[str, ...] = PAPER_LABELS
    id: str = field(default_factory=lambda: new_id("paper-evidence"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperCorporateActionReview:
    paper_portfolio_id: str
    instrument_id: str
    action_type: str
    effective_date: date
    verification_status: str
    support_status: str
    decision: str
    reviewer_id_nullable: str | None = None
    incident_id_nullable: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("paper-ca-review"))
    created_at: datetime = field(default_factory=utc_now)


def default_approval_expiry(decision_time: datetime) -> datetime:
    return require_aware_utc(decision_time) + timedelta(hours=18)
