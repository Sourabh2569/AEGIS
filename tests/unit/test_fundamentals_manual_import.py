from __future__ import annotations

from pathlib import Path

import pytest

from aegis.domain.models import ProviderLicenseStatus
from aegis.provider_adapters.fundamentals_manual_import import (
    FundamentalsManualImportProvider,
    extract_board_approval_date,
    find_reporting_periods,
    parse_manually_downloaded_filing,
    select_quarterly_period,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "xbrl"

# Real, expected values confirmed against the live filings this session --
# a regression here means the self-contained period-detection stopped
# reading the real quarter correctly.
REAL_FIXTURES = {
    "RELIANCE": ("reliance_q3_fy2025_standalone.xml", "1282600000000.00", "87210000000.00"),
    "TCS": ("tcs_q3_fy2025_standalone.xml", "538830000000.00", "118320000000.00"),
    "HCLTECH": ("hcltech_q3_fy2025_standalone.xml", "132740000000.00", "35260000000.00"),
    "INFY": ("infy_q3_fy2025_standalone.xml", "349150000000.00", "63580000000.00"),
    "TECHM": ("techm_q3_fy2025_standalone.xml", "111762000000.00", "8583000000.00"),
    "WIPRO": ("wipro_q3_fy2025_standalone.xml", "168030000000.00", "28121000000.00"),
}


def test_find_reporting_periods_reads_both_real_declared_periods() -> None:
    xml_bytes = (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes()
    periods = find_reporting_periods(xml_bytes)
    assert periods["OneD"] == ("2024-10-01", "2024-12-31")
    assert periods["FourD"] == ("2024-04-01", "2024-12-31")


def test_select_quarterly_period_picks_the_real_quarter_not_the_ytd_period() -> None:
    periods = {"OneD": ("2024-10-01", "2024-12-31"), "FourD": ("2024-04-01", "2024-12-31")}
    result = select_quarterly_period(periods)
    assert result == ("OneD", "2024-10-01", "2024-12-31")


def test_select_quarterly_period_returns_none_without_a_real_quarterly_period() -> None:
    assert select_quarterly_period({"FourD": ("2024-04-01", "2024-12-31")}) is None
    assert select_quarterly_period({}) is None


def test_extract_board_approval_date_reads_the_real_filing_date() -> None:
    xml_bytes = (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes()
    assert extract_board_approval_date(xml_bytes, "OneD") == "2025-01-16"


@pytest.mark.parametrize("symbol", sorted(REAL_FIXTURES))
def test_parse_manually_downloaded_filing_is_fully_self_contained(symbol: str) -> None:
    """No external period/date input at all -- every real company's filing
    parses correctly from the file alone."""
    filename, revenue, profit = REAL_FIXTURES[symbol]
    xml_bytes = (FIXTURES_DIR / filename).read_bytes()
    record = parse_manually_downloaded_filing(xml_bytes, symbol)
    assert record is not None
    assert record["symbol"] == symbol
    assert record["period_from"] == "2024-10-01"
    assert record["period_to"] == "2024-12-31"
    assert record["filing_date"] is not None
    assert record["revenue_from_operations"] == revenue
    assert record["profit_for_period"] == profit


def test_parse_manually_downloaded_filing_returns_none_for_garbage() -> None:
    assert parse_manually_downloaded_filing(b"<not-xbrl/>", "FAKE") is None


def test_provider_scans_a_directory_and_skips_invalid_files(tmp_path: Path) -> None:
    (tmp_path / "RELIANCE.xml").write_bytes(
        (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes()
    )
    (tmp_path / "BROKEN.xml").write_bytes(b"not xml at all")
    provider = FundamentalsManualImportProvider(base_path=tmp_path)

    assert provider.get_license_status().license_status == ProviderLicenseStatus.APPROVED
    assert provider.dataset_origin == "APPROVED_FILE_IMPORT"

    envelope = provider.fetch_fundamentals()
    assert len(envelope.payload) == 1
    assert envelope.payload[0]["symbol"] == "RELIANCE"
    assert "BROKEN" in envelope.metadata["skipped_symbols"]


def test_provider_is_healthy_only_when_the_directory_exists(tmp_path: Path) -> None:
    missing = FundamentalsManualImportProvider(base_path=tmp_path / "does-not-exist")
    assert missing.get_health_status().healthy is False

    (tmp_path / "real").mkdir()
    present = FundamentalsManualImportProvider(base_path=tmp_path / "real")
    assert present.get_health_status().healthy is True


def test_provider_other_fetch_methods_are_honest_unsupported_stubs(tmp_path: Path) -> None:
    provider = FundamentalsManualImportProvider(base_path=tmp_path)
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
