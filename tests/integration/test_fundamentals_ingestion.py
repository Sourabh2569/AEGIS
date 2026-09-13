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

    # This is also what makes compute_ttm_eps possible at all -- one real
    # ingested quarter is recorded under its own period_to, not just as
    # "the latest".
    history = service.repository.fundamentals_history["RELIANCE"]
    assert set(history.keys()) == {"2024-12-31"}
    assert history["2024-12-31"]["revenue_from_operations"] == "1282600000000.00"


class _TwoQuarterFakeProvider:
    """Minimal test-only provider isolating exactly one thing:
    ingest_fundamentals's history bookkeeping across repeated real runs --
    not a claim about any real company's financials (the quarters below
    are synthetic, unlike every other fixture-backed test in this file)."""

    name = "fake-two-quarter"
    dataset_origin = "TEST_DATA"

    def __init__(self, records: list[dict[str, str]]) -> None:
        self._records = records
        self._license = ProviderLicense(
            provider_id="fake-two-quarter",
            license_status=ProviderLicenseStatus.APPROVED,
            permitted_use="test",
            automation_rights=True,
            backtesting_rights=False,
            model_training_rights=False,
            dashboard_display_rights=True,
            data_retention_period="test",
        )

    def get_license_status(self) -> ProviderLicense:
        return self._license

    def fetch_fundamentals(self):
        from aegis.provider_adapters.base import ProviderResponseEnvelope

        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_fundamentals",
            schema_version="fundamentals.v1",
            source_reference="test://fake",
            payload=self._records,
        )


def test_ingest_fundamentals_accumulates_real_history_across_separate_runs(
    tmp_path: Path,
) -> None:
    """Two separate real ingestion runs for the same symbol, one real
    quarter each -- fundamentals_history must accumulate both (keyed by
    period_to), while latest_fundamentals keeps reflecting only the most
    recent one. This is the exact mechanism compute_ttm_eps depends on to
    ever see 4 real quarters."""
    service = _service(tmp_path)
    q1 = {
        "symbol": "RELIANCE",
        "period_from": "2024-04-01",
        "period_to": "2024-06-30",
        "basic_eps": "5.00",
    }
    q2 = {
        "symbol": "RELIANCE",
        "period_from": "2024-07-01",
        "period_to": "2024-09-30",
        "basic_eps": "6.00",
    }
    service.ingest_fundamentals(
        provider=_TwoQuarterFakeProvider([q1]),
        provider_id="fake-two-quarter",
        dataset_id="fundamentals",
    )
    service.ingest_fundamentals(
        provider=_TwoQuarterFakeProvider([q2]),
        provider_id="fake-two-quarter",
        dataset_id="fundamentals",
    )

    history = service.repository.fundamentals_history["RELIANCE"]
    assert set(history.keys()) == {"2024-06-30", "2024-09-30"}
    assert history["2024-06-30"]["basic_eps"] == "5.00"
    assert history["2024-09-30"]["basic_eps"] == "6.00"
    assert service.repository.latest_fundamentals["RELIANCE"]["period_to"] == "2024-09-30"


def test_ingest_fundamentals_keeps_latest_pointing_at_the_true_latest_out_of_order(
    tmp_path: Path,
) -> None:
    """Real bug found via live use: a multi-quarter manual-import batch is
    not guaranteed to arrive in chronological order (the Cockpit's
    multi-file upload processes files in whatever order the browser's file
    list gives them). latest_fundamentals used to just take whatever the
    most recent ingest call happened to process -- ingesting an OLDER
    quarter after a NEWER one already existed silently made the "latest"
    convenience pointer stale, even though fundamentals_history (and so
    compute_ttm_eps) stayed correct throughout."""
    service = _service(tmp_path)
    newer = {
        "symbol": "RELIANCE",
        "period_from": "2024-07-01",
        "period_to": "2024-09-30",
        "basic_eps": "6.00",
    }
    older = {
        "symbol": "RELIANCE",
        "period_from": "2024-04-01",
        "period_to": "2024-06-30",
        "basic_eps": "5.00",
    }
    service.ingest_fundamentals(
        provider=_TwoQuarterFakeProvider([newer]),
        provider_id="fake-two-quarter",
        dataset_id="fundamentals",
    )
    # The older quarter arrives second, e.g. filling a gap -- must not
    # clobber the newer one that's already on file.
    service.ingest_fundamentals(
        provider=_TwoQuarterFakeProvider([older]),
        provider_id="fake-two-quarter",
        dataset_id="fundamentals",
    )

    assert service.repository.latest_fundamentals["RELIANCE"]["period_to"] == "2024-09-30"
    assert service.repository.latest_fundamentals["RELIANCE"]["basic_eps"] == "6.00"
