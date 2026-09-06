from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
from typing import Any

from aegis.configuration.settings import Settings
from aegis.data_ingestion.service import InMemoryRepository
from aegis.domain.models import (
    DataProvider,
    ProviderLicense,
    ProviderLicenseStatus,
    ValidationStatus,
)

PROVIDER_STATE_LABELS = {
    "NOT_CONFIGURED": "Provider setup required",
    "CONFIGURED_UNVERIFIED": "Configured - verification pending",
    "HEALTHY": "Connected and healthy",
    "DEGRADED": "Connected with issues",
    "STALE": "Data is stale",
    "BLOCKED_LICENSE": "Blocked by licensing",
    "BLOCKED_VALIDATION": "Blocked by validation",
    "FIXTURE": "Fixture data only",
    "DISABLED": "Provider disabled",
}

DATASET_LABELS = {
    ValidationStatus.GREEN: "Ready",
    ValidationStatus.GREEN_CAUTION: "Ready with caution",
    ValidationStatus.AMBER: "Needs review",
    ValidationStatus.RED: "Blocked",
}


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    provider_name: str
    provider_type: str
    provider_mode: str
    connection_status: str
    health_status: str
    license_status: str
    instrument_master_supported: bool
    historical_eod_supported: bool
    live_quotes_supported: bool
    market_calendar_supported: bool
    corporate_actions_supported: bool
    benchmark_data_supported: bool
    automation_rights: bool
    backtesting_rights: bool
    dashboard_display_rights: bool
    model_training_rights: bool
    data_retention_policy: str
    read_only_enforced: bool
    order_access_enabled: bool
    last_health_check_at: str | None
    last_successful_ingestion_at: str | None
    created_at: str
    updated_at: str


class DataActivationService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: InMemoryRepository,
        providers: dict[str, DataProvider],
        licenses: dict[str, ProviderLicense],
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.providers = providers
        self.licenses = licenses

    def selected_provider(self) -> tuple[DataProvider | None, ProviderLicense | None]:
        configured_name = self.settings.market_data_provider_name
        if configured_name:
            for provider in self.providers.values():
                if provider.name == configured_name:
                    return provider, self.licenses.get(provider.id)
        live = next(
            (
                provider
                for provider in self.providers.values()
                if provider.provider_type == "LIVE_READONLY_MARKET_DATA"
            ),
            None,
        )
        return live, self.licenses.get(live.id) if live else None

    def provider_configured(self) -> bool:
        return self.settings.market_data_provider_configured()

    def provider_state(self, provider_id: str | None = None) -> dict[str, Any]:
        provider, license_ = self.selected_provider()
        if provider_id:
            provider = self.providers.get(provider_id)
            license_ = self.licenses.get(provider_id)

        if not self.settings.market_data_enabled:
            state = "DISABLED"
        elif not self.provider_configured():
            state = "NOT_CONFIGURED"
        elif license_ is None or license_.license_status != ProviderLicenseStatus.APPROVED:
            state = "BLOCKED_LICENSE"
        else:
            health = self.repository.provider_health.get(provider.id if provider else "")
            if health is None:
                state = "CONFIGURED_UNVERIFIED"
            elif not health.get("healthy"):
                state = "DEGRADED"
            else:
                freshness: dict[str, Any] = next(iter(self.repository.data_freshness.values()), {})
                state = "STALE" if freshness.get("status") == "STALE" else "HEALTHY"

        return {
            "state": state,
            "label": PROVIDER_STATE_LABELS[state],
            "provider_id": provider.id if provider else None,
            "provider_name": provider.name if provider else self.settings.market_data_provider_name,
            "provider_configured": self.provider_configured(),
            "read_only": True,
            "order_access_enabled": False,
            "last_updated_at": datetime.now(UTC).isoformat(),
        }

    def capability(self, provider_id: str) -> ProviderCapability:
        provider = self.providers[provider_id]
        license_ = self.licenses.get(provider_id)
        health = self.repository.provider_health.get(provider_id, {})
        latest_run = self.latest_successful_ingestion(provider_id)
        state = self.provider_state(provider_id)
        now = datetime.now(UTC).isoformat()
        license_status = license_.license_status.value if license_ else "NOT_APPROVED"
        return ProviderCapability(
            provider_id=provider_id,
            provider_name=provider.name,
            provider_type=provider.provider_type,
            provider_mode=self.settings.data_source_mode
            if self.provider_configured()
            else "DISABLED",
            connection_status=state["state"],
            health_status="HEALTHY" if health.get("healthy") else state["state"],
            license_status=license_status,
            instrument_master_supported=True,
            historical_eod_supported=self.settings.market_data_eod_enabled,
            live_quotes_supported=self.settings.market_data_quotes_enabled,
            market_calendar_supported=self.settings.market_data_calendar_enabled,
            corporate_actions_supported=self.settings.market_data_corporate_actions_enabled,
            benchmark_data_supported=self.settings.market_data_benchmark_enabled,
            automation_rights=bool(license_ and license_.automation_rights),
            backtesting_rights=bool(license_ and license_.backtesting_rights),
            dashboard_display_rights=bool(license_ and license_.dashboard_display_rights),
            model_training_rights=bool(license_ and license_.model_training_rights),
            data_retention_policy=license_.data_retention_period if license_ else "not-recorded",
            read_only_enforced=True,
            order_access_enabled=False,
            last_health_check_at=health.get("checked_at"),
            last_successful_ingestion_at=latest_run.completed_at.isoformat()
            if latest_run and latest_run.completed_at
            else None,
            created_at=provider.created_at.isoformat(),
            updated_at=now,
        )

    def capabilities(self) -> list[dict[str, Any]]:
        return [asdict(self.capability(provider_id)) for provider_id in self.providers]

    def latest_successful_ingestion(self, provider_id: str | None = None):
        runs = [
            run
            for run in self.repository.ingestion_runs.values()
            if (provider_id is None or run.provider_id == provider_id)
            and run.status in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
        ]
        return max(runs, key=lambda run: run.started_at, default=None)

    def dataset_versions(self) -> list[dict[str, Any]]:
        versions = []
        for version in self.repository.dataset_versions.values():
            eligible = version.validation_status in {
                ValidationStatus.GREEN,
                ValidationStatus.GREEN_CAUTION,
            }
            versions.append(
                {
                    **asdict(version),
                    "validation_label": DATASET_LABELS[version.validation_status],
                    "research_eligibility": "ELIGIBLE_FOR_RESEARCH" if eligible else "BLOCKED",
                    "paper_trading_ready": False,
                    "live_trading_ready": False,
                }
            )
        return versions

    def truth_summary(self) -> dict[str, Any]:
        state = self.provider_state()
        versions = self.dataset_versions()
        eligible_count = sum(
            1 for version in versions if version["research_eligibility"] == "ELIGIBLE_FOR_RESEARCH"
        )
        blockers = self.blockers()
        latest_run = self.latest_successful_ingestion()
        freshness = list(self.repository.data_freshness.values())
        return {
            "data_source": {
                "mode": self.settings.data_source_mode,
                "label": "Read-only data source" if self.provider_configured() else state["label"],
                "state": state["state"],
                "state_label": state["label"],
                "fixture_data_visible": not self.provider_configured(),
                "actual_data_ingested": latest_run is not None and self.provider_configured(),
            },
            "provider": state,
            "latest_ingestion": asdict(latest_run) if latest_run else None,
            "dataset_readiness": {
                "dataset_version_count": len(versions),
                "research_eligible_dataset_count": eligible_count,
                "versions": versions,
            },
            "freshness": freshness,
            "coverage": self.coverage_summary(),
            "blockers": blockers,
            "safety": {
                "live_execution_enabled": self.settings.live_execution_enabled,
                "broker_order_access": self.settings.broker_order_access,
                "live_broker_connection_enabled": self.settings.live_broker_connection_enabled,
                "paper_trading_use_live_data": self.settings.paper_trading_use_live_data,
                "human_approval_required": self.settings.human_approval_required,
                "labels": [
                    "READ_ONLY",
                    "NO_REAL_CAPITAL_DEPLOYED",
                    "BROKER_ORDER_ACCESS_DISABLED",
                    "LIVE_EXECUTION_LOCKED",
                    "PAPER_TRADING_USE_OF_ACTUAL_DATA_DISABLED",
                ],
            },
            "last_updated_at": datetime.now(UTC).isoformat(),
        }

    def blockers(self) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        if not self.provider_configured():
            blockers.append(
                {
                    "code": "PROVIDER_NOT_CONFIGURED",
                    "label": "Provider setup required",
                    "severity": "WARNING",
                }
            )
        _provider, license_ = self.selected_provider()
        if license_ is None or license_.license_status != ProviderLicenseStatus.APPROVED:
            blockers.append(
                {
                    "code": "PROVIDER_LICENSE_NOT_APPROVED",
                    "label": "Provider license not approved",
                    "severity": "CRITICAL",
                }
            )
        if (
            self.settings.broker_order_access
            or self.settings.live_execution_enabled
            or self.settings.paper_trading_use_live_data
        ):
            blockers.append(
                {
                    "code": "SAFETY_GUARD_VIOLATION",
                    "label": "Trading safety guard violated",
                    "severity": "CRITICAL",
                }
            )
        if not self.repository.dataset_versions:
            blockers.append(
                {
                    "code": "NO_ACTUAL_DATASET_VERSION",
                    "label": "No actual dataset version available",
                    "severity": "WARNING",
                }
            )
        return blockers

    def coverage_summary(self) -> dict[str, Any]:
        eod_runs = [
            run
            for run in self.repository.ingestion_runs.values()
            if run.dataset_name == "eod_prices"
        ]
        accepted = sum(run.records_accepted for run in eod_runs)
        rejected = sum(run.records_rejected for run in eod_runs)
        return {
            "controlled_universe_id": "AEGIS_LIQUID_EQUITY_RESEARCH_UNIVERSE_V0",
            "included_instruments": accepted,
            "excluded_instruments": rejected,
            "coverage_status": "NOT_ASSESSED"
            if not eod_runs
            else ("GREEN" if rejected == 0 else "AMBER"),
            "coverage_label": "Not assessed"
            if not eod_runs
            else ("Ready" if rejected == 0 else "Needs review"),
        }
