from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from aegis.audit.service import AuditLog
from aegis.backtesting.accounting import (
    drawdown,
    gross_notional,
    high_water_mark,
    nav,
    realized_pnl,
    unrealized_pnl,
    weighted_average_cost_basis,
)
from aegis.backtesting.domain import (
    BacktestEventType,
    BacktestRun,
    BacktestRunStatus,
    CashEntryType,
    CashLedgerEntry,
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    PortfolioNavSnapshot,
    PortfolioStatus,
    PositionEntryType,
    PositionLedgerEntry,
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderStatus,
    SimulatedPortfolio,
)
from aegis.backtesting.eligibility import BacktestPreflightGuard
from aegis.backtesting.execution import (
    NextEligibleSessionOpenExecutionModelV0,
    validate_order_timing,
)
from aegis.backtesting.repositories import (
    BacktestRepository,
    MarketDataReader,
    TradingCalendarReader,
    update_portfolio,
)
from aegis.domain.models import DatasetVersion, Instrument, ProviderLicense
from aegis.shared.errors import EligibilityError, OrderRejected, ReconciliationError
from aegis.shared.ids import new_id
from aegis.shared.money import INR, money, quantity
from aegis.shared.time import utc_now


class BacktestService:
    def __init__(self, repository: BacktestRepository, audit_log: AuditLog) -> None:
        self.repository = repository
        self.audit_log = audit_log
        self.execution_model = NextEligibleSessionOpenExecutionModelV0()
        self.preflight = BacktestPreflightGuard()

    def create_run(
        self,
        *,
        name: str,
        description: str,
        dataset_version_id: str,
        instrument_master_version: str,
        instrument_id: str,
        start_date: Any,
        end_date: Any,
        starting_cash: Decimal,
        created_by: str,
        correlation_id: str | None = None,
    ) -> BacktestRun:
        correlation_id = correlation_id or new_id("corr")
        portfolio_id = new_id("pf")
        run = BacktestRun(
            name=name,
            description=description,
            dataset_version_id=dataset_version_id,
            instrument_master_version=instrument_master_version,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            starting_cash=starting_cash,
            created_by=created_by,
        )
        portfolio = SimulatedPortfolio(
            id=portfolio_id,
            backtest_run_id=run.backtest_run_id,
            name=f"{name} Portfolio",
            starting_cash=run.starting_cash,
            current_available_cash=run.starting_cash,
            current_nav=run.starting_cash,
            currency=run.currency,
        )
        self.repository.add_run(run, portfolio)
        cash = CashLedgerEntry(
            backtest_run_id=run.backtest_run_id,
            portfolio_id=portfolio.id,
            entry_type=CashEntryType.INITIAL_CAPITAL,
            effective_time=run.created_at,
            currency=run.currency,
            amount=run.starting_cash,
            balance_after=run.starting_cash,
            reference_entity_type="BacktestRun",
            reference_entity_id=run.backtest_run_id,
            description="Initial foundation simulation capital.",
            correlation_id=correlation_id,
        )
        self.repository.append_cash(cash)
        self.repository.append_event(
            backtest_run_id=run.backtest_run_id,
            event_type=BacktestEventType.BACKTEST_CREATED,
            event_time=run.created_at,
            payload_json={"labels": list(run.labels), "starting_cash": str(run.starting_cash)},
            correlation_id=correlation_id,
            entity_type="BacktestRun",
            entity_id=run.backtest_run_id,
        )
        self.audit_log.record(
            event_type="BACKTEST_CREATED",
            entity_type="BacktestRun",
            entity_id=run.backtest_run_id,
            actor_type="USER",
            actor_id=created_by,
            action="CREATE_FOUNDATION_BACKTEST",
            before_state=None,
            after_state={"backtest_run_id": run.backtest_run_id, "labels": list(run.labels)},
            correlation_id=correlation_id,
        )
        return run

    def create_order_intent(
        self,
        *,
        backtest_run_id: str,
        side: OrderSide,
        requested_quantity: Decimal,
        decision_time: datetime,
        available_data_cutoff: datetime,
        created_by: str,
    ) -> OrderIntent:
        run = self.repository.runs[backtest_run_id]
        if run.status in {
            BacktestRunStatus.COMPLETED,
            BacktestRunStatus.FAILED,
            BacktestRunStatus.CANCELLED,
            BacktestRunStatus.INVALIDATED,
        }:
            raise OrderRejected(
                "RUN_NOT_MUTABLE",
                "Completed, failed, cancelled, or invalidated runs cannot be modified.",
            )
        if requested_quantity <= 0:
            raise OrderRejected("INVALID_QUANTITY", "requested_quantity must be > 0.")
        next_session = (
            self._calendar.next_session_after(decision_time) if hasattr(self, "_calendar") else None
        )
        if next_session is None:
            raise OrderRejected(
                "NEXT_SESSION_UNAVAILABLE", "No eligible next market session exists."
            )
        eligible_execution_time = self._calendar.session_open_time(next_session)
        intent = OrderIntent(
            backtest_run_id=run.backtest_run_id,
            portfolio_id=run.portfolio_id,
            instrument_id=run.instrument_id,
            side=side,
            requested_quantity=requested_quantity,
            decision_time=decision_time,
            available_data_cutoff=available_data_cutoff,
            eligible_execution_time=eligible_execution_time,
            created_by=created_by,
        )
        validate_order_timing(intent)
        self.repository.append_intent(intent)
        self.audit_log.record(
            event_type="ORDER_INTENT_CREATED",
            entity_type="OrderIntent",
            entity_id=intent.id,
            actor_type="USER",
            actor_id=created_by,
            action="CREATE_SIMULATION_INSTRUCTION",
            before_state=None,
            after_state={
                "order_intent_id": intent.id,
                "side": intent.side,
                "quantity": str(intent.requested_quantity),
            },
            correlation_id=intent.correlation_id,
        )
        return intent

    def attach_calendar_for_intent_creation(self, calendar: TradingCalendarReader) -> None:
        self._calendar = calendar

    def start_run(
        self,
        *,
        backtest_run_id: str,
        dataset_version: DatasetVersion,
        provider_license: ProviderLicense,
        instrument: Instrument,
        calendar: TradingCalendarReader,
        market_data: MarketDataReader,
        correlation_id: str | None = None,
        inject_reconciliation_failure: bool = False,
    ) -> BacktestRun:
        correlation_id = correlation_id or new_id("corr")
        self.attach_calendar_for_intent_creation(calendar)
        run = self.repository.runs[backtest_run_id]
        if not self.repository.mark_job_started_once(backtest_run_id):
            return run
        try:
            self.preflight.assert_can_start(
                run=run,
                dataset_version=dataset_version,
                provider_license=provider_license,
                instrument=instrument,
                calendar=calendar,
                market_data=market_data,
            )
            running = run.mark_running()
            self.repository.save_run(running)
            portfolio = update_portfolio(
                self.repository.portfolios[backtest_run_id], status=PortfolioStatus.ACTIVE
            )
            self.repository.save_portfolio(portfolio)
            self.repository.append_event(
                backtest_run_id=backtest_run_id,
                event_type=BacktestEventType.BACKTEST_STARTED,
                event_time=running.started_at or utc_now(),
                payload_json={"engine_version": running.engine_version},
                correlation_id=correlation_id,
            )
            self._run_sessions(
                running, calendar, market_data, correlation_id, inject_reconciliation_failure
            )
            completed = self.repository.runs[backtest_run_id].mark_completed()
            self.repository.save_run(completed)
            self.repository.save_portfolio(
                update_portfolio(
                    self.repository.portfolios[backtest_run_id], status=PortfolioStatus.COMPLETED
                )
            )
            self.repository.append_event(
                backtest_run_id=backtest_run_id,
                event_type=BacktestEventType.BACKTEST_COMPLETED,
                event_time=completed.completed_at or utc_now(),
                payload_json={"labels": list(completed.labels)},
                correlation_id=correlation_id,
            )
            self.audit_log.record(
                event_type="BACKTEST_COMPLETED",
                entity_type="BacktestRun",
                entity_id=backtest_run_id,
                actor_type="SYSTEM_SERVICE",
                actor_id="backtest-engine",
                action="COMPLETE",
                before_state=None,
                after_state={"status": completed.status},
                correlation_id=correlation_id,
            )
            return completed
        except (EligibilityError, OrderRejected, ReconciliationError, ValueError) as exc:
            failed = self.repository.runs[backtest_run_id].mark_failed(str(exc))
            self.repository.save_run(failed)
            self.repository.save_portfolio(
                update_portfolio(
                    self.repository.portfolios[backtest_run_id], status=PortfolioStatus.FAILED
                )
            )
            self.repository.append_event(
                backtest_run_id=backtest_run_id,
                event_type=BacktestEventType.BACKTEST_FAILED,
                event_time=utc_now(),
                payload_json={
                    "reason": str(exc),
                    "reason_code": getattr(exc, "reason_code", "FAILED"),
                },
                correlation_id=correlation_id,
            )
            self.audit_log.record(
                event_type="BACKTEST_FAILED",
                entity_type="BacktestRun",
                entity_id=backtest_run_id,
                actor_type="SYSTEM_SERVICE",
                actor_id="backtest-engine",
                action="FAIL_CLOSED",
                before_state=None,
                after_state={"status": failed.status, "reason": str(exc)},
                correlation_id=correlation_id,
            )
            return failed

    def _run_sessions(
        self,
        run: BacktestRun,
        calendar: TradingCalendarReader,
        market_data: MarketDataReader,
        correlation_id: str,
        inject_reconciliation_failure: bool,
    ) -> None:
        hwm = run.starting_cash
        for session in calendar.sessions_between(run.start_date, run.end_date):
            open_time = calendar.session_open_time(session)
            close_time = calendar.session_close_time(session)
            self.repository.append_event(
                backtest_run_id=run.backtest_run_id,
                event_type=BacktestEventType.MARKET_SESSION_OPEN,
                event_time=open_time,
                market_session_date=session,
                payload_json={},
                correlation_id=correlation_id,
            )
            for intent in list(self.repository.order_intents.get(run.backtest_run_id, [])):
                if (
                    intent.status == OrderIntentStatus.PENDING
                    and intent.eligible_execution_time == open_time
                ):
                    self._execute_or_reject(run, intent, calendar, market_data)
            self.repository.append_event(
                backtest_run_id=run.backtest_run_id,
                event_type=BacktestEventType.MARKET_SESSION_CLOSE,
                event_time=close_time,
                market_session_date=session,
                payload_json={},
                correlation_id=correlation_id,
            )
            hwm = self._value_portfolio(run, market_data, session, close_time, hwm, correlation_id)
            if inject_reconciliation_failure:
                raise ReconciliationError("Injected reconciliation failure for controlled test.")

    def _execute_or_reject(
        self,
        run: BacktestRun,
        intent: OrderIntent,
        calendar: TradingCalendarReader,
        market_data: MarketDataReader,
    ) -> None:
        try:
            if not self.repository.mark_intent_executed_once(intent.id):
                raise OrderRejected(
                    "DUPLICATE_EXECUTION", "Order intent has already been executed."
                )
            fill_time, fill_price = self.execution_model.resolve_fill_price(
                intent=intent, calendar=calendar, market_data=market_data
            )
            if intent.instrument_id != run.instrument_id:
                raise OrderRejected(
                    "INSTRUMENT_MISMATCH", "Order instrument must match backtest instrument."
                )
            portfolio = self.repository.portfolios[run.backtest_run_id]
            current_qty = self.repository.current_quantity(run.backtest_run_id)
            current_basis = self.repository.current_cost_basis(run.backtest_run_id)
            notional = gross_notional(intent.requested_quantity, fill_price)
            if intent.side == OrderSide.BUY:
                if portfolio.current_available_cash - notional < 0:
                    raise OrderRejected(
                        "INSUFFICIENT_CASH", "Buy would make available cash negative."
                    )
                new_cash = money(portfolio.current_available_cash - notional)
                new_qty = quantity(current_qty + intent.requested_quantity)
                new_basis = weighted_average_cost_basis(
                    current_qty, current_basis, intent.requested_quantity, fill_price
                )
                realized = money(0)
                cash_type = CashEntryType.BUY_DEBIT
                pos_type = PositionEntryType.BUY
                cash_amount = -notional
            else:
                if intent.requested_quantity > current_qty:
                    raise OrderRejected("OVERSELL", "Sell quantity exceeds current position.")
                new_cash = money(portfolio.current_available_cash + notional)
                new_qty = quantity(current_qty - intent.requested_quantity)
                realized = realized_pnl(fill_price, current_basis, intent.requested_quantity)
                new_basis = money(0) if new_qty == 0 else current_basis
                cash_type = CashEntryType.SELL_CREDIT
                pos_type = PositionEntryType.SELL
                cash_amount = notional
            order = SimulatedOrder(
                order_intent_id=intent.id,
                backtest_run_id=run.backtest_run_id,
                portfolio_id=run.portfolio_id,
                instrument_id=run.instrument_id,
                status=SimulatedOrderStatus.FILLED,
                submitted_at=intent.created_at,
                eligible_execution_time=intent.eligible_execution_time,
                executed_at_nullable=fill_time,
                requested_quantity=intent.requested_quantity,
                filled_quantity=intent.requested_quantity,
                average_fill_price_nullable=fill_price,
                gross_notional_nullable=notional,
            )
            fill = SimulatedFill(
                simulated_order_id=order.id,
                backtest_run_id=run.backtest_run_id,
                portfolio_id=run.portfolio_id,
                instrument_id=run.instrument_id,
                fill_time=fill_time,
                fill_quantity=intent.requested_quantity,
                fill_price=fill_price,
                gross_notional=notional,
                currency=INR,
                net_cash_effect=cash_amount,
            )
            self.repository.append_order(order)
            self.repository.append_fill(fill)
            self.repository.append_cash(
                CashLedgerEntry(
                    backtest_run_id=run.backtest_run_id,
                    portfolio_id=run.portfolio_id,
                    entry_type=cash_type,
                    effective_time=fill_time,
                    currency=INR,
                    amount=cash_amount,
                    balance_after=new_cash,
                    reference_entity_type="SimulatedFill",
                    reference_entity_id=fill.id,
                    description=f"{intent.side} fill cash movement.",
                    correlation_id=intent.correlation_id,
                )
            )
            self.repository.append_position(
                PositionLedgerEntry(
                    backtest_run_id=run.backtest_run_id,
                    portfolio_id=run.portfolio_id,
                    instrument_id=run.instrument_id,
                    entry_type=pos_type,
                    effective_time=fill_time,
                    quantity_delta=intent.requested_quantity
                    if intent.side == OrderSide.BUY
                    else -intent.requested_quantity,
                    quantity_after=new_qty,
                    price_reference=fill_price,
                    gross_notional=notional,
                    cost_basis_after=new_basis,
                    realized_pnl_delta=realized,
                    reference_entity_type="SimulatedFill",
                    reference_entity_id=fill.id,
                    description=f"{intent.side} fill position movement.",
                    correlation_id=intent.correlation_id,
                )
            )
            self.repository.save_portfolio(
                update_portfolio(portfolio, current_available_cash=new_cash)
            )
            self.repository.replace_intent(replace(intent, status=OrderIntentStatus.FILLED))
            self.repository.append_event(
                backtest_run_id=run.backtest_run_id,
                event_type=BacktestEventType.ORDER_FILLED,
                event_time=fill_time,
                market_session_date=fill_time.date(),
                entity_type="SimulatedOrder",
                entity_id=order.id,
                payload_json={
                    "fill_price": str(fill_price),
                    "quantity": str(intent.requested_quantity),
                },
                correlation_id=intent.correlation_id,
            )
            self.audit_log.record(
                event_type="ORDER_FILLED",
                entity_type="SimulatedOrder",
                entity_id=order.id,
                actor_type="SYSTEM_SERVICE",
                actor_id="backtest-engine",
                action="FILL_SIMULATED_ORDER",
                before_state=None,
                after_state={"fill_id": fill.id},
                correlation_id=intent.correlation_id,
            )
        except OrderRejected as exc:
            order = SimulatedOrder(
                order_intent_id=intent.id,
                backtest_run_id=run.backtest_run_id,
                portfolio_id=run.portfolio_id,
                instrument_id=run.instrument_id,
                status=SimulatedOrderStatus.REJECTED,
                submitted_at=intent.created_at,
                eligible_execution_time=intent.eligible_execution_time,
                requested_quantity=intent.requested_quantity,
                rejection_reason_nullable=exc.reason_code,
            )
            self.repository.append_order(order)
            self.repository.replace_intent(
                replace(intent, status=OrderIntentStatus.REJECTED, reason_code=exc.reason_code)
            )
            self.repository.append_event(
                backtest_run_id=run.backtest_run_id,
                event_type=BacktestEventType.ORDER_REJECTED,
                event_time=utc_now(),
                entity_type="SimulatedOrder",
                entity_id=order.id,
                payload_json={"reason_code": exc.reason_code, "message": str(exc)},
                correlation_id=intent.correlation_id,
            )
            self.audit_log.record(
                event_type="ORDER_REJECTED",
                entity_type="SimulatedOrder",
                entity_id=order.id,
                actor_type="SYSTEM_SERVICE",
                actor_id="backtest-engine",
                action="REJECT_SIMULATED_ORDER",
                before_state=None,
                after_state={"reason_code": exc.reason_code},
                correlation_id=intent.correlation_id,
            )

    def _value_portfolio(
        self,
        run: BacktestRun,
        market_data: MarketDataReader,
        session: Any,
        close_time: datetime,
        previous_hwm: Decimal,
        correlation_id: str,
    ) -> Decimal:
        close_price = market_data.get_close(run.instrument_id, session)
        if close_price is None or close_price <= 0:
            raise ReconciliationError(f"Missing close price for {session}.")
        portfolio = self.repository.portfolios[run.backtest_run_id]
        qty = self.repository.current_quantity(run.backtest_run_id)
        basis = self.repository.current_cost_basis(run.backtest_run_id)
        market_value = gross_notional(qty, close_price)
        current_nav = nav(portfolio.current_available_cash, market_value)
        realized = self.repository.realized_pnl(run.backtest_run_id)
        unrealized = unrealized_pnl(close_price, basis, qty)
        expected_nav = money(run.starting_cash + realized + unrealized)
        if current_nav != expected_nav:
            raise ReconciliationError(
                f"NAV reconciliation mismatch: nav={current_nav} expected={expected_nav}"
            )
        hwm = high_water_mark(previous_hwm, current_nav)
        snapshot = PortfolioNavSnapshot(
            backtest_run_id=run.backtest_run_id,
            portfolio_id=run.portfolio_id,
            valuation_time=close_time,
            market_session_date=session,
            available_cash=portfolio.current_available_cash,
            reserved_cash=Decimal(0),
            gross_market_value=market_value,
            net_market_value=market_value,
            position_quantity=qty,
            position_cost_basis=basis,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            portfolio_nav=current_nav,
            drawdown=drawdown(current_nav, hwm),
            high_water_mark=hwm,
            market_price_reference=close_price,
            dataset_version_id=run.dataset_version_id,
        )
        self.repository.append_nav(snapshot)
        self.repository.save_portfolio(
            update_portfolio(portfolio, current_market_value=market_value, current_nav=current_nav)
        )
        self.repository.append_event(
            backtest_run_id=run.backtest_run_id,
            event_type=BacktestEventType.POSITION_VALUED,
            event_time=close_time,
            market_session_date=session,
            payload_json={"close_price": str(close_price), "quantity": str(qty)},
            correlation_id=correlation_id,
        )
        self.repository.append_event(
            backtest_run_id=run.backtest_run_id,
            event_type=BacktestEventType.NAV_SNAPSHOT_CREATED,
            event_time=close_time,
            market_session_date=session,
            entity_type="PortfolioNavSnapshot",
            entity_id=snapshot.id,
            payload_json={"portfolio_nav": str(current_nav), "drawdown": str(snapshot.drawdown)},
            correlation_id=correlation_id,
        )
        return hwm
