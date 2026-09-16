from __future__ import annotations

from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.live_trading.domain import (
    LiveApprovalDecision,
    LiveIncidentType,
    LiveIntentStatus,
    LiveOrder,
    LiveOrderIntent,
    LiveOrderStatus,
    LivePortfolio,
    LivePortfolioConfiguration,
    LivePortfolioStatus,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.services import LiveOrderStatusMonitor
from aegis.provider_adapters.kite_connect_order_adapter import BrokerOrderStatus
from aegis.shared.time import utc_now


class ScriptedOrderAdapter:
    name = "kite_connect_orders"

    def __init__(self) -> None:
        self._scripts: dict[str, BrokerOrderStatus] = {}

    def script(self, broker_order_id: str, status: BrokerOrderStatus) -> None:
        self._scripts[broker_order_id] = status

    def get_order_status(self, *, broker_order_id: str) -> BrokerOrderStatus:
        return self._scripts[broker_order_id]


def _portfolio(**overrides) -> LivePortfolio:
    kwargs = {
        "name": "Pilot",
        "description": "test",
        "starting_capital": Decimal(400000),
        "pilot_capital_cap": Decimal(400000),
        "risk_profile_version_id": "v1",
        "portfolio_configuration_version": "v1",
        "created_by": "founder",
        "status": LivePortfolioStatus.ACTIVE,
    }
    kwargs.update(overrides)
    return LivePortfolio(**kwargs)


def _config(portfolio: LivePortfolio) -> LivePortfolioConfiguration:
    return LivePortfolioConfiguration(
        live_portfolio_id=portfolio.live_portfolio_id,
        version="v1",
        risk_profile_version_id="v1",
        minimum_cash_weight=Decimal("0.20"),
        maximum_gross_equity_exposure=Decimal("0.80"),
        maximum_position_count=50,
        settlement_model_version="v1",
        cost_schedule_version="v1",
        execution_model_version="v1",
        market_calendar_policy="NSE_STANDARD",
        valuation_policy="CLOSE",
        corporate_action_policy="FREEZE_ON_UNSUPPORTED",
        created_by="founder",
    )


def _open_order(
    repo, portfolio, *, side="BUY", broker_order_id="BROKER-1", requested_quantity=Decimal(10)
) -> LiveOrder:
    now = utc_now()
    intent = LiveOrderIntent(
        live_portfolio_id=portfolio.live_portfolio_id,
        live_strategy_config_id="cfg1",
        strategy_version_id="DiversifiedRiskOverlayStrategyV2",
        instrument_id="AEGIS-IN-000001",
        side=side,
        proposed_quantity=requested_quantity,
        decision_time=now,
        available_data_cutoff=now,
        eligible_execution_time=now + __import__("datetime").timedelta(hours=1),
        risk_assessment_id="r1",
        configuration_version="v1",
        idempotency_key=broker_order_id,
        correlation_id="c1",
        approval_status=LiveApprovalDecision.APPROVED,
        intent_status=LiveIntentStatus.APPROVED,
    )
    repo.save_intent(intent)
    order = LiveOrder(
        live_order_intent_id=intent.live_order_intent_id,
        live_portfolio_id=portfolio.live_portfolio_id,
        instrument_id="AEGIS-IN-000001",
        status=LiveOrderStatus.SUBMITTED_TO_BROKER,
        requested_quantity=requested_quantity,
        idempotency_key=broker_order_id,
        broker_order_id_nullable=broker_order_id,
        remaining_quantity=requested_quantity,
    )
    repo.save_order(order)
    return order


def _setup(tmp_path):
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    adapter = ScriptedOrderAdapter()
    monitor = LiveOrderStatusMonitor(repository=repo, order_adapter=adapter, audit_log=AuditLog())
    portfolio = _portfolio()
    repo.add_portfolio(portfolio, _config(portfolio))
    return repo, adapter, monitor, portfolio


def test_a_complete_fill_creates_a_real_fill_and_increments_clean_fill_count(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    _open_order(repo, portfolio)
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="1234.50",
            rejection_reason=None,
        ),
    )

    updated = monitor.poll_open_orders()

    assert len(updated) == 1
    assert updated[0].status == LiveOrderStatus.FILLED
    fills = list(repo.fills.values())
    assert len(fills) == 1
    assert fills[0].fill_price == Decimal("1234.5000")
    assert fills[0].fill_quantity == Decimal("10.000000")
    assert fills[0].broker_fill_reference == "BROKER-1"
    assert repo.portfolios[portfolio.live_portfolio_id].clean_fill_count == 1


def test_a_buy_fill_has_negative_net_cash_effect(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    _open_order(repo, portfolio, side="BUY")
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="100.00",
            rejection_reason=None,
        ),
    )
    monitor.poll_open_orders()
    fill = next(iter(repo.fills.values()))
    assert fill.net_cash_effect < 0


def test_a_sell_fill_has_positive_net_cash_effect_and_settles_t_plus_1(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    _open_order(repo, portfolio, side="SELL")
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="100.00",
            rejection_reason=None,
        ),
    )
    monitor.poll_open_orders()
    fill = next(iter(repo.fills.values()))
    assert fill.net_cash_effect > 0
    assert fill.settlement_date > fill.fill_time.date()


def test_a_buy_fill_updates_the_real_cash_and_position_ledger(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    starting_cash = repo.research_portfolios[portfolio.live_portfolio_id].cash
    _open_order(repo, portfolio, side="BUY", requested_quantity=Decimal(10))
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="100.00",
            rejection_reason=None,
        ),
    )

    monitor.poll_open_orders()

    ledger = repo.research_portfolios[portfolio.live_portfolio_id]
    assert ledger.positions["AEGIS-IN-000001"] == Decimal("10.000000")
    assert ledger.cash == starting_cash - Decimal("1000.0000")


def test_a_sell_fill_reduces_the_real_position_and_credits_unsettled_receivables(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    ledger = repo.research_portfolios[portfolio.live_portfolio_id]
    ledger.positions["AEGIS-IN-000001"] = Decimal(10)
    ledger.average_cost["AEGIS-IN-000001"] = Decimal(100)
    _open_order(repo, portfolio, side="SELL", requested_quantity=Decimal(10))
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="110.00",
            rejection_reason=None,
        ),
    )

    monitor.poll_open_orders()

    assert ledger.positions["AEGIS-IN-000001"] == Decimal("0.000000")
    assert ledger.unsettled_receivables > 0


def test_a_broker_reported_oversell_becomes_an_incident_not_a_crash(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    # No shares actually held in the real ledger -- a broker-reported sell
    # fill for shares we don't believe we hold must never crash the poll
    # loop or silently go negative.
    _open_order(repo, portfolio, side="SELL", requested_quantity=Decimal(10))
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="COMPLETE",
            filled_quantity=10,
            average_price="100.00",
            rejection_reason=None,
        ),
    )

    updated = monitor.poll_open_orders()

    assert updated[0].status == LiveOrderStatus.FILLED
    assert len(repo.fills) == 1
    reconciliation_incidents = [
        incident
        for incident in repo.incidents.values()
        if incident.incident_type == LiveIncidentType.RECONCILIATION_INCIDENT
    ]
    assert len(reconciliation_incidents) == 1


def test_a_broker_rejection_creates_an_incident_and_resets_clean_fill_count(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    repo.save_portfolio(portfolio.record_clean_fill().record_clean_fill())
    assert repo.portfolios[portfolio.live_portfolio_id].clean_fill_count == 2

    _open_order(repo, portfolio, broker_order_id="BROKER-2")
    adapter.script(
        "BROKER-2",
        BrokerOrderStatus(
            broker_order_id="BROKER-2",
            status="REJECTED",
            filled_quantity=0,
            average_price=None,
            rejection_reason="Insufficient margin",
        ),
    )

    updated = monitor.poll_open_orders()

    assert updated[0].status == LiveOrderStatus.REJECTED_BY_BROKER
    assert len(repo.incidents) == 1
    incident = next(iter(repo.incidents.values()))
    assert incident.incident_type == LiveIncidentType.BROKER_INCIDENT
    assert "Insufficient margin" in incident.description
    assert repo.portfolios[portfolio.live_portfolio_id].clean_fill_count == 0


def test_a_partial_fill_updates_quantities_without_recording_a_fill_yet(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    _open_order(repo, portfolio, requested_quantity=Decimal(10))
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="OPEN",
            filled_quantity=4,
            average_price=None,
            rejection_reason=None,
        ),
    )

    updated = monitor.poll_open_orders()

    assert updated[0].status == LiveOrderStatus.PARTIALLY_FILLED
    assert updated[0].filled_quantity == Decimal(4)
    assert updated[0].remaining_quantity == Decimal(6)
    assert repo.fills == {}  # no fill recorded until fully COMPLETE


def test_a_cancelled_order_is_marked_cancelled(tmp_path) -> None:
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    _open_order(repo, portfolio)
    adapter.script(
        "BROKER-1",
        BrokerOrderStatus(
            broker_order_id="BROKER-1",
            status="CANCELLED",
            filled_quantity=0,
            average_price=None,
            rejection_reason=None,
        ),
    )
    updated = monitor.poll_open_orders()
    assert updated[0].status == LiveOrderStatus.CANCELLED


def test_a_realistic_batch_of_open_orders_all_resolve_independently(tmp_path) -> None:
    """DiversifiedRiskOverlayStrategyV2 rebalances dozens of positions per
    cycle -- confirms the monitor handles real volume, not just one order."""
    repo, adapter, monitor, portfolio = _setup(tmp_path)
    for i in range(25):
        broker_order_id = f"BROKER-{i}"
        _open_order(repo, portfolio, broker_order_id=broker_order_id)
        if i % 3 == 0:
            adapter.script(
                broker_order_id,
                BrokerOrderStatus(
                    broker_order_id=broker_order_id,
                    status="COMPLETE",
                    filled_quantity=10,
                    average_price="500.00",
                    rejection_reason=None,
                ),
            )
        elif i % 3 == 1:
            adapter.script(
                broker_order_id,
                BrokerOrderStatus(
                    broker_order_id=broker_order_id,
                    status="REJECTED",
                    filled_quantity=0,
                    average_price=None,
                    rejection_reason="No liquidity",
                ),
            )
        else:
            adapter.script(
                broker_order_id,
                BrokerOrderStatus(
                    broker_order_id=broker_order_id,
                    status="OPEN",
                    filled_quantity=0,
                    average_price=None,
                    rejection_reason=None,
                ),
            )

    updated = monitor.poll_open_orders()
    assert len(updated) == 25
    filled = [o for o in updated if o.status == LiveOrderStatus.FILLED]
    rejected = [o for o in updated if o.status == LiveOrderStatus.REJECTED_BY_BROKER]
    still_open = [o for o in updated if o.status == LiveOrderStatus.OPEN]
    assert len(filled) == 9  # i in {0,3,6,...,24}
    assert len(rejected) == 8  # i in {1,4,7,...,22}
    assert len(still_open) == 8  # i in {2,5,8,...,23}
