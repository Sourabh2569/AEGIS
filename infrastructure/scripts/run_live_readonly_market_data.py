from __future__ import annotations

from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.data_ingestion.service import InMemoryRepository, LocalObjectStore, ProviderIngestionService
from aegis.instrument_master.service import InstrumentMasterService
from aegis.provider_adapters.live_readonly_provider import LiveReadOnlyMarketDataProvider


def main() -> None:
    audit_log = AuditLog()
    repository = InMemoryRepository()
    instrument_master = InstrumentMasterService()
    service = ProviderIngestionService(
        object_store=LocalObjectStore(Path("work/live_readonly_object_store")),
        repository=repository,
        audit_log=audit_log,
    )
    provider = LiveReadOnlyMarketDataProvider()
    provider_id = "live-readonly-provider"

    health = service.check_provider_health(provider=provider, provider_id=provider_id)
    instruments = service.sync_instrument_master(provider=provider, provider_id=provider_id, instrument_master=instrument_master)
    eod = service.ingest_eod_prices(
        provider=provider,
        provider_id=provider_id,
        dataset_id="dataset-eod-prices",
        dataset_name="eod_prices",
        known_instrument_ids=instrument_master.known_aegis_ids(),
    )
    quotes = service.ingest_live_quotes(
        provider=provider,
        provider_id=provider_id,
        dataset_id="dataset-live-quotes",
        known_instrument_ids=instrument_master.known_aegis_ids(),
    )
    calendar = service.sync_market_calendar(provider=provider, provider_id=provider_id)

    print("AEGIS live-readonly market data integration")
    print(f"mode={health['mode']} broker_order_access={health['order_access']} healthy={health['healthy']}")
    print(f"instruments={instruments.records_accepted} eod={eod.records_accepted} quotes={quotes.records_accepted} calendar={calendar.records_accepted}")
    print(f"raw_objects={len(repository.raw_objects)} normalized_objects={len(repository.layer_objects['normalized'])} curated_objects={len(repository.layer_objects['curated'])}")
    print(f"freshness={repository.data_freshness.get('live_quotes', {}).get('status')}")
    print(f"audit_events={len(audit_log.list_events())}")


if __name__ == "__main__":
    main()
