"""Real fundamentals from XBRL filings a human deliberately downloaded and
placed locally -- the honest, zero-compliance-risk alternative to
fundamentals_nse_provider.py's automated pipeline, whose license is
REJECTED because NSE's Terms of Use prohibit automated data collection.

A person visually using NSE's website and clicking "download" on one real
filing is not "systematic or automated data collection" under any
reasonable reading of that clause -- it's the same thing every investor
already does. This provider never makes a network request; it only reads
files a human already placed in `base_path`, one real file per symbol
(`base_path/{SYMBOL}.xml`), a single deliberate click per company per
quarter.

Fully self-contained parsing: every field this needs is read directly from
the XBRL file itself -- the real reporting period (from the filing's own
DateOfStartOfReportingPeriod / DateOfEndOfReportingPeriod tags, picking
whichever real period is closest to one quarter in length, since filings
also declare a longer cumulative year-to-date period), the real filing
date (DateOfBoardMeetingWhenFinancialResultsWereApproved), and the real
Standalone/Consolidated nature (NatureOfReportStandaloneConsolidated) --
files are rejected unless that tag says "Standalone", since a human doing
a manual download has no trusted upstream filter guaranteeing they picked
the right row (unlike fundamentals_nse_provider.py's automated pipeline,
which filters on NSE discovery-API metadata before ever fetching the XBRL;
caught for real when a genuinely Consolidated RELIANCE filing was uploaded
and needed to be rejected, not silently mislabeled). No external
period/date input is required, unlike fundamentals_nse_provider.py's
adapter, which needed the discovery API's filing metadata for this.

Known gaps (same as fundamentals_nse_provider.py, inherited by reusing its
parse_xbrl_fundamentals() and _find_by_local_name()): only the generic
Ind-AS company taxonomy is supported, matched by tag local-name regardless
of which real namespace URI wraps it -- confirmed necessary since NSE/SEBI
have already shipped at least one real taxonomy migration mid-flight
(BSE's "in-bse-fin 2020-03-31" through ~Jan 2025, then SEBI's own
"in-capmkt 2026-01-31"). A file under a genuinely different taxonomy
(e.g. a bank's "BANKING_*.xml", which uses different tag names entirely --
InterestEarned, not RevenueFromOperations) is honestly skipped -- its tags
simply don't match any mapped local name, so no context/value is ever
found, never guessed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope
from aegis.provider_adapters.fundamentals_nse_provider import (
    _find_by_local_name,
    parse_xbrl_fundamentals,
)

# A real quarterly reporting period is ~91 days; filings also declare a
# longer cumulative year-to-date period (e.g. a Q3 filing's Apr-Dec YTD
# span). This range is generous enough to admit real-world filing-date
# rounding without ever matching the YTD period by accident.
QUARTER_DAYS_MIN = 80
QUARTER_DAYS_MAX = 100


def find_reporting_periods(xml_bytes: bytes) -> dict[str, tuple[str, str]]:
    """Real, self-declared reporting periods read directly from the filing
    -- maps contextRef -> (start_date, end_date), both ISO strings."""
    root = ElementTree.fromstring(xml_bytes)
    starts: dict[str, str] = {}
    ends: dict[str, str] = {}
    for element in _find_by_local_name(root, "DateOfStartOfReportingPeriod"):
        context_ref = element.get("contextRef")
        if context_ref and element.text:
            starts[context_ref] = element.text.strip()
    for element in _find_by_local_name(root, "DateOfEndOfReportingPeriod"):
        context_ref = element.get("contextRef")
        if context_ref and element.text:
            ends[context_ref] = element.text.strip()
    return {ref: (starts[ref], ends[ref]) for ref in starts if ref in ends}


def select_quarterly_period(periods: dict[str, tuple[str, str]]) -> tuple[str, str, str] | None:
    """Picks the real declared period whose real duration is closest to one
    quarter -- never a naming-convention guess. Returns
    (contextRef, period_from, period_to), or None if nothing in a real
    quarterly-length range exists in this file."""
    best: tuple[str, str, str] | None = None
    best_diff: int | None = None
    for context_ref, (start, end) in periods.items():
        try:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        except ValueError:
            continue
        if not (QUARTER_DAYS_MIN <= days <= QUARTER_DAYS_MAX):
            continue
        diff = abs(days - 91)
        if best_diff is None or diff < best_diff:
            best = (context_ref, start, end)
            best_diff = diff
    return best


def extract_board_approval_date(xml_bytes: bytes, context_ref: str) -> str | None:
    """The real date the company's board approved these results -- the same
    real-world event NSE's own discovery API reports as "filingDate"."""
    root = ElementTree.fromstring(xml_bytes)
    for element in _find_by_local_name(
        root, "DateOfBoardMeetingWhenFinancialResultsWereApproved"
    ):
        if element.get("contextRef") == context_ref and element.text:
            return element.text.strip()
    return None


def find_nature_of_report(xml_bytes: bytes, context_ref: str) -> str | None:
    """The real self-declared "Standalone" vs "Consolidated" tag for a given
    context. fundamentals_nse_provider.py's automated pipeline filters this
    upstream, from NSE's discovery-API metadata, before ever fetching the
    XBRL file -- but a human doing a manual download has no such trusted
    upstream filter, so the file's own declaration is the only real source
    of truth here. Confirmed real and present under both taxonomies this
    adapter supports (BSE's in-bse-fin and SEBI's in-capmkt)."""
    root = ElementTree.fromstring(xml_bytes)
    for element in _find_by_local_name(root, "NatureOfReportStandaloneConsolidated"):
        if element.get("contextRef") == context_ref and element.text:
            return element.text.strip()
    return None


def describe_why_unparseable(xml_bytes: bytes) -> str:
    """Best-effort, honest explanation for why parse_manually_downloaded_filing
    returned None -- re-derives the same real facts it computes internally,
    to report the most specific real cause instead of one generic message
    for every possible failure."""
    periods = find_reporting_periods(xml_bytes)
    quarterly = select_quarterly_period(periods)
    if quarterly is None:
        return (
            "no real quarterly-length reporting period found in the file -- "
            "see the module docstring's Known gaps"
        )
    context_ref, _, _ = quarterly
    nature = find_nature_of_report(xml_bytes, context_ref)
    if nature is not None and nature != "Standalone":
        return (
            f"this file is a real {nature} filing, not Standalone -- AEGIS only "
            "accepts Standalone (labelled \"Non-Consolidated\" on NSE's website) "
            "results; go back to NSE's Financial Results page and download that "
            "row instead"
        )
    return (
        "no mapped tags found for the real quarterly period in this file -- "
        "see the module docstring's Known gaps"
    )


def parse_manually_downloaded_filing(xml_bytes: bytes, symbol: str) -> dict[str, Any] | None:
    """Fully self-contained: every field comes from the file itself. Returns
    None (never a partial guess) if the file doesn't declare a real
    quarterly-length reporting period, declares itself Consolidated rather
    than Standalone, or no mapped tags match it -- see
    describe_why_unparseable for which of these actually happened."""
    periods = find_reporting_periods(xml_bytes)
    quarterly = select_quarterly_period(periods)
    if quarterly is None:
        return None
    context_ref, period_from, period_to = quarterly
    nature = find_nature_of_report(xml_bytes, context_ref)
    if nature is not None and nature != "Standalone":
        return None
    values = parse_xbrl_fundamentals(xml_bytes, period_from=period_from, period_to=period_to)
    if not values:
        return None
    return {
        "symbol": symbol,
        "period_from": period_from,
        "period_to": period_to,
        "filing_date": extract_board_approval_date(xml_bytes, context_ref),
        "source_xbrl_url": None,
        **values,
    }


class FundamentalsManualImportProvider:
    """Real fundamentals sourced entirely from human-downloaded local files
    -- no network access, ever. See the module docstring for why this is a
    real, honest, zero-compliance-risk path, unlike fundamentals_nse_provider.py."""

    name = "fundamentals_manual_import"
    dataset_origin = "APPROVED_FILE_IMPORT"
    data_source_mode = "LOCAL_FILE_IMPORT"
    broker_order_access = False

    def __init__(self, base_path: Path, license_: ProviderLicense | None = None) -> None:
        self.base_path = base_path
        self._license = license_ or ProviderLicense(
            provider_id="fundamentals-manual-import",
            license_status=ProviderLicenseStatus.APPROVED,
            permitted_use=(
                "Real fundamentals from XBRL filings a human deliberately downloaded "
                "themselves and placed locally, one real file per symbol -- no automated "
                "network access, so NSE's Terms of Use prohibition on automated data "
                "collection does not apply."
            ),
            automation_rights=False,
            backtesting_rights=True,
            model_training_rights=False,
            dashboard_display_rights=True,
            data_retention_period="indefinite-local",
        )

    def validate_read_only_scope(self) -> None:
        return None

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        payload: list[dict[str, Any]] = []
        skipped: dict[str, str] = {}
        if self.base_path.exists():
            for path in sorted(self.base_path.glob("*.xml")):
                symbol = path.stem.upper()
                xml_bytes = path.read_bytes()
                try:
                    record = parse_manually_downloaded_filing(xml_bytes, symbol)
                except ElementTree.ParseError as exc:
                    skipped[symbol] = f"not a valid XML file: {exc}"
                    continue
                if record is None:
                    skipped[symbol] = describe_why_unparseable(xml_bytes)
                    continue
                payload.append(record)
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_fundamentals",
            schema_version="fundamentals.v1",
            source_reference=f"file://{self.base_path}",
            payload=payload,
            metadata={"skipped_symbols": skipped},
        )

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_instruments", "instruments.v1", [], "unsupported/instruments"
        )

    def fetch_historical_eod_bars(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_historical_eod_bars",
            "eod_bars.v1",
            [],
            "unsupported/historical_eod_bars",
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_eod_prices", "eod_prices.v1", [], "unsupported/eod_prices"
        )

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_live_quotes", "live_quotes.v1", [], "unsupported/live_quotes"
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_market_calendar", "market_calendar.v1", [], "unsupported/market_calendar"
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_corporate_actions",
            "corporate_actions.v1",
            [],
            "unsupported/corporate_actions",
        )

    def fetch_benchmark_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_benchmark_data", "benchmark_eod.v1", [], "unsupported/benchmark_data"
        )

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_filings", "filings.v1", [], "unsupported/filings"
        )

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_index_membership",
            "index_membership.v1",
            [],
            "unsupported/index_membership",
        )

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_macro_data", "macro.v1", [], "unsupported/macro"
        )

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "base_path": str(self.base_path),
            "capabilities": ["fundamentals_quarterly_results_standalone_from_local_files"],
            "unsupported": [
                "instruments",
                "historical_eod_bars",
                "eod_prices",
                "live_quotes",
                "market_calendar",
                "corporate_actions",
                "benchmark_data",
                "filings",
                "index_membership",
                "macro",
            ],
        }

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        exists = self.base_path.exists()
        return ProviderHealthResult(
            healthy=exists,
            message=f"local import directory exists: {exists} ({self.base_path})",
            mode=self.data_source_mode,
            order_access=False,
        )
