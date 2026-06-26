from __future__ import annotations

from fastapi.testclient import TestClient

from aegis_api.main import app


def test_live_readonly_sync_surfaces_data_health() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/data-source/live-readonly/sync", headers={"X-AEGIS-Role": "DATA_STEWARD"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "LIVE_READONLY"
    assert payload["live_execution_enabled"] is False
    assert payload["broker_order_access"] is False
    assert payload["health"]["order_access"] is False
    assert payload["runs"]["instrument_master"]["records_accepted"] >= 1
    assert payload["runs"]["historical_eod_ohlcv"]["records_accepted"] >= 1
    assert payload["runs"]["live_quotes"]["records_accepted"] >= 1
    assert payload["runs"]["market_calendar"]["records_accepted"] >= 1

    mode = client.get("/api/v1/data-source/mode").json()
    assert "place_order" in mode["prohibited_operations"]
    assert mode["broker_order_access"] is False

    health = client.get("/api/v1/provider-health").json()
    freshness = client.get("/api/v1/data-freshness").json()
    quotes = client.get("/api/v1/live-quotes").json()
    calendar = client.get("/api/v1/market-calendar").json()
    assert health and health[0]["order_access"] is False
    assert freshness and freshness[0]["status"] in {"FRESH", "STALE"}
    assert quotes
    assert calendar
