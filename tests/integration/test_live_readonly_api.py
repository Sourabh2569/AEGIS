from __future__ import annotations

from fastapi.testclient import TestClient

from aegis_api.main import app


def test_live_readonly_sync_blocks_when_provider_is_not_configured() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/data-source/live-readonly/sync", headers={"X-AEGIS-Role": "DATA_STEWARD"}
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["state"] == "NOT_CONFIGURED"
    assert payload["detail"]["label"] == "Provider setup required"

    mode = client.get("/api/v1/data-source/mode").json()
    assert "place_order" in mode["prohibited_operations"]
    assert mode["broker_order_access"] is False
    assert mode["market_data_provider_configured"] is False

    health = client.get("/api/v1/provider-health").json()
    quotes = client.get("/api/v1/live-quotes").json()
    truth = client.get("/api/v1/system/data-truth-summary").json()
    assert health and health[0]["order_access"] is False
    assert health[0]["healthy"] is False
    assert quotes == []
    assert truth["data_source"]["fixture_data_visible"] is True
    assert truth["safety"]["broker_order_access"] is False
