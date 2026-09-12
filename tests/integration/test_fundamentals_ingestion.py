from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.audit.service import AuditLog
from aegis.data_ingestion.service import InMemoryRepository, LocalObjectStore, ProviderIngestionService
from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.fundamentals_nse_provider import NseFundamentalsProvider

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "xbrl"
    / "reliance_q3_fy2025_standalone.xml"
)

DISCOVERY_URL = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&period=Quarterly&symbol=RELIANCE"
)
XBRL_URL = "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml"

DISCOVERY_RESPONSE = json.dumps(
    [
        {
            "companyName": "Reliance Industries Limited",
            "consolidated": "Non-Consolidated",
            "filingDate": "16-Jan-2025 20:20",
            "fromDate": "01-Oct-2024",
            "toDate": "31-Dec-2024",
            "isin": "INE002A01018",
            "symbol": "RELIANCE",
            "xbrl": XBRL_URL,
        }
    ]
).encode("utf-8")


class FakeHttpClient:
    def __init__(self) -> None:
        self._responses = {DISCOVERY_URL: DISCOVERY_RESPONSE, XBRL_URL: FIXTURE_PATH.read_bytes()}

    def get(self, url: str) -> bytes:
        return self._responses[url]


def _rejected_provider() -> NseFundamentalsProvider:
    return NseFundamentalsProvider(http_client=FakeHttpClient(), symbols=["RELIANCE"], configured=True)


def _approved_provider() -> NseFundamentalsProvider:
    approved_license = ProviderLicense(
        provider_id="fundamentals-nse",
        license_status=ProviderLicenseStatus.APPROVED,
        permitted_use="test",
        automation_rights=True,
        backtesting_rights=False,
        model_training_rights=False,
        dashboard_display_rights=True,
        data_retention_period="test",
    )
    return NseFundamentalsProvider(
        http_client=FakeHttpClient(), symbols=["RELIANCE"], license_=approved_license, configured=True
    )


def _service(tmp_path: Path) -> ProviderIngestionService:
    return ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path),
        repository=InMemoryRepository(),
        audit_log=AuditLog(),
    )


def test_ingest_fundamentals_is_blocked_because_nse_tos_rejects_automation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    provider = _rejected_provider()
    assert provider.get_license_status().license_status == ProviderLicenseStatus.REJECTED
    with pytest.raises(PermissionError):
        service.ingest_fundamentals(
            provider=provider, provider_id="fundamentals-nse", dataset_id="fundamentals"
        )
    # Refusing must happen before any real HTTP call -- nothing should have
    # been written anywhere.
    assert service.repository.latest_fundamentals == {}


def test_ingest_fundamentals_real_flow_once_approved(tmp_path: Path) -> None:
    service = _service(tmp_path)
    provider = _approved_provider()
    run = service.ingest_fundamentals(
        provider=provider, provider_id="fundamentals-nse", dataset_id="fundamentals"
    )
    assert run.records_accepted == 1
    assert run.records_rejected == 0

    stored = service.repository.latest_fundamentals["RELIANCE"]
    assert stored["revenue_from_operations"] == "1282600000000.00"
    assert stored["profit_for_period"] == "87210000000.00"

    # Real dataset-level provenance, same discipline as EOD prices.
    [dataset_version] = service.repository.dataset_versions.values()
    assert dataset_version.raw_snapshot_hash
    assert not dataset_version.raw_snapshot_hash.startswith("fixture-")
    origin = service.repository.dataset_origins[dataset_version.id]
    assert origin == "ACTUAL_PROVIDER_DATA"
