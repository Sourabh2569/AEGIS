from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.backtesting.domain import OrderSide
from aegis.backtesting.engine import BacktestService
from aegis.backtesting.fixtures import load_calendar, load_market_data
from aegis.backtesting.repositories import BacktestRepository
from aegis.domain.models import DatasetVersion, Instrument, ProviderLicense, ProviderLicenseStatus, ValidationStatus


repo = BacktestRepository()
audit = AuditLog()
service = BacktestService(repo, audit)
calendar = load_calendar(Path("sample_data/backtesting/market_calendar.csv"))
market_data = load_market_data(Path("sample_data/backtesting/valid_eod_prices.csv"), "dataset-version-1")
service.attach_calendar_for_intent_creation(calendar)

run = service.create_run(
    name="Scenario A - Single Buy And Hold",
    description="Foundation simulation only",
    dataset_version_id="dataset-version-1",
    instrument_master_version="instrument-master.v1",
    instrument_id="AEGIS-IN-000001",
    start_date=date(2026, 6, 25),
    end_date=date(2026, 6, 29),
    starting_cash=Decimal("100000"),
    created_by="RESEARCHER",
)
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
    dataset_version=DatasetVersion(
        dataset_id="dataset-1",
        provider_id="provider-1",
        schema_version="eod_ohlcv.v1",
        raw_snapshot_hash="hash",
        transformation_version="v1",
        instrument_master_version="instrument-master.v1",
        corporate_action_version="corporate-actions.v1",
        validation_status=ValidationStatus.GREEN,
        quality_score=100,
        lineage_record_exists=True,
        id="dataset-version-1",
    ),
    provider_license=ProviderLicense(
        provider_id="provider-1",
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="test",
        automation_rights=True,
        backtesting_rights=True,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="test",
    ),
    instrument=Instrument(
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
        mapping_confidence_score=0.99,
    ),
    calendar=calendar,
    market_data=market_data,
)
print(
    {
        "backtest_run_id": completed.backtest_run_id,
        "status": completed.status,
        "final_nav": repo.nav_snapshots[completed.backtest_run_id][-1].portfolio_nav,
        "labels": completed.labels,
    }
)
