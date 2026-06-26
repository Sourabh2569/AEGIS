# Sprint 1A Architecture Mapping

Sprint 0 was implemented as a runnable scaffold with in-memory repositories. Sprint 1A preserves that shape and adds compatible in-memory repositories plus SQL migration sketches.

Mapping:

- Sprint 0 `AuditLog` remains the global audit-event integration point.
- Sprint 0 `Role` enum is reused for authorization.
- Sprint 0 `DatasetVersion` and `ProviderLicense` dataclasses are reused by Sprint 1A eligibility guards.
- Sprint 0 `Instrument` and `aegis_instrument_id` remain the simulation identity source.
- Sprint 0 local object storage conventions remain separate from the Sprint 1A market-data reader.
- Sprint 1A adds read-only `MarketDataReader` and `TradingCalendarReader`; the engine does not call provider adapters.

Deviation:

- The contract requests database models and background jobs. The current repository does not yet have real SQLAlchemy repositories or a queue. Sprint 1A therefore implements deterministic in-memory repositories and a synchronous idempotent job runner compatible with later persistence.
