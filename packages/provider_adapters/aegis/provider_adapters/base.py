from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from aegis.domain.models import ProviderLicense


@dataclass(frozen=True)
class ProviderHealthResult:
    healthy: bool
    message: str
    checked_at: datetime | None = None
    latency_ms: float | None = None
    mode: str = "LOCAL_FIXTURE"
    order_access: bool = False


@dataclass(frozen=True)
class ProviderResponseEnvelope:
    provider_name: str
    endpoint: str
    schema_version: str
    payload: list[dict[str, Any]]
    source_reference: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MarketDataProvider(Protocol):
    name: str

    def fetch_instruments(self) -> ProviderResponseEnvelope: ...
    def fetch_eod_prices(self) -> ProviderResponseEnvelope: ...
    def fetch_live_quotes(self) -> ProviderResponseEnvelope: ...
    def fetch_market_calendar(self) -> ProviderResponseEnvelope: ...
    def fetch_corporate_actions(self) -> ProviderResponseEnvelope: ...
    def fetch_fundamentals(self) -> ProviderResponseEnvelope: ...
    def fetch_filings(self) -> ProviderResponseEnvelope: ...
    def fetch_index_membership(self) -> ProviderResponseEnvelope: ...
    def fetch_macro_data(self) -> ProviderResponseEnvelope: ...
    def get_source_metadata(self) -> dict[str, Any]: ...
    def get_license_status(self) -> ProviderLicense | None: ...
    def get_health_status(self) -> ProviderHealthResult: ...


class ProviderAdapterRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MarketDataProvider] = {}

    def register(self, provider: MarketDataProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> MarketDataProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Provider is not registered: {name}") from exc

    def list(self) -> list[MarketDataProvider]:
        return list(self._providers.values())
