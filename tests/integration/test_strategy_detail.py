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

INSTRUMENT_A = "AEGIS-IN-000001"  # RELIANCE
INSTRUMENT_B = "AEGIS-IN-000002"  # TCS
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
        payload.append(_bar(INSTRUMENT_A, trade_date, 100.0 * (1.0015**index)))
        payload.append(_bar(INSTRUMENT_B, trade_date, 100.0 * (0.9985**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def seeded_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(store_root))
    monkeypatch.setattr(app_main, "real_momentum_reports", [])
    # paper_repo is a module-level singleton shared across the whole pytest
    # session -- clear it so portfolios/configs created by one test (here or
    # in test_strategy_leaderboard.py) can't leak into another test's list.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.strategy_configs.clear()
    app_main.paper_repo.nav.clear()
    return TestClient(app)


def test_detail_is_404_for_unknown_strategy_id(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/strategies/NotARealStrategy/detail")
    assert response.status_code == 404


def test_detail_has_rules_for_all_three_strategies_before_any_backtest(
    seeded_client: TestClient,
) -> None:
    for strategy_id in (
        "TrendFollowingBaselineStrategyV0",
        "EqualWeightUniverseBenchmarkStrategyV0",
        "BuyAndHoldBenchmarkStrategyV0",
    ):
        response = seeded_client.get(f"/api/v1/strategies/{strategy_id}/detail")
        assert response.status_code == 200
        body = response.json()
        assert body["strategy_id"] == strategy_id
        assert body["backtest_status"] == "NOT_RUN_YET"
        assert body["backtest"] is None
        assert body["benchmark_equity_curve"] is None
        assert set(body["rules"].keys()) == {
            "eligibility",
            "selection",
            "sizing",
            "stop",
            "max_positions",
        }
        assert isinstance(body["rules"]["max_positions"], int)
        assert body["rules"]["max_positions"] > 0
        assert body["live_portfolios"] == []


def test_detail_max_positions_reflects_each_strategys_real_construction(
    seeded_client: TestClient,
) -> None:
    # TrendFollowing/EqualWeight share the platform's real risk-profile cap;
    # BuyAndHold's own construction always holds exactly one instrument.
    trend_response = seeded_client.get("/api/v1/strategies/TrendFollowingBaselineStrategyV0/detail")
    equal_weight_response = seeded_client.get(
        "/api/v1/strategies/EqualWeightUniverseBenchmarkStrategyV0/detail"
    )
    buy_and_hold_response = seeded_client.get(
        "/api/v1/strategies/BuyAndHoldBenchmarkStrategyV0/detail"
    )
    trend_max = trend_response.json()["rules"]["max_positions"]
    assert trend_max == equal_weight_response.json()["rules"]["max_positions"]
    assert trend_max > 1
    assert buy_and_hold_response.json()["rules"]["max_positions"] == 1


def test_detail_includes_real_equity_curve_and_benchmark_overlay(
    seeded_client: TestClient,
) -> None:
    run_response = seeded_client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert run_response.status_code == 200

    response = seeded_client.get("/api/v1/strategies/TrendFollowingBaselineStrategyV0/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["backtest_status"] == "AVAILABLE"
    assert len(body["backtest"]["equity_curve"]) > 0
    assert body["backtest"]["equity_curve"][0].keys() == {"date", "nav"}
    assert body["benchmark_equity_curve"] is not None
    assert len(body["benchmark_equity_curve"]) > 0

    # The benchmark itself must not be compared against a copy of its own line.
    benchmark_response = seeded_client.get(
        "/api/v1/strategies/EqualWeightUniverseBenchmarkStrategyV0/detail"
    )
    assert benchmark_response.json()["benchmark_equity_curve"] is None


def test_detail_itemizes_live_portfolios_including_one_that_never_ran(
    seeded_client: TestClient,
) -> None:
    ran_portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Detail Test Ran",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    app_main.paper_orchestrator.create_strategy_config(
        ran_portfolio.paper_portfolio_id, strategy_id="TrendFollowingBaselineStrategyV0"
    )
    never_ran_portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Detail Test Never Ran",
        description="unit test",
        starting_capital=Decimal(50000),
        created_by="FOUNDER",
    )
    app_main.paper_orchestrator.create_strategy_config(
        never_ran_portfolio.paper_portfolio_id, strategy_id="TrendFollowingBaselineStrategyV0"
    )

    from datetime import UTC, datetime

    from aegis.paper_trading.domain import PaperNavSnapshot

    app_main.paper_repo.nav[ran_portfolio.paper_portfolio_id] = [
        PaperNavSnapshot(
            paper_portfolio_id=ran_portfolio.paper_portfolio_id,
            valuation_time=datetime(2026, 1, 2, tzinfo=UTC),
            available_cash=Decimal(0),
            unsettled_receivables=Decimal(0),
            market_value=Decimal(110000),
            nav=Decimal(110000),
            high_water_mark=Decimal(110000),
            drawdown=Decimal(0),
            reconciliation_status="RECONCILED",
        )
    ]

    response = seeded_client.get("/api/v1/strategies/TrendFollowingBaselineStrategyV0/detail")
    assert response.status_code == 200
    by_id = {p["paper_portfolio_id"]: p for p in response.json()["live_portfolios"]}
    assert by_id.keys() == {
        ran_portfolio.paper_portfolio_id,
        never_ran_portfolio.paper_portfolio_id,
    }
    assert by_id[ran_portfolio.paper_portfolio_id]["run_status"] == "HAS_RUN"
    assert Decimal(by_id[ran_portfolio.paper_portfolio_id]["latest_nav"]) == Decimal(110000)
    assert by_id[never_ran_portfolio.paper_portfolio_id]["run_status"] == "HAS_NOT_RUN_YET"
    assert by_id[never_ran_portfolio.paper_portfolio_id]["latest_nav"] is None
