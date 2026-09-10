from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis.backtesting.momentum_report_store import SqliteMomentumReportStore
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
def isolated_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(store_root))
    monkeypatch.setattr(app_main, "real_momentum_reports", [])
    # Isolate the durable store too -- not just the in-memory list -- so
    # this test's assertions about "what got persisted" aren't order-
    # dependent on other test files sharing the session's AEGIS_WORK_DIR.
    monkeypatch.setattr(
        app_main, "momentum_report_store", SqliteMomentumReportStore(tmp_path / "reports.sqlite")
    )
    return TestClient(app)


def test_running_a_real_backtest_persists_reports_to_the_durable_store(
    isolated_client: TestClient,
) -> None:
    response = isolated_client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert response.status_code == 200

    persisted = app_main.momentum_report_store.load_all()
    assert {report["strategy_name"] for report in persisted} == {
        "TrendFollowingBaselineStrategyV0",
        "EqualWeightUniverseBenchmarkStrategyV0",
        "BuyAndHoldBenchmarkStrategyV0",
    }


def test_reports_persisted_by_the_api_survive_a_fresh_store_instance(
    isolated_client: TestClient,
) -> None:
    """The actual point of this whole change: a brand-new
    SqliteMomentumReportStore pointed at the same file -- standing in for
    the API process restarting -- must see what a real backtest run wrote,
    not just the live in-memory list."""
    isolated_client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    db_path = app_main.momentum_report_store.db_path

    reloaded = SqliteMomentumReportStore(db_path)
    assert len(reloaded.load_all()) == 3
