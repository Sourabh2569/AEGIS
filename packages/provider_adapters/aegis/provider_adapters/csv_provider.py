from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope


class CsvFileProvider:
    name = "csv_file_provider"
    dataset_origin = "APPROVED_FILE_IMPORT"

    def __init__(self, base_path: Path, license_: ProviderLicense | None = None) -> None:
        self.base_path = base_path
        self._license = license_ or ProviderLicense(
            provider_id="csv-provider",
            license_status=ProviderLicenseStatus.APPROVED,
            permitted_use="local file ingestion",
            automation_rights=True,
            backtesting_rights=True,
            model_training_rights=False,
            dashboard_display_rights=True,
            data_retention_period="indefinite-local",
        )

    def _read_csv(self, relative_path: str, required_columns: set[str]) -> list[dict[str, Any]]:
        path = (self.base_path / relative_path).resolve()
        if not str(path).startswith(str(self.base_path.resolve())):
            raise ValueError("CSV path escapes configured sample_data directory.")
        with path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            missing = required_columns - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV schema missing required columns: {sorted(missing)}")
            return [dict(row) for row in reader]

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_instruments",
            "instruments.v1",
            self._read_csv(
                "instruments/instruments.csv",
                {"aegis_instrument_id", "isin", "company_legal_name", "current_symbol"},
            ),
            "sample_data/instruments/instruments.csv",
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_eod_prices",
            "eod_ohlcv.v1",
            self._read_csv(
                "eod_prices/eod_prices.csv",
                {"aegis_instrument_id", "trade_date", "open", "high", "low", "close", "volume"},
            ),
            "sample_data/eod_prices/eod_prices.csv",
        )

    def fetch_historical_eod_bars(self) -> ProviderResponseEnvelope:
        return self.fetch_eod_prices()

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_live_quotes",
            "live_quotes.v1",
            [],
            "sample_data/live_quotes/not-configured",
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_market_calendar",
            "market_calendar.v1",
            [],
            "sample_data/market_calendar/not-configured",
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_corporate_actions",
            "corporate_actions.v1",
            self._read_csv(
                "corporate_actions/corporate_actions.csv",
                {"aegis_instrument_id", "action_type", "announcement_time", "source_reference"},
            ),
            "sample_data/corporate_actions/corporate_actions.csv",
        )

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_fundamentals", "fundamentals.v1", [], "sample_data/fundamentals"
        )

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_filings", "filings.v1", [], "sample_data/filings"
        )

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_index_membership", "index_membership.v1", [], "sample_data/index"
        )

    def fetch_benchmark_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_benchmark_data",
            "benchmark_eod.v1",
            [],
            "sample_data/benchmark/not-configured",
        )

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_macro_data", "macro.v1", [], "sample_data/macro"
        )

    def get_source_metadata(self) -> dict[str, str]:
        return {"provider": self.name, "base_path": str(self.base_path)}

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        return ProviderHealthResult(
            self.base_path.exists(), f"base path exists: {self.base_path.exists()}"
        )

    def validate_read_only_scope(self) -> None:
        return None
