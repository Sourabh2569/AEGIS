from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis_api.main import app
from fastapi.testclient import TestClient


def _stub_target_resolver(
    strategy_id: str, session_date: date
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Deterministic stand-in for the real strategy resolver, so this test
    stays independent of real on-disk Kite data (which won't exist in CI or
    a fresh clone -- see test_momentum_research_api.py for the same
    principle applied to the momentum-backtest endpoint)."""
    return {"AEGIS-IN-000001": Decimal("0.10")}, {"AEGIS-IN-000001": Decimal(100)}


def test_paper_session_job_uses_real_ingested_price_when_none_supplied() -> None:
    """Omitting reference_prices must pull the real last-ingested EOD close,
    never fall back to a fixture literal -- that fixture default is exactly
    the gap that made paper trading blind to real Kite data."""
    client = TestClient(app)
    headers = {"X-Aegis-Role": "FOUNDER"}

    ingested = client.post("/api/v1/ingestions/mock", headers=headers)
    assert ingested.status_code == 200

    created = client.post(
        "/api/v1/paper-portfolios",
        json={
            "name": "Real Price Paper",
            "description": "integration",
            "starting_capital": "100000",
        },
        headers=headers,
    )
    portfolio_id = created.json()["paper_portfolio_id"]
    client.post(f"/api/v1/paper-portfolios/{portfolio_id}/activate", headers=headers)

    enqueued = client.post(
        "/api/v1/paper-session-jobs",
        json={"paper_portfolio_id": portfolio_id, "session_date": "2026-06-26"},
    )
    assert enqueued.status_code == 200
    job_reference_prices = enqueued.json()["reference_prices"]
    assert job_reference_prices.get("AEGIS-IN-000001") == "2931.2"

    # The job queue is a shared, persistent, FIFO resource across tests in
    # this session -- drain what this test enqueued so it doesn't get
    # consumed by (and break) a later test's run-next call.
    drained = client.post("/api/v1/paper-session-jobs/run-next")
    assert drained.json()["status"] == "COMPLETED"


def test_paper_portfolio_queue_and_corporate_action_api_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_main.paper_orchestrator, "strategy_target_resolver", _stub_target_resolver
    )
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
