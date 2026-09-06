from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from aegis.configuration.settings import Settings
from aegis.data_ingestion.service import InMemoryRepository
from aegis.domain.models import (
    DatasetVersion,
    ProviderLicense,
    ProviderLicenseStatus,
    ValidationStatus,
)

HISTORICAL_RESEARCH_LABELS = [
    "ACTUAL_HISTORICAL_RESEARCH_ONLY",
    "NOT_VALIDATED",
    "NOT_PAPER_TRADING_ELIGIBLE",
    "NOT_LIVE_TRADING_ELIGIBLE",
    "NO_REAL_CAPITAL_DEPLOYED",
    "NO_PAPER_TRADING",
    "NO_LIVE_EXECUTION",
    "NO_HOLDINGS_MUTATION",
    "LINEAGE_REQUIRED",
]

ELIGIBLE_VALIDATION_STATUSES = {
    ValidationStatus.GREEN,
    ValidationStatus.GREEN_CAUTION,
}


class DataOrigin(str, Enum):
    ACTUAL_PROVIDER_DATA = "ACTUAL_PROVIDER_DATA"
    APPROVED_FILE_IMPORT = "APPROVED_FILE_IMPORT"
    FIXTURE_DATA = "FIXTURE_DATA"
    TEST_DATA = "TEST_DATA"


class FixtureIsolationGuard:
    def assert_actual_research_origin(self, origins: set[str]) -> None:
        if len(origins) > 1:
            raise ValueError("MIXED_DATA_ORIGIN_NOT_ALLOWED")
        origin = next(iter(origins), None)
        if origin not in {
            DataOrigin.ACTUAL_PROVIDER_DATA.value,
            DataOrigin.APPROVED_FILE_IMPORT.value,
        }:
            raise ValueError("FIXTURE_DATA_NOT_ALLOWED")


class ActualResearchEligibilityGuard:
    def __init__(self, service: HistoricalResearchActivationService) -> None:
        self.service = service

    def assert_dataset_eligible(self, dataset_version_id: str) -> None:
        version = self.service.repository.dataset_versions.get(dataset_version_id)
        if version is None:
            raise ValueError("DATASET_VERSION_NOT_FOUND")
        blockers = self.service.dataset_blockers(version) + self.service.system_blockers()
        if blockers:
            raise ValueError(",".join(blocker.code for blocker in blockers))


@dataclass(frozen=True)
class ResearchActivationBlocker:
    code: str
    label: str
    severity: str
    remediation: str


@dataclass(frozen=True)
class ResearchActivationManifest:
    activation_id: str
    dataset_version_id: str | None
    status: str
    status_label: str
    research_mode: str
    data_source_mode: str
    labels: list[str]
    blockers: list[ResearchActivationBlocker]
    paper_trading_ready: bool = False
    live_trading_ready: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class HistoricalResearchActivationService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: InMemoryRepository,
        licenses: dict[str, ProviderLicense],
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.licenses = licenses
        self.fixture_guard = FixtureIsolationGuard()

    def status(self) -> dict[str, Any]:
        eligible = self.eligible_dataset_versions()
        blockers = self.system_blockers()
        if not self.settings.market_data_provider_configured():
            blockers.append(
                ResearchActivationBlocker(
                    code="PROVIDER_NOT_CONFIGURED",
                    label="Provider or approved file import is not configured",
                    severity="CRITICAL",
                    remediation="Configure a read-only provider or approved file import.",
                )
            )
        if not eligible:
            for version in self.repository.dataset_versions.values():
                blockers.extend(self.dataset_blockers(version))
        if not self.repository.dataset_versions:
            blockers.append(
                ResearchActivationBlocker(
                    code="NO_DATASET_VERSION",
                    label="No dataset version exists for actual historical research",
                    severity="CRITICAL",
                    remediation="Ingest governed historical EOD data.",
                )
            )
        if eligible and not blockers:
            status = "ELIGIBLE_FOR_HISTORICAL_RESEARCH"
            label = "Historical research ready"
        elif not self.settings.market_data_provider_configured():
            status = "PROVIDER_SETUP_REQUIRED"
            label = "Provider or licensed file required"
        else:
            status = "NO_ELIGIBLE_HISTORICAL_DATASET"
            label = "No eligible historical dataset"

        return {
            "research_readiness_id": f"research-readiness-{uuid4()}",
            "dataset_version_id": eligible[0]["dataset_version_id"] if eligible else None,
            "universe_version_id": "AEGIS_LIQUID_EQUITY_RESEARCH_UNIVERSE_V0",
            "benchmark_version_id": "BENCHMARK_DEFINITION_PENDING",
            "instrument_master_version_id": eligible[0]["instrument_master_version"]
            if eligible
            else "instrument-master.v1",
            "corporate_action_version_id": eligible[0]["corporate_action_version"]
            if eligible
            else "corporate-actions.v1",
            "feature_readiness_status": "BLOCKED" if not eligible else "READY",
            "cost_schedule_readiness": "CONFIGURED",
            "slippage_model_readiness": "CONFIGURED",
            "settlement_model_readiness": "CONFIGURED",
            "risk_profile_readiness": "CONFIGURED",
            "overall_status": status
            if status in {"BLOCKED", "READY_WITH_CAUTION"}
            else ("READY_FOR_ACTUAL_RESEARCH" if eligible and not blockers else "BLOCKED"),
            "status": status,
            "status_label": label,
            "research_mode": "ACTUAL_HISTORICAL_RESEARCH_ONLY",
            "data_source_mode": self.settings.data_source_mode,
            "eligible_dataset_count": len(eligible),
            "dataset_version_count": len(self.repository.dataset_versions),
            "paper_trading_ready": False,
            "live_trading_ready": False,
            "labels": HISTORICAL_RESEARCH_LABELS,
            "eligible_datasets": eligible,
            "reason_codes": [blocker.code for blocker in blockers],
            "blockers": [asdict(blocker) for blocker in blockers],
            "checked_at": datetime.now(UTC).isoformat(),
            "correlation_id": f"readiness-{uuid4()}",
            "last_updated_at": datetime.now(UTC).isoformat(),
        }

    def eligible_dataset_versions(self) -> list[dict[str, Any]]:
        eligible: list[dict[str, Any]] = []
        for version in self.repository.dataset_versions.values():
            blockers = self.dataset_blockers(version)
            if blockers:
                continue
            license_ = self.licenses[version.provider_id]
            eligible.append(
                {
                    "dataset_version_id": version.id,
                    "dataset_id": version.dataset_id,
                    "provider_id": version.provider_id,
                    "data_origin": self.data_origin(version.id),
                    "schema_version": version.schema_version,
                    "raw_snapshot_hash": version.raw_snapshot_hash,
                    "transformation_version": version.transformation_version,
                    "instrument_master_version": version.instrument_master_version,
                    "corporate_action_version": version.corporate_action_version,
                    "validation_status": version.validation_status.value,
                    "quality_score": version.quality_score,
                    "lineage_record_exists": version.lineage_record_exists,
                    "license_status": license_.license_status.value,
                    "backtesting_rights": license_.backtesting_rights,
                    "dashboard_display_rights": license_.dashboard_display_rights,
                    "paper_trading_ready": False,
                    "live_trading_ready": False,
                    "classification": "ACTUAL_HISTORICAL_RESEARCH_ONLY",
                }
            )
        return eligible

    def dataset_diagnostics(self) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        for version in self.repository.dataset_versions.values():
            diagnostics.append(
                {
                    "dataset_version_id": version.id,
                    "dataset_id": version.dataset_id,
                    "provider_id": version.provider_id,
                    "data_origin": self.data_origin(version.id),
                    "validation_status": version.validation_status.value,
                    "quality_score": version.quality_score,
                    "blockers": [asdict(blocker) for blocker in self.dataset_blockers(version)],
                }
            )
        return diagnostics

    def dataset_blockers(self, version: DatasetVersion) -> list[ResearchActivationBlocker]:
        blockers: list[ResearchActivationBlocker] = []
        origin = self.data_origin(version.id)
        try:
            self.fixture_guard.assert_actual_research_origin({origin})
        except ValueError as exc:
            blockers.append(
                ResearchActivationBlocker(
                    code=str(exc),
                    label="Dataset origin is not eligible for actual historical research",
                    severity="CRITICAL",
                    remediation="Use only ACTUAL_PROVIDER_DATA or APPROVED_FILE_IMPORT dataset versions.",
                )
            )
        if version.validation_status not in ELIGIBLE_VALIDATION_STATUSES:
            blockers.append(
                ResearchActivationBlocker(
                    code="DATASET_VALIDATION_NOT_GREEN",
                    label="Dataset validation is not GREEN or GREEN_CAUTION",
                    severity="CRITICAL",
                    remediation="Fix data-quality failures and create a new dataset version.",
                )
            )
        if not version.lineage_record_exists:
            blockers.append(
                ResearchActivationBlocker(
                    code="MISSING_LINEAGE",
                    label="Dataset lineage record is missing",
                    severity="CRITICAL",
                    remediation="Attach raw, normalized, curated, and validation lineage.",
                )
            )
        if not version.raw_snapshot_hash or version.raw_snapshot_hash.startswith("fixture-"):
            blockers.append(
                ResearchActivationBlocker(
                    code="RAW_EVIDENCE_NOT_REAL",
                    label="Immutable real raw snapshot hash is missing",
                    severity="CRITICAL",
                    remediation="Ingest provider or licensed-file data into raw immutable storage.",
                )
            )
        elif not self.raw_object_linked(version.raw_snapshot_hash):
            blockers.append(
                ResearchActivationBlocker(
                    code="MISSING_RAW_OBJECT_LINKAGE",
                    label="Dataset version is not linked to an immutable raw object",
                    severity="CRITICAL",
                    remediation="Persist the raw source object and link its content hash.",
                )
            )

        license_ = self.licenses.get(version.provider_id)
        if license_ is None:
            blockers.append(
                ResearchActivationBlocker(
                    code="PROVIDER_LICENSE_MISSING",
                    label="Provider license is missing",
                    severity="CRITICAL",
                    remediation="Register approved provider/license rights before research use.",
                )
            )
        elif license_.license_status != ProviderLicenseStatus.APPROVED:
            blockers.append(
                ResearchActivationBlocker(
                    code="PROVIDER_LICENSE_NOT_APPROVED",
                    label="Provider license is not approved",
                    severity="CRITICAL",
                    remediation="Complete legal/provider review and mark license approved.",
                )
            )
        elif not license_.backtesting_rights:
            blockers.append(
                ResearchActivationBlocker(
                    code="BACKTESTING_RIGHTS_MISSING",
                    label="Provider license does not allow backtesting",
                    severity="CRITICAL",
                    remediation="Obtain explicit historical research/backtesting rights.",
                )
            )
        health = self.repository.provider_health.get(version.provider_id)
        if health is None or not health.get("healthy", False):
            blockers.append(
                ResearchActivationBlocker(
                    code="PROVIDER_HEALTH_NOT_VERIFIED",
                    label="Provider health has not been verified in read-only mode",
                    severity="CRITICAL",
                    remediation="Run a provider health check after configuring the provider.",
                )
            )

        return blockers

    def data_origin(self, dataset_version_id: str) -> str:
        return self.repository.dataset_origins.get(
            dataset_version_id, DataOrigin.FIXTURE_DATA.value
        )

    def raw_object_linked(self, raw_snapshot_hash: str) -> bool:
        return any(
            raw.content_hash == raw_snapshot_hash for raw in self.repository.raw_objects.values()
        )

    def system_blockers(self) -> list[ResearchActivationBlocker]:
        blockers: list[ResearchActivationBlocker] = []
        # paper_trading_use_live_data deliberately excluded here too -- see
        # the matching comment in data_activation/service.py's blockers().
        if self.settings.live_execution_enabled or self.settings.broker_order_access:
            blockers.append(
                ResearchActivationBlocker(
                    code="TRADING_SAFETY_GUARD_VIOLATION",
                    label="Trading safety flags must remain disabled",
                    severity="CRITICAL",
                    remediation="Set live execution and broker access to false.",
                )
            )
        return blockers

    def activate_historical_dataset(
        self, dataset_version_id: str | None = None
    ) -> ResearchActivationManifest:
        eligible = self.eligible_dataset_versions()
        system_blockers = self.system_blockers()
        selected = None
        if dataset_version_id:
            selected = next(
                (
                    version
                    for version in self.repository.dataset_versions.values()
                    if version.id == dataset_version_id
                ),
                None,
            )
            if selected is None:
                blockers = [
                    ResearchActivationBlocker(
                        code="DATASET_VERSION_NOT_FOUND",
                        label="Dataset version was not found",
                        severity="CRITICAL",
                        remediation="Submit an existing dataset version identifier.",
                    )
                ]
            else:
                blockers = self.dataset_blockers(selected) + system_blockers
        else:
            selected_id = (
                eligible[0]["dataset_version_id"] if eligible and not system_blockers else None
            )
            selected = self.repository.dataset_versions.get(selected_id) if selected_id else None
            blockers = system_blockers
            if selected is None:
                blockers = blockers + [
                    ResearchActivationBlocker(
                        code="NO_ELIGIBLE_HISTORICAL_DATASET",
                        label="No eligible real historical dataset is available",
                        severity="CRITICAL",
                        remediation="Ingest licensed historical EOD data and pass quality gates.",
                    )
                ]

        if blockers:
            return ResearchActivationManifest(
                activation_id=f"research-activation-{uuid4()}",
                dataset_version_id=selected.id if selected else dataset_version_id,
                status="BLOCKED",
                status_label="Historical research activation blocked",
                research_mode="ACTUAL_HISTORICAL_RESEARCH_ONLY",
                data_source_mode=self.settings.data_source_mode,
                labels=HISTORICAL_RESEARCH_LABELS,
                blockers=blockers,
            )

        if selected is None:
            raise ValueError("Research activation selected no dataset without blockers.")

        return ResearchActivationManifest(
            activation_id=f"research-activation-{uuid4()}",
            dataset_version_id=selected.id,
            status="ACTIVE",
            status_label="Historical research activated",
            research_mode="ACTUAL_HISTORICAL_RESEARCH_ONLY",
            data_source_mode=self.settings.data_source_mode,
            labels=HISTORICAL_RESEARCH_LABELS,
            blockers=[],
        )


ActualHistoricalResearchEligibilityService = HistoricalResearchActivationService
