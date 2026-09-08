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


def _seed_object_store(root: Path) -> list[date]:
    dates = _trading_dates(date(2024, 1, 1), SEEDED_DAYS)
    payload = []
    for index, trade_date in enumerate(dates):
        payload.append(_bar(UPTREND_ID, trade_date, 100.0 * (1.0015**index)))
        payload.append(_bar(DOWNTREND_ID, trade_date, 100.0 * (0.9985**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")
    return dates


@pytest.fixture
def seeded_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[TestClient, list[date]]:
    store_root = tmp_path / "object_store"
    dates = _seed_object_store(store_root)
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(store_root))
    return TestClient(app), dates


def test_ohlcv_returns_real_bars_in_requested_range(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, dates = seeded_client
    response = client.get(
        "/api/v1/instruments/RELIANCE/ohlcv",
        params={"from": dates[0].isoformat(), "to": dates[10].isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "RELIANCE"
    assert body["aegis_instrument_id"] == UPTREND_ID
    assert body["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert len(body["bars"]) == 11
    assert body["bars"][0]["date"] == dates[0].isoformat()
    assert body["bars"][-1]["date"] == dates[10].isoformat()


def test_ohlcv_unknown_symbol_is_404(seeded_client: tuple[TestClient, list[date]]) -> None:
    client, _ = seeded_client
    response = client.get("/api/v1/instruments/NOT-A-REAL-SYMBOL/ohlcv")
    assert response.status_code == 404


def test_ohlcv_with_no_real_data_captured_is_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(tmp_path / "empty"))
    client = TestClient(app)
    response = client.get("/api/v1/instruments/RELIANCE/ohlcv")
    assert response.status_code == 409
    assert response.json()["detail"]["state"] == "NO_REAL_HISTORICAL_DATA_CAPTURED"


def test_indicators_use_only_data_up_to_each_date_no_lookahead(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, dates = seeded_client
    response = client.get(
        "/api/v1/instruments/RELIANCE/indicators",
        params={"from": dates[200].isoformat(), "to": dates[250].isoformat()},
    )
    assert response.status_code == 200
    points = {p["date"]: p for p in response.json()["points"]}
    early = points[dates[210].isoformat()]
    later = points[dates[240].isoformat()]
    assert early["close"] is not None
    assert early["sma_50"] is not None
    assert early["close"] != later["close"]
    assert early["sma_50"] != later["sma_50"]


def test_signal_is_buy_for_real_uptrend_with_no_portfolio_context(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, _ = seeded_client
    response = client.get("/api/v1/instruments/RELIANCE/signal")
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True
    assert body["held"] is False
    assert body["signal"] == "BUY"
    assert body["inputs"]["momentum_60"] is not None
    assert Decimal(body["inputs"]["momentum_60"]) > 0
    assert body["warnings"]  # no portfolio supplied -- must say so, not stay silent


def test_signal_is_no_position_for_real_downtrend(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, _ = seeded_client
    response = client.get("/api/v1/instruments/TCS/signal")
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is False
    assert body["signal"] == "NO_POSITION"


def test_signal_is_hold_when_eligible_and_a_real_position_is_held(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, _ = seeded_client
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Signal Test", description="d", starting_capital=Decimal(100000), created_by="FOUNDER"
    )
    app_main.paper_repo.paper_portfolios[portfolio.paper_portfolio_id].positions[UPTREND_ID] = (
        Decimal(10)
    )

    response = client.get(
        "/api/v1/instruments/RELIANCE/signal",
        params={"paper_portfolio_id": portfolio.paper_portfolio_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["held"] is True
    assert body["held_quantity"] == "10"
    assert body["signal"] == "HOLD"
    assert body["warnings"] == []


def test_rule_events_detects_the_real_eligibility_transition(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, dates = seeded_client
    response = client.get(
        "/api/v1/instruments/RELIANCE/rule-events",
        params={"from": dates[195].isoformat(), "to": dates[220].isoformat()},
    )
    assert response.status_code == 200
    events = response.json()["events"]
    assert any(event["type"] == "ELIGIBILITY_START" for event in events)


def test_rule_events_are_empty_for_a_real_downtrend(
    seeded_client: tuple[TestClient, list[date]],
) -> None:
    client, dates = seeded_client
    response = client.get(
        "/api/v1/instruments/TCS/rule-events",
        params={"from": dates[200].isoformat(), "to": dates[259].isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["events"] == []
