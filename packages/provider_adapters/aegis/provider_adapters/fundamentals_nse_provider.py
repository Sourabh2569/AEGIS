"""NSE fundamentals adapter -- real, structured company financial-statement
data parsed from NSE's own public corporate-filings XBRL archive.

**This provider's real ProviderLicense is REJECTED, permanently, by design.**
NSE's own Terms of Use (https://www.nseindia.com/static/nse-terms-of-use,
reviewed 2026-09-12) explicitly prohibit "systematic or automated data
collection activities (including scraping, data mining, data extraction and
data harvesting)" on their site -- exactly what this adapter's real HTTP
calls do. Technical feasibility was real (confirmed live: NSE's discovery
API and XBRL archive are both publicly fetchable, no login wall), but
feasibility isn't permission. This code is kept as a working, tested
reference for the real parsing logic (it may be reusable against a
genuinely licensed data source later) but must never have its license
flipped to APPROVED against NSE itself. See
docs/data_activation_sprint/fundamentals_provider_decision.md for the full
finding and what a compliant path would actually require.

Known gaps (do not fabricate data for these):
- Only quarterly RESULTS filings are read today -- these carry P&L-shaped
  tags (revenue, profit before tax, profit for the period). Balance-sheet
  items (total assets, total equity) are not present in this filing type;
  reading those would mean parsing a different filing (annual report XBRL),
  not attempted here.
- Only the "Non-Consolidated" filing is read (matches every real filing
  this adapter was built and tested against -- see tests/fixtures/xbrl/,
  one real captured quarterly filing each for RELIANCE, TCS, HCLTECH, INFY,
  TECHM, WIPRO). A consolidated variant may report different figures; not
  read here.
- Only tags confirmed present and correctly scoped by real XBRL context in
  those captured filings are mapped (see FUNDAMENTALS_TAGS). Any company or
  period whose filing doesn't carry a context matching the filing's own
  declared (fromDate, toDate) is honestly skipped, never guessed from a
  context-naming convention (e.g. "OneD"/"FourD" are filer-specific, not a
  reliable cross-company signal of "this quarter" vs "cumulative").
- **Only companies filing under the generic Ind-AS taxonomy are supported.**
  Banks/NBFCs/insurers file under a materially different taxonomy (confirmed
  by fetching a real HDFCBANK filing: "BANKING_*.xml", tags like
  InterestEarned/ProfitLossForThePeriod, not RevenueFromOperations/
  ProfitBeforeTax/ProfitLossForPeriod) -- pointing this adapter at a
  financial-sector symbol will honestly skip it (no mapped tags match), not
  silently return wrong numbers. Supporting those sectors needs separate,
  real tag-mapping work against a real captured filing from each, not
  attempted here. See fundamentals_provider_decision.md.
- Storage is keyed by real market symbol, not aegis_instrument_id -- a
  deliberate simplification for this pilot's scale (currently one sector,
  5-11 companies); a full-universe rollout should remap through the same
  sector_by_instrument_id-style lookup already used elsewhere in main.py.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from xml.etree import ElementTree

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope

XBRLI_NAMESPACE = "http://www.xbrl.org/2003/instance"
NSE_FIN_NAMESPACE = "http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"

# Only tags confirmed present, real, and correctly period-scoped in a real
# captured filing -- see the module docstring's "Known gaps".
FUNDAMENTALS_TAGS: dict[str, str] = {
    "revenue_from_operations": "RevenueFromOperations",
    "profit_before_tax": "ProfitBeforeTax",
    "profit_for_period": "ProfitLossForPeriod",
}

USER_AGENT = "Mozilla/5.0 (compatible; AEGIS-research/1.0)"


class HttpClient(Protocol):
    """Injectable so tests never hit the real network -- see FakeHttpClient
    in tests/unit/test_fundamentals_nse_provider.py."""

    def get(self, url: str) -> bytes: ...


class UrllibHttpClient:
    """The one real implementation -- stdlib only, no new dependency."""

    def get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            return response.read()


def _to_iso_date(value: str) -> str:
    return datetime.strptime(value, "%d-%b-%Y").date().isoformat()


def _to_filing_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%d-%b-%Y %H:%M")


@dataclass(frozen=True)
class FundamentalsFilingRef:
    symbol: str
    xbrl_url: str
    period_from: str
    period_to: str
    filing_date: str


def find_latest_standalone_filing(
    records: list[dict[str, Any]], *, symbol: str
) -> FundamentalsFilingRef | None:
    """Real filter + selection logic, kept separate from any network call so
    it's directly unit-testable against a captured API response."""
    candidates = [
        record
        for record in records
        if record.get("consolidated") == "Non-Consolidated" and record.get("xbrl")
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda record: _to_filing_datetime(record["filingDate"]))
    return FundamentalsFilingRef(
        symbol=symbol,
        xbrl_url=latest["xbrl"],
        period_from=_to_iso_date(latest["fromDate"]),
        period_to=_to_iso_date(latest["toDate"]),
        filing_date=latest["filingDate"],
    )


def parse_xbrl_fundamentals(
    xml_bytes: bytes, *, period_from: str, period_to: str
) -> dict[str, str]:
    """Real, minimal XBRL parse. Finds the context(s) whose declared period
    exactly matches the filing's own (period_from, period_to) -- never a
    naming-convention guess -- then reads only FUNDAMENTALS_TAGS values
    scoped to one of those contexts. Returns {} (never a partial guess) if no
    context matches; callers must treat that as "not available"."""
    root = ElementTree.fromstring(xml_bytes)
    ns = {"xbrli": XBRLI_NAMESPACE, "fin": NSE_FIN_NAMESPACE}

    matching_context_ids: set[str] = set()
    for context in root.findall("xbrli:context", ns):
        context_id = context.get("id")
        period = context.find("xbrli:period", ns)
        if period is None or context_id is None:
            continue
        start = period.findtext("xbrli:startDate", namespaces=ns)
        end = period.findtext("xbrli:endDate", namespaces=ns)
        if start == period_from and end == period_to:
            matching_context_ids.add(context_id)

    if not matching_context_ids:
        return {}

    values: dict[str, str] = {}
    for field_name, tag in FUNDAMENTALS_TAGS.items():
        for element in root.findall(f"fin:{tag}", ns):
            if element.get("contextRef") in matching_context_ids and element.text:
                values[field_name] = element.text.strip()
                break
    return values


class NseFundamentalsProvider:
    """Real fundamentals adapter reading NSE's public corporate-filings
    archive for a small, explicit pilot symbol set. See the module docstring
    for known gaps and the still-PENDING license this ships with."""

    name = "fundamentals_nse"
    data_source_mode = "LIVE_READONLY"
    broker_order_access = False

    @property
    def dataset_origin(self) -> str:
        # Only claim real data once actually configured for real HTTP access
        # -- _assert_configured() already blocks fetch_fundamentals() before
        # this matters, but stay honest defensively too, matching
        # kite_connect_provider.py's own dataset_origin property.
        return "ACTUAL_PROVIDER_DATA" if self.configured else "FIXTURE_DATA"

    def __init__(
        self,
        *,
        http_client: HttpClient | None = None,
        symbols: list[str] | None = None,
        license_: ProviderLicense | None = None,
        configured: bool = False,
        min_request_interval_seconds: float = 1.0,
    ) -> None:
        self._http_client = http_client or UrllibHttpClient()
        self._symbols = symbols or ["RELIANCE"]
        self.configured = configured
        # Real politeness toward a public archive that wasn't built to serve
        # bulk automated traffic -- one real HTTP request per this many
        # seconds, across both the discovery API and XBRL downloads. Tests
        # pass 0 to stay fast; see kite_connect_provider.py's identical
        # historical_data_min_interval_seconds pattern.
        self._min_request_interval_seconds = min_request_interval_seconds
        self._last_request_at: float | None = None
        self._license = license_ or ProviderLicense(
            provider_id="fundamentals-nse",
            license_status=ProviderLicenseStatus.REJECTED,
            permitted_use=(
                "None -- NSE's real Terms of Use (https://www.nseindia.com/static/nse-terms-of-use, "
                "reviewed 2026-09-12) explicitly state: 'User is prohibited to conduct any "
                "systematic or automated data collection activities (including scraping, "
                "data mining, data extraction and data harvesting) on or in relation to our "
                "Website / Mobile Application.' This adapter's real HTTP calls to NSE's "
                "public discovery API and XBRL archive are exactly that. See "
                "docs/data_activation_sprint/fundamentals_provider_decision.md."
            ),
            automation_rights=False,
            backtesting_rights=False,
            model_training_rights=False,
            dashboard_display_rights=False,
            data_retention_period="not-recorded",
            legal_review_status="REJECTED_TOS_PROHIBITS_AUTOMATION",
        )

    def __getattr__(self, name: str) -> Any:
        blocked = {
            "place_order",
            "submit_order",
            "modify_order",
            "cancel_order",
            "get_holdings",
            "fetch_holdings",
            "margins",
            "orders",
            "positions",
        }
        if name in blocked:
            raise AttributeError(
                f"{name} is prohibited: provider is DATA_SOURCE_MODE=LIVE_READONLY."
            )
        raise AttributeError(name)

    def validate_read_only_scope(self) -> None:
        if self.broker_order_access:
            raise PermissionError(
                "BROKER_ORDER_ACCESS must remain false for read-only provider adapters."
            )

    def _assert_configured(self) -> None:
        self.validate_read_only_scope()
        if not self.configured:
            raise PermissionError(
                "Provider setup required: fundamentals_nse has no real HTTP access configured."
            )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            remaining = self._min_request_interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _get(self, url: str) -> bytes:
        self._throttle()
        return self._http_client.get(url)

    def _latest_filing(self, symbol: str) -> FundamentalsFilingRef | None:
        url = (
            "https://www.nseindia.com/api/corporates-financial-results"
            f"?index=equities&period=Quarterly&symbol={symbol}"
        )
        records = json.loads(self._get(url))
        return find_latest_standalone_filing(records, symbol=symbol)

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        now = self._now().isoformat()
        payload: list[dict[str, Any]] = []
        skipped: dict[str, str] = {}
        for symbol in self._symbols:
            try:
                filing = self._latest_filing(symbol)
                if filing is None:
                    skipped[symbol] = "no standalone quarterly filing found"
                    continue
                xml_bytes = self._get(filing.xbrl_url)
                values = parse_xbrl_fundamentals(
                    xml_bytes, period_from=filing.period_from, period_to=filing.period_to
                )
                if not values:
                    skipped[symbol] = "filing found but no mapped tags matched its declared period"
                    continue
            except Exception as exc:  # noqa: BLE001 -- one company's failure (network
                # error, malformed response, etc.) must never abort fetching the
                # rest of the batch; the real reason is recorded, not swallowed.
                skipped[symbol] = f"{type(exc).__name__}: {exc}"
                continue
            payload.append(
                {
                    "symbol": symbol,
                    "period_from": filing.period_from,
                    "period_to": filing.period_to,
                    "filing_date": filing.filing_date,
                    "source_xbrl_url": filing.xbrl_url,
                    **values,
                    "event_time": now,
                    "available_time": now,
                    "ingested_time": now,
                }
            )
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_fundamentals",
            schema_version="fundamentals.v1",
            source_reference="nse://corporate-filings/financial-results",
            payload=payload,
            metadata={"skipped_symbols": skipped},
        )

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_instruments", "instruments.v1", [], "nse://unsupported/instruments"
        )

    def fetch_historical_eod_bars(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_historical_eod_bars",
            "eod_bars.v1",
            [],
            "nse://unsupported/historical_eod_bars",
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_eod_prices", "eod_prices.v1", [], "nse://unsupported/eod_prices"
        )

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_live_quotes", "live_quotes.v1", [], "nse://unsupported/live_quotes"
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_market_calendar",
            "market_calendar.v1",
            [],
            "nse://unsupported/market_calendar",
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_corporate_actions",
            "corporate_actions.v1",
            [],
            "nse://unsupported/corporate_actions",
        )

    def fetch_benchmark_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_benchmark_data",
            "benchmark_eod.v1",
            [],
            "nse://unsupported/benchmark_data",
        )

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_filings", "filings.v1", [], "nse://unsupported/filings"
        )

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_index_membership",
            "index_membership.v1",
            [],
            "nse://unsupported/index_membership",
        )

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_macro_data", "macro.v1", [], "nse://unsupported/macro"
        )

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "data_source_mode": self.data_source_mode,
            "broker_order_access": self.broker_order_access,
            "configured": self.configured,
            "symbols": list(self._symbols),
            "capabilities": ["fundamentals_quarterly_results_standalone"],
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
                "fundamentals_consolidated",
                "fundamentals_balance_sheet",
            ],
        }

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        if not self.configured:
            return ProviderHealthResult(
                healthy=False,
                message="Provider setup required: fundamentals_nse HTTP access is not configured.",
                checked_at=self._now(),
                latency_ms=None,
                mode=self.data_source_mode,
                order_access=self.broker_order_access,
            )
        started = self._now()
        try:
            self._http_client.get(
                "https://www.nseindia.com/api/corporates-financial-results"
                "?index=equities&period=Quarterly&symbol=RELIANCE"
            )
        except Exception as exc:  # noqa: BLE001 -- surfaced honestly, not swallowed
            return ProviderHealthResult(
                healthy=False,
                message=f"NSE fundamentals endpoint unreachable: {exc}",
                checked_at=started,
                latency_ms=None,
                mode=self.data_source_mode,
                order_access=self.broker_order_access,
            )
        latency_ms = (self._now() - started).total_seconds() * 1000
        return ProviderHealthResult(
            healthy=True,
            message="NSE fundamentals endpoint reachable.",
            checked_at=started,
            latency_ms=latency_ms,
            mode=self.data_source_mode,
            order_access=self.broker_order_access,
        )
