from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.data_ingestion.service import InMemoryRepository, LocalObjectStore, ProviderIngestionService
from aegis.provider_adapters.mock_provider import MockMarketDataProvider


audit = AuditLog()
repo = InMemoryRepository()
service = ProviderIngestionService(
    object_store=LocalObjectStore(Path("work/object_store")),
    repository=repo,
    audit_log=audit,
)
run = service.ingest_eod_prices(
    provider=MockMarketDataProvider(),
    provider_id="mock-provider",
    dataset_id="eod-prices",
    dataset_name="eod_prices",
    known_instrument_ids={"AEGIS-IN-000001"},
)
print(run)
