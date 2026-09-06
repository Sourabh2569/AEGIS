from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
# fabricated here. Only add entries you have verified against an authoritative
# source (e.g. the NSE instrument master / MCA filings) -- an unmapped symbol is
# skipped and reported via metadata["unmapped_symbols"] rather than guessed.
CURATED_INSTRUMENT_METADATA: dict[str, CuratedInstrumentMetadata] = {
    "RELIANCE": CuratedInstrumentMetadata(
        isin="INE002A01018",
        company_legal_name="Reliance Industries Limited",
        security_type="EQUITY",
        listing_date=date(1995, 1, 1),
        sector="Energy",
        industry="Oil, Gas and Consumable Fuels",
        aegis_instrument_id="AEGIS-IN-000001",
    ),
    "TCS": CuratedInstrumentMetadata(
        isin="INE467B01029",
        company_legal_name="Tata Consultancy Services Limited",
        security_type="EQUITY",
        listing_date=date(2004, 8, 25),
        sector="Information Technology",
        industry="IT Services",
        aegis_instrument_id="AEGIS-IN-000002",
    ),
}

DEFAULT_BENCHMARK_TRADINGSYMBOL = "NIFTY 50"

# Kite Connect's historical-data endpoint caps how many days can be requested in a
# single call for the "day" interval. Verify this against the current Kite Connect
# API docs before relying on it -- it has changed across API versions.
MAX_DAY_INTERVAL_DAYS_PER_REQUEST = 2000


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

    def __init__(
        self,
        *,
        client: KiteClientProtocol | None = None,
        tradingsymbols: list[str] | None = None,
        benchmark_tradingsymbol: str = DEFAULT_BENCHMARK_TRADINGSYMBOL,
        lookback_days: int = 3650,
        license_: ProviderLicense | None = None,
        configured: bool = False,
    ) -> None:
        self._client = client
        self._tradingsymbols = tradingsymbols or list(CURATED_INSTRUMENT_METADATA.keys())
        self._benchmark_tradingsymbol = benchmark_tradingsymbol
        self._lookback_days = lookback_days
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
        return datetime.now(timezone.utc)

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
            curated = CURATED_INSTRUMENT_METADATA.get(symbol)
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

    def _fetch_day_candles(self, instrument_token: int) -> list[dict[str, Any]]:
        to_date = date.today()
        from_date = to_date - timedelta(days=self._lookback_days)
        candles: list[dict[str, Any]] = []
        chunk_start = from_date
        while chunk_start < to_date:
            chunk_end = min(
                chunk_start + timedelta(days=MAX_DAY_INTERVAL_DAYS_PER_REQUEST), to_date
            )
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
            curated = CURATED_INSTRUMENT_METADATA.get(symbol)
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
            if symbol in CURATED_INSTRUMENT_METADATA
        ]
        quotes = self._client.quote(instrument_keys) if instrument_keys else {}  # type: ignore[union-attr]
        now = self._now().isoformat()
        payload: list[dict[str, Any]] = []
        for key, data in quotes.items():
            symbol = key.split(":", 1)[-1]
            curated = CURATED_INSTRUMENT_METADATA.get(symbol)
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
