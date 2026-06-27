from __future__ import annotations

from fastapi.testclient import TestClient

from aegis_api.main import app


def test_data_activation_truth_endpoints_are_fail_closed() -> None:
    client = TestClient(app)

    truth = client.get("/api/v1/system/data-truth-summary").json()
    readiness = client.get("/api/v1/system/provider-readiness").json()
    blockers = client.get("/api/v1/system/data-blockers").json()
    quotes = client.get("/api/v1/live-quotes").json()

    assert truth["provider"]["state"] == "NOT_CONFIGURED"
    assert truth["data_source"]["actual_data_ingested"] is False
    assert truth["safety"]["live_execution_enabled"] is False
    assert truth["safety"]["paper_trading_use_live_data"] is False
    assert readiness["provider"]["label"] == "Provider setup required"
    assert any(blocker["code"] == "PROVIDER_NOT_CONFIGURED" for blocker in blockers)
    assert quotes == []


def test_required_provider_endpoints_do_not_expose_secrets() -> None:
    client = TestClient(app)
    providers = client.get("/api/v1/providers").json()
    assert providers
    provider_id = next(
        provider["id"]
        for provider in providers
        if provider["provider_type"] == "LIVE_READONLY_MARKET_DATA"
    )

    capabilities = client.get(f"/api/v1/providers/{provider_id}/capabilities").json()
    license_payload = client.get(f"/api/v1/providers/{provider_id}/license").json()

    serialized = str(capabilities) + str(license_payload)
    assert "CLIENT_SECRET" not in serialized
    assert "API_KEY" not in serialized
    assert capabilities["order_access_enabled"] is False
