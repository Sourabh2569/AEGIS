from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from aegis_api.main import app


def test_paper_portfolio_queue_and_corporate_action_api_flow() -> None:
    client = TestClient(app)
    headers = {"X-Aegis-Role": "FOUNDER"}

    created = client.post(
        "/api/v1/paper-portfolios",
        json={"name": "API Paper", "description": "integration", "starting_capital": "100000"},
        headers=headers,
    )
    assert created.status_code == 200
    portfolio_id = created.json()["paper_portfolio_id"]
    assert "PAPER_TRADING_ONLY" in created.json()["labels"]

    activated = client.post(f"/api/v1/paper-portfolios/{portfolio_id}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    enqueued = client.post(
        "/api/v1/paper-session-jobs",
        json={
            "paper_portfolio_id": portfolio_id,
            "session_date": "2026-06-26",
            "reference_prices": {"AEGIS-IN-000001": "112"},
        },
    )
    assert enqueued.status_code == 200

    run = client.post("/api/v1/paper-session-jobs/run-next")
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETED"

    intents = client.get("/api/v1/paper-trade-intents").json()
    portfolio_intents = [item for item in intents if item["paper_portfolio_id"] == portfolio_id]
    assert portfolio_intents
    assert portfolio_intents[0]["eligible_execution_time"].startswith("2026-06-29T03:45:00")

    review = client.post(
        "/api/v1/paper-corporate-action-reviews",
        json={
            "paper_portfolio_id": portfolio_id,
            "instrument_id": "AEGIS-IN-000001",
            "action_type": "DEMERGER",
            "effective_date": "2026-06-30",
            "verification_status": "PENDING",
            "supported": False,
        },
        headers={"X-Aegis-Role": "DATA_STEWARD"},
    )
    assert review.status_code == 200
    assert review.json()["decision"] == "REJECTED_AND_PORTFOLIO_FROZEN"
