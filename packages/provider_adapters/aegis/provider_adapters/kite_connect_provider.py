from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus
from aegis.provider_adapters.base import ProviderHealthResult, ProviderResponseEnvelope


class KiteClientProtocol(Protocol):
    """The subset of kiteconnect.KiteConnect this adapter depends on.

    Isolated as a Protocol so tests can inject a fake client instead of hitting
    the real Kite Connect API (which requires a paid subscription and a
    daily-refreshed access token).
    """

    def instruments(self, exchange: str) -> list[dict[str, Any]]: ...

    def historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]: ...

    def quote(self, instruments: list[str]) -> dict[str, Any]: ...

    def profile(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CuratedInstrumentMetadata:
    isin: str
    company_legal_name: str
    security_type: str
    listing_date: date
    sector: str
    industry: str
    aegis_instrument_id: str


# Kite Connect's instrument dump does not include ISIN, listing date, sector, or
# industry. Those must come from AEGIS's governed instrument master, not be
# fabricated here.
#
# This table is the Nifty 50 as of 2026-09, cross-verified against three
# independent official sources before being added: NSE's official Nifty 50
# constituent list (nsearchives.nseindia.com/content/indices/ind_nifty50list.csv),
# NSE's official securities master (nsearchives.nseindia.com/content/equities/EQUITY_L.csv,
# for listing dates and an ISIN cross-check), and Kite's own live NSE
# instrument dump (to confirm every tradingsymbol actually resolves). All 50
# ISINs matched exactly between the two independent NSE sources, and all 50
# tradingsymbols resolved against Kite. Company names and listing dates are
# NSE's own master data.
#
# NSE's public constituent list provides only one industry classification
# tier, not a separate broader "sector" -- sector and industry below are
# deliberately set to the same NSE-verified value rather than inventing a
# second tier that hasn't been verified against anything.
#
# Nifty 50 membership itself changes periodically as NSE reconstitutes the
# index; re-derive this table from the same two NSE URLs above rather than
# hand-editing if it drifts.
#
# Only add entries you have verified against an authoritative source this
# way -- an unmapped symbol is skipped and reported via
# metadata["unmapped_symbols"] rather than guessed.
CURATED_INSTRUMENT_METADATA: dict[str, CuratedInstrumentMetadata] = {
    "RELIANCE": CuratedInstrumentMetadata(
        isin="INE002A01018",
        company_legal_name="Reliance Industries Limited",
        security_type="EQUITY",
        listing_date=date(1995, 11, 29),
        sector="Oil Gas & Consumable Fuels",
        industry="Oil Gas & Consumable Fuels",
        aegis_instrument_id="AEGIS-IN-000001",
    ),
    "TCS": CuratedInstrumentMetadata(
        isin="INE467B01029",
        company_legal_name="Tata Consultancy Services Limited",
        security_type="EQUITY",
        listing_date=date(2004, 8, 25),
        sector="Information Technology",
        industry="Information Technology",
        aegis_instrument_id="AEGIS-IN-000002",
    ),
    "ADANIENT": CuratedInstrumentMetadata(
        isin="INE423A01024",
        company_legal_name="Adani Enterprises Limited",
        security_type="EQUITY",
        listing_date=date(1997, 6, 4),
        sector="Metals & Mining",
        industry="Metals & Mining",
        aegis_instrument_id="AEGIS-IN-000003",
    ),
    "ADANIPORTS": CuratedInstrumentMetadata(
        isin="INE742F01042",
        company_legal_name="Adani Ports and Special Economic Zone Limited",
        security_type="EQUITY",
        listing_date=date(2007, 11, 27),
        sector="Services",
        industry="Services",
        aegis_instrument_id="AEGIS-IN-000004",
    ),
    "APOLLOHOSP": CuratedInstrumentMetadata(
        isin="INE437A01024",
        company_legal_name="Apollo Hospitals Enterprise Limited",
        security_type="EQUITY",
        listing_date=date(1996, 1, 10),
        sector="Healthcare",
        industry="Healthcare",
        aegis_instrument_id="AEGIS-IN-000005",
    ),
    "ASIANPAINT": CuratedInstrumentMetadata(
        isin="INE021A01026",
        company_legal_name="Asian Paints Limited",
        security_type="EQUITY",
        listing_date=date(1995, 5, 31),
        sector="Consumer Durables",
        industry="Consumer Durables",
        aegis_instrument_id="AEGIS-IN-000006",
    ),
    "AXISBANK": CuratedInstrumentMetadata(
        isin="INE238A01034",
        company_legal_name="Axis Bank Limited",
        security_type="EQUITY",
        listing_date=date(1998, 11, 16),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000007",
    ),
    "BAJAJ-AUTO": CuratedInstrumentMetadata(
        isin="INE917I01010",
        company_legal_name="Bajaj Auto Limited",
        security_type="EQUITY",
        listing_date=date(2008, 5, 26),
        sector="Automobile and Auto Components",
        industry="Automobile and Auto Components",
        aegis_instrument_id="AEGIS-IN-000008",
    ),
    "BAJFINANCE": CuratedInstrumentMetadata(
        isin="INE296A01032",
        company_legal_name="Bajaj Finance Limited",
        security_type="EQUITY",
        listing_date=date(2003, 4, 1),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000009",
    ),
    "BAJAJFINSV": CuratedInstrumentMetadata(
        isin="INE918I01026",
        company_legal_name="Bajaj Finserv Limited",
        security_type="EQUITY",
        listing_date=date(2008, 5, 26),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000010",
    ),
    "BEL": CuratedInstrumentMetadata(
        isin="INE263A01024",
        company_legal_name="Bharat Electronics Limited",
        security_type="EQUITY",
        listing_date=date(2000, 7, 19),
        sector="Capital Goods",
        industry="Capital Goods",
        aegis_instrument_id="AEGIS-IN-000011",
    ),
    "BHARTIARTL": CuratedInstrumentMetadata(
        isin="INE397D01024",
        company_legal_name="Bharti Airtel Limited",
        security_type="EQUITY",
        listing_date=date(2002, 2, 15),
        sector="Telecommunication",
        industry="Telecommunication",
        aegis_instrument_id="AEGIS-IN-000012",
    ),
    "CIPLA": CuratedInstrumentMetadata(
        isin="INE059A01026",
        company_legal_name="Cipla Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector="Healthcare",
        industry="Healthcare",
        aegis_instrument_id="AEGIS-IN-000013",
    ),
    "COALINDIA": CuratedInstrumentMetadata(
        isin="INE522F01014",
        company_legal_name="Coal India Limited",
        security_type="EQUITY",
        listing_date=date(2010, 11, 4),
        sector="Oil Gas & Consumable Fuels",
        industry="Oil Gas & Consumable Fuels",
        aegis_instrument_id="AEGIS-IN-000014",
    ),
    "DRREDDY": CuratedInstrumentMetadata(
        isin="INE089A01031",
        company_legal_name="Dr. Reddy's Laboratories Limited",
        security_type="EQUITY",
        listing_date=date(2003, 5, 30),
        sector="Healthcare",
        industry="Healthcare",
        aegis_instrument_id="AEGIS-IN-000015",
    ),
    "EICHERMOT": CuratedInstrumentMetadata(
        isin="INE066A01021",
        company_legal_name="Eicher Motors Limited",
        security_type="EQUITY",
        listing_date=date(2004, 9, 7),
        sector="Automobile and Auto Components",
        industry="Automobile and Auto Components",
        aegis_instrument_id="AEGIS-IN-000016",
    ),
    "ETERNAL": CuratedInstrumentMetadata(
        isin="INE758T01015",
        company_legal_name="ETERNAL LIMITED",
        security_type="EQUITY",
        listing_date=date(2021, 7, 23),
        sector="Consumer Services",
        industry="Consumer Services",
        aegis_instrument_id="AEGIS-IN-000017",
    ),
    "GRASIM": CuratedInstrumentMetadata(
        isin="INE047A01021",
        company_legal_name="Grasim Industries Limited",
        security_type="EQUITY",
        listing_date=date(1995, 5, 10),
        sector="Construction Materials",
        industry="Construction Materials",
        aegis_instrument_id="AEGIS-IN-000018",
    ),
    "HCLTECH": CuratedInstrumentMetadata(
        isin="INE860A01027",
        company_legal_name="HCL Technologies Limited",
        security_type="EQUITY",
        listing_date=date(2000, 1, 6),
        sector="Information Technology",
        industry="Information Technology",
        aegis_instrument_id="AEGIS-IN-000019",
    ),
    "HDFCBANK": CuratedInstrumentMetadata(
        isin="INE040A01034",
        company_legal_name="HDFC Bank Limited",
        security_type="EQUITY",
        listing_date=date(1995, 11, 8),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000020",
    ),
    "HDFCLIFE": CuratedInstrumentMetadata(
        isin="INE795G01014",
        company_legal_name="HDFC Life Insurance Company Limited",
        security_type="EQUITY",
        listing_date=date(2017, 11, 17),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000021",
    ),
    "HINDALCO": CuratedInstrumentMetadata(
        isin="INE038A01020",
        company_legal_name="Hindalco Industries Limited",
        security_type="EQUITY",
        listing_date=date(1997, 1, 8),
        sector="Metals & Mining",
        industry="Metals & Mining",
        aegis_instrument_id="AEGIS-IN-000022",
    ),
    "HINDUNILVR": CuratedInstrumentMetadata(
        isin="INE030A01027",
        company_legal_name="Hindustan Unilever Limited",
        security_type="EQUITY",
        listing_date=date(1995, 7, 6),
        sector="Fast Moving Consumer Goods",
        industry="Fast Moving Consumer Goods",
        aegis_instrument_id="AEGIS-IN-000023",
    ),
    "ICICIBANK": CuratedInstrumentMetadata(
        isin="INE090A01021",
        company_legal_name="ICICI Bank Limited",
        security_type="EQUITY",
        listing_date=date(1997, 9, 17),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000024",
    ),
    "ITC": CuratedInstrumentMetadata(
        isin="INE154A01025",
        company_legal_name="ITC Limited",
        security_type="EQUITY",
        listing_date=date(1995, 8, 23),
        sector="Fast Moving Consumer Goods",
        industry="Fast Moving Consumer Goods",
        aegis_instrument_id="AEGIS-IN-000025",
    ),
    "INFY": CuratedInstrumentMetadata(
        isin="INE009A01021",
        company_legal_name="Infosys Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector="Information Technology",
        industry="Information Technology",
        aegis_instrument_id="AEGIS-IN-000026",
    ),
    "INDIGO": CuratedInstrumentMetadata(
        isin="INE646L01027",
        company_legal_name="InterGlobe Aviation Limited",
        security_type="EQUITY",
        listing_date=date(2015, 11, 10),
        sector="Services",
        industry="Services",
        aegis_instrument_id="AEGIS-IN-000027",
    ),
    "JSWSTEEL": CuratedInstrumentMetadata(
        isin="INE019A01038",
        company_legal_name="JSW Steel Limited",
        security_type="EQUITY",
        listing_date=date(2005, 3, 23),
        sector="Metals & Mining",
        industry="Metals & Mining",
        aegis_instrument_id="AEGIS-IN-000028",
    ),
    "JIOFIN": CuratedInstrumentMetadata(
        isin="INE758E01017",
        company_legal_name="Jio Financial Services Limited",
        security_type="EQUITY",
        listing_date=date(2023, 8, 21),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000029",
    ),
    "KOTAKBANK": CuratedInstrumentMetadata(
        isin="INE237A01036",
        company_legal_name="Kotak Mahindra Bank Limited",
        security_type="EQUITY",
        listing_date=date(1995, 12, 20),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000030",
    ),
    "LT": CuratedInstrumentMetadata(
        isin="INE018A01030",
        company_legal_name="Larsen & Toubro Limited",
        security_type="EQUITY",
        listing_date=date(2004, 6, 23),
        sector="Construction",
        industry="Construction",
        aegis_instrument_id="AEGIS-IN-000031",
    ),
    "M&M": CuratedInstrumentMetadata(
        isin="INE101A01026",
        company_legal_name="Mahindra & Mahindra Limited",
        security_type="EQUITY",
        listing_date=date(1996, 1, 3),
        sector="Automobile and Auto Components",
        industry="Automobile and Auto Components",
        aegis_instrument_id="AEGIS-IN-000032",
    ),
    "MARUTI": CuratedInstrumentMetadata(
        isin="INE585B01010",
        company_legal_name="Maruti Suzuki India Limited",
        security_type="EQUITY",
        listing_date=date(2003, 7, 9),
        sector="Automobile and Auto Components",
        industry="Automobile and Auto Components",
        aegis_instrument_id="AEGIS-IN-000033",
    ),
    "MAXHEALTH": CuratedInstrumentMetadata(
        isin="INE027H01010",
        company_legal_name="Max Healthcare Institute Limited",
        security_type="EQUITY",
        listing_date=date(2020, 8, 21),
        sector="Healthcare",
        industry="Healthcare",
        aegis_instrument_id="AEGIS-IN-000034",
    ),
    "NTPC": CuratedInstrumentMetadata(
        isin="INE733E01010",
        company_legal_name="NTPC Limited",
        security_type="EQUITY",
        listing_date=date(2004, 11, 5),
        sector="Power",
        industry="Power",
        aegis_instrument_id="AEGIS-IN-000035",
    ),
    "NESTLEIND": CuratedInstrumentMetadata(
        isin="INE239A01024",
        company_legal_name="Nestle India Limited",
        security_type="EQUITY",
        listing_date=date(2023, 8, 1),
        sector="Fast Moving Consumer Goods",
        industry="Fast Moving Consumer Goods",
        aegis_instrument_id="AEGIS-IN-000036",
    ),
    "ONGC": CuratedInstrumentMetadata(
        isin="INE213A01029",
        company_legal_name="Oil & Natural Gas Corporation Limited",
        security_type="EQUITY",
        listing_date=date(1995, 7, 19),
        sector="Oil Gas & Consumable Fuels",
        industry="Oil Gas & Consumable Fuels",
        aegis_instrument_id="AEGIS-IN-000037",
    ),
    "POWERGRID": CuratedInstrumentMetadata(
        isin="INE752E01010",
        company_legal_name="Power Grid Corporation of India Limited",
        security_type="EQUITY",
        listing_date=date(2007, 10, 5),
        sector="Power",
        industry="Power",
        aegis_instrument_id="AEGIS-IN-000038",
    ),
    "SBILIFE": CuratedInstrumentMetadata(
        isin="INE123W01016",
        company_legal_name="SBI Life Insurance Company Limited",
        security_type="EQUITY",
        listing_date=date(2017, 10, 3),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000039",
    ),
    "SHRIRAMFIN": CuratedInstrumentMetadata(
        isin="INE721A01047",
        company_legal_name="Shriram Finance Limited",
        security_type="EQUITY",
        listing_date=date(1996, 12, 11),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000040",
    ),
    "SBIN": CuratedInstrumentMetadata(
        isin="INE062A01020",
        company_legal_name="State Bank of India",
        security_type="EQUITY",
        listing_date=date(1995, 3, 1),
        sector="Financial Services",
        industry="Financial Services",
        aegis_instrument_id="AEGIS-IN-000041",
    ),
    "SUNPHARMA": CuratedInstrumentMetadata(
        isin="INE044A01036",
        company_legal_name="Sun Pharmaceutical Industries Limited",
        security_type="EQUITY",
        listing_date=date(1995, 2, 8),
        sector="Healthcare",
        industry="Healthcare",
        aegis_instrument_id="AEGIS-IN-000042",
    ),
    "TATACONSUM": CuratedInstrumentMetadata(
        isin="INE192A01025",
        company_legal_name="TATA CONSUMER PRODUCTS LIMITED",
        security_type="EQUITY",
        listing_date=date(1998, 11, 18),
        sector="Fast Moving Consumer Goods",
        industry="Fast Moving Consumer Goods",
        aegis_instrument_id="AEGIS-IN-000043",
    ),
    "TMPV": CuratedInstrumentMetadata(
        isin="INE155A01022",
        company_legal_name="Tata Motors Passenger Vehicles Limited",
        security_type="EQUITY",
        listing_date=date(1998, 7, 22),
        sector="Automobile and Auto Components",
        industry="Automobile and Auto Components",
        aegis_instrument_id="AEGIS-IN-000044",
    ),
    "TATASTEEL": CuratedInstrumentMetadata(
        isin="INE081A01020",
        company_legal_name="Tata Steel Limited",
        security_type="EQUITY",
        listing_date=date(1998, 11, 18),
        sector="Metals & Mining",
        industry="Metals & Mining",
        aegis_instrument_id="AEGIS-IN-000045",
    ),
    "TECHM": CuratedInstrumentMetadata(
        isin="INE669C01036",
        company_legal_name="Tech Mahindra Limited",
        security_type="EQUITY",
        listing_date=date(2006, 8, 28),
        sector="Information Technology",
        industry="Information Technology",
        aegis_instrument_id="AEGIS-IN-000046",
    ),
    "TITAN": CuratedInstrumentMetadata(
        isin="INE280A01028",
        company_legal_name="Titan Company Limited",
        security_type="EQUITY",
        listing_date=date(2004, 9, 24),
        sector="Consumer Durables",
        industry="Consumer Durables",
        aegis_instrument_id="AEGIS-IN-000047",
    ),
    "TRENT": CuratedInstrumentMetadata(
        isin="INE849A01020",
        company_legal_name="Trent Limited",
        security_type="EQUITY",
        listing_date=date(2004, 6, 7),
        sector="Consumer Services",
        industry="Consumer Services",
        aegis_instrument_id="AEGIS-IN-000048",
    ),
    "ULTRACEMCO": CuratedInstrumentMetadata(
        isin="INE481G01011",
        company_legal_name="UltraTech Cement Limited",
        security_type="EQUITY",
        listing_date=date(2004, 8, 24),
        sector="Construction Materials",
        industry="Construction Materials",
        aegis_instrument_id="AEGIS-IN-000049",
    ),
    "WIPRO": CuratedInstrumentMetadata(
        isin="INE075A01022",
        company_legal_name="Wipro Limited",
        security_type="EQUITY",
        listing_date=date(1995, 11, 8),
        sector="Information Technology",
        industry="Information Technology",
        aegis_instrument_id="AEGIS-IN-000050",
    ),
}

DEFAULT_BENCHMARK_TRADINGSYMBOL = "NIFTY 50"

# Kite Connect's historical-data endpoint caps how many days can be requested in a
# single call for the "day" interval. Verify this against the current Kite Connect
# API docs before relying on it -- it has changed across API versions.
MAX_DAY_INTERVAL_DAYS_PER_REQUEST = 2000

# Kite Connect's historical-data endpoint is rate-limited to 3 requests/second
# (per Kite's developer forum, verify against current docs). A 50-instrument
# universe with a multi-year lookback needs multiple chunked calls per
# instrument -- comfortably enough to trip that limit without throttling.
HISTORICAL_DATA_MIN_INTERVAL_SECONDS = 0.4


class KiteConnectMarketDataProvider:
    """Read-only Kite Connect market-data adapter.

    Deliberately exposes no order/holdings/margin methods (see __getattr__) and
    fails closed via _assert_configured() until a real api_key + daily access
    token have been supplied and a client constructed. See
    docs/data_activation_sprint/kite_connect_integration.md for the operational
    setup (subscription, key generation, daily login flow) and known gaps
    (Kite has no market-calendar or corporate-actions endpoint).
    """

    name = "kite_connect"
    data_source_mode = "LIVE_READONLY"
    broker_order_access = False

    @property
    def dataset_origin(self) -> str:
        # Only claim real data once there's an actual configured client behind
        # it. _assert_configured() already blocks every fetch_* call before
        # this matters, but stay honest defensively too.
        return "ACTUAL_PROVIDER_DATA" if self.configured else "FIXTURE_DATA"

    def __init__(
        self,
        *,
        client: KiteClientProtocol | None = None,
        tradingsymbols: list[str] | None = None,
        metadata: dict[str, CuratedInstrumentMetadata] | None = None,
        benchmark_tradingsymbol: str = DEFAULT_BENCHMARK_TRADINGSYMBOL,
        lookback_days: int = 3650,
        license_: ProviderLicense | None = None,
        configured: bool = False,
        historical_data_min_interval_seconds: float = HISTORICAL_DATA_MIN_INTERVAL_SECONDS,
    ) -> None:
        self._client = client
        # Injectable so this adapter is genuinely reusable for a second,
        # separately-curated universe (e.g. the Sector Screener) -- every
        # internal lookup below uses self._metadata, never the module-level
        # CURATED_INSTRUMENT_METADATA directly, so a caller passing a
        # different metadata dict + tradingsymbols list gets a fully correct
        # adapter, not one that silently resolves zero symbols.
        self._metadata = metadata if metadata is not None else CURATED_INSTRUMENT_METADATA
        self._tradingsymbols = tradingsymbols or list(self._metadata.keys())
        self._benchmark_tradingsymbol = benchmark_tradingsymbol
        self._lookback_days = lookback_days
        self._historical_data_min_interval_seconds = historical_data_min_interval_seconds
        self.configured = configured and client is not None
        self._license = license_ or ProviderLicense(
            provider_id="kite-connect",
            license_status=ProviderLicenseStatus.PENDING,
            permitted_use="read-only historical and EOD market data ingestion pending legal review",
            automation_rights=False,
            backtesting_rights=False,
            model_training_rights=False,
            dashboard_display_rights=False,
            data_retention_period="not-recorded",
            legal_review_status="PENDING_PROVIDER_SETUP",
        )
        self._instrument_cache: list[dict[str, Any]] | None = None
        self._last_historical_request_at: float | None = None

    def __getattr__(self, name: str) -> Any:
        blocked = {
            "place_order",
            "submit_order",
            "modify_order",
            "cancel_order",
            "get_holdings",
            "fetch_holdings",
            "mutate_holdings",
            "margins",
            "orders",
            "positions",
        }
        if name in blocked:
            raise AttributeError(
                f"{name} is prohibited: provider is DATA_SOURCE_MODE=LIVE_READONLY."
            )
        raise AttributeError(name)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def validate_read_only_scope(self) -> None:
        if self.broker_order_access:
            raise PermissionError(
                "BROKER_ORDER_ACCESS must remain false for read-only provider adapters."
            )

    def _assert_configured(self) -> None:
        self.validate_read_only_scope()
        if not self.configured or self._client is None:
            raise PermissionError(
                "Provider setup required: Kite Connect api_key and a valid, "
                "daily-refreshed access_token must be configured and verified "
                "before ingestion."
            )

    def _nse_instruments(self) -> list[dict[str, Any]]:
        if self._instrument_cache is None:
            self._instrument_cache = self._client.instruments("NSE")  # type: ignore[union-attr]
        return self._instrument_cache

    def _resolve_tradingsymbol(self, tradingsymbol: str) -> dict[str, Any] | None:
        for row in self._nse_instruments():
            if row.get("tradingsymbol") == tradingsymbol:
                return row
        return None

    def fetch_instruments(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        now = self._now().isoformat()
        payload: list[dict[str, Any]] = []
        unmapped: list[str] = []
        for symbol in self._tradingsymbols:
            curated = self._metadata.get(symbol)
            row = self._resolve_tradingsymbol(symbol)
            if curated is None or row is None:
                unmapped.append(symbol)
                continue
            payload.append(
                {
                    "aegis_instrument_id": curated.aegis_instrument_id,
                    "isin": curated.isin,
                    "company_legal_name": curated.company_legal_name,
                    "security_type": curated.security_type,
                    "current_symbol": row["tradingsymbol"],
                    "primary_exchange": row.get("exchange", "NSE"),
                    "listing_date": str(curated.listing_date),
                    "trading_status": "ACTIVE",
                    "sector": curated.sector,
                    "industry": curated.industry,
                    "currency": "INR",
                    "lot_size": int(row.get("lot_size", 1)),
                    "tick_size": float(row.get("tick_size", 0.05)),
                    "liquidity_classification": "UNKNOWN",
                    "mapping_confidence_score": 0.95,
                    "event_time": now,
                    "available_time": now,
                    "ingested_time": now,
                }
            )
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_instruments",
            schema_version="instruments.v1",
            source_reference="kite_connect://instruments/NSE",
            payload=payload,
            metadata={"unmapped_symbols": unmapped},
        )

    def _throttle_historical_request(self) -> None:
        if self._last_historical_request_at is not None:
            elapsed = time.monotonic() - self._last_historical_request_at
            remaining = self._historical_data_min_interval_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_historical_request_at = time.monotonic()

    def _fetch_day_candles(self, instrument_token: int) -> list[dict[str, Any]]:
        to_date = datetime.now(UTC).date()
        from_date = to_date - timedelta(days=self._lookback_days)
        candles: list[dict[str, Any]] = []
        chunk_start = from_date
        while chunk_start < to_date:
            chunk_end = min(
                chunk_start + timedelta(days=MAX_DAY_INTERVAL_DAYS_PER_REQUEST), to_date
            )
            self._throttle_historical_request()
            candles.extend(
                self._client.historical_data(  # type: ignore[union-attr]
                    instrument_token, chunk_start, chunk_end, "day"
                )
            )
            chunk_start = chunk_end + timedelta(days=1)
        return candles

    @staticmethod
    def _candle_date(candle: dict[str, Any]) -> tuple[str, str]:
        trade_date = candle["date"]
        if hasattr(trade_date, "date"):
            return trade_date.date().isoformat(), trade_date.isoformat()
        return str(trade_date), str(trade_date)

    def _historical_bars(
        self, tradingsymbol: str, aegis_instrument_id: str
    ) -> list[dict[str, Any]]:
        row = self._resolve_tradingsymbol(tradingsymbol)
        if row is None:
            return []
        now = self._now().isoformat()
        bars: list[dict[str, Any]] = []
        for candle in self._fetch_day_candles(row["instrument_token"]):
            trade_date_str, event_time = self._candle_date(candle)
            bars.append(
                {
                    "aegis_instrument_id": aegis_instrument_id,
                    "trade_date": trade_date_str,
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                    "volume": int(candle["volume"]),
                    "event_time": event_time,
                    "available_time": now,
                    "ingested_time": now,
                }
            )
        return bars

    def fetch_historical_eod_bars(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        payload: list[dict[str, Any]] = []
        for symbol in self._tradingsymbols:
            curated = self._metadata.get(symbol)
            if curated is None:
                continue
            payload.extend(self._historical_bars(symbol, curated.aegis_instrument_id))
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_historical_eod_bars",
            schema_version="eod_ohlcv.v1",
            source_reference=f"kite_connect://historical/day/lookback_{self._lookback_days}d",
            payload=payload,
            metadata={"interval": "day", "lookback_days": self._lookback_days},
        )

    def fetch_eod_prices(self) -> ProviderResponseEnvelope:
        return self.fetch_historical_eod_bars()

    def fetch_live_quotes(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        instrument_keys = [
            f"NSE:{symbol}"
            for symbol in self._tradingsymbols
            if symbol in self._metadata
        ]
        quotes = self._client.quote(instrument_keys) if instrument_keys else {}  # type: ignore[union-attr]
        now = self._now().isoformat()
        payload: list[dict[str, Any]] = []
        for key, data in quotes.items():
            symbol = key.split(":", 1)[-1]
            curated = self._metadata.get(symbol)
            if curated is None:
                continue
            depth = data.get("depth", {})
            best_bid = (depth.get("buy") or [{}])[0].get("price")
            best_ask = (depth.get("sell") or [{}])[0].get("price")
            payload.append(
                {
                    "aegis_instrument_id": curated.aegis_instrument_id,
                    "exchange": "NSE",
                    "last_price": float(data.get("last_price", 0.0)),
                    "bid_price": best_bid,
                    "ask_price": best_ask,
                    "last_traded_quantity": data.get("last_quantity"),
                    "volume": data.get("volume"),
                    "event_time": now,
                    "available_time": now,
                    "ingested_time": now,
                }
            )
        return ProviderResponseEnvelope(
            provider_name=self.name,
            endpoint="fetch_live_quotes",
            schema_version="live_quotes.v1",
            source_reference="kite_connect://quotes/nse",
            payload=payload,
            metadata={"mode": self.data_source_mode, "transport": "poll_readonly"},
        )

    def fetch_market_calendar(self) -> ProviderResponseEnvelope:
        # Kite Connect has no market-holiday/session-calendar endpoint. Do not
        # fabricate one here -- source the trading calendar from a separate
        # governed input via csv_provider.py per
        # docs/data_activation_sprint/market_calendar_governance.md.
        self._assert_configured()
        return ProviderResponseEnvelope(
            self.name,
            "fetch_market_calendar",
            "market_calendar.v1",
            [],
            "kite_connect://unsupported/market_calendar",
            metadata={"note": "Kite Connect exposes no calendar endpoint; use CSV import."},
        )

    def fetch_corporate_actions(self) -> ProviderResponseEnvelope:
        # Same reasoning as fetch_market_calendar: no real endpoint, no fabrication.
        self._assert_configured()
        return ProviderResponseEnvelope(
            self.name,
            "fetch_corporate_actions",
            "corporate_actions.v1",
            [],
            "kite_connect://unsupported/corporate_actions",
            metadata={
                "note": "Kite Connect exposes no corporate-actions endpoint; use CSV import."
            },
        )

    def _resolve_benchmark(self) -> dict[str, Any] | None:
        for row in self._nse_instruments():
            if row.get("tradingsymbol") == self._benchmark_tradingsymbol:
                return row
        return None

    def fetch_benchmark_data(self) -> ProviderResponseEnvelope:
        self._assert_configured()
        now = self._now().isoformat()
        row = self._resolve_benchmark()
        payload: list[dict[str, Any]] = []
        if row is not None:
            for candle in self._fetch_day_candles(row["instrument_token"]):
                trade_date_str, event_time = self._candle_date(candle)
                payload.append(
                    {
                        "benchmark_symbol": self._benchmark_tradingsymbol,
                        "trade_date": trade_date_str,
                        "open": float(candle["open"]),
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "close": float(candle["close"]),
                        "event_time": event_time,
                        "available_time": now,
                        "ingested_time": now,
                    }
                )
        return ProviderResponseEnvelope(
            self.name,
            "fetch_benchmark_data",
            "benchmark_eod.v1",
            payload,
            "kite_connect://historical/benchmark",
        )

    def fetch_fundamentals(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_fundamentals",
            "fundamentals.v1",
            [],
            "kite_connect://unsupported/fundamentals",
        )

    def fetch_filings(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_filings", "filings.v1", [], "kite_connect://unsupported/filings"
        )

    def fetch_index_membership(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name,
            "fetch_index_membership",
            "index_membership.v1",
            [],
            "kite_connect://unsupported/index_membership",
        )

    def fetch_macro_data(self) -> ProviderResponseEnvelope:
        return ProviderResponseEnvelope(
            self.name, "fetch_macro_data", "macro.v1", [], "kite_connect://unsupported/macro"
        )

    def get_source_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "data_source_mode": self.data_source_mode,
            "broker_order_access": self.broker_order_access,
            "configured": self.configured,
            "tradingsymbols": list(self._tradingsymbols),
            "capabilities": [
                "instrument_master_subset",
                "historical_eod_ohlcv",
                "live_quotes",
                "benchmark_eod",
            ],
            "unsupported": [
                "market_calendar",
                "corporate_actions",
                "fundamentals",
                "filings",
                "index_membership",
                "macro",
            ],
        }

    def get_license_status(self) -> ProviderLicense | None:
        return self._license

    def get_health_status(self) -> ProviderHealthResult:
        if not self.configured or self._client is None:
            return ProviderHealthResult(
                healthy=False,
                message="Provider setup required: Kite Connect api_key and access_token are not configured.",
                checked_at=self._now(),
                latency_ms=None,
                mode=self.data_source_mode,
                order_access=self.broker_order_access,
            )
        started = self._now()
        try:
            self._client.profile()
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the caller
            return ProviderHealthResult(
                healthy=False,
                message=f"Kite Connect health check failed: {exc}",
                checked_at=self._now(),
                latency_ms=None,
                mode=self.data_source_mode,
                order_access=self.broker_order_access,
            )
        latency_ms = (self._now() - started).total_seconds() * 1000
        return ProviderHealthResult(
            healthy=True,
            message="Kite Connect read-only market data provider healthy; broker order access disabled",
            checked_at=self._now(),
            latency_ms=latency_ms,
            mode=self.data_source_mode,
            order_access=self.broker_order_access,
        )
