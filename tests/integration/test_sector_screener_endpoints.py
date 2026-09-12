from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis.data_ingestion.service import LocalObjectStore
from aegis_api.main import app
from fastapi.testclient import TestClient

CIPLA_ID = "AEGIS-IN-000056"  # real id from SECTOR_SCREENER_INSTRUMENTS
DIXON_ID = "AEGIS-IN-000081"
SEEDED_DAYS = 260


def _trading_dates(start: date, count: int) -> list[date]:
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _bar(instrument_id: str, trade_date: date, close: float) -> dict:
    return {
        "aegis_instrument_id": instrument_id,
        "trade_date": trade_date.isoformat(),
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1_000_000,
        "event_time": f"{trade_date.isoformat()}T00:00:00+05:30",
        "available_time": f"{trade_date.isoformat()}T18:00:00+00:00",
    }


def _seed_sector_screener_store(root: Path) -> None:
    dates = _trading_dates(date(2024, 1, 1), SEEDED_DAYS)
    payload = []
    for index, trade_date in enumerate(dates):
        payload.append(_bar(CIPLA_ID, trade_date, 1000.0 * (1.001**index)))
        payload.append(_bar(DIXON_ID, trade_date, 5000.0 * (1.002**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_sector_screener_instruments_is_honestly_empty_before_any_sync(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        app_main, "sector_screener_object_store", LocalObjectStore(tmp_path / "sector_screener_object_store")
    )
    response = client.get("/api/v1/sector-screener/instruments")
    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] is None
    assert body["sectors"]["Pharmaceuticals"] == []
    assert body["sectors"]["Solar & Renewable Energy"] == []
    assert body["sectors"]["Electronics Manufacturing"] == []
    assert "sync" in body["warnings"][0].lower()


def test_sector_screener_instruments_reflects_real_seeded_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store_root = tmp_path / "sector_screener_object_store"
    _seed_sector_screener_store(store_root)
    monkeypatch.setattr(app_main, "sector_screener_object_store", LocalObjectStore(store_root))

    response = client.get("/api/v1/sector-screener/instruments")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert body["raw_snapshot_hash"]

    pharma_symbols = {row["symbol"] for row in body["sectors"]["Pharmaceuticals"]}
    electronics_symbols = {row["symbol"] for row in body["sectors"]["Electronics Manufacturing"]}
    assert "CIPLA" in pharma_symbols
    assert "DIXON" in electronics_symbols
    # Every Pharmaceuticals/Solar/Electronics symbol should be present in
    # its group even without real bars -- honestly null, not omitted.
    assert len(body["sectors"]["Pharmaceuticals"]) == 20
    assert len(body["sectors"]["Solar & Renewable Energy"]) == 10
    assert len(body["sectors"]["Electronics Manufacturing"]) == 5

    cipla_row = next(r for r in body["sectors"]["Pharmaceuticals"] if r["symbol"] == "CIPLA")
    assert cipla_row["close"] is not None
    assert cipla_row["company_legal_name"] == "Cipla Limited"

    # A real symbol with no seeded bars in this test must show honestly
    # null fields, never a fabricated value.
    lupin_row = next(r for r in body["sectors"]["Pharmaceuticals"] if r["symbol"] == "LUPIN")
    assert lupin_row["close"] is None


def test_main_instruments_endpoint_is_unaffected_by_sector_screener(client: TestClient) -> None:
    """The whole point of the isolation work -- confirm the existing
    Instruments universe still returns exactly the original 50, not 85.
    Note: CIPLA, DRREDDY, and SUNPHARMA are real constituents of *both* the
    main Nifty 50 and the real NIFTY PHARMA index, so they legitimately
    appear in both universes under different aegis_instrument_ids -- not a
    bug, just two independent, unmerged real-data universes. DIXON
    (Electronics Manufacturing) has no such overlap, so it's the cleaner
    symbol to assert exclusivity with."""
    response = client.get("/api/v1/instruments")
    assert response.status_code == 200
    symbols = {row["current_symbol"] for row in response.json()}
    assert len(symbols) == 50
    assert "DIXON" not in symbols
    assert "CIPLA" in symbols  # real, pre-existing Nifty 50 member -- unaffected
