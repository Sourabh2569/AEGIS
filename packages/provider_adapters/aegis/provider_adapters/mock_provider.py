from __future__ import annotations

from datetime import date

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope


class MockMarketDataProvider:
    name = "mock_market_data"

    def __init__(self, license_: ProviderLicense | None = None) -> None:
        self._license = license_ or ProviderLicense(
            provider_id="mock-provider",
            license_status=ProviderLicenseStatus.APPROVED,
            permitted_use="local development and tests",
            automation_rights=True,
            backtesting_rights=True,
            model_training_rights=False,
            dashboard_display_rights=True,
            data_retention_period="indefinite-local",
        )

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_instruments",
            schema_version="instruments.v1",
            source_reference="mock://instruments",
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
                }
            ],
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_eod_prices",
            schema_version="eod_ohlcv.v1",
            source_reference="mock://eod_prices/2026-06-25",
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
                    "ingested_time": "2026-06-25T18:05:00+05:30",
                }
            ],
        )

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_live_quotes",
            schema_version="live_quotes.v1",
            source_reference="mock://live_quotes",
            payload=[],
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_market_calendar",
            schema_version="market_calendar.v1",
            source_reference="mock://market_calendar",
            payload=[],
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_corporate_actions",
            schema_version="corporate_actions.v1",
            source_reference="mock://corporate_actions",
            payload=[],
        )

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(self.name, "fetch_fundamentals", "fundamentals.v1", [], "mock://fundamentals")

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(self.name, "fetch_filings", "filings.v1", [], "mock://filings")

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(self.name, "fetch_index_membership", "index_membership.v1", [], "mock://index")

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(self.name, "fetch_macro_data", "macro.v1", [], "mock://macro")

    def get_source_metadata(self) -> dict[str, str]:
        return {"provider": self.name, "deterministic": "true"}

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        return ProviderHealthResult(True, "mock provider healthy")
