from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult


class KiteOrderClientProtocol(Protocol):
    """The subset of kiteconnect.KiteConnect's WRITE surface this adapter
    depends on -- isolated as a Protocol exactly like KiteClientProtocol in
    kite_connect_provider.py, so every test here can inject a fake client
    instead of a real paid Kite Connect order-placement subscription (none
    exists yet -- the founder currently has data-only Kite access)."""

    def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        product: str,
        order_type: str,
        tag: str,
        **kwargs: Any,
    ) -> str: ...

    def cancel_order(self, variety: str, order_id: str, **kwargs: Any) -> str: ...

    def order_history(self, order_id: str) -> list[dict[str, Any]]: ...

    def positions(self) -> dict[str, Any]: ...

    def margins(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BrokerOrderStatus:
    """A real, honest translation of whatever the broker's order_history()
    actually returned -- never a guess at what a fill 'should' look like."""

    broker_order_id: str
    status: str
    filled_quantity: int
    average_price: str | None
    rejection_reason: str | None


class KiteConnectOrderAdapter:
    """The ONLY code path in AEGIS allowed to place, cancel, or query a real
    broker order -- never called directly from an API endpoint or strategy
    code, only from LiveExecutionGateway (packages/live_trading/aegis/
    live_trading/services.py), keeping Document 007's "no direct Strategy ->
    Broker API path" structurally true.

    A genuinely separate class from KiteConnectMarketDataProvider in
    kite_connect_provider.py -- that adapter stays exactly as it is today,
    deliberately read-only (broker_order_access = False, __getattr__-blocked
    order methods). Never weaken it; this class exists instead, matching
    this project's established pattern of layering a fix/capability one
    level up rather than loosening an existing guardrail.

    Checks BOTH live_execution_enabled and broker_order_access at the point
    of every real call (_assert_write_allowed) -- defense in depth,
    independent of Settings.validate_startup()'s own unconditional block on
    both flags. Even if a future caller somehow constructed this adapter
    directly in a context that skipped startup validation (e.g. a test
    harness), it still could not place a real order.
    """

    name = "kite_connect_orders"
    broker_order_access = True

    def __init__(
        self,
        *,
        client: KiteOrderClientProtocol | None = None,
        live_execution_enabled: bool = False,
        broker_order_access_setting: bool = False,
        configured: bool = False,
        license_: ProviderLicense | None = None,
    ) -> None:
        self._client = client
        self._live_execution_enabled = live_execution_enabled
        self._broker_order_access_setting = broker_order_access_setting
        self.configured = configured and client is not None
        self._license = license_ or ProviderLicense(
            provider_id="kite-connect-orders",
            license_status=ProviderLicenseStatus.PENDING,
            permitted_use=(
                "real order placement pending SEBI Feb 2025 retail-algo compliance "
                "(order tagging, static IP) and a dated Gate 7 founder sign-off"
            ),
            automation_rights=False,
            backtesting_rights=False,
            model_training_rights=False,
            dashboard_display_rights=False,
            data_retention_period="not-recorded",
            legal_review_status="PENDING_GATE_6_AND_GATE_7",
        )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _assert_write_allowed(self) -> None:
        if not self._live_execution_enabled or not self._broker_order_access_setting:
            raise PermissionError(
                "LIVE_EXECUTION_ENABLED and BROKER_ORDER_ACCESS must both be true "
                "to place, cancel, or query real broker orders."
            )
        if self._license.license_status != ProviderLicenseStatus.APPROVED:
            raise PermissionError(f"Order-placement license is {self._license.license_status}.")
        if not self.configured or self._client is None:
            raise PermissionError("Order-placement client not configured.")

    def place_order(
        self,
        *,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_tag: str,
        correlation_id: str,
        product: str = "CNC",
        order_type: str = "MARKET",
        variety: str = "regular",
    ) -> str:
        """Returns the broker's real order id. order_tag is mandatory, never
        optional -- the concrete engineering hook for SEBI's real "orders
        must still be tagged" retail-algo requirement (Gate 6). Quantity is
        never second-guessed or re-derived here -- this method trusts
        whatever the Execution Preflight Gate already approved; it is never
        called from anywhere else."""
        self._assert_write_allowed()
        if not order_tag:
            raise ValueError("order_tag is mandatory for every real order.")
        assert self._client is not None
        return self._client.place_order(
            variety,
            exchange,
            tradingsymbol,
            transaction_type,
            quantity,
            product,
            order_type,
            order_tag,
        )

    def cancel_order(self, *, broker_order_id: str, variety: str = "regular") -> str:
        self._assert_write_allowed()
        assert self._client is not None
        return self._client.cancel_order(variety, broker_order_id)

    def get_order_status(self, *, broker_order_id: str) -> BrokerOrderStatus:
        self._assert_write_allowed()
        assert self._client is not None
        history = self._client.order_history(broker_order_id)
        if not history:
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status="UNKNOWN",
                filled_quantity=0,
                average_price=None,
                rejection_reason=None,
            )
        latest = history[-1]
        return BrokerOrderStatus(
            broker_order_id=broker_order_id,
            status=str(latest.get("status", "UNKNOWN")),
            filled_quantity=int(latest.get("filled_quantity", 0)),
            average_price=(
                str(latest["average_price"]) if latest.get("average_price") is not None else None
            ),
            rejection_reason=latest.get("status_message"),
        )

    def get_positions(self) -> dict[str, Any]:
        self._assert_write_allowed()
        assert self._client is not None
        return self._client.positions()

    def get_margins(self) -> dict[str, Any]:
        self._assert_write_allowed()
        assert self._client is not None
        return self._client.margins()

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        healthy = (
            self._live_execution_enabled
            and self._broker_order_access_setting
            and self.configured
            and self._license.license_status == ProviderLicenseStatus.APPROVED
        )
        return ProviderHealthResult(
            healthy=healthy,
            message=(
                "Order-placement adapter ready."
                if healthy
                else "Order-placement adapter not ready -- flags, license, or client missing."
            ),
            checked_at=self._now(),
            mode="LIVE_TRADING",
            order_access=self.broker_order_access,
        )
