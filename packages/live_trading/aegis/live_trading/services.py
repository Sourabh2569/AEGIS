from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from datetime import date as date_
from datetime import time as time_
from decimal import Decimal
from typing import Any, Callable

from aegis.live_trading.domain import (
    LiveApproval,
    LiveApprovalDecision,
    LiveExecutionPreflight,
    LiveFill,
    LiveIncident,
    LiveIncidentType,
    LiveIntentStatus,
    LiveOrder,
    LiveOrderIntent,
    LiveOrderStatus,
    LivePortfolio,
    LivePortfolioConfiguration,
    LivePortfolioStatus,
    LiveReconciliationRecord,
    LiveStrategyConfiguration,
    LiveStrategyConfigStatus,
    default_live_approval_expiry,
)
from aegis.live_trading.preflight import ExecutionPreflightGate
from aegis.portfolio.sprint2 import ResearchPortfolio
from aegis.risk.engine import KillSwitch, PositionSizingEngine, RiskDecision, RiskProfileVersion
from aegis.shared.ids import new_id
from aegis.shared.money import money, quantity
from aegis.shared.time import require_aware_utc, utc_now


class LiveTradingRepository:
    """Deliberately a separate in-memory store from PaperTradingRepository --
    Document 007's own stance is that live and paper data must never be
    structurally co-mingled. Kill switches are the one thing later wired to
    be genuinely shared across both repositories at the orchestrator-
    construction layer (see Phase 7 of the live-trading plan) rather than
    duplicated here silently."""

    def __init__(self) -> None:
        self.portfolios: dict[str, LivePortfolio] = {}
        self.portfolio_configs: dict[str, LivePortfolioConfiguration] = {}
        self.strategy_configs: dict[str, LiveStrategyConfiguration] = {}
        self.intents: dict[str, LiveOrderIntent] = {}
        self.approvals: dict[str, LiveApproval] = {}
        self.orders: dict[str, LiveOrder] = {}
        self.fills: dict[str, LiveFill] = {}
        self.reconciliations: dict[str, list[LiveReconciliationRecord]] = {}
        self.incidents: dict[str, LiveIncident] = {}
        self.preflights: dict[str, LiveExecutionPreflight] = {}
        self.executed_idempotency_keys: set[str] = set()
        self.kill_switches: dict[str, KillSwitch] = {}
        # Real cash/position ledger -- reused directly from paper_trading's
        # ResearchPortfolio rather than duplicated (see Phase 1's deferred-
        # entities note: LiveCashLedger/LivePositionLedger fold into this).
        # Mutated ONLY by LiveOrderStatusMonitor._record_fill(), from a real
        # broker-reported fill -- never by the decision cycle itself, which
        # only reads it to size new intents against real current holdings.
        self.research_portfolios: dict[str, ResearchPortfolio] = {}

    def add_portfolio(
        self, portfolio: LivePortfolio, config: LivePortfolioConfiguration
    ) -> None:
        self.portfolios[portfolio.live_portfolio_id] = portfolio
        self.portfolio_configs[portfolio.live_portfolio_id] = config
        self.research_portfolios[portfolio.live_portfolio_id] = ResearchPortfolio(
            portfolio_id=portfolio.live_portfolio_id,
            cash=portfolio.starting_capital,
        )

    def save_portfolio(self, portfolio: LivePortfolio) -> None:
        self.portfolios[portfolio.live_portfolio_id] = portfolio

    def save_strategy_config(self, config: LiveStrategyConfiguration) -> None:
        self.strategy_configs[config.live_strategy_config_id] = config

    def active_strategy_configs(self, live_portfolio_id: str) -> list[LiveStrategyConfiguration]:
        return [
            config
            for config in self.strategy_configs.values()
            if config.live_portfolio_id == live_portfolio_id
            and config.status == LiveStrategyConfigStatus.ACTIVE
        ]

    def save_intent(self, intent: LiveOrderIntent) -> None:
        self.intents[intent.live_order_intent_id] = intent

    def save_approval(self, approval: LiveApproval) -> None:
        self.approvals[approval.live_order_intent_id] = approval

    def save_order(self, order: LiveOrder) -> None:
        self.orders[order.live_order_id] = order

    def save_fill(self, fill: LiveFill) -> None:
        self.fills[fill.live_fill_id] = fill

    def save_incident(self, incident: LiveIncident) -> None:
        self.incidents[incident.id] = incident

    def save_preflight(self, preflight: LiveExecutionPreflight) -> None:
        self.preflights[preflight.id] = preflight

    def add_reconciliation(self, record: LiveReconciliationRecord) -> None:
        self.reconciliations.setdefault(record.live_portfolio_id, []).append(record)

    def orders_for_portfolio(self, live_portfolio_id: str) -> list[LiveOrder]:
        return [
            order
            for order in self.orders.values()
            if self.intents.get(order.live_order_intent_id, None) is not None
            and self.intents[order.live_order_intent_id].live_portfolio_id == live_portfolio_id
        ]

    def open_orders(self) -> list[LiveOrder]:
        open_statuses = {
            LiveOrderStatus.SUBMITTED_TO_BROKER,
            LiveOrderStatus.BROKER_ACKNOWLEDGED,
            LiveOrderStatus.OPEN,
            LiveOrderStatus.PARTIALLY_FILLED,
        }
        return [order for order in self.orders.values() if order.status in open_statuses]


class LiveApprovalService:
    """Mirrors PaperApprovalService's exact shape and portfolio-status
    guard, with one deliberate fix: PaperApprovalService.reject() never
    calls audit_log.record() (only approve() does) -- a real asymmetry
    that's fine for simulated paper trading but not acceptable here, given
    real-money stakes. Both approve() and reject() are audited."""

    def __init__(self, repository: LiveTradingRepository, audit_log: Any) -> None:
        self.repository = repository
        self.audit_log = audit_log

    def approve(
        self,
        intent_id: str,
        approver_id: str,
        *,
        confirmed_amount: Decimal | None = None,
        now: datetime | None = None,
    ) -> LiveApproval:
        now = require_aware_utc(now or utc_now())
        intent = self.repository.intents[intent_id]
        portfolio = self.repository.portfolios[intent.live_portfolio_id]
        if portfolio.status in {
            LivePortfolioStatus.CAPITAL_PRESERVATION,
            LivePortfolioStatus.FROZEN,
            LivePortfolioStatus.PAUSED,
        }:
            raise ValueError(f"APPROVAL_BLOCKED_BY_PORTFOLIO_STATE:{portfolio.status}")
        approval = LiveApproval(
            live_order_intent_id=intent.live_order_intent_id,
            approver_id=approver_id,
            decision=LiveApprovalDecision.APPROVED,
            decision_time=now,
            risk_assessment_id=intent.risk_assessment_id,
            live_strategy_config_id=intent.live_strategy_config_id,
            reason="Approved for real broker execution.",
            expiry_time=max(
                default_live_approval_expiry(now), intent.eligible_execution_time + timedelta(hours=1)
            ),
            confirmed_amount_nullable=confirmed_amount,
        )
        self.repository.save_approval(approval)
        self.repository.save_intent(
            replace(
                intent,
                approval_status=LiveApprovalDecision.APPROVED,
                intent_status=LiveIntentStatus.APPROVED,
                approved_quantity_nullable=intent.approved_quantity_nullable
                or intent.proposed_quantity,
                updated_at=utc_now(),
            )
        )
        self.audit_log.record(
            event_type="LIVE_INTENT_APPROVED",
            entity_type="LiveOrderIntent",
            entity_id=intent_id,
            actor_type="USER",
            actor_id=approver_id,
            action="APPROVE_LIVE_INTENT",
            before_state=None,
            after_state={
                "confirmed_amount": str(confirmed_amount) if confirmed_amount is not None else None,
            },
            correlation_id=intent.correlation_id,
        )
        return approval

    def reject(self, intent_id: str, approver_id: str, reason: str) -> LiveApproval:
        if not reason:
            raise ValueError("REJECTION_REASON_REQUIRED")
        now = utc_now()
        intent = self.repository.intents[intent_id]
        approval = LiveApproval(
            live_order_intent_id=intent.live_order_intent_id,
            approver_id=approver_id,
            decision=LiveApprovalDecision.REJECTED,
            decision_time=now,
            risk_assessment_id=intent.risk_assessment_id,
            live_strategy_config_id=intent.live_strategy_config_id,
            reason=reason,
            expiry_time=now,
        )
        self.repository.save_approval(approval)
        self.repository.save_intent(
            replace(
                intent,
                approval_status=LiveApprovalDecision.REJECTED,
                intent_status=LiveIntentStatus.REJECTED,
                updated_at=utc_now(),
            )
        )
        self.audit_log.record(
            event_type="LIVE_INTENT_REJECTED",
            entity_type="LiveOrderIntent",
            entity_id=intent_id,
            actor_type="USER",
            actor_id=approver_id,
            action="REJECT_LIVE_INTENT",
            before_state=None,
            after_state={"reason": reason},
            correlation_id=intent.correlation_id,
        )
        return approval


class LiveExecutionGateway:
    """The only code path in AEGIS allowed to call order_adapter.place_order()
    -- mirrors PaperTradingOrchestrator.execute_approved_orders()'s
    BLOCKED-order pattern, but never marks anything FILLED itself, since a
    real broker fill is asynchronous unlike a simulated one (that's
    LiveOrderStatusMonitor's job, below)."""

    def __init__(
        self,
        *,
        repository: LiveTradingRepository,
        preflight: ExecutionPreflightGate,
        order_adapter: Any,
        audit_log: Any,
    ) -> None:
        self.repository = repository
        self.preflight = preflight
        self.order_adapter = order_adapter
        self.audit_log = audit_log

    def submit_approved_orders(
        self,
        *,
        live_portfolio_id: str,
        execution_time: datetime,
        entry_prices: dict[str, Decimal],
        symbol_by_instrument: dict[str, str],
        existing_deployed_notional: Decimal,
        kill_switches: list[KillSwitch],
        correlation_id: str | None = None,
    ) -> list[LiveOrder]:
        correlation_id = correlation_id or new_id("corr")
        portfolio = self.repository.portfolios[live_portfolio_id]
        orders: list[LiveOrder] = []
        # A running tally across this whole batch -- DiversifiedRiskOverlayStrategyV2
        # rebalances dozens of positions in one cycle, and the pilot capital
        # cap must hold across the WHOLE batch, not just against whatever
        # was deployed before this cycle started.
        running_deployed_notional = existing_deployed_notional

        for intent in list(self.repository.intents.values()):
            if intent.live_portfolio_id != live_portfolio_id:
                continue
            if intent.intent_status != LiveIntentStatus.APPROVED:
                continue

            requested_quantity = intent.approved_quantity_nullable or intent.proposed_quantity
            entry_price = entry_prices.get(intent.instrument_id)
            if entry_price is None:
                # Never fabricate a price to force a decision through --
                # honestly skip this cycle for this instrument.
                continue

            preflight_result = self.preflight.check(
                intent=intent,
                portfolio=portfolio,
                execution_time=execution_time,
                entry_price=entry_price,
                existing_deployed_notional=running_deployed_notional,
                kill_switches=kill_switches,
            )
            if not preflight_result.passed:
                order = LiveOrder(
                    live_order_intent_id=intent.live_order_intent_id,
                    live_portfolio_id=live_portfolio_id,
                    instrument_id=intent.instrument_id,
                    status=LiveOrderStatus.BLOCKED,
                    requested_quantity=requested_quantity,
                    idempotency_key=intent.idempotency_key,
                    rejection_reason_nullable=",".join(preflight_result.failure_reasons),
                )
                self.repository.save_order(order)
                orders.append(order)
                continue

            symbol = symbol_by_instrument.get(intent.instrument_id)
            if symbol is None:
                order = LiveOrder(
                    live_order_intent_id=intent.live_order_intent_id,
                    live_portfolio_id=live_portfolio_id,
                    instrument_id=intent.instrument_id,
                    status=LiveOrderStatus.FAILED,
                    requested_quantity=requested_quantity,
                    idempotency_key=intent.idempotency_key,
                    rejection_reason_nullable="NO_REAL_SYMBOL_MAPPING",
                )
                self.repository.save_order(order)
                orders.append(order)
                continue

            self.repository.executed_idempotency_keys.add(intent.idempotency_key)
            order_tag = f"AEGIS-{intent.live_order_intent_id[-16:]}"
            try:
                broker_order_id = self.order_adapter.place_order(
                    tradingsymbol=symbol,
                    exchange="NSE",
                    transaction_type=intent.side,
                    quantity=int(requested_quantity),
                    order_tag=order_tag,
                    correlation_id=correlation_id,
                )
            except Exception as exc:  # noqa: BLE001 -- a real broker call failing must never crash the batch
                order = LiveOrder(
                    live_order_intent_id=intent.live_order_intent_id,
                    live_portfolio_id=live_portfolio_id,
                    instrument_id=intent.instrument_id,
                    status=LiveOrderStatus.FAILED,
                    requested_quantity=requested_quantity,
                    idempotency_key=intent.idempotency_key,
                    rejection_reason_nullable=f"BROKER_CALL_FAILED:{exc}",
                )
                self.repository.save_order(order)
                orders.append(order)
                continue

            order = LiveOrder(
                live_order_intent_id=intent.live_order_intent_id,
                live_portfolio_id=live_portfolio_id,
                instrument_id=intent.instrument_id,
                status=LiveOrderStatus.SUBMITTED_TO_BROKER,
                requested_quantity=requested_quantity,
                idempotency_key=intent.idempotency_key,
                broker_order_id_nullable=broker_order_id,
                submitted_at_nullable=utc_now(),
                remaining_quantity=requested_quantity,
            )
            self.repository.save_order(order)
            orders.append(order)
            running_deployed_notional = money(running_deployed_notional + requested_quantity * entry_price)

            self.audit_log.record(
                event_type="LIVE_ORDER_SUBMITTED",
                entity_type="LiveOrder",
                entity_id=order.live_order_id,
                actor_type="SYSTEM",
                actor_id="live_execution_gateway",
                action="SUBMIT_REAL_ORDER",
                before_state=None,
                after_state={
                    "broker_order_id": broker_order_id,
                    "instrument_id": intent.instrument_id,
                    "quantity": str(requested_quantity),
                },
                correlation_id=correlation_id,
            )

        return orders


class LiveOrderStatusMonitor:
    """Polls every open LiveOrder against the real broker -- unlike a
    simulated paper fill (resolved synchronously, same request), a real
    order can sit OPEN or PARTIALLY_FILLED for a real, unpredictable amount
    of time. A definitive LiveFill is only ever recorded once the broker
    reports the order fully COMPLETE, from the broker's own real reported
    price/quantity -- never approximated or backfilled from an interim
    partial-fill snapshot."""

    def __init__(self, *, repository: LiveTradingRepository, order_adapter: Any, audit_log: Any) -> None:
        self.repository = repository
        self.order_adapter = order_adapter
        self.audit_log = audit_log

    def poll_open_orders(self, *, correlation_id: str | None = None) -> list[LiveOrder]:
        correlation_id = correlation_id or new_id("corr")
        updated: list[LiveOrder] = []
        for order in self.repository.open_orders():
            if order.broker_order_id_nullable is None:
                continue
            status = self.order_adapter.get_order_status(broker_order_id=order.broker_order_id_nullable)

            if status.status == "COMPLETE":
                updated.append(self._record_fill(order, status))
            elif status.status == "REJECTED":
                updated.append(self._record_rejection(order, status))
            elif status.status == "CANCELLED":
                self.repository.save_order(
                    order := _with_status(order, LiveOrderStatus.CANCELLED)
                )
                updated.append(order)
            elif status.filled_quantity > 0 and status.filled_quantity < order.requested_quantity:
                partially_filled = _with_status(
                    order,
                    LiveOrderStatus.PARTIALLY_FILLED,
                    filled_quantity=Decimal(status.filled_quantity),
                    remaining_quantity=order.requested_quantity - Decimal(status.filled_quantity),
                )
                self.repository.save_order(partially_filled)
                updated.append(partially_filled)
            else:
                acknowledged = _with_status(order, LiveOrderStatus.OPEN)
                self.repository.save_order(acknowledged)
                updated.append(acknowledged)
        return updated

    def _record_fill(self, order: LiveOrder, status: Any) -> LiveOrder:
        filled_order = _with_status(
            order,
            LiveOrderStatus.FILLED,
            filled_quantity=Decimal(status.filled_quantity),
            remaining_quantity=Decimal(0),
        )
        self.repository.save_order(filled_order)

        real_price = money(status.average_price) if status.average_price else Decimal(0)
        real_quantity = quantity(Decimal(status.filled_quantity))
        gross_notional = money(real_price * real_quantity)
        is_sell = self._is_sell(order)
        # A BUY reduces cash (negative net effect); a SELL adds to it --
        # matching the exact same sign convention paper trading already
        # uses. Settlement follows the same T+0 buy / T+1 sell convention
        # this codebase already established for paper fills.
        side_sign = Decimal(1) if is_sell else Decimal(-1)
        fill_time = utc_now()
        settlement_date = (
            (fill_time + timedelta(days=1)).date() if is_sell else fill_time.date()
        )
        fill = LiveFill(
            live_order_id=order.live_order_id,
            live_portfolio_id=order.live_portfolio_id,
            instrument_id=order.instrument_id,
            fill_time=fill_time,
            fill_quantity=real_quantity,
            fill_price=real_price,
            broker_fill_reference=status.broker_order_id,
            gross_notional=gross_notional,
            # Real per-order brokerage/fees are not available from Kite's
            # order_history() response -- Kite reports charges via a
            # separate contract-note/trades mechanism this adapter doesn't
            # call yet. Zero here is an honest "not yet available", never a
            # claim that live trading is genuinely cost-free; do not treat
            # this as a real cost figure until that data source is wired in.
            cost_total=Decimal("0.0000"),
            net_cash_effect=money(side_sign * gross_notional),
            settlement_date=settlement_date,
            fill_status="COMPLETE",
        )
        self.repository.save_fill(fill)

        # Update the REAL cash/position ledger from the broker's own
        # reported price/quantity -- the only place this ledger is ever
        # mutated for live trading. A real broker-reported oversell (more
        # shares sold than the ledger believes are held, e.g. after a
        # missed prior fill) must never crash the poll loop; it becomes an
        # honest incident instead of a fabricated correction.
        research_portfolio = self.repository.research_portfolios[order.live_portfolio_id]
        try:
            if is_sell:
                research_portfolio.sell_t_plus_1(
                    order.instrument_id, real_quantity, real_price, fill.cost_total, settlement_date
                )
            else:
                research_portfolio.buy(order.instrument_id, real_quantity, real_price, fill.cost_total)
        except ValueError as exc:
            self.repository.save_incident(
                LiveIncident(
                    live_portfolio_id=order.live_portfolio_id,
                    incident_type=LiveIncidentType.RECONCILIATION_INCIDENT,
                    severity="CRITICAL",
                    description=f"Real fill could not be applied to the internal ledger: {exc}",
                    status="OPEN",
                    reason_codes=["LEDGER_UPDATE_FAILED"],
                )
            )

        portfolio = self.repository.portfolios[order.live_portfolio_id]
        self.repository.save_portfolio(portfolio.record_clean_fill())

        self.audit_log.record(
            event_type="LIVE_ORDER_FILLED",
            entity_type="LiveFill",
            entity_id=fill.live_fill_id,
            actor_type="SYSTEM",
            actor_id="live_order_status_monitor",
            action="RECORD_REAL_FILL",
            before_state=None,
            after_state={
                "broker_order_id": order.broker_order_id_nullable,
                "fill_price": str(real_price),
                "fill_quantity": str(real_quantity),
            },
            correlation_id=new_id("corr"),
        )
        return filled_order

    def _is_sell(self, order: LiveOrder) -> bool:
        intent = self.repository.intents.get(order.live_order_intent_id)
        return intent is not None and intent.side == "SELL"

    def _record_rejection(self, order: LiveOrder, status: Any) -> LiveOrder:
        rejected_order = _with_status(
            order, LiveOrderStatus.REJECTED_BY_BROKER, rejection_reason_nullable=status.rejection_reason
        )
        self.repository.save_order(rejected_order)

        incident = LiveIncident(
            live_portfolio_id=order.live_portfolio_id,
            incident_type=LiveIncidentType.BROKER_INCIDENT,
            severity="HIGH",
            description=f"Real broker order {order.broker_order_id_nullable} rejected: {status.rejection_reason}",
            status="OPEN",
            reason_codes=["BROKER_REJECTED_ORDER"],
        )
        self.repository.save_incident(incident)

        portfolio = self.repository.portfolios[order.live_portfolio_id]
        self.repository.save_portfolio(portfolio.reset_clean_fill_count())

        self.audit_log.record(
            event_type="LIVE_ORDER_REJECTED",
            entity_type="LiveOrder",
            entity_id=order.live_order_id,
            actor_type="SYSTEM",
            actor_id="live_order_status_monitor",
            action="RECORD_REAL_REJECTION",
            before_state=None,
            after_state={"rejection_reason": status.rejection_reason},
            correlation_id=new_id("corr"),
        )
        return rejected_order


class LiveDecisionCycleService:
    """Mirrors PaperTradingOrchestrator.run_decision_cycle()'s exact
    target-weight -> sized-intent pipeline, reusing the same shared,
    unmodified PositionSizingEngine/RiskProfileVersion -- this is the one
    place a live pilot's real strategy signal ever turns into a real
    LiveOrderIntent. It only ever produces PENDING_APPROVAL intents; it
    never places an order and never touches the broker (that is
    LiveExecutionGateway's job, strictly after a human approval).

    strategy_target_resolver has the exact same signature paper trading's
    build_paper_strategy_resolver() already produces, so the same resolver
    instance can be shared by both orchestrators at the API wiring layer --
    it is a stateless, read-only function of (strategy_id, as_of date).
    """

    def __init__(
        self,
        *,
        repository: LiveTradingRepository,
        audit_log: Any,
        calendar: Any,
        sector_by_instrument: dict[str, str] | None = None,
        strategy_target_resolver: (
            Callable[[str, date_], tuple[dict[str, Decimal], dict[str, Decimal]] | None] | None
        ) = None,
        risk_engine: PositionSizingEngine | None = None,
        profile: RiskProfileVersion | None = None,
    ) -> None:
        self.repository = repository
        self.audit_log = audit_log
        self.calendar = calendar
        self.sector_by_instrument = sector_by_instrument or {}
        self.strategy_target_resolver = strategy_target_resolver
        self.risk_engine = risk_engine or PositionSizingEngine()
        self.profile = profile or RiskProfileVersion()

    def run_decision_cycle(
        self,
        *,
        live_portfolio_id: str,
        session_date: date_,
        reference_prices: dict[str, Decimal],
        correlation_id: str | None = None,
    ) -> list[LiveOrderIntent]:
        correlation_id = correlation_id or new_id("corr")
        portfolio = self.repository.portfolios[live_portfolio_id]
        research_portfolio = self.repository.research_portfolios[live_portfolio_id]
        # Move any real cash that has actually settled by today into
        # available_cash before sizing new intents -- real money, so this
        # is done eagerly rather than left for a later cycle.
        research_portfolio.settle_due(session_date)

        created: list[LiveOrderIntent] = []
        if portfolio.status in {
            LivePortfolioStatus.CAPITAL_PRESERVATION,
            LivePortfolioStatus.FROZEN,
            LivePortfolioStatus.PAUSED,
        }:
            self.audit_log.record(
                event_type="LIVE_DECISION_CYCLE_SKIPPED",
                entity_type="LivePortfolio",
                entity_id=live_portfolio_id,
                actor_type="SYSTEM",
                actor_id="live_decision_cycle_service",
                action="SKIP_PORTFOLIO_STATE_BLOCKS_DECISION",
                before_state=None,
                after_state={"status": portfolio.status.value},
                correlation_id=correlation_id,
            )
            return created

        if self.strategy_target_resolver is None:
            return created

        for config in self.repository.active_strategy_configs(live_portfolio_id):
            resolved = self.strategy_target_resolver(config.strategy_id, session_date)
            if resolved is None:
                self.audit_log.record(
                    event_type="LIVE_DECISION_CYCLE_SKIPPED",
                    entity_type="LiveStrategyConfiguration",
                    entity_id=config.live_strategy_config_id,
                    actor_type="SYSTEM",
                    actor_id="live_decision_cycle_service",
                    action="SKIP_NO_REAL_DATA_OR_UNKNOWN_STRATEGY",
                    before_state=None,
                    after_state={"strategy_id": config.strategy_id},
                    correlation_id=correlation_id,
                )
                continue
            target_weights, invalidation_prices = resolved

            market_value = money(
                sum(
                    (
                        qty * reference_prices.get(inst, Decimal(0))
                        for inst, qty in research_portfolio.positions.items()
                    ),
                    Decimal(0),
                )
            )
            portfolio_nav = money(
                research_portfolio.cash + research_portfolio.unsettled_receivables + market_value
            )
            available_cash = research_portfolio.available_cash()
            sector_values: dict[str, Decimal] = {}
            for inst, qty in research_portfolio.positions.items():
                if qty <= 0:
                    continue
                sector = self.sector_by_instrument.get(inst, "UNKNOWN")
                notional = money(qty * reference_prices.get(inst, Decimal(0)))
                sector_values[sector] = money(sector_values.get(sector, Decimal(0)) + notional)

            instrument_ids = set(target_weights) | set(research_portfolio.positions)
            for instrument_id in instrument_ids:
                price = reference_prices.get(instrument_id)
                if price is None or portfolio_nav <= 0:
                    continue  # never fabricate a price or size against a zero/negative NAV
                held_qty = research_portfolio.positions.get(instrument_id, Decimal(0))
                target_weight = target_weights.get(instrument_id, Decimal(0))
                target_qty = (
                    quantity(money(portfolio_nav * target_weight) / price)
                    if price > 0
                    else Decimal(0)
                )
                if target_qty == held_qty:
                    continue
                side = "BUY" if target_qty > held_qty else "SELL"
                proposed_quantity = abs(target_qty - held_qty)
                idempotency_key = f"{live_portfolio_id}:{session_date}:{instrument_id}:{side}"
                if idempotency_key in self.repository.executed_idempotency_keys or any(
                    intent.idempotency_key == idempotency_key
                    for intent in self.repository.intents.values()
                ):
                    continue
                sector = self.sector_by_instrument.get(instrument_id, "UNKNOWN")
                invalidation_price = invalidation_prices.get(
                    instrument_id, money(price * Decimal("0.90"))
                )
                risk = self.risk_engine.assess(
                    portfolio_id=live_portfolio_id,
                    strategy_id=config.strategy_id,
                    instrument_id=instrument_id,
                    portfolio_nav=portfolio_nav,
                    available_cash=available_cash,
                    existing_position_value=money(held_qty * price),
                    sector_value=sector_values.get(sector, Decimal(0)),
                    cluster_value=sector_values.get(sector, Decimal(0)),
                    gross_equity_value=market_value,
                    entry_price=price,
                    invalidation_price=invalidation_price,
                    proposed_quantity=proposed_quantity,
                    sector=sector,
                    cluster=sector,
                    data_quality_status="GREEN",
                    instrument_eligibility_status="ELIGIBLE",
                    profile=self.profile,
                    current_drawdown=Decimal(0),
                    kill_switches=list(self.repository.kill_switches.values()),
                    side=side,
                )
                if (
                    risk.decision
                    in {RiskDecision.APPROVED, RiskDecision.APPROVED_WITH_REDUCED_SIZE}
                    and risk.approved_quantity > 0
                ):
                    decision_time = datetime.combine(session_date, time_(10, 45), tzinfo=UTC)
                    next_session = self.calendar.next_open_session_after(decision_time)
                    intent = LiveOrderIntent(
                        live_portfolio_id=live_portfolio_id,
                        live_strategy_config_id=config.live_strategy_config_id,
                        strategy_version_id=config.strategy_version_id,
                        instrument_id=instrument_id,
                        side=side,
                        proposed_quantity=proposed_quantity,
                        decision_time=decision_time,
                        available_data_cutoff=datetime.combine(
                            session_date, time_(10, 30), tzinfo=UTC
                        ),
                        eligible_execution_time=self.calendar.open_time(next_session),
                        risk_assessment_id=risk.risk_assessment_id,
                        configuration_version=config.live_strategy_config_id,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                        reason_codes_json=risk.reason_codes,
                    )
                    self.repository.save_intent(intent)
                    created.append(intent)
        return created


def _with_status(order: LiveOrder, status: LiveOrderStatus, **overrides: Any) -> LiveOrder:
    from dataclasses import replace

    return replace(order, status=status, updated_at=utc_now(), **overrides)


# Never called automatically by anything in this codebase -- the only path
# to LivePortfolio.capital_tier ever becoming FULL is this function, and
# this function is only ever invoked from the POST /live-portfolios/{id}/
# graduate API endpoint (Phase 8), which is itself Role.FOUNDER-only.
# Document 007 explicitly prohibits "automating capital allocation" --
# this is the concrete guarantee that graduation stays a distinct,
# deliberate, dated human decision.
GRADUATION_CLEAN_FILL_THRESHOLD = 20


def graduate_live_portfolio(
    *,
    repository: LiveTradingRepository,
    live_portfolio_id: str,
    reason: str,
    confirmed_new_capital_amount: Decimal,
    graduated_by: str,
    audit_log: Any,
    correlation_id: str | None = None,
) -> LivePortfolio:
    correlation_id = correlation_id or new_id("corr")
    portfolio = repository.portfolios[live_portfolio_id]
    if not reason or not reason.strip():
        raise ValueError("REASON_REQUIRED: a non-empty reason is required to graduate.")
    if confirmed_new_capital_amount <= 0:
        raise ValueError("confirmed_new_capital_amount must be a positive real amount.")
    if portfolio.clean_fill_count < GRADUATION_CLEAN_FILL_THRESHOLD:
        raise ValueError(
            f"GRADUATION_THRESHOLD_NOT_MET: {portfolio.clean_fill_count} of "
            f"{GRADUATION_CLEAN_FILL_THRESHOLD} required clean fills."
        )

    before_tier = portfolio.capital_tier.value
    before_cap = str(portfolio.pilot_capital_cap)
    graduated = portfolio.graduate(
        new_capital_cap=confirmed_new_capital_amount, graduated_by=graduated_by
    )
    repository.save_portfolio(graduated)

    audit_log.record(
        event_type="LIVE_PORTFOLIO_GRADUATED",
        entity_type="LivePortfolio",
        entity_id=graduated.live_portfolio_id,
        actor_type="USER",
        actor_id=graduated_by,
        action="GRADUATE_PILOT_TO_FULL_CAPITAL",
        before_state={"capital_tier": before_tier, "pilot_capital_cap": before_cap},
        after_state={
            "capital_tier": graduated.capital_tier.value,
            "pilot_capital_cap": str(graduated.pilot_capital_cap),
            "reason": reason,
            "clean_fill_count_at_graduation": portfolio.clean_fill_count,
        },
        correlation_id=correlation_id,
    )
    return graduated
