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
    # into this file's held/HOLD/SELL assertions, and vice versa.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.strategy_configs.clear()
    app_main.paper_repo.nav.clear()
    app_main.paper_repo.paper_portfolios.clear()
    return TestClient(app)


def test_signals_with_no_portfolio_is_buy_or_no_position_only_with_a_warning(
    seeded_client: TestClient,
) -> None:
    response = seeded_client.get("/api/v1/signals")
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert body["paper_portfolio_id"] is None
    assert body["warnings"]  # must say so, not stay silent
    signals = {row["aegis_instrument_id"]: row for row in body["signals"]}
    assert signals[UPTREND_ID]["signal"] == "BUY"
    assert signals[DOWNTREND_ID]["signal"] == "NO_POSITION"
    # Every seeded instrument must appear, unlike /actionables which filters.
    assert set(signals) == {UPTREND_ID, DOWNTREND_ID}
    for row in signals.values():
        assert row["held"] is False
        assert row["held_quantity"] == "0"


def test_signals_with_no_real_data_captured_is_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(tmp_path / "empty"))
    client = TestClient(app)
    response = client.get("/api/v1/signals")
    assert response.status_code == 409
    assert response.json()["detail"]["state"] == "NO_REAL_HISTORICAL_DATA_CAPTURED"


def test_signals_report_real_hold_and_sell_states_with_a_portfolio(
    seeded_client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Signals Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    # Held and still eligible -- HOLD.
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[UPTREND_ID] = (
        Decimal(10)
    )
    # Held but no longer eligible -- SELL.
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[DOWNTREND_ID] = (
        Decimal(5)
    )

    response = seeded_client.get(
        "/api/v1/signals", params={"paper_portfolio_id": portfolio.paper_portfolio_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["warnings"] == []
    signals = {row["aegis_instrument_id"]: row for row in body["signals"]}
    assert signals[UPTREND_ID]["signal"] == "HOLD"
    assert signals[UPTREND_ID]["held"] is True
    assert signals[UPTREND_ID]["held_quantity"] == "10"
    assert signals[DOWNTREND_ID]["signal"] == "SELL"
    assert signals[DOWNTREND_ID]["held"] is True
    assert signals[DOWNTREND_ID]["held_quantity"] == "5"


def test_signals_matches_actionables_for_the_same_universe_and_portfolio(
    seeded_client: TestClient,
) -> None:
    """/signals and /actionables must agree -- they share the same
    _signal_rows_for_universe helper, so a BUY/SELL row's core numbers
    (close, momentum_60) must be identical between the two endpoints."""
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Cross-Check Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[DOWNTREND_ID] = (
        Decimal(5)
    )

    signals_body = seeded_client.get(
        "/api/v1/signals", params={"paper_portfolio_id": portfolio.paper_portfolio_id}
    ).json()
    actionables_body = seeded_client.get(
        "/api/v1/actionables", params={"paper_portfolio_id": portfolio.paper_portfolio_id}
    ).json()

    signals_by_id = {row["aegis_instrument_id"]: row for row in signals_body["signals"]}
    actionables_by_id = {row["aegis_instrument_id"]: row for row in actionables_body["actionables"]}

    for instrument_id, action_row in actionables_by_id.items():
        assert signals_by_id[instrument_id]["close"] == action_row["close"]
        assert signals_by_id[instrument_id]["momentum_60"] == action_row["momentum_60"]
        assert signals_by_id[instrument_id]["signal"] == action_row["action"]
