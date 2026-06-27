# Reuse Matrix

| Capability | Reused Module |
| --- | --- |
| Provider licensing | `ProviderLicense`, `ProviderLicenseGuard` |
| Raw object storage | `LocalObjectStore` |
| Dataset versioning | `DatasetVersion`, `InMemoryRepository.dataset_versions` |
| Data quality | `validate_eod_ohlcv`, `derive_validation_status` |
| Instrument master | `InstrumentMasterService` |
| Corporate actions | `CorporateAction` domain model |
| Market calendar | `sync_market_calendar`, fixture calendar services |
| Audit logging | `AuditLog` |
| Workers | Existing worker entrypoint and script pattern |
| Dashboard rendering | Next.js dashboard components |
| Fixtures | `sample_data/*`, now extended by `sample_data/data_activation` |
| Research eligibility | Dataset validation status and truth layer |
