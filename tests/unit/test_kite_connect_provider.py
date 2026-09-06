from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aegis.audit.service import AuditLog
from aegis.data_ingestion.service import (
    InMemoryRepository,
    LocalObjectStore,
    ProviderIngestionService,
)
from aegis.domain.models import IngestionStatus, ProviderLicense, ProviderLicenseStatus
from aegis.instrument_master.service import InstrumentMasterService
from aegis.provider_adapters.kite_connect_provider import (
    MAX_DAY_INTERVAL_DAYS_PER_REQUEST,
    KiteConnectMarketDataProvider,
)

IST = timezone(timedelta(hours=5, minutes=30))


class FakeKiteClient:
    """Stands in for kiteconnect.KiteConnect so tests never touch the real API."""

    def __init__(self) -> None:
        self.historical_data_calls: list[tuple[Any, Any, Any, str]] = []

    def instruments(self, exchange: str) -> list[dict[str, Any]]:
        assert exchange == "NSE"
        return [
            {
                "instrument_token": 738561,
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "name": "RELIANCE INDUSTRIES LTD",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 2953217,
                "tradingsymbol": "TCS",
                "exchange": "NSE",
                "name": "TATA CONSULTANCY SERV LT",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 256265,
                "tradingsymbol": "NIFTY 50",
                "exchange": "NSE",
                "name": "NIFTY 50",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 999999,
                "tradingsymbol": "UNMAPPED_CO",
                "exchange": "NSE",
                "name": "SOME OTHER COMPANY",
                "lot_size": 1,
                "tick_size": 0.05,
            },
        ]

    def historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]:
        self.historical_data_calls.append((instrument_token, from_date, to_date, interval))
        return [
            {
                "date": datetime(2024, 1, 2, 15, 30, tzinfo=IST),
                "open": 2900.0,
                "high": 2950.0,
                "low": 2890.0,
                "close": 2930.0,
                "volume": 1_000_000,
            },
            {
                "date": datetime(2024, 1, 3, 15, 30, tzinfo=IST),
                "open": 2930.0,
                "high": 2960.0,
                "low": 2905.0,
                "close": 2945.0,
                "volume": 1_100_000,
            },
        ]

    def quote(self, instruments: list[str]) -> dict[str, Any]:
        return {
            key: {
                "last_price": 2934.4,
                "last_quantity": 42,
                "volume": 1_189_200,
                "depth": {"buy": [{"price": 2934.35}], "sell": [{"price": 2934.45}]},
            }
            for key in instruments
        }

    def profile(self) -> dict[str, Any]:
        return {"user_id": "AB1234"}


def test_fails_closed_when_unconfigured() -> None:
    provider = KiteConnectMarketDataProvider()
    assert provider.configured is False
    health = provider.get_health_status()
    assert health.healthy is False
    assert "Provider setup required" in health.message
    for forbidden in (
        "place_order",
        "submit_order",
        "cancel_order",
        "modify_order",
        "fetch_holdings",
        "mutate_holdings",
        "margins",
        "orders",
        "positions",
    ):
        assert not hasattr(provider, forbidden)


def test_dataset_origin_is_actual_provider_data_only_when_configured() -> None:
    unconfigured = KiteConnectMarketDataProvider()
    assert unconfigured.dataset_origin == "FIXTURE_DATA"

    configured = KiteConnectMarketDataProvider(client=FakeKiteClient(), configured=True)
    assert configured.dataset_origin == "ACTUAL_PROVIDER_DATA"


def test_health_check_uses_profile_and_reports_latency() -> None:
    provider = KiteConnectMarketDataProvider(client=FakeKiteClient(), configured=True)
    health = provider.get_health_status()
    assert health.healthy is True
    assert health.order_access is False
    assert health.latency_ms is not None


def test_fetch_instruments_maps_curated_metadata_and_flags_unmapped() -> None:
    provider = KiteConnectMarketDataProvider(
        client=FakeKiteClient(),
        tradingsymbols=["RELIANCE", "TCS", "UNMAPPED_CO"],
        configured=True,
    )
    envelope = provider.fetch_instruments()
    symbols = {row["current_symbol"] for row in envelope.payload}
    assert symbols == {"RELIANCE", "TCS"}
    reliance = next(row for row in envelope.payload if row["current_symbol"] == "RELIANCE")
    assert reliance["isin"] == "INE002A01018"
    assert reliance["aegis_instrument_id"] == "AEGIS-IN-000001"
    assert envelope.metadata["unmapped_symbols"] == ["UNMAPPED_CO"]


def test_fetch_historical_eod_bars_reshapes_candles() -> None:
    provider = KiteConnectMarketDataProvider(
        client=FakeKiteClient(), tradingsymbols=["RELIANCE"], lookback_days=30, configured=True
    )
    envelope = provider.fetch_historical_eod_bars()
    assert envelope.schema_version == "eod_ohlcv.v1"
    assert len(envelope.payload) == 2
    bar = envelope.payload[0]
    assert bar["aegis_instrument_id"] == "AEGIS-IN-000001"
    assert bar["trade_date"] == "2024-01-02"
    assert bar["open"] == 2900.0
    assert bar["volume"] == 1_000_000


def test_fetch_historical_eod_bars_chunks_long_lookback_windows() -> None:
    client = FakeKiteClient()
    lookback_days = MAX_DAY_INTERVAL_DAYS_PER_REQUEST + 500
    provider = KiteConnectMarketDataProvider(
        client=client, tradingsymbols=["RELIANCE"], lookback_days=lookback_days, configured=True
    )
    provider.fetch_historical_eod_bars()
    assert len(client.historical_data_calls) == 2
    first_call = client.historical_data_calls[0]
    span_days = (first_call[2] - first_call[1]).days
    assert span_days <= MAX_DAY_INTERVAL_DAYS_PER_REQUEST


def test_market_calendar_and_corporate_actions_are_empty_not_fabricated() -> None:
    provider = KiteConnectMarketDataProvider(client=FakeKiteClient(), configured=True)
    calendar = provider.fetch_market_calendar()
    actions = provider.fetch_corporate_actions()
    assert calendar.payload == []
    assert actions.payload == []
    assert "note" in calendar.metadata
    assert "note" in actions.metadata


def test_fetch_benchmark_data_resolves_nifty_50() -> None:
    provider = KiteConnectMarketDataProvider(
        client=FakeKiteClient(), tradingsymbols=["RELIANCE"], lookback_days=30, configured=True
    )
    envelope = provider.fetch_benchmark_data()
    assert len(envelope.payload) == 2
    assert envelope.payload[0]["benchmark_symbol"] == "NIFTY 50"


def test_kite_provider_satisfies_generic_ingestion_pipeline(tmp_path: Path) -> None:
    audit_log = AuditLog()
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path),
        repository=repo,
        audit_log=audit_log,
    )
    instrument_master = InstrumentMasterService()
    approved_license = ProviderLicense(
        provider_id="kite-connect",
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="read-only historical and EOD market data ingestion",
        automation_rights=True,
        backtesting_rights=True,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="provider-contract-controlled",
    )
    provider = KiteConnectMarketDataProvider(
        client=FakeKiteClient(),
        tradingsymbols=["RELIANCE", "TCS"],
        lookback_days=30,
        license_=approved_license,
        configured=True,
    )

    health = service.check_provider_health(provider=provider, provider_id="provider-kite-connect")
    instruments = service.sync_instrument_master(
        provider=provider, provider_id="provider-kite-connect", instrument_master=instrument_master
    )
    eod = service.ingest_eod_prices(
        provider=provider,
        provider_id="provider-kite-connect",
        dataset_id="dataset-eod",
        dataset_name="eod_prices",
        known_instrument_ids=instrument_master.known_aegis_ids(),
    )

    assert health["mode"] == "LIVE_READONLY"
    assert health["order_access"] is False
    assert instruments.status == IngestionStatus.COMPLETED
    assert eod.status == IngestionStatus.COMPLETED
    assert len(instrument_master.instruments) == 2
    eod_version_id = eod.validation_summary["dataset_version_id"]
    assert repo.dataset_origins[eod_version_id] == "ACTUAL_PROVIDER_DATA"
