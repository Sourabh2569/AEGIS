from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from aegis.shared.ids import new_id
from aegis.shared.money import INR, money, quantity
from aegis.shared.time import require_aware_utc, utc_now


class StrEnum(str, Enum):
    pass


SPRINT_1A_LABELS = (
    "FOUNDATION_SIMULATION_ONLY",
    "NOT_VALIDATED",
    "NOT_PAPER_TRADING_ELIGIBLE",
    "NOT_LIVE_TRADING_ELIGIBLE",
    "ZERO_COST_MODEL",
    "IMMEDIATE_SETTLEMENT_SIMULATION",
    "SINGLE_INSTRUMENT_ONLY",
)


class BacktestRunStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


class SimulationClassification(StrEnum):
    FOUNDATION_SIMULATION_ONLY = "FOUNDATION_SIMULATION_ONLY"


class ValidationEligibility(StrEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class BacktestEventType(StrEnum):
    BACKTEST_CREATED = "BACKTEST_CREATED"
    BACKTEST_STARTED = "BACKTEST_STARTED"
    MARKET_SESSION_OPEN = "MARKET_SESSION_OPEN"
    ORDER_ELIGIBLE = "ORDER_ELIGIBLE"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    MARKET_SESSION_CLOSE = "MARKET_SESSION_CLOSE"
    POSITION_VALUED = "POSITION_VALUED"
    NAV_SNAPSHOT_CREATED = "NAV_SNAPSHOT_CREATED"
    BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
    BACKTEST_FAILED = "BACKTEST_FAILED"


class PortfolioStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CashEntryType(StrEnum):
    INITIAL_CAPITAL = "INITIAL_CAPITAL"
    BUY_DEBIT = "BUY_DEBIT"
    SELL_CREDIT = "SELL_CREDIT"
    MANUAL_ADJUSTMENT_PROHIBITED = "MANUAL_ADJUSTMENT_PROHIBITED"


class PositionEntryType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    MARK_TO_MARKET_REFERENCE = "MARK_TO_MARKET_REFERENCE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionReferenceType(StrEnum):
    NEXT_ELIGIBLE_SESSION_OPEN = "NEXT_ELIGIBLE_SESSION_OPEN"


class OrderIntentStatus(StrEnum):
    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SimulatedOrderStatus(StrEnum):
    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class BacktestRun:
    name: str
    description: str
    dataset_version_id: str
    instrument_master_version: str
    portfolio_id: str
    instrument_id: str
    start_date: date
    end_date: date
    starting_cash: Decimal
    created_by: str
    currency: str = INR
    status: BacktestRunStatus = BacktestRunStatus.DRAFT
    simulation_classification: SimulationClassification = (
        SimulationClassification.FOUNDATION_SIMULATION_ONLY
    )
    strategy_id_nullable: str | None = None
    strategy_version_nullable: str | None = None
    experiment_manifest_id_nullable: str | None = None
    universe_version_nullable: str | None = None
    corporate_action_version_nullable: str | None = None
    execution_model_version: str = "NEXT_ELIGIBLE_SESSION_OPEN_V0"
    cost_model_version: str = "ZERO_COST_V0"
    settlement_model_version: str = "IMMEDIATE_SETTLEMENT_SIMULATION_V0"
    engine_version: str = "AEGIS_BACKTEST_ENGINE_V0"
    software_commit_hash: str = "unknown-local"
    random_seed_nullable: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason_nullable: str | None = None
    validation_eligibility: ValidationEligibility = ValidationEligibility.NOT_ELIGIBLE
    id: str = field(default_factory=lambda: new_id("bt"))
    backtest_run_id: str = field(default_factory=lambda: new_id("btrun"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "starting_cash", money(self.starting_cash))
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be > 0.")
        if self.simulation_classification != SimulationClassification.FOUNDATION_SIMULATION_ONLY:
            raise ValueError("Sprint 1A runs must remain FOUNDATION_SIMULATION_ONLY.")
        if self.validation_eligibility != ValidationEligibility.NOT_ELIGIBLE:
            raise ValueError("Sprint 1A runs are never validation eligible.")

    @property
    def labels(self) -> tuple[str, ...]:
        return SPRINT_1A_LABELS

    def mark_running(self) -> "BacktestRun":
        return replace(self, status=BacktestRunStatus.RUNNING, started_at=utc_now())

    def mark_completed(self) -> "BacktestRun":
        return replace(self, status=BacktestRunStatus.COMPLETED, completed_at=utc_now())

    def mark_failed(self, reason: str) -> "BacktestRun":
        return replace(
            self,
            status=BacktestRunStatus.FAILED,
            completed_at=utc_now(),
            failure_reason_nullable=reason,
        )


@dataclass(frozen=True)
class BacktestEvent:
    backtest_run_id: str
    sequence_number: int
    event_type: BacktestEventType
    event_time: datetime
    payload_json: dict[str, Any]
    correlation_id: str
    market_session_date_nullable: date | None = None
    entity_type_nullable: str | None = None
    entity_id_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("btevt"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_aware_utc(self.event_time))


@dataclass(frozen=True)
class SimulatedPortfolio:
    backtest_run_id: str
    name: str
    starting_cash: Decimal
    current_available_cash: Decimal
    current_reserved_cash: Decimal = Decimal("0")
    current_market_value: Decimal = Decimal("0")
    current_nav: Decimal = Decimal("0")
    currency: str = INR
    status: PortfolioStatus = PortfolioStatus.CREATED
    id: str = field(default_factory=lambda: new_id("pf"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for name in (
            "starting_cash",
            "current_available_cash",
            "current_reserved_cash",
            "current_market_value",
            "current_nav",
        ):
            object.__setattr__(self, name, money(getattr(self, name)))


@dataclass(frozen=True)
class CashLedgerEntry:
    backtest_run_id: str
    portfolio_id: str
    entry_type: CashEntryType
    effective_time: datetime
    currency: str
    amount: Decimal
    balance_after: Decimal
    reference_entity_type: str
    reference_entity_id: str
    description: str
    correlation_id: str
    id: str = field(default_factory=lambda: new_id("cash"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "effective_time", require_aware_utc(self.effective_time))
        object.__setattr__(self, "amount", money(self.amount))
        object.__setattr__(self, "balance_after", money(self.balance_after))


@dataclass(frozen=True)
class PositionLedgerEntry:
    backtest_run_id: str
    portfolio_id: str
    instrument_id: str
    entry_type: PositionEntryType
    effective_time: datetime
    quantity_delta: Decimal
    quantity_after: Decimal
    price_reference: Decimal
    gross_notional: Decimal
    cost_basis_after: Decimal
    realized_pnl_delta: Decimal
    reference_entity_type: str
    reference_entity_id: str
    description: str
    correlation_id: str
    id: str = field(default_factory=lambda: new_id("pos"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "effective_time", require_aware_utc(self.effective_time))
        object.__setattr__(self, "quantity_delta", quantity(self.quantity_delta))
        object.__setattr__(self, "quantity_after", quantity(self.quantity_after))
        object.__setattr__(self, "price_reference", money(self.price_reference))
        object.__setattr__(self, "gross_notional", money(self.gross_notional))
        object.__setattr__(self, "cost_basis_after", money(self.cost_basis_after))
        object.__setattr__(self, "realized_pnl_delta", money(self.realized_pnl_delta))


@dataclass(frozen=True)
class OrderIntent:
    backtest_run_id: str
    portfolio_id: str
    instrument_id: str
    side: OrderSide
    requested_quantity: Decimal
    decision_time: datetime
    available_data_cutoff: datetime
    eligible_execution_time: datetime
    created_by: str
    execution_reference_type: ExecutionReferenceType = (
        ExecutionReferenceType.NEXT_ELIGIBLE_SESSION_OPEN
    )
    status: OrderIntentStatus = OrderIntentStatus.PENDING
    reason_code: str | None = None
    id: str = field(default_factory=lambda: new_id("intent"))
    correlation_id: str = field(default_factory=lambda: new_id("corr"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_quantity", quantity(self.requested_quantity))
        object.__setattr__(self, "decision_time", require_aware_utc(self.decision_time))
        object.__setattr__(
            self, "available_data_cutoff", require_aware_utc(self.available_data_cutoff)
        )
        object.__setattr__(
            self, "eligible_execution_time", require_aware_utc(self.eligible_execution_time)
        )


@dataclass(frozen=True)
class SimulatedOrder:
    order_intent_id: str
    backtest_run_id: str
    portfolio_id: str
    instrument_id: str
    status: SimulatedOrderStatus
    submitted_at: datetime
    eligible_execution_time: datetime
    requested_quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    executed_at_nullable: datetime | None = None
    average_fill_price_nullable: Decimal | None = None
    gross_notional_nullable: Decimal | None = None
    execution_model_version: str = "NEXT_ELIGIBLE_SESSION_OPEN_V0"
    rejection_reason_nullable: str | None = None
    id: str = field(default_factory=lambda: new_id("order"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class SimulatedFill:
    simulated_order_id: str
    backtest_run_id: str
    portfolio_id: str
    instrument_id: str
    fill_time: datetime
    fill_quantity: Decimal
    fill_price: Decimal
    gross_notional: Decimal
    currency: str
    net_cash_effect: Decimal
    cost_total: Decimal = Decimal("0")
    settlement_model_version: str = "IMMEDIATE_SETTLEMENT_SIMULATION_V0"
    id: str = field(default_factory=lambda: new_id("fill"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cost_total", money(self.cost_total))
        if self.cost_total != Decimal("0.0000"):
            raise ValueError("Sprint 1A fills must have zero costs.")
        if self.settlement_model_version != "IMMEDIATE_SETTLEMENT_SIMULATION_V0":
            raise ValueError("Sprint 1A uses immediate settlement simulation only.")


@dataclass(frozen=True)
class PortfolioNavSnapshot:
    backtest_run_id: str
    portfolio_id: str
    valuation_time: datetime
    market_session_date: date
    available_cash: Decimal
    reserved_cash: Decimal
    gross_market_value: Decimal
    net_market_value: Decimal
    position_quantity: Decimal
    position_cost_basis: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    portfolio_nav: Decimal
    drawdown: Decimal
    high_water_mark: Decimal
    market_price_reference: Decimal
    dataset_version_id: str
    id: str = field(default_factory=lambda: new_id("nav"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "valuation_time", require_aware_utc(self.valuation_time))
        for name in (
            "available_cash",
            "reserved_cash",
            "gross_market_value",
            "net_market_value",
            "position_cost_basis",
            "unrealized_pnl",
            "realized_pnl",
            "portfolio_nav",
            "drawdown",
            "high_water_mark",
            "market_price_reference",
        ):
            object.__setattr__(self, name, money(getattr(self, name)))
        object.__setattr__(self, "position_quantity", quantity(self.position_quantity))
