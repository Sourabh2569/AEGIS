from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aegis.audit.service import AuditLog
from aegis.live_trading.domain import (
    LiveApproval,
    LiveApprovalDecision,
    LiveIntentStatus,
    LiveOrderIntent,
    LiveOrderStatus,
    LivePortfolio,
    LivePortfolioStatus,
)
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.preflight import ExecutionPreflightGate
from aegis.live_trading.services import LiveExecutionGateway
from aegis.paper_trading.services import PaperTradingCalendarService
from aegis.provider_adapters.base import ProviderHealthResult
from aegis.shared.time import utc_now


class FakeOrderAdapter:
    name = "kite_connect_orders"

    def __init__(self) -> None:
        self.placed: list[dict] = []
        self.fail_next = False

    def get_health_status(self) -> ProviderHealthResult:
        return ProviderHealthResult(healthy=True, message="ready")

    def place_order(self, *, tradingsymbol, exchange, transaction_type, quantity, order_tag, correlation_id):
        if self.fail_next:
            raise RuntimeError("simulated broker network failure")
        order_id = f"BROKER-{len(self.placed) + 1}"
        self.placed.append(
            {"tradingsymbol": tradingsymbol, "transaction_type": transaction_type, "quantity": quantity, "tag": order_tag, "order_id": order_id}
        )
        return order_id


NOW = utc_now()
CALENDAR = PaperTradingCalendarService(sessions=[NOW.date()])


def _setup(tmp_path):
    repo = SqliteLiveTradingRepository(tmp_path / "live.sqlite")
    adapter = FakeOrderAdapter()
    preflight = ExecutionPreflightGate(repository=repo, calendar=CALENDAR, order_adapter=adapter)
    audit_log = AuditLog()
    gateway = LiveExecutionGateway(repository=repo, preflight=preflight, order_adapter=adapter, audit_log=audit_log)
    portfolio = LivePortfolio(
        name="Pilot", description="test", starting_capital=Decimal(400000),
        pilot_capital_cap=Decimal(400000), risk_profile_version_id="v1",
        portfolio_configuration_version="v1", created_by="founder", status=LivePortfolioStatus.ACTIVE,
    )
    repo.add_portfolio(portfolio, config=_config(portfolio))
    return repo, adapter, gateway, portfolio


def _config(portfolio):
    from aegis.live_trading.domain import LivePortfolioConfiguration

    return LivePortfolioConfiguration(
        live_portfolio_id=portfolio.live_portfolio_id, version="v1", risk_profile_version_id="v1",
        minimum_cash_weight=Decimal("0.20"), maximum_gross_equity_exposure=Decimal("0.80"),
        maximum_position_count=50, settlement_model_version="v1", cost_schedule_version="v1",
        execution_model_version="v1", market_calendar_policy="NSE_STANDARD", valuation_policy="CLOSE",
        corporate_action_policy="FREEZE_ON_UNSUPPORTED", created_by="founder",
    )


def _approved_intent(repo, portfolio, *, instrument_id="AEGIS-IN-000001", quantity=Decimal(10), idempotency_key="k1"):
    decision_time = NOW - timedelta(minutes=5)
    intent = LiveOrderIntent(
        live_portfolio_id=portfolio.live_portfolio_id, live_strategy_config_id="cfg1",
        strategy_version_id="DiversifiedRiskOverlayStrategyV2", instrument_id=instrument_id, side="BUY",
        proposed_quantity=quantity, decision_time=decision_time, available_data_cutoff=decision_time,
        eligible_execution_time=NOW + timedelta(hours=1), risk_assessment_id="r1",
        configuration_version="v1", idempotency_key=idempotency_key, correlation_id="c1",
        approval_status=LiveApprovalDecision.APPROVED, intent_status=LiveIntentStatus.APPROVED,
        approved_quantity_nullable=quantity,
    )
    repo.save_intent(intent)
    repo.save_approval(
        LiveApproval(
            live_order_intent_id=intent.live_order_intent_id, approver_id="founder",
            decision=LiveApprovalDecision.APPROVED, decision_time=NOW, risk_assessment_id="r1",
            live_strategy_config_id="cfg1", reason="fine", expiry_time=NOW + timedelta(hours=18),
        )
    )
    return intent


def test_submit_approved_orders_places_a_real_order_via_the_fake_adapter(tmp_path) -> None:
    repo, adapter, gateway, portfolio = _setup(tmp_path)
    intent = _approved_intent(repo, portfolio)

    orders = gateway.submit_approved_orders(
        live_portfolio_id=portfolio.live_portfolio_id, execution_time=NOW,
        entry_prices={"AEGIS-IN-000001": Decimal(1000)},
        symbol_by_instrument={"AEGIS-IN-000001": "RELIANCE"},
        existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert len(orders) == 1
    assert orders[0].status == LiveOrderStatus.SUBMITTED_TO_BROKER
    assert orders[0].broker_order_id_nullable == "BROKER-1"
    assert len(adapter.placed) == 1
    assert adapter.placed[0]["tradingsymbol"] == "RELIANCE"
    assert adapter.placed[0]["tag"]  # a real, non-empty tag was sent


def test_a_preflight_failure_creates_a_blocked_order_never_calls_the_adapter(tmp_path) -> None:
    repo, adapter, gateway, portfolio = _setup(tmp_path)
    frozen = portfolio.freeze("manual review")
    repo.save_portfolio(frozen)
    intent = _approved_intent(repo, portfolio)

    orders = gateway.submit_approved_orders(
        live_portfolio_id=portfolio.live_portfolio_id, execution_time=NOW,
        entry_prices={"AEGIS-IN-000001": Decimal(1000)},
        symbol_by_instrument={"AEGIS-IN-000001": "RELIANCE"},
        existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert len(orders) == 1
    assert orders[0].status == LiveOrderStatus.BLOCKED
    assert adapter.placed == []


def test_a_broker_call_failure_marks_failed_and_does_not_crash_the_batch(tmp_path) -> None:
    repo, adapter, gateway, portfolio = _setup(tmp_path)
    adapter.fail_next = True
    intent = _approved_intent(repo, portfolio)

    orders = gateway.submit_approved_orders(
        live_portfolio_id=portfolio.live_portfolio_id, execution_time=NOW,
        entry_prices={"AEGIS-IN-000001": Decimal(1000)},
        symbol_by_instrument={"AEGIS-IN-000001": "RELIANCE"},
        existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert len(orders) == 1
    assert orders[0].status == LiveOrderStatus.FAILED
    assert "BROKER_CALL_FAILED" in (orders[0].rejection_reason_nullable or "")


def test_missing_symbol_mapping_fails_honestly_without_a_fabricated_call(tmp_path) -> None:
    repo, adapter, gateway, portfolio = _setup(tmp_path)
    _approved_intent(repo, portfolio)

    orders = gateway.submit_approved_orders(
        live_portfolio_id=portfolio.live_portfolio_id, execution_time=NOW,
        entry_prices={"AEGIS-IN-000001": Decimal(1000)},
        symbol_by_instrument={},  # no mapping at all
        existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert orders[0].status == LiveOrderStatus.FAILED
    assert orders[0].rejection_reason_nullable == "NO_REAL_SYMBOL_MAPPING"
    assert adapter.placed == []


def test_a_realistic_multi_position_rebalance_batch_respects_the_running_capital_cap(tmp_path) -> None:
    """DiversifiedRiskOverlayStrategyV2 rebalances dozens of positions per
    cycle -- this proves the capital cap is enforced cumulatively across
    the WHOLE batch, not just against pre-batch deployed notional."""
    repo, adapter, gateway, portfolio = _setup(tmp_path)
    small_cap_portfolio = LivePortfolio(
        name="Pilot", description="test", starting_capital=Decimal(25000),
        pilot_capital_cap=Decimal(25000), risk_profile_version_id="v1",
        portfolio_configuration_version="v1", created_by="founder", status=LivePortfolioStatus.ACTIVE,
        live_portfolio_id=portfolio.live_portfolio_id,
    )
    repo.save_portfolio(small_cap_portfolio)

    symbol_by_instrument = {}
    entry_prices = {}
    for i in range(30):
        instrument_id = f"AEGIS-IN-{i:06d}"
        symbol_by_instrument[instrument_id] = f"SYMBOL{i}"
        entry_prices[instrument_id] = Decimal(1000)
        _approved_intent(repo, portfolio, instrument_id=instrument_id, quantity=Decimal(10), idempotency_key=f"k{i}")

    orders = gateway.submit_approved_orders(
        live_portfolio_id=portfolio.live_portfolio_id, execution_time=NOW,
        entry_prices=entry_prices, symbol_by_instrument=symbol_by_instrument,
        existing_deployed_notional=Decimal(0), kill_switches=[],
    )
    assert len(orders) == 30
    submitted = [o for o in orders if o.status == LiveOrderStatus.SUBMITTED_TO_BROKER]
    blocked = [o for o in orders if o.status == LiveOrderStatus.BLOCKED]
    # Each order is Rs 10,000 notional; Rs 25,000 cap allows exactly 2 before
    # the 3rd would exceed it -- the rest must be blocked on capital_cap,
    # not silently allowed through.
    assert len(submitted) == 2
    assert len(blocked) == 28
    assert len(adapter.placed) == 2  # the real broker call only happened for the ones that passed
