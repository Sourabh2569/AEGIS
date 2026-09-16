from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis_api.main import app
from fastapi.testclient import TestClient

FOUNDER = {"X-Aegis-Role": "FOUNDER"}
READ_ONLY = {"X-Aegis-Role": "READ_ONLY"}


@pytest.fixture
def client() -> TestClient:
    app_main.live_repo.portfolios.clear()
    app_main.live_repo.portfolio_configs.clear()
    app_main.live_repo.strategy_configs.clear()
    app_main.live_repo.intents.clear()
    app_main.live_repo.approvals.clear()
    app_main.live_repo.orders.clear()
    app_main.live_repo.fills.clear()
    app_main.live_repo.incidents.clear()
    app_main.live_repo.research_portfolios.clear()
    app_main.paper_repo.kill_switches.clear()
    return TestClient(app)


def _create_portfolio(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "Pilot",
        "description": "test pilot",
        "starting_capital": "400000",
        "pilot_capital_cap": "400000",
    }
    payload.update(overrides)
    response = client.post("/api/v1/live-portfolios", json=payload, headers=FOUNDER)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_is_rejected_for_an_unauthorized_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/live-portfolios",
        json={"name": "Pilot", "starting_capital": "400000"},
        headers=READ_ONLY,
    )
    assert response.status_code == 403


def test_create_and_activate_a_real_pilot_portfolio(client: TestClient) -> None:
    portfolio = _create_portfolio(client)
    assert portfolio["status"] == "SETUP_PENDING"
    assert portfolio["capital_tier"] == "PILOT"
    assert "REAL_CAPITAL_AT_RISK" in portfolio["labels"]

    live_portfolio_id = portfolio["live_portfolio_id"]
    activated = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/activate",
        json={"strategy_id": "DiversifiedRiskOverlayStrategyV2"},
        headers=FOUNDER,
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"


def test_a_realistic_multi_position_decision_cycle_creates_approvable_intents(
    client: TestClient,
) -> None:
    """Matches DiversifiedRiskOverlayStrategyV2's real shape: one cycle
    proposes many positions across the eligible universe, not just one."""
    portfolio = _create_portfolio(client, starting_capital="400000", pilot_capital_cap="400000")
    live_portfolio_id = portfolio["live_portfolio_id"]
    client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/activate",
        json={"strategy_id": "DiversifiedRiskOverlayStrategyV2"},
        headers=FOUNDER,
    )

    def fake_resolver(strategy_id: str, as_of):
        instrument_ids = [f"AEGIS-IN-{i:06d}" for i in range(1, 51)]
        weight = Decimal("1") / Decimal(50)
        return {inst: weight for inst in instrument_ids}, {}

    app_main.live_decision_cycle_service.strategy_target_resolver = fake_resolver
    reference_prices = {f"AEGIS-IN-{i:06d}": str(100 + i) for i in range(1, 51)}

    response = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/decision-cycle",
        json={"reference_prices": reference_prices, "session_date": "2026-09-16"},
        headers=FOUNDER,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_intent_count"] > 20  # a real, broad rebalance, not a toy single-order case
    assert all(intent["intent_status"] == "PENDING_APPROVAL" for intent in body["intents"])

    intents_response = client.get("/api/v1/live-order-intents")
    assert len(intents_response.json()) == body["created_intent_count"]

    batch = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/approve-pending-cycle", headers=FOUNDER
    )
    assert batch.status_code == 200
    assert batch.json()["approved_count"] == body["created_intent_count"]

    approved_intents = client.get("/api/v1/live-order-intents").json()
    assert all(intent["intent_status"] == "APPROVED" for intent in approved_intents)


def test_execute_approved_orders_is_blocked_when_it_would_exceed_the_pilot_capital_cap(
    client: TestClient,
) -> None:
    """Real position sizing (starting_capital=400000) proposes a real,
    sensibly-sized order -- but a deliberately tiny pilot_capital_cap
    (1000, far below what founder capital this position would actually
    need) must still BLOCK it at the preflight gate before any real broker
    call, never silently execute past the pilot's own real cap."""
    portfolio = _create_portfolio(client, starting_capital="400000", pilot_capital_cap="1000")
    live_portfolio_id = portfolio["live_portfolio_id"]
    client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/activate",
        json={"strategy_id": "DiversifiedRiskOverlayStrategyV2"},
        headers=FOUNDER,
    )

    def fake_resolver(strategy_id: str, as_of):
        return {"AEGIS-IN-000001": Decimal("0.5")}, {}

    app_main.live_decision_cycle_service.strategy_target_resolver = fake_resolver
    reference_prices = {"AEGIS-IN-000001": "100"}

    client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/decision-cycle",
        json={"reference_prices": reference_prices, "session_date": "2026-09-16"},
        headers=FOUNDER,
    )
    intents = client.get("/api/v1/live-order-intents").json()
    assert len(intents) == 1
    assert Decimal(intents[0]["proposed_quantity"]) > 0

    client.post(
        f"/api/v1/live-order-intents/{intents[0]['live_order_intent_id']}/approve", headers=FOUNDER
    )
    orders = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/execute-approved-orders",
        json={"reference_prices": reference_prices},
        headers=FOUNDER,
    ).json()
    assert len(orders) == 1
    assert orders[0]["status"] == "BLOCKED"
    assert "capital_cap" in orders[0]["rejection_reason_nullable"]


def test_graduate_is_rejected_below_the_clean_fill_threshold(client: TestClient) -> None:
    portfolio = _create_portfolio(client)
    live_portfolio_id = portfolio["live_portfolio_id"]

    response = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/graduate",
        json={"reason": "ready", "confirmed_new_capital_amount": "1000000"},
        headers=FOUNDER,
    )
    assert response.status_code == 422


def test_pilot_status_reports_real_clean_fill_progress(client: TestClient) -> None:
    portfolio = _create_portfolio(client)
    live_portfolio_id = portfolio["live_portfolio_id"]

    response = client.get(f"/api/v1/live-portfolios/{live_portfolio_id}/pilot-status")
    assert response.status_code == 200
    body = response.json()
    assert body["clean_fill_count"] == 0
    assert body["threshold_met"] is False
    assert body["graduation_threshold"] == 20


def test_kill_switch_activated_via_the_existing_endpoint_blocks_a_live_decision_cycle(
    client: TestClient,
) -> None:
    """Confirms the Phase 7 sharing decision actually works end-to-end: a
    kill switch activated through the existing paper endpoint is
    immediately visible to live trading's own risk sizing, with no separate
    live-kill-switch endpoint required. PositionSizingEngine.assess() (the
    shared, unmodified risk engine) checks kill switches during sizing
    itself, so a real GLOBAL switch blocks the position before an intent is
    even proposed -- an even earlier stop than the execution preflight gate."""
    portfolio = _create_portfolio(client)
    live_portfolio_id = portfolio["live_portfolio_id"]
    client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/activate",
        json={"strategy_id": "DiversifiedRiskOverlayStrategyV2"},
        headers=FOUNDER,
    )
    client.post(
        "/api/v1/kill-switches/GLOBAL/activate",
        json={"switch_type": "GLOBAL_TRADING_KILL_SWITCH", "reason": "test drill"},
        headers=FOUNDER,
    )

    def fake_resolver(strategy_id: str, as_of):
        return {"AEGIS-IN-000001": Decimal("0.5")}, {}

    app_main.live_decision_cycle_service.strategy_target_resolver = fake_resolver
    response = client.post(
        f"/api/v1/live-portfolios/{live_portfolio_id}/decision-cycle",
        json={"reference_prices": {"AEGIS-IN-000001": "100"}, "session_date": "2026-09-16"},
        headers=FOUNDER,
    )
    assert response.json()["created_intent_count"] == 0
    assert client.get("/api/v1/live-order-intents").json() == []


def test_live_readiness_evidence_includes_gate_8(client: TestClient) -> None:
    response = client.get("/api/v1/live-readiness/evidence")
    assert response.status_code == 200
    body = response.json()
    assert "gate_8_controlled_live_pilot" in body
    assert body["gate_8_controlled_live_pilot"]["graduation_threshold"] == 20
