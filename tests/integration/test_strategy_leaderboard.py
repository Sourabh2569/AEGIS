from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis.data_ingestion.service import LocalObjectStore
from aegis.paper_trading.domain import PaperNavSnapshot
from aegis_api.main import app
from fastapi.testclient import TestClient

INSTRUMENT_A = "AEGIS-IN-000001"  # RELIANCE
INSTRUMENT_B = "AEGIS-IN-000002"  # TCS
SEEDED_DAYS = 260
ALL_STRATEGY_IDS = {
    "TrendFollowingBaselineStrategyV0",
    "EqualWeightUniverseBenchmarkStrategyV0",
    "BuyAndHoldBenchmarkStrategyV0",
}


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
    # in test_strategy_detail.py) can't leak into another test's live rollup.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.strategy_configs.clear()
    app_main.paper_repo.nav.clear()
    return TestClient(app)


def test_leaderboard_is_all_not_run_yet_before_any_backtest(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/strategies/leaderboard")
    assert response.status_code == 200
    rows = response.json()
    assert {row["strategy_id"] for row in rows} == ALL_STRATEGY_IDS
    assert all(row["backtest"] is None for row in rows)
    assert all(row["backtest_status"] == "NOT_RUN_YET" for row in rows)
    assert all(row["live"] is None for row in rows)
    assert all(row["live_status"] == "NO_LIVE_PORTFOLIOS_YET" for row in rows)
    assert all(row["return_to_drawdown_ratio"] is None for row in rows)


def test_leaderboard_reflects_a_real_backtest_run_and_ranks_by_return_to_drawdown(
    seeded_client: TestClient,
) -> None:
    run_response = seeded_client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert run_response.status_code == 200
    assert "buy_and_hold" in run_response.json()

    response = seeded_client.get("/api/v1/strategies/leaderboard")
    assert response.status_code == 200
    rows = response.json()
    by_id = {row["strategy_id"]: row for row in rows}
    assert by_id.keys() == ALL_STRATEGY_IDS
    for strategy_id in ALL_STRATEGY_IDS:
        assert by_id[strategy_id]["backtest_status"] == "AVAILABLE"
        assert by_id[strategy_id]["backtest"]["dataset_origin"] == "ACTUAL_PROVIDER_DATA"
        assert by_id[strategy_id]["return_to_drawdown_ratio"] is not None

    ratios = [Decimal(row["return_to_drawdown_ratio"]) for row in rows]
    assert ratios == sorted(ratios, reverse=True)


def test_leaderboard_ratio_is_null_when_a_strategy_has_no_drawdown(
    seeded_client: TestClient,
) -> None:
    report = {
        "scenario": "Synthetic Flat Line",
        "strategy_name": "BuyAndHoldBenchmarkStrategyV0",
        "classification": ["RESEARCH_ONLY"],
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "starting_cash": "1000000.0000",
        "ending_nav": "1000000.0000",
        "total_return": "0.0000",
        "max_drawdown": "0.0000",
        "rebalance_count": 0,
        "position_count": 0,
        "total_transaction_cost": "0.0000",
        "universe_size": 2,
        "bar_count": 520,
        "raw_snapshot_hash": "synthetic-hash",
        "equity_curve": [],
        "warnings": [],
    }
    monkeypatch_reports = [report]
    app_main.real_momentum_reports.extend(monkeypatch_reports)
    try:
        response = seeded_client.get("/api/v1/strategies/leaderboard")
        assert response.status_code == 200
        row = next(
            r for r in response.json() if r["strategy_id"] == "BuyAndHoldBenchmarkStrategyV0"
        )
        assert row["backtest_status"] == "AVAILABLE"
        assert row["return_to_drawdown_ratio"] is None
    finally:
        app_main.real_momentum_reports.clear()


def test_leaderboard_live_rollup_aggregates_real_nav_history(seeded_client: TestClient) -> None:
    portfolio_a = app_main.paper_orchestrator.create_portfolio(
        name="Leaderboard Test A",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    app_main.paper_orchestrator.create_strategy_config(
        portfolio_a.paper_portfolio_id, strategy_id="TrendFollowingBaselineStrategyV0"
    )
    portfolio_b = app_main.paper_orchestrator.create_portfolio(
        name="Leaderboard Test B",
        description="unit test",
        starting_capital=Decimal(200000),
        created_by="FOUNDER",
    )
    app_main.paper_orchestrator.create_strategy_config(
        portfolio_b.paper_portfolio_id, strategy_id="TrendFollowingBaselineStrategyV0"
    )
    # A strategy config with no nav-history at all (never run a session) must
    # not count toward the rollup.
    portfolio_c = app_main.paper_orchestrator.create_portfolio(
        name="Leaderboard Test C",
        description="unit test",
        starting_capital=Decimal(50000),
        created_by="FOUNDER",
    )
    app_main.paper_orchestrator.create_strategy_config(
        portfolio_c.paper_portfolio_id, strategy_id="TrendFollowingBaselineStrategyV0"
    )

    def snapshot(
        portfolio_id: str, nav: Decimal, high_water_mark: Decimal, drawdown: Decimal
    ) -> PaperNavSnapshot:
        return PaperNavSnapshot(
            paper_portfolio_id=portfolio_id,
            valuation_time=datetime(2026, 1, 2, tzinfo=UTC),
            available_cash=Decimal(0),
            unsettled_receivables=Decimal(0),
            market_value=nav,
            nav=nav,
            high_water_mark=high_water_mark,
            drawdown=drawdown,
            reconciliation_status="RECONCILED",
        )

    app_main.paper_repo.nav[portfolio_a.paper_portfolio_id] = [
        snapshot(portfolio_a.paper_portfolio_id, Decimal(110000), Decimal(110000), Decimal(0))
    ]
    app_main.paper_repo.nav[portfolio_b.paper_portfolio_id] = [
        snapshot(portfolio_b.paper_portfolio_id, Decimal(200000), Decimal(200000), Decimal(0)),
        snapshot(
            portfolio_b.paper_portfolio_id, Decimal(180000), Decimal(200000), Decimal("-0.10")
        ),
    ]

    response = seeded_client.get("/api/v1/strategies/leaderboard")
    assert response.status_code == 200
    row = next(r for r in response.json() if r["strategy_id"] == "TrendFollowingBaselineStrategyV0")
    assert row["live_status"] == "AVAILABLE"
    assert row["live"]["portfolio_count"] == 2  # C excluded -- no nav-history
    assert Decimal(row["live"]["combined_starting_capital"]) == Decimal("300000.0000")
    assert Decimal(row["live"]["combined_latest_nav"]) == Decimal("290000.0000")
    assert Decimal(row["live"]["worst_drawdown"]) == Decimal("-0.1000")
    expected_return = (Decimal("290000.0000") - Decimal("300000.0000")) / Decimal("300000.0000")
    assert Decimal(row["live"]["combined_return"]) == expected_return.quantize(Decimal("0.0001"))
