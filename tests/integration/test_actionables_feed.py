from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis.data_ingestion.service import LocalObjectStore
from aegis_api.main import app
from fastapi.testclient import TestClient

UPTREND_ID = "AEGIS-IN-000001"  # RELIANCE
DOWNTREND_ID = "AEGIS-IN-000002"  # TCS
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


def _seed_object_store(root: Path) -> None:
    dates = _trading_dates(date(2024, 1, 1), SEEDED_DAYS)
    payload = []
    for index, trade_date in enumerate(dates):
        payload.append(_bar(UPTREND_ID, trade_date, 100.0 * (1.0015**index)))
        payload.append(_bar(DOWNTREND_ID, trade_date, 100.0 * (0.9985**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def seeded_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(store_root))
    # paper_repo is a module-level singleton shared across the whole pytest
    # session -- clear it so other Cockpit test files' portfolios can't leak
    # into this file's held/SELL assertions, and vice versa.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.strategy_configs.clear()
    app_main.paper_repo.nav.clear()
    app_main.paper_repo.paper_portfolios.clear()
    return TestClient(app)


def test_actionables_with_no_portfolio_is_buy_only_with_a_warning(
    seeded_client: TestClient,
) -> None:
    response = seeded_client.get("/api/v1/actionables")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert body["paper_portfolio_id"] is None
    assert body["warnings"]  # must say so, not stay silent
    actions = {row["aegis_instrument_id"]: row for row in body["actionables"]}
    assert actions[UPTREND_ID]["action"] == "BUY"
    assert DOWNTREND_ID not in actions  # ineligible and not held -- NO_POSITION, not actionable


def test_actionables_with_no_real_data_captured_is_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(tmp_path / "empty"))
    client = TestClient(app)
    response = client.get("/api/v1/actionables")
    assert response.status_code == 409
    assert response.json()["detail"]["state"] == "NO_REAL_HISTORICAL_DATA_CAPTURED"


def test_actionables_detects_a_real_sell_when_a_held_position_is_no_longer_eligible(
    seeded_client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Actionables Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[DOWNTREND_ID] = (
        Decimal(5)
    )

    response = seeded_client.get(
        "/api/v1/actionables", params={"paper_portfolio_id": portfolio.paper_portfolio_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["warnings"] == []
    actions = {row["aegis_instrument_id"]: row for row in body["actionables"]}
    assert actions[DOWNTREND_ID]["action"] == "SELL"
    assert actions[DOWNTREND_ID]["held_quantity"] == "5"
    assert actions[UPTREND_ID]["action"] == "BUY"

    # SELL rows must sort before BUY rows.
    action_order = [row["action"] for row in body["actionables"]]
    assert action_order.index("SELL") < action_order.index("BUY")


def test_actionables_excludes_hold_and_no_position_steady_states(
    seeded_client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Actionables Steady State Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    # Held and still eligible -- HOLD, not actionable.
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[UPTREND_ID] = (
        Decimal(10)
    )

    response = seeded_client.get(
        "/api/v1/actionables", params={"paper_portfolio_id": portfolio.paper_portfolio_id}
    )
    assert response.status_code == 200
    ids = {row["aegis_instrument_id"] for row in response.json()["actionables"]}
    assert UPTREND_ID not in ids  # HOLD
    assert DOWNTREND_ID not in ids  # NO_POSITION
