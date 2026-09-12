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
    return TestClient(app)


def test_fundamentals_endpoint_is_honest_when_nothing_ingested_yet(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "Not available -- no verified fundamentals provider yet"


def test_fundamentals_endpoint_rejects_unknown_symbol(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/NOT-A-REAL-SYMBOL/fundamentals")
    assert response.status_code == 404


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
