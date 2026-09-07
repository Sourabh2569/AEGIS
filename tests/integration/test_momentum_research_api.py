from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from aegis.data_ingestion.service import LocalObjectStore
from aegis_api.main import app
from fastapi.testclient import TestClient


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
    dates = _trading_dates(date(2024, 1, 1), 260)
    payload = []
    for index, trade_date in enumerate(dates):
        # AEGIS-IN-000001 (RELIANCE) trends up; AEGIS-IN-000002 (TCS) trends down --
        # both real curated instrument ids, so sector lookup resolves correctly.
        payload.append(_bar("AEGIS-IN-000001", trade_date, 100.0 * (1.0015**index)))
        payload.append(_bar("AEGIS-IN-000002", trade_date, 100.0 * (0.9985**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")


def test_run_momentum_backtest_returns_409_when_no_real_data_captured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("aegis_api.main.object_store", LocalObjectStore(tmp_path / "empty-store"))
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["state"] == "NO_REAL_HISTORICAL_DATA_CAPTURED"


def test_run_momentum_backtest_requires_a_privileged_role(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr("aegis_api.main.object_store", LocalObjectStore(store_root))
    client = TestClient(app)

    response = client.post("/api/v1/research/momentum/run", headers={"X-Aegis-Role": "READ_ONLY"})

    assert response.status_code == 403


def test_run_momentum_backtest_produces_and_persists_both_scenarios(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr("aegis_api.main.object_store", LocalObjectStore(store_root))
    client = TestClient(app)

    run_response = client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["momentum"]["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
    assert body["momentum"]["universe_size"] == 2
    assert body["benchmark"]["strategy_name"] == "EqualWeightUniverseBenchmarkStrategyV0"

    reports_response = client.get("/api/v1/research/momentum/reports")
    assert reports_response.status_code == 200
    reports = reports_response.json()
    assert len(reports) >= 2
    scenario_names = {report["scenario"] for report in reports}
    assert "Real Nifty 50 Trend-Following Momentum" in scenario_names
    assert "Real Nifty 50 Equal-Weight Benchmark" in scenario_names
