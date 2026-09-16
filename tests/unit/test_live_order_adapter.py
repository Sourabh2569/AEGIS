from __future__ import annotations

from typing import Any

import pytest
from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.kite_connect_order_adapter import KiteConnectOrderAdapter


class FakeKiteOrderClient:
    """A scriptable fake -- never touches the real Kite Connect API. No
    real order-placement credentials exist yet for this project; every
    test here must pass without any network or credentials."""

    def __init__(self) -> None:
        self.placed_orders: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self._order_history: dict[str, list[dict[str, Any]]] = {}
        self._positions: dict[str, Any] = {}
        self._margins: dict[str, Any] = {}

    def place_order(
        self,
        variety,
        exchange,
        tradingsymbol,
        transaction_type,
        quantity,
        product,
        order_type,
        tag,
        **kwargs,
    ) -> str:
        order_id = f"BROKER-{len(self.placed_orders) + 1}"
        self.placed_orders.append(
            {
                "variety": variety,
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "product": product,
                "order_type": order_type,
                "tag": tag,
                "order_id": order_id,
            }
        )
        return order_id

    def cancel_order(self, variety, order_id, **kwargs) -> str:
        self.cancelled.append(order_id)
        return order_id

    def order_history(self, order_id: str) -> list[dict[str, Any]]:
        return self._order_history.get(order_id, [])

    def positions(self) -> dict[str, Any]:
        return self._positions

    def margins(self) -> dict[str, Any]:
        return self._margins

    def script_order_history(self, order_id: str, history: list[dict[str, Any]]) -> None:
        self._order_history[order_id] = history


def _approved_license() -> ProviderLicense:
    return ProviderLicense(
        provider_id="kite-connect-orders",
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="test-only approval",
        automation_rights=True,
        backtesting_rights=False,
        model_training_rights=False,
        dashboard_display_rights=False,
        data_retention_period="not-recorded",
    )


def test_place_order_rejected_when_live_execution_disabled() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=False,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    with pytest.raises(PermissionError, match="LIVE_EXECUTION_ENABLED"):
        adapter.place_order(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_tag="TEST",
            correlation_id="c1",
        )


def test_place_order_rejected_when_broker_order_access_disabled() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=True,
        broker_order_access_setting=False,
        configured=True,
        license_=_approved_license(),
    )
    with pytest.raises(PermissionError, match="BROKER_ORDER_ACCESS"):
        adapter.place_order(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_tag="TEST",
            correlation_id="c1",
        )


def test_place_order_rejected_when_license_not_approved() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        # default license is PENDING
    )
    with pytest.raises(PermissionError, match="PENDING"):
        adapter.place_order(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_tag="TEST",
            correlation_id="c1",
        )


def test_place_order_rejected_when_not_configured() -> None:
    adapter = KiteConnectOrderAdapter(
        client=None,
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=False,
        license_=_approved_license(),
    )
    with pytest.raises(PermissionError, match="not configured"):
        adapter.place_order(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_tag="TEST",
            correlation_id="c1",
        )


def test_place_order_requires_a_non_empty_tag_even_when_everything_else_allows_it() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    with pytest.raises(ValueError, match="order_tag"):
        adapter.place_order(
            tradingsymbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_tag="",
            correlation_id="c1",
        )


def test_place_order_calls_fake_client_with_required_tag_when_fully_allowed() -> None:
    client = FakeKiteOrderClient()
    adapter = KiteConnectOrderAdapter(
        client=client,
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    order_id = adapter.place_order(
        tradingsymbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=5,
        order_tag="AEGIS-PILOT-1",
        correlation_id="c1",
    )
    assert order_id == "BROKER-1"
    assert len(client.placed_orders) == 1
    assert client.placed_orders[0]["tag"] == "AEGIS-PILOT-1"
    assert client.placed_orders[0]["quantity"] == 5


def test_cancel_order_also_requires_full_permission() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=False,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    with pytest.raises(PermissionError):
        adapter.cancel_order(broker_order_id="BROKER-1")


def test_get_order_status_maps_a_real_fake_broker_response() -> None:
    client = FakeKiteOrderClient()
    client.script_order_history(
        "BROKER-1",
        [
            {"status": "OPEN", "filled_quantity": 0},
            {"status": "COMPLETE", "filled_quantity": 5, "average_price": 2500.5},
        ],
    )
    adapter = KiteConnectOrderAdapter(
        client=client,
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    status = adapter.get_order_status(broker_order_id="BROKER-1")
    assert status.status == "COMPLETE"
    assert status.filled_quantity == 5
    assert status.average_price == "2500.5"


def test_get_order_status_handles_a_rejection() -> None:
    client = FakeKiteOrderClient()
    client.script_order_history(
        "BROKER-2",
        [{"status": "REJECTED", "filled_quantity": 0, "status_message": "Insufficient margin"}],
    )
    adapter = KiteConnectOrderAdapter(
        client=client,
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    status = adapter.get_order_status(broker_order_id="BROKER-2")
    assert status.status == "REJECTED"
    assert status.rejection_reason == "Insufficient margin"


def test_get_order_status_for_unknown_order_is_honest_not_fabricated() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    status = adapter.get_order_status(broker_order_id="NEVER-PLACED")
    assert status.status == "UNKNOWN"


def test_get_health_status_is_unhealthy_by_default() -> None:
    adapter = KiteConnectOrderAdapter()
    health = adapter.get_health_status()
    assert health.healthy is False


def test_get_health_status_is_healthy_only_when_everything_lines_up() -> None:
    adapter = KiteConnectOrderAdapter(
        client=FakeKiteOrderClient(),
        live_execution_enabled=True,
        broker_order_access_setting=True,
        configured=True,
        license_=_approved_license(),
    )
    health = adapter.get_health_status()
    assert health.healthy is True
    assert health.order_access is True
