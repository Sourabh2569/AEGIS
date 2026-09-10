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
from aegis.paper_trading.domain import (
    PaperApproval,
    PaperApprovalDecision,
    PaperNavSnapshot,
    PaperTradeIntent,
)
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
    dates = _trading_dates(date(2016, 1, 1), SEEDED_DAYS * 4)
    payload = []
    for index, trade_date in enumerate(dates):
        payload.append(_bar(UPTREND_ID, trade_date, 100.0 * (1.002**index)))
        payload.append(_bar(DOWNTREND_ID, trade_date, 100.0 * (0.998**index)))
    target_dir = root / "raw" / "test-provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seed.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    store_root = tmp_path / "object_store"
    _seed_object_store(store_root)
    monkeypatch.setattr(app_main, "object_store", LocalObjectStore(store_root))
    # paper_repo/real_momentum_reports are module-level singletons shared
    # across the whole pytest session -- clear them so other Cockpit test
    # files' data can't leak into this file's achievement assertions.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.strategy_configs.clear()
    app_main.paper_repo.nav.clear()
    app_main.paper_repo.paper_portfolios.clear()
    app_main.paper_repo.intents.clear()
    app_main.paper_repo.approvals.clear()
    app_main.real_momentum_reports.clear()
    return TestClient(app)


def _achievements_by_id(body: dict) -> dict[str, dict]:
    return {item["id"]: item for item in body["achievements"]}


def test_benchmark_beater_is_unachieved_with_no_backtest_yet(client: TestClient) -> None:
    response = client.get("/api/v1/achievements")
    assert response.status_code == 200
    by_id = _achievements_by_id(response.json())
    beater = by_id["benchmark-beater-EqualWeightUniverseBenchmarkStrategyV0"]
    assert beater["achieved"] is False
    assert "no real backtest run yet" in beater["detail"].lower()


def test_benchmark_beater_is_achieved_after_a_real_backtest(client: TestClient) -> None:
    run_response = client.post(
        "/api/v1/research/momentum/run", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert run_response.status_code == 200

    response = client.get("/api/v1/achievements")
    by_id = _achievements_by_id(response.json())
    beater = by_id["benchmark-beater-EqualWeightUniverseBenchmarkStrategyV0"]
    # A strongly uptrending real instrument alone must beat a book diluted by
    # a real downtrending instrument for a real, sustained run of months.
    assert beater["achieved"] is True
    assert beater["achieved_at"] is not None
    assert "straight real rebalance months" in beater["detail"]


def test_portfolio_nav_achievements_with_no_sessions(client: TestClient) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Achievements Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    response = client.get("/api/v1/achievements")
    by_id = _achievements_by_id(response.json())
    hwm = by_id[f"new-high-water-mark-{portfolio.paper_portfolio_id}"]
    recovery = by_id[f"drawdown-recovery-{portfolio.paper_portfolio_id}"]
    assert hwm["achieved"] is False
    assert recovery["achieved"] is False
    assert "no real trading sessions" in hwm["detail"].lower()


def test_portfolio_nav_achievements_reflect_a_real_high_water_mark_and_recovery(
    client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Recovery Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    snapshots = [
        PaperNavSnapshot(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            valuation_time=base_time,
            available_cash=Decimal(10000),
            unsettled_receivables=Decimal(0),
            market_value=Decimal(90000),
            nav=Decimal(100000),
            high_water_mark=Decimal(100000),
            drawdown=Decimal(0),
            reconciliation_status="MATCHED",
        ),
        PaperNavSnapshot(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            valuation_time=base_time + timedelta(days=10),
            available_cash=Decimal(10000),
            unsettled_receivables=Decimal(0),
            market_value=Decimal(84000),
            nav=Decimal(94000),
            high_water_mark=Decimal(100000),
            drawdown=Decimal("-0.06"),
            reconciliation_status="MATCHED",
        ),
        PaperNavSnapshot(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            valuation_time=base_time + timedelta(days=20),
            available_cash=Decimal(10000),
            unsettled_receivables=Decimal(0),
            market_value=Decimal(101500),
            nav=Decimal(101500),
            high_water_mark=Decimal(101500),
            drawdown=Decimal(0),
            reconciliation_status="MATCHED",
        ),
    ]
    app_main.paper_repo.nav[portfolio.paper_portfolio_id] = snapshots

    response = client.get("/api/v1/achievements")
    by_id = _achievements_by_id(response.json())
    hwm = by_id[f"new-high-water-mark-{portfolio.paper_portfolio_id}"]
    recovery = by_id[f"drawdown-recovery-{portfolio.paper_portfolio_id}"]
    assert hwm["achieved"] is True
    assert "101500" in hwm["detail"]
    assert recovery["achieved"] is True
    assert "-6.0%" in recovery["detail"]


def test_on_time_reviewer_and_first_live_approval_count_real_decisions(
    client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Approval Timing Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    eligible = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    on_time_intent = PaperTradeIntent(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        paper_strategy_config_id="config-1",
        strategy_version_id="strategy-v0",
        instrument_id=UPTREND_ID,
        side="BUY",
        proposed_quantity=Decimal(10),
        decision_time=eligible - timedelta(hours=2),
        available_data_cutoff=eligible - timedelta(hours=3),
        eligible_execution_time=eligible,
        risk_assessment_id="risk-1",
        configuration_version="v0",
        idempotency_key="idem-1",
        correlation_id="corr-1",
    )
    late_intent = PaperTradeIntent(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        paper_strategy_config_id="config-1",
        strategy_version_id="strategy-v0",
        instrument_id=DOWNTREND_ID,
        side="SELL",
        proposed_quantity=Decimal(5),
        decision_time=eligible - timedelta(hours=2),
        available_data_cutoff=eligible - timedelta(hours=3),
        eligible_execution_time=eligible,
        risk_assessment_id="risk-2",
        configuration_version="v0",
        idempotency_key="idem-2",
        correlation_id="corr-2",
    )
    app_main.paper_repo.intents[on_time_intent.paper_trade_intent_id] = on_time_intent
    app_main.paper_repo.intents[late_intent.paper_trade_intent_id] = late_intent
    app_main.paper_repo.approvals[on_time_intent.paper_trade_intent_id] = PaperApproval(
        paper_trade_intent_id=on_time_intent.paper_trade_intent_id,
        approver_id="FOUNDER",
        decision=PaperApprovalDecision.APPROVED,
        decision_time=eligible - timedelta(hours=1),  # before the eligible window -- on time
        risk_assessment_id="risk-1",
        paper_strategy_config_id="config-1",
        reason="looks good",
        expiry_time=eligible + timedelta(days=1),
    )
    app_main.paper_repo.approvals[late_intent.paper_trade_intent_id] = PaperApproval(
        paper_trade_intent_id=late_intent.paper_trade_intent_id,
        approver_id="FOUNDER",
        decision=PaperApprovalDecision.REJECTED,
        decision_time=eligible + timedelta(hours=1),  # after the eligible window -- late
        risk_assessment_id="risk-2",
        paper_strategy_config_id="config-1",
        reason="too late",
        expiry_time=eligible + timedelta(days=1),
    )

    response = client.get("/api/v1/achievements")
    by_id = _achievements_by_id(response.json())

    reviewer = by_id["on-time-reviewer"]
    assert reviewer["achieved"] is True
    assert "1 of 2" in reviewer["detail"]

    first_approval = by_id[f"first-live-approval-{portfolio.paper_portfolio_id}"]
    assert first_approval["achieved"] is True
    assert first_approval["achieved_at"] is not None


def test_on_time_reviewer_is_not_achieved_when_most_decisions_are_late(client: TestClient) -> None:
    """A real 1-of-3 on-time rate must read as unachieved -- this badge
    rewards genuine process discipline, not mere participation."""
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Mostly Late Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    eligible = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    for index in range(3):
        intent = PaperTradeIntent(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            paper_strategy_config_id="config-1",
            strategy_version_id="strategy-v0",
            instrument_id=UPTREND_ID,
            side="BUY",
            proposed_quantity=Decimal(1),
            decision_time=eligible - timedelta(hours=2),
            available_data_cutoff=eligible - timedelta(hours=3),
            eligible_execution_time=eligible,
            risk_assessment_id=f"risk-{index}",
            configuration_version="v0",
            idempotency_key=f"idem-late-{index}",
            correlation_id=f"corr-late-{index}",
        )
        app_main.paper_repo.intents[intent.paper_trade_intent_id] = intent
        # Only the first of three is on time -- a real 1-of-3 rate.
        decided_at = eligible - timedelta(hours=1) if index == 0 else eligible + timedelta(hours=1)
        app_main.paper_repo.approvals[intent.paper_trade_intent_id] = PaperApproval(
            paper_trade_intent_id=intent.paper_trade_intent_id,
            approver_id="FOUNDER",
            decision=PaperApprovalDecision.APPROVED,
            decision_time=decided_at,
            risk_assessment_id=f"risk-{index}",
            paper_strategy_config_id="config-1",
            reason="test",
            expiry_time=eligible + timedelta(days=1),
        )

    response = client.get("/api/v1/achievements")
    reviewer = _achievements_by_id(response.json())["on-time-reviewer"]
    assert reviewer["achieved"] is False
    assert "1 of 3" in reviewer["detail"]
