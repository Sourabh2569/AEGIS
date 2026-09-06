from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from aegis.audit.service import AuditLog
from aegis.configuration.settings import Settings
from aegis.corporate_actions.service import CorporateActionService
from aegis.data_ingestion.service import (
    InMemoryRepository,
    LocalObjectStore,
    ProviderIngestionService,
    stable_payload_hash,
)
from aegis.data_quality.validation import derive_validation_status, validate_eod_ohlcv
from aegis.domain.models import (
    CorporateAction,
    CorporateActionType,
    CorporateActionVerificationStatus,
    DataQualityResult,
    ExperimentManifest,
    IngestionStatus,
    ProviderLicense,
    ProviderLicenseStatus,
    QualityCategory,
    Severity,
    ValidationStatus,
    now_utc,
)
from aegis.provider_adapters.csv_provider import CsvFileProvider
from aegis.provider_adapters.mock_provider import MockMarketDataProvider


def license_with(status: ProviderLicenseStatus) -> ProviderLicense:
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


def test_expired_provider_license_blocks_ingestion(tmp_path: Path) -> None:
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path),
        repository=InMemoryRepository(),
        audit_log=AuditLog(),
    )
    run = service.ingest_eod_prices(
        provider=MockMarketDataProvider(license_with(ProviderLicenseStatus.EXPIRED)),
        provider_id="provider-1",
        dataset_id="dataset-1",
        dataset_name="eod_prices",
        known_instrument_ids={"AEGIS-IN-000001"},
    )
    assert run.status == IngestionStatus.BLOCKED
    assert "EXPIRED" in run.error_summary[0]


def test_duplicate_payload_does_not_create_second_dataset_version(tmp_path: Path) -> None:
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path),
        repository=repo,
        audit_log=AuditLog(),
    )
    kwargs = {
        "provider": MockMarketDataProvider(),
        "provider_id": "provider-1",
        "dataset_id": "dataset-1",
        "dataset_name": "eod_prices",
        "known_instrument_ids": {"AEGIS-IN-000001"},
    }
    first = service.ingest_eod_prices(**kwargs)
    second = service.ingest_eod_prices(**kwargs)
    assert first.status == IngestionStatus.COMPLETED
    assert second.status == IngestionStatus.BLOCKED
    assert len(repo.dataset_versions) == 1


def test_ingestion_defaults_dataset_origin_to_fixture_when_undeclared(tmp_path: Path) -> None:
    """A provider that never declares dataset_origin must default to
    FIXTURE_DATA (fail closed) -- ingestion must never assume data is real."""
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path), repository=repo, audit_log=AuditLog()
    )

    class UndeclaredOriginProvider:
        name = "undeclared-origin-provider"

        def get_license_status(self) -> ProviderLicense:
            return license_with(ProviderLicenseStatus.APPROVED)

        def fetch_eod_prices(self):
            return MockMarketDataProvider().fetch_eod_prices()

    run = service.ingest_eod_prices(
        provider=UndeclaredOriginProvider(),
        provider_id="provider-1",
        dataset_id="dataset-1",
        dataset_name="eod_prices",
        known_instrument_ids={"AEGIS-IN-000001"},
    )
    version_id = run.validation_summary["dataset_version_id"]
    assert repo.dataset_origins[version_id] == "FIXTURE_DATA"


def test_ingestion_tags_dataset_origin_as_declared_by_provider(tmp_path: Path) -> None:
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path), repository=repo, audit_log=AuditLog()
    )

    class RealDataProvider(MockMarketDataProvider):
        dataset_origin = "ACTUAL_PROVIDER_DATA"

    run = service.ingest_eod_prices(
        provider=RealDataProvider(),
        provider_id="provider-1",
        dataset_id="dataset-1",
        dataset_name="eod_prices",
        known_instrument_ids={"AEGIS-IN-000001"},
    )
    version_id = run.validation_summary["dataset_version_id"]
    assert repo.dataset_origins[version_id] == "ACTUAL_PROVIDER_DATA"


def test_adapter_dataset_origins_are_correctly_classified(tmp_path: Path) -> None:
    """Each adapter type must self-declare the right dataset_origin: mock/test
    fixtures never masquerade as real, and CSV import -- the designated
    approved-file path -- is distinct from a live provider connection."""
    assert MockMarketDataProvider().dataset_origin == "TEST_DATA"
    assert CsvFileProvider(tmp_path).dataset_origin == "APPROVED_FILE_IMPORT"


def test_ingestion_records_latest_eod_price_per_instrument(tmp_path: Path) -> None:
    """repo.latest_eod_prices is the only queryable record of ingested EOD
    prices (everything else lands only in the file-backed object store).
    Paper trading's real-price lookup depends on this being kept accurate:
    the most recent trade_date per instrument, not just whatever arrived
    last in the payload."""
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path), repository=repo, audit_log=AuditLog()
    )

    class TwoDayHistoryProvider(MockMarketDataProvider):
        def fetch_eod_prices(self):
            envelope = super().fetch_eod_prices()
            older = dict(envelope.payload[0])
            newer = dict(envelope.payload[0])
            older["trade_date"] = "2026-06-24"
            older["close"] = 2900.0
            newer["trade_date"] = "2026-06-25"
            newer["close"] = 2920.0
            # Intentionally out of order -- the older record arrives second.
            return replace(envelope, payload=[newer, older])

    service.ingest_eod_prices(
        provider=TwoDayHistoryProvider(),
        provider_id="provider-1",
        dataset_id="dataset-1",
        dataset_name="eod_prices",
        known_instrument_ids={"AEGIS-IN-000001"},
    )
    latest = repo.latest_eod_prices["AEGIS-IN-000001"]
    assert latest["trade_date"] == "2026-06-25"
    assert latest["close"] == 2920.0


def test_invalid_ohlc_record_is_rejected_and_red() -> None:
    records = [
        {
            "aegis_instrument_id": "AEGIS-IN-000001",
            "trade_date": "2026-06-25",
            "open": 100,
            "high": 90,
            "low": 95,
            "close": 98,
            "volume": 1,
            "event_time": "2026-06-25T15:30:00+05:30",
            "available_time": "2026-06-25T18:00:00+05:30",
            "ingested_time": "2026-06-25T18:05:00+05:30",
        }
    ]
    accepted, rejected, results = validate_eod_ohlcv(records, {"AEGIS-IN-000001"}, "version-1")
    assert accepted == []
    assert rejected
    assert derive_validation_status(results, critical_dataset=True) == ValidationStatus.RED


def test_missing_instrument_mapping_blocks_curated_eligibility() -> None:
    records = [
        {
            "aegis_instrument_id": "UNKNOWN",
            "trade_date": "2026-06-25",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1,
            "event_time": "2026-06-25T15:30:00+05:30",
            "available_time": "2026-06-25T18:00:00+05:30",
            "ingested_time": "2026-06-25T18:05:00+05:30",
        }
    ]
    _, rejected, results = validate_eod_ohlcv(records, set(), "version-1")
    assert "INSTRUMENT_MAPPING" in rejected[0]["reasons"][0]
    assert derive_validation_status(results, critical_dataset=True) == ValidationStatus.RED


def test_critical_quality_failure_sets_dataset_red() -> None:
    results = [
        DataQualityResult(
            dataset_version_id="version-1",
            check_name="critical",
            check_category=QualityCategory.SCHEMA,
            severity=Severity.CRITICAL,
            passed=False,
            message="failed",
        )
    ]
    assert derive_validation_status(results, critical_dataset=True) == ValidationStatus.RED


def test_frozen_experiment_manifest_cannot_be_modified() -> None:
    manifest = ExperimentManifest(
        experiment_id="exp-1",
        dataset_version_id="dv-1",
        instrument_master_version="im-v1",
        corporate_action_version="ca-v1",
        universe_version="universe-v1",
        feature_versions_json={},
        backtest_engine_version="disabled-sprint0",
        transaction_cost_model_version="disabled-sprint0",
        slippage_model_version="disabled-sprint0",
        benchmark="NIFTY 50",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        training_period="none-sprint0",
        validation_period="none-sprint0",
        holdout_period="none-sprint0",
        random_seed=42,
        primary_metric="none",
        secondary_metrics_json=[],
        rejection_criteria_json={},
    ).freeze()
    with pytest.raises(ValueError):
        manifest.update_metric("sharpe")


def test_audit_log_has_no_delete_api() -> None:
    audit = AuditLog()
    assert not hasattr(audit, "delete")
    assert not hasattr(audit, "update")


def test_missing_object_storage_fails_safely(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    payload = [{"x": 1}]
    digest = stable_payload_hash(payload)
    store.put_raw_once(f"provider/eod/{digest}.json", payload)
    with pytest.raises(FileExistsError):
        store.put_raw_once(f"provider/eod/{digest}.json", payload)


def test_live_execution_enabled_is_rejected() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        minio_endpoint="http://localhost:9000",
        minio_access_key="x",
        minio_secret_key="y",
        minio_bucket="bucket",
        jwt_secret="secret",
        log_level="INFO",
        live_execution_enabled=True,
    )
    with pytest.raises(ValueError):
        settings.validate_startup()


def test_unverified_corporate_action_cannot_impact_curated_dataset() -> None:
    service = CorporateActionService()
    action = service.create(
        CorporateAction(
            instrument_id="instrument-1",
            action_type=CorporateActionType.SPLIT,
            announcement_time=now_utc(),
            record_date=None,
            ex_date=None,
            effective_date=None,
            ratio_or_amount="1:2",
            currency="INR",
            source_reference="test",
            verification_status=CorporateActionVerificationStatus.AMBER,
            adjustment_method="pending",
            adjustment_version="v1",
        )
    )
    assert service.can_impact_curated_dataset(action.id) is False
