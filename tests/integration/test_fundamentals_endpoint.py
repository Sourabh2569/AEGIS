from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis_api.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    app_main.repo.latest_fundamentals.clear()
    app_main.repo.fundamentals_history.clear()
    return TestClient(app)


def test_fundamentals_endpoint_is_honest_when_nothing_ingested_yet(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "Not available -- no verified fundamentals provider yet"


def test_fundamentals_endpoint_is_honest_for_a_symbol_outside_the_main_curated_universe(
    client: TestClient,
) -> None:
    """No _resolve_symbol gate here on purpose: fundamentals storage is
    keyed by plain symbol string, not aegis_instrument_id, so it works for
    real companies never in the main 50-instrument universe (e.g. Sector
    Screener companies like DIXON). An unrecognized symbol can't be told
    apart from a recognized one with nothing uploaded yet -- both honestly
    report unavailable rather than a 404 implying the symbol itself is
    invalid, which this endpoint has no way to actually verify."""
    response = client.get("/api/v1/instruments/NOT-A-REAL-SYMBOL/fundamentals")
    assert response.status_code == 200
    assert response.json()["available"] is False


def test_fundamentals_endpoint_reflects_a_real_ingested_record(client: TestClient) -> None:
    # Simulates what a real ProviderIngestionService.ingest_fundamentals()
    # run would have written -- the endpoint itself never ingests, it only
    # reads back real state.
    app_main.repo.latest_fundamentals["RELIANCE"] = {
        "symbol": "RELIANCE",
        "period_from": "2024-10-01",
        "period_to": "2024-12-31",
        "filing_date": "16-Jan-2025 20:20",
        "revenue_from_operations": "1282600000000.00",
        "profit_before_tax": "108680000000.00",
        "profit_for_period": "87210000000.00",
        "source_xbrl_url": "https://nsearchives.nseindia.com/corporate/xbrl/example.xml",
    }
    response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert body["revenue_from_operations"] == "1282600000000.00"
    assert body["ttm_eps"] is None
    assert body["real_quarters_on_file"] == 0


def test_fundamentals_endpoint_reflects_real_ttm_eps_once_four_quarters_are_on_file(
    client: TestClient,
) -> None:
    quarters = [
        ("2024-01-01", "2024-03-31", "5.00"),
        ("2024-04-01", "2024-06-30", "6.00"),
        ("2024-07-01", "2024-09-30", "7.00"),
        ("2024-10-01", "2024-12-31", "8.00"),
    ]
    for period_from, period_to, basic_eps in quarters:
        record = {
            "symbol": "RELIANCE",
            "period_from": period_from,
            "period_to": period_to,
            "basic_eps": basic_eps,
        }
        app_main.repo.latest_fundamentals["RELIANCE"] = record
        app_main.repo.fundamentals_history.setdefault("RELIANCE", {})[period_to] = record

    response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["real_quarters_on_file"] == 4
    assert body["ttm_eps"] == "26.00"
    assert body["ttm_eps_quarters"] == ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]


def test_fundamentals_endpoint_works_for_a_real_sector_screener_only_company(
    client: TestClient,
) -> None:
    """DIXON is real and in SECTOR_SCREENER_INSTRUMENTS but never in the
    main 50-instrument CURATED_INSTRUMENT_METADATA -- this is the actual
    point of dropping the _resolve_symbol gate: the Sector Screener's own
    detail page needs this endpoint to work for its companies too."""
    app_main.repo.latest_fundamentals["DIXON"] = {
        "symbol": "DIXON",
        "period_from": "2024-10-01",
        "period_to": "2024-12-31",
        "revenue_from_operations": "50000000000.00",
    }
    response = client.get("/api/v1/instruments/DIXON/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["revenue_from_operations"] == "50000000000.00"
