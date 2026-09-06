from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from typing import Any

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope


class LiveReadOnlyMarketDataProvider:
    name = "live_readonly_market_data"
    data_source_mode = "LIVE_READONLY"
    broker_order_access = False

    def __init__(
        self, license_: ProviderLicense | None = None, *, configured: bool = False
    ) -> None:
        self.configured = configured
        self._license = license_ or ProviderLicense(
            provider_id="live-readonly-provider",
            license_status=ProviderLicenseStatus.APPROVED,
            permitted_use="read-only market data ingestion, dashboard display, and governed research",
            automation_rights=True,
            backtesting_rights=True,
            model_training_rights=False,
            dashboard_display_rights=True,
            data_retention_period="provider-contract-controlled",
            legal_review_status="APPROVED_READONLY_DATA",
        )

    def __getattr__(self, name: str) -> Any:
        blocked = {
            "place_order",
            "submit_order",
            "modify_order",
            "cancel_order",
            "get_holdings",
            "fetch_holdings",
            "mutate_holdings",
        }
        if name in blocked:
            raise AttributeError(
                f"{name} is prohibited: provider is DATA_SOURCE_MODE=LIVE_READONLY."
            )
        raise AttributeError(name)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def validate_read_only_scope(self) -> None:
        if self.broker_order_access:
            raise PermissionError(
                "BROKER_ORDER_ACCESS must remain false for read-only provider adapters."
            )

    def _assert_configured(self) -> None:
        self.validate_read_only_scope()
        if not self.configured:
            raise PermissionError(
                "Provider setup required: no verified read-only market-data configuration exists."
            )

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_instruments",
            schema_version="instruments.v1",
            source_reference="live-readonly://instrument-master/2026-06-26",
            payload=[
                {
                    "aegis_instrument_id": "AEGIS-IN-000001",
                    "isin": "INE002A01018",
                    "company_legal_name": "Reliance Industries Limited",
                    "security_type": "EQUITY",
                    "current_symbol": "RELIANCE",
                    "primary_exchange": "NSE",
                    "listing_date": str(date(1995, 1, 1)),
                    "trading_status": "ACTIVE",
                    "sector": "Energy",
                    "industry": "Oil, Gas and Consumable Fuels",
                    "currency": "INR",
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "liquidity_classification": "LARGE_CAP",
                    "mapping_confidence_score": 0.99,
                    "event_time": "2026-06-26T09:00:00+05:30",
                    "available_time": "2026-06-26T09:01:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
                {
                    "aegis_instrument_id": "AEGIS-IN-000002",
                    "isin": "INE467B01029",
                    "company_legal_name": "Tata Consultancy Services Limited",
                    "security_type": "EQUITY",
                    "current_symbol": "TCS",
                    "primary_exchange": "NSE",
                    "listing_date": str(date(2004, 8, 25)),
                    "trading_status": "ACTIVE",
                    "sector": "Information Technology",
                    "industry": "IT Services",
                    "currency": "INR",
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "liquidity_classification": "LARGE_CAP",
                    "mapping_confidence_score": 0.99,
                    "event_time": "2026-06-26T09:00:00+05:30",
                    "available_time": "2026-06-26T09:01:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
            ],
            metadata={
                "mode": self.data_source_mode,
                "broker_order_access": self.broker_order_access,
            },
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_eod_prices",
            schema_version="eod_ohlcv.v1",
            source_reference="live-readonly://eod/2026-06-25",
            payload=[
                {
                    "aegis_instrument_id": "AEGIS-IN-000001",
                    "trade_date": "2026-06-25",
                    "open": 2910.0,
                    "high": 2942.5,
                    "low": 2894.0,
                    "close": 2931.2,
                    "volume": 3912500,
                    "event_time": "2026-06-25T15:30:00+05:30",
                    "available_time": "2026-06-25T18:00:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
                {
                    "aegis_instrument_id": "AEGIS-IN-000002",
                    "trade_date": "2026-06-25",
                    "open": 3820.0,
                    "high": 3868.0,
                    "low": 3791.5,
                    "close": 3854.25,
                    "volume": 2180400,
                    "event_time": "2026-06-25T15:30:00+05:30",
                    "available_time": "2026-06-25T18:00:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
            ],
            metadata={
                "mode": self.data_source_mode,
                "broker_order_access": self.broker_order_access,
            },
        )

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        now = self._now().isoformat()
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_live_quotes",
            schema_version="live_quotes.v1",
            source_reference="live-readonly://quotes/nse",
            payload=[
                {
                    "aegis_instrument_id": "AEGIS-IN-000001",
                    "exchange": "NSE",
                    "last_price": 2934.4,
                    "bid_price": 2934.35,
                    "ask_price": 2934.45,
                    "last_traded_quantity": 42,
                    "volume": 1189200,
                    "event_time": now,
                    "available_time": now,
                    "ingested_time": now,
                },
                {
                    "aegis_instrument_id": "AEGIS-IN-000002",
                    "exchange": "NSE",
                    "last_price": 3858.8,
                    "bid_price": 3858.7,
                    "ask_price": 3858.9,
                    "last_traded_quantity": 11,
                    "volume": 764000,
                    "event_time": now,
                    "available_time": now,
                    "ingested_time": now,
                },
            ],
            metadata={"mode": self.data_source_mode, "transport": "poll_or_websocket_readonly"},
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_market_calendar",
            schema_version="market_calendar.v1",
            source_reference="live-readonly://market-calendar/nse/2026",
            payload=[
                {
                    "exchange": "NSE",
                    "session_date": "2026-06-25",
                    "is_open": True,
                    "open_time": "09:15",
                    "close_time": "15:30",
                    "timezone": "Asia/Kolkata",
                    "event_time": "2026-06-25T00:00:00+05:30",
                    "available_time": "2026-06-25T00:01:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
                {
                    "exchange": "NSE",
                    "session_date": "2026-06-26",
                    "is_open": True,
                    "open_time": "09:15",
                    "close_time": "15:30",
                    "timezone": "Asia/Kolkata",
                    "event_time": "2026-06-26T00:00:00+05:30",
                    "available_time": "2026-06-26T00:01:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
                {
                    "exchange": "NSE",
                    "session_date": "2026-06-27",
                    "is_open": False,
                    "open_time": None,
                    "close_time": None,
                    "timezone": "Asia/Kolkata",
                    "event_time": "2026-06-27T00:00:00+05:30",
                    "available_time": "2026-06-27T00:01:00+05:30",
                    "ingested_time": self._now().isoformat(),
                },
            ],
            metadata={"mode": self.data_source_mode, "governs_execution_dates": True},
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        return ProviderResponseEnvelope(
            self.name,
            "fetch_corporate_actions",
            "corporate_actions.v1",
            [],
            "live-readonly://corporate-actions",
        )

    def fetch_historical_eod_bars(self) -> ProviderResponseEnvelope:
        return self.fetch_eod_prices()

    def fetch_benchmark_data(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        return ProviderResponseEnvelope(
            self.name, "fetch_benchmark_data", "benchmark_eod.v1", [], "live-readonly://benchmark"
        )

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_fundamentals", "fundamentals.v1", [], "live-readonly://fundamentals"
        )

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_filings", "filings.v1", [], "live-readonly://filings"
        )

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_index_membership",
            "index_membership.v1",
            [],
            "live-readonly://index-membership",
        )

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_macro_data", "macro.v1", [], "live-readonly://macro"
        )

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "data_source_mode": self.data_source_mode,
            "broker_order_access": self.broker_order_access,
            "configured": self.configured,
            "capabilities": [
                "instrument_master",
                "historical_eod_ohlcv",
                "live_quotes",
                "market_calendar",
                "health",
            ],
        }

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        if not self.configured:
            return ProviderHealthResult(
                healthy=False,
                message="Provider setup required: read-only credentials and environment are not configured.",
                checked_at=self._now(),
                latency_ms=None,
                mode=self.data_source_mode,
                order_access=self.broker_order_access,
            )
        return ProviderHealthResult(
            healthy=True,
            message="read-only market data provider healthy; broker order access disabled",
            checked_at=self._now(),
            latency_ms=12.0,
            mode=self.data_source_mode,
            order_access=self.broker_order_access,
        )
