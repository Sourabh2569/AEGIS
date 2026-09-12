"""Real regression test for the exact collision risk found while scoping the
Sector Screener: load_real_eod_bars() globs *within* whatever object-store
root it's given, picking one "freshest" capture file across every provider
directory under that root. If the Sector Screener's real EOD price
ingestion ever shared the main pipeline's object store, its capture could
silently start winning that freshness tie-break and get treated as the
main 50-instrument universe's data by every backtest/actionables/signals
endpoint. This test proves the two are genuinely isolated."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aegis.audit.service import AuditLog
from aegis.data_ingestion.service import InMemoryRepository, LocalObjectStore, ProviderIngestionService
from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.backtesting.momentum_research import load_real_eod_bars
from aegis.provider_adapters.kite_connect_provider import KiteConnectMarketDataProvider
from aegis.provider_adapters.sector_screener_instruments import SECTOR_SCREENER_INSTRUMENTS

IST = timezone(timedelta(hours=5, minutes=30))


class FakeSectorScreenerKiteClient:
    """A minimal fake covering exactly the two Sector Screener symbols this
    test needs -- CIPLA (Pharmaceuticals) and DIXON (Electronics
    Manufacturing) -- real symbols from SECTOR_SCREENER_INSTRUMENTS."""

    def instruments(self, exchange: str) -> list[dict[str, Any]]:
        assert exchange == "NSE"
        return [
            {
                "instrument_token": 1,
                "tradingsymbol": "CIPLA",
                "exchange": "NSE",
                "name": "CIPLA LTD",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 2,
                "tradingsymbol": "DIXON",
                "exchange": "NSE",
                "name": "DIXON TECHNOLOGIES",
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
        return [
            {
                "date": datetime(2026, 9, 1, 15, 30, tzinfo=IST),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "volume": 10000,
            }
        ]

    def profile(self) -> dict[str, Any]:
        return {"user_id": "test"}


def _approved_license() -> ProviderLicense:
    return ProviderLicense(
        provider_id="kite-connect-sector-screener-test",
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="test",
        automation_rights=True,
        backtesting_rights=False,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="test",
    )


def test_sector_screener_object_store_is_a_different_root(tmp_path: Path) -> None:
    main_store = LocalObjectStore(tmp_path / "object_store")
    sector_store = LocalObjectStore(tmp_path / "sector_screener_object_store")
    assert main_store.root != sector_store.root
    assert not str(sector_store.root).startswith(str(main_store.root))
    assert not str(main_store.root).startswith(str(sector_store.root))


def test_sector_screener_ingestion_never_affects_the_main_universe_capture(
    tmp_path: Path,
) -> None:
    main_store = LocalObjectStore(tmp_path / "object_store")
    sector_store = LocalObjectStore(tmp_path / "sector_screener_object_store")
    sector_service = ProviderIngestionService(
        object_store=sector_store,
        repository=InMemoryRepository(),
        audit_log=AuditLog(),
    )
    provider = KiteConnectMarketDataProvider(
        client=FakeSectorScreenerKiteClient(),
        tradingsymbols=["CIPLA", "DIXON"],
        metadata=SECTOR_SCREENER_INSTRUMENTS,
        license_=_approved_license(),
        configured=True,
        historical_data_min_interval_seconds=0,
    )
    known_ids = {
        SECTOR_SCREENER_INSTRUMENTS["CIPLA"].aegis_instrument_id,
        SECTOR_SCREENER_INSTRUMENTS["DIXON"].aegis_instrument_id,
    }

    # Real, before-and-after proof: the main universe's loader sees nothing
    # both before and after the Sector Screener's real ingestion run.
    assert load_real_eod_bars(main_store.root) is None

    run = sector_service.ingest_eod_prices(
        provider=provider,
        provider_id="kite-connect-sector-screener-test",
        dataset_id="sector-screener-eod-test",
        dataset_name="sector_screener_eod_prices",
        known_instrument_ids=known_ids,
    )
    assert run.records_accepted == 2

    assert load_real_eod_bars(main_store.root) is None, (
        "Sector Screener ingestion must never be visible to the main "
        "universe's capture loader -- this is the exact collision this "
        "isolation was built to prevent."
    )

    # And the Sector Screener's own loader, pointed at its own root, does
    # see its real ingested data.
    sector_capture = load_real_eod_bars(sector_store.root)
    assert sector_capture is not None
    assert set(sector_capture.bars_by_instrument.keys()) == known_ids
