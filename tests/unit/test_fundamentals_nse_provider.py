from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.fundamentals_nse_provider import (
    FundamentalsFilingRef,
    NseFundamentalsProvider,
    find_latest_standalone_filing,
    parse_xbrl_fundamentals,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "xbrl"
    / "reliance_q3_fy2025_standalone.xml"
)


class FakeHttpClient:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.requested_urls.append(url)
        if url not in self._responses:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return self._responses[url]


DISCOVERY_URL = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&period=Quarterly&symbol=RELIANCE"
)

# A trimmed real shape of what NSE's discovery API actually returns (matches
# the live response captured this session, field-for-field).
DISCOVERY_RESPONSE = b"""
[
  {
    "companyName": "Reliance Industries Limited",
    "consolidated": "Non-Consolidated",
    "filingDate": "16-Jan-2025 20:20",
    "fromDate": "01-Oct-2024",
    "toDate": "31-Dec-2024",
    "isin": "INE002A01018",
    "symbol": "RELIANCE",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml"
  },
  {
    "companyName": "Reliance Industries Limited",
    "consolidated": "Consolidated",
    "filingDate": "16-Jan-2025 20:15",
    "fromDate": "01-Oct-2024",
    "toDate": "31-Dec-2024",
    "isin": "INE002A01018",
    "symbol": "RELIANCE",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/consolidated-not-used.xml"
  },
  {
    "companyName": "Reliance Industries Limited",
    "consolidated": "Non-Consolidated",
    "filingDate": "15-Oct-2024 18:00",
    "fromDate": "01-Jul-2024",
    "toDate": "30-Sep-2024",
    "isin": "INE002A01018",
    "symbol": "RELIANCE",
    "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/older-quarter-not-used.xml"
  }
]
"""


def test_find_latest_standalone_filing_picks_newest_non_consolidated() -> None:
    records = json.loads(DISCOVERY_RESPONSE)
    filing = find_latest_standalone_filing(records, symbol="RELIANCE")
    assert filing is not None
    assert filing.xbrl_url == (
        "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml"
    )
    assert filing.period_from == "2024-10-01"
    assert filing.period_to == "2024-12-31"


def test_find_latest_standalone_filing_returns_none_when_no_candidates() -> None:
    assert find_latest_standalone_filing([], symbol="RELIANCE") is None
    only_consolidated = [
        {
            "consolidated": "Consolidated",
            "xbrl": "https://example.com/x.xml",
            "filingDate": "01-Jan-2025 00:00",
            "fromDate": "01-Oct-2024",
            "toDate": "31-Dec-2024",
        }
    ]
    assert find_latest_standalone_filing(only_consolidated, symbol="RELIANCE") is None


def test_parse_xbrl_fundamentals_reads_real_captured_filing() -> None:
    xml_bytes = FIXTURE_PATH.read_bytes()
    values = parse_xbrl_fundamentals(xml_bytes, period_from="2024-10-01", period_to="2024-12-31")
    # Real values confirmed against the live filing this session -- a
    # regression here means the parser stopped reading the real quarter.
    assert values["revenue_from_operations"] == "1282600000000.00"
    assert values["profit_for_period"] == "87210000000.00"


def test_parse_xbrl_fundamentals_returns_empty_for_unmatched_period() -> None:
    xml_bytes = FIXTURE_PATH.read_bytes()
    values = parse_xbrl_fundamentals(xml_bytes, period_from="1999-01-01", period_to="1999-03-31")
    assert values == {}


def test_fetch_fundamentals_end_to_end_against_fake_client() -> None:
    xml_bytes = FIXTURE_PATH.read_bytes()
    client = FakeHttpClient(
        {
            DISCOVERY_URL: DISCOVERY_RESPONSE,
            "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml": xml_bytes,
        }
    )
    provider = NseFundamentalsProvider(
        http_client=client, symbols=["RELIANCE"], configured=True, min_request_interval_seconds=0
    )
    envelope = provider.fetch_fundamentals()
    assert envelope.metadata["skipped_symbols"] == {}
    assert len(envelope.payload) == 1
    record = envelope.payload[0]
    assert record["symbol"] == "RELIANCE"
    assert record["revenue_from_operations"] == "1282600000000.00"
    assert record["source_xbrl_url"].endswith("16012025082021.xml")
    # Only the discovery call + the one matched XBRL doc -- never the two
    # unused ones in DISCOVERY_RESPONSE.
    assert client.requested_urls == [
        DISCOVERY_URL,
        "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_117298_1348254_16012025082021.xml",
    ]


IT_SECTOR_FIXTURES = {
    "TCS": ("tcs_q3_fy2025_standalone.xml", "538830000000.00", "118320000000.00"),
    "HCLTECH": ("hcltech_q3_fy2025_standalone.xml", "132740000000.00", "35260000000.00"),
    "INFY": ("infy_q3_fy2025_standalone.xml", "349150000000.00", "63580000000.00"),
    "TECHM": ("techm_q3_fy2025_standalone.xml", "111762000000.00", "8583000000.00"),
    "WIPRO": ("wipro_q3_fy2025_standalone.xml", "168030000000.00", "28121000000.00"),
}


def _discovery_response_for(symbol: str, xbrl_url: str) -> bytes:
    return json.dumps(
        [
            {
                "companyName": symbol,
                "consolidated": "Non-Consolidated",
                "filingDate": "17-Jan-2025 16:17",
                "fromDate": "01-Oct-2024",
                "toDate": "31-Dec-2024",
                "isin": "TEST",
                "symbol": symbol,
                "xbrl": xbrl_url,
            }
        ]
    ).encode("utf-8")


def test_fetch_fundamentals_across_a_real_multi_company_sector() -> None:
    """Verifies the parser generalizes across 5 real IT-sector filings, not
    just the one Reliance filing it was originally built against -- each
    fixture is a real captured quarterly filing for a different company."""
    responses: dict[str, bytes] = {}
    for symbol, (filename, _revenue, _profit) in IT_SECTOR_FIXTURES.items():
        discovery_url = (
            "https://www.nseindia.com/api/corporates-financial-results"
            f"?index=equities&period=Quarterly&symbol={symbol}"
        )
        xbrl_url = f"https://nsearchives.nseindia.com/corporate/xbrl/test-{symbol}.xml"
        responses[discovery_url] = _discovery_response_for(symbol, xbrl_url)
        responses[xbrl_url] = (
            Path(__file__).resolve().parents[1] / "fixtures" / "xbrl" / filename
        ).read_bytes()

    provider = NseFundamentalsProvider(
        http_client=FakeHttpClient(responses),
        symbols=list(IT_SECTOR_FIXTURES.keys()),
        configured=True,
        min_request_interval_seconds=0,
    )
    envelope = provider.fetch_fundamentals()
    assert envelope.metadata["skipped_symbols"] == {}
    assert len(envelope.payload) == 5
    by_symbol = {record["symbol"]: record for record in envelope.payload}
    for symbol, (_filename, revenue, profit) in IT_SECTOR_FIXTURES.items():
        assert by_symbol[symbol]["revenue_from_operations"] == revenue
        assert by_symbol[symbol]["profit_for_period"] == profit


def test_one_companys_failure_does_not_abort_the_rest_of_the_batch() -> None:
    good_xbrl_url = "https://nsearchives.nseindia.com/corporate/xbrl/good.xml"
    good_discovery_url = (
        "https://www.nseindia.com/api/corporates-financial-results"
        "?index=equities&period=Quarterly&symbol=GOOD"
    )
    client = FakeHttpClient(
        {
            good_discovery_url: _discovery_response_for("GOOD", good_xbrl_url),
            good_xbrl_url: FIXTURE_PATH.read_bytes(),
            # BROKEN's discovery URL is deliberately absent from responses --
            # FakeHttpClient.get() raises AssertionError for it, simulating a
            # real network/server failure for just that one company.
        }
    )
    provider = NseFundamentalsProvider(
        http_client=client,
        symbols=["BROKEN", "GOOD"],
        configured=True,
        min_request_interval_seconds=0,
    )
    envelope = provider.fetch_fundamentals()
    assert len(envelope.payload) == 1
    assert envelope.payload[0]["symbol"] == "GOOD"
    assert "BROKEN" in envelope.metadata["skipped_symbols"]
    assert "AssertionError" in envelope.metadata["skipped_symbols"]["BROKEN"]


def test_requests_are_throttled_between_companies() -> None:
    good_xbrl_url = "https://nsearchives.nseindia.com/corporate/xbrl/good.xml"
    good_discovery_url = (
        "https://www.nseindia.com/api/corporates-financial-results"
        "?index=equities&period=Quarterly&symbol=GOOD"
    )
    client = FakeHttpClient({good_discovery_url: _discovery_response_for("GOOD", good_xbrl_url)})
    provider = NseFundamentalsProvider(
        http_client=client,
        symbols=["GOOD"],
        configured=True,
        min_request_interval_seconds=0.05,
    )
    started = time.monotonic()
    provider.fetch_fundamentals()
    elapsed = time.monotonic() - started
    # Two real requests (discovery, then the XBRL doc -- even though the
    # second one 404s via FakeHttpClient's AssertionError, throttling already
    # happened before that failure) at >=0.05s apart must take >=0.05s total.
    assert elapsed >= 0.05


def test_fetch_fundamentals_refuses_when_not_configured() -> None:
    provider = NseFundamentalsProvider(http_client=FakeHttpClient({}), configured=False)
    with pytest.raises(PermissionError):
        provider.fetch_fundamentals()


def test_dataset_origin_is_honest_about_configuration() -> None:
    unconfigured = NseFundamentalsProvider(http_client=FakeHttpClient({}), configured=False)
    assert unconfigured.dataset_origin == "FIXTURE_DATA"
    configured = NseFundamentalsProvider(http_client=FakeHttpClient({}), configured=True)
    assert configured.dataset_origin == "ACTUAL_PROVIDER_DATA"


def test_license_defaults_to_pending() -> None:
    provider = NseFundamentalsProvider(http_client=FakeHttpClient({}))
    license_ = provider.get_license_status()
    assert license_ is not None
    assert license_.license_status == ProviderLicenseStatus.PENDING


def test_get_source_metadata_declares_real_capabilities_and_gaps() -> None:
    provider = NseFundamentalsProvider(http_client=FakeHttpClient({}), symbols=["RELIANCE"])
    metadata = provider.get_source_metadata()
    assert metadata["capabilities"] == ["fundamentals_quarterly_results_standalone"]
    assert "fundamentals_balance_sheet" in metadata["unsupported"]
    assert "fundamentals_consolidated" in metadata["unsupported"]


def test_other_fetch_methods_are_honest_unsupported_stubs() -> None:
    provider = NseFundamentalsProvider(http_client=FakeHttpClient({}), configured=True)
    for method_name in (
        "fetch_instruments",
        "fetch_historical_eod_bars",
        "fetch_eod_prices",
        "fetch_live_quotes",
        "fetch_market_calendar",
        "fetch_corporate_actions",
        "fetch_benchmark_data",
        "fetch_filings",
        "fetch_index_membership",
        "fetch_macro_data",
    ):
        envelope = getattr(provider, method_name)()
        assert envelope.payload == []
        assert "unsupported" in envelope.source_reference


def test_blocked_broker_attributes_are_never_exposed() -> None:
    provider = NseFundamentalsProvider(http_client=FakeHttpClient({}))
    with pytest.raises(AttributeError):
        provider.place_order  # type: ignore[attr-defined]
