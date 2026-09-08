from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from aegis.audit.service import AuditLog
from aegis.paper_trading.domain import (
    PAPER_LABELS,
    IncidentType,
    LifecycleStatus,
    PaperApprovalDecision,
    PaperIntentStatus,
    PaperOrderStatus,
    PaperPortfolioStatus,
)
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import PaperSessionJob, SqlitePaperSessionQueue
from aegis.paper_trading.services import (
    PaperTradingCalendarService,
    PaperTradingOrchestrator,
    PaperTradingRepository,
    all_admission_evidence,
    all_readiness_green,
)
from aegis.risk.engine import KillSwitchType


def _stub_target_resolver(
    strategy_id: str, session_date: date
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Deterministic stand-in for a real strategy signal -- these tests
    exercise approval/execution/idempotency/kill-switch mechanics, not
    strategy selection, so a fixed 10% target weight is enough to produce a
    real, risk-sized BUY intent without depending on real market data."""
    return {"AEGIS-IN-000001": Decimal("0.10")}, {"AEGIS-IN-000001": Decimal(100)}


def setup_active_orchestrator():
    repo = PaperTradingRepository()
    audit = AuditLog()
    orch = PaperTradingOrchestrator(
        repo,
        audit,
        sector_by_instrument={"AEGIS-IN-000001": "Financials"},
        strategy_target_resolver=_stub_target_resolver,
    )
    portfolio = orch.create_portfolio(
        name="Paper Test",
        description="Paper-only fixture",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )
    return orch, repo, audit, portfolio, config


def create_intent(orch, repo, portfolio):
    orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(112)},
    )
    return next(
        intent
        for intent in repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id
    )


def test_paper_labels_and_no_broker_fields() -> None:
    orch, _, _, portfolio, _ = setup_active_orchestrator()
    assert PAPER_LABELS == portfolio.labels
    assert not hasattr(portfolio, "broker_account_id")
    assert not hasattr(orch, "broker")


def test_admission_requires_all_evidence() -> None:
    orch, _, _, portfolio, _ = setup_active_orchestrator()
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    evidence = all_admission_evidence()
    evidence["founder_approval_recorded"] = False
    with pytest.raises(ValueError):
        orch.admit_and_activate_strategy(config.paper_strategy_config_id, evidence, "FOUNDER")


def test_frozen_strategy_configuration_is_immutable() -> None:
    _, repo, _, _, config = setup_active_orchestrator()
    with pytest.raises(ValueError):
        repo.strategy_configs[config.paper_strategy_config_id].update_strategy_version("new")


def test_readiness_failure_blocks_new_order_and_freezes_on_red_dataset() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    flags = all_readiness_green()
    flags["dataset_green_or_caution"] = False
    session = orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=flags,
        reference_prices={"AEGIS-IN-000001": Decimal(112)},
    )
    assert session.decision_cycle_status == LifecycleStatus.BLOCKED
    assert repo.portfolios[portfolio.paper_portfolio_id].status == PaperPortfolioStatus.FROZEN


def test_order_cannot_execute_without_approval() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    create_intent(orch, repo, portfolio)
    orders = orch.execute_approved_orders(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        execution_time=datetime(2026, 6, 29, 3, 45, tzinfo=UTC),
        reference_prices={"AEGIS-IN-000001": Decimal(113)},
    )
    assert orders[0].status == PaperOrderStatus.BLOCKED
    assert orders[0].rejection_reason_nullable == "APPROVAL_MISSING"


def test_approval_expiry_blocks_execution() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    intent = create_intent(orch, repo, portfolio)
    approval = orch.approvals.approve(intent.paper_trade_intent_id, "RISK_REVIEWER")
    expired = orch.approvals.expire_due(approval.expiry_time + timedelta(seconds=1))
    assert expired[0].decision == PaperApprovalDecision.EXPIRED
    assert repo.intents[intent.paper_trade_intent_id].intent_status == PaperIntentStatus.EXPIRED


def test_successful_forward_cycle_and_duplicate_execution_impossible() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    intent = create_intent(orch, repo, portfolio)
    orch.approvals.approve(
        intent.paper_trade_intent_id,
        "RISK_REVIEWER",
        datetime(2026, 6, 26, 11, 0, tzinfo=UTC),
    )
    orders = orch.execute_approved_orders(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        execution_time=datetime(2026, 6, 29, 3, 45, tzinfo=UTC),
        reference_prices={"AEGIS-IN-000001": Decimal(113)},
    )
    assert orders[0].status == PaperOrderStatus.FILLED
    fill_count = len(repo.fills)
    second = orch.execute_approved_orders(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        execution_time=datetime(2026, 6, 29, 3, 46, tzinfo=UTC),
        reference_prices={"AEGIS-IN-000001": Decimal(113)},
    )
    assert second == []
    assert len(repo.fills) == fill_count


def test_reconciliation_failure_freezes_portfolio() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    orch.value_and_reconcile(portfolio.paper_portfolio_id, {}, inject_failure=True)
    assert repo.portfolios[portfolio.paper_portfolio_id].status == PaperPortfolioStatus.FROZEN
    assert any(
        incident.incident_type == IncidentType.RECONCILIATION_INCIDENT
        for incident in repo.incidents.values()
    )


def test_kill_switch_blocks_pending_intent() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    intent = create_intent(orch, repo, portfolio)
    orch.activate_kill_switch(
        KillSwitchType.PORTFOLIO_KILL_SWITCH, portfolio.paper_portfolio_id, "test"
    )
    assert repo.intents[intent.paper_trade_intent_id].intent_status == PaperIntentStatus.BLOCKED


def test_evidence_package_has_paper_classification() -> None:
    orch, _, _, portfolio, _ = setup_active_orchestrator()
    package = orch.evidence_package(portfolio.paper_portfolio_id)
    assert "PAPER_TRADING_ONLY" in package.classification


def test_exchange_calendar_governs_eligible_execution_time() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    intent = create_intent(orch, repo, portfolio)
    assert intent.eligible_execution_time == datetime(2026, 6, 29, 3, 45, tzinfo=UTC)


def test_sqlite_repository_persists_paper_tables(tmp_path) -> None:
    db_path = tmp_path / "paper.sqlite"
    repo = SqlitePaperTradingRepository(db_path)
    audit = AuditLog()
    orch = PaperTradingOrchestrator(repo, audit)  # persistence-only fixture, no decision cycle run
    portfolio = orch.create_portfolio(
        name="Persistent Paper",
        description="DB-backed fixture",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )
    reloaded = SqlitePaperTradingRepository(db_path)
    assert portfolio.paper_portfolio_id in reloaded.portfolios
    assert config.paper_strategy_config_id in reloaded.strategy_configs


def test_queue_backed_session_execution(tmp_path) -> None:
    db_path = tmp_path / "paper.sqlite"
    queue_path = tmp_path / "queue.sqlite"
    repo = SqlitePaperTradingRepository(db_path)
    orch = PaperTradingOrchestrator(
        repo,
        AuditLog(),
        sector_by_instrument={"AEGIS-IN-000001": "Financials"},
        strategy_target_resolver=_stub_target_resolver,
    )
    portfolio = orch.create_portfolio(
        name="Queued Paper",
        description="Queue-backed fixture",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )
    queue = SqlitePaperSessionQueue(queue_path)
    job = queue.enqueue(
        PaperSessionJob(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            session_date=date(2026, 6, 26),
            reference_prices={"AEGIS-IN-000001": Decimal(112)},
        )
    )
    completed = queue.run_once(orch)
    assert completed is not None
    assert completed.id == job.id
    assert queue.list_jobs()[0]["status"] == "COMPLETED"
    assert repo.intents


def test_corporate_action_review_freezes_unsupported_actions() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    review = orch.corporate_actions.review(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        instrument_id="AEGIS-IN-000001",
        action_type="DEMERGER",
        effective_date=date(2026, 6, 30),
        verification_status="PENDING",
        supported=False,
        reviewer_id="DATA_STEWARD",
        correlation_id="test-ca-review",
    )
    assert review.decision == "REJECTED_AND_PORTFOLIO_FROZEN"
    assert repo.portfolios[portfolio.paper_portfolio_id].status == PaperPortfolioStatus.FROZEN


def test_calendar_fixture_rejects_closed_session_execution() -> None:
    calendar = PaperTradingCalendarService(sessions=[date(2026, 6, 26), date(2026, 6, 29)])
    assert calendar.next_open_session_after(datetime(2026, 6, 26, 10, 45, tzinfo=UTC)) == date(
        2026, 6, 29
    )
    with pytest.raises(ValueError):
        calendar.open_time(date(2026, 6, 27))


def test_run_decision_cycle_creates_one_intent_per_instrument_in_target_weights() -> None:
    """The old placeholder could only ever propose one instrument. A real
    strategy's target weights can span several -- the bridge must create one
    real, risk-sized intent per instrument that actually needs a trade."""
    repo = PaperTradingRepository()
    orch = PaperTradingOrchestrator(
        repo,
        AuditLog(),
        sector_by_instrument={
            "AEGIS-IN-000001": "Financials",
            "AEGIS-IN-000002": "Information Technology",
        },
        strategy_target_resolver=lambda strategy_id, session_date: (
            {"AEGIS-IN-000001": Decimal("0.10"), "AEGIS-IN-000002": Decimal("0.10")},
            {},
        ),
    )
    portfolio = orch.create_portfolio(
        name="Multi",
        description="multi-instrument",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )

    orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(112), "AEGIS-IN-000002": Decimal(220)},
    )

    portfolio_intents = [
        intent
        for intent in repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id
    ]
    assert {intent.instrument_id for intent in portfolio_intents} == {
        "AEGIS-IN-000001",
        "AEGIS-IN-000002",
    }
    assert all(intent.side == "BUY" for intent in portfolio_intents)


def test_run_decision_cycle_sells_a_position_dropped_from_target_weights() -> None:
    """A real strategy rotates: an instrument that was bought last cycle can
    legitimately fall out of the target this cycle. The bridge must propose
    a real SELL sized to the actual holding, not just ever-growing BUYs."""
    repo = PaperTradingRepository()
    weights: dict[str, Decimal] = {"AEGIS-IN-000001": Decimal("0.10")}
    orch = PaperTradingOrchestrator(
        repo,
        AuditLog(),
        calendar=PaperTradingCalendarService(
            sessions=[
                date(2026, 6, 26),
                date(2026, 6, 29),
                date(2026, 6, 30),
                date(2026, 7, 1),
            ]
        ),
        sector_by_instrument={"AEGIS-IN-000001": "Financials"},
        strategy_target_resolver=lambda strategy_id, session_date: (weights, {}),
    )
    portfolio = orch.create_portfolio(
        name="SellTest",
        description="drop from target",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )

    orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(112)},
    )
    buy_intent = next(
        intent
        for intent in repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id
    )
    orch.approvals.approve(
        buy_intent.paper_trade_intent_id, "RISK_REVIEWER", datetime(2026, 6, 26, 11, 0, tzinfo=UTC)
    )
    orch.execute_approved_orders(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        execution_time=datetime(2026, 6, 29, 3, 45, tzinfo=UTC),
        reference_prices={"AEGIS-IN-000001": Decimal(113)},
    )
    held_qty = repo.paper_portfolios[portfolio.paper_portfolio_id].positions.get(
        "AEGIS-IN-000001", Decimal(0)
    )
    assert held_qty > 0

    weights.clear()  # the strategy no longer wants this instrument
    orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 30),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(115)},
    )

    sell_intents = [
        intent
        for intent in repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id and intent.side == "SELL"
    ]
    assert sell_intents
    assert sell_intents[0].approved_quantity_nullable == held_qty


def test_run_decision_cycle_skips_cleanly_when_resolver_has_no_signal() -> None:
    """A resolver returning None (no real data captured yet, or an unknown
    strategy_id) must never be treated as 'trade zero' -- it must skip
    without fabricating any intent."""
    repo = PaperTradingRepository()
    orch = PaperTradingOrchestrator(
        repo,
        AuditLog(),
        sector_by_instrument={"AEGIS-IN-000001": "Financials"},
        strategy_target_resolver=lambda strategy_id, session_date: None,
    )
    portfolio = orch.create_portfolio(
        name="NoSignal",
        description="no real data",
        starting_capital=Decimal(100000),
        created_by="FOUNDER",
    )
    config = orch.create_strategy_config(portfolio.paper_portfolio_id)
    orch.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), "FOUNDER"
    )

    session = orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(112)},
    )

    assert session.decision_cycle_status == LifecycleStatus.COMPLETED
    assert not any(
        intent.paper_portfolio_id == portfolio.paper_portfolio_id
        for intent in repo.intents.values()
    )


def test_run_decision_cycle_is_idempotent_per_portfolio_and_session_date() -> None:
    orch, repo, _, portfolio, _ = setup_active_orchestrator()
    first = create_intent(orch, repo, portfolio)
    session_before = next(
        session
        for session in repo.sessions.values()
        if session.paper_portfolio_id == portfolio.paper_portfolio_id
    )

    orch.run_decision_cycle(
        paper_portfolio_id=portfolio.paper_portfolio_id,
        session_date=date(2026, 6, 26),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal(112)},
    )

    portfolio_intents = [
        intent
        for intent in repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id
    ]
    assert portfolio_intents == [first]
    session_after = next(
        session
        for session in repo.sessions.values()
        if session.paper_portfolio_id == portfolio.paper_portfolio_id
    )
    assert session_after.paper_trading_session_id == session_before.paper_trading_session_id
