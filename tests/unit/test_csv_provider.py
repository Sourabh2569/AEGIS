from __future__ import annotations

import csv
from pathlib import Path

import pytest
from aegis.provider_adapters.csv_provider import CsvFileProvider


@pytest.fixture
def sample_data_root(tmp_path: Path) -> Path:
    calendar_dir = tmp_path / "market_calendar"
    calendar_dir.mkdir()
    with (calendar_dir / "market_calendar.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["exchange", "session_date", "is_open"])
        writer.writerow(["NSE", "2026-09-01", "true"])
        writer.writerow(["NSE", "2026-09-02", "true"])
    return tmp_path


def test_fetch_market_calendar_reads_real_csv_not_a_stub(sample_data_root: Path) -> None:
    """fetch_market_calendar used to unconditionally return an empty payload
    regardless of any file on disk -- confirm it now actually reads one."""
    provider = CsvFileProvider(sample_data_root)
    envelope = provider.fetch_market_calendar()
    assert len(envelope.payload) == 2
    assert envelope.payload[0]["exchange"] == "NSE"
    assert envelope.payload[0]["session_date"] == "2026-09-01"
    assert envelope.payload[0]["is_open"] == "true"


def test_fetch_market_calendar_missing_file_raises(tmp_path: Path) -> None:
    provider = CsvFileProvider(tmp_path)
    with pytest.raises(FileNotFoundError):
        provider.fetch_market_calendar()
