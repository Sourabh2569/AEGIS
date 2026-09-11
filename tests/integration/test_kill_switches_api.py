from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis_api.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    app_main.paper_repo.kill_switches.clear()
    app_main.paper_repo.intents.clear()
    return TestClient(app)


def test_activate_creates_the_real_requested_type_not_hardcoded_portfolio(
    client: TestClient,
) -> None:
    """Regression test: activate used to ignore switch_type entirely and
    always create a PORTFOLIO_KILL_SWITCH."""
    response = client.post(
        "/api/v1/kill-switches/GLOBAL/activate",
        json={"switch_type": "GLOBAL_TRADING_KILL_SWITCH", "reason": "test drill"},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["switch_type"] == "GLOBAL_TRADING_KILL_SWITCH"
    assert body["scope_id"] == "GLOBAL"
    assert body["is_active"] is True
    assert body["reason"] == "test drill"


def test_activate_requires_a_real_reason(client: TestClient) -> None:
    response = client.post(
        "/api/v1/kill-switches/GLOBAL/activate",
        json={"switch_type": "GLOBAL_TRADING_KILL_SWITCH", "reason": ""},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert response.status_code == 422


def test_activate_rejects_an_unknown_switch_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/kill-switches/GLOBAL/activate",
        json={"switch_type": "NOT_A_REAL_TYPE", "reason": "test"},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert response.status_code == 422


def test_activate_is_rejected_for_an_unauthorized_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/kill-switches/GLOBAL/activate",
        json={"switch_type": "GLOBAL_TRADING_KILL_SWITCH", "reason": "test"},
        headers={"X-Aegis-Role": "READ_ONLY"},
    )
    assert response.status_code == 403


def test_deactivate_actually_clears_is_active_and_requires_a_reason(client: TestClient) -> None:
    """Regression test: deactivate used to be a complete no-op that never
    touched any state."""
    activated = client.post(
        "/api/v1/kill-switches/some-portfolio/activate",
        json={"switch_type": "PORTFOLIO_KILL_SWITCH", "reason": "test drill"},
        headers={"X-Aegis-Role": "FOUNDER"},
    ).json()
    switch_id = activated["id"]

    missing_reason = client.post(
        f"/api/v1/kill-switches/{switch_id}/deactivate",
        json={"reason": ""},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert missing_reason.status_code == 422

    response = client.post(
        f"/api/v1/kill-switches/{switch_id}/deactivate",
        json={"reason": "reviewed, safe to resume"},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["reason"] == "reviewed, safe to resume"

    listed = client.get("/api/v1/kill-switches").json()
    assert next(row for row in listed if row["id"] == switch_id)["is_active"] is False


def test_deactivate_is_rejected_for_an_unauthorized_role(client: TestClient) -> None:
    activated = client.post(
        "/api/v1/kill-switches/some-portfolio/activate",
        json={"switch_type": "PORTFOLIO_KILL_SWITCH", "reason": "test"},
        headers={"X-Aegis-Role": "FOUNDER"},
    ).json()

    response = client.post(
        f"/api/v1/kill-switches/{activated['id']}/deactivate",
        json={"reason": "trying anyway"},
        headers={"X-Aegis-Role": "PAPER_TRADING_OPERATOR"},
    )
    assert response.status_code == 403


def test_deactivate_unknown_id_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/kill-switches/does-not-exist/deactivate",
        json={"reason": "test"},
        headers={"X-Aegis-Role": "FOUNDER"},
    )
    assert response.status_code == 404
