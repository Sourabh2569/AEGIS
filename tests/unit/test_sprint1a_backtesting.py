from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from aegis.audit.service import AuditLog
from aegis.backtesting.accounting import gross_notional, weighted_average_cost_basis
from aegis.backtesting.domain import BacktestRunStatus, OrderSide, SimulatedOrderStatus, SPRINT_1A_LABELS
from aegis.backtesting.engine import BacktestService
from aegis.backtesting.execution import reject_same_close_execution
from aegis.backtesting.fixtures import load_calendar, load_market_data
from aegis.backtesting.repositories import BacktestRepository
from aegis.domain.models import (
    DatasetVersion,
    Instrument,
    ProviderLicense,
    ProviderLicenseStatus,
    ValidationStatus,
)
from aegis.shared.errors import OrderRejected


ROOT = Path(__file__).resolve().parents[2]


def dataset(status: ValidationStatus = ValidationStatus.GREEN) -> DatasetVersion:
    return DatasetVersion(
        dataset_id="dataset-1",
        provider_id="provider-1",
        schema_version="eod_ohlcv.v1",
        raw_snapshot_hash="hash",
        transformation_version="v1",
        instrument_master_version="instrument-master.v1",
        corporate_action_version="corporate-actions.v1",
        validation_status=status,
        quality_score=100,
        lineage_record_exists=True,
        id="dataset-version-1",
    )


def license_(status: ProviderLicenseStatus = ProviderLicenseStatus.APPROVED) -> ProviderLicense:
    return ProviderLicense(
        provider_id="provider-1",
        license_status=status,
        permitted_use="test",
        automation_rights=True,
        backtesting_rights=True,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="test",
    )


def instrument(confidence: float = 0.99) -> Instrument:
    return Instrument(
        aegis_instrument_id="AEGIS-IN-000001",
        isin="INE000A01000",
        company_legal_name="AEGIS Test Equity Limited",
        security_type="EQUITY",
        current_symbol="AEGISTEST",
        primary_exchange="NSE",
        listing_date=date(2020, 1, 1),
        trading_status="ACTIVE",
        sector="Financials",
        industry="Capital Markets",
        mapping_confidence_score=confidence,
    )


def service_setup(market_file: str = "valid_eod_prices.csv"):
    repo = BacktestRepository()
    audit = AuditLog()
    service = BacktestService(repo, audit)
    calendar = load_calendar(ROOT / "sample_data/backtesting/market_calendar.csv")
    market_data = load_market_data(ROOT / f"sample_data/backtesting/{market_file}", "dataset-version-1")
    service.attach_calendar_for_intent_creation(calendar)
    run = service.create_run(
        name="Scenario",
        description="Foundation simulation only",
        dataset_version_id="dataset-version-1",
        instrument_master_version="instrument-master.v1",
        instrument_id="AEGIS-IN-000001",
        start_date=date(2026, 6, 25),
        end_date=date(2026, 6, 29),
        starting_cash=Decimal("100000"),
        created_by="RESEARCHER",
    )
    return service, repo, audit, calendar, market_data, run


def test_decimal_money_arithmetic_and_weighted_average_cost_basis() -> None:
    assert gross_notional(Decimal("10"), Decimal("106.00")) == Decimal("1060.0000")
    assert weighted_average_cost_basis(
        Decimal("10"), Decimal("100"), Decimal("10"), Decimal("110")
    ) == Decimal("105.0000")


def test_scenario_a_single_buy_and_hold() -> None:
    service, repo, audit, calendar, market_data, run = service_setup()
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.BUY,
        requested_quantity=Decimal("100"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    completed = service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert completed.status == BacktestRunStatus.COMPLETED
    assert repo.cash_ledger[run.backtest_run_id][-1].balance_after == Decimal("89400.0000")
    assert repo.position_ledger[run.backtest_run_id][-1].quantity_after == Decimal("100.000000")
    assert repo.nav_snapshots[run.backtest_run_id][-1].portfolio_nav == Decimal("100300.0000")
    assert audit.list_events()
    assert set(SPRINT_1A_LABELS) == set(completed.labels)


def test_scenario_b_buy_then_sell_realized_pnl() -> None:
    service, repo, _, calendar, market_data, run = service_setup()
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.BUY,
        requested_quantity=Decimal("100"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.SELL,
        requested_quantity=Decimal("100"),
        decision_time=datetime(2026, 6, 26, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 26, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert repo.realized_pnl(run.backtest_run_id) == Decimal("600.0000")
    assert repo.current_quantity(run.backtest_run_id) == Decimal("0.000000")


def test_insufficient_cash_rejects_without_ledger_movement() -> None:
    service, repo, _, calendar, market_data, run = service_setup()
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.BUY,
        requested_quantity=Decimal("10000"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert repo.orders[run.backtest_run_id][-1].status == SimulatedOrderStatus.REJECTED
    assert repo.orders[run.backtest_run_id][-1].rejection_reason_nullable == "INSUFFICIENT_CASH"
    assert len(repo.cash_ledger[run.backtest_run_id]) == 1


def test_same_close_execution_rejected() -> None:
    service, _, _, _, _, run = service_setup()
    intent = service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.BUY,
        requested_quantity=Decimal("10"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    with pytest.raises(OrderRejected):
        reject_same_close_execution(intent, datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc))


def test_missing_next_open_rejects_order() -> None:
    service, repo, _, calendar, market_data, run = service_setup("missing_open_price.csv")
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.BUY,
        requested_quantity=Decimal("10"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert repo.orders[run.backtest_run_id][-1].rejection_reason_nullable == "NEXT_OPEN_PRICE_MISSING"


def test_oversell_rejected() -> None:
    service, repo, _, calendar, market_data, run = service_setup()
    service.create_order_intent(
        backtest_run_id=run.backtest_run_id,
        side=OrderSide.SELL,
        requested_quantity=Decimal("10"),
        decision_time=datetime(2026, 6, 25, 10, 45, tzinfo=timezone.utc),
        available_data_cutoff=datetime(2026, 6, 25, 10, 30, tzinfo=timezone.utc),
        created_by="RESEARCHER",
    )
    service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert repo.orders[run.backtest_run_id][-1].rejection_reason_nullable == "OVERSELL"


def test_red_dataset_blocks_run() -> None:
    service, repo, _, calendar, market_data, run = service_setup()
    failed = service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(ValidationStatus.RED),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert failed.status == BacktestRunStatus.FAILED
    assert "DATASET_NOT_ELIGIBLE" in (failed.failure_reason_nullable or "")


def test_duplicate_start_is_idempotent() -> None:
    service, repo, _, calendar, market_data, run = service_setup()
    first = service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    second = service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
    )
    assert first.backtest_run_id == second.backtest_run_id
    assert len([e for e in repo.events[run.backtest_run_id] if e.event_type == "BACKTEST_STARTED"]) == 1


def test_reconciliation_failure_injection_fails_closed() -> None:
    service, _, audit, calendar, market_data, run = service_setup()
    failed = service.start_run(
        backtest_run_id=run.backtest_run_id,
        dataset_version=dataset(),
        provider_license=license_(),
        instrument=instrument(),
        calendar=calendar,
        market_data=market_data,
        inject_reconciliation_failure=True,
    )
    assert failed.status == BacktestRunStatus.FAILED
    assert any(event.event_type == "BACKTEST_FAILED" for event in audit.list_events())
