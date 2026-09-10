from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis.paper_trading.domain import (
    LifecycleStatus,
    PaperNavSnapshot,
    PaperReconciliationRecord,
    PaperTradingSession,
)
from aegis_api.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    # paper_repo/real_momentum_reports are module-level singletons shared
    # across the whole pytest session -- clear them so other Cockpit test
    # files' data can't leak into this file's evidence assertions.
    app_main.paper_repo.portfolios.clear()
    app_main.paper_repo.sessions.clear()
    app_main.paper_repo.nav.clear()
    app_main.paper_repo.reconciliations.clear()
    app_main.real_momentum_reports.clear()
    return TestClient(app)


def test_evidence_is_honest_zero_with_no_real_data_yet(client: TestClient) -> None:
    response = client.get("/api/v1/live-readiness/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["gate_1_research_integrity"]["real_backtests_run"] == 0
    assert body["gate_1_research_integrity"]["dataset_origin"] is None
    assert "No real backtest run yet" in body["gate_1_research_integrity"]["detail"]
    assert body["gate_2_paper_trading_evidence"]["portfolio_count"] == 0
    assert body["gate_2_paper_trading_evidence"]["total_real_sessions"] == 0
    assert body["gate_2_paper_trading_evidence"]["longest_days_active"] == 0


def test_evidence_reflects_real_sessions_drawdown_and_activation_age(
    client: TestClient,
) -> None:
    portfolio = app_main.paper_orchestrator.create_portfolio(
        name="Evidence Test",
        description="unit test",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    activated_at = datetime.now(UTC) - timedelta(days=10)
    app_main.paper_repo.portfolios[portfolio.paper_portfolio_id] = portfolio.activate()
    # activate() stamps activated_at_nullable with utc_now() -- override with
    # a real 10-days-ago timestamp so days_active is deterministically testable.
    from dataclasses import replace

    app_main.paper_repo.portfolios[portfolio.paper_portfolio_id] = replace(
        app_main.paper_repo.portfolios[portfolio.paper_portfolio_id],
        activated_at_nullable=activated_at,
    )

    for index in range(3):
        session = PaperTradingSession(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            session_date=(datetime.now(UTC) - timedelta(days=index)).date(),
            market_session_status="OPEN",
            data_readiness_status="GREEN",
            portfolio_risk_state="NORMAL",
            decision_cycle_status=LifecycleStatus.COMPLETED,
            execution_cycle_status=LifecycleStatus.COMPLETED,
            reconciliation_status="MATCHED",
            correlation_id=f"corr-{index}",
        )
        app_main.paper_repo.sessions[session.id] = session

    app_main.paper_repo.nav[portfolio.paper_portfolio_id] = [
        PaperNavSnapshot(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            valuation_time=datetime.now(UTC),
            available_cash=Decimal(10000),
            unsettled_receivables=Decimal(0),
            market_value=Decimal(84000),
            nav=Decimal(94000),
            high_water_mark=Decimal(100000),
            drawdown=Decimal("-0.06"),
            reconciliation_status="MATCHED",
        )
    ]
    app_main.paper_repo.reconciliations[portfolio.paper_portfolio_id] = [
        PaperReconciliationRecord(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            reconciliation_time=datetime.now(UTC),
            expected_nav=Decimal(94000),
            observed_nav=Decimal(94000),
            status="MATCHED",
            reason_codes=[],
        ),
        PaperReconciliationRecord(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            reconciliation_time=datetime.now(UTC),
            expected_nav=Decimal(94000),
            observed_nav=Decimal(93500),
            status="MISMATCH",
            reason_codes=["PRICE_SOURCE_DRIFT"],
        ),
    ]

    response = client.get("/api/v1/live-readiness/evidence")
    assert response.status_code == 200
    gate_2 = response.json()["gate_2_paper_trading_evidence"]
    assert gate_2["portfolio_count"] == 1
    assert gate_2["total_real_sessions"] == 3
    assert gate_2["longest_days_active"] == 10
    assert gate_2["total_reconciliation_mismatches"] == 1

    portfolio_row = gate_2["portfolios"][0]
    assert portfolio_row["worst_drawdown_observed"] == "-0.06"
    assert portfolio_row["reconciliation_count"] == 2
