from __future__ import annotations

from pathlib import Path

import pytest
from aegis.audit.service import AuditLog
from aegis.configuration.settings import Settings
from aegis.data_ingestion.service import (
    InMemoryRepository,
    LocalObjectStore,
    ProviderIngestionService,
)
from aegis.domain.models import IngestionStatus
from aegis.instrument_master.service import InstrumentMasterService
from aegis.provider_adapters.live_readonly_provider import LiveReadOnlyMarketDataProvider


def test_broker_order_access_is_rejected_at_startup() -> None:
    settings = Settings(
        environment="development",
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        minio_endpoint="http://localhost:9000",
        minio_access_key="x",
        minio_secret_key="y",
        minio_bucket="bucket",
        jwt_secret="secret",
        log_level="INFO",
        broker_order_access=True,
        data_source_mode="LIVE_READONLY",
    )
    with pytest.raises(ValueError, match="BROKER_ORDER_ACCESS"):
        settings.validate_startup()


def test_live_readonly_provider_exposes_no_order_methods() -> None:
    provider = LiveReadOnlyMarketDataProvider()
    assert provider.data_source_mode == "LIVE_READONLY"
    assert provider.broker_order_access is False
    health = provider.get_health_status()
    assert health.order_access is False
    assert health.healthy is False
    assert "Provider setup required" in health.message
    for forbidden in (
        "place_order",
        "submit_order",
        "cancel_order",
        "modify_order",
        "fetch_holdings",
        "mutate_holdings",
    ):
        assert not hasattr(provider, forbidden)


def test_live_readonly_ingestion_creates_governed_layers(tmp_path: Path) -> None:
    audit_log = AuditLog()
    repo = InMemoryRepository()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(tmp_path),
        repository=repo,
        audit_log=audit_log,
    )
    instrument_master = InstrumentMasterService()
    provider = LiveReadOnlyMarketDataProvider(configured=True)

    health = service.check_provider_health(provider=provider, provider_id="provider-live-readonly")
    instruments = service.sync_instrument_master(
        provider=provider, provider_id="provider-live-readonly", instrument_master=instrument_master
    )
    eod = service.ingest_eod_prices(
        provider=provider,
        provider_id="provider-live-readonly",
        dataset_id="dataset-eod",
        dataset_name="eod_prices",
        known_instrument_ids=instrument_master.known_aegis_ids(),
    )
    quotes = service.ingest_live_quotes(
        provider=provider,
        provider_id="provider-live-readonly",
        dataset_id="dataset-quotes",
        known_instrument_ids=instrument_master.known_aegis_ids(),
    )
    calendar = service.sync_market_calendar(provider=provider, provider_id="provider-live-readonly")

    assert health["mode"] == "LIVE_READONLY"
    assert health["order_access"] is False
    assert instruments.status == IngestionStatus.COMPLETED
    assert eod.status == IngestionStatus.COMPLETED
    assert quotes.status == IngestionStatus.COMPLETED
    assert calendar.status == IngestionStatus.COMPLETED
    assert len(repo.raw_objects) == 4
    assert len(repo.layer_objects["normalized"]) == 4
    assert len(repo.layer_objects["curated"]) == 4
    assert repo.data_freshness["live_quotes"]["status"] == "FRESH"
    assert repo.live_quotes
    assert repo.market_calendar
    assert any(
        event.event_type == "LIVE_QUOTES_INGESTED_READONLY" for event in audit_log.list_events()
    )
