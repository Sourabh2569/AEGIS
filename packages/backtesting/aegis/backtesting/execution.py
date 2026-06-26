from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from aegis.backtesting.domain import ExecutionReferenceType, OrderIntent, OrderSide
from aegis.backtesting.repositories import MarketDataReader, TradingCalendarReader
from aegis.shared.errors import OrderRejected


def validate_order_timing(intent: OrderIntent) -> None:
    if intent.available_data_cutoff > intent.decision_time:
        raise OrderRejected("DATA_UNAVAILABLE_AT_DECISION_TIME", "available_data_cutoff is after decision_time.")
    if intent.eligible_execution_time <= intent.decision_time:
        raise OrderRejected("EXECUTION_NOT_AFTER_DECISION", "eligible_execution_time must be after decision_time.")


def reject_same_close_execution(intent: OrderIntent, execution_price_time: datetime) -> None:
    if execution_price_time <= intent.decision_time:
        raise OrderRejected("SAME_CLOSE_EXECUTION_PROHIBITED", "Execution cannot use a price at or before decision time.")


@dataclass(frozen=True)
class ExecutionModelMetadata:
    model_name: str
    model_version: str
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    supports_partial_fills: bool = False
    supports_costs: bool = False
    supports_slippage: bool = False
    supports_settlement: bool = False


class NextEligibleSessionOpenExecutionModelV0:
    metadata = ExecutionModelMetadata(
        model_name="NextEligibleSessionOpenExecutionModel",
        model_version="NEXT_ELIGIBLE_SESSION_OPEN_V0",
        assumptions=("Fill at validated next eligible session open", "Zero costs", "Zero slippage"),
        limitations=("No partial fills", "No liquidity model", "No settlement lag"),
    )

    def resolve_fill_price(
        self,
        *,
        intent: OrderIntent,
        calendar: TradingCalendarReader,
        market_data: MarketDataReader,
    ) -> tuple[datetime, Decimal]:
        if intent.execution_reference_type != ExecutionReferenceType.NEXT_ELIGIBLE_SESSION_OPEN:
            raise OrderRejected("UNSUPPORTED_EXECUTION_REFERENCE", "Only next-session-open execution is supported.")
        if intent.side not in {OrderSide.BUY, OrderSide.SELL}:
            raise OrderRejected("UNSUPPORTED_ORDER_SIDE", "Only BUY and SELL are supported.")
        validate_order_timing(intent)
        next_session = calendar.next_session_after(intent.decision_time)
        if next_session is None:
            raise OrderRejected("NEXT_SESSION_UNAVAILABLE", "No eligible next market session exists.")
        execution_time = calendar.session_open_time(next_session)
        if execution_time != intent.eligible_execution_time:
            raise OrderRejected("ELIGIBLE_EXECUTION_TIME_MISMATCH", "Intent execution time does not match calendar.")
        reject_same_close_execution(intent, execution_time)
        price = market_data.get_open(intent.instrument_id, next_session)
        if price is None or price <= 0:
            raise OrderRejected("NEXT_OPEN_PRICE_MISSING", "Next eligible session open price is missing or invalid.")
        return execution_time, price
