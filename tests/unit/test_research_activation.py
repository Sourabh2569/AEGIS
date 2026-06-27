from __future__ import annotations

from aegis.configuration.settings import Settings
from aegis.data_ingestion.service import InMemoryRepository
from aegis.domain.models import (
    DatasetVersion,
    ProviderLicense,
    ProviderLicenseStatus,
    RawDataObject,
    ValidationStatus,
)
from aegis.research_activation.jobs import (
    ActualResearchJob,
    ActualResearchJobRunner,
    ActualResearchJobType,
)
from aegis.research_activation.service import HistoricalResearchActivationService


def approved_license(provider_id: str) -> ProviderLicense:
    return ProviderLicense(
        provider_id=provider_id,
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="Historical research and dashboard display",
        automation_rights=False,
        backtesting_rights=True,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="local-governed-retention",
        legal_review_status="APPROVED",
    )


def dataset_version(
    *,
    raw_snapshot_hash: str = "sha256:real-provider-snapshot",
    validation_status: ValidationStatus = ValidationStatus.GREEN,
    lineage_record_exists: bool = True,
) -> DatasetVersion:
    return DatasetVersion(
        dataset_id="eod-prices",
        provider_id="provider-1",
        schema_version="eod_ohlcv.v1",
        raw_snapshot_hash=raw_snapshot_hash,
        transformation_version="normalized.v1",
        instrument_master_version="instrument-master.v1",
        corporate_action_version="corporate-actions.v1",
        validation_status=validation_status,
        quality_score=99.0,
        lineage_record_exists=lineage_record_exists,
        id="dataset-version-real-1",
    )


def service(repository: InMemoryRepository) -> HistoricalResearchActivationService:
    return HistoricalResearchActivationService(
        settings=Settings.from_env(),
        repository=repository,
        licenses={"provider-1": approved_license("provider-1")},
    )


def test_fixture_dataset_is_not_real_historical_research_eligible() -> None:
    repository = InMemoryRepository()
    repository.dataset_versions["dataset-version-1"] = dataset_version(
        raw_snapshot_hash="fixture-hash"
    )
    repository.dataset_origins["dataset-version-1"] = "FIXTURE_DATA"

    status = service(repository).status()

    assert status["eligible_dataset_count"] == 0
    assert status["status"] == "PROVIDER_SETUP_REQUIRED"
    diagnostics = service(repository).dataset_diagnostics()
    assert any(
        blocker["code"] == "FIXTURE_DATA_NOT_ALLOWED" for blocker in diagnostics[0]["blockers"]
    )


def test_validated_real_dataset_can_activate_research_only_manifest() -> None:
    repository = InMemoryRepository()
    repository.dataset_versions["dataset-version-real-1"] = dataset_version()
    repository.dataset_origins["dataset-version-real-1"] = "ACTUAL_PROVIDER_DATA"
    repository.raw_objects["raw-1"] = RawDataObject(
        provider_id="provider-1",
        source_reference="provider://historical/eod",
        content_hash="sha256:real-provider-snapshot",
        schema_version="eod_ohlcv.v1",
        ingestion_run_id="ingestion-1",
        storage_uri="file://work/object_store/raw/real-provider-snapshot.json",
        processing_status="IMMUTABLE",
    )
    repository.provider_health["provider-1"] = {"healthy": True}

    manifest = service(repository).activate_historical_dataset("dataset-version-real-1")

    assert manifest.status == "ACTIVE"
    assert manifest.dataset_version_id == "dataset-version-real-1"
    assert manifest.paper_trading_ready is False
    assert manifest.live_trading_ready is False
    assert "ACTUAL_HISTORICAL_RESEARCH_ONLY" in manifest.labels


def test_red_or_missing_lineage_dataset_blocks_activation() -> None:
    repository = InMemoryRepository()
    repository.dataset_versions["dataset-version-real-1"] = dataset_version(
        validation_status=ValidationStatus.RED,
        lineage_record_exists=False,
    )
    repository.dataset_origins["dataset-version-real-1"] = "ACTUAL_PROVIDER_DATA"
    repository.raw_objects["raw-1"] = RawDataObject(
        provider_id="provider-1",
        source_reference="provider://historical/eod",
        content_hash="sha256:real-provider-snapshot",
        schema_version="eod_ohlcv.v1",
        ingestion_run_id="ingestion-1",
        storage_uri="file://work/object_store/raw/real-provider-snapshot.json",
        processing_status="IMMUTABLE",
    )
    repository.provider_health["provider-1"] = {"healthy": True}

    manifest = service(repository).activate_historical_dataset("dataset-version-real-1")

    assert manifest.status == "BLOCKED"
    assert {blocker.code for blocker in manifest.blockers} == {
        "DATASET_VALIDATION_NOT_GREEN",
        "MISSING_LINEAGE",
    }


def test_blocked_manifest_uses_actual_historical_classification() -> None:
    repository = InMemoryRepository()
    repository.dataset_versions["dataset-version-1"] = dataset_version(
        raw_snapshot_hash="fixture-hash"
    )
    repository.dataset_origins["dataset-version-1"] = "FIXTURE_DATA"

    manifest = service(repository).activate_historical_dataset("dataset-version-1")

    assert manifest.status == "BLOCKED"
    assert manifest.research_mode == "ACTUAL_HISTORICAL_RESEARCH_ONLY"


def test_actual_research_job_runner_is_idempotent_and_fail_closed() -> None:
    repository = InMemoryRepository()
    research_service = service(repository)
    runner = ActualResearchJobRunner(research_service)
    job = ActualResearchJob(
        job_type=ActualResearchJobType.READINESS,
        correlation_id="correlation-1",
        dataset_version_id="dataset-version-1",
    )

    first = runner.enqueue(job)
    duplicate = runner.enqueue(job)
    completed = runner.run_once()

    assert first.job_id == duplicate.job_id
    assert completed is not None
    assert completed.status == "BLOCKED"
    assert completed.result["paper_trading_activated"] is False
    assert completed.result["live_execution_activated"] is False
