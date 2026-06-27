from __future__ import annotations

from aegis.backtesting.domain import BacktestRun, SimulationClassification
from aegis.backtesting.repositories import MarketDataReader, TradingCalendarReader
from aegis.domain.models import (
    DatasetVersion,
    Instrument,
    ProviderLicense,
    ProviderLicenseStatus,
    ValidationStatus,
)
from aegis.shared.errors import EligibilityError


class DatasetEligibilityGuard:
    allowed_statuses = {ValidationStatus.GREEN, ValidationStatus.GREEN_CAUTION}

    def assert_eligible(self, version: DatasetVersion, license_: ProviderLicense) -> None:
        if version.validation_status not in self.allowed_statuses:
            raise EligibilityError(f"DATASET_NOT_ELIGIBLE:{version.validation_status}")
        if not version.lineage_record_exists:
            raise EligibilityError("DATASET_LINEAGE_MISSING")
        if license_.license_status != ProviderLicenseStatus.APPROVED:
            raise EligibilityError(f"PROVIDER_LICENSE_NOT_APPROVED:{license_.license_status}")


class InstrumentEligibilityGuard:
    def assert_eligible(self, instrument: Instrument, run: BacktestRun) -> None:
        if instrument.aegis_instrument_id != run.instrument_id:
            raise EligibilityError("INSTRUMENT_ID_MISMATCH")
        if instrument.trading_status not in {"ACTIVE", "ELIGIBLE"}:
            raise EligibilityError(f"INSTRUMENT_NOT_ELIGIBLE:{instrument.trading_status}")
        if instrument.mapping_confidence_score < 0.9:
            raise EligibilityError("INSTRUMENT_MAPPING_UNRESOLVED")


class BacktestPreflightGuard:
    def __init__(
        self,
        dataset_guard: DatasetEligibilityGuard | None = None,
        instrument_guard: InstrumentEligibilityGuard | None = None,
    ) -> None:
        self.dataset_guard = dataset_guard or DatasetEligibilityGuard()
        self.instrument_guard = instrument_guard or InstrumentEligibilityGuard()

    def assert_can_start(
        self,
        *,
        run: BacktestRun,
        dataset_version: DatasetVersion,
        provider_license: ProviderLicense,
        instrument: Instrument,
        calendar: TradingCalendarReader,
        market_data: MarketDataReader,
    ) -> None:
        self.dataset_guard.assert_eligible(dataset_version, provider_license)
        self.instrument_guard.assert_eligible(instrument, run)
        if not calendar.sessions_between(run.start_date, run.end_date):
            raise EligibilityError("MARKET_CALENDAR_MISSING")
        if not market_data.has_bars(run.instrument_id, run.start_date, run.end_date):
            raise EligibilityError("EOD_BARS_MISSING")
        if run.execution_model_version != "NEXT_ELIGIBLE_SESSION_OPEN_V0":
            raise EligibilityError("UNSUPPORTED_EXECUTION_MODEL")
        if run.simulation_classification != SimulationClassification.FOUNDATION_SIMULATION_ONLY:
            raise EligibilityError("INVALID_SIMULATION_CLASSIFICATION")
